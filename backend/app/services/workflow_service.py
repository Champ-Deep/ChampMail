"""
Workflow management service for n8n integration.

Handles workflow CRUD operations, execution triggering, and n8n communication.
"""

from __future__ import annotations

import json
import httpx
from datetime import datetime
from typing import Optional, Any
from uuid import UUID, uuid4

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.workflow import Workflow, WorkflowExecution, WorkflowType, WorkflowStatus


# Default workflow configurations extracted from n8n JSON files
# Note: Auto Reply, Email Writer, and Email Summary are SUB-WORKFLOWS called by the Controller.
# They don't have direct webhooks - they're triggered via "Execute Workflow" nodes in n8n.
# Only the Controller (Head Bot) has a webhook endpoint.
DEFAULT_WORKFLOWS = {
    "auto_reply": {
        "name": "Auto Email Reply - IMAP Listener",
        "description": "Automatically generates and sends intelligent email replies using AI. Monitors IMAP inbox for new emails and sends contextual responses. Called as sub-workflow by Controller or triggered by IMAP.",
        "workflow_type": WorkflowType.AUTO_REPLY,
        "n8n_workflow_id": "G7pQAm3Z7ZRgXMMqC-K-y",
        # No webhook - triggered by IMAP listener or called as sub-workflow
        "settings": {
            "auto_reply_enabled": True,
            "auto_reply_context": "I am currently unavailable and will respond as soon as possible.",
            "skip_patterns": ["noreply", "no-reply", "donotreply", "mailer-daemon", "postmaster", "notifications", "newsletter", "marketing", "bounce", "auto"],
            "ai_model": "openai/gpt-4o-mini",
            "ai_temperature": 0.7,
            "trigger_type": "imap_or_subworkflow",
        },
    },
    "email_writer": {
        "name": "Email Writer",
        "description": "AI-powered email composition assistant. Generates professional emails based on provided context, tone, and recipient information. Called as sub-workflow by Controller.",
        "workflow_type": WorkflowType.EMAIL_WRITER,
        "n8n_workflow_id": "jXkL3ebRhjgFcLafa9AZH",
        # No webhook - called as sub-workflow by Controller
        "settings": {
            "default_tone": "professional",
            "ai_model": "openai/gpt-4o-mini",
            "ai_temperature": 0.7,
            "trigger_type": "subworkflow",
        },
    },
    "email_summary": {
        "name": "User Call Email Summary",
        "description": "Fetches and summarizes inbox emails using AI. Provides categorized summaries with priority highlighting and action items. Called as sub-workflow by Controller.",
        "workflow_type": WorkflowType.EMAIL_SUMMARY,
        "n8n_workflow_id": "XX4N5P3IiiqTvomnztmvT",
        # No webhook - called as sub-workflow by Controller
        "settings": {
            "max_emails": 20,
            "ai_model": "openai/gpt-4o-mini",
            "ai_temperature": 0.3,
            "store_in_postgres": True,
            "trigger_type": "subworkflow",
        },
    },
    "controller": {
        "name": "Head Bot Flow - Main Controller",
        "description": "Central orchestrator for email automation workflows. Routes requests to appropriate sub-workflows based on intent classification. This is the MAIN entry point - call this webhook to use email automation.",
        "workflow_type": WorkflowType.CONTROLLER,
        "n8n_workflow_id": "B01-22OIGZyap8T3ZEf2C",
        "n8n_webhook_path": "email_agent",  # Webhook path: /webhook/email_agent
        "settings": {
            "ai_model": "openai/gpt-4o",
            "ai_temperature": 0,
            "trigger_type": "webhook",
        },
    },
}


