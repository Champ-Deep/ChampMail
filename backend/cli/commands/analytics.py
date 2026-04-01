"""
champmail analytics — Campaign analytics commands.

  analytics campaign CAMPAIGN_ID
  analytics tracking CAMPAIGN_ID
  analytics summary
"""

from __future__ import annotations

import json

import click

from cli.context import CliContext
from cli.repl_skin import print_error, print_info, print_kv, print_section, print_success, print_table
from cli.session import is_logged_in


def _require_login(obj):
    if not is_logged_in():
        print_error("Not logged in.  Run: champmail auth login")
        raise SystemExit(1)


@click.group()
def analytics() -> None:
    """Campaign analytics and tracking stats."""


@analytics.command("campaign")
@click.argument("campaign_id")
@click.pass_obj
def campaign_analytics(obj, campaign_id) -> None:
    """Show delivery and engagement stats for a campaign."""
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
        print_section(f"Campaign Analytics  [{campaign_id[:8]}…]")
        print_kv("Sent", str(data.get("sent", 0)))
        print_kv("Delivered", str(data.get("delivered", 0)))
        print_kv("Opened", str(data.get("opened", 0)))
        print_kv("Clicked", str(data.get("clicked", 0)))
        print_kv("Replied", str(data.get("replied", 0)))
        print_kv("Bounced", str(data.get("bounced", 0)))
        sent = data.get("sent", 0)
        if sent:
            print_kv("Open rate", f"{data.get('opened',0)/sent*100:.1f}%")
            print_kv("Click rate", f"{data.get('clicked',0)/sent*100:.1f}%")
            print_kv("Reply rate", f"{data.get('replied',0)/sent*100:.1f}%")


@analytics.command("tracking")
@click.argument("campaign_id")
@click.pass_obj
def tracking_analytics(obj, campaign_id) -> None:
    """Detailed tracking stats (real-time Redis + DB) for a campaign."""
    _require_login(obj)

    async def _do():
        from app.services.tracking_service import tracking_service

        return await tracking_service.get_campaign_tracking_stats(campaign_id)

    data = obj.run(_do())

    if obj.json_output:
        print(json.dumps({"ok": True, **data}, default=str))
    else:
        print_section(f"Tracking Stats  [{campaign_id[:8]}…]")
        for k, v in data.items():
            if not isinstance(v, dict):
                print_kv(k, str(v))
        # Nested dicts (opens/clicks)
        for k in ("opens", "clicks", "bounces"):
            sub = data.get(k, {})
            if isinstance(sub, dict) and sub:
                print_info(f"\n{k}:")
                for sk, sv in sub.items():
                    print_kv(f"  {sk}", str(sv))


@analytics.command("summary")
@click.option("--limit", default=10, show_default=True, help="Top N campaigns.")
@click.pass_obj
def summary(obj, limit) -> None:
    """Show a summary across all campaigns."""
    _require_login(obj)

    async def _do():
        from app.db.postgres import init_db, get_db
        from app.services.campaigns import campaign_service

        await init_db()
        async with get_db() as session:
            rows = await campaign_service.list_campaigns(session, limit=limit)
            result = []
            for c in rows:
                sent = c.sent_count or 0
                opened = c.opened_count or 0
                clicked = c.clicked_count or 0
                result.append({
                    "id": str(c.id)[:8] + "…",
                    "name": (c.name or "")[:25],
                    "status": c.status,
                    "sent": sent,
                    "open%": f"{opened/sent*100:.0f}" if sent else "0",
                    "click%": f"{clicked/sent*100:.0f}" if sent else "0",
                })
            return result

    rows = obj.run(_do())

    if obj.json_output:
        print(json.dumps({"ok": True, "summary": rows}))
    else:
        print_table(
            ["ID", "Name", "Status", "Sent", "Open%", "Click%"],
            [[r["id"], r["name"], r["status"], str(r["sent"]), r["open%"], r["click%"]] for r in rows],
        )
