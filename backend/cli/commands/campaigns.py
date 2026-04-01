"""
champmail campaigns — Campaign management commands.

  campaigns list   [--status] [--limit] [--offset]
  campaigns create --name NAME [--description] [--from-name] [--from-address]
                   [--daily-limit] [--template-id] [--sequence-id]
  campaigns get    CAMPAIGN_ID
  campaigns stats  CAMPAIGN_ID
  campaigns send   CAMPAIGN_ID
  campaigns pause  CAMPAIGN_ID
  campaigns resume CAMPAIGN_ID
  campaigns delete CAMPAIGN_ID
  campaigns recipients add   CAMPAIGN_ID --prospect-ids id1,id2,...
  campaigns recipients list  CAMPAIGN_ID [--status]
"""

from __future__ import annotations

import json

import click

from cli.context import CliContext
from cli.repl_skin import print_error, print_info, print_kv, print_section, print_success, print_table, print_warning
from cli.session import is_logged_in, get_user_id, get_role


def _require_login(obj: CliContext) -> None:
    if not is_logged_in():
        print_error("Not logged in.  Run: champmail auth login")
        raise SystemExit(1)


# ─────────────────────────────────────────────────────────────────────────────

@click.group()
def campaigns() -> None:
    """Campaign lifecycle — create, send, pause, stats."""


# ── list ──────────────────────────────────────────────────────────────────────

@campaigns.command("list")
@click.option("--status", default=None, help="Filter: draft|scheduled|running|paused|completed|failed")
@click.option("--limit", default=50, show_default=True)
@click.option("--offset", default=0, show_default=True)
@click.option("--mine", is_flag=True, default=False, help="Only my campaigns.")
@click.pass_obj
def list_campaigns(obj: CliContext, status, limit, offset, mine) -> None:
    """List campaigns."""
    _require_login(obj)

    async def _do():
        from app.db.postgres import init_db, get_db
        from app.services.campaigns import campaign_service, CampaignStatus

        await init_db()
        async with get_db() as session:
            cs = CampaignStatus(status) if status else None
            owner = get_user_id() if mine else None
            rows = await campaign_service.list_campaigns(session, owner_id=owner, status=cs, limit=limit, offset=offset)
            return [
                {
                    "id": str(r.id),
                    "name": r.name,
                    "status": r.status,
                    "sent": r.sent_count or 0,
                    "daily_limit": r.daily_limit or 100,
                    "created_at": r.created_at.isoformat() if r.created_at else "",
                }
                for r in rows
            ]

    data = obj.run(_do())

    if obj.json_output:
        print(json.dumps({"ok": True, "campaigns": data, "total": len(data)}))
    else:
        print_table(
            ["ID", "Name", "Status", "Sent", "Daily Limit", "Created"],
            [[d["id"][:8] + "…", d["name"][:30], d["status"], str(d["sent"]), str(d["daily_limit"]), d["created_at"][:10]] for d in data],
        )


# ── create ────────────────────────────────────────────────────────────────────

@campaigns.command("create")
@click.option("--name", required=True, help="Campaign name.")
@click.option("--description", default=None)
@click.option("--from-name", "from_name", default=None)
@click.option("--from-address", "from_address", default=None)
@click.option("--daily-limit", "daily_limit", default=100, show_default=True)
@click.option("--template-id", "template_id", default=None)
@click.option("--sequence-id", "sequence_id", default=None)
@click.pass_obj
def create_campaign(obj, name, description, from_name, from_address, daily_limit, template_id, sequence_id) -> None:
    """Create a new campaign."""
    _require_login(obj)

    async def _do():
        from app.db.postgres import init_db, get_db
        from app.services.campaigns import campaign_service

        await init_db()
        async with get_db() as session:
            c = await campaign_service.create_campaign(
                session=session,
                name=name,
                owner_id=get_user_id(),
                description=description,
                from_name=from_name,
                from_address=from_address,
                daily_limit=daily_limit,
                template_id=template_id,
                sequence_id=sequence_id,
            )
            await session.commit()
            return {"id": str(c.id), "name": c.name, "status": c.status}

    data = obj.run(_do())

    if obj.json_output:
        print(json.dumps({"ok": True, **data}))
    else:
        print_success(f"Campaign created: {data['name']}  id={data['id']}")


