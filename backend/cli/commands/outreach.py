"""
champmail outreach — End-to-end cold outreach pipeline.

Full process in one command group:

  outreach start         EMAIL [options]     # full guided wizard
  outreach prospect      EMAIL [options]     # step 1: create + research prospect
  outreach research      EMAIL              # step 2: query ChampGraph for context
  outreach questionnaire EMAIL              # step 3: interactive questionnaire → ingest answers
  outreach prep          EMAIL              # step 4: AI-prep email from graph context
  outreach send          EMAIL              # step 5: send cold email
  outreach replies       EMAIL              # step 6: check for replies
  outreach status        EMAIL              # full pipeline status for a prospect

All steps are idempotent — run any step independently or run `outreach start`
to walk through the full wizard interactively.
"""

from __future__ import annotations

import json
import textwrap
import time
from datetime import datetime, timezone

import click

from cli.repl_skin import (
    print_error, print_info, print_kv, print_section,
    print_success, print_table, print_warning,
)
from cli.session import is_logged_in, get_user_id, get_email as get_session_email, load_session


# ── helpers ───────────────────────────────────────────────────────────────────

def _require_login(obj):
    if not is_logged_in():
        print_error("Not logged in.  Run: champmail auth login")
        raise SystemExit(1)


def _account_name(email: str) -> str:
    """Derive ChampGraph account_name from email — matches what was ingested."""
    return email.split("@")[1] if "@" in email else "champmail"


def _graph_init():
    from app.db.falkordb import init_graph_db, graph_db
    init_graph_db()
    return graph_db


async def _best_account(email: str) -> str:
    """Return the best ChampGraph account_name for this email (checks PG for name)."""
    from app.db.postgres import init_db, get_db
    from app.services.prospect_service import prospect_service

    await init_db()
    async with get_db() as session:
        pg = await prospect_service.get_by_email(session, email)
    if pg:
        fname = (pg.get("first_name") or "").strip()
        lname = (pg.get("last_name") or "").strip()
        if fname or lname:
            return f"{fname}_{lname}".strip("_").lower().replace(" ", "_")
    return _account_name(email)


# ── group ─────────────────────────────────────────────────────────────────────

@click.group()
def outreach() -> None:
    """End-to-end cold outreach pipeline: prospect → research → campaign → send → replies."""


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — prospect
# ─────────────────────────────────────────────────────────────────────────────

@outreach.command("prospect")
@click.argument("email")
@click.option("--first-name", "first_name", default="", help="First name.")
@click.option("--last-name",  "last_name",  default="", help="Last name.")
@click.option("--title",      default="",   help="Job title.")
@click.option("--phone",      default="",   help="Phone number.")
@click.option("--linkedin",   "linkedin_url", default="", help="LinkedIn URL.")
@click.option("--company",    "company_name",  default="", help="Company name.")
@click.option("--domain",     "company_domain", default="", help="Company domain.")
@click.option("--industry",   default="",   help="Industry.")
@click.pass_obj
def cmd_prospect(obj, email, first_name, last_name, title, phone,
                 linkedin_url, company_name, company_domain, industry):
    """Step 1 — Create prospect in DB + ChampGraph, then kick off research ingest."""
    _require_login(obj)

    async def _do():
        from app.db.postgres import init_db, get_db
        from app.db.falkordb import init_graph_db, graph_db
        from app.services.prospect_service import prospect_service

        await init_db()
        init_graph_db()
        session_data = load_session()
        team_id = session_data.get("team_id")
        user_id = get_user_id()

        # 1a — PostgreSQL prospect record
        async with get_db() as session:
            existing = await prospect_service.get_by_email(session, email)
            if existing:
                pg_id = existing.get("id")
                created = False
            else:
                p = await prospect_service.create(
                    session, email=email, team_id=team_id,
                    first_name=first_name, last_name=last_name,
                    company_name=company_name,
                )
                await session.commit()
                pg_id = p.get("id")
                created = True

        # 1b — ChampGraph ingest (prospect node + company link)
        parts = [f"Prospect: {first_name} {last_name}".strip() or email]
        parts.append(f"Email: {email}")
        if title:      parts.append(f"Title: {title}")
        if phone:      parts.append(f"Phone: {phone}")
        if company_name: parts.append(f"Company: {company_name}")
        if industry:   parts.append(f"Industry: {industry}")
        if linkedin_url: parts.append(f"LinkedIn: {linkedin_url}")

        # Use name-based account key so research queries can find this data
        name_key = f"{first_name}_{last_name}".strip("_").lower().replace(" ", "_")
        account = name_key if name_key else _account_name(email)
        await graph_db._ingest(
            content="\n".join(parts),
            name=f"Prospect: {first_name} {last_name} ({email})".strip(),
            account_name=account,
            source="outreach_prospect_create",
        )

        if company_domain:
            await graph_db.create_company(
                name=company_name or company_domain,
                domain=company_domain,
                industry=industry,
            )
            await graph_db.link_prospect_to_company(
                prospect_email=email,
                company_domain=company_domain,
                title=title,
            )

        return {"pg_id": str(pg_id), "created": created, "account": account}

    data = obj.run(_do())
    if obj.json_output:
        print(json.dumps({"ok": True, "email": email, **data}))
    else:
        status = "Created" if data["created"] else "Already exists"
        print_section("Step 1 — Prospect")
        print_kv("Email",   email)
        print_kv("Status",  status)
        print_kv("PG ID",   data["pg_id"])
        print_kv("Account", data["account"])
        print_success("Prospect ready.  Run next: outreach research " + email)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — research
