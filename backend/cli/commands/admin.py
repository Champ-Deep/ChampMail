"""
champmail admin — Admin-only commands.

  admin users list
  admin users create   --email --password --name [--role]
  admin users get      USER_ID
  admin users delete   USER_ID

  admin prospects list         [--assigned-to USER_ID]
  admin prospects create       --email EMAIL [options]
  admin prospects assign       PROSPECT_EMAIL --user USER_ID
  admin prospects send-list    --user USER_ID --emails a@x.com,b@x.com  (or --file prospects.csv)
  admin prospects bulk-import  --file prospects.csv [--assign-to USER_ID]
"""

from __future__ import annotations

import csv
import json

import click

from cli.context import CliContext
from cli.repl_skin import (
    print_error, print_info, print_kv, print_section,
    print_success, print_table, print_warning,
)
from cli.session import get_role, get_user_id, is_logged_in


def _require_admin(obj):
    if not is_logged_in():
        print_error("Not logged in.  Run: champmail auth login")
        raise SystemExit(1)
    if get_role() not in ("admin",):
        print_error("Admin role required for this command.")
        raise SystemExit(1)


@click.group()
def admin() -> None:
    """Admin operations (requires admin role)."""


# ─────────────────────────────────────────────────────────────────────────────
# USERS
# ─────────────────────────────────────────────────────────────────────────────

@admin.group("users")
def users() -> None:
    """User management."""


@users.command("list")
@click.option("--limit", default=50, show_default=True)
@click.pass_obj
def list_users(obj, limit) -> None:
    """List all users."""
    _require_admin(obj)

    async def _do():
        from app.db.postgres import init_db, get_db
        from sqlalchemy import select
        from app.models.user import User

        await init_db()
        async with get_db() as session:
            result = await session.execute(select(User).limit(limit))
            rows = result.scalars().all()
            return [
                {
                    "id": str(r.id),
                    "email": r.email,
                    "name": r.full_name or "",
                    "role": r.role,
                    "is_active": r.is_active,
                    "created_at": r.created_at.isoformat()[:10] if getattr(r, "created_at", None) else "",
                }
                for r in rows
            ]

    data = obj.run(_do())

    if obj.json_output:
        print(json.dumps({"ok": True, "users": data}))
    else:
        print_table(
            ["ID", "Email", "Name", "Role", "Active", "Created"],
            [[d["id"][:8] + "…", d["email"], d["name"], d["role"],
              str(d["is_active"]), d["created_at"]] for d in data],
        )


@users.command("create")
@click.option("--email",    required=True, help="New user e-mail.")
@click.option("--password", required=True, help="New user password.")
@click.option("--name",     default="",   help="Full name.")
@click.option("--role",     default="user",
              type=click.Choice(["user", "admin", "team_admin", "data_team"]),
              help="Role (default: user).")
@click.pass_obj
def create_user(obj, email, password, name, role) -> None:
    """Create a new user login (admin only)."""
    _require_admin(obj)

    async def _do():
        from app.db.postgres import init_db, get_db
        from app.services.user_service import user_service

        await init_db()
        async with get_db() as session:
            if await user_service.email_exists(session, email):
                return None, f"User {email} already exists"
            user = await user_service.create(
                session, email=email, password=password, full_name=name, role=role
            )
            await session.commit()
            return {"id": str(user.id), "email": user.email, "role": user.role}, None

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
        print_success(f"User created: {data['email']}  role={data['role']}  id={data['id']}")


@users.command("get")
@click.argument("user_id")
@click.pass_obj
def get_user(obj, user_id) -> None:
    """Get user details."""
    _require_admin(obj)

    async def _do():
        from app.db.postgres import init_db, get_db
        from app.services.user_service import user_service

        await init_db()
        async with get_db() as session:
            u = await user_service.get_by_id(session, user_id)
            if not u:
                return None
            return {
                "id": str(u.id),
                "email": u.email,
                "full_name": u.full_name or "",
                "role": u.role,
                "is_active": u.is_active,
                "is_verified": u.is_verified,
                "team_id": str(u.team_id) if u.team_id else "",
            }

    data = obj.run(_do())
    if not data:
        print_error("User not found.")
        raise SystemExit(1)

    if obj.json_output:
        print(json.dumps({"ok": True, **data}))
    else:
        print_section(f"User: {data['email']}")
        for k, v in data.items():
            print_kv(k, str(v))


@users.command("delete")
@click.argument("user_id")
@click.option("--yes", is_flag=True, default=False)
@click.pass_obj
def delete_user(obj, user_id, yes) -> None:
    """Deactivate a user account."""
    _require_admin(obj)
    if not yes:
        click.confirm(f"Deactivate user {user_id}?", abort=True)

    async def _do():
        from app.db.postgres import init_db, get_db
        from sqlalchemy import update as sql_update
        from app.models.user import User

        await init_db()
        async with get_db() as session:
            await session.execute(
                sql_update(User).where(User.id == user_id).values(is_active=False)
            )
            await session.commit()

    obj.run(_do())

    if obj.json_output:
        print(json.dumps({"ok": True, "user_id": user_id}))
    else:
        print_success(f"User {user_id} deactivated.")


