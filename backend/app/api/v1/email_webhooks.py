"""
Email webhook endpoints for n8n integration.

These endpoints allow n8n workflows to send/receive emails through the ChampMail app
using the user's configured SMTP/IMAP credentials.
"""

from __future__ import annotations

import os
import re
from typing import Optional, Any
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import get_db_session
from app.core.config import settings
from app.core.security import require_auth, TokenData
from app.models.user import User
from app.services.email_service import email_service
from app.services.workflow_service import workflow_service
from app.services.email_account_service import email_account_service

router = APIRouter()


# ============================================================================
# Request/Response Models
# ============================================================================

class SendEmailRequest(BaseModel):
    """Request to send an email."""
    to: str  # Can be email or "Name <email>"
    subject: str
    body: str
    from_email: Optional[str] = None
    from_name: Optional[str] = None
    reply_to: Optional[str] = None
    html_body: Optional[str] = None
    # Context from n8n workflow
    workflow_id: Optional[str] = None
    chat_id: Optional[str] = None
    user_name: Optional[str] = None


class SendEmailResponse(BaseModel):
    """Response from send email."""
    success: bool
    message: str
    details: Optional[dict] = None
    error: Optional[str] = None


class FetchEmailsRequest(BaseModel):
    """Request to fetch emails."""
    mailbox: str = "INBOX"
    limit: int = 20
    unseen_only: bool = False
    # Context from n8n workflow
    workflow_id: Optional[str] = None
    chat_id: Optional[str] = None
    user_name: Optional[str] = None


class FetchEmailsResponse(BaseModel):
    """Response from fetch emails."""
    success: bool
    emails: list[dict]
    count: int
    mailbox: str
    error: Optional[str] = None


# ============================================================================
# Internal Endpoints (Authenticated - called from app frontend)
# ============================================================================

