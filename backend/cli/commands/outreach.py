"""
champmail outreach — End-to-end cold outreach pipeline.

Full process in one command group:

  outreach start         EMAIL [options]     # full guided wizard
  outreach prospect      EMAIL [options]     # step 1: create + research prospect
  outreach research      EMAIL              # step 2: query ChampGraph for context
  outreach view-research EMAIL              # view saved research from DB (no API calls)
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

        # 1b — ChampGraph ingest (rich prospect profile for research agent)
        full_name = f"{first_name} {last_name}".strip() or email
        parts = [f"{full_name} is a prospect in the ChampMail outreach system."]
        parts.append(f"Email: {email}")
        if first_name:   parts.append(f"First name: {first_name}")
        if last_name:    parts.append(f"Last name: {last_name}")
        if title:        parts.append(f"Job title: {title}")
        if phone:        parts.append(f"Phone number: {phone}")
        if linkedin_url: parts.append(f"LinkedIn profile: {linkedin_url}")
        if company_name: parts.append(f"Works at company: {company_name}")
        if company_domain: parts.append(f"Company website/domain: {company_domain}")
        if industry:     parts.append(f"Industry: {industry}")
        # Summary sentence for the research agent
        who = f"{full_name}, {title} at {company_name}" if title and company_name else full_name
        parts.append(
            f"Summary: {who} can be reached at {email}"
            + (f" or {phone}" if phone else "")
            + (f". LinkedIn: {linkedin_url}" if linkedin_url else "")
            + "."
        )

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
@click.option("--detailed", is_flag=True, default=False,
              help="Show full detailed Perplexity research output.")
@click.pass_obj
def cmd_research(obj, email, account_override, detailed):
    """Step 2 — Pull full knowledge graph profile + live web research via Perplexity."""
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

        # ── Live web research via Perplexity ──────────────────────────
        perplexity_data = {}
        try:
            from app.services.ai.openrouter_service import research_service

            prospect_dict = {
                "id": pg.get("id") if pg else None,
                "email": email,
                "first_name": pg.get("first_name", "") if pg else "",
                "last_name": pg.get("last_name", "") if pg else "",
                "title": pg.get("title", "") if pg else "",
                "company_name": pg.get("company_name", "") if pg else "",
                "company_domain": pg.get("company_domain", "") if pg else "",
                "linkedin_url": pg.get("linkedin_url", "") if pg else "",
            }

            perplexity_data = await research_service.research_prospect(prospect_dict)

            # Ingest Perplexity findings into ChampGraph for later steps
            if perplexity_data and not perplexity_data.get("error"):
                ingest_parts = [f"Web Research for {email}"]
                ci = perplexity_data.get("company_info", {})
                if isinstance(ci, dict) and ci.get("description"):
                    ingest_parts.append(f"Company: {ci['description']}")
                if isinstance(ci, dict):
                    for news in ci.get("recent_news", [])[:5]:
                        ingest_parts.append(f"News: {news}")
                pi = perplexity_data.get("person_intel", {})
                if isinstance(pi, dict):
                    if pi.get("linkedin_headline"):
                        ingest_parts.append(f"LinkedIn headline: {pi['linkedin_headline']}")
                    if pi.get("career_background"):
                        ingest_parts.append(f"Background: {pi['career_background']}")
                    for post in pi.get("recent_posts", [])[:3]:
                        ingest_parts.append(f"Recent post: {post}")
                    for talk in pi.get("articles_or_talks", [])[:3]:
                        ingest_parts.append(f"Article/talk: {talk}")
                    for interest in pi.get("interests", [])[:5]:
                        ingest_parts.append(f"Interest: {interest}")
                for hook in perplexity_data.get("personalization_hooks", []):
                    ingest_parts.append(f"Hook: {hook}")

                await gdb._ingest(
                    content="\n".join(ingest_parts),
                    name=f"Web Research: {email}",
                    account_name=best_account,
                    source="perplexity_research",
                )

                # Persist research data to PostgreSQL for later retrieval
                if pg and pg.get("id"):
                    try:
                        async with get_db() as session:
                            await prospect_service.save_research_data(
                                session, pg["id"], perplexity_data, "completed",
                            )
                    except Exception:
                        pass  # DB save failure should not block pipeline
        except Exception:
            pass  # Perplexity failure should not block the pipeline

        return {
            "account": best_account,
            "candidates_queried": candidates,
            "nodes": nodes,
            "briefing": briefing,
            "email_context": ctx,
            "perplexity": perplexity_data,
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

    perp = data.get("perplexity", {})
    if perp and not perp.get("error"):
        # Truncation limit — detailed mode shows everything
        _t = 10000 if detailed else 120

        print_section("Web Research (Perplexity)")

        # ── Company Info ──
        ci = perp.get("company_info", {})
        if isinstance(ci, dict):
            if ci.get("description"):
                print_kv("Company", str(ci["description"])[:_t])
            if ci.get("industry"):
                print_kv("Industry", str(ci["industry"])[:_t])
            if detailed:
                if ci.get("size"):
                    print_kv("Size", str(ci["size"])[:_t])
                if ci.get("revenue"):
                    print_kv("Revenue", str(ci["revenue"])[:_t])
                for prod in ci.get("products", []):
                    print_kv("Product", str(prod)[:_t])
                for tech in ci.get("tech_stack", []):
                    print_kv("Tech", str(tech)[:_t])
            for news in ci.get("recent_news", [])[:5 if detailed else 2]:
                print_kv("News", str(news)[:_t])

        # ── Person Intel ──
        pi = perp.get("person_intel", {})
        if isinstance(pi, dict):
            if pi.get("linkedin_headline"):
                print_kv("LinkedIn", str(pi["linkedin_headline"])[:_t])
            if pi.get("linkedin_about") and detailed:
                print_kv("About", str(pi["linkedin_about"])[:_t])
            if pi.get("career_background"):
                print_kv("Background", str(pi["career_background"])[:_t])
            for post in pi.get("recent_posts", [])[:5 if detailed else 2]:
                print_kv("Post", str(post)[:_t])
            for talk in pi.get("articles_or_talks", [])[:5 if detailed else 2]:
                print_kv("Talk/Article", str(talk)[:_t])
            for profile in pi.get("public_profiles", [])[:5 if detailed else 0]:
                print_kv("Profile", str(profile)[:_t])
            for interest in pi.get("interests", [])[:5 if detailed else 3]:
                print_kv("Interest", str(interest)[:_t])

        # ── Persona Details ──
        pd = perp.get("persona_details", {})
        if isinstance(pd, dict) and detailed:
            if pd.get("responsibilities"):
                print_section("Persona Details")
                for r in pd.get("responsibilities", []):
                    print_kv("Responsibility", str(r)[:_t])
                for c in pd.get("challenges", []):
                    print_kv("Challenge", str(c)[:_t])
                for p in pd.get("priorities", []):
                    print_kv("Priority", str(p)[:_t])
                if pd.get("decision_authority"):
                    print_kv("Decision Auth", str(pd["decision_authority"])[:_t])

        # ── Triggers ──
        triggers = perp.get("triggers", {})
        if isinstance(triggers, dict):
            for tk in ("funding", "expansion", "leadership_changes", "acquisitions"):
                val = triggers.get(tk)
                if val and str(val).lower() not in ("null", "none", ""):
                    print_kv(tk.replace("_", " ").title(), str(val)[:_t])
            if detailed:
                for hire in triggers.get("hiring", []):
                    print_kv("Hiring", str(hire)[:_t])

        # ── Industry Insights ──
        ii = perp.get("industry_insights", {})
        if isinstance(ii, dict) and detailed:
            for trend in ii.get("trends", []):
                print_kv("Trend", str(trend)[:_t])
            for pp in ii.get("pain_points", []):
                print_kv("Pain Point", str(pp)[:_t])

        # ── Personalization Hooks ──
        hooks = perp.get("personalization_hooks", [])
        if hooks:
            if detailed:
                print_section("Personalization Hooks")
            for hook in hooks[:7 if detailed else 3]:
                print_kv("Hook", str(hook)[:_t])

    elif perp and perp.get("error"):
        print_warning(f"Web research failed: {perp['error'][:80]}")

    if not detailed and perp and not perp.get("error"):
        print_info("Run with --detailed for full research output")

    print_success("Research done.  Run next: outreach questionnaire " + email)


# ─────────────────────────────────────────────────────────────────────────────
# VIEW-RESEARCH — display saved research from DB (no re-fetch)
# ─────────────────────────────────────────────────────────────────────────────

@outreach.command("view-research")
@click.argument("email")
@click.option("--raw", is_flag=True, default=False, help="Dump full raw JSON.")
@click.pass_obj
def cmd_view_research(obj, email, raw):
    """View saved research data for a prospect (from DB, no API calls)."""
    _require_login(obj)

    async def _do():
        from app.db.postgres import init_db, get_db
        from app.services.prospect_service import prospect_service

        await init_db()
        async with get_db() as session:
            pg = await prospect_service.get_by_email(session, email)

        if not pg:
            return None, "No prospect record found. Run: outreach prospect " + email
        if not pg.get("research_data"):
            return None, (
                f"No research data saved for {email}. "
                f"Research status: {pg.get('research_status', 'pending')}. "
                f"Run: outreach research {email}"
            )
        return {"prospect": pg, "research": pg["research_data"]}, None

    result, err = obj.run(_do())

    if err:
        if obj.json_output:
            print(json.dumps({"ok": False, "error": err}))
        else:
            print_error(err)
        return

    research = result["research"]
    pg = result["prospect"]

    if obj.json_output:
        print(json.dumps({"ok": True, "email": email, "research": research}, default=str))
        return

    if raw:
        print(json.dumps(research, indent=2, default=str))
        return

    name = f"{pg.get('first_name', '')} {pg.get('last_name', '')}".strip() or email
    print_section(f"Saved Research: {name} ({email})")
    print_kv("Research Status", pg.get("research_status", "unknown"))
    click.echo()

    # ── Company Info ──
    ci = research.get("company_info", {})
    if isinstance(ci, dict) and ci:
        print_section("Company Info")
        for key in ("description", "industry", "size", "revenue"):
            val = ci.get(key)
            if val and str(val).lower() not in ("null", "none", ""):
                print_kv(key.replace("_", " ").title(), str(val))
        for prod in ci.get("products", []):
            print_kv("Product", str(prod))
        for tech in ci.get("tech_stack", []):
            print_kv("Tech Stack", str(tech))
        for news in ci.get("recent_news", []):
            print_kv("Recent News", str(news))

    # ── Person Intel ──
    pi = research.get("person_intel", {})
    if isinstance(pi, dict) and pi:
        print_section("Person Intel")
        for key in ("linkedin_headline", "linkedin_about", "career_background"):
            val = pi.get(key)
            if val and str(val).lower() not in ("null", "none", ""):
                print_kv(key.replace("_", " ").title(), str(val))
        for post in pi.get("recent_posts", []):
            print_kv("Recent Post", str(post))
        for talk in pi.get("articles_or_talks", []):
            print_kv("Article/Talk", str(talk))
        for profile in pi.get("public_profiles", []):
            print_kv("Profile", str(profile))
        for interest in pi.get("interests", []):
            print_kv("Interest", str(interest))

    # ── Persona Details ──
    pd = research.get("persona_details", {})
    if isinstance(pd, dict) and pd:
        print_section("Persona Details")
        for r in pd.get("responsibilities", []):
            print_kv("Responsibility", str(r))
        for c in pd.get("challenges", []):
            print_kv("Challenge", str(c))
        for p in pd.get("priorities", []):
            print_kv("Priority", str(p))
        if pd.get("decision_authority"):
            print_kv("Decision Authority", str(pd["decision_authority"]))

    # ── Triggers ──
    triggers = research.get("triggers", {})
    if isinstance(triggers, dict) and triggers:
        print_section("Business Triggers")
        for tk in ("funding", "acquisitions", "leadership_changes", "hiring", "expansion"):
            val = triggers.get(tk)
            if val and str(val).lower() not in ("null", "none", "", "[]"):
                if isinstance(val, list):
                    for item in val:
                        print_kv(tk.replace("_", " ").title(), str(item))
                else:
                    print_kv(tk.replace("_", " ").title(), str(val))

    # ── Industry Insights ──
    ii = research.get("industry_insights", {})
    if isinstance(ii, dict) and ii:
        print_section("Industry Insights")
        for trend in ii.get("trends", []):
            print_kv("Trend", str(trend))
        for pp in ii.get("pain_points", []):
            print_kv("Pain Point", str(pp))
        if ii.get("regulatory"):
            print_kv("Regulatory", str(ii["regulatory"]))

    # ── Personalization Hooks ──
    hooks = research.get("personalization_hooks", [])
    if hooks:
        print_section("Personalization Hooks")
        for i, hook in enumerate(hooks, 1):
            print_kv(f"Hook {i}", str(hook))

    click.echo()
    print_info("Use --raw for full JSON dump")


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
@click.option("--answers-file", "answers_file", default=None, type=click.Path(exists=True),
              help="Questionnaire answers JSON (used as primary campaign context).")
@click.pass_obj
def cmd_prep(obj, email, subject, save_to, answers_file):
    """Step 4 — Pull research + questionnaire from ChampGraph, generate personalised email draft via AI."""
    _require_login(obj)

    # Load raw questionnaire answers if available — these are the PRIMARY
    # source of truth for campaign intent (not the ChampGraph summary).
    raw_answers = {}
    if answers_file:
        try:
            with open(answers_file) as f:
                raw_answers = json.load(f)
        except Exception:
            pass

    async def _do():
        import httpx
        from app.core.config import settings
        from app.db.postgres import init_db, get_db
        from app.services.prospect_service import prospect_service

        gdb = _graph_init()
        account = await _best_account(email)

        # ── Prospect details from DB ──
        await init_db()
        prospect_info = ""
        async with get_db() as session:
            pg = await prospect_service.get_by_email(session, email)
        if pg:
            prospect_info = (
                f"Name: {pg.get('first_name', '')} {pg.get('last_name', '')}\n"
                f"Title: {pg.get('job_title', '')}\n"
                f"Company: {pg.get('company_name', '')}\n"
                f"Industry: {pg.get('industry', '')}\n"
                f"LinkedIn: {pg.get('linkedin_url', '')}"
            )

        # ── Saved Perplexity research from DB ──
        research_text = "No prior research available."
        if pg and pg.get("research_data"):
            rd = pg["research_data"]
            parts = []
            ci = rd.get("company_info", {})
            if isinstance(ci, dict):
                if ci.get("description"):
                    parts.append(f"Company: {ci['description']}")
                if ci.get("industry"):
                    parts.append(f"Industry: {ci['industry']}")
                for news in ci.get("recent_news", [])[:3]:
                    parts.append(f"Recent news: {news}")
            pi = rd.get("person_intel", {})
            if isinstance(pi, dict):
                if pi.get("linkedin_headline"):
                    parts.append(f"LinkedIn: {pi['linkedin_headline']}")
                if pi.get("career_background"):
                    parts.append(f"Background: {pi['career_background']}")
                for interest in pi.get("interests", [])[:5]:
                    parts.append(f"Interest: {interest}")
            for hook in rd.get("personalization_hooks", [])[:5]:
                parts.append(f"Personalization hook: {hook}")
            triggers = rd.get("triggers", {})
            if isinstance(triggers, dict):
                for tk in ("funding", "expansion", "leadership_changes"):
                    val = triggers.get(tk)
                    if val and str(val).lower() not in ("null", "none", ""):
                        parts.append(f"Trigger - {tk}: {val}")
            if parts:
                research_text = "\n".join(f"- {p}" for p in parts)

        # ── ChampGraph context (supplementary) ──
        graph_context = ""
        try:
            graph_nodes = await gdb.query(
                f"Everything known about {email} — role, company, interests, "
                f"background, topics, relationships.",
                account_name=account,
            )
            graph_lines = [
                f"- {n.get('name','')}: {n.get('summary','')}"
                for n in graph_nodes if n.get("type") == "node" and n.get("summary")
            ]
            if graph_lines:
                graph_context = "\n".join(graph_lines)
        except Exception:
            pass

        ctx = await gdb.get_email_context(
            account_name=account,
            contact_email=email,
        )
        ctx_hints = ""
        if ctx.get("success") or ctx.get("context"):
            ctx_hints = "\n".join(
                f"- {k}: {v}" for k, v in ctx.items()
                if k not in ("success",) and v and isinstance(v, str)
            )

        # ── Build the CAMPAIGN INTENT section ──
        # If raw_answers exist, use them verbatim — they are the user's
        # real-time input and MUST take priority over graph summaries.
        if raw_answers:
            intent_lines = []
            field_labels = {
                "goal": "Campaign Goal",
                "pain_point": "Pain Point Solved",
                "value_prop": "Value Proposition",
                "context": "Why This Person Now",
                "cta": "Call to Action",
                "tone": "Tone",
                "sender": "Sender Name & Role",
                "sender_position": "Sender Position",
                "sender_company": "Sender Company",
                "from_email": "Sender Email",
            }
            for key, label in field_labels.items():
                val = raw_answers.get(key, "").strip()
                if val:
                    intent_lines.append(f"- {label}: {val}")
            intent_text = "\n".join(intent_lines) or "No campaign intent provided."
        else:
            # Fallback: query ChampGraph for intent
            intent = await gdb.query(
                f"Campaign intent and questionnaire answers for outreach to {email}. "
                f"Goal, value proposition, pain point, CTA, tone, sender.",
                account_name=account,
            )
            intent_text = "\n".join(
                f"- {n.get('name','')}: {n.get('summary','')}"
                for n in intent if n.get("type") == "node" and n.get("summary")
            ) or "No questionnaire answers ingested yet."

        # ── Sender signature ──
        sender_name     = raw_answers.get("sender", "").strip()
        sender_position = raw_answers.get("sender_position", "").strip()
        sender_company  = raw_answers.get("sender_company", "").strip()
        sender_email    = raw_answers.get("from_email", "").strip()
        if not sender_name:
            from cli.config_store import get_value
            sender_name = get_value("campaign_defaults", "from_name") or ""
        if not sender_email:
            from cli.config_store import get_value
            sender_email = get_value("campaign_defaults", "from_email") or ""

        # Build signature block
        sig_parts = []
        if sender_name:
            sig_parts.append(sender_name)
        if sender_position:
            sig_parts.append(sender_position)
        if sender_company:
            sig_parts.append(sender_company)
        if sender_email:
            sig_parts.append(sender_email)

        signature_instruction = ""
        if sig_parts:
            sig_block = "\n  ".join(sig_parts)
            signature_instruction = f"""
