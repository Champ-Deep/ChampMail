from fastapi import APIRouter, Depends, HTTPException, Header
from typing import Optional, List
from pydantic import BaseModel, EmailStr
from datetime import datetime
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import get_db_session
from app.core.security import require_auth, TokenData
from app.services.email_service import email_service


router = APIRouter()


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
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    result = await email_service.send_email(
        session=session,
        user_id=str(user.user_id),
        to_email=str(request.to),
        subject=request.subject,
        body=request.text_body or "",
        from_email=request.from_address,
        from_name=request.from_name,
        reply_to=request.reply_to,
        html_body=request.html_body,
    )

    if not result.get("success"):
        raise HTTPException(
            status_code=500,
            detail=result.get("error", "Failed to send email"),
        )

    details = result.get("details", {})
    message_id = details.get("message_id") or str(uuid.uuid4())

    return SendEmailResponse(
        message_id=message_id,
        status="sent",
        domain_id=request.domain_id or "",
        sent_at=datetime.utcnow(),
    )


@router.post("/send/batch", response_model=BatchSendResponse)
async def send_batch(
    request: BatchSendRequest,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    results = []
    successful = 0
    failed = 0

    for email_req in request.emails:
        result = await email_service.send_email(
            session=session,
            user_id=str(user.user_id),
            to_email=str(email_req.to),
            subject=email_req.subject,
            body=email_req.text_body or "",
            from_email=email_req.from_address,
            from_name=email_req.from_name,
            reply_to=email_req.reply_to,
            html_body=email_req.html_body,
        )

        if result.get("success"):
            details = result.get("details", {})
            message_id = details.get("message_id") or str(uuid.uuid4())
            results.append(SendEmailResponse(
                message_id=message_id,
                status="sent",
                domain_id=request.domain_id or email_req.domain_id or "",
                sent_at=datetime.utcnow(),
            ))
            successful += 1
        else:
            failed += 1

    return BatchSendResponse(
        total=len(request.emails),
        successful=successful,
        failed=failed,
        results=results,
    )


@router.get("/send/status/{message_id}")
async def get_send_status(
    message_id: str,
    user: TokenData = Depends(require_auth),
):
    return {"message_id": message_id, "status": "sent"}


@router.get("/send/stats", response_model=SendStatsResponse)
async def get_send_stats(
    domain_id: Optional[str] = None,
    user: TokenData = Depends(require_auth),
):
    return SendStatsResponse(
        domain_id=domain_id or "",
        today_sent=0,
        today_limit=1000,
        total_sent=0,
        total_opened=0,
        total_clicked=0,
        total_bounced=0,
        open_rate=0.0,
        click_rate=0.0,
        bounce_rate=0.0,
    )