# ─────────────────────────────────────────────────────────────────────────────
# PROSPECTS (admin-managed)
# ─────────────────────────────────────────────────────────────────────────────

@admin.group("prospects")
def admin_prospects() -> None:
    """Prospect management — create, assign, and send lists to users."""


@admin_prospects.command("list")
@click.option("--assigned-to", "assigned_to", default=None,
              help="Filter by assigned user ID or email.")
@click.option("--unassigned",  is_flag=True, default=False,
              help="Show only prospects not yet assigned.")
@click.option("--limit", default=100, show_default=True)
@click.pass_obj
def list_admin_prospects(obj, assigned_to, unassigned, limit) -> None:
    """List all prospects (admin view)."""
    _require_admin(obj)

    async def _do():
        from app.db.postgres import init_db, get_db
        from app.services.prospect_service import prospect_service
        from sqlalchemy import select
        from app.models import Prospect

        await init_db()
        async with get_db() as session:
            # Resolve user email → id if needed
            target_user_id = None
            if assigned_to:
                if "@" in assigned_to:
                    from app.services.user_service import user_service
                    u = await user_service.get_by_email(session, assigned_to)
                    target_user_id = str(u.id) if u else None
                    if not target_user_id:
                        return [], f"User {assigned_to} not found"
                else:
                    target_user_id = assigned_to

            if target_user_id:
                rows = await prospect_service.get_assigned_to_user(
                    session, target_user_id, limit=limit
                )
            elif unassigned:
                result = await session.execute(
                    select(Prospect)
                    .where(Prospect.assigned_to_user_id == None)
                    .limit(limit)
                )
                rows = [prospect_service._prospect_to_dict(p)
                        for p in result.scalars().all()]
            else:
                rows = await prospect_service.list_all(session, limit=limit)
            return rows, None

    rows, err = obj.run(_do())
    if err:
        print_error(err)
        raise SystemExit(1)

    if obj.json_output:
        print(json.dumps({"ok": True, "prospects": rows, "total": len(rows)}))
    else:
        print_table(
            ["ID", "Email", "Name", "Company", "Assigned To"],
            [
                [
                    str(r.get("id", ""))[:8] + "…",
                    r.get("email", ""),
                    f"{r.get('first_name','') or ''} {r.get('last_name','') or ''}".strip(),
                    r.get("company_name", ""),
                    (r.get("assigned_to_user_id") or "—")[:8] + ("…" if r.get("assigned_to_user_id") else ""),
                ]
                for r in rows
            ],
        )


@admin_prospects.command("create")
@click.option("--email",          required=True,  help="Prospect email.")
@click.option("--first-name",     "first_name",   default="",  help="First name.")
@click.option("--last-name",      "last_name",    default="",  help="Last name.")
@click.option("--title",          default="",     help="Job title.")
@click.option("--phone",          default="",     help="Phone.")
@click.option("--company-name",   "company_name", default="",  help="Company name.")
@click.option("--company-domain", "company_domain", default="", help="Company domain.")
@click.option("--industry",       default="",     help="Industry.")
@click.option("--assign-to",      "assign_to",    default=None,
              help="Assign to user immediately (user ID or email).")