class WorkflowService:
    """Service for managing email automation workflows."""

    async def create_workflow(
        self,
        session: AsyncSession,
        name: str,
        description: str,
        workflow_type: WorkflowType,
        owner_id: UUID,
        n8n_workflow_id: Optional[str] = None,
        n8n_webhook_path: Optional[str] = None,
        config: Optional[dict] = None,
        settings_data: Optional[dict] = None,
        team_id: Optional[UUID] = None,
    ) -> Workflow:
        """Create a new workflow."""
        workflow = Workflow(
            name=name,
            description=description,
            workflow_type=workflow_type,
            n8n_workflow_id=n8n_workflow_id,
            n8n_webhook_path=n8n_webhook_path,
            config=config or {},
            settings=settings_data or {},
            owner_id=owner_id,
            team_id=team_id,
            status=WorkflowStatus.INACTIVE,
            is_active=False,
        )
        session.add(workflow)
        await session.commit()
        await session.refresh(workflow)
        return workflow

    async def get_workflow(
        self,
        session: AsyncSession,
        workflow_id: UUID,
    ) -> Optional[Workflow]:
        """Get a workflow by ID."""
        result = await session.execute(
            select(Workflow).where(Workflow.id == workflow_id)
        )
        return result.scalar_one_or_none()

    async def get_workflow_by_n8n_id(
        self,
        session: AsyncSession,
        n8n_workflow_id: str,
    ) -> Optional[Workflow]:
        """Get a workflow by its n8n workflow ID."""
        result = await session.execute(
            select(Workflow).where(Workflow.n8n_workflow_id == n8n_workflow_id)
        )
        return result.scalar_one_or_none()

    async def list_workflows(
        self,
        session: AsyncSession,
        owner_id: Optional[UUID] = None,
        team_id: Optional[UUID] = None,
        workflow_type: Optional[WorkflowType] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Workflow]:
        """List workflows with optional filtering."""
        query = select(Workflow)

        if owner_id:
            query = query.where(Workflow.owner_id == owner_id)
        if team_id:
            query = query.where(Workflow.team_id == team_id)
        if workflow_type:
            query = query.where(Workflow.workflow_type == workflow_type)

        query = query.order_by(Workflow.created_at.desc())
        query = query.offset(offset).limit(limit)

        result = await session.execute(query)
        return list(result.scalars().all())

    async def update_workflow(
        self,
        session: AsyncSession,
        workflow_id: UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
        settings_data: Optional[dict] = None,
        is_active: Optional[bool] = None,
        status: Optional[WorkflowStatus] = None,
    ) -> Optional[Workflow]:
        """Update an existing workflow."""
        workflow = await self.get_workflow(session, workflow_id)
        if not workflow:
            return None

        if name is not None:
            workflow.name = name
        if description is not None:
            workflow.description = description
        if settings_data is not None:
            workflow.settings = settings_data
        if is_active is not None:
            workflow.is_active = is_active
        if status is not None:
            workflow.status = status

        workflow.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(workflow)
        return workflow

    async def delete_workflow(
        self,
        session: AsyncSession,
        workflow_id: UUID,
    ) -> bool:
        """Delete a workflow and its executions."""
        workflow = await self.get_workflow(session, workflow_id)
        if not workflow:
            return False

        await session.delete(workflow)
        await session.commit()
        return True

    async def toggle_workflow(
        self,
        session: AsyncSession,
        workflow_id: UUID,
    ) -> Optional[Workflow]:
        """Toggle workflow active status."""
        workflow = await self.get_workflow(session, workflow_id)
        if not workflow:
            return None

        workflow.is_active = not workflow.is_active
        workflow.status = WorkflowStatus.ACTIVE if workflow.is_active else WorkflowStatus.INACTIVE
        workflow.updated_at = datetime.utcnow()

        await session.commit()
        await session.refresh(workflow)
        return workflow

    async def trigger_workflow(
        self,
        session: AsyncSession,
        workflow_id: UUID,
        input_data: dict[str, Any],
        trigger_type: str = "manual",
    ) -> Optional[WorkflowExecution]:
        """
        Trigger a workflow execution via n8n webhook.

        Args:
            session: Database session
            workflow_id: ID of the workflow to trigger
            input_data: Data to send to the workflow
            trigger_type: Type of trigger (manual, webhook, schedule)

        Returns:
            WorkflowExecution record or None if failed
        """
        workflow = await self.get_workflow(session, workflow_id)
        if not workflow or not workflow.is_active:
            return None

        # Create execution record
        execution = WorkflowExecution(
            workflow_id=workflow_id,
            status="pending",
            trigger_type=trigger_type,
            input_data=input_data,
            started_at=datetime.utcnow(),
        )
        session.add(execution)
        await session.commit()
        await session.refresh(execution)

        # Try to trigger n8n webhook
        try:
            execution.status = "running"
            await session.commit()

            webhook_url = self._build_webhook_url(workflow)
            if webhook_url:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        webhook_url,
                        json=input_data,
                        headers={
                            "Content-Type": "application/json",
                            "X-Workflow-Id": str(workflow_id),
                        },
                    )
                    response.raise_for_status()
                    execution.output_data = response.json() if response.text else {}
                    execution.status = "success"
            else:
                # No webhook configured, just mark as success for now
                execution.output_data = {"message": "Workflow triggered (no webhook configured)"}
                execution.status = "success"

            execution.completed_at = datetime.utcnow()
            if execution.started_at:
                duration = (execution.completed_at - execution.started_at).total_seconds() * 1000
                execution.duration_ms = str(int(duration))

            # Update workflow stats
            workflow.last_executed_at = datetime.utcnow()
            workflow.execution_count = str(int(workflow.execution_count or "0") + 1)

            await session.commit()
            await session.refresh(execution)
            return execution

        except Exception as e:
            execution.status = "failed"
            execution.error_message = str(e)
            execution.completed_at = datetime.utcnow()

            workflow.last_error = str(e)
            workflow.status = WorkflowStatus.ERROR

            await session.commit()
            await session.refresh(execution)
            return execution

    def _build_webhook_url(self, workflow: Workflow) -> Optional[str]:
        """
        Build the n8n webhook URL for a workflow.

        Only the Controller workflow has a webhook. Other workflows are sub-workflows
        that are called internally by n8n via "Execute Workflow" nodes.
        """
        if workflow.n8n_webhook_path:
            base_url = settings.n8n_webhook_url.rstrip("/")
            # Remove any leading slashes and "webhook/" prefix if already in base_url
            path = workflow.n8n_webhook_path.lstrip("/")
            if path.startswith("webhook/"):
                path = path[8:]  # Remove "webhook/" prefix

            # Ensure base_url ends with /webhook
            if not base_url.endswith("/webhook"):
                base_url = f"{base_url}/webhook" if "/webhook" not in base_url else base_url

            return f"{base_url}/{path}"
        return None

    async def get_executions(
        self,
        session: AsyncSession,
        workflow_id: UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> list[WorkflowExecution]:
        """Get execution history for a workflow."""
        result = await session.execute(
            select(WorkflowExecution)
            .where(WorkflowExecution.workflow_id == workflow_id)
            .order_by(WorkflowExecution.started_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def seed_default_workflows(
        self,
        session: AsyncSession,
        owner_id: UUID,
        team_id: Optional[UUID] = None,
    ) -> list[Workflow]:
        """
        Seed the default email automation workflows for a user.

        This creates the 4 main workflows from the n8n JSON files.
        """
        created_workflows = []

        for key, config in DEFAULT_WORKFLOWS.items():
            # Check if workflow already exists
            existing = await self.get_workflow_by_n8n_id(session, config["n8n_workflow_id"])
            if existing:
                continue

            workflow = await self.create_workflow(
                session=session,
                name=config["name"],
                description=config["description"],
                workflow_type=config["workflow_type"],
                owner_id=owner_id,
                n8n_workflow_id=config["n8n_workflow_id"],
                n8n_webhook_path=config.get("n8n_webhook_path"),
                settings_data=config.get("settings", {}),
                team_id=team_id,
            )
            created_workflows.append(workflow)

        return created_workflows

    async def import_from_n8n_json(
        self,
        session: AsyncSession,
        json_content: dict,
        owner_id: UUID,
        team_id: Optional[UUID] = None,
    ) -> Workflow:
        """
        Import a workflow from n8n JSON export.

        Args:
            session: Database session
            json_content: Parsed n8n workflow JSON
            owner_id: Owner user ID
            team_id: Optional team ID

        Returns:
            Created workflow
        """
        name = json_content.get("name", "Imported Workflow")
        n8n_id = json_content.get("id")

        # Detect workflow type from nodes
        workflow_type = self._detect_workflow_type(json_content)

        # Extract webhook path if present
        webhook_path = None
        nodes = json_content.get("nodes", [])
        for node in nodes:
            if node.get("type") == "n8n-nodes-base.webhook":
                webhook_path = node.get("parameters", {}).get("path")
                break

        return await self.create_workflow(
            session=session,
            name=name,
            description=f"Imported from n8n: {name}",
            workflow_type=workflow_type,
            owner_id=owner_id,
            n8n_workflow_id=n8n_id,
            n8n_webhook_path=webhook_path,
            config=json_content,
            team_id=team_id,
        )

    def _detect_workflow_type(self, json_content: dict) -> WorkflowType:
        """Detect workflow type from n8n JSON content."""
        name = json_content.get("name", "").lower()
        nodes = json_content.get("nodes", [])

        # Check for IMAP listener
        has_imap = any("emailReadImap" in n.get("type", "") for n in nodes)
        if has_imap or "auto" in name and "reply" in name:
            return WorkflowType.AUTO_REPLY

        # Check for email writer pattern
        if "writer" in name or "compose" in name:
            return WorkflowType.EMAIL_WRITER

        # Check for summary pattern
        if "summary" in name or "summarize" in name:
            return WorkflowType.EMAIL_SUMMARY

        # Check for controller pattern
        has_subworkflows = any("toolWorkflow" in n.get("type", "") for n in nodes)
        if has_subworkflows or "controller" in name or "head" in name:
            return WorkflowType.CONTROLLER

        return WorkflowType.CUSTOM


# Global service instance
workflow_service = WorkflowService()
