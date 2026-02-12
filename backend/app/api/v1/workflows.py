"""
Workflow API endpoints for n8n email automation integration.

Provides CRUD operations for workflows and execution triggering.
"""

from __future__ import annotations

from typing import Optional, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File
from pydantic import BaseModel, Field

from app.core.security import TokenData, require_auth
from app.db.postgres import get_db
from app.models.workflow import WorkflowType, WorkflowStatus
from app.services.workflow_service import workflow_service


router = APIRouter(prefix="/workflows", tags=["Workflows"])


# ============================================================================
# Request/Response Models
# ============================================================================


class WorkflowCreate(BaseModel):
    """Request to create a new workflow."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    workflow_type: WorkflowType = Field(default=WorkflowType.CUSTOM)
    n8n_workflow_id: Optional[str] = Field(None, max_length=100)
    n8n_webhook_path: Optional[str] = Field(None, max_length=255)
    settings: dict[str, Any] = Field(default_factory=dict)


class WorkflowUpdate(BaseModel):
    """Request to update a workflow."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    settings: Optional[dict[str, Any]] = None
    is_active: Optional[bool] = None


class WorkflowResponse(BaseModel):
    """Workflow response model."""
    id: str
    name: str
    description: Optional[str]
    workflow_type: str
    n8n_workflow_id: Optional[str]
    n8n_webhook_path: Optional[str]
    settings: dict[str, Any]
    status: str
    is_active: bool
    owner_id: str
    team_id: Optional[str]
    execution_count: str
    last_executed_at: Optional[str]
    last_error: Optional[str]
    created_at: str
    updated_at: str


class WorkflowListResponse(BaseModel):
    """List of workflows response."""
    workflows: list[WorkflowResponse]
    total: int
    limit: int
    offset: int


class ExecutionResponse(BaseModel):
    """Workflow execution response."""
    id: str
    workflow_id: str
    status: str
    trigger_type: Optional[str]
    input_data: dict[str, Any]
    output_data: dict[str, Any]
    error_message: Optional[str]
    started_at: str
    completed_at: Optional[str]
    duration_ms: Optional[str]


class TriggerRequest(BaseModel):
    """Request to trigger a workflow execution."""
    input_data: dict[str, Any] = Field(default_factory=dict)


class TriggerResponse(BaseModel):
    """Response from workflow trigger."""
    execution_id: str
    status: str
    message: str


# ============================================================================
# Helper Functions
# ============================================================================


def workflow_to_response(workflow) -> WorkflowResponse:
    """Convert Workflow model to response."""
    return WorkflowResponse(
        id=str(workflow.id),
        name=workflow.name,
        description=workflow.description,
        workflow_type=workflow.workflow_type.value if workflow.workflow_type else "custom",
        n8n_workflow_id=workflow.n8n_workflow_id,
        n8n_webhook_path=workflow.n8n_webhook_path,
        settings=workflow.settings or {},
        status=workflow.status.value if workflow.status else "inactive",
        is_active=workflow.is_active,
        owner_id=str(workflow.owner_id),
        team_id=str(workflow.team_id) if workflow.team_id else None,
        execution_count=workflow.execution_count or "0",
        last_executed_at=workflow.last_executed_at.isoformat() if workflow.last_executed_at else None,
        last_error=workflow.last_error,
        created_at=workflow.created_at.isoformat() if workflow.created_at else "",
        updated_at=workflow.updated_at.isoformat() if workflow.updated_at else "",
    )


def execution_to_response(execution) -> ExecutionResponse:
    """Convert WorkflowExecution model to response."""
    return ExecutionResponse(
        id=str(execution.id),
        workflow_id=str(execution.workflow_id),
        status=execution.status,
        trigger_type=execution.trigger_type,
        input_data=execution.input_data or {},
        output_data=execution.output_data or {},
        error_message=execution.error_message,
        started_at=execution.started_at.isoformat() if execution.started_at else "",
        completed_at=execution.completed_at.isoformat() if execution.completed_at else None,
        duration_ms=execution.duration_ms,
    )


# ============================================================================
# Endpoints
# ============================================================================


@router.post("", response_model=WorkflowResponse, status_code=201)
async def create_workflow(
    request: WorkflowCreate,
    user: TokenData = Depends(require_auth),
):
    """
    Create a new workflow.

    Workflows can be linked to n8n workflows for automation.
    """
    async with get_db() as session:
        workflow = await workflow_service.create_workflow(
            session=session,
            name=request.name,
            description=request.description,
            workflow_type=request.workflow_type,
            owner_id=UUID(user.user_id),
            n8n_workflow_id=request.n8n_workflow_id,
            n8n_webhook_path=request.n8n_webhook_path,
            settings_data=request.settings,
        )
        return workflow_to_response(workflow)


@router.get("", response_model=WorkflowListResponse)
async def list_workflows(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    workflow_type: Optional[WorkflowType] = Query(default=None),
    my_workflows: bool = Query(default=False, description="Only show my workflows"),
    user: TokenData = Depends(require_auth),
):
    """
    List all available workflows.

    Filter by type or owner using query parameters.
    """
    async with get_db() as session:
        owner_id = UUID(user.user_id) if my_workflows else None
        workflows = await workflow_service.list_workflows(
            session=session,
            owner_id=owner_id,
            workflow_type=workflow_type,
            limit=limit,
            offset=offset,
        )
        return WorkflowListResponse(
            workflows=[workflow_to_response(w) for w in workflows],
            total=len(workflows),
            limit=limit,
            offset=offset,
        )


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(
    workflow_id: str,
    user: TokenData = Depends(require_auth),
):
    """Get a workflow by ID."""
    async with get_db() as session:
        workflow = await workflow_service.get_workflow(session, UUID(workflow_id))
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        return workflow_to_response(workflow)


