"""
Three-Point Follow-up Sequence Service.

Defines and executes the built-in "3-Point Follow-up" sequence:
  Step 1 — Send initial outreach email immediately upon enrollment.
  Step 2 — After 24 h: check for reply.
            Replied  → send acknowledgement email
            No reply → send follow-up email
  Step 3 — No email; write final log entry and mark enrollment complete.

Every step writes a row to sequence_step_logs for future AI context.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Sequence,
    SequenceStep,
    SequenceEnrollment,
    Prospect,
)
from app.services.sequence_service import sequence_service

logger = logging.getLogger(__name__)

THREE_POINT_FOLLOWUP_NAME = "3-Point Follow-up"


# ---------------------------------------------------------------------------
# Sequence bootstrap
# ---------------------------------------------------------------------------

async def get_or_create_three_point_sequence(
    session: AsyncSession,
    team_id: str,
    created_by: str,
) -> str:
    """
    Idempotently ensure the '3-Point Follow-up' sequence exists for this team.
    Returns the sequence_id as a string.
    """
    result = await session.execute(
        select(Sequence).where(
            Sequence.name == THREE_POINT_FOLLOWUP_NAME,
            Sequence.team_id == team_id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return str(existing.id)

    seq_id = str(uuid4())
    sequence = Sequence(
        id=seq_id,
        name=THREE_POINT_FOLLOWUP_NAME,
        description=(
            "Built-in 3-step outreach template. "
            "Sends initial email, waits 1 day, then sends acknowledgement if replied "
            "or follow-up if not. Every step is logged to PostgreSQL."
        ),
        status="active",
        team_id=team_id,
        created_by=created_by,
        auto_pause_on_reply=True,
        reply_detection_enabled=True,
        default_delay_hours=24,
    )
    session.add(sequence)
    await session.flush()

    steps = [
        SequenceStep(
            id=str(uuid4()),
            sequence_id=seq_id,
            order=1,
            name="Initial Outreach",
            subject_template="{{personalized_subject}}",
            html_template="{{personalized_body}}",
            delay_hours=0,
            wait_for_reply=False,
            is_active=True,
        ),
        SequenceStep(
            id=str(uuid4()),
            sequence_id=seq_id,
            order=2,
            name="Follow-up or Acknowledgement",
            subject_template="Re: {{personalized_subject}}",
            html_template="{{followup_or_ack_body}}",
            delay_hours=24,
            wait_for_reply=True,
            is_active=True,
        ),
        SequenceStep(
            id=str(uuid4()),
            sequence_id=seq_id,
            order=3,
            name="Sequence Complete (Log Only)",
            subject_template="",
            html_template="",
            delay_hours=0,
            wait_for_reply=False,
            is_active=True,
        ),
    ]
    for step in steps:
        session.add(step)

    await session.commit()
    logger.info("Created 3-Point Follow-up sequence %s for team %s", seq_id, team_id)
    return seq_id


# ---------------------------------------------------------------------------
# Enrollment helper
# ---------------------------------------------------------------------------

async def enroll_prospect(
    session: AsyncSession,
    sequence_id: str,
    prospect_id: str,
    campaign_id: Optional[str] = None,
) -> str:
    """
    Enroll a prospect in the 3-Point Follow-up sequence.
    Returns the enrollment_id.
    """
    enrollment_id = str(uuid4())
    enrollment = SequenceEnrollment(
        id=enrollment_id,
        sequence_id=sequence_id,
        prospect_id=prospect_id,
        status="active",
        current_step_order=0,
        enrolled_at=datetime.utcnow(),
        next_step_at=datetime.utcnow(),  # step 1 fires immediately
    )
    session.add(enrollment)
    await session.commit()
    return enrollment_id


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------

class ThreePointFollowupExecutor:
    """
    Drives the 3-point follow-up logic for a single enrollment.

    Call execute_step(session, enrollment_id, step_order) from a
    background task, Celery beat, or cron worker.
    """

    async def execute_step(
        self,
        session: AsyncSession,
        enrollment_id: str,
        step_order: int,
        sender_user_id: Optional[str] = None,
    ) -> dict:
        """Execute a single step for an enrollment. Returns a status dict."""
        enrollment, prospect = await self._load(session, enrollment_id)
        if not enrollment or not prospect:
            return {"ok": False, "error": "enrollment or prospect not found"}

        if enrollment.status in ("completed", "stopped"):
            return {"ok": False, "error": f"enrollment already {enrollment.status}"}

        campaign_id = str(enrollment.sequence.campaign_id) if enrollment.sequence and enrollment.sequence.campaign_id else None

        if step_order == 1:
            result = await self._step1(session, enrollment, prospect, campaign_id, sender_user_id)
        elif step_order == 2:
            result = await self._step2(session, enrollment, prospect, campaign_id, sender_user_id)
        elif step_order == 3:
            result = await self._step3(session, enrollment, prospect, campaign_id)
        else:
            return {"ok": False, "error": f"unknown step_order {step_order}"}

        # Advance enrollment step counter
        await session.execute(
            update(SequenceEnrollment)
            .where(SequenceEnrollment.id == enrollment_id)
            .values(current_step_order=step_order)
        )
        await session.commit()
        return result

    # ------------------------------------------------------------------
    # Step implementations
    # ------------------------------------------------------------------

    async def _step1(self, session, enrollment, prospect, campaign_id, sender_user_id):
        """Send the initial outreach email."""
        subject = prospect.personalized_subject or f"Hi {prospect.first_name or prospect.email}"
        body = prospect.personalized_body or self._default_initial_body(prospect)

        message_id = await self._send(
            session=session,
            sender_user_id=sender_user_id,
            to_email=prospect.email,
            subject=subject,
            html_body=body,
        )

        await sequence_service.log_step(
            session=session,
            prospect_id=str(prospect.id),
            campaign_id=campaign_id,
            sequence_id=str(enrollment.sequence_id),
            enrollment_id=str(enrollment.id),
            sequence_step=1,
            action_taken="sent",
            reply_detected=False,
            raw_subject=subject,
            raw_body=body,
            email_content_summary=f"Initial outreach sent to {prospect.email}",
        )

        # Schedule step 2 in 24 h
        await session.execute(
            update(SequenceEnrollment)
            .where(SequenceEnrollment.id == str(enrollment.id))
            .values(next_step_at=datetime.utcnow() + timedelta(hours=24))
        )
        await session.commit()

        return {"ok": True, "step": 1, "action": "sent", "message_id": message_id}

    async def _step2(self, session, enrollment, prospect, campaign_id, sender_user_id):
        """Check for reply; send acknowledgement or follow-up."""
        has_replied = bool(enrollment.replied)

        if has_replied:
            action = "acknowledged"
            subject = f"Re: {prospect.personalized_subject or 'your inquiry'}"
            body = self._render_acknowledgement(prospect)
        else:
            action = "followed_up"
            subject = f"Quick follow-up — {prospect.first_name or prospect.email}"
            body = self._render_followup(prospect)

        message_id = await self._send(
            session=session,
            sender_user_id=sender_user_id,
            to_email=prospect.email,
            subject=subject,
            html_body=body,
        )

        await sequence_service.log_step(
            session=session,
            prospect_id=str(prospect.id),
            campaign_id=campaign_id,
            sequence_id=str(enrollment.sequence_id),
            enrollment_id=str(enrollment.id),
            sequence_step=2,
            action_taken=action,
            reply_detected=has_replied,
            raw_subject=subject,
            raw_body=body,
            email_content_summary=(
                f"Step 2 {'acknowledgement' if has_replied else 'follow-up'} "
                f"sent to {prospect.email}"
            ),
        )

        # Step 3 fires immediately (it's just a log step)
        await session.execute(
            update(SequenceEnrollment)
            .where(SequenceEnrollment.id == str(enrollment.id))
            .values(next_step_at=datetime.utcnow())
        )
        await session.commit()

        return {"ok": True, "step": 2, "action": action, "message_id": message_id}

    async def _step3(self, session, enrollment, prospect, campaign_id):
        """No email — write final log and mark enrollment complete."""
        await sequence_service.log_step(
            session=session,
            prospect_id=str(prospect.id),
            campaign_id=campaign_id,
            sequence_id=str(enrollment.sequence_id),
            enrollment_id=str(enrollment.id),
            sequence_step=3,
            action_taken="completed",
            reply_detected=bool(enrollment.replied),
            email_content_summary="Sequence completed. All 3 steps logged.",
        )

        await session.execute(
            update(SequenceEnrollment)
            .where(SequenceEnrollment.id == str(enrollment.id))
            .values(
                status="completed",
                completed_at=datetime.utcnow(),
                next_step_at=None,
            )
        )
        await session.commit()

        return {"ok": True, "step": 3, "action": "completed"}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _load(self, session, enrollment_id):
        result = await session.execute(
            select(SequenceEnrollment)
            .options(
                selectinload(SequenceEnrollment.prospect),
                selectinload(SequenceEnrollment.sequence),
            )
            .where(SequenceEnrollment.id == enrollment_id)
        )
        enrollment = result.scalar_one_or_none()
        if not enrollment:
            return None, None
        return enrollment, enrollment.prospect

    async def _send(
        self,
        session,
        sender_user_id: Optional[str],
        to_email: str,
        subject: str,
        html_body: str,
    ) -> Optional[str]:
        """Send an email; returns message_id or None on failure."""
        if not sender_user_id:
            logger.warning("No sender_user_id — skipping actual send for %s", to_email)
            return None
        try:
            from app.services.email_service import email_service
            result = await email_service.send_email(
                session=session,
                user_id=sender_user_id,
                to_email=to_email,
                subject=subject,
                html_body=html_body,
            )
            return result.get("message_id") if isinstance(result, dict) else None
        except Exception as exc:
            logger.error("Email send failed for %s: %s", to_email, exc)
            return None

    def _default_initial_body(self, prospect) -> str:
        name = prospect.first_name or prospect.full_name or "there"
        company = f" at {prospect.company_name}" if prospect.company_name else ""
        return (
            f"<p>Hi {name},</p>"
            f"<p>I came across your profile{company} and thought there might be a great fit "
            f"for what we're working on.</p>"
            f"<p>Would you be open to a quick chat?</p>"
        )

    def _render_acknowledgement(self, prospect) -> str:
        name = prospect.first_name or "there"
        return (
            f"<p>Hi {name},</p>"
            f"<p>Thanks so much for getting back to me! I really appreciate it.</p>"
            f"<p>Looking forward to connecting with you soon.</p>"
        )

    def _render_followup(self, prospect) -> str:
        name = prospect.first_name or "there"
        return (
            f"<p>Hi {name},</p>"
            f"<p>Just following up on my previous note — didn't want it to get lost.</p>"
            f"<p>Happy to share more details if this might be relevant to what you're working on. "
            f"Would a brief call make sense?</p>"
        )


three_point_executor = ThreePointFollowupExecutor()
