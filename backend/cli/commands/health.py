"""
champmail health — System health check.

  health check
"""

from __future__ import annotations

import json

import click

from cli.context import CliContext
from cli.repl_skin import print_error, print_info, print_kv, print_section, print_success, print_warning


@click.group()
def health() -> None:
    """System health checks."""


@health.command("check")
@click.pass_obj
def check(obj: CliContext) -> None:
    """Check connectivity to PostgreSQL, Redis, and ChampGraph."""

    results = {}

    # PostgreSQL
    async def _pg():
        from app.db.postgres import init_db, get_db
        try:
            await init_db()
            async with get_db() as session:
                await session.execute(__import__("sqlalchemy").text("SELECT 1"))
            return "ok"
        except Exception as e:
            return f"error: {e}"

    results["postgres"] = obj.run(_pg())

    # Redis
    async def _redis():
        from app.db.redis import redis_client
        try:
            await redis_client.ping()
            return "ok"
        except Exception as e:
            return f"error: {e}"

    results["redis"] = obj.run(_redis())

    # ChampGraph
    async def _graph():
        from app.db.falkordb import init_graph_db, graph_db
        try:
            ok = init_graph_db()
            if not ok:
                return "unavailable"
            return "ok"
        except Exception as e:
            return f"error: {e}"

    results["champgraph"] = obj.run(_graph())

    overall = "healthy" if all(v == "ok" for v in results.values()) else "degraded"

    if obj.json_output:
        print(json.dumps({"ok": True, "status": overall, **results}))
    else:
        print_section("System Health")
        for svc, status in results.items():
            if status == "ok":
                print_success(f"{svc:<15} {status}")
            elif status == "unavailable":
                print_warning(f"{svc:<15} {status}")
            else:
                print_error(f"{svc:<15} {status}")
        print()
        if overall == "healthy":
            print_success("All systems operational.")
        else:
            print_warning("Some systems degraded — check logs.")
