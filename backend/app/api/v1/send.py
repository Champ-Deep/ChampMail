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
    send_mode: Optional[str] = None  # "user_smtp" or None (default = mail engine)


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
    # ── User SMTP mode: send via user's own SMTP credentials ──
    if request.send_mode == "user_smtp":
        try:
            return await _send_via_user_smtp(request, current_user)
        except HTTPException:
            raise
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"User SMTP send failed: {type(e).__name__}: {e}")

    # ── Default: send via mail engine ──
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


async def _send_via_user_smtp(request: SendEmailRequest, current_user) -> SendEmailResponse:
    """Send a single email using the current user's SMTP settings."""
    import smtplib
    import ssl
    import uuid
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.utils import formataddr, formatdate, make_msgid

    from app.db.postgres import async_session_maker
    from app.services.email_settings_service import email_settings_service

    async with async_session_maker() as session:
        settings = await email_settings_service.get_settings(session, current_user.user_id)

    if not settings or not settings.smtp_host or not settings.smtp_username:
        raise HTTPException(status_code=400, detail="SMTP settings not configured. Go to Settings to set up SMTP.")

    if not settings.smtp_verified:
        raise HTTPException(status_code=400, detail="SMTP not verified. Test your connection in Settings first.")

    password = email_settings_service.get_decrypted_smtp_password(settings)
    if not password:
        raise HTTPException(status_code=400, detail="SMTP password not set.")

    from_email = request.from_address or settings.from_email or settings.smtp_username
    from_name = request.from_name or settings.from_name or "ChampMail"

    # Build MIME message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = request.subject
    msg["From"] = formataddr((from_name, from_email))
    msg["To"] = request.to
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=from_email.split("@")[-1] if "@" in from_email else "champmail.local")

    if request.reply_to:
        msg["Reply-To"] = request.reply_to

    if request.text_body:
        msg.attach(MIMEText(request.text_body, "plain", "utf-8"))
    msg.attach(MIMEText(request.html_body, "html", "utf-8"))

    # Send synchronously via executor
    import asyncio

    def _send_sync() -> str:
        ctx = ssl.create_default_context()
        if settings.smtp_use_tls:
            server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15)
            server.starttls(context=ctx)
        else:
            server = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=ctx, timeout=15)

        try:
            server.login(settings.smtp_username, password)
            server.send_message(msg)
            return msg["Message-ID"]
        finally:
            server.quit()

    try:
        loop = asyncio.get_event_loop()
        message_id = await loop.run_in_executor(None, _send_sync)
    except smtplib.SMTPAuthenticationError as e:
        raise HTTPException(status_code=502, detail=f"SMTP auth failed: {e}")
    except smtplib.SMTPException as e:
        raise HTTPException(status_code=502, detail=f"SMTP error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send: {e}")

    return SendEmailResponse(
        message_id=message_id or f"<{uuid.uuid4()}@champmail>",
        status="sent",
        domain_id="user_smtp",
        sent_at=datetime.utcnow(),
    )


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

    except Exception:
        # Mail engine not running — return empty stats instead of crashing
        return SendStatsResponse(
            domain_id=domain_id or "none",
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