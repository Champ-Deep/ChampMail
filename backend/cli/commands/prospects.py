"""
champmail prospects — Prospect management commands.

  prospects list    [--query] [--industry] [--limit] [--skip]
  prospects get     EMAIL
  prospects create  --email EMAIL [--first-name] [--last-name] [--title]
                    [--company-name] [--company-domain] [--industry]
  prospects update  EMAIL [--first-name] [--last-name] [--title]
  prospects delete  EMAIL
  prospects bulk-import  --file prospects.csv
  prospects timeline EMAIL
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import click

from cli.context import CliContext
from cli.repl_skin import print_error, print_info, print_kv, print_section, print_success, print_table
from cli.session import is_logged_in


def _require_login(obj):
    if not is_logged_in():
        print_error("Not logged in.  Run: champmail auth login")
        raise SystemExit(1)


@click.group()
def prospects() -> None:
    """Prospect management — CRUD and bulk import."""


# ── list ──────────────────────────────────────────────────────────────────────

@prospects.command("list")
@click.option("--query", "-q", default="", help="Search text.")
@click.option("--industry", default="", help="Filter by industry.")
@click.option("--limit", default=50, show_default=True)
@click.option("--skip", default=0, show_default=True)
@click.pass_obj
def list_prospects(obj, query, industry, limit, skip) -> None:
    """List / search prospects."""
    _require_login(obj)

    async def _do():
        from app.db.falkordb import init_graph_db, graph_db

        init_graph_db()
        results = await graph_db.search_prospects(
            query_text=query, industry=industry, limit=limit, skip=skip
        )
        out = []
        for r in results:
            p = r.get("p", {})
            props = p.get("properties", p) if isinstance(p, dict) else {}
            out.append({
                "email": props.get("email", ""),
                "first_name": props.get("first_name", ""),
                "last_name": props.get("last_name", ""),
                "title": props.get("title", ""),
                "id": str(p.get("id", "") or props.get("id", "")),
            })
        return [r for r in out if r["email"]]

    data = obj.run(_do())

    if obj.json_output:
        print(json.dumps({"ok": True, "prospects": data, "total": len(data)}))
    else:
        print_table(
            ["Email", "First", "Last", "Title"],
            [[d["email"], d["first_name"], d["last_name"], d["title"]] for d in data],
        )


# ── get ───────────────────────────────────────────────────────────────────────

@prospects.command("get")
@click.argument("email")
@click.pass_obj
def get_prospect(obj, email) -> None:
    """Get a prospect by email."""
    _require_login(obj)

    async def _do():
        from app.db.falkordb import init_graph_db, graph_db

        init_graph_db()
        return await graph_db.get_prospect_by_email(email)

    result = obj.run(_do())
    if not result or not result.get("p"):
        if obj.json_output:
            print(json.dumps({"ok": False, "error": "Prospect not found"}))
        else:
            print_error("Prospect not found.")
        raise SystemExit(1)

    p = result.get("p", {})
    props = p.get("properties", p) if isinstance(p, dict) else {}

    if obj.json_output:
        print(json.dumps({"ok": True, "prospect": props}))
    else:
        print_section(f"Prospect: {email}")
        for k, v in props.items():
            print_kv(k, str(v))


# ── create ────────────────────────────────────────────────────────────────────

@prospects.command("create")
@click.option("--email", required=True)
@click.option("--first-name", "first_name", default="")
@click.option("--last-name", "last_name", default="")
@click.option("--title", default="")
@click.option("--phone", default="")
@click.option("--linkedin-url", "linkedin_url", default="")
@click.option("--company-name", "company_name", default="")
@click.option("--company-domain", "company_domain", default="")
@click.option("--industry", default="")
@click.pass_obj
def create_prospect(obj, email, first_name, last_name, title, phone, linkedin_url,
                    company_name, company_domain, industry) -> None:
    """Create a new prospect."""
    _require_login(obj)

    async def _do():
        from app.db.falkordb import init_graph_db, graph_db

        init_graph_db()
        existing = await graph_db.get_prospect_by_email(email)
        if existing and existing.get("p"):
            return None, f"Prospect {email} already exists"

        await graph_db.create_prospect(
            email=email,
            first_name=first_name,
            last_name=last_name,
            title=title,
            phone=phone,
            linkedin_url=linkedin_url,
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
        return {"email": email}, None

    data, err = obj.run(_do())
    if err:
        if obj.json_output:
            print(json.dumps({"ok": False, "error": err}))
        else:
            print_error(err)
        raise SystemExit(1)

    if obj.json_output:
        print(json.dumps({"ok": True, **data}))
    else:
        print_success(f"Prospect created: {email}")


# ── update ────────────────────────────────────────────────────────────────────

@prospects.command("update")
@click.argument("email")
@click.option("--first-name", "first_name", default=None)
@click.option("--last-name", "last_name", default=None)
@click.option("--title", default=None)
@click.option("--phone", default=None)
@click.option("--linkedin-url", "linkedin_url", default=None)
@click.pass_obj
def update_prospect(obj, email, first_name, last_name, title, phone, linkedin_url) -> None:
    """Update prospect fields."""
    _require_login(obj)
    updates = {k: v for k, v in {
        "first_name": first_name, "last_name": last_name,
        "title": title, "phone": phone, "linkedin_url": linkedin_url,
    }.items() if v is not None}

    if not updates:
        print_error("No fields to update.")
        raise SystemExit(1)

    async def _do():
        from app.db.falkordb import init_graph_db, graph_db

        init_graph_db()
        existing = await graph_db.get_prospect_by_email(email)
        if not existing or not existing.get("p"):
            return None, "Prospect not found"
        await graph_db.create_prospect(email=email, **updates)
        return {"email": email, "updated": list(updates.keys())}, None

    data, err = obj.run(_do())
    if err:
        if obj.json_output:
            print(json.dumps({"ok": False, "error": err}))
        else:
            print_error(err)
        raise SystemExit(1)

    if obj.json_output:
        print(json.dumps({"ok": True, **data}))
    else:
        print_success(f"Updated {email}: {', '.join(data['updated'])}")


# ── delete ────────────────────────────────────────────────────────────────────

@prospects.command("delete")
@click.argument("email")
@click.option("--yes", is_flag=True, default=False, help="Skip confirmation.")
@click.pass_obj
def delete_prospect(obj, email, yes) -> None:
    """Delete a prospect (soft delete)."""
    _require_login(obj)
    if not yes:
        click.confirm(f"Delete prospect {email}?", abort=True)

    async def _do():
        from app.db.falkordb import init_graph_db, graph_db

        init_graph_db()
        existing = await graph_db.get_prospect_by_email(email)
        if not existing or not existing.get("p"):
            return None, "Prospect not found"
        await graph_db._ingest(
            content=f"Prospect {email} marked as deleted",
            name=f"Prospect Deleted: {email}",
            account_name=email.split("@")[1] if "@" in email else "champmail",
            source="prospect_deletion",
        )
        return {"email": email}, None

    data, err = obj.run(_do())
    if err:
        if obj.json_output:
            print(json.dumps({"ok": False, "error": err}))
        else:
            print_error(err)
        raise SystemExit(1)

    if obj.json_output:
        print(json.dumps({"ok": True, **data}))
    else:
        print_success(f"Deleted {email}.")


# ── bulk-import ───────────────────────────────────────────────────────────────

@prospects.command("bulk-import")
@click.option("--file", "-f", "filepath", required=True, type=click.Path(exists=True),
              help="CSV file with columns: email,first_name,last_name,title,company_domain,industry")
@click.pass_obj
def bulk_import(obj, filepath) -> None:
    """Bulk-import prospects from a CSV file."""
    _require_login(obj)

    rows = []
    with open(filepath, newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if row.get("email"):
                rows.append(row)

    if not rows:
        print_error("CSV has no rows with an email column.")
        raise SystemExit(1)

    print_info(f"Importing {len(rows)} prospects…")
    created = updated = failed = 0
    errors = []

    async def _do(batch):
        from app.db.falkordb import init_graph_db, graph_db

        init_graph_db()
        nonlocal created, updated, failed
        for row in batch:
            email = row["email"].strip()
            try:
                existing = await graph_db.get_prospect_by_email(email)
                if existing and existing.get("p"):
                    await graph_db.create_prospect(
                        email=email,
                        first_name=row.get("first_name", ""),
                        last_name=row.get("last_name", ""),
                        title=row.get("title", ""),
                    )
                    updated += 1
                else:
                    await graph_db.create_prospect(
                        email=email,
                        first_name=row.get("first_name", ""),
                        last_name=row.get("last_name", ""),
                        title=row.get("title", ""),
                    )
                    domain = row.get("company_domain", "")
                    if domain:
                        await graph_db.create_company(
                            name=domain, domain=domain, industry=row.get("industry", "")
                        )
                        await graph_db.link_prospect_to_company(
                            prospect_email=email, company_domain=domain, title=row.get("title", "")
                        )
                    created += 1
            except Exception as e:
                failed += 1
                errors.append(f"{email}: {e}")

    obj.run(_do(rows))

    result = {"created": created, "updated": updated, "failed": failed, "errors": errors[:10]}
    if obj.json_output:
        print(json.dumps({"ok": True, **result}))
    else:
        print_success(f"Import done — created={created}  updated={updated}  failed={failed}")
        for err in errors[:5]:
            print_error(f"  {err}")


# ── timeline ──────────────────────────────────────────────────────────────────

@prospects.command("timeline")
@click.argument("email")
@click.pass_obj
def timeline(obj, email) -> None:
    """Show activity timeline for a prospect."""
    _require_login(obj)

    async def _do():
        from app.db.falkordb import init_graph_db, graph_db

        init_graph_db()
        account = email.split("@")[1] if "@" in email else "champmail"
        return await graph_db.get_email_context(account_name=account, contact_email=email)

    data = obj.run(_do())

    if obj.json_output:
        print(json.dumps({"ok": True, "timeline": data}))
    else:
        print_section(f"Timeline: {email}")
        history = data.get("email_history", [])
        if not history:
            print_info("No email history found.")
        else:
            for item in history[:20]:
                print_kv(item.get("date", "")[:10], item.get("subject", item.get("content", ""))[:80])