IMPORTANT — Sender signature:
  The email MUST end with a professional signature block:
  {sig_block}
  Include "Best regards," or "Warm regards," before the signature.
  Do NOT use placeholder text like [Your Name] or [Your Position].
  Do NOT use "ChampMail Test" as sender — use the actual sender name above."""

        system_prompt = textwrap.dedent(f"""\
            You are an expert cold email copywriter.
            Write a single cold outreach email that is:
            - Personalised using the prospect research AND the campaign intent provided
            - Short (3-4 short paragraphs max)
            - Conversational and human — not salesy
            - Ends with one clear, low-friction CTA
            - Subject line is punchy and specific, not generic

            CRITICAL RULES:
            - The CAMPAIGN INTENT section contains the user's EXACT instructions.
              Use the EXACT goal, pain point, value prop, CTA, and tone they specified.
              Do NOT invent offers, discounts, or claims not in the campaign intent.
            - Use research data ONLY for personalisation (referencing their role,
              company, interests, recent events). Do NOT let research override
              the campaign intent.
            - The Call to Action MUST match what the user specified — do not change
              "5 min call" to "15-minute chat" or similar.
            {signature_instruction}

            Return a JSON object ONLY with keys:
              "subject": string,
              "body_html": string (HTML with <p> tags),
              "body_text": string (plain text version)
        """)

        user_prompt = textwrap.dedent(f"""\
            === PROSPECT INFO ===
            Email: {email}
            {prospect_info}

            === CAMPAIGN INTENT (PRIMARY — follow these instructions exactly) ===
            {intent_text}

            === PROSPECT RESEARCH (for personalisation only) ===
            {research_text}

            === KNOWLEDGE GRAPH CONTEXT (supplementary) ===
            {graph_context or 'None'}

            === EMAIL CONTEXT HINTS ===
            {ctx_hints or 'None'}

            Write the cold email now. Follow the campaign intent exactly.
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
            return None, "IMAP connection failed — check IMAP_HOST / IMAP_PORT / IMAP_USERNAME / IMAP_PASSWORD"

        try:
            msgs = await detector.check_new_messages()
        except Exception as e:
            return None, f"IMAP fetch error: {e}"

        account = await _best_account(email)

        matched = []
        for m in (msgs or [])[:limit]:
            from_addr = (m.from_email or "").lower().strip()
            prospect_email = email.lower().strip()

            # Primary: exact from-address match (reply came from the prospect)
            from_match = from_addr == prospect_email

            # Secondary: In-Reply-To / References headers indicate it's
            # a reply to a thread (any sender replying to our outreach)
            has_reply_headers = bool(m.in_reply_to or m.references)

            # Tertiary: subject starts with Re:/Fwd: AND sender domain matches
            prospect_domain = prospect_email.split("@")[-1] if "@" in prospect_email else ""
            from_domain = from_addr.split("@")[-1] if "@" in from_addr else ""
            subject_re = m.subject and m.subject.lower().lstrip().startswith(("re:", "fwd:"))
            domain_match = prospect_domain and from_domain == prospect_domain

            is_reply = from_match or (has_reply_headers and (from_match or domain_match)) or (subject_re and from_match)

            matched.append({
                "message_id": m.message_id,
                "from":       m.from_email,
                "from_name":  m.from_name or "",
                "subject":    m.subject,
                "body":       m.body[:500] if m.body else "",
                "received_at": m.received_at.isoformat(),
                "is_reply":   is_reply,
                "in_reply_to": m.in_reply_to or "",
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
        for i, r in enumerate(replies, 1):
            click.echo()
            click.echo(f"  \033[1;36m── Reply {i} ──────────────────────────────────────\033[0m")
            print_kv("From",     f"{r.get('from_name', '')} <{r['from']}>".strip())
            print_kv("Subject",  r["subject"][:80])
            print_kv("Received", r["received_at"][:19])
            if r.get("body"):
                click.echo(f"  \033[2m{'─' * 50}\033[0m")
                # Show first 300 chars of body, cleaned up
                body_preview = r["body"].strip().replace('\r\n', '\n')
                for line in body_preview[:300].split('\n')[:8]:
                    line = line.strip()
                    if line:
                        click.echo(f"  \033[2m  {line}\033[0m")
                if len(body_preview) > 300:
                    click.echo(f"  \033[2m  ...(truncated)\033[0m")
            click.echo(f"  \033[2m{'─' * 50}\033[0m")
        click.echo()
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
