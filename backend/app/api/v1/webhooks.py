"""
Webhook endpoints for n8n and external service integration.
Handles events from BillionMail, n8n workflows, etc.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional, Dict

from fastapi import APIRouter, HTTPException, Header, Request
from pydantic import BaseModel

from app.core.config import settings
from app.db.falkordb import graph_db

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
    source: str  # e.g., "lakeb2b_form", "apollo", "manual"
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
    event: str  # e.g., "started", "completed", "failed"
    data: dict[str, Any] = {}


def verify_webhook_signature(
    signature: str | None,
    expected_key: str,
) -> bool:
    """Verify webhook signature for security."""
    # Simple key comparison for now
    # TODO: Implement proper HMAC signature verification
    if not expected_key:
        return True  # No verification if no key configured
    return signature == expected_key


@router.post("/email-events")
async def handle_email_event(
    event: EmailEvent,
    x_webhook_signature: str | None = Header(default=None),
):
    """
    Handle email tracking events from BillionMail.

    Events:
    - sent: Email was sent
    - delivered: Email was delivered
    - opened: Recipient opened the email
    - clicked: Recipient clicked a link
    - replied: Recipient replied
    - bounced: Email bounced
    - unsubscribed: Recipient unsubscribed
    - complained: Recipient marked as spam
    """
    # Verify signature (optional based on config)
    # if not verify_webhook_signature(x_webhook_signature, settings.billionmail_webhook_secret):
    #     raise HTTPException(status_code=401, detail="Invalid webhook signature")

    timestamp = event.timestamp or datetime.utcnow()

    # Update email record in graph
    if event.event_type == EmailEventType.OPENED:
        query = """
            MATCH (p:Prospect {email: $email})-[:RECEIVED]->(e:Email)
            WHERE e.sequence_id = $sequence_id AND e.step_number = $step
            SET e.opened_at = $timestamp
            RETURN e
        """
        graph_db.query(query, {
            'email': event.prospect_email.lower(),
            'sequence_id': event.sequence_id,
            'step': event.step_number,
            'timestamp': timestamp.isoformat(),
        })

    elif event.event_type == EmailEventType.CLICKED:
        query = """
            MATCH (p:Prospect {email: $email})-[:RECEIVED]->(e:Email)
            WHERE e.sequence_id = $sequence_id AND e.step_number = $step
            SET e.clicked_at = $timestamp,
                e.click_url = $url
            RETURN e
        """
        graph_db.query(query, {
            'email': event.prospect_email.lower(),
            'sequence_id': event.sequence_id,
            'step': event.step_number,
            'timestamp': timestamp.isoformat(),
            'url': event.metadata.get('url', ''),
        })

    elif event.event_type == EmailEventType.REPLIED:
        # Mark email as replied
        query = """
            MATCH (p:Prospect {email: $email})-[:RECEIVED]->(e:Email)
            WHERE e.sequence_id = $sequence_id AND e.step_number = $step
            SET e.replied_at = $timestamp
            WITH p
            MATCH (p)-[enroll:ENROLLED_IN]->(s:Sequence)
            WHERE id(s) = $sequence_id
            SET enroll.status = 'replied'
            RETURN p
        """
        graph_db.query(query, {
            'email': event.prospect_email.lower(),
            'sequence_id': event.sequence_id,
            'step': event.step_number,
            'timestamp': timestamp.isoformat(),
        })

    elif event.event_type == EmailEventType.BOUNCED:
        # Update prospect and enrollment status
        query = """
            MATCH (p:Prospect {email: $email})
            SET p.email_status = 'bounced',
                p.bounce_type = $bounce_type
            WITH p
            MATCH (p)-[enroll:ENROLLED_IN]->(s:Sequence)
            SET enroll.status = 'bounced'
            RETURN p
        """
        graph_db.query(query, {
            'email': event.prospect_email.lower(),
            'bounce_type': event.metadata.get('bounce_type', 'unknown'),
        })

    elif event.event_type == EmailEventType.UNSUBSCRIBED:
        query = """
            MATCH (p:Prospect {email: $email})
            SET p.unsubscribed = true,
                p.unsubscribed_at = $timestamp
            WITH p
            MATCH (p)-[enroll:ENROLLED_IN]->(s:Sequence)
            SET enroll.status = 'unsubscribed'
            RETURN p
        """
        graph_db.query(query, {
            'email': event.prospect_email.lower(),
            'timestamp': timestamp.isoformat(),
        })

    return {"status": "processed", "event_type": event.event_type}


@router.post("/leads")
async def handle_new_lead(
    lead: LeadEvent,
    x_webhook_signature: str | None = Header(default=None),
):
    """
    Handle new lead submission from forms/integrations.

    This is the entry point for leads from:
    - LakeB2B contact forms
    - Apollo imports
    - Manual entry via n8n
    """
    # Create or update prospect
    existing = graph_db.get_prospect_by_email(lead.email)

    if existing and existing.get('p'):
        # Update existing prospect with new data
        updates = {
            'first_name': lead.first_name,
            'last_name': lead.last_name,
            'title': lead.title,
            'phone': lead.phone,
        }
        updates = {k: v for k, v in updates.items() if v}

        if updates:
            set_clause = ', '.join(f'p.{k} = ${k}' for k in updates.keys())
            query = f"""
                MATCH (p:Prospect {{email: $email}})
                SET {set_clause},
                    p.last_form_submission = datetime(),
                    p.inquiry_type = $inquiry_type,
                    p.comments = $comments
                RETURN p
            """
            updates['email'] = lead.email.lower()
            updates['inquiry_type'] = lead.inquiry_type
            updates['comments'] = lead.comments
            graph_db.query(query, updates)

        status = "updated"
    else:
        # Create new prospect
        graph_db.create_prospect(
            email=lead.email,
            first_name=lead.first_name,
            last_name=lead.last_name,
            title=lead.title,
            phone=lead.phone,
            inquiry_type=lead.inquiry_type,
            comments=lead.comments,
            source=lead.source,
        )
        status = "created"

    # Create/link company if provided
    if lead.company_domain:
        graph_db.create_company(
            name=lead.company_name or lead.company_domain,
            domain=lead.company_domain,
            industry=lead.industry,
        )
        graph_db.link_prospect_to_company(
            prospect_email=lead.email,
            company_domain=lead.company_domain,
            title=lead.title,
        )

    # Record intent signal if inquiry type suggests interest
    if lead.inquiry_type:
        signal_query = """
            MATCH (p:Prospect {email: $email})
            CREATE (s:IntentSignal {
                type: 'form_submission',
                description: $inquiry_type,
                source: $source,
                detected_at: datetime(),
                relevance_score: 0.7
            })
            CREATE (p)-[:HAS_SIGNAL]->(s)
            RETURN s
        """
        graph_db.query(signal_query, {
            'email': lead.email.lower(),
            'inquiry_type': lead.inquiry_type,
            'source': lead.source,
        })

    return {
        "status": status,
        "prospect_email": lead.email,
        "source": lead.source,
    }


@router.post("/n8n")
async def handle_n8n_event(
    event: N8NWorkflowEvent,
    x_n8n_signature: str | None = Header(default=None),
):
    """
    Handle workflow events from n8n.

    Used for:
    - Workflow execution notifications
    - Error alerts
    - Custom workflow triggers
    """
    # Log workflow event
    # TODO: Store in a proper logging/metrics system

    if event.event == "completed":
        # Workflow completed successfully
        return {"status": "acknowledged", "workflow_id": event.workflow_id}

    elif event.event == "failed":
        # Workflow failed - log error
        # TODO: Send alert via Slack/email
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
    """
    Trigger an n8n workflow by name.

    Forwards the request body to n8n webhook.
    """
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