# ─────────────────────────────────────────────────────────────────────────────

@outreach.command("research")
@click.argument("email")
@click.option("--account", "account_override", default=None,
              help="ChampGraph account name to query (default: derived from email + prospect name).")
@click.pass_obj
def cmd_research(obj, email, account_override):
    """Step 2 — Pull full knowledge graph profile from ChampGraph."""
    _require_login(obj)

    async def _do():
        from app.db.postgres import init_db, get_db
        from app.services.prospect_service import prospect_service

        gdb = _graph_init()

        # Derive candidate account names to query
        # 1) explicit override  2) email domain  3) "firstname_lastname" from DB
        candidates = []
        if account_override:
            candidates.append(account_override)

        domain_account = _account_name(email)
        candidates.append(domain_account)

        # Look up name from postgres to build a name-based account key
        await init_db()
        async with get_db() as session:
            pg = await prospect_service.get_by_email(session, email)
        if pg:
            fname = (pg.get("first_name") or "").strip()
            lname = (pg.get("last_name") or "").strip()
            if fname or lname:
                name_account = f"{fname}_{lname}".strip("_").lower().replace(" ", "_")
                candidates.append(name_account)

        # Query all candidate accounts, merge results
        all_nodes = []
        best_account = domain_account
        for acct in candidates:
            res = await gdb.query(
                f"Who is {email}? Give me their role, company, interests, background, "
                f"topics they care about, and any relationships.",
                account_name=acct,
            )
            if res:
                all_nodes.extend(res)
                best_account = acct  # prefer account with actual data

        # Deduplicate by node name
        seen = set()
        nodes = []
        for n in all_nodes:
            key = n.get("name", "") + n.get("fact", "")
            if key not in seen:
                seen.add(key)
                nodes.append(n)

        briefing = await gdb.get_account_briefing(best_account)
        ctx = await gdb.get_email_context(
            account_name=best_account,
            contact_email=email,
        )

        return {
            "account": best_account,
            "candidates_queried": candidates,
            "nodes": nodes,
            "briefing": briefing,
            "email_context": ctx,
        }

    data = obj.run(_do())

    if obj.json_output:
        print(json.dumps({"ok": True, "email": email, **data}, default=str))
        return

    print_section(f"Step 2 — Research: {email}")
    nodes = data.get("nodes", [])
    if not nodes:
        print_warning("No graph data yet.  Run outreach prospect first, or wait for ingest.")
    else:
        for n in nodes:
            if n.get("type") == "node":
                print_kv(n.get("name", ""), n.get("summary", "")[:120])

    briefing = data.get("briefing", {})
    if briefing.get("success"):
        print_section("Account Briefing")
        for k, v in briefing.items():
            if k != "success" and v:
                print_kv(k.replace("_", " ").title(), str(v)[:120])

    ctx = data.get("email_context", {})
    if ctx.get("success") or ctx.get("context"):
        print_section("Email Context Hints")
        for k, v in ctx.items():
            if k not in ("success",) and v:
                print_kv(k.replace("_", " ").title(), str(v)[:120])

    print_success("Research done.  Run next: outreach questionnaire " + email)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — questionnaire
# ─────────────────────────────────────────────────────────────────────────────

