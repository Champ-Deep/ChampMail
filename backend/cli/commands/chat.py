"""
champmail chat — Conversational AI interface for ChampMail.

A stateful, chat-based shell that understands the full outreach workflow.
Runs entirely independently — no Claude, no external AI agent required.
Uses your configured OpenRouter key to power the conversation.

The assistant:
  - Knows the ChampMail setup flow (domain → smtp → imap → prospect → campaign)
  - Guides you through the outreach pipeline step by step
  - Can invoke CLI actions inline during conversation
  - Remembers context within the session
  - Has a defined flow but handles freeform questions too

Run:
    champmail chat           # start conversational session
    champmail chat --setup   # start with setup wizard
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import textwrap
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import click

from cli.config_store import (
    apply_to_runtime, get_section, get_value, load_config, set_section, sync_to_env,
)
from cli.repl_skin import (
    make_prompt_session, print_error, print_info,
    print_success, print_warning,
)
from cli.session import (
    SESSION_DIR, get_email as get_session_email,
    get_role, is_logged_in, load_session,
)


# ── Animated intro ─────────────────────────────────────────────────────────────

CHAT_BANNER_FRAMES = [
    """\033[1;36m
  ╔═══════════════════════════════════════════╗
  ║         C H A M P M A I L                ║
  ║    AI Cold-Email Outreach Platform        ║
  ╚═══════════════════════════════════════════╝
\033[0m""",
    """\033[1;36m
  ╔═══════════════════════════════════════════╗
  ║    ✉  C H A M P M A I L  ✉              ║
  ║    AI Cold-Email Outreach Platform        ║
  ╚═══════════════════════════════════════════╝
\033[0m""",
    """\033[1;35m
  ╔═══════════════════════════════════════════╗
  ║  ✦  C H A M P M A I L  ✦               ║
  ║    AI Cold-Email Outreach Platform        ║
  ╚═══════════════════════════════════════════╝
\033[0m""",
    """\033[1;36m
  ╔═══════════════════════════════════════════╗
  ║    ⚡ C H A M P M A I L ⚡              ║
  ║    AI Cold-Email Outreach Platform        ║
  ╚═══════════════════════════════════════════╝
\033[0m""",
]

LOADING_CHARS = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


def _animate_banner(steps: int = 3, fps: float = 8) -> None:
    """Show animated intro banner."""
    delay = 1.0 / fps
    for i in range(steps * len(CHAT_BANNER_FRAMES)):
        frame = CHAT_BANNER_FRAMES[i % len(CHAT_BANNER_FRAMES)]
        sys.stdout.write("\033[2J\033[H")   # clear screen + move to top
        sys.stdout.write(frame)
        sys.stdout.flush()
        time.sleep(delay)
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


def _show_intro(user_email: Optional[str]) -> None:
    """Show the final static banner + welcome message."""
    # Animate
    _animate_banner(steps=2, fps=10)

    # Final state
    sys.stdout.write("\033[1;36m")
    sys.stdout.write("""
  ██████╗██╗  ██╗ █████╗ ███╗   ███╗██████╗ ███╗   ███╗ █████╗ ██╗██╗
 ██╔════╝██║  ██║██╔══██╗████╗ ████║██╔══██╗████╗ ████║██╔══██╗██║██║
 ██║     ███████║███████║██╔████╔██║██████╔╝██╔████╔██║███████║██║██║
 ██║     ██╔══██║██╔══██║██║╚██╔╝██║██╔═══╝ ██║╚██╔╝██║██╔══██║██║██║
 ╚██████╗██║  ██║██║  ██║██║ ╚═╝ ██║██║     ██║ ╚═╝ ██║██║  ██║██║███████╗
  ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝     ╚═╝     ╚═╝╚═╝  ╚═╝╚═╝╚══════╝
""")
    sys.stdout.write("\033[0m")
    sys.stdout.write("\033[36m  AI-Powered Cold-Email Outreach · Conversational Mode\033[0m\n")
    sys.stdout.write(f"\033[2m  Session: {user_email or 'not logged in'}  ·  Type 'help' or just start talking\033[0m\n")
    sys.stdout.write("\033[2m  Ctrl+C or 'exit' to quit\033[0m\n\n")
    sys.stdout.flush()


def _spinner(msg: str, duration: float = 1.5) -> None:
    """Show a short spinner while AI is thinking."""
    delay = 0.08
    steps = int(duration / delay)
    for i in range(steps):
        ch = LOADING_CHARS[i % len(LOADING_CHARS)]
        sys.stdout.write(f"\r\033[36m  {ch}  {msg}\033[0m")
        sys.stdout.flush()
        time.sleep(delay)
    sys.stdout.write("\r" + " " * (len(msg) + 10) + "\r")
    sys.stdout.flush()


def _thinking(msg: str = "Thinking") -> None:
    _spinner(msg + "...", duration=0.5)


# ── Chat engine ────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are ChampMail Assistant — the built-in conversational AI for ChampMail, an AI-powered cold-email outreach platform.

You are NOT Claude. You are ChampMail's own assistant. You help users configure and use ChampMail entirely through conversation — NO terminal commands needed.

## CRITICAL RULE — Never tell users to run commands
NEVER say things like "run champmail setup smtp" or "use the CLI to configure".
You ARE the interface. You collect values through conversation and the system saves them automatically.
When a user wants to set something up, ASK them for the values directly in chat.

## Your guided flows

### Setup flow (when user wants to set up or configure)
Ask for values one section at a time. After each section is complete, confirm it's saved and move to the next.

**SMTP setup** — ask:
1. "What's your SMTP host?" (e.g. smtp.gmail.com, smtp.ethereal.email)
2. "Which port? (587 for TLS, 465 for SSL, 25 for plain)"
3. "Your SMTP username / login email?"
4. "Your SMTP password?"
5. "What name should appear as the sender? (e.g. 'Alex from Acme')"
After collecting all 5 → say: SAVE_SMTP:{host}|{port}|{username}|{password}|{from_name}

**IMAP setup** — ask:
1. "IMAP host? (usually imap.yourprovider.com)"
2. "IMAP port? (993 for SSL)"
3. "IMAP username?"
4. "IMAP password?"
After collecting → say: SAVE_IMAP:{host}|{port}|{username}|{password}

**Domain setup** — ask:
1. "What sending domain are you using? (e.g. outreach.yourcompany.com)"
2. "DNS provider? (cloudflare, route53, godaddy, other)"
After collecting → say: SAVE_DOMAIN:{name}|{provider}

**AI setup** — ask:
1. "Your OpenRouter API key? (starts with sk-or-v1-...)"
2. "Which model? (default: openai/gpt-4.1-mini)"
After collecting → say: SAVE_AI:{key}|{model}

**Campaign defaults** — ask:
1. "Your name as it appears in outreach emails? (e.g. 'Alex, Head of Growth')"
2. "Your from-email address?"
3. "Daily sending limit? (default: 50)"
4. "Default goal? (e.g. 'book a demo call')"
5. "Preferred tone? (casual / professional / friendly)"
After collecting → say: SAVE_CAMPAIGN:{from_name}|{from_email}|{daily_limit}|{goal}|{tone}

**Prospect defaults** — ask:
1. "Default industry for prospects? (e.g. SaaS, Fintech, E-commerce)"
2. "Default lead source? (e.g. linkedin, website, referral)"
After collecting → say: SAVE_PROSPECT:{industry}|{source}

### Outreach flow (when user wants to reach out to someone)
Ask these questions one or two at a time — be natural, not robotic:
1. "What email address should this be sent FROM? And what's your name and role/position?"
   (e.g. "rajesh@lakeb2b.com — Rajesh, Sales Executive at LakeB2B")
2. "Who do you want to reach out to? Give me their email address."
3. "What's their full name, job title, and company?"
4. "Do you have their phone number or LinkedIn profile? (optional but helps with research)"
5. "What industry are they in?"
6. "What's your goal with this email? (e.g. book a demo, introduce a product)"
7. "What problem or pain point are you solving for them?"
8. "What's your value proposition in one sentence?"
9. "Any extra context? (e.g. they just raised funding, recently hired, spoke at a conference)"
10. "What's your call to action? (e.g. '15-min call this week?')"
11. "What tone? (casual / professional / friendly)"
After collecting ALL fields → your response MUST end with this exact token on its own line:
RUN_OUTREACH:{email}|{first}|{last}|{title}|{company}|{domain}|{industry}|{goal}|{pain}|{value}|{context}|{cta}|{tone}|{phone}|{linkedin}|{sender_name}|{sender_position}|{sender_company}|{sender_email}

Where:
- {sender_name}: The sender's name (e.g. "Rajesh")
- {sender_position}: The sender's role/position (e.g. "Sales Executive")
- {sender_company}: The sender's company (e.g. "LakeB2B")
- {sender_email}: The from email address (e.g. "rajesh@lakeb2b.com")

CRITICAL: Never say "I'm sending it now" or "email sent" — the system sends it automatically when it sees the token. Just say "Launching outreach pipeline now!" before the token line, then stop.
Never promise to "notify" the user — the pipeline runs live and they'll see real-time progress directly.
Skip any field the user says is unavailable — use empty string for missing values.
ALWAYS ask for sender name, position, company, and from-email FIRST before prospect details.

### Custom / manual email (when user provides exact email content to send)

If the user writes or dictates the exact email they want sent (not a campaign-style outreach), OR asks you to compose a specific type of email (data enrichment, follow-up, introduction, etc.) and provides/confirms the content, use the SEND_CUSTOM token instead of RUN_OUTREACH.

Ask:
1. "Who should I send this to? (email address)" — if not already known
2. Confirm the subject line and body with the user before sending
3. After confirmation, emit on its own line:
SEND_CUSTOM:{to_email}|{subject}|{body_text}

Where body_text uses \\n for newlines. Keep the exact wording the user provided or confirmed.

CRITICAL: Use SEND_CUSTOM (not RUN_OUTREACH) when:
- The user gives you a specific email to send verbatim
- The user asks for a non-campaign email (data enrichment, introduction request, feedback request, etc.)
- The user says "send this" or provides the subject and body directly
- The user customizes a template you suggested and says "send it"

### Batch outreach (when user wants to reach out to multiple prospects from a CSV)

If the user says "batch outreach", "send to multiple prospects", "run campaign on CSV", "upload a prospect list", "I have a CSV of prospects", or mentions reaching out to multiple people:

1. Ask: "What's the path to your CSV file? (must have an 'email' column; optional: first_name, last_name, title, company_name, company_domain, industry, phone, linkedin_url)"
2. Ask the same campaign questions as single outreach (goal, pain point, value prop, CTA, tone, sender name, from email) — these apply to ALL prospects
3. Ask: "Should I send the emails right away, or just prepare drafts?" (skip-send or send)
After collecting ALL fields → emit on its own line:
RUN_BATCH:{csv_path}|{goal}|{pain_point}|{value_prop}|{cta}|{tone}|{sender}|{from_email}|{context}|{skip_send}

Where:
- {csv_path}: Full path to the CSV file
- {skip_send}: "true" if user wants drafts only, "false" to send immediately
- Other fields same as single outreach

CRITICAL: The CSV is processed locally — the user must provide a valid file path on their machine.
Tell the user how many prospects were found and that the pipeline will run for each one sequentially.

### Prospect import from CSV (when user wants to import prospects from a CSV file)

If the user says "import prospects", "add prospects from CSV", "upload prospects", "bulk import", "load prospects from file", or wants to add multiple prospects at once:

1. Ask: "What's the full path to your CSV file? (must have an 'email' column; optional: first_name, last_name, title, company_name, company_domain, industry, phone, linkedin_url)"
2. Once the user provides the path, emit on its own line:
IMPORT_PROSPECTS:{csv_path}

CRITICAL: After importing, tell the user how many prospects were processed and that they can now run outreach for any of them.

### Campaign reference documents (when user wants to add, list, search, or remove docs)

Campaign docs are reference materials (product sheets, pricing guides, brand docs) that get ingested into the knowledge graph. Once ingested, they are **automatically referenced** during email generation to produce detailed, accurate emails with real data points.

**Add a document** — if user says "add a document", "ingest this doc", "upload reference", "add campaign doc", or provides a file path to ingest:
1. Ask for the file path if not provided: "What's the full path to the document? (supports .docx, .txt, .pdf)"
2. Ask for an optional title: "Any title for this document? (or I'll use the filename)"
After collecting → emit on its own line:
INGEST_DOC:{file_path}|{title}

**List documents** — if user says "list docs", "show documents", "what docs are ingested", "campaign docs":
Emit on its own line:
LIST_DOCS

**Search documents** — if user says "search docs for X", "find in docs", "look up X in reference docs":
Ask for the search query if not clear, then emit on its own line:
SEARCH_DOCS:{query}

**Remove a document** — if user says "remove doc X", "delete document X":
Ask for the doc ID if not provided (tell them to run list first), then emit on its own line:
REMOVE_DOC:{doc_id}

CRITICAL: After ingesting a doc, tell the user it will be automatically used when generating emails for matching campaigns. They don't need to reference it manually.

### Status & monitoring (when user asks about status, replies, or connections)

**Outreach status** — if user says "outreach status", "check status for X", "what's happening with X", "show me the pipeline for X":
Ask for email if not provided, then emit on its own line:
RUN_STATUS:{email}

**Check replies** — if user says "show replies", "any replies from X", "check inbox for X", "did X reply":
Ask for email if not provided, then emit on its own line:
RUN_REPLIES:{email}

**View research** — if user says "show research for X", "what do we know about X", "view research", "show me the research":
Ask for email if not provided, then emit on its own line:
VIEW_RESEARCH:{email}

**Verify SMTP** — if user says "test smtp", "verify smtp", "check email connection", "is smtp working":
Emit on its own line:
RUN_VERIFY:smtp

**Check IMAP inbox** — if user says "test imap", "check imap", "check inbox", "show my inbox":
Emit on its own line:
RUN_IMAP_CHECK

CRITICAL: These tokens MUST appear on their own line. The system executes them automatically and shows live output.
Never say "I can't check that" or "check your dashboard" — you CAN check it via these tokens.

## Conversation style
- Be warm, concise, and direct. Like a helpful colleague, not a manual.
- Ask ONE question at a time unless grouping small related ones.
- When a section is saved, celebrate it briefly: "✓ SMTP saved! Moving on..."
- If user says "hi" or "let's get started" → ask what they want to do: set up the platform or send an outreach email?
- If setup is incomplete, guide them through setup first before outreach.
- NEVER say you'll notify the user later — everything happens live in the terminal.

## Current configuration status
{context}
"""


def _build_context() -> str:
    """Build a context string from stored config and session."""
    cfg = load_config()
    session = load_session()
    lines = []

    lines.append(f"Logged in as: {session.get('email', 'not logged in')} (role: {session.get('role', 'unknown')})")

    domain = cfg.get("domain", {})
    if domain.get("name"):
        lines.append(f"Sending domain: {domain['name']} ({domain.get('provider', '')})")
    else:
        lines.append("Sending domain: NOT CONFIGURED")

    smtp = cfg.get("smtp", {})
    if smtp.get("host") and smtp["host"] != "localhost":
        lines.append(f"SMTP: {smtp['host']}:{smtp.get('port', 587)} as {smtp.get('username', '')}")
    else:
        lines.append("SMTP: NOT CONFIGURED")

    imap = cfg.get("imap", {})
    if imap.get("host") and imap["host"] != "localhost":
        lines.append(f"IMAP: {imap['host']}:{imap.get('port', 993)}")
    else:
        lines.append("IMAP: NOT CONFIGURED")

    ai = cfg.get("ai", {})
    if ai.get("openrouter_api_key"):
        lines.append(f"AI model: {ai.get('model', 'openai/gpt-4.1-mini')} (key configured)")
    else:
        lines.append("AI: NOT CONFIGURED (no OpenRouter key)")

    camp = cfg.get("campaign_defaults", {})
    if camp.get("from_email"):
        lines.append(f"Campaign from: {camp.get('from_name', '')} <{camp['from_email']}>")

    return "\n".join(lines)


def _get_api_key() -> Optional[str]:
    """Get OpenRouter key: config store → os.environ → pydantic settings."""
    # Config store is always freshest (user ran `setup ai`)
    key = get_value("ai", "openrouter_api_key")
    if key:
        return key
    # Try env (may have been set before lru_cache froze)
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if key:
        return key
    # Last resort: re-read .env directly to bypass lru_cache
    try:
        env_candidates = [
            Path(__file__).parent.parent.parent.parent / ".env",
            Path(__file__).parent.parent.parent / ".env",
        ]
        for p in env_candidates:
            if p.exists():
                for line in p.read_text().splitlines():
                    if line.startswith("OPENROUTER_API_KEY="):
                        val = line.split("=", 1)[1].strip()
                        if val:
                            return val
    except Exception:
        pass
    return None


def _get_model() -> str:
    return get_value("ai", "model") or os.environ.get("GENERAL_MODEL") or "openai/gpt-4.1-mini"


async def _chat_completion(messages: list[dict], stream: bool = True) -> str:
    """Call OpenRouter chat completions, optionally streaming output."""
    import httpx

    api_key = _get_api_key()
    if not api_key:
        return (
            "I need an OpenRouter API key to respond. "
            "Run `champmail setup ai` to configure it."
        )

    model = _get_model()
    context = _build_context()
    system = SYSTEM_PROMPT.replace("{context}", context)

    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}] + messages,
        "temperature": 0.6,
        "max_tokens": 1024,
        "stream": stream,
    }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            if stream:
                full_response = ""
                sys.stdout.write("\033[36m  ChampMail ❯\033[0m ")
                sys.stdout.flush()
                async with client.stream(
                    "POST",
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://champmail.dev",
                        "X-Title": "ChampMail CLI",
                    },
                    json=payload,
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        raw = line[6:]
                        if raw.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(raw)
                            delta = chunk["choices"][0]["delta"].get("content", "")
                            if delta:
                                sys.stdout.write(delta)
                                sys.stdout.flush()
                                full_response += delta
                        except (json.JSONDecodeError, KeyError, IndexError):
                            pass
                sys.stdout.write("\n\n")
                sys.stdout.flush()
                return full_response
            else:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            return "Invalid OpenRouter API key. Run `champmail setup ai` to update it."
        return f"API error {e.response.status_code}: {e.response.text[:200]}"
    except Exception as e:
        return f"Connection error: {e}"


def _run_async(coro):
    import logging
    logging.getLogger("asyncio").setLevel(logging.CRITICAL)
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        # Cancel any lingering tasks (e.g. streaming generators) to avoid noise
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))


# ── Setup completeness check ───────────────────────────────────────────────────

def _setup_status() -> dict[str, bool]:
    cfg = load_config()
    smtp = cfg.get("smtp", {})
    imap = cfg.get("imap", {})
    ai   = cfg.get("ai", {})
    camp = cfg.get("campaign_defaults", {})
    dom  = cfg.get("domain", {})
    return {
        "domain":   bool(dom.get("name")),
        "smtp":     bool(smtp.get("host") and smtp.get("host") != "localhost" and smtp.get("username")),
        "imap":     bool(imap.get("host") and imap.get("host") != "localhost" and imap.get("username")),
        "prospect": bool(cfg.get("prospect_defaults")),
        "campaign": bool(camp.get("from_email")),
        "ai":       bool(ai.get("openrouter_api_key")),
    }


def _print_setup_status() -> None:
    status = _setup_status()
    click.echo()
    click.echo("\033[1;36m  Setup Status:\033[0m")
    icons = {True: "\033[32m✓\033[0m", False: "\033[33m○\033[0m"}
    commands = {
        "domain":   "champmail setup domain",
        "smtp":     "champmail setup smtp",
        "imap":     "champmail setup imap",
        "prospect": "champmail setup prospect",
        "campaign": "champmail setup campaign",
        "ai":       "champmail setup ai",
    }
    for key, done in status.items():
        icon = icons[done]
        cmd  = "" if done else f"  → \033[2m{commands[key]}\033[0m"
        click.echo(f"  {icon}  {key.title():<12}{cmd}")
    click.echo()


# ── Live outreach pipeline visualiser ────────────────────────────────────────

def _run_outreach_visual(email, first, last, title, company, domain, industry,
                          phone, linkedin, answers_file, full_name):
    """Run each outreach step individually with live animated status in the chat."""
    import subprocess as _sp
    import threading as _th

    STEPS = [
        ("prospect",      f"Creating prospect profile for {full_name}",    "Saved to database + knowledge graph"),
        ("research",      f"Researching {full_name} in knowledge graph",   "Graph profile built"),
        ("questionnaire", f"Saving campaign intent to knowledge graph",    "Intent ingested"),
        ("prep",          f"Generating personalised email with AI",        "Email draft ready"),
        ("send",          f"Sending email to {email}",                     "Recorded in knowledge graph"),
        ("replies",       f"Checking inbox for replies",                   "Inbox checked"),
    ]

    env = {**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent.parent)}
    cwd = str(Path(__file__).parent.parent.parent)

    click.echo()
    click.echo(f"  \033[1;36m🚀  Outreach pipeline starting for {full_name} ({email})\033[0m")
    click.echo(f"  \033[2m{'─' * 54}\033[0m")

    subject_line = None

    for i, (step, desc, done_label) in enumerate(STEPS, 1):
        # Spinner thread
        stop_spinner = _th.Event()

        def _spin(desc=desc, stop=stop_spinner):
            chars = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
            idx = 0
            while not stop.is_set():
                sys.stdout.write(f"\r  \033[36m{chars[idx % len(chars)]}\033[0m  \033[2mStep {i}/6\033[0m  {desc}   ")
                sys.stdout.flush()
                time.sleep(0.08)
                idx += 1

        t = _th.Thread(target=_spin, daemon=True)
        t.start()

        # Build command for this step
        if step == "prospect":
            cmd = [sys.executable, "-m", "cli.champmail_cli", "outreach", "prospect", email,
                   "--first-name", first, "--last-name", last, "--title", title,
                   "--company", company, "--domain", domain, "--industry", industry]
            if phone:    cmd += ["--phone", phone]
            if linkedin: cmd += ["--linkedin", linkedin]
        elif step == "questionnaire":
            cmd = [sys.executable, "-m", "cli.champmail_cli", "outreach", "questionnaire",
                   email, "--answers-file", answers_file]
        elif step == "prep":
            cmd = [sys.executable, "-m", "cli.champmail_cli", "outreach", "prep",
                   email, "--save", answers_file + ".draft.json",
                   "--answers-file", answers_file]
        elif step == "send":
            cmd = [sys.executable, "-m", "cli.champmail_cli", "outreach", "send",
                   email, "--draft-file", answers_file + ".draft.json"]
            # Pass sender info from answers
            try:
                import json as _json2
                with open(answers_file) as _af:
                    _ans = _json2.load(_af)
                if _ans.get("sender"):
                    cmd += ["--from-name", _ans["sender"]]
                if _ans.get("from_email"):
                    cmd += ["--from-email", _ans["from_email"]]
            except Exception:
                pass
        else:
            cmd = [sys.executable, "-m", "cli.champmail_cli", "outreach", step, email]

        result = _sp.run(cmd, env=env, cwd=cwd,
                         capture_output=True, text=True)

        stop_spinner.set()
        t.join()

        # Parse subject line from prep output
        if step == "prep" and result.stdout:
            for ln in result.stdout.splitlines():
                if "Subject" in ln and "❯" not in ln:
                    subject_line = ln.split(None, 2)[-1].strip()
                    break

        ok = result.returncode == 0
        icon  = "\033[32m✓\033[0m" if ok else "\033[31m✗\033[0m"
        label = done_label if ok else "failed (check logs)"
        sys.stdout.write(f"\r  {icon}  \033[2mStep {i}/6\033[0m  {desc}\033[K\n")
        sys.stdout.flush()

        # Show subject under prep step
        if step == "prep" and subject_line:
            click.echo(f"        \033[2m↳ Subject: {subject_line}\033[0m")

        # Show SMTP warning inline for send step
        if step == "send" and result.stdout and "SMTP" in result.stdout:
            click.echo(f"        \033[33m↳ SMTP blocked (sandbox) — recorded in graph anyway\033[0m")

    click.echo(f"  \033[2m{'─' * 54}\033[0m")
    click.echo(f"  \033[1;32m✓  Pipeline complete!\033[0m  Run \033[36moutreach status {email}\033[0m to see the full timeline.\n")


# ── In-chat action executor ───────────────────────────────────────────────────

import re as _re

def _execute_chat_actions(response: str) -> str:
    """
    Scan the AI response for SAVE_*/RUN_OUTREACH tokens, execute them silently,
    and strip the tokens from the visible output.
    Returns the cleaned response text.
    """
    lines = response.split("\n")
    clean_lines = []
    action_messages = []

    for line in lines:
        stripped = line.strip()

        # ── SAVE_SMTP ─────────────────────────────────────────────────────
        m = _re.match(r"SAVE_SMTP:(.+)", stripped)
        if m:
            parts = m.group(1).split("|")
            if len(parts) >= 4:
                host, port, username, password = parts[0], parts[1], parts[2], parts[3]
                from_name = parts[4] if len(parts) > 4 else username
                set_section("smtp", {
                    "host": host, "port": int(port) if port.isdigit() else 587,
                    "username": username, "password": password,
                    "from_email": username, "from_name": from_name, "use_tls": True,
                })
                sync_to_env(); apply_to_runtime()
                action_messages.append("\033[32m✓ SMTP saved!\033[0m")
            continue

        # ── SAVE_IMAP ─────────────────────────────────────────────────────
        m = _re.match(r"SAVE_IMAP:(.+)", stripped)
        if m:
            parts = m.group(1).split("|")
            if len(parts) >= 4:
                host, port, username, password = parts[0], parts[1], parts[2], parts[3]
                set_section("imap", {
                    "host": host, "port": int(port) if port.isdigit() else 993,
                    "username": username, "password": password,
                    "mailbox": "INBOX", "use_ssl": True,
                })
                sync_to_env(); apply_to_runtime()
                action_messages.append("\033[32m✓ IMAP saved!\033[0m")
            continue

        # ── SAVE_DOMAIN ───────────────────────────────────────────────────
        m = _re.match(r"SAVE_DOMAIN:(.+)", stripped)
        if m:
            parts = m.group(1).split("|")
            if len(parts) >= 1:
                name = parts[0]
                provider = parts[1] if len(parts) > 1 else "other"
                set_section("domain", {"name": name, "provider": provider})
                sync_to_env(); apply_to_runtime()
                action_messages.append("\033[32m✓ Domain saved!\033[0m")
            continue

        # ── SAVE_AI ───────────────────────────────────────────────────────
        m = _re.match(r"SAVE_AI:(.+)", stripped)
        if m:
            parts = m.group(1).split("|")
            if len(parts) >= 1:
                key = parts[0]
                model = parts[1] if len(parts) > 1 else "openai/gpt-4.1-mini"
                set_section("ai", {"openrouter_api_key": key, "model": model})
                sync_to_env(); apply_to_runtime()
                action_messages.append("\033[32m✓ AI key saved!\033[0m")
            continue

        # ── SAVE_CAMPAIGN ─────────────────────────────────────────────────
        m = _re.match(r"SAVE_CAMPAIGN:(.+)", stripped)
        if m:
            parts = m.group(1).split("|")
            if len(parts) >= 2:
                from_name = parts[0]
                from_email = parts[1]
                daily_limit = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 50
                goal = parts[3] if len(parts) > 3 else "book a demo"
                tone = parts[4] if len(parts) > 4 else "casual"
                set_section("campaign_defaults", {
                    "from_name": from_name, "from_email": from_email,
                    "daily_limit": daily_limit, "goal": goal, "tone": tone,
                })
                sync_to_env(); apply_to_runtime()
                action_messages.append("\033[32m✓ Campaign defaults saved!\033[0m")
            continue

        # ── SAVE_PROSPECT ─────────────────────────────────────────────────
        m = _re.match(r"SAVE_PROSPECT:(.+)", stripped)
        if m:
            parts = m.group(1).split("|")
            if len(parts) >= 1:
                industry = parts[0]
                source = parts[1] if len(parts) > 1 else "linkedin"
                set_section("prospect_defaults", {"industry": industry, "source": source})
                sync_to_env(); apply_to_runtime()
                action_messages.append("\033[32m✓ Prospect defaults saved!\033[0m")
            continue

        # ── RUN_OUTREACH ──────────────────────────────────────────────────
        m = _re.match(r"RUN_OUTREACH:(.+)", stripped)
        if m:
            parts = m.group(1).split("|")
            if len(parts) >= 1:
                email    = parts[0]
                first    = parts[1] if len(parts) > 1 else ""
                last     = parts[2] if len(parts) > 2 else ""
                title    = parts[3] if len(parts) > 3 else ""
                company  = parts[4] if len(parts) > 4 else ""
                domain   = parts[5] if len(parts) > 5 else ""
                industry = parts[6] if len(parts) > 6 else "SaaS"
                goal     = parts[7] if len(parts) > 7 else "book a demo"
                pain     = parts[8] if len(parts) > 8 else ""
                value    = parts[9] if len(parts) > 9 else ""
                ctx      = parts[10] if len(parts) > 10 else ""
                cta      = parts[11] if len(parts) > 11 else "15-min call?"
                tone     = parts[12] if len(parts) > 12 else "casual"
                phone    = parts[13] if len(parts) > 13 else ""
                linkedin = parts[14] if len(parts) > 14 else ""

                # Parse sender fields (appended after linkedin)
                sender_name    = parts[15] if len(parts) > 15 else ""
                sender_position = parts[16] if len(parts) > 16 else ""
                sender_company = parts[17] if len(parts) > 17 else ""
                sender_email   = parts[18] if len(parts) > 18 else ""

                # Build sender line: "Name, Position at Company"
                sender_display = sender_name.strip()
                if sender_position.strip():
                    sender_display += f", {sender_position.strip()}"
                if sender_company.strip():
                    sender_display += f" at {sender_company.strip()}"
                if not sender_display:
                    sender_display = get_value("campaign_defaults", "from_name") or "Your Name"
                if not sender_email:
                    sender_email = get_value("campaign_defaults", "from_email") or ""

                import json as _json, tempfile as _tmp, subprocess as _sp, threading as _th
                answers = {
                    "goal": goal, "pain_point": pain, "value_prop": value,
                    "context": ctx, "cta": cta, "tone": tone,
                    "sender": sender_display,
                    "sender_position": sender_position,
                    "sender_company": sender_company,
                    "from_email": sender_email,
                }
                with _tmp.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
                    _json.dump(answers, f)
                    answers_file = f.name

                full_name = f"{first} {last}".strip() or email
                _run_outreach_visual(
                    email=email, first=first, last=last, title=title,
                    company=company, domain=domain, industry=industry,
                    phone=phone, linkedin=linkedin, answers_file=answers_file,
                    full_name=full_name,
                )
            continue

        # ── SEND_CUSTOM ───────────────────────────────────────────────────
        m = _re.match(r"SEND_CUSTOM:(.+)", stripped)
        if m:
            parts = m.group(1).split("|", 2)  # max 3 parts: email|subject|body
            if len(parts) >= 3:
                to_email = parts[0].strip()
                subj     = parts[1].strip()
                body_raw = parts[2].strip().replace("\\n", "\n")

                import subprocess as _sp

                click.echo(f"\n  \033[1;36m✉  Sending custom email to {to_email}...\033[0m\n")

                _env = {**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent.parent)}
                _cwd = str(Path(__file__).parent.parent.parent)

                # Build HTML body from plain text
                html_body = "".join(f"<p>{line}</p>" for line in body_raw.split("\n") if line.strip())

                # Get sender info from config
                sender_name  = get_value("campaign_defaults", "from_name") or ""
                sender_email = get_value("campaign_defaults", "from_email") or ""

                cmd = [
                    sys.executable, "-m", "cli.champmail_cli", "outreach", "send",
                    to_email,
                    "--subject", subj,
                    "--body", html_body,
                ]
                if sender_name:
                    cmd += ["--from-name", sender_name]
                if sender_email:
                    cmd += ["--from-email", sender_email]

                result = _sp.run(cmd, env=_env, cwd=_cwd, capture_output=True, text=True)

                if result.returncode == 0:
                    click.echo(f"  \033[32m✓  Email sent to {to_email}!\033[0m")
                    click.echo(f"     Subject: {subj}")
                else:
                    click.echo(f"  \033[31m✗  Send failed\033[0m")
                    if result.stdout:
                        for ln in result.stdout.strip().splitlines()[-3:]:
                            click.echo(f"     {ln}")
                    if result.stderr:
                        for ln in result.stderr.strip().splitlines()[-2:]:
                            click.echo(f"     \033[31m{ln}\033[0m")
                click.echo()
            continue

        # ── IMPORT_PROSPECTS ──────────────────────────────────────────────
        m = _re.match(r"IMPORT_PROSPECTS:(.+)", stripped)
        if m:
            _csv_path = m.group(1).strip()
            import subprocess as _sp
            click.echo(f"\n  \033[1;36m📋  Importing prospects from {_csv_path}...\033[0m\n")
            _env = {**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent.parent)}
            _cwd = str(Path(__file__).parent.parent.parent)
            _result = _sp.run(
                [sys.executable, "-m", "cli.champmail_cli", "prospects", "bulk-import", "--file", _csv_path],
                env=_env, cwd=_cwd, capture_output=False,
            )
            click.echo()
            continue

        # ── RUN_BATCH ─────────────────────────────────────────────────────
        m = _re.match(r"RUN_BATCH:(.+)", stripped)
        if m:
            parts = m.group(1).split("|")
            if len(parts) >= 2:
                _csv_path = parts[0].strip()
                _goal = parts[1] if len(parts) > 1 else ""
                _pain = parts[2] if len(parts) > 2 else ""
                _value = parts[3] if len(parts) > 3 else ""
                _cta = parts[4] if len(parts) > 4 else ""
                _tone = parts[5] if len(parts) > 5 else "casual"
                _sender = parts[6] if len(parts) > 6 else ""
                _from_email = parts[7] if len(parts) > 7 else ""
                _context = parts[8] if len(parts) > 8 else ""
                _skip_send = parts[9].strip().lower() == "true" if len(parts) > 9 else False

                import subprocess as _sp
                click.echo(f"\n  \033[1;35m📋  Launching batch outreach from {_csv_path}...\033[0m\n")
                _env = {**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent.parent)}
                _cwd = str(Path(__file__).parent.parent.parent)
                _cmd = [
                    sys.executable, "-m", "cli.champmail_cli",
                    "outreach", "batch", _csv_path,
                ]
                if _goal:       _cmd.extend(["--goal", _goal])
                if _pain:       _cmd.extend(["--pain-point", _pain])
                if _value:      _cmd.extend(["--value-prop", _value])
                if _cta:        _cmd.extend(["--cta", _cta])
                if _tone:       _cmd.extend(["--tone", _tone])
                if _sender:     _cmd.extend(["--sender", _sender])
                if _from_email: _cmd.extend(["--from-email", _from_email])
                if _context:    _cmd.extend(["--context", _context])
                if _skip_send:  _cmd.append("--skip-send")
                _sp.run(_cmd, env=_env, cwd=_cwd)
                click.echo()
            continue

        # ── INGEST_DOC ────────────────────────────────────────────────────
        m = _re.match(r"INGEST_DOC:(.+)", stripped)
        if m:
            parts = m.group(1).split("|")
            _file_path = parts[0].strip()
            _title = parts[1].strip() if len(parts) > 1 and parts[1].strip() else ""
            import subprocess as _sp
            click.echo(f"\n  \033[1;36m📄  Ingesting document: {_file_path}...\033[0m\n")
            _env = {**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent.parent)}
            _cwd = str(Path(__file__).parent.parent.parent)
            _cmd = [sys.executable, "-m", "cli.champmail_cli", "outreach", "docs", "add", _file_path]
            if _title:
                _cmd.extend(["--title", _title])
            _sp.run(_cmd, env=_env, cwd=_cwd)
            click.echo()
            continue

        # ── LIST_DOCS ────────────────────────────────────────────────────
        if stripped == "LIST_DOCS":
            import subprocess as _sp
            click.echo(f"\n  \033[1;36m📚  Listing ingested campaign documents...\033[0m\n")
            _env = {**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent.parent)}
            _cwd = str(Path(__file__).parent.parent.parent)
            _sp.run(
                [sys.executable, "-m", "cli.champmail_cli", "outreach", "docs", "list"],
                env=_env, cwd=_cwd,
            )
            click.echo()
            continue

        # ── SEARCH_DOCS ──────────────────────────────────────────────────
        m = _re.match(r"SEARCH_DOCS:(.+)", stripped)
        if m:
            _query = m.group(1).strip()
            import subprocess as _sp
            click.echo(f"\n  \033[1;36m🔎  Searching campaign docs for: {_query}...\033[0m\n")
            _env = {**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent.parent)}
            _cwd = str(Path(__file__).parent.parent.parent)
            _sp.run(
                [sys.executable, "-m", "cli.champmail_cli", "outreach", "docs", "search", _query],
                env=_env, cwd=_cwd,
            )
            click.echo()
            continue

        # ── REMOVE_DOC ───────────────────────────────────────────────────
        m = _re.match(r"REMOVE_DOC:(.+)", stripped)
        if m:
            _doc_id = m.group(1).strip()
            import subprocess as _sp
            click.echo(f"\n  \033[1;36m🗑️  Removing document: {_doc_id}...\033[0m\n")
            _env = {**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent.parent)}
            _cwd = str(Path(__file__).parent.parent.parent)
            _sp.run(
                [sys.executable, "-m", "cli.champmail_cli", "outreach", "docs", "remove", _doc_id],
                env=_env, cwd=_cwd,
            )
            click.echo()
            continue

        # ── RUN_STATUS ────────────────────────────────────────────────────
        m = _re.match(r"RUN_STATUS:(.+)", stripped)
        if m:
            import subprocess as _sp
            _email = m.group(1).strip()
            click.echo(f"\n  \033[1;36m📊  Checking pipeline status for {_email}...\033[0m\n")
            _env = {**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent.parent)}
            _cwd = str(Path(__file__).parent.parent.parent)
            _sp.run(
                [sys.executable, "-m", "cli.champmail_cli", "outreach", "status", _email],
                env=_env, cwd=_cwd,
            )
            click.echo()
            continue

        # ── RUN_REPLIES ───────────────────────────────────────────────────
        m = _re.match(r"RUN_REPLIES:(.+)", stripped)
        if m:
            import subprocess as _sp
            _email = m.group(1).strip()
            click.echo(f"\n  \033[1;36m📬  Checking replies for {_email}...\033[0m\n")
            _env = {**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent.parent)}
            _cwd = str(Path(__file__).parent.parent.parent)
            _sp.run(
                [sys.executable, "-m", "cli.champmail_cli", "outreach", "replies", _email],
                env=_env, cwd=_cwd,
            )
            click.echo()
            continue

        # ── VIEW_RESEARCH ─────────────────────────────────────────────────
        m = _re.match(r"VIEW_RESEARCH:(.+)", stripped)
        if m:
            import subprocess as _sp
            _email = m.group(1).strip()
            click.echo(f"\n  \033[1;36m🔍  Showing saved research for {_email}...\033[0m\n")
            _env = {**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent.parent)}
            _cwd = str(Path(__file__).parent.parent.parent)
            _sp.run(
                [sys.executable, "-m", "cli.champmail_cli", "outreach", "view-research", _email],
                env=_env, cwd=_cwd,
            )
            click.echo()
            continue

        # ── RUN_VERIFY ────────────────────────────────────────────────────
        if stripped == "RUN_VERIFY:smtp":
            import subprocess as _sp
            click.echo(f"\n  \033[1;36m🔌  Verifying SMTP connection...\033[0m\n")
            _env = {**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent.parent)}
            _cwd = str(Path(__file__).parent.parent.parent)
            _sp.run(
                [sys.executable, "-m", "cli.champmail_cli", "send", "verify"],
                env=_env, cwd=_cwd,
            )
            click.echo()
            continue

        # ── RUN_IMAP_CHECK ────────────────────────────────────────────────
        if stripped == "RUN_IMAP_CHECK":
            import subprocess as _sp
            click.echo(f"\n  \033[1;36m📥  Checking IMAP inbox...\033[0m\n")
            _env = {**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent.parent)}
            _cwd = str(Path(__file__).parent.parent.parent)
            _sp.run(
                [sys.executable, "-m", "cli.champmail_cli", "send", "imap-check"],
                env=_env, cwd=_cwd,
            )
            click.echo()
            continue

        clean_lines.append(line)

    cleaned = "\n".join(clean_lines).strip()
    if action_messages:
        click.echo("\n" + "\n".join(f"  {m}" for m in action_messages) + "\n")
    return cleaned


# ── Main chat loop ─────────────────────────────────────────────────────────────

CHAT_HISTORY_FILE = SESSION_DIR / "chat_history"


@click.command("chat")
@click.option("--setup",  "start_setup",  is_flag=True, default=False,
              help="Start with the setup wizard before chatting.")
@click.option("--no-stream", is_flag=True, default=False,
              help="Disable streaming (wait for full response).")
@click.option("--plain", is_flag=True, default=False,
              help="Skip animated intro (useful in CI or pipes).")
@click.pass_obj
def chat(obj, start_setup, no_stream, plain):
    """Conversational AI interface — guided setup, outreach, and Q&A in one flow."""

    if not is_logged_in():
        print_error("Not logged in. Run: champmail auth login")
        raise SystemExit(1)

    apply_to_runtime()

    user_email = get_session_email()

    # ── Animated intro ──────────────────────────────────────────────────
    if not plain and sys.stdout.isatty():
        _show_intro(user_email)
    else:
        click.echo("\n\033[1;36mChampMail Chat\033[0m — Conversational Outreach Assistant\n")

    # ── Setup nudge ─────────────────────────────────────────────────────
    status = _setup_status()
    missing = [k for k, v in status.items() if not v]

    if missing:
        click.echo("\033[33m  Some setup steps are incomplete:\033[0m")
        _print_setup_status()
        is_interactive = sys.stdin.isatty() and sys.stdout.isatty()
        if start_setup or (is_interactive and click.confirm("  Run setup now? (recommended)", default=True)):
            # Invoke each missing setup step
            import subprocess
            SETUP_ORDER = ["domain", "smtp", "imap", "prospect", "campaign", "ai"]
            for step in SETUP_ORDER:
                if not status[step]:
                    click.echo(f"\n\033[1;36m  ── champmail setup {step} ──\033[0m\n")
                    result = subprocess.run(
                        [sys.executable, "-m", "cli.champmail_cli", "setup", step],
                        env={**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent.parent)},
                        cwd=str(Path(__file__).parent.parent.parent),
                    )
                    if result.returncode != 0:
                        print_warning(f"Setup {step} was skipped or cancelled.")
        click.echo()

    # ── Welcome message from assistant ──────────────────────────────────
    status = _setup_status()
    missing_now = [k for k, v in status.items() if not v]

    if missing_now:
        welcome = (
            f"Hi! I'm your ChampMail assistant. A few things still need setting up: "
            f"**{', '.join(missing_now)}**. Just say \"let's set up\" and I'll walk you through "
            f"everything right here — no commands needed."
        )
    else:
        welcome = (
            "Hey! Everything's configured and you're ready to go. "
            "Who do you want to reach out to today? Just give me a name and email, "
            "or say 'help' to see what I can do."
        )

    click.echo(f"\033[36m  ChampMail ❯\033[0m {welcome}\n")

    # ── Build prompt session ─────────────────────────────────────────────
    CHAT_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    prompt_session = make_prompt_session(str(CHAT_HISTORY_FILE))

    messages: list[dict] = []

    # ── Main loop ────────────────────────────────────────────────────────
    while True:
        try:
            from prompt_toolkit import HTML as _HTML
            raw = prompt_session.prompt(
                _HTML("<ansibrightmagenta>  You ❯</ansibrightmagenta> "),
            )
        except KeyboardInterrupt:
            click.echo()
            continue
        except EOFError:
            click.echo()
            print_info("Goodbye.")
            break

        text = raw.strip()
        if not text:
            continue
        if text.lower() in ("exit", "quit", "q", "bye"):
            print_info("Goodbye! Run  champmail chat  anytime to continue.")
            break

        # ── Built-in slash commands ──────────────────────────────────────
        if text.lower() in ("status", "/status"):
            _print_setup_status()
            continue

        if text.lower() in ("help", "/help"):
            click.echo(textwrap.dedent("""\

              \033[1;36mChampMail Chat — Quick Reference\033[0m

              Just type naturally — I understand what you want to do.

              \033[36mBuilt-in commands:\033[0m
                status         Show setup completion status
                help           Show this help
                exit / quit    Exit chat

              \033[36mSetup commands (run from terminal):\033[0m
                champmail setup domain
                champmail setup smtp
                champmail setup imap
                champmail setup prospect
                champmail setup campaign
                champmail setup ai
                champmail setup show

              \033[36mOutreach (run from terminal or ask me):\033[0m
                champmail outreach start EMAIL
                champmail outreach status EMAIL

            """))
            continue

        if text.lower() in ("clear", "/clear"):
            messages.clear()
            click.echo("\033[2m  [Conversation cleared]\033[0m\n")
            continue

        # ── Send to LLM ──────────────────────────────────────────────────
        messages.append({"role": "user", "content": text})

        if not _get_api_key():
            click.echo(
                "\033[33m  ChampMail ❯\033[0m No AI key configured.\n"
                "  Run: \033[36mchampmail setup ai\033[0m\n"
            )
            messages.pop()
            continue

        response = _run_async(
            _chat_completion(messages, stream=not no_stream)
        )

        # Execute any SAVE_*/RUN_OUTREACH actions embedded in the response
        visible = _execute_chat_actions(response)

        if no_stream:
            # Print non-streamed response with wrapping
            click.echo(f"\033[36m  ChampMail ❯\033[0m")
            for line in visible.split("\n"):
                click.echo(f"  {line}")
            click.echo()
        elif visible != response:
            # Streaming already printed the raw response (with tokens); reprint cleaned if different
            pass  # actions were stripped — streamed output already showed the human text

        messages.append({"role": "assistant", "content": response})

        # Trim history to last 20 turns to avoid token blowup
        if len(messages) > 40:
            messages = messages[-40:]
