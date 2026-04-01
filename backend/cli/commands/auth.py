"""
champmail auth — Authentication commands.

  auth login   --email  --password
  auth logout
  auth whoami
  auth register  --email --password --name [--role]  (admin only)
"""

from __future__ import annotations

import json

import click

from cli.context import CliContext
from cli.repl_skin import print_error, print_info, print_kv, print_section, print_success
from cli.session import clear_auth, get_email, get_role, get_user_id, is_logged_in, set_auth


# ─────────────────────────────────────────────────────────────────────────────

@click.group()
def auth() -> None:
    """Authentication — login, logout, profile."""


# ── login ─────────────────────────────────────────────────────────────────────

@auth.command("login")
@click.option("--email", prompt=True, help="Account e-mail.")
@click.option("--password", prompt=True, hide_input=True, help="Password.")
@click.pass_obj
def login(obj: CliContext, email: str, password: str) -> None:
    """Authenticate and store session token."""

    async def _do():
        from app.db.postgres import init_db, get_db
        from app.services.user_service import user_service
        from app.core.security import create_access_token
        from app.core.config import settings
        from datetime import timedelta

        await init_db()
        async with get_db() as session:
            user = await user_service.authenticate(session, email, password)
            if not user:
                return None, "Invalid email or password"

            await user_service.update_last_login(session, user)
            await session.commit()

            token = create_access_token(
                data={
                    "user_id": str(user.id),
                    "email": user.email,
                    "role": user.role,
                    "team_id": str(user.team_id) if user.team_id else None,
                },
                expires_delta=timedelta(minutes=settings.jwt_access_token_expire_minutes),
            )
            return (token, str(user.id), user.email, user.role, str(user.team_id) if user.team_id else None), None

    result, err = obj.run(_do())
    if err:
        if obj.json_output:
            print(json.dumps({"ok": False, "error": err}))
        else:
            print_error(err)
        raise SystemExit(1)

    token, user_id, em, role, team_id = result
    set_auth(token, user_id, em, role)
    # Also persist team_id for FK-safe sequence/team operations
    from cli.session import load_session, save_session
    s = load_session(); s["team_id"] = team_id; save_session(s)

    if obj.json_output:
        print(json.dumps({"ok": True, "email": em, "role": role, "user_id": user_id}))
    else:
        print_success(f"Logged in as {em}  [{role}]")


# ── logout ────────────────────────────────────────────────────────────────────

@auth.command("logout")
@click.pass_obj
def logout(obj: CliContext) -> None:
    """Clear the local session token."""
    clear_auth()
    if obj.json_output:
        print(json.dumps({"ok": True}))
    else:
        print_success("Logged out.")


# ── whoami ────────────────────────────────────────────────────────────────────

@auth.command("whoami")
@click.pass_obj
def whoami(obj: CliContext) -> None:
    """Show current authenticated user."""
    if not is_logged_in():
        if obj.json_output:
            print(json.dumps({"ok": False, "error": "Not logged in"}))
        else:
            print_error("Not logged in.  Run: champmail auth login")
        raise SystemExit(1)

    em = get_email()
    uid = get_user_id()
    role = get_role()

    if obj.json_output:
        print(json.dumps({"ok": True, "email": em, "user_id": uid, "role": role}))
    else:
        print_section("Current User")
        print_kv("Email", em or "")
        print_kv("User ID", uid or "")
        print_kv("Role", role or "")


# ── register ──────────────────────────────────────────────────────────────────

@auth.command("register")
@click.option("--email", required=True, help="New user e-mail.")
@click.option("--password", required=True, help="New user password.")
@click.option("--name", default="", help="Full name.")
@click.option("--role", default="user", type=click.Choice(["user", "admin", "team_admin", "data_team"]), help="Role.")
@click.pass_obj
def register(obj: CliContext, email: str, password: str, name: str, role: str) -> None:
    """Create a new user account (admin only)."""
    if not is_logged_in():
        print_error("Must be logged in as admin.")
        raise SystemExit(1)

    async def _do():
        from app.db.postgres import init_db, get_db
        from app.services.user_service import user_service

        await init_db()
        async with get_db() as session:
            if await user_service.email_exists(session, email):
                return None, f"User {email} already exists"
            user = await user_service.create(session, email=email, password=password, full_name=name, role=role)
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
        print_success(f"Created user {data['email']}  [{data['role']}]  id={data['id']}")