QUESTIONNAIRE = [
    ("goal",       "What is your main goal with this outreach? (e.g. book a demo, partnership, feedback)"),
    ("pain_point", "What pain point / problem does your offer solve for this prospect?"),
    ("value_prop", "In one sentence — what value do you uniquely deliver?"),
    ("context",    "Why THIS person right now? Any recent trigger or reason to reach out?"),
    ("cta",        "What is the one call-to-action you want in the email? (e.g. 15-min call, reply with interest)"),
    ("tone",       "Preferred tone: [formal / casual / friendly / direct]"),
    ("sender",     "Who is sending this email? (your name and role)"),
    ("from_email", "From email address to use:"),
]


@outreach.command("questionnaire")
@click.argument("email")
@click.option("--answers-file", "answers_file", default=None, type=click.Path(exists=True),
              help="JSON file with pre-filled answers (skip interactive prompts).")
@click.pass_obj
def cmd_questionnaire(obj, email, answers_file):
    """Step 3 — Questionnaire: capture campaign intent, ingest answers into ChampGraph."""
    _require_login(obj)

    # Load pre-filled answers or prompt interactively
    if answers_file:
        with open(answers_file) as f:
            answers = json.load(f)
        print_info(f"Loaded answers from {answers_file}")
    else:
        if obj.json_output:
            print_error("--answers-file required in --json mode (no interactive prompts).")
            raise SystemExit(1)

        print_section(f"Step 3 — Questionnaire for {email}")
        print_info("Answer each question. Press Enter to skip.")
        answers = {}
        for key, question in QUESTIONNAIRE:
            print()
            click.echo(f"  \033[36m{question}\033[0m")
            val = click.prompt("  > ", default="", show_default=False).strip()
            if val:
                answers[key] = val

    if not answers:
        print_warning("No answers provided. Skipping questionnaire ingest.")
        if obj.json_output:
            print(json.dumps({"ok": True, "email": email, "answers": {}}))
        return

    async def _do():
        gdb = _graph_init()
        account = await _best_account(email)

        lines = [f"Outreach Campaign Intent for prospect: {email}"]
        for key, question in QUESTIONNAIRE:
            if key in answers:
                lines.append(f"{key.replace('_',' ').title()}: {answers[key]}")

        await gdb._ingest(
            content="\n".join(lines),
            name=f"Campaign Intent: {email}",
            account_name=account,
            source="outreach_questionnaire",
        )
        return answers

    saved = obj.run(_do())

    if obj.json_output:
        print(json.dumps({"ok": True, "email": email, "answers": saved}))
    else:
        print_section("Questionnaire saved to ChampGraph")
        for k, v in saved.items():
            print_kv(k.replace("_", " ").title(), v)
        print_success("Done.  Run next: outreach prep " + email)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — prep (AI email generation from graph context)
# ─────────────────────────────────────────────────────────────────────────────

@outreach.command("prep")
@click.argument("email")
@click.option("--subject", default=None, help="Override subject line.")
@click.option("--save",    "save_to", default=None, type=click.Path(),
              help="Save draft to this JSON file.")
