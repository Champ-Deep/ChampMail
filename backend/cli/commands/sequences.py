"""
champmail sequences — Multi-step email sequence commands.

  sequences list   [--status]
  sequences get    SEQUENCE_ID
  sequences create --name NAME [--description] [--steps-file steps.json]
  sequences pause  SEQUENCE_ID
  sequences resume SEQUENCE_ID
  sequences enroll SEQUENCE_ID --emails email1,email2,...
  sequences analytics SEQUENCE_ID
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from cli.context import CliContext
from cli.repl_skin import print_error, print_info, print_kv, print_section, print_success, print_table
from cli.session import get_user_id, is_logged_in, load_session


def _require_login(obj):
    if not is_logged_in():
        print_error("Not logged in.  Run: champmail auth login")
        raise SystemExit(1)


@click.group()
def sequences() -> None:
    """Email sequence management."""


# ── list ──────────────────────────────────────────────────────────────────────

@sequences.command("list")
@click.option("--status", default=None, help="draft|active|paused|completed")
@click.option("--limit", default=50, show_default=True)
@click.pass_obj
def list_sequences(obj, status, limit) -> None:
    """List sequences."""
    _require_login(obj)

    async def _do():
        from app.db.postgres import init_db, get_db
        from app.services.sequence_service import sequence_service

        await init_db()
        async with get_db() as session:
            team_id = load_session().get("team_id") or None
            rows = await sequence_service.get_by_team(
                session, team_id=team_id or get_user_id(), status=status
            )
            return rows[:limit]

    rows = obj.run(_do())

    if obj.json_output:
        print(json.dumps({"ok": True, "sequences": rows}))
    else:
        print_table(
            ["ID", "Name", "Status", "Steps", "Enrolled", "Active"],
            [
                [
                    str(r.get("id", "")),
                    str(r.get("name", ""))[:30],
                    str(r.get("status", "")),
                    str(len(r.get("steps", []))),
                    str(r.get("enrolled_count", 0)),
                    str(r.get("active_count", 0)),
                ]
                for r in rows
            ],
        )


# ── get ───────────────────────────────────────────────────────────────────────

@sequences.command("get")
@click.argument("sequence_id")
@click.pass_obj
def get_sequence(obj, sequence_id) -> None:
    """Show sequence details."""
    _require_login(obj)

    async def _do():
        from app.db.postgres import init_db, get_db
        from app.services.sequence_service import sequence_service

        await init_db()
        async with get_db() as session:
            return await sequence_service.get_by_id(session, sequence_id)

    data = obj.run(_do())
    if not data:
        if obj.json_output:
            print(json.dumps({"ok": False, "error": "Sequence not found"}))
        else:
            print_error("Sequence not found.")
        raise SystemExit(1)

    if obj.json_output:
        print(json.dumps({"ok": True, "sequence": data}, default=str))
    else:
        print_section(f"Sequence: {data.get('name')}")
        print_kv("ID", str(data.get("id", "")))
        print_kv("Status", data.get("status", ""))
        print_kv("Steps", str(len(data.get("steps", []))))
        print_kv("Enrolled", str(data.get("enrolled_count", 0)))
        print_kv("Active", str(data.get("active_count", 0)))
        print_kv("Completed", str(data.get("completed_count", 0)))
        steps = data.get("steps", [])
        if steps:
            print_info("\nSteps:")
            for i, step in enumerate(steps, 1):
                s = step if isinstance(step, dict) else {}
                print_kv(f"  Step {i}", f"{s.get('subject_template','')[:50]}  [delay={s.get('delay_hours',24)}h]")


# ── create ────────────────────────────────────────────────────────────────────

@sequences.command("create")
@click.option("--name", required=True)
@click.option("--description", default="")
@click.option("--steps-file", "steps_file", default=None, type=click.Path(),
              help="JSON file with step definitions.")
@click.pass_obj
def create_sequence(obj, name, description, steps_file) -> None:
    """Create a new sequence.

    Steps JSON format example (steps.json):
    [
      {"name": "Initial Outreach", "subject": "Hi {{first_name}}", "body": "<p>Hello</p>", "delay_hours": 0},
      {"name": "Follow-up 1",      "subject": "Following up",      "body": "<p>Just checking</p>", "delay_hours": 72}
    ]
    """
    _require_login(obj)

    steps = []
    if steps_file:
        try:
            steps = json.loads(Path(steps_file).read_text())
        except Exception as e:
            print_error(f"Failed to read steps file: {e}")
            raise SystemExit(1)

    async def _do():
        from app.db.postgres import init_db, get_db
        from app.db.champgraph import init_graph_db, graph_db
        from app.services.sequence_service import sequence_service

        await init_db()
        init_graph_db()
        async with get_db() as session:
            team_id = load_session().get("team_id") or None
            seq = await sequence_service.create(
                session, name=name, team_id=team_id,
                created_by=get_user_id(), description=description,
            )
            for i, step in enumerate(steps):
                await sequence_service.add_step(
                    session,
                    sequence_id=seq["id"],
                    order=i + 1,
                    name=step.get("name", f"Step {i+1}"),
                    subject_template=step.get("subject", ""),
                    html_template=step.get("body", ""),
                    delay_hours=step.get("delay_hours", 24),
                )
            await session.commit()
            await graph_db.create_sequence(
                name=name, owner_id=get_user_id(), steps_count=len(steps)
            )
            return {"id": str(seq["id"]), "name": name, "steps": len(steps)}

    data = obj.run(_do())

    if obj.json_output:
        print(json.dumps({"ok": True, **data}))
    else:
        print_success(f"Sequence created: {data['name']}  id={data['id']}  steps={data['steps']}")


# ── pause / resume ────────────────────────────────────────────────────────────

@sequences.command("pause")
@click.argument("sequence_id")
@click.pass_obj
def pause_sequence(obj, sequence_id) -> None:
    """Pause a sequence."""
    _require_login(obj)

    async def _do():
        from app.db.postgres import init_db, get_db
        from app.services.sequence_service import sequence_service

        await init_db()
        async with get_db() as session:
            if not await sequence_service.get_by_id(session, sequence_id):
                return None, "Sequence not found"
            await sequence_service.pause(session, sequence_id)
            await session.commit()
            return {"sequence_id": sequence_id, "status": "paused"}, None

    data, err = obj.run(_do())
    if err:
        print_error(err)
        raise SystemExit(1)
    if obj.json_output:
        print(json.dumps({"ok": True, **data}))
    else:
        print_success(f"Sequence {sequence_id} paused.")


@sequences.command("resume")
@click.argument("sequence_id")
@click.pass_obj
def resume_sequence(obj, sequence_id) -> None:
    """Resume a paused sequence."""
    _require_login(obj)

    async def _do():
        from app.db.postgres import init_db, get_db
        from app.services.sequence_service import sequence_service

        await init_db()
        async with get_db() as session:
            if not await sequence_service.get_by_id(session, sequence_id):
                return None, "Sequence not found"
            await sequence_service.resume(session, sequence_id)
            await session.commit()
            return {"sequence_id": sequence_id, "status": "active"}, None

    data, err = obj.run(_do())
    if err:
        print_error(err)
        raise SystemExit(1)
    if obj.json_output:
        print(json.dumps({"ok": True, **data}))
    else:
        print_success(f"Sequence {sequence_id} resumed.")


# ── enroll ────────────────────────────────────────────────────────────────────

@sequences.command("enroll")
@click.argument("sequence_id")
@click.option("--emails", required=True, help="Comma-separated prospect emails.")
@click.pass_obj
def enroll(obj, sequence_id, emails) -> None:
    """Enroll prospects in a sequence by email."""
    _require_login(obj)
    email_list = [e.strip() for e in emails.split(",") if e.strip()]

    async def _do():
        from app.db.postgres import init_db, get_db
        from app.db.champgraph import init_graph_db, graph_db
        from app.services.sequence_service import sequence_service
        from app.models import Prospect, SequenceEnrollment
        from sqlalchemy import select

        await init_db()
        init_graph_db()
        enrolled = already = failed = 0
        errors = []

        async with get_db() as session:
            for email in email_list:
                try:
                    result = await session.execute(select(Prospect).where(Prospect.email == email.lower()))
                    prospect = result.scalar_one_or_none()
                    if not prospect:
                        failed += 1
                        errors.append(f"{email}: not found")
                        continue
                    existing = await session.execute(
                        select(SequenceEnrollment).where(
                            SequenceEnrollment.sequence_id == sequence_id,
                            SequenceEnrollment.prospect_id == str(prospect.id),
                            SequenceEnrollment.status.in_(["active", "paused"]),
                        )
                    )
                    if existing.scalar_one_or_none():
                        already += 1
                        continue
                    await sequence_service.enroll_prospect(session, sequence_id, str(prospect.id))
                    await graph_db.enroll_prospect_in_sequence(email, int(sequence_id) if sequence_id.isdigit() else 0)
                    enrolled += 1
                except Exception as e:
                    failed += 1
                    errors.append(f"{email}: {e}")
            await session.commit()
        return {"enrolled": enrolled, "already_enrolled": already, "failed": failed, "errors": errors[:10]}

    data = obj.run(_do())

    if obj.json_output:
        print(json.dumps({"ok": True, **data}))
    else:
        print_success(f"Enrolled={data['enrolled']}  already={data['already_enrolled']}  failed={data['failed']}")
        for err in data.get("errors", [])[:5]:
            print_error(f"  {err}")


# ── analytics ─────────────────────────────────────────────────────────────────

@sequences.command("analytics")
@click.argument("sequence_id")
@click.pass_obj
def analytics(obj, sequence_id) -> None:
    """Show sequence analytics."""
    _require_login(obj)

    async def _do():
        from app.db.postgres import init_db, get_db
        from app.services.sequence_service import sequence_service
        from app.models import SequenceEnrollment, SequenceStepExecution
        from sqlalchemy import select, func

        await init_db()
        async with get_db() as session:
            seq = await sequence_service.get_by_id(session, sequence_id)
            if not seq:
                return None, "Sequence not found"

            enr = await session.execute(
                select(SequenceEnrollment.status, func.count().label("count"))
                .where(SequenceEnrollment.sequence_id == sequence_id)
                .group_by(SequenceEnrollment.status)
            )
            enrollment_stats = {r[0]: r[1] for r in enr.fetchall()}

            step_stats = await session.execute(
                select(SequenceStepExecution.step_id, func.count().label("sent"))
                .join(SequenceEnrollment, SequenceStepExecution.enrollment_id == SequenceEnrollment.id)
                .where(
                    SequenceEnrollment.sequence_id == sequence_id,
                    SequenceStepExecution.status == "sent",
                )
                .group_by(SequenceStepExecution.step_id)
            )
            return {
                "sequence_id": sequence_id,
                "name": seq.get("name"),
                "enrollment_stats": enrollment_stats,
                "step_stats": [{"step_id": str(r[0]), "sent": r[1]} for r in step_stats.fetchall()],
            }, None

    data, err = obj.run(_do())
    if err:
        print_error(err)
        raise SystemExit(1)

    if obj.json_output:
        print(json.dumps({"ok": True, **data}))
    else:
        print_section(f"Analytics: {data['name']}")
        print_info("Enrollment breakdown:")
        for status, count in (data.get("enrollment_stats") or {}).items():
            print_kv(f"  {status}", str(count))
        print_info("\nEmails sent per step:")
        for step in data.get("step_stats") or []:
            print_kv(f"  step {step['step_id']}", str(step["sent"]))
