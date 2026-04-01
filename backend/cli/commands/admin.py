"""
champmail admin — Admin-only commands.

  admin users list
  admin users get    USER_ID
  admin users delete USER_ID
  admin prospects list  [--assigned-to USER_ID]
  admin prospects assign PROSPECT_EMAIL --user USER_ID
"""

from __future__ import annotations

import json

import click

from cli.context import CliContext
from cli.repl_skin import print_error, print_info, print_kv, print_section, print_success, print_table, print_warning
from cli.session import get_role, is_logged_in


def _require_admin(obj):
    if not is_logged_in():
        print_error("Not logged in.  Run: champmail auth login")
        raise SystemExit(1)
    if get_role() not in ("admin",):
        print_error("Admin role required.")
        raise SystemExit(1)


@click.group()
def admin() -> None:
    """Admin operations (requires admin role)."""


# ── users ─────────────────────────────────────────────────────────────────────

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
            ["ID", "Email", "Role", "Active", "Created"],
            [[d["id"][:8] + "…", d["email"], d["role"], str(d["is_active"]), d["created_at"]] for d in data],
        )


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
    """Deactivate / delete a user."""
    _require_admin(obj)
    if not yes:
        click.confirm(f"Delete user {user_id}?", abort=True)

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


# ── admin prospects ───────────────────────────────────────────────────────────

@admin.group("prospects")
def admin_prospects() -> None:
    """Admin prospect management."""


@admin_prospects.command("list")
@click.option("--assigned-to", "assigned_to", default=None, help="Filter by assigned user ID.")
@click.option("--limit", default=50, show_default=True)
@click.pass_obj
def list_admin_prospects(obj, assigned_to, limit) -> None:
    """List prospects (admin view from PostgreSQL)."""
    _require_admin(obj)

    async def _do():
        from app.db.postgres import init_db, get_db
        from app.services.prospect_service import prospect_service

        await init_db()
        async with get_db() as session:
            if assigned_to:
                rows = await prospect_service.get_assigned_to_user(session, assigned_to, limit=limit)
            else:
                rows = await prospect_service.list_all(session, limit=limit)
            return rows

    rows = obj.run(_do())

    if obj.json_output:
        print(json.dumps({"ok": True, "prospects": rows}))
    else:
        print_table(
            ["ID", "Email", "Name", "Company", "Assigned To"],
            [
                [
                    str(r.get("id", ""))[:8] + "…",
                    r.get("email", ""),
                    f"{r.get('first_name','')} {r.get('last_name','')}".strip(),
                    r.get("company", ""),
                    r.get("assigned_to", ""),
                ]
                for r in rows
            ],
        )


@admin_prospects.command("assign")
@click.argument("prospect_email")
@click.option("--user", "user_id", required=True, help="Target user ID.")
@click.pass_obj
def assign_prospect(obj, prospect_email, user_id) -> None:
    """Assign a prospect to a user."""
    _require_admin(obj)

    async def _do():
        from app.db.postgres import init_db, get_db
        from app.services.prospect_service import prospect_service

        await init_db()
        async with get_db() as session:
            result = await prospect_service.assign_to_user(session, prospect_email, user_id)
            await session.commit()
            return result

    result = obj.run(_do())

    if obj.json_output:
        print(json.dumps({"ok": True, "result": result}))
    else:
        print_success(f"Assigned {prospect_email} → user {user_id}")