@click.pass_obj
def cmd_prep(obj, email, subject, save_to):
    """Step 4 — Pull research + questionnaire from ChampGraph, generate personalised email draft via AI."""
    _require_login(obj)

    async def _do():
        import httpx
        from app.core.config import settings

        gdb = _graph_init()
        account = await _best_account(email)

        # Pull all context from ChampGraph
        research = await gdb.query(
            f"Everything known about {email} — role, company, interests, "
            f"background, topics, relationships.",
            account_name=account,
        )
        intent = await gdb.query(
            f"Campaign intent and questionnaire answers for outreach to {email}. "
            f"Goal, value proposition, pain point, CTA, tone, sender.",
            account_name=account,
        )
        ctx = await gdb.get_email_context(
            account_name=account,
            contact_email=email,
        )

        # Build context summary for the LLM
        research_text = "\n".join(
            f"- {n.get('name','')}: {n.get('summary','')}"
            for n in research if n.get("type") == "node" and n.get("summary")
        ) or "No prior research available."

        intent_text = "\n".join(
            f"- {n.get('name','')}: {n.get('summary','')}"
            for n in intent if n.get("type") == "node" and n.get("summary")
        ) or "No questionnaire answers ingested yet."

        ctx_hints = ""
        if ctx.get("success") or ctx.get("context"):
            ctx_hints = "\n".join(
                f"- {k}: {v}" for k, v in ctx.items()
                if k not in ("success",) and v and isinstance(v, str)
            )

        system_prompt = textwrap.dedent("""\
            You are an expert cold email copywriter.
            Write a single cold outreach email that is:
            - Personalised using the research and context provided
            - Short (3-4 short paragraphs max)
            - Conversational and human — not salesy
            - Ends with one clear, low-friction CTA
            - Subject line is punchy and specific, not generic

            Return a JSON object ONLY with keys:
              "subject": string,
              "body_html": string (HTML with <p> tags),
              "body_text": string (plain text version)
        """)

        user_prompt = textwrap.dedent(f"""\
            Prospect email: {email}

            === RESEARCH (from knowledge graph) ===
            {research_text}

            === CAMPAIGN INTENT (from questionnaire) ===
            {intent_text}

            === ADDITIONAL EMAIL CONTEXT ===
            {ctx_hints or 'None'}

            Write the cold email now.
        """)

        # Call OpenRouter (same key used everywhere in ChampMail)
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "openai/gpt-4.1-mini",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user",   "content": user_prompt},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.7,
                },
            )
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
            draft = json.loads(content)

        # Override subject if provided
        if subject:
            draft["subject"] = subject

        # Ingest the draft into ChampGraph so it's part of the prospect's timeline
        await gdb._ingest(
            content=(
                f"Email Draft Prepared for {email}\n"
                f"Subject: {draft.get('subject','')}\n"
                f"Body: {draft.get('body_text','')[:500]}"
            ),
            name=f"Email Draft: {email}",
            account_name=account,
            source="outreach_prep",
        )

        return draft

    draft = obj.run(_do())

    if save_to:
        with open(save_to, "w") as f:
            json.dump(draft, f, indent=2)
        print_success(f"Draft saved to {save_to}")

    if obj.json_output:
        print(json.dumps({"ok": True, "email": email, "draft": draft}))
    else:
        print_section(f"Step 4 — Email Draft for {email}")
        print_kv("Subject",    draft.get("subject", ""))
        print()
        click.echo("\033[36m── HTML Body ──────────────────────────────────────────\033[0m")
        click.echo(draft.get("body_text", draft.get("body_html", "")))
        click.echo("\033[36m───────────────────────────────────────────────────────\033[0m")
        print_success("Draft ready.  Run next: outreach send " + email)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5 — send
# ─────────────────────────────────────────────────────────────────────────────

@outreach.command("send")
@click.argument("email")
@click.option("--subject",    default=None, help="Subject override (else uses prepped draft).")
@click.option("--body",       default=None, help="HTML body override.")
@click.option("--draft-file", "draft_file", default=None, type=click.Path(exists=True),
              help="JSON draft file from outreach prep --save.")
@click.option("--from-name",  "from_name",  default=None, help="Sender name.")
@click.option("--from-email", "from_email_addr", default=None, help="Sender email.")
@click.pass_obj
def cmd_send(obj, email, subject, body, draft_file, from_name, from_email_addr):
    """Step 5 — Send the cold email and record it in ChampGraph."""
    _require_login(obj)

    # Load draft from file if provided
    draft = {}
    if draft_file:
        with open(draft_file) as f:
            draft = json.load(f)

    final_subject = subject or draft.get("subject") or "Following up"
    final_body    = body    or draft.get("body_html") or draft.get("body_text") or \
                    f"<p>Hi,</p><p>Reaching out regarding a potential collaboration.</p>"

    async def _do():
        from app.services.email_provider import get_email_provider, EmailMessage
        from app.db.falkordb import init_graph_db, graph_db

        init_graph_db()
        provider = get_email_provider()

        msg = EmailMessage(
            to=email,
            subject=final_subject,
            html_body=final_body,
            text_body=draft.get("body_text"),
            from_name=from_name,
            from_email=from_email_addr,
        )
        result = await provider.send_email(msg)

        # Record in ChampGraph regardless of SMTP outcome
        account = await _best_account(email)
        await graph_db._ingest(
            content=(
                f"Cold Email Sent\n"
                f"To: {email}\n"
                f"Subject: {final_subject}\n"
                f"Status: {'sent' if result.success else 'failed'}\n"
                f"Message-ID: {result.message_id or 'unknown'}\n"
                f"Timestamp: {datetime.now(timezone.utc).isoformat()}"
            ),
            name=f"Email Sent: {email}",
            account_name=account,
            source="outreach_send",
        )

        return result

    result = obj.run(_do())

    if obj.json_output:
        print(json.dumps({
            "ok": result.success,
            "email": email,
            "subject": final_subject,
            "message_id": result.message_id,
            "error": result.error,
        }))
    else:
        print_section(f"Step 5 — Send: {email}")
        print_kv("To",      email)
        print_kv("Subject", final_subject)
        if result.success:
            print_success(f"Email sent!  Message-ID: {result.message_id}")
            print_info("View at: https://ethereal.email/messages")
        else:
            print_warning(f"SMTP result: {result.error}")
            print_info("Recorded in ChampGraph regardless — timeline is up to date.")
        print_success("Run next: outreach replies " + email)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 6 — replies
