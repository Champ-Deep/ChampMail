"""
Sequence service for managing email outreach sequences.
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, and_, or_
from sqlalchemy.orm import selectinload
from uuid import uuid4
from datetime import datetime, timedelta

from app.models import Sequence, SequenceStep, SequenceEnrollment, SequenceStepExecution, Prospect


class SequenceService:
    """Service for managing email sequences."""

    async def get_by_id(self, session: AsyncSession, sequence_id: str) -> Optional[Dict[str, Any]]:
        """Get sequence by ID with steps."""
        result = await session.execute(
            select(Sequence)
            .options(selectinload(Sequence.steps))
            .where(Sequence.id == sequence_id)
        )
        sequence = result.scalar_one_or_none()
        if sequence:
            return self._sequence_to_dict(sequence)
        return None

    async def get_by_team(
        self, session: AsyncSession, team_id: str, status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all sequences for a team."""
        query = select(Sequence).where(Sequence.team_id == team_id)
        if status:
            query = query.where(Sequence.status == status)

        result = await session.execute(query)
        sequences = result.scalars().all()
        return [self._sequence_to_dict(s) for s in sequences]

    async def get_active_sequences(self, session: AsyncSession) -> List[Dict[str, Any]]:
        """Get all active sequences."""
        result = await session.execute(
            select(Sequence).where(Sequence.status == "active")
        )
        sequences = result.scalars().all()
        return [self._sequence_to_dict(s) for s in sequences]

    async def create(
        self,
        session: AsyncSession,
        name: str,
        team_id: str,
        created_by: Optional[str] = None,
        description: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Create a new sequence."""
        sequence = Sequence(
            id=uuid4(),
            name=name,
            description=description,
            team_id=team_id,
            created_by=created_by,
            **kwargs,
        )

        session.add(sequence)
        await session.commit()
        await session.refresh(sequence)

        return self._sequence_to_dict(sequence)

    async def add_step(
        self,
        session: AsyncSession,
        sequence_id: str,
        order: int,
        name: str,
        subject_template: str,
        html_template: str,
        delay_hours: int = 24,
        **kwargs,
    ) -> Dict[str, Any]:
        """Add a step to a sequence."""
        step = SequenceStep(
            id=uuid4(),
            sequence_id=sequence_id,
            order=order,
            name=name,
            subject_template=subject_template,
            html_template=html_template,
            delay_hours=delay_hours,
            **kwargs,
        )

        session.add(step)
        await session.commit()
        await session.refresh(step)

        return self._step_to_dict(step)

    async def activate(self, session: AsyncSession, sequence_id: str) -> bool:
        """Activate a sequence."""
        await session.execute(
            update(Sequence).where(Sequence.id == sequence_id).values(
                status="active",
                activated_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
        await session.commit()
        return True

    async def pause(self, session: AsyncSession, sequence_id: str, prospect_id: Optional[str] = None, reason: str = "manual") -> bool:
        """Pause a sequence or specific enrollment."""
        if prospect_id:
            await session.execute(
                update(SequenceEnrollment).where(
                    and_(
                        SequenceEnrollment.sequence_id == sequence_id,
                        SequenceEnrollment.prospect_id == prospect_id
                    )
                ).values(
                    status="paused",
                    paused_at=datetime.utcnow(),
                    pause_reason=reason,
                )
            )
        else:
            await session.execute(
                update(Sequence).where(Sequence.id == sequence_id).values(
                    status="paused",
                    updated_at=datetime.utcnow(),
                )
            )
            await session.execute(
                update(SequenceEnrollment).where(
                    SequenceEnrollment.sequence_id == sequence_id
                ).values(
                    status="paused",
                    paused_at=datetime.utcnow(),
                )
            )
        await session.commit()
        return True

    async def resume(self, session: AsyncSession, sequence_id: str, prospect_id: Optional[str] = None) -> bool:
        """Resume a paused sequence or enrollment."""
        if prospect_id:
            await session.execute(
                update(SequenceEnrollment).where(
                    and_(
                        SequenceEnrollment.sequence_id == sequence_id,
                        SequenceEnrollment.prospect_id == prospect_id
                    )
                ).values(
                    status="active",
                    paused_at=None,
                    pause_reason=None,
                )
            )
        else:
            await session.execute(
                update(Sequence).where(Sequence.id == sequence_id).values(
                    status="active",
                    updated_at=datetime.utcnow(),
                )
            )
            await session.execute(
                update(SequenceEnrollment).where(
                    and_(
                        SequenceEnrollment.sequence_id == sequence_id,
                        SequenceEnrollment.paused_at != None
                    )
                ).values(
                    status="active",
                    paused_at=None,
                    pause_reason=None,
                )
            )
        await session.commit()
        return True

    async def enroll_prospect(
        self,
        session: AsyncSession,
        sequence_id: str,
        prospect_id: str,
    ) -> Dict[str, Any]:
        """Enroll a prospect in a sequence."""
        enrollment = SequenceEnrollment(
            id=uuid4(),
            sequence_id=sequence_id,
            prospect_id=prospect_id,
            status="active",
            enrolled_at=datetime.utcnow(),
        )

        session.add(enrollment)
        await session.commit()
        await session.refresh(enrollment)

        return self._enrollment_to_dict(enrollment)

    async def get_pending_steps(self, session: AsyncSession) -> List[Dict[str, Any]]:
        """Get all pending sequence step executions."""
        now = datetime.utcnow()

        result = await session.execute(
            select(SequenceStepExecution)
            .options(
                selectinload(SequenceStepExecution.step).selectinload(SequenceStep.sequence),
                selectinload(SequenceStepExecution.enrollment).selectinload(SequenceEnrollment.prospect)
            )
            .where(
                and_(
                    SequenceStepExecution.status == "scheduled",
                    SequenceStepExecution.scheduled_for <= now,
                    SequenceEnrollment.status == "active"
                )
            )
            .limit(100)
        )

        executions = result.scalars().all()
        return [self._execution_to_dict(e) for e in executions]

    async def mark_step_sent(
        self,
        session: AsyncSession,
        execution_id: str,
        message_id: str,
    ) -> bool:
        """Mark a step as sent."""
        now = datetime.utcnow()
        await session.execute(
            update(SequenceStepExecution).where(
                SequenceStepExecution.id == execution_id
            ).values(
                status="sent",
                sent_at=now,
                message_id=message_id,
            )
        )

        result = await session.execute(
            select(SequenceStepExecution).where(SequenceExecution.id == execution_id)
        )
        execution = result.scalar_one_or_none()

        if execution:
            await session.execute(
                update(SequenceEnrollment).where(
                    SequenceEnrollment.id == execution.enrollment_id
                ).values(
                    emails_sent=SequenceEnrollment.emails_sent + 1,
                    last_sent_at=now,
                    next_step_at=None,
                )
            )

        await session.commit()
        return True

    async def mark_step_failed(
        self,
        session: AsyncSession,
        execution_id: str,
        error_message: str,
    ) -> bool:
        """Mark a step as failed."""
        await session.execute(
            update(SequenceStepExecution).where(
                SequenceStepExecution.id == execution_id
            ).values(
                status="failed",
                error_message=error_message,
                retry_count=SequenceStepExecution.retry_count + 1,
            )
        )
        await session.commit()
        return True

    async def schedule_next_step(
        self,
        session: AsyncSession,
        sequence_id: str,
        prospect_id: str,
        next_step_order: int,
    ) -> Optional[Dict[str, Any]]:
        """Schedule the next step in a sequence."""
        result = await session.execute(
            select(SequenceStep)
            .where(
                and_(
                    SequenceStep.sequence_id == sequence_id,
                    SequenceStep.order == next_step_order,
                    SequenceStep.is_active == True
                )
            )
        )
        next_step = result.scalar_one_or_none()

        if not next_step:
            await self._complete_enrollment(session, sequence_id, prospect_id)
            return None

        result = await session.execute(
            select(SequenceEnrollment).where(
                and_(
                    SequenceEnrollment.sequence_id == sequence_id,
                    SequenceEnrollment.prospect_id == prospect_id
                )
            )
        )
        enrollment = result.scalar_one_or_none()

        if not enrollment:
            return None

        delay_hours = next_step.delay_hours or 24
        scheduled_for = datetime.utcnow() + timedelta(hours=delay_hours)

        execution = SequenceStepExecution(
            id=uuid4(),
            enrollment_id=enrollment.id,
            step_id=next_step.id,
            status="scheduled",
            scheduled_for=scheduled_for,
        )

        session.add(execution)
        await session.commit()
        await session.refresh(execution)

        await session.execute(
            update(SequenceEnrollment).where(
                SequenceEnrollment.id == enrollment.id
            ).values(
                current_step_order=next_step_order,
                next_step_at=scheduled_for,
            )
        )
        await session.commit()

        return self._execution_to_dict(execution)

    async def _complete_enrollment(
        self,
        session: AsyncSession,
        sequence_id: str,
        prospect_id: str,
    ) -> bool:
        """Mark an enrollment as completed."""
        await session.execute(
            update(SequenceEnrollment).where(
                and_(
                    SequenceEnrollment.sequence_id == sequence_id,
                    SequenceEnrollment.prospect_id == prospect_id
                )
            ).values(
                status="completed",
                completed_at=datetime.utcnow(),
            )
        )
        await session.commit()
        return True

    async def get_enrolled_prospect_ids(
        self,
        session: AsyncSession,
        sequence_id: str,
    ) -> List[str]:
        """Get all prospect IDs enrolled in a sequence."""
        result = await session.execute(
            select(SequenceEnrollment.prospect_id).where(
                SequenceEnrollment.sequence_id == sequence_id
            )
        )
        return [str(row[0]) for row in result.fetchall()]

    def _sequence_to_dict(self, sequence: Sequence) -> Dict[str, Any]:
        return {
            "id": str(sequence.id),
            "name": sequence.name,
            "description": sequence.description,
            "status": sequence.status,
            "from_name": sequence.from_name,
            "from_address": sequence.from_address,
            "reply_to": sequence.reply_to,
            "default_delay_hours": sequence.default_delay_hours,
            "daily_limit": sequence.daily_limit,
            "auto_pause_on_reply": sequence.auto_pause_on_reply,
            "team_id": str(sequence.team_id) if sequence.team_id else None,
            "created_at": sequence.created_at.isoformat() if sequence.created_at else None,
            "updated_at": sequence.updated_at.isoformat() if sequence.updated_at else None,
            "activated_at": sequence.activated_at.isoformat() if sequence.activated_at else None,
            "steps": [self._step_to_dict(s) for s in (sequence.steps or [])],
        }

    def _step_to_dict(self, step: SequenceStep) -> Dict[str, Any]:
        return {
            "id": str(step.id),
            "sequence_id": str(step.sequence_id),
            "order": step.order,
            "name": step.name,
            "subject_template": step.subject_template,
            "html_template": step.html_template,
            "delay_hours": step.delay_hours,
            "is_active": step.is_active,
            "created_at": step.created_at.isoformat() if step.created_at else None,
        }

    def _enrollment_to_dict(self, enrollment: SequenceEnrollment) -> Dict[str, Any]:
        return {
            "id": str(enrollment.id),
            "sequence_id": str(enrollment.sequence_id),
            "prospect_id": str(enrollment.prospect_id),
            "status": enrollment.status,
            "current_step_order": enrollment.current_step_order,
            "enrolled_at": enrollment.enrolled_at.isoformat() if enrollment.enrolled_at else None,
        }

    def _execution_to_dict(self, execution: SequenceStepExecution) -> Dict[str, Any]:
        step = execution.step
        sequence = step.sequence if step else None
        enrollment = execution.enrollment
        prospect = enrollment.prospect if enrollment else None

        return {
            "id": str(execution.id),
            "enrollment_id": str(execution.enrollment_id),
            "step_id": str(execution.step_id),
            "sequence_id": str(sequence.id) if sequence else None,
            "sequence_name": sequence.name if sequence else None,
            "prospect_id": str(prospect.id) if prospect else None,
            "prospect_email": prospect.email if prospect else None,
            "prospect_name": f"{prospect.first_name} {prospect.last_name}" if prospect else None,
            "team_id": str(sequence.team_id) if sequence else None,
            "step_order": step.order if step else None,
            "subject": execution.subject or step.subject_template if step else None,
            "body": execution.html_body or step.html_template if step else None,
            "scheduled_for": execution.scheduled_for.isoformat() if execution.scheduled_for else None,
        }


sequence_service = SequenceService()