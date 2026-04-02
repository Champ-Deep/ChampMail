"""
champmail setup — Admin configuration wizard.

Separate setup sections, each independently configurable:

  setup domain      — sending domain name + provider
  setup smtp        — SMTP outbound credentials
  setup imap        — IMAP reply-detection credentials
  setup prospect    — default prospect fields
  setup campaign    — default campaign settings
  setup ai          — OpenRouter API key + model
  setup show        — print all stored config
  setup test        — test SMTP + IMAP connections live

All settings are stored in ~/.champmail/config.json and synced to .env.
"""

from __future__ import annotations

import json
import sys

import click

from cli.config_store import (
    get_section, get_value, load_config, save_config,
    set_section, sync_to_env, apply_to_runtime,
)
from cli.repl_skin import (
    print_error, print_info, print_kv, print_section,
    print_success, print_table, print_warning,
)
from cli.session import is_logged_in


def _require_login(obj):
    if not is_logged_in():
        print_error("Not logged in.  Run: champmail auth login")
        raise SystemExit(1)


def _prompt(label: str, default: str = "", password: bool = False, required: bool = False) -> str:
    """Prompt with optional default shown. Returns default immediately if not a tty."""
    # Non-interactive (piped / --yes with all flags provided): just use default
    if not sys.stdin.isatty():
        return default
    suffix = f" [{default}]" if default and not password else (" [hidden]" if password and default else "")
    click.echo(f"  \033[36m{label}{suffix}:\033[0m ", nl=False)
    val = click.prompt("", default=default or "", hide_input=password, show_default=False).strip()
    if required and not val:
        print_error(f"{label} is required.")
        raise SystemExit(1)
    return val or default


# ── group ─────────────────────────────────────────────────────────────────────

@click.group()
def setup() -> None:
    """Admin configuration: domain, SMTP, IMAP, prospects, campaigns, AI."""


# ─────────────────────────────────────────────────────────────────────────────
# setup domain
# ─────────────────────────────────────────────────────────────────────────────

@setup.command("domain")
@click.option("--name",     default=None, help="Domain name (e.g. outreach.acme.com).")
@click.option("--provider", default=None, help="DNS provider (cloudflare/namecheap/other).")
@click.option("--yes", "-y", is_flag=True, default=False, help="Skip confirmation.")
@click.pass_obj
def setup_domain(obj, name, provider, yes):
    """Configure your sending domain."""
    _require_login(obj)
    existing = get_section("domain")

    print_section("Setup — Sending Domain")
    print_info("This is the domain from which cold emails are sent.")
    print_info("Examples: outreach.yourcompany.com  |  mail.yourcompany.com")
    click.echo()

    d_name     = name     or _prompt("Domain name",  existing.get("name", ""))
    d_provider = provider or _prompt("DNS provider", existing.get("provider", "cloudflare"))

    if not yes:
        click.echo()
        print_kv("Domain",   d_name)
        print_kv("Provider", d_provider)
        click.echo()
        if not click.confirm("  Save these settings?", default=True):
            print_info("Cancelled.")
            return

    set_section("domain", {"name": d_name, "provider": d_provider})
    sync_to_env()

    if obj.json_output:
        print(json.dumps({"ok": True, "domain": {"name": d_name, "provider": d_provider}}))
    else:
        print_success(f"Domain saved: {d_name} ({d_provider})")
        print_info("Next: champmail setup smtp")


# ─────────────────────────────────────────────────────────────────────────────
# setup smtp
# ─────────────────────────────────────────────────────────────────────────────

