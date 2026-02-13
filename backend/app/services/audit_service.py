"""
Audit logging service for tracking sensitive operations.
Records all significant actions for security and compliance.
"""

import uuid
from typing import Dict, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Request

from app.core.security import TokenData


class AuditLog:
    """
    Simple audit log model for database insertion.
    Maps to audit_logs table created in migration 005.
    """

    def __init__(
        self,
        user_id: Optional[str],
        team_id: Optional[str],
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        resource_name: Optional[str] = None,
        user_email: Optional[str] = None,
        user_role: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_method: Optional[str] = None,
        request_path: Optional[str] = None,
        details: Optional[Dict] = None,
        changes: Optional[Dict] = None,
        status: str = "success",
        error_message: Optional[str] = None
    ):
        self.id = str(uuid.uuid4())
        self.user_id = user_id
        self.team_id = team_id
        self.user_email = user_email
        self.user_role = user_role
        self.action = action
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.resource_name = resource_name
        self.ip_address = ip_address
        self.user_agent = user_agent
        self.request_method = request_method
        self.request_path = request_path
        self.details = details or {}
        self.changes = changes or {}
        self.status = status
        self.error_message = error_message
        self.created_at = datetime.utcnow()


class AuditService:
    """Service for creating and querying audit logs."""

    # Common action types
    ACTION_CREATE = "create"
    ACTION_UPDATE = "update"
    ACTION_DELETE = "delete"
    ACTION_UPLOAD = "upload"
    ACTION_DOWNLOAD = "download"
    ACTION_EXPORT = "export"
    ACTION_IMPORT = "import"
    ACTION_LOGIN = "login"
    ACTION_LOGOUT = "logout"
    ACTION_ACCESS = "access"
    ACTION_APPROVE = "approve"
    ACTION_REJECT = "reject"

    # Common resource types
    RESOURCE_PROSPECT_LIST = "prospect_list"
    RESOURCE_CAMPAIGN = "campaign"
    RESOURCE_USER = "user"
    RESOURCE_TEAM = "team"
    RESOURCE_DOMAIN = "domain"
    RESOURCE_TEMPLATE = "template"
    RESOURCE_SEQUENCE = "sequence"
    RESOURCE_EMAIL = "email"

    @staticmethod
    def _extract_ip_from_request(request: Optional[Request]) -> Optional[str]:
        """Extract IP address from request."""
        if not request:
            return None

        # Check X-Forwarded-For header (for proxies)
        if "x-forwarded-for" in request.headers:
            return request.headers["x-forwarded-for"].split(",")[0].strip()

        # Check X-Real-IP header
        if "x-real-ip" in request.headers:
            return request.headers["x-real-ip"]

        # Fallback to client host
        if hasattr(request, "client") and request.client:
            return request.client.host

        return None

    @staticmethod
    def _extract_user_agent(request: Optional[Request]) -> Optional[str]:
        """Extract user agent from request."""
        if not request:
            return None

        return request.headers.get("user-agent")

    @staticmethod
    async def log_action(
        session: AsyncSession,
        user: TokenData,
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        resource_name: Optional[str] = None,
        details: Optional[Dict] = None,
        changes: Optional[Dict] = None,
        request: Optional[Request] = None,
        status: str = "success",
        error_message: Optional[str] = None
    ):
        """
        Log an audit event.

        Args:
            session: Database session
            user: Authenticated user
            action: Action type (create, update, delete, etc.)
            resource_type: Type of resource affected
            resource_id: Optional resource ID
            resource_name: Optional resource name for readability
            details: Optional arbitrary details dict
            changes: Optional before/after changes dict
            request: Optional FastAPI Request object for IP/user agent extraction
            status: Action status (success, failed, denied)
            error_message: Optional error message if status is failed
        """
        ip_address = AuditService._extract_ip_from_request(request)
        user_agent = AuditService._extract_user_agent(request)

        audit_log = AuditLog(
            user_id=user.user_id,
            team_id=getattr(user, 'team_id', None),
            user_email=user.email,
            user_role=user.role,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            ip_address=ip_address,
            user_agent=user_agent,
            request_method=request.method if request else None,
            request_path=str(request.url.path) if request else None,
            details=details,
            changes=changes,
            status=status,
            error_message=error_message
        )

        # Insert into database using raw SQL
        from sqlalchemy import text

        insert_query = text("""
            INSERT INTO audit_logs (
                id, user_id, team_id, user_email, user_role,
                action, resource_type, resource_id, resource_name,
                ip_address, user_agent, request_method, request_path,
                details, changes, status, error_message, created_at
            ) VALUES (
                :id, :user_id, :team_id, :user_email, :user_role,
                :action, :resource_type, :resource_id, :resource_name,
                :ip_address, :user_agent, :request_method, :request_path,
                :details, :changes, :status, :error_message, :created_at
            )
        """)

        await session.execute(insert_query, {
            "id": audit_log.id,
            "user_id": audit_log.user_id,
            "team_id": audit_log.team_id,
            "user_email": audit_log.user_email,
            "user_role": audit_log.user_role,
            "action": audit_log.action,
            "resource_type": audit_log.resource_type,
            "resource_id": audit_log.resource_id,
            "resource_name": audit_log.resource_name,
            "ip_address": audit_log.ip_address,
            "user_agent": audit_log.user_agent,
            "request_method": audit_log.request_method,
            "request_path": audit_log.request_path,
            "details": audit_log.details,
            "changes": audit_log.changes,
            "status": audit_log.status,
            "error_message": audit_log.error_message,
            "created_at": audit_log.created_at
        })

        await session.commit()

    @staticmethod
    async def log_prospect_list_upload(
        session: AsyncSession,
        user: TokenData,
        list_id: str,
        filename: str,
        file_size: int,
        total_prospects: int,
        request: Optional[Request] = None
    ):
        """Convenience method for logging prospect list uploads."""
        await AuditService.log_action(
            session=session,
            user=user,
            action=AuditService.ACTION_UPLOAD,
            resource_type=AuditService.RESOURCE_PROSPECT_LIST,
            resource_id=list_id,
            resource_name=filename,
            details={
                "filename": filename,
                "file_size": file_size,
                "total_prospects": total_prospects
            },
            request=request
        )

    @staticmethod
    async def log_campaign_action(
        session: AsyncSession,
        user: TokenData,
        action: str,
        campaign_id: str,
        campaign_name: str,
        details: Optional[Dict] = None,
        request: Optional[Request] = None
    ):
        """Convenience method for logging campaign actions."""
        await AuditService.log_action(
            session=session,
            user=user,
            action=action,
            resource_type=AuditService.RESOURCE_CAMPAIGN,
            resource_id=campaign_id,
            resource_name=campaign_name,
            details=details,
            request=request
        )


# Singleton instance
audit_service = AuditService()