@click.pass_obj
def create_prospect(obj, email, first_name, last_name, title, phone,
                    company_name, company_domain, industry, assign_to) -> None:
    """Create a prospect (admin only). Optionally assign immediately."""
    _require_admin(obj)

    async def _do():
        from app.db.postgres import init_db, get_db
        from app.services.prospect_service import prospect_service
        from app.db.champgraph import init_graph_db, graph_db
        from cli.session import load_session

        await init_db()
        init_graph_db()

        async with get_db() as session:
            # Resolve assign_to user
            target_user_id = None
            if assign_to:
                if "@" in assign_to:
                    from app.services.user_service import user_service
                    u = await user_service.get_by_email(session, assign_to)
                    if not u:
                        return None, f"User {assign_to} not found"
                    target_user_id = str(u.id)
                else:
                    target_user_id = assign_to

            # Check duplicate
            existing = await prospect_service.get_by_email(session, email)
            if existing:
                return None, f"Prospect {email} already exists (id={existing['id'][:8]}…)"

            sess_data = load_session()
            admin_id  = get_user_id()
            team_id   = sess_data.get("team_id")

            kwargs = {}
            if target_user_id:
                from uuid import UUID
                kwargs["assigned_to_user_id"] = UUID(target_user_id)

            p = await prospect_service.create(
                session,
                email=email,
                team_id=team_id,
                first_name=first_name or None,
                last_name=last_name or None,
                company_name=company_name or None,
                created_by=admin_id,
                **kwargs,
            )
            await session.commit()

        # Also ingest into ChampGraph for research
        full_name = f"{first_name} {last_name}".strip() or email
        parts = [
            f"{full_name} is a prospect managed by admin in ChampMail.",
            f"Email: {email}",
        ]
        if title:          parts.append(f"Job title: {title}")
        if phone:          parts.append(f"Phone: {phone}")
        if company_name:   parts.append(f"Company: {company_name}")
        if company_domain: parts.append(f"Domain: {company_domain}")
        if industry:       parts.append(f"Industry: {industry}")

        name_key = f"{first_name}_{last_name}".strip("_").lower().replace(" ", "_")
        account  = name_key or (email.split("@")[1] if "@" in email else "champmail")

        await graph_db._ingest(
            content="\n".join(parts),
            name=f"Prospect: {full_name} ({email})",
            account_name=account,
            source="admin_prospect_create",
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

        return {"id": p["id"], "email": email, "assigned_to": target_user_id}, None

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
        if data.get("assigned_to"):
            print_info(f"Assigned to user: {data['assigned_to'][:8]}…")


@admin_prospects.command("assign")
@click.argument("prospect_email")
@click.option("--user", "user_ref", required=True,
              help="Target user ID or email.")
@click.pass_obj
def assign_prospect(obj, prospect_email, user_ref) -> None:
    """Assign a single prospect to a user."""
    _require_admin(obj)

    async def _do():
        from app.db.postgres import init_db, get_db
        from app.services.prospect_service import prospect_service

        await init_db()
        async with get_db() as session:
            # Resolve user ref
            if "@" in user_ref:
                from app.services.user_service import user_service
                u = await user_service.get_by_email(session, user_ref)
                if not u:
                    return None, f"User {user_ref} not found"
                target_user_id = str(u.id)
                target_email   = u.email
            else:
                target_user_id = user_ref
                target_email   = user_ref

            p = await prospect_service.get_by_email(session, prospect_email)
            if not p:
                return None, f"Prospect {prospect_email} not found"

            await prospect_service.assign_to_user(session, p["id"], target_user_id)
            return {"prospect": prospect_email, "user": target_email}, None

    result, err = obj.run(_do())
    if err:
        if obj.json_output:
            print(json.dumps({"ok": False, "error": err}))
        else:
            print_error(err)
        raise SystemExit(1)

    if obj.json_output:
        print(json.dumps({"ok": True, **result}))
    else:
        print_success(f"Assigned {result['prospect']} → {result['user']}")


@admin_prospects.command("send-list")
@click.option("--user",   "user_ref",  required=True,
              help="Target user ID or email.")
@click.option("--emails", "emails_csv", default=None,
              help="Comma-separated prospect emails to assign.")
@click.option("--file",   "filepath",  default=None, type=click.Path(exists=True),
              help="CSV file with an 'email' column (prospect emails to assign).")
@click.pass_obj
def send_prospect_list(obj, user_ref, emails_csv, filepath) -> None:
    """Assign a list of prospects to a user so they can run outreach on them.

    Examples:
      admin prospects send-list --user raj@acme.com --emails a@co.com,b@co.com
      admin prospects send-list --user raj@acme.com --file prospects.csv
    """
    _require_admin(obj)

    if not emails_csv and not filepath:
        print_error("Provide --emails or --file.")
        raise SystemExit(1)

    # Build email list
    prospect_emails: list[str] = []
    if emails_csv:
        prospect_emails += [e.strip() for e in emails_csv.split(",") if e.strip()]
    if filepath:
        with open(filepath, newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                row_lower = {k.strip().lower(): v for k, v in row.items() if k}
                em = row_lower.get("email", "").strip()
                if em and "@" in em:
                    prospect_emails.append(em.lower())

    if not prospect_emails:
        print_error("No valid prospect emails found.")
        raise SystemExit(1)

    async def _do():
        from app.db.postgres import init_db, get_db
        from app.services.prospect_service import prospect_service

        await init_db()
        async with get_db() as session:
            # Resolve user
            if "@" in user_ref:
                from app.services.user_service import user_service
                u = await user_service.get_by_email(session, user_ref)
                if not u:
                    return None, f"User {user_ref} not found"
                target_user_id = str(u.id)
                target_email   = u.email
            else:
                target_user_id = user_ref
                target_email   = user_ref

            assigned = []
            not_found = []
            for em in prospect_emails:
                p = await prospect_service.get_by_email(session, em)
                if not p:
                    not_found.append(em)
                    continue
                await prospect_service.assign_to_user(session, p["id"], target_user_id)
                assigned.append(em)

            return {
                "user": target_email,
                "assigned": assigned,
                "not_found": not_found,
                "total_assigned": len(assigned),
            }, None

    result, err = obj.run(_do())
    if err:
        if obj.json_output:
            print(json.dumps({"ok": False, "error": err}))
        else:
            print_error(err)
        raise SystemExit(1)

    if obj.json_output:
        print(json.dumps({"ok": True, **result}))
    else:
        print_success(
            f"Assigned {result['total_assigned']} prospects → {result['user']}"
        )
        if result["not_found"]:
            print_warning("Not found (create them first with `admin prospects create`):")
            for em in result["not_found"]:
                print_info(f"  {em}")


@admin_prospects.command("bulk-import")
@click.option("--file", "-f", "filepath", required=True, type=click.Path(exists=True),
              help="CSV: email,first_name,last_name,title,company_name,company_domain,industry")
@click.option("--assign-to", "assign_to", default=None,
              help="Assign all imported prospects to this user (ID or email).")
@click.pass_obj
def bulk_import_prospects(obj, filepath, assign_to) -> None:
    """Bulk-import prospects from CSV. Admin only. Optionally assign to a user."""
    _require_admin(obj)

    rows = []
    with open(filepath, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            row_clean = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
            if row_clean.get("email"):
                rows.append(row_clean)

    if not rows:
        print_error("CSV has no rows with an email column.")
        raise SystemExit(1)

    print_info(f"Importing {len(rows)} prospects…")
    created = skipped = failed = 0
    errors = []

    async def _do():
        from app.db.postgres import init_db, get_db
        from app.services.prospect_service import prospect_service
        from app.db.champgraph import init_graph_db, graph_db
        from cli.session import load_session
        from uuid import UUID

        await init_db()
        init_graph_db()
        sess_data = load_session()
        team_id   = sess_data.get("team_id")
        admin_id  = get_user_id()

        nonlocal created, skipped, failed

        async with get_db() as session:
            # Resolve assign_to once
            target_user_id = None
            if assign_to:
                if "@" in assign_to:
                    from app.services.user_service import user_service
                    u = await user_service.get_by_email(session, assign_to)
                    if not u:
                        return None, f"User {assign_to} not found"
                    target_user_id = str(u.id)
                else:
                    target_user_id = assign_to

            for row in rows:
                em = row["email"].strip().lower()
                try:
                    existing = await prospect_service.get_by_email(session, em)
                    if existing:
                        # If not yet assigned and we have a target, assign now
                        if target_user_id and not existing.get("assigned_to_user_id"):
                            await prospect_service.assign_to_user(
                                session, existing["id"], target_user_id
                            )
                        skipped += 1
                        continue

                    kwargs = {}
                    if target_user_id:
                        kwargs["assigned_to_user_id"] = UUID(target_user_id)

                    await prospect_service.create(
                        session,
                        email=em,
                        team_id=team_id,
                        first_name=row.get("first_name") or None,
                        last_name=row.get("last_name") or None,
                        company_name=row.get("company_name") or None,
                        created_by=admin_id,
                        **kwargs,
                    )
                    await session.commit()

                    # ChampGraph ingest
                    fn = row.get("first_name", "")
                    ln = row.get("last_name", "")
                    name_key = f"{fn}_{ln}".strip("_").lower().replace(" ", "_")
                    account  = name_key or (em.split("@")[1] if "@" in em else "champmail")
                    parts = [f"{(fn+' '+ln).strip() or em} is a prospect in ChampMail.", f"Email: {em}"]
                    if row.get("title"):         parts.append(f"Title: {row['title']}")
                    if row.get("company_name"):  parts.append(f"Company: {row['company_name']}")
                    if row.get("company_domain"):parts.append(f"Domain: {row['company_domain']}")
                    if row.get("industry"):      parts.append(f"Industry: {row['industry']}")
                    await graph_db._ingest(
                        content="\n".join(parts),
                        name=f"Prospect: {em}",
                        account_name=account,
                        source="admin_bulk_import",
                    )
                    created += 1

                except Exception as e:
                    failed += 1
                    errors.append(f"{em}: {e}")

        return {"created": created, "skipped": skipped, "failed": failed,
                "errors": errors[:10], "assigned_to": assign_to}, None

    result, err = obj.run(_do())
    if err:
        if obj.json_output:
            print(json.dumps({"ok": False, "error": err}))
        else:
            print_error(err)
        raise SystemExit(1)

    if obj.json_output:
        print(json.dumps({"ok": True, **result}))
    else:
        print_success(
            f"Import done — created={result['created']}  "
            f"skipped={result['skipped']}  failed={result['failed']}"
        )
        if result.get("assigned_to"):
            print_info(f"All new prospects assigned to: {result['assigned_to']}")
        for e in result["errors"][:5]:
            print_error(f"  {e}")