@setup.command("smtp")
@click.option("--host",       default=None)
@click.option("--port",       default=None, type=int)
@click.option("--username",   default=None)
@click.option("--password",   default=None)
@click.option("--from-email", "from_email", default=None)
@click.option("--from-name",  "from_name",  default=None)
@click.option("--no-tls",     is_flag=True, default=False, help="Disable STARTTLS.")
@click.option("--yes", "-y",  is_flag=True, default=False)
@click.pass_obj
def setup_smtp(obj, host, port, username, password, from_email, from_name, no_tls, yes):
    """Configure SMTP outbound mail credentials."""
    _require_login(obj)
    existing = get_section("smtp")

    print_section("Setup — SMTP (Outbound)")
    print_info("For Ethereal testing: smtp.ethereal.email:587")
    print_info("For Gmail: smtp.gmail.com:587  (use App Password)")
    click.echo()

    s_host       = host       or _prompt("SMTP host",       existing.get("host", "smtp.ethereal.email"))
    s_port       = port       or int(_prompt("SMTP port",   str(existing.get("port", 587))))
    s_user       = username   or _prompt("Username",        existing.get("username", ""))
    s_pass       = password   or _prompt("Password",        existing.get("password", ""), password=True)
    s_from_email = from_email or _prompt("From email",      existing.get("from_email", ""))
    s_from_name  = from_name  or _prompt("From name",       existing.get("from_name", "ChampMail"))
    s_tls        = not no_tls

    values = {
        "host": s_host, "port": s_port,
        "username": s_user, "password": s_pass,
        "from_email": s_from_email, "from_name": s_from_name,
        "use_tls": s_tls,
    }

    if not yes:
        click.echo()
        print_kv("Host",       f"{s_host}:{s_port}")
        print_kv("Username",   s_user)
        print_kv("From",       f"{s_from_name} <{s_from_email}>")
        print_kv("TLS",        "yes" if s_tls else "no")
        click.echo()
        if not click.confirm("  Save SMTP settings?", default=True):
            print_info("Cancelled.")
            return

    set_section("smtp", values)
    sync_to_env()
    apply_to_runtime()

    if obj.json_output:
        safe = {k: v for k, v in values.items() if k != "password"}
        print(json.dumps({"ok": True, "smtp": safe}))
    else:
        print_success(f"SMTP saved: {s_host}:{s_port} ({s_user})")
        print_info("Run  champmail setup test smtp  to verify connection.")


# ─────────────────────────────────────────────────────────────────────────────
# setup imap
# ─────────────────────────────────────────────────────────────────────────────

@setup.command("imap")
@click.option("--host",     default=None)
@click.option("--port",     default=None, type=int)
@click.option("--username", default=None)
@click.option("--password", default=None)
@click.option("--mailbox",  default=None)
@click.option("--no-ssl",   is_flag=True, default=False)
@click.option("--yes", "-y", is_flag=True, default=False)
@click.pass_obj
def setup_imap(obj, host, port, username, password, mailbox, no_ssl, yes):
    """Configure IMAP reply-detection credentials."""
    _require_login(obj)
    existing = get_section("imap")

    print_section("Setup — IMAP (Reply Detection)")
    print_info("For Ethereal: imap.ethereal.email:993")
    print_info("For Gmail: imap.gmail.com:993  (use App Password)")
    click.echo()

    i_host    = host     or _prompt("IMAP host",    existing.get("host", "imap.ethereal.email"))
    i_port    = port     or int(_prompt("IMAP port", str(existing.get("port", 993))))
    i_user    = username or _prompt("Username",     existing.get("username", ""))
    i_pass    = password or _prompt("Password",     existing.get("password", ""), password=True)
    i_mailbox = mailbox  or _prompt("Mailbox",      existing.get("mailbox", "INBOX"))
    i_ssl     = not no_ssl

    values = {
        "host": i_host, "port": i_port,
        "username": i_user, "password": i_pass,
        "mailbox": i_mailbox, "use_ssl": i_ssl,
    }

    if not yes:
        click.echo()
        print_kv("Host",    f"{i_host}:{i_port}")
        print_kv("Username", i_user)
        print_kv("Mailbox",  i_mailbox)
        print_kv("SSL",      "yes" if i_ssl else "no")
        click.echo()
        if not click.confirm("  Save IMAP settings?", default=True):
            print_info("Cancelled.")
            return

    set_section("imap", values)
    sync_to_env()
    apply_to_runtime()

    if obj.json_output:
        safe = {k: v for k, v in values.items() if k != "password"}
        print(json.dumps({"ok": True, "imap": safe}))
    else:
        print_success(f"IMAP saved: {i_host}:{i_port} ({i_user})")
        print_info("Run  champmail setup test imap  to verify connection.")


# ─────────────────────────────────────────────────────────────────────────────
# setup prospect
# ─────────────────────────────────────────────────────────────────────────────