# ── get ───────────────────────────────────────────────────────────────────────

@campaigns.command("get")
@click.argument("campaign_id")
@click.pass_obj
def get_campaign(obj, campaign_id) -> None:
    """Show campaign details."""
    _require_login(obj)

    async def _do():
        from app.db.postgres import init_db, get_db
        from app.services.campaigns import campaign_service

        await init_db()
        async with get_db() as session:
            c = await campaign_service.get_campaign(session, campaign_id)
            if not c:
                return None
            return {
                "id": str(c.id),
                "name": c.name,
                "description": c.description or "",
                "status": c.status,
                "from_name": c.from_name or "",
                "from_address": c.from_address or "",
                "daily_limit": c.daily_limit or 100,
                "total_prospects": c.total_prospects or 0,
                "sent_count": c.sent_count or 0,
                "opened_count": c.opened_count or 0,
                "clicked_count": c.clicked_count or 0,
                "bounced_count": c.bounced_count or 0,
                "created_at": c.created_at.isoformat() if c.created_at else "",
            }

    data = obj.run(_do())
    if not data:
        if obj.json_output:
            print(json.dumps({"ok": False, "error": "Campaign not found"}))
        else:
            print_error("Campaign not found.")
        raise SystemExit(1)

    if obj.json_output:
        print(json.dumps({"ok": True, **data}))
    else:
        print_section(f"Campaign: {data['name']}")
        for k, v in data.items():
            print_kv(k, str(v))


# ── stats ─────────────────────────────────────────────────────────────────────

@campaigns.command("stats")
@click.argument("campaign_id")
@click.pass_obj
def campaign_stats(obj, campaign_id) -> None:
    """Show campaign delivery/engagement stats."""
    _require_login(obj)

    async def _do():
        from app.db.postgres import init_db, get_db
        from app.services.campaigns import campaign_service

        await init_db()
        async with get_db() as session:
            return await campaign_service.get_campaign_stats(session, campaign_id)

    data = obj.run(_do())
    if not data:
        print_error("Campaign not found.")
        raise SystemExit(1)

    if obj.json_output:
        print(json.dumps({"ok": True, **data}))
    else:
        print_section("Campaign Stats")
        for k, v in data.items():
            print_kv(k, str(v))


# ── send ──────────────────────────────────────────────────────────────────────

@campaigns.command("send")
@click.argument("campaign_id")
@click.pass_obj
def send_campaign(obj, campaign_id) -> None:
    """Start sending a campaign."""
    _require_login(obj)

    async def _do():
        from app.db.postgres import init_db, get_db
        from app.services.campaigns import campaign_service, CampaignStatus

        await init_db()
        async with get_db() as session:
            c = await campaign_service.get_campaign(session, campaign_id)
            if not c:
                return None, "Campaign not found"
            if c.status == CampaignStatus.RUNNING.value:
                return None, "Campaign already running"
            if c.status == CampaignStatus.COMPLETED.value:
                return None, "Campaign already completed"
            await campaign_service.update_campaign_status(session, campaign_id, CampaignStatus.RUNNING)
            await session.commit()
            return {"campaign_id": campaign_id, "status": "running"}, None

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
        print_success(f"Campaign {campaign_id} is now running.")
        print_info("Sending is handled by the Celery worker. Use  campaigns stats <id>  to monitor.")


# ── pause ─────────────────────────────────────────────────────────────────────

