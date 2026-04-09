"""
Webhook endpoints for n8n and external service integration.
Handles events from BillionMail, n8n workflows, etc.
"""

from __future__ import annotations

import hmac
import hashlib
from datetime import datetime
from enum import Enum
from typing import Any, Optional, Dict

from fastapi import APIRouter, HTTPException, Header, Request
from pydantic import BaseModel

from app.core.config import settings
from app.db.champgraph import graph_db
from app.services.tracking_service import tracking_service

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


class EmailEventType(str, Enum):
    """Email event types from BillionMail/n8n."""
    SENT = "sent"
    DELIVERED = "delivered"
    OPENED = "opened"
    CLICKED = "clicked"
    REPLIED = "replied"
    BOUNCED = "bounced"
    UNSUBSCRIBED = "unsubscribed"
    COMPLAINED = "complained"


class EmailEvent(BaseModel):
    """Webhook payload for email events."""
    event_type: EmailEventType
    email_id: str | None = None
    prospect_email: str
    sequence_id: int | None = None
    step_number: int | None = None
    timestamp: datetime | None = None
    metadata: dict[str, Any] = {}


class LeadEvent(BaseModel):
    """Webhook payload for new leads from forms/integrations."""
    source: str
    email: str
    first_name: str = ""
    last_name: str = ""
    title: str = ""
    phone: str = ""
    company_name: str = ""
    company_domain: str = ""
    industry: str = ""
    inquiry_type: str = ""
    comments: str = ""
    metadata: dict[str, Any] = {}


class N8NWorkflowEvent(BaseModel):
    """Event from n8n workflow execution."""
    workflow_id: str
    execution_id: str
    event: str
    data: dict[str, Any] = {}


def verify_webhook_signature(
    payload: bytes,
    signature: str | None,
    secret: str,
) -> bool:
    if not secret:
        return True
    if not signature:
        return False
    expected = hmac.new(
        secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected)


@router.post("/email-events")
async def handle_email_event(
    request: Request,
    event: EmailEvent,
    x_webhook_signature: str | None = Header(default=None),
):
    """Handle email tracking events from BillionMail."""
    if settings.environment == "production":
        body = await request.body()
        if not verify_webhook_signature(body, x_webhook_signature, settings.webhook_secret):
            raise HTTPException(status_code=401, detail="Invalid webhook signature.")

    timestamp = event.timestamp or datetime.utcnow()
    account = event.prospect_email.split("@")[1] if "@" in event.prospect_email else "champmail"

    # Ingest the event into ChampGraph for relationship tracking
    event_content = (
        f"Email Event: {event.event_type.value}\n"
        f"Prospect: {event.prospect_email}\n"
        f"Timestamp: {timestamp.isoformat()}\n"
        f"Sequence ID: {event.sequence_id}\n"
        f"Step: {event.step_number}\n"
    )
    if event.metadata:
        for k, v in event.metadata.items():
            event_content += f"{k}: {v}\n"

    await graph_db._ingest(
        content=event_content,
        name=f"Email {event.event_type.value}: {event.prospect_email}",
        account_name=account,
        source=f"email_event_{event.event_type.value}",
    )

    # Process bounces through tracking service
    if event.event_type == EmailEventType.BOUNCED:
        try:
            await tracking_service.process_bounce_webhook({
                "email": event.prospect_email,
                "smtp_code": event.metadata.get("smtp_code", ""),
                "smtp_response": event.metadata.get("smtp_response", ""),
                "bounce_type": event.metadata.get("bounce_type", ""),
                "message_id": event.email_id or "",
            })
        except Exception:
            pass

    return {"status": "processed", "event_type": event.event_type}


@router.post("/leads")
async def handle_new_lead(
    lead: LeadEvent,
    x_webhook_signature: str | None = Header(default=None),
):
    """Handle new lead submission from forms/integrations."""
    # Create prospect in ChampGraph
    await graph_db.create_prospect(
        email=lead.email,
        first_name=lead.first_name,
        last_name=lead.last_name,
        title=lead.title,
        phone=lead.phone,
        inquiry_type=lead.inquiry_type,
        comments=lead.comments,
        source=lead.source,
    )

    # Create/link company if provided
    if lead.company_domain:
        await graph_db.create_company(
            name=lead.company_name or lead.company_domain,
            domain=lead.company_domain,
            industry=lead.industry,
        )
        await graph_db.link_prospect_to_company(
            prospect_email=lead.email,
            company_domain=lead.company_domain,
            title=lead.title,
        )

    return {
        "status": "created",
        "prospect_email": lead.email,
        "source": lead.source,
    }


@router.post("/n8n")
async def handle_n8n_event(
    event: N8NWorkflowEvent,
    x_n8n_signature: str | None = Header(default=None),
):
    """Handle workflow events from n8n."""
    if event.event == "completed":
        return {"status": "acknowledged", "workflow_id": event.workflow_id}
    elif event.event == "failed":
        return {
            "status": "acknowledged",
            "workflow_id": event.workflow_id,
            "error": event.data.get("error", "Unknown error"),
        }
    return {"status": "acknowledged"}


@router.post("/trigger/{workflow_name}")
async def trigger_n8n_workflow(
    workflow_name: str,
    request: Request,
):
    """Trigger an n8n workflow by name."""
    import httpx

    body = await request.json()
    webhook_url = f"{settings.n8n_webhook_url}/{workflow_name}"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                webhook_url,
                json=body,
                headers={"Content-Type": "application/json"},
                timeout=30.0,
            )
            return {
                "status": "triggered",
                "workflow": workflow_name,
                "response_status": response.status_code,
            }
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="n8n webhook timeout")
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Failed to reach n8n: {str(e)}")
