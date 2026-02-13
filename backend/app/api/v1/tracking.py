"""
Public email tracking endpoints.

These endpoints are unauthenticated because they are embedded in outgoing
emails as pixel URLs, click-through links, and unsubscribe links.

Security is handled via HMAC-signed tracking IDs - the signature parameter
ensures only legitimately generated tracking URLs can record events.

Routes:
    GET  /track/open/{tracking_id}     - 1x1 transparent pixel (records open)
    GET  /track/click/{tracking_id}    - Click redirect (records click, redirects)
    GET  /track/unsubscribe/{tracking_id} - Unsubscribe page
    POST /track/unsubscribe/{tracking_id} - Process unsubscribe
    POST /track/bounce                 - Bounce webhook from mail server
"""

from __future__ import annotations

import logging
from io import BytesIO

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, Response, HTMLResponse
from pydantic import BaseModel

from app.services.tracking_service import tracking_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/track", tags=["Tracking"])

# Transparent 1x1 GIF pixel (43 bytes)
TRACKING_PIXEL = (
    b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00"
    b"\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x00\x00\x00\x00"
    b"\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02"
    b"\x44\x01\x00\x3b"
)


@router.get("/open/{tracking_id}")
async def track_open(
    tracking_id: str,
    sig: str = Query(..., description="HMAC signature"),
):
    """Record an email open event and return a 1x1 transparent pixel.

    Embedded in emails as: <img src="{tracking_url}" width="1" height="1" />
    """
    # Verify signature
    if not tracking_service._verify_tracking_signature(tracking_id, sig):
        # Still return the pixel (don't break email rendering) but don't record
        logger.warning("Invalid tracking signature for open: %s", tracking_id)
        return Response(
            content=TRACKING_PIXEL,
            media_type="image/gif",
            headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
        )

    # Record the open event
    try:
        await tracking_service.record_open(tracking_id)
    except Exception as exc:
        logger.error("Error recording open for %s: %s", tracking_id, exc)

    return Response(
        content=TRACKING_PIXEL,
        media_type="image/gif",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


@router.get("/click/{tracking_id}")
async def track_click(
    tracking_id: str,
    sig: str = Query(..., description="HMAC signature"),
    url: str = Query(..., description="Original destination URL"),
):
    """Record a link click and redirect to the original destination URL.

    Links in emails are rewritten to pass through this endpoint.
    """
    # Verify signature
    if not tracking_service._verify_tracking_signature(tracking_id, sig):
        logger.warning("Invalid tracking signature for click: %s", tracking_id)
        # Still redirect so the user experience isn't broken
        return RedirectResponse(url=url, status_code=302)

    # Record the click event
    try:
        await tracking_service.record_click(tracking_id, url)
    except Exception as exc:
        logger.error("Error recording click for %s: %s", tracking_id, exc)

    return RedirectResponse(url=url, status_code=302)


@router.get("/unsubscribe/{tracking_id}", response_class=HTMLResponse)
async def unsubscribe_page(
    tracking_id: str,
    sig: str = Query(..., description="HMAC signature"),
):
    """Display an unsubscribe confirmation page."""
    if not tracking_service._verify_tracking_signature(tracking_id, sig):
        return HTMLResponse(
            content=_unsubscribe_html("Invalid or expired unsubscribe link.", error=True),
            status_code=400,
        )

    return HTMLResponse(
        content=_unsubscribe_html(tracking_id=tracking_id, sig=sig),
    )


@router.post("/unsubscribe/{tracking_id}")
async def process_unsubscribe(
    tracking_id: str,
    sig: str = Query(..., description="HMAC signature"),
):
    """Process an unsubscribe request."""
    if not tracking_service._verify_tracking_signature(tracking_id, sig):
        raise HTTPException(status_code=400, detail="Invalid or expired unsubscribe link")

    result = await tracking_service.handle_unsubscribe(tracking_id)

    if result.get("status") == "unknown_tracking_id":
        raise HTTPException(status_code=404, detail="Tracking ID not found")

    if result.get("status") == "prospect_not_found":
        raise HTTPException(status_code=404, detail="Prospect not found")

    return HTMLResponse(
        content=_unsubscribe_html(
            message="You have been successfully unsubscribed. You will no longer receive emails from this campaign.",
            success=True,
        ),
    )


class BounceWebhookPayload(BaseModel):
    """Bounce webhook payload from mail server."""
    email: str
    smtp_code: str = ""
    smtp_response: str = ""
    bounce_type: str = ""
    diagnostic_message: str = ""
    message_id: str = ""


@router.post("/bounce")
async def handle_bounce_webhook(payload: BounceWebhookPayload):
    """Process a bounce notification from the mail server.

    This endpoint should be configured as the bounce webhook URL
    in your mail server (BillionMail, Postal, etc.).
    """
    result = await tracking_service.process_bounce_webhook(payload.model_dump())

    return {
        "status": "processed",
        "email": payload.email,
        "bounce_type": result.get("classification", {}).get("bounce_type", "unknown"),
        "actions": result.get("actions_taken", []),
    }


def _unsubscribe_html(
    message: str = "",
    tracking_id: str = "",
    sig: str = "",
    error: bool = False,
    success: bool = False,
) -> str:
    """Generate a simple unsubscribe HTML page."""
    if error:
        body = f"""
        <div style="text-align:center;padding:60px 20px;">
            <h1 style="color:#ef4444;">Error</h1>
            <p style="color:#64748b;font-size:18px;">{message}</p>
        </div>
        """
    elif success:
        body = f"""
        <div style="text-align:center;padding:60px 20px;">
            <h1 style="color:#10b981;">Unsubscribed</h1>
            <p style="color:#64748b;font-size:18px;">{message}</p>
        </div>
        """
    else:
        body = f"""
        <div style="text-align:center;padding:60px 20px;">
            <h1 style="color:#1e293b;">Unsubscribe</h1>
            <p style="color:#64748b;font-size:18px;margin-bottom:30px;">
                Are you sure you want to unsubscribe from future emails?
            </p>
            <form method="POST" action="/api/v1/track/unsubscribe/{tracking_id}?sig={sig}">
                <button type="submit" style="
                    background-color:#ef4444;color:white;border:none;padding:12px 32px;
                    font-size:16px;border-radius:8px;cursor:pointer;
                ">
                    Yes, Unsubscribe Me
                </button>
            </form>
            <p style="color:#94a3b8;font-size:14px;margin-top:20px;">
                You can always re-subscribe by contacting our team.
            </p>
        </div>
        """

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Unsubscribe</title>
</head>
<body style="margin:0;padding:0;background-color:#f8fafc;font-family:-apple-system,BlinkMacSystemFont,sans-serif;">
    <div style="max-width:500px;margin:0 auto;">
        {body}
    </div>
</body>
</html>"""