@setup.command("prospect")
@click.option("--industry",    default=None)
@click.option("--company",     default=None)
@click.option("--title",       default=None)
@click.option("--phone",       default=None, help="Default phone number prefix / format hint.")
@click.option("--linkedin",    "linkedin_url", default=None, help="Example LinkedIn base URL (e.g. linkedin.com/in/).")
@click.option("--source",      default=None, help="Default source label (e.g. linkedin, referral).")
@click.option("--yes", "-y",   is_flag=True, default=False)
@click.pass_obj
def setup_prospect(obj, industry, company, title, phone, linkedin_url, source, yes):
    """Set default prospect field values used when creating new prospects."""
    _require_login(obj)
    existing = get_section("prospect_defaults")

    print_section("Setup — Prospect Defaults")
    print_info("These defaults pre-fill fields when creating new prospects.")
    print_info("Per-prospect fields (name, email, phone, LinkedIn) are collected during outreach.")
    click.echo()

    p_industry  = industry     or _prompt("Default industry",  existing.get("industry", "SaaS"))
    p_company   = company      or _prompt("Default company",   existing.get("company", ""))
    p_title     = title        or _prompt("Default title",     existing.get("title", ""))
    p_phone     = phone        or _prompt("Phone (optional)",  existing.get("phone", ""))
    p_linkedin  = linkedin_url or _prompt("LinkedIn base URL", existing.get("linkedin_url", "linkedin.com/in/"))
    p_source    = source       or _prompt("Default source",    existing.get("source", "linkedin"))

    values = {
        "industry": p_industry, "company": p_company, "title": p_title,
        "phone": p_phone, "linkedin_url": p_linkedin, "source": p_source,
    }

    if not yes:
        click.echo()
        for k, v in values.items():
            if v:
                print_kv(k.replace("_", " ").title(), v)
        click.echo()
        if not click.confirm("  Save prospect defaults?", default=True):
            print_info("Cancelled.")
            return

    set_section("prospect_defaults", values)

    if obj.json_output:
        print(json.dumps({"ok": True, "prospect_defaults": values}))
    else:
        print_success("Prospect defaults saved.")


# ─────────────────────────────────────────────────────────────────────────────
# setup campaign
# ─────────────────────────────────────────────────────────────────────────────

@setup.command("campaign")
@click.option("--from-name",    "from_name",   default=None)
@click.option("--from-email",   "from_email",  default=None)
@click.option("--reply-to",     "reply_to",    default=None)
@click.option("--daily-limit",  "daily_limit", default=None, type=int)
@click.option("--goal",         default=None,  help="Default outreach goal / pitch description.")
@click.option("--tone",         default=None,  help="Default email tone (casual/direct/formal).")
@click.option("--cta",          default=None,  help="Default CTA in emails.")
@click.option("--yes", "-y",    is_flag=True, default=False)
@click.pass_obj
def setup_campaign(obj, from_name, from_email, reply_to, daily_limit, goal, tone, cta, yes):
    """Set default campaign settings used as starting values for new campaigns."""
    _require_login(obj)
    existing = get_section("campaign_defaults")

    print_section("Setup — Campaign Defaults")
    click.echo()

    smtp = get_section("smtp")
    c_from_name  = from_name   or _prompt("Default from name",   existing.get("from_name",  smtp.get("from_name", "ChampMail")))
    c_from_email = from_email  or _prompt("Default from email",  existing.get("from_email", smtp.get("from_email", "")))
    c_reply_to   = reply_to    or _prompt("Default reply-to",    existing.get("reply_to", ""))
    c_daily_limit = daily_limit or int(_prompt("Daily send limit", str(existing.get("daily_limit", 50))))
    c_goal       = goal        or _prompt("Default goal",        existing.get("goal", "book a discovery call"))
    c_tone       = tone        or _prompt("Default tone",        existing.get("tone", "casual"))
    c_cta        = cta         or _prompt("Default CTA",         existing.get("cta", "15-min call this week?"))

    values = {
        "from_name": c_from_name, "from_email": c_from_email, "reply_to": c_reply_to,
        "daily_limit": c_daily_limit, "goal": c_goal, "tone": c_tone, "cta": c_cta,
    }

    if not yes:
        click.echo()
        for k, v in values.items():
            if v:
                print_kv(k.replace("_", " ").title(), str(v))
        click.echo()
        if not click.confirm("  Save campaign defaults?", default=True):
            print_info("Cancelled.")
            return

    set_section("campaign_defaults", values)

    if obj.json_output:
        print(json.dumps({"ok": True, "campaign_defaults": values}))
    else:
        print_success("Campaign defaults saved.")


# ─────────────────────────────────────────────────────────────────────────────
# setup ai
# ─────────────────────────────────────────────────────────────────────────────