@campaigns.command("pause")
@click.argument("campaign_id")
@click.pass_obj
def pause_campaign(obj, campaign_id) -> None:
    """Pause a running campaign."""
    _require_login(obj)

    async def _do():
        from app.db.postgres import init_db, get_db
        from app.services.campaigns import campaign_service, CampaignStatus

        await init_db()
        async with get_db() as session:
            c = await campaign_service.get_campaign(session, campaign_id)
            if not c:
                return None, "Campaign not found"
            if c.status != CampaignStatus.RUNNING.value:
                return None, f"Campaign is not running (status={c.status})"
            await campaign_service.update_campaign_status(session, campaign_id, CampaignStatus.PAUSED)
            await session.commit()
            return {"campaign_id": campaign_id, "status": "paused"}, None

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
        print_success(f"Campaign {campaign_id} paused.")


# ── resume ────────────────────────────────────────────────────────────────────

@campaigns.command("resume")
@click.argument("campaign_id")
@click.pass_obj
def resume_campaign(obj, campaign_id) -> None:
    """Resume a paused campaign."""
    _require_login(obj)

    async def _do():
        from app.db.postgres import init_db, get_db
        from app.services.campaigns import campaign_service, CampaignStatus

        await init_db()
        async with get_db() as session:
            c = await campaign_service.get_campaign(session, campaign_id)
            if not c:
                return None, "Campaign not found"
            if c.status != CampaignStatus.PAUSED.value:
                return None, f"Campaign is not paused (status={c.status})"
            await campaign_service.update_campaign_status(session, campaign_id, CampaignStatus.RUNNING)
            await session.commit()
            return {"campaign_id": campaign_id, "status": "running"}, None

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
        print_success(f"Campaign {campaign_id} resumed.")


# ── recipients ────────────────────────────────────────────────────────────────

@campaigns.group("recipients")
def recipients() -> None:
    """Manage campaign recipients."""


@recipients.command("add")
@click.argument("campaign_id")
@click.option("--prospect-ids", "prospect_ids", required=True,
              help="Comma-separated prospect IDs.")
@click.pass_obj
def add_recipients(obj, campaign_id, prospect_ids) -> None:
    """Add prospects as recipients of a campaign."""
    _require_login(obj)
    ids = [p.strip() for p in prospect_ids.split(",") if p.strip()]

    async def _do():
        from app.db.postgres import init_db, get_db
        from app.services.campaigns import campaign_service

        await init_db()
        async with get_db() as session:
            c = await campaign_service.get_campaign(session, campaign_id)
            if not c:
                return None, "Campaign not found"
            if c.status not in ("draft", "paused"):
                return None, f"Cannot add recipients when status={c.status}"
            added = await campaign_service.add_recipients(session, campaign_id, ids)
            await session.commit()
            return {"added": added, "requested": len(ids)}, None

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
        print_success(f"Added {data['added']} / {data['requested']} recipients.")


@recipients.command("list")
@click.argument("campaign_id")
@click.option("--status", default=None, help="Filter by status.")
@click.option("--limit", default=100, show_default=True)
@click.pass_obj
def list_recipients(obj, campaign_id, status, limit) -> None:
    """List campaign recipients."""
    _require_login(obj)

    async def _do():
        from app.db.postgres import init_db, get_db
        from app.services.campaigns import campaign_service

        await init_db()
        async with get_db() as session:
            return await campaign_service.get_recipients(session, campaign_id, status=status, limit=limit)

    rows = obj.run(_do())

    if obj.json_output:
        print(json.dumps({"ok": True, "recipients": rows}))
    else:
        print_table(
            ["Email", "Name", "Company", "Status", "Sent At"],
            [
                [
                    r.get("email", ""),
                    f"{r.get('first_name','')} {r.get('last_name','')}".strip(),
                    r.get("company", ""),
                    r.get("status", ""),
                    (r.get("sent_at") or "").split("T")[0],
                ]
                for r in rows
            ],
        )
