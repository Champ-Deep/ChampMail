"""Mailboxes. Response keys mirror Harbinger's MailboxStatus (email, status) plus health and accounting."""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_session, require_api_key
from app.api.v1.domains import StatusPatch, _today
from app.models.domain import Domain
from app.models.email_account import EmailAccount

router = APIRouter(prefix="/mailboxes", tags=["Mailboxes"], dependencies=[Depends(require_api_key)])


def serialize_mailbox(m: EmailAccount, d: Optional[Domain]) -> dict:
    status, reason = m.status, m.status_reason
    if status == "active" and d is not None and d.send_status != "active":
        status, reason = d.send_status, d.send_status_reason
    return {
        "id": str(m.id),
        "email": m.email,
        # A consumer reading only {email, status} must see a gated mailbox as such.
        "status": status if status != "active" else ("active" if m.is_active else "pending"),
        "status_reason": reason,
        "domain": d.domain_name if d else None,
        # Per-mailbox health is not collected yet (M2): null means unknown, not clean.
        "dnsbl_listed": d.blacklisted if d else None,
        "complaint_rate": None,
        "hard_bounce_rate": None,
        "sends_today": m.sent_today if m.sent_today_date == _today() else 0,
        "cap": m.daily_send_limit,
    }


@router.get("")
async def list_mailboxes(domain: Optional[str] = None, session: AsyncSession = Depends(get_session)) -> list[dict]:
    q = select(EmailAccount, Domain).outerjoin(Domain, EmailAccount.domain_id == Domain.id).order_by(EmailAccount.email)
    if domain:
        q = q.where(Domain.domain_name == domain.strip().lower())
    return [serialize_mailbox(m, d) for m, d in (await session.execute(q)).all()]


@router.patch("/{mailbox_id}")
async def patch_mailbox(mailbox_id: str, body: StatusPatch, session: AsyncSession = Depends(get_session)) -> dict:
    try:
        m = await session.get(EmailAccount, UUID(mailbox_id))
    except ValueError:
        m = None
    if m is None:
        raise HTTPException(404, "mailbox not found")
    if m.status == "retired" and body.status != "retired":
        raise HTTPException(409, "retired is terminal")
    m.status, m.status_reason = body.status, body.reason
    await session.commit()
    d = await session.get(Domain, m.domain_id) if m.domain_id else None
    return serialize_mailbox(m, d)