# ─────────────────────────────────────────────────────────────────────────────

@outreach.command("replies")
@click.argument("email")
@click.option("--limit", default=10, show_default=True, help="Max messages to check.")
@click.pass_obj
def cmd_replies(obj, email, limit):
    """Step 6 — Check IMAP inbox for replies, record any matches in ChampGraph."""
    _require_login(obj)

    async def _do():
        from app.services.email_provider import get_reply_detector
        from app.db.falkordb import init_graph_db, graph_db

        init_graph_db()
        detector = get_reply_detector()

        ok = await detector.verify_connection()
        if not ok:
            return None, "IMAP connection failed"

        msgs = await detector.check_new_messages()
        account = await _best_account(email)

        matched = []
        for m in (msgs or [])[:limit]:
            is_reply = (
                (m.from_email and email.lower() in m.from_email.lower()) or
                (m.subject and (
                    "re:" in m.subject.lower() or
                    email.split("@")[0].lower() in m.subject.lower()
                ))
            )
            matched.append({
                "message_id": m.message_id,
                "from":       m.from_email,
                "subject":    m.subject,
                "received_at": m.received_at.isoformat(),
                "is_reply":   is_reply,
            })
            if is_reply:
                # Record reply in ChampGraph
                await graph_db._ingest(
                    content=(
                        f"Reply Received\n"
                        f"From: {m.from_email}\n"
                        f"Subject: {m.subject}\n"
                        f"Received: {m.received_at.isoformat()}\n"
                        f"Prospect: {email}"
                    ),
                    name=f"Reply from {email}",
                    account_name=account,
                    source="outreach_reply",
                )

        return matched, None

    msgs, err = obj.run(_do())
    if err:
        if obj.json_output:
            print(json.dumps({"ok": False, "error": err}))
        else:
            print_error(err)
            print_info("IMAP ports may be blocked in this sandbox — works in Docker/cloud.")
        return

    replies = [m for m in (msgs or []) if m["is_reply"]]
    all_msgs = msgs or []

    if obj.json_output:
        print(json.dumps({"ok": True, "email": email,
                          "replies": replies, "all_messages": all_msgs}))
        return

    print_section(f"Step 6 — Replies for {email}")
    print_kv("Inbox checked", str(len(all_msgs)) + " messages")
    print_kv("Replies found", str(len(replies)))

    if replies:
        print_table(
            ["From", "Subject", "Received"],
            [[r["from"][:30], r["subject"][:40],
              r["received_at"][:16]] for r in replies],
        )
        print_success("Replies recorded in ChampGraph. Pipeline complete.")
    else:
        print_info("No replies yet.  Re-run this command later to poll for updates.")
        print_info("All inbox messages:")
        if all_msgs:
            print_table(
                ["From", "Subject", "Received"],
                [[m["from"][:30], m["subject"][:40],
                  m["received_at"][:16]] for m in all_msgs],
            )


# ─────────────────────────────────────────────────────────────────────────────
# STATUS — full pipeline view for a prospect
# ─────────────────────────────────────────────────────────────────────────────