@setup.command("ai")
@click.option("--api-key",  "api_key", default=None, help="OpenRouter API key.")
@click.option("--model",    default=None, help="Model slug (e.g. openai/gpt-4.1-mini).")
@click.option("--yes", "-y", is_flag=True, default=False)
@click.pass_obj
def setup_ai(obj, api_key, model, yes):
    """Configure AI settings (OpenRouter key + model for email generation)."""
    _require_login(obj)
    existing = get_section("ai")

    print_section("Setup — AI (OpenRouter)")
    print_info("Get your key at: https://openrouter.ai/keys")
    print_info("Recommended models: openai/gpt-4.1-mini  |  anthropic/claude-haiku-4-5")
    click.echo()

    a_key   = api_key or _prompt("OpenRouter API key", existing.get("openrouter_api_key", ""), password=True)
    a_model = model   or _prompt("Model",              existing.get("model", "openai/gpt-4.1-mini"))

    values = {"openrouter_api_key": a_key, "model": a_model}

    if not yes:
        click.echo()
        print_kv("Model",   a_model)
        print_kv("API key", "***" + a_key[-6:] if len(a_key) > 6 else "set")
        click.echo()
        if not click.confirm("  Save AI settings?", default=True):
            print_info("Cancelled.")
            return

    set_section("ai", values)
    sync_to_env()
    apply_to_runtime()

    if obj.json_output:
        print(json.dumps({"ok": True, "ai": {"model": a_model}}))
    else:
        print_success(f"AI settings saved. Model: {a_model}")


# ─────────────────────────────────────────────────────────────────────────────
# setup show
# ─────────────────────────────────────────────────────────────────────────────

@setup.command("show")
@click.pass_obj
def setup_show(obj):
    """Show all stored configuration (passwords hidden)."""
    _require_login(obj)
    cfg = load_config()

    if obj.json_output:
        # Strip passwords before output
        safe = json.loads(json.dumps(cfg))
        for section in ("smtp", "imap"):
            if section in safe:
                safe[section].pop("password", None)
        print(json.dumps({"ok": True, "config": safe}))
        return

    if not cfg:
        print_warning("No configuration saved yet. Run: champmail setup domain")
        return

    SECTIONS = [
        ("domain",           "Domain"),
        ("smtp",             "SMTP (Outbound)"),
        ("imap",             "IMAP (Reply Detection)"),
        ("prospect_defaults","Prospect Defaults"),
        ("campaign_defaults","Campaign Defaults"),
        ("ai",               "AI"),
    ]

    for key, label in SECTIONS:
        data = cfg.get(key)
        if not data:
            continue
        print_section(label)
        for k, v in data.items():
            if k == "password":
                v = "●●●●●●●●"
            elif k == "openrouter_api_key":
                v = "***" + str(v)[-6:] if len(str(v)) > 6 else "set"
            print_kv(k.replace("_", " ").title(), str(v))


# ─────────────────────────────────────────────────────────────────────────────
# setup test
# ─────────────────────────────────────────────────────────────────────────────

@setup.command("test")
@click.argument("what", type=click.Choice(["smtp", "imap", "all"]), default="all")
@click.pass_obj
def setup_test(obj, what):
    """Test SMTP and/or IMAP connections using stored credentials."""
    _require_login(obj)
    apply_to_runtime()

    results = {}

    async def _do():
        from app.services.email_provider import get_email_provider, get_reply_detector

        if what in ("smtp", "all"):
            provider = get_email_provider()
            ok = await provider.verify_connection()
            results["smtp"] = ok

        if what in ("imap", "all"):
            detector = get_reply_detector()
            ok = await detector.verify_connection()
            results["imap"] = ok

        return results

    from cli.context import CliContext
    ctx = obj if hasattr(obj, "run") else CliContext()
    r = ctx.run(_do())

    if obj.json_output:
        print(json.dumps({"ok": all(r.values()), **r}))
        return

    print_section("Connection Tests")
    smtp_cfg = get_section("smtp")
    imap_cfg = get_section("imap")

    if "smtp" in r:
        if r["smtp"]:
            print_success(f"SMTP OK  — {smtp_cfg.get('host')}:{smtp_cfg.get('port')}")
        else:
            print_warning(f"SMTP failed — {smtp_cfg.get('host')}:{smtp_cfg.get('port')}")
            print_info("Note: outbound SMTP ports may be blocked in sandboxed environments.")

    if "imap" in r:
        if r["imap"]:
            print_success(f"IMAP OK  — {imap_cfg.get('host')}:{imap_cfg.get('port')}")
        else:
            print_warning(f"IMAP failed — {imap_cfg.get('host')}:{imap_cfg.get('port')}")
            print_info("Note: IMAP ports may be blocked in sandboxed environments.")
