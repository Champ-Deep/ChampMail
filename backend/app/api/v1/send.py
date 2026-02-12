from fastapi import APIRouter, Depends, HTTPException, Header
from typing import Optional, List
from pydantic import BaseModel, EmailStr
from datetime import datetime
from app.services.mail_engine_client import mail_engine_client
from app.core.security import get_current_user


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
    current_user = Depends(get_current_user),
):
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
    current_user = Depends(get_current_user),
):
    try:
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
            for email in request.emails
        ]

        result = await mail_engine_client.send_batch(emails=emails, domain_id=request.domain_id)

        return BatchSendResponse(
            total=result.total,
            successful=result.successful,
            failed=result.failed,
            results=[
                SendEmailResponse(
                    message_id=r.message_id,
                    status=r.status,
                    domain_id=r.domain_id,
                    sent_at=r.sent_at,
                )
                for r in result.results
            ],
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send batch: {str(e)}")


@router.get("/send/status/{message_id}")
async def get_send_status(
    message_id: str,
    current_user = Depends(get_current_user),
):
    try:
        status = await mail_engine_client.get_send_status(message_id)
        return status
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Send status not found: {str(e)}")


@router.get("/send/stats", response_model=SendStatsResponse)
async def get_send_stats(
    domain_id: Optional[str] = None,
    current_user = Depends(get_current_user),
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