@router.put("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(
    workflow_id: str,
    request: WorkflowUpdate,
    user: TokenData = Depends(require_auth),
):
    """Update an existing workflow."""
    async with get_db() as session:
        workflow = await workflow_service.get_workflow(session, UUID(workflow_id))
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")

        # Check ownership
        if str(workflow.owner_id) != user.user_id and user.role != "admin":
            raise HTTPException(status_code=403, detail="Not authorized to modify this workflow")

        updated = await workflow_service.update_workflow(
            session=session,
            workflow_id=UUID(workflow_id),
            name=request.name,
            description=request.description,
            settings_data=request.settings,
            is_active=request.is_active,
        )

        if not updated:
            raise HTTPException(status_code=500, detail="Failed to update workflow")

        return workflow_to_response(updated)


@router.delete("/{workflow_id}", status_code=204)
async def delete_workflow(
    workflow_id: str,
    user: TokenData = Depends(require_auth),
):
    """Delete a workflow."""
    async with get_db() as session:
        workflow = await workflow_service.get_workflow(session, UUID(workflow_id))
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")

        if str(workflow.owner_id) != user.user_id and user.role != "admin":
            raise HTTPException(status_code=403, detail="Not authorized to delete this workflow")

        success = await workflow_service.delete_workflow(session, UUID(workflow_id))
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete workflow")


@router.post("/{workflow_id}/toggle", response_model=WorkflowResponse)
async def toggle_workflow(
    workflow_id: str,
    user: TokenData = Depends(require_auth),
):
    """Toggle workflow active status."""
    async with get_db() as session:
        workflow = await workflow_service.get_workflow(session, UUID(workflow_id))
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")

        if str(workflow.owner_id) != user.user_id and user.role != "admin":
            raise HTTPException(status_code=403, detail="Not authorized to modify this workflow")

        updated = await workflow_service.toggle_workflow(session, UUID(workflow_id))
        if not updated:
            raise HTTPException(status_code=500, detail="Failed to toggle workflow")

        return workflow_to_response(updated)


@router.post("/{workflow_id}/trigger", response_model=TriggerResponse)
async def trigger_workflow(
    workflow_id: str,
    request: TriggerRequest,
    user: TokenData = Depends(require_auth),
):
    """
    Manually trigger a workflow execution.

    The workflow must be active to be triggered.
    """
    async with get_db() as session:
        workflow = await workflow_service.get_workflow(session, UUID(workflow_id))
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")

        if not workflow.is_active:
            raise HTTPException(status_code=400, detail="Workflow is not active")

        execution = await workflow_service.trigger_workflow(
            session=session,
            workflow_id=UUID(workflow_id),
            input_data=request.input_data,
            trigger_type="manual",
        )

        if not execution:
            raise HTTPException(status_code=500, detail="Failed to trigger workflow")

        return TriggerResponse(
            execution_id=str(execution.id),
            status=execution.status,
            message=f"Workflow triggered successfully" if execution.status == "success" else f"Workflow execution {execution.status}",
        )


@router.get("/{workflow_id}/executions", response_model=list[ExecutionResponse])
async def get_workflow_executions(
    workflow_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: TokenData = Depends(require_auth),
):
    """Get execution history for a workflow."""
    async with get_db() as session:
        workflow = await workflow_service.get_workflow(session, UUID(workflow_id))
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")

        executions = await workflow_service.get_executions(
            session=session,
            workflow_id=UUID(workflow_id),
            limit=limit,
            offset=offset,
        )

        return [execution_to_response(e) for e in executions]


@router.post("/seed", response_model=list[WorkflowResponse])
async def seed_default_workflows(
    user: TokenData = Depends(require_auth),
):
    """
    Seed the default email automation workflows.

    Creates the 4 main workflows from the n8n templates:
    - Auto Email Reply (IMAP Listener)
    - Email Writer
    - User Call Email Summary
    - Head Bot Flow (Controller)
    """
    async with get_db() as session:
        workflows = await workflow_service.seed_default_workflows(
            session=session,
            owner_id=UUID(user.user_id),
        )
        return [workflow_to_response(w) for w in workflows]


@router.post("/import", response_model=WorkflowResponse)
async def import_workflow(
    file: UploadFile = File(...),
    user: TokenData = Depends(require_auth),
):
    """
    Import a workflow from n8n JSON export file.

    Upload a .json file exported from n8n to create a new workflow.
    """
    if not file.filename or not file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="File must be a JSON file")

    try:
        import json
        content = await file.read()
        json_data = json.loads(content.decode("utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {str(e)}")

    async with get_db() as session:
        workflow = await workflow_service.import_from_n8n_json(
            session=session,
            json_content=json_data,
            owner_id=UUID(user.user_id),
        )
        return workflow_to_response(workflow)


@router.get("/types/available")
async def get_workflow_types(
    user: TokenData = Depends(require_auth),
):
    """Get available workflow types with descriptions."""
    return {
        "types": [
            {
                "value": WorkflowType.AUTO_REPLY.value,
                "name": "Auto Reply",
                "description": "Automatically reply to incoming emails using AI",
            },
            {
                "value": WorkflowType.EMAIL_WRITER.value,
                "name": "Email Writer",
                "description": "AI-powered email composition assistant",
            },
            {
                "value": WorkflowType.EMAIL_SUMMARY.value,
                "name": "Email Summary",
                "description": "Summarize and categorize inbox emails",
            },
            {
                "value": WorkflowType.CONTROLLER.value,
                "name": "Controller",
                "description": "Orchestrate multiple workflows based on intent",
            },
            {
                "value": WorkflowType.CUSTOM.value,
                "name": "Custom",
                "description": "User-defined custom workflow",
            },
        ]
    }
