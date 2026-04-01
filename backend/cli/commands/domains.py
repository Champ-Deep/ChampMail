"""
champmail domains — Domain management commands.

  domains list
  domains get      DOMAIN_ID
  domains add      --domain example.com [--description TEXT]
  domains validate DOMAIN_ID
  domains delete   DOMAIN_ID
"""

from __future__ import annotations

import json

import click

from cli.context import CliContext
from cli.repl_skin import print_error, print_info, print_kv, print_section, print_success, print_table, print_warning
from cli.session import get_user_id, is_logged_in


def _require_login(obj):
    if not is_logged_in():
        print_error("Not logged in.  Run: champmail auth login")
        raise SystemExit(1)


@click.group()
def domains() -> None:
    """Domain management — add, validate, rotate."""


@domains.command("list")
@click.pass_obj
def list_domains(obj) -> None:
    """List configured domains."""
    _require_login(obj)

    async def _do():
        from app.db.postgres import init_db, get_db
        from app.models.domain import Domain
        from sqlalchemy import select

        await init_db()
        async with get_db() as session:
            result = await session.execute(select(Domain).limit(100))
            rows = result.scalars().all()
            return [
                {
                    "id": str(r.id),
                    "domain": r.domain_name,
                    "status": r.status,
                    "health_score": r.health_score or 0,
                    "warmup_day": r.warmup_day or 0,
                    "sent_count": r.sent_today or 0,
                }
                for r in rows
            ]

    data = obj.run(_do())

    if obj.json_output:
        print(json.dumps({"ok": True, "domains": data}, default=str))
    else:
        print_table(
            ["ID", "Domain", "Status", "Health", "Warmup Day", "Sent"],
            [
                [
                    str(d.get("id", ""))[:8] + "…",
                    d.get("domain", ""),
                    d.get("status", ""),
                    f"{d.get('health_score', 0):.0f}%",
                    str(d.get("warmup_day", 0)),
                    str(d.get("sent_count", 0)),
                ]
                for d in data
            ],
        )


@domains.command("get")
@click.argument("domain_id")
@click.pass_obj
def get_domain(obj, domain_id) -> None:
    """Show domain details and DNS records."""
    _require_login(obj)

    async def _do():
        from app.db.postgres import init_db, get_db
        from app.services.domain_service import domain_service

        await init_db()
        async with get_db() as session:
            return await domain_service.get_by_id(session, domain_id)

    data = obj.run(_do())
    if not data:
        print_error("Domain not found.")
        raise SystemExit(1)

    if obj.json_output:
        print(json.dumps({"ok": True, **data}, default=str))
    else:
        print_section(f"Domain: {data.get('domain')}")
        for k, v in data.items():
            print_kv(k, str(v))


@domains.command("add")
@click.option("--domain", "domain_name", required=True, help="Domain name (e.g. outreach.acme.com)")
@click.option("--description", default="", help="Optional description.")
@click.pass_obj
def add_domain(obj, domain_name, description) -> None:
    """Add a new sending domain."""
    _require_login(obj)

    async def _do():
        from app.db.postgres import init_db, get_db
        from app.services.domain_service import domain_service

        await init_db()
        async with get_db() as session:
            d = await domain_service.create(
                session,
                name=domain_name,
                team_id=None,
            )
            await session.commit()
            return d

    data = obj.run(_do())

    if obj.json_output:
        print(json.dumps({"ok": True, **data}, default=str))
    else:
        name = data.get('domain') or data.get('domain_name') or domain_name
        print_success(f"Domain added: {name}  id={data.get('id')}")
        print_info("Run  domains validate <id>  to verify DNS records.")


@domains.command("validate")
@click.argument("domain_id")
@click.pass_obj
def validate_domain(obj, domain_id) -> None:
    """Check DNS health for a domain."""
    _require_login(obj)

    async def _do():
        from app.db.postgres import init_db, get_db
        from app.services.domain_service import domain_service

        await init_db()
        async with get_db() as session:
            d = await domain_service.get_by_id(session, domain_id)
            if not d:
                return None, "Domain not found"
            # Recalculate reputation/health
            score = await domain_service.recalculate_reputation(session, domain_id)
            await session.commit()
            return {"domain": d.get("domain"), "health_score": score, "status": d.get("status")}, None

    data, err = obj.run(_do())
    if err:
        print_error(err)
        raise SystemExit(1)

    if obj.json_output:
        print(json.dumps({"ok": True, **data}))
    else:
        print_section("DNS Validation")
        print_kv("Domain", data["domain"])
        print_kv("Health Score", f"{data['health_score']:.1f}%")
        print_kv("Status", data["status"])


@domains.command("delete")
@click.argument("domain_id")
@click.option("--yes", is_flag=True, default=False)
@click.pass_obj
def delete_domain(obj, domain_id, yes) -> None:
    """Remove a domain."""
    _require_login(obj)
    if not yes:
        click.confirm(f"Delete domain {domain_id}?", abort=True)

    async def _do():
        from app.db.postgres import init_db, get_db
        from app.services.domain_service import domain_service

        await init_db()
        async with get_db() as session:
            ok = await domain_service.delete(session, domain_id)
            if not ok:
                return False
            await session.commit()
            return True

    ok = obj.run(_do())
    if not ok:
        print_error("Domain not found.")
        raise SystemExit(1)

    if obj.json_output:
        print(json.dumps({"ok": True, "domain_id": domain_id}))
    else:
        print_success(f"Domain {domain_id} deleted.")
