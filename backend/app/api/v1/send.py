from fastapi import APIRouter, Depends, HTTPException, Header
from typing import Optional, List
from pydantic import BaseModel, EmailStr
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.mail_engine_client import mail_engine_client
from app.services.champiq_emit import emit_email_event
from app.core.security import require_auth
from app.db.postgres import get_db_session
from app.models.suppression import Suppression


router = APIRouter()


async def _suppressed_emails(session: AsyncSession, emails: list[str]) -> set[str]:
    """Lowercased lookup of suppressed recipients (SUGGESTIONS 4.6)."""
    if not emails:
        return set()
    rows = await session.execute(
        select(Suppression.email).where(Suppression.email.in_([e.lower() for e in emails]))
    )
    return {r[0] for r in rows.all()}


class SendEmailRequest(BaseModel):
    to: EmailStr
    from_name: Optional[str] = None
    from_address: Optional[str] = None
    subject: str
    html_body: str
    text_body: Optional[str] = None
    reply_to: Optional[str] = None
    domain_id: Optional[str] = None
    track_opens: bool = True
    track_clicks: bool = True


class SendEmailResponse(BaseModel):
    message_id: str
    status: str
    domain_id: str
    sent_at: datetime


class BatchSendRequest(BaseModel):
    emails: List[SendEmailRequest]
    domain_id: Optional[str] = None


class BatchSendResponse(BaseModel):
    total: int
    successful: int
    failed: int
    results: List[SendEmailResponse]


class SendStatsResponse(BaseModel):
    domain_id: str
    today_sent: int
    today_limit: int
    total_sent: int
    total_opened: int
    total_clicked: int
    total_bounced: int
    open_rate: float
    click_rate: float
    bounce_rate: float


@router.post("/send", response_model=SendEmailResponse)
async def send_email(
    request: SendEmailRequest,
    x_api_key: Optional[str] = Header(None),
    current_user = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    # ! suppression is checked before EVERY touch, no exceptions (4.6)
    if str(request.to).lower() in await _suppressed_emails(session, [str(request.to)]):
        raise HTTPException(status_code=422, detail=f"Recipient {request.to} is suppressed")
    try:
        result = await mail_engine_client.send_email(
            recipient=request.to,
            recipient_name=request.from_name or "",
            subject=request.subject,
            html_body=request.html_body,
            text_body=request.text_body,
            from_address=request.from_address,
            reply_to=request.reply_to,
            domain_id=request.domain_id,
            track_opens=request.track_opens,
            track_clicks=request.track_clicks,
        )

        await emit_email_event(
            "email.sent",
            to_email=str(request.to),
            from_email=request.from_address or "",
            subject=request.subject,
            body=request.text_body or request.html_body,
            message_id=result.message_id,
            occurred_at=result.sent_at,
        )

        return SendEmailResponse(
            message_id=result.message_id,
            status=result.status,
            domain_id=result.domain_id,
            sent_at=result.sent_at,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")


@router.post("/send/batch", response_model=BatchSendResponse)
async def send_batch(
    request: BatchSendRequest,
    current_user = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    try:
        # ! suppressed recipients are filtered out BEFORE dispatch and reported,
        # ! never sent (SUGGESTIONS 4.6 — CAN-SPAM/GDPR line)
        suppressed = await _suppressed_emails(session, [str(e.to) for e in request.emails])
        allowed = [e for e in request.emails if str(e.to).lower() not in suppressed]
        blocked = [e for e in request.emails if str(e.to).lower() in suppressed]

        emails = [
            {
                "to": email.to,
                "to_name": email.from_name or "",
                "subject": email.subject,
                "html_body": email.html_body,
                "text_body": email.text_body,
                "track_opens": email.track_opens,
                "track_clicks": email.track_clicks,
            }
            for email in allowed
        ]

        blocked_results = [
            SendEmailResponse(
                message_id="",
                status="suppressed",
                domain_id="",
                sent_at=datetime.utcnow(),
            )
            for _ in blocked
        ]

        if not emails:
            return BatchSendResponse(
                total=len(request.emails),
                successful=0,
                failed=len(blocked),
                results=blocked_results,
            )

        result = await mail_engine_client.send_batch(emails=emails, domain_id=request.domain_id)

        for sent, r in zip(allowed, result.results):
            if r.status not in ("failed", "suppressed"):
                await emit_email_event(
                    "email.sent",
                    to_email=str(sent.to),
                    from_email=sent.from_address or "",
                    subject=sent.subject,
                    body=sent.text_body or sent.html_body,
                    message_id=r.message_id,
                    occurred_at=r.sent_at,
                )

        return BatchSendResponse(
            total=len(request.emails),
            successful=result.successful,
            failed=result.failed + len(blocked),
            results=[
                SendEmailResponse(
                    message_id=r.message_id,
                    status=r.status,
                    domain_id=r.domain_id,
                    sent_at=r.sent_at,
                )
                for r in result.results
            ] + blocked_results,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send batch: {str(e)}")


@router.get("/send/status/{message_id}")
async def get_send_status(
    message_id: str,
    current_user = Depends(require_auth),
):
    try:
        status = await mail_engine_client.get_send_status(message_id)
        return status
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Send status not found: {str(e)}")


@router.get("/send/stats", response_model=SendStatsResponse)
async def get_send_stats(
    domain_id: Optional[str] = None,
    current_user = Depends(require_auth),
):
    try:
        stats = await mail_engine_client.get_send_stats(domain_id)

        return SendStatsResponse(
            domain_id=stats.domain_id,
            today_sent=stats.today_sent,
            today_limit=stats.today_limit,
            total_sent=stats.total_sent,
            total_opened=stats.total_opened,
            total_clicked=stats.total_clicked,
            total_bounced=stats.total_bounced,
            open_rate=stats.open_rate,
            click_rate=stats.click_rate,
            bounce_rate=stats.bounce_rate,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")