@router.post("/send", response_model=SendEmailResponse)
async def send_email(
    request: SendEmailRequest,
    current_user: User = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Send an email using the authenticated user's SMTP settings.

    This endpoint is for internal app use (authenticated).
    """
    # Parse to_email - handle "Name <email>" format
    to_email = request.to
    if "<" in to_email:
        to_email = to_email.split("<")[1].strip(">")

    result = await email_service.send_email(
        session=session,
        user_id=str(current_user.id),
        to_email=to_email,
        subject=request.subject,
        body=request.body,
        from_email=request.from_email,
        from_name=request.from_name,
        reply_to=request.reply_to,
        html_body=request.html_body,
    )

    return SendEmailResponse(
        success=result.get("success", False),
        message=result.get("message", ""),
        details=result.get("details"),
        error=result.get("error"),
    )


@router.post("/fetch", response_model=FetchEmailsResponse)
async def fetch_emails(
    request: FetchEmailsRequest,
    current_user: User = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Fetch emails using the authenticated user's IMAP settings.

    This endpoint is for internal app use (authenticated).
    """
    result = await email_service.fetch_emails(
        session=session,
        user_id=str(current_user.id),
        mailbox=request.mailbox,
        limit=request.limit,
        unseen_only=request.unseen_only,
    )

    return FetchEmailsResponse(
        success=result.get("success", False),
        emails=result.get("emails", []),
        count=result.get("count", 0),
        mailbox=result.get("mailbox", "INBOX"),
        error=result.get("error"),
    )


# ============================================================================
# Webhook Endpoints (For n8n Integration)
# ============================================================================

@router.post("/webhook/send")
async def webhook_send_email(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    x_workflow_id: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
):
    """
    Webhook endpoint for n8n to send emails.

    n8n workflows call this instead of using their own SMTP node.
    The app uses the user's configured SMTP credentials.

    Authentication options:
    1. X-User-Id header: Direct user ID (for trusted internal calls)
    2. X-Api-Key header: API key for external integrations (future)
    3. X-Workflow-Id header: Workflow ID to look up owner
    """
    body = await request.json()

    # Determine user ID
    user_id = None

    if x_user_id:
        user_id = x_user_id
    elif x_workflow_id:
        # Look up workflow to get owner
        try:
            workflow = await workflow_service.get_workflow(session, UUID(x_workflow_id))
            if workflow and workflow.is_active:
                user_id = str(workflow.owner_id)
            else:
                return {
                    "success": False,
                    "error": "Workflow not found or not active",
                    "status": "WORKFLOW_INACTIVE"
                }
        except:
            pass

    if not user_id:
        # For demo/development: use the first admin user
        # In production, this should be secured with API keys
        from sqlalchemy import select
        from app.models.user import User
        result = await session.execute(
            select(User).where(User.role == "admin").limit(1)
        )
        admin_user = result.scalar_one_or_none()
        print(f"[DEBUG webhook] Looking for admin user, found: {admin_user}")
        if admin_user:
            user_id = str(admin_user.id)
            print(f"[DEBUG webhook] Using admin user_id: {user_id}")
        else:
            return {"success": False, "error": "No user configured", "status": "NO_USER"}

    # Parse email data from n8n format
    to_email = body.get("to") or body.get("toEmail") or body.get("to_email", "")
    if "<" in to_email:
        to_email = to_email.split("<")[1].strip(">")

    subject = body.get("subject", "No Subject")
    email_body = body.get("body") or body.get("emailBody") or body.get("text", "")
    html_body = body.get("html_body") or body.get("htmlBody") or body.get("html")
    from_email = body.get("from_email") or body.get("fromEmail") or body.get("from")
    from_name = body.get("from_name") or body.get("fromName")

    if not to_email:
        return {
            "success": False,
            "error": "No recipient email specified",
            "status": "NO_RECIPIENT"
        }

    # Send the email
    try:
        result = await email_service.send_email(
            session=session,
            user_id=user_id,
            to_email=to_email,
            subject=subject,
            body=email_body,
            from_email=from_email,
            from_name=from_name,
            html_body=html_body,
        )
        print(f"[DEBUG] Email send result: {result}")
    except Exception as e:
        print(f"[DEBUG] Email send exception: {e}")
        result = {"success": False, "error": str(e)}

    # Return n8n-compatible response
    return {
        "success": result.get("success", False),
        "message": result.get("message", ""),
        "error": result.get("error"),
        "status": "SUCCESS" if result.get("success") else "FAILED",
        "details": result.get("details", {}),
        "response": result.get("message", ""),  # For n8n output compatibility
        "chatId": body.get("chatId") or body.get("chat_id"),
        "userName": body.get("userName") or body.get("user_name"),
    }


@router.post("/webhook/fetch")
async def webhook_fetch_emails(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    x_workflow_id: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
):
    """
    Webhook endpoint for n8n to fetch emails.

    n8n workflows call this instead of using their own IMAP node.
    The app uses the user's configured IMAP credentials.
    """
    body = await request.json()

    # Determine user ID (same logic as send)
    user_id = None

    if x_user_id:
        user_id = x_user_id
    elif x_workflow_id:
        try:
            workflow = await workflow_service.get_workflow(session, UUID(x_workflow_id))
            if workflow and workflow.is_active:
                user_id = str(workflow.owner_id)
            else:
                return {
                    "success": False,
                    "error": "Workflow not found or not active",
                    "emails": []
                }
        except:
            pass

    if not user_id:
        from sqlalchemy import select
        from app.models.user import User
        result = await session.execute(
            select(User).where(User.role == "admin").limit(1)
        )
        admin_user = result.scalar_one_or_none()
        if admin_user:
            user_id = str(admin_user.id)
        else:
            return {"success": False, "error": "No user configured", "emails": []}

    # Parse request
    mailbox = body.get("mailbox", "INBOX")
    limit = body.get("limit", 20)
    unseen_only = body.get("unseen_only") or body.get("unseenOnly", False)

    # Fetch emails
    result = await email_service.fetch_emails(
        session=session,
        user_id=user_id,
        mailbox=mailbox,
        limit=limit,
        unseen_only=unseen_only,
    )

    # Return n8n-compatible response (matches IMAP node output format)
    emails = result.get("emails", [])

    return {
        "success": result.get("success", False),
        "emails": emails,
        "count": len(emails),
        "mailbox": mailbox,
        "error": result.get("error"),
        "chatId": body.get("chatId") or body.get("chat_id"),
        "userName": body.get("userName") or body.get("user_name"),
    }


@router.get("/webhook/status")
async def webhook_status(
    session: AsyncSession = Depends(get_db_session),
    x_workflow_id: Optional[str] = Header(None),
):
    """
    Check if email webhooks are properly configured and active.

    n8n can call this to verify the integration is working.
    """
    # Check if workflow is active
    workflow_active = False
    workflow_name = None

    if x_workflow_id:
        try:
            workflow = await workflow_service.get_workflow(session, UUID(x_workflow_id))
            if workflow:
                workflow_active = workflow.is_active
                workflow_name = workflow.name
        except:
            pass

    # Check if we have configured email settings
    from sqlalchemy import select
    from app.models.user import User
    from app.models.email_settings import EmailSettings

    result = await session.execute(
        select(User).where(User.role == "admin").limit(1)
    )
    admin_user = result.scalar_one_or_none()

    smtp_configured = False
    imap_configured = False

    if admin_user:
        settings = await email_settings_service.get_settings(session, str(admin_user.id))
        if settings:
            smtp_configured = bool(settings.smtp_host and settings.smtp_username and settings.smtp_password_encrypted)
            imap_configured = bool(settings.imap_host and settings.imap_username and settings.imap_password_encrypted)

    return {
        "status": "ready" if (smtp_configured or imap_configured) else "not_configured",
        "smtp_configured": smtp_configured,
        "imap_configured": imap_configured,
        "workflow_active": workflow_active,
        "workflow_name": workflow_name,
        "message": "Email webhooks are ready" if smtp_configured else "Please configure email settings first",
    }


# Import the settings service for status check
from app.services.email_settings_service import email_settings_service


# ============================================================================
# Email Assistant Chat Endpoint
# ============================================================================

class ChatRequest(BaseModel):
    """Request to chat with the email assistant."""
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    """Response from the email assistant."""
    success: bool
    response: str
    session_id: str
    error: Optional[str] = None
    # Draft email data (when n8n returns a drafted email)
    draft: Optional[dict] = None


class SendDraftRequest(BaseModel):
    """Request to send a drafted email."""
    to: str  # Recipient email (stored on frontend)
    subject: str  # From n8n draft
    body: str  # From n8n draft
    html_body: Optional[str] = None
    from_email: Optional[str] = None
    from_name: Optional[str] = None
    reply_to: Optional[str] = None


@router.post("/send-draft", response_model=SendEmailResponse)
async def send_draft_email(
    request: SendDraftRequest,
    current_user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Send a drafted email using the user's SMTP settings.

    This endpoint is called after n8n returns a draft via webhook response.
    The frontend combines the draft (subject, body) with the stored recipient (to).
    """
    # Parse to_email - handle "Name <email>" format
    to_email = request.to
    if "<" in to_email:
        to_email = to_email.split("<")[1].strip(">")

    if not to_email:
        return SendEmailResponse(
            success=False,
            message="",
            error="No recipient email specified",
        )

    result = await email_service.send_email(
        session=session,
        user_id=str(current_user.user_id),
        to_email=to_email,
        subject=request.subject,
        body=request.body,
        from_email=request.from_email,
        from_name=request.from_name,
        reply_to=request.reply_to,
        html_body=request.html_body,
    )

    return SendEmailResponse(
        success=result.get("success", False),
        message=result.get("message", ""),
        details=result.get("details"),
        error=result.get("error"),
    )


@router.post("/chat", response_model=ChatResponse)
async def chat_with_assistant(
    request: ChatRequest,
    current_user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Chat with the Email Assistant.

    Sends the user message to the n8n Head Bot workflow which:
    1. Classifies the intent (check emails, write email, reply, etc.)
    2. Executes the appropriate sub-workflow
    3. Returns the AI response (may include draft email data)

    When n8n returns a drafted email, the response includes a 'draft' object
    with subject and body. The frontend combines this with the recipient
    and calls /send-draft to actually send.
    """
    # Generate session ID if not provided
    session_id = request.session_id or f"chat_{current_user.user_id}_{int(__import__('time').time())}"

    # Get user's email account (prefer email_accounts, fallback to email_settings)
    email_account = await email_account_service.get_default_account(session, current_user.user_id)
    user_settings = await email_settings_service.get_settings(session, current_user.user_id)

    # Get from email/name for context
    from_email = None
    from_name = None

    if email_account:
        from_email = email_account.email
        from_name = email_account.from_name or email_account.name
    elif user_settings:
        from_email = user_settings.from_email or user_settings.smtp_username
        from_name = user_settings.from_name

    # Build the webhook URL
    webhook_url = settings.n8n_webhook_url.rstrip("/")
    if not webhook_url.endswith("/email_agent"):
        if "/webhook" not in webhook_url:
            webhook_url = f"{webhook_url}/webhook/email_agent"
        else:
            webhook_url = f"{webhook_url}/email_agent"

    # Build the base URL for webhook callbacks (use cloudflare tunnel URL in dev)
    base_url = os.environ.get("PUBLIC_API_URL", "http://localhost:8000")

    # Parse email-related data from the user message
    # This helps the AI agent extract structured data for email operations
    user_message = request.message

    # Try to extract email address from the message
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    found_emails = re.findall(email_pattern, user_message)
    to_email = found_emails[0] if found_emails else ""

    # Try to extract subject if mentioned (e.g., "subject: xyz" or "about xyz")
    subject = ""
    subject_match = re.search(r'(?:subject[:\s]+|about\s+)([^,\.]+)', user_message, re.IGNORECASE)
    if subject_match:
        subject = subject_match.group(1).strip()

    # The rest of the message can be used as body/key points
    body = user_message

    # Prepare payload for n8n Head Bot
    # n8n will call back to our webhook endpoints to send/fetch emails
    # The backend handles SMTP/IMAP using the user's configured credentials
    payload = {
        "userMessage": user_message,
        "message": user_message,
        "chatId": session_id,
        "sessionId": session_id,
        "userName": current_user.email.split("@")[0],
        "userEmail": current_user.email,
        "userId": current_user.user_id,
        # Email context for the AI
        "fromEmail": from_email,
        "fromName": from_name,
        # Pre-parsed email data (AI can use or override)
        "to": to_email,
        "toEmail": to_email,
        "subject": subject,
        "body": body,
        "tone": "professional",
        # Webhook callback URLs - n8n calls these to send/fetch emails
        # The backend handles SMTP/IMAP internally
        "webhookSendUrl": f"{base_url}{settings.api_v1_prefix}/webhook/send",
        "webhookFetchUrl": f"{base_url}{settings.api_v1_prefix}/webhook/fetch",
        "webhookUrl": webhook_url,
    }

    # Debug log the payload being sent to n8n
    print(f"[CHAT DEBUG] Sending to n8n webhook: {webhook_url}")
    print(f"[CHAT DEBUG] Parsed email data - to: {to_email}, subject: {subject}")
    print(f"[CHAT DEBUG] Full payload: {payload}")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                webhook_url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "X-User-Id": str(current_user.user_id),
                },
            )

            print(f"[CHAT DEBUG] n8n response status: {response.status_code}")
            print(f"[CHAT DEBUG] n8n response body: {response.text[:500]}")

            if response.status_code == 200:
                data = response.json()
                # Extract response from various possible fields
                ai_response = (
                    data.get("response") or
                    data.get("output") or
                    data.get("text") or
                    data.get("message") or
                    "I processed your request."
                )

                # Extract draft email data if n8n returned it
                # n8n should return: { subject, body/emailBody, response }
                draft_data = None
                draft_subject = data.get("subject")
                draft_body = data.get("emailBody") or data.get("body") or data.get("email_body")

                if draft_subject or draft_body:
                    draft_data = {
                        "subject": draft_subject or "",
                        "body": draft_body or "",
                        "html_body": data.get("htmlBody") or data.get("html_body"),
                    }
                    print(f"[CHAT DEBUG] Draft email extracted: subject='{draft_subject}'")

                return ChatResponse(
                    success=True,
                    response=ai_response,
                    session_id=session_id,
                    draft=draft_data,
                )
            else:
                return ChatResponse(
                    success=False,
                    response="",
                    session_id=session_id,
                    error=f"Workflow returned status {response.status_code}: {response.text[:200]}",
                )
    except httpx.TimeoutException:
        return ChatResponse(
            success=False,
            response="",
            session_id=session_id,
            error="Request timed out. The workflow might be taking too long.",
        )
    except httpx.ConnectError:
        return ChatResponse(
            success=False,
            response="",
            session_id=session_id,
            error=f"Could not connect to n8n workflow at {webhook_url}. Please check if n8n is running.",
        )
    except Exception as e:
        return ChatResponse(
            success=False,
            response="",
            session_id=session_id,
            error=str(e),
        )