@outreach.command("status")
@click.argument("email")
@click.pass_obj
def cmd_status(obj, email):
    """Show full pipeline status for a prospect (graph timeline + DB record)."""
    _require_login(obj)

    async def _do():
        from app.db.postgres import init_db, get_db
        from app.services.prospect_service import prospect_service
        from app.db.falkordb import init_graph_db, graph_db

        await init_db()
        init_graph_db()

        async with get_db() as session:
            pg = await prospect_service.get_by_email(session, email)

        account = await _best_account(email)

        # Timeline from ChampGraph
        timeline_raw = await graph_db.query(
            f"Show me the complete timeline and history for {email}. "
            f"Include: prospect creation, questionnaire, email draft, email sent, replies.",
            account_name=account,
        )

        return {"pg": pg, "timeline": timeline_raw}

    data = obj.run(_do())

    if obj.json_output:
        print(json.dumps({"ok": True, "email": email, **data}, default=str))
        return

    print_section(f"Pipeline Status: {email}")

    pg = data.get("pg")
    if pg:
        print_kv("DB Record",  "found")
        print_kv("Name",       f"{pg.get('first_name','')} {pg.get('last_name','')}".strip() or "—")
        print_kv("Company",    pg.get("company_name", "—"))
        print_kv("Status",     pg.get("status", "—"))
    else:
        print_warning("No PostgreSQL record found.  Run: outreach prospect " + email)

    timeline = data.get("timeline", [])
    if timeline:
        print_section("ChampGraph Timeline")
        for item in timeline:
            name    = item.get("name", "")
            summary = item.get("summary", item.get("fact", ""))
            if name or summary:
                click.echo(f"  \033[36m•\033[0m {name}: {str(summary)[:100]}")
    else:
        print_info("No ChampGraph timeline yet.  Start with: outreach prospect " + email)


# ─────────────────────────────────────────────────────────────────────────────
# START — full guided wizard
# ─────────────────────────────────────────────────────────────────────────────

@outreach.command("start")
@click.argument("email")
@click.option("--first-name",    "first_name",      default="", help="Prospect first name.")
@click.option("--last-name",     "last_name",       default="", help="Prospect last name.")
@click.option("--title",         default="",        help="Job title.")
@click.option("--phone",         default="",        help="Phone.")
@click.option("--company",       "company_name",    default="", help="Company name.")
@click.option("--domain",        "company_domain",  default="", help="Company domain.")
@click.option("--industry",      default="",        help="Industry.")
@click.option("--answers-file",  "answers_file",    default=None, type=click.Path(exists=True),
              help="Pre-filled questionnaire JSON (skips interactive prompts).")
@click.option("--draft-file",    "draft_file",      default=None, type=click.Path(),
              help="Save AI email draft to this file.")
@click.option("--skip-send",     is_flag=True, default=False, help="Prep email but don't send.")
@click.pass_obj
def cmd_start(obj, email, first_name, last_name, title, phone,
              company_name, company_domain, industry,
              answers_file, draft_file, skip_send):
    """Full guided pipeline: prospect → research → questionnaire → prep → send → replies."""
    _require_login(obj)

    # ── Step 1: Prospect ──────────────────────────────────────────────────────
    if not obj.json_output:
        click.echo()
        click.echo("\033[1;35m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m")
        click.echo("\033[1;35m  ChampMail Outreach Pipeline\033[0m")
        click.echo("\033[1;35m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m")
        click.echo()

    ctx = click.get_current_context()

    # Invoke each sub-command with the shared obj
    ctx.invoke(cmd_prospect, email=email, first_name=first_name, last_name=last_name,
               title=title, phone=phone, linkedin_url="",
               company_name=company_name, company_domain=company_domain, industry=industry)

    # ── Step 2: Research ──────────────────────────────────────────────────────
    if not obj.json_output:
        click.echo()
    ctx.invoke(cmd_research, email=email)

    # ── Step 3: Questionnaire ─────────────────────────────────────────────────
    if not obj.json_output:
        click.echo()
    ctx.invoke(cmd_questionnaire, email=email, answers_file=answers_file)

    # ── Step 4: Prep ──────────────────────────────────────────────────────────
    if not obj.json_output:
        click.echo()
    ctx.invoke(cmd_prep, email=email, subject=None, save_to=draft_file)

    # ── Step 5: Send ──────────────────────────────────────────────────────────
    if not skip_send:
        if not obj.json_output:
            click.echo()
            if not click.confirm("\033[33m  Send the email now?\033[0m", default=True):
                print_info("Skipping send.  Run:  outreach send " + email)
                return
        ctx.invoke(cmd_send, email=email, subject=None, body=None,
                   draft_file=draft_file, from_name=None, from_email_addr=None)

    # ── Step 6: Replies ───────────────────────────────────────────────────────
    if not obj.json_output:
        click.echo()
        print_info("Checking for replies (may be empty if just sent)...")
    ctx.invoke(cmd_replies, email=email, limit=10)

    if not obj.json_output:
        click.echo()
        click.echo("\033[1;32m  Pipeline complete for " + email + "\033[0m")
        click.echo("\033[36m  Re-run  outreach replies " + email + "  to poll for new replies.\033[0m")
        click.echo()
