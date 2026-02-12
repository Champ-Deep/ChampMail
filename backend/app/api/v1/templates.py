"""
Template API endpoints.

Provides CRUD operations for email templates with MJML support.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field

from app.core.security import TokenData, require_auth
from app.services.templates import (
    template_service,
    EmailTemplate,
    compile_mjml,
    extract_variables,
    substitute_variables,
)


router = APIRouter(prefix="/templates", tags=["Templates"])


# ============================================================================
# Request/Response Models
# ============================================================================


class TemplateCreate(BaseModel):
    """Request to create a new template."""
    name: str = Field(..., min_length=1, max_length=200)
    subject: str = Field(..., min_length=1, max_length=500)
    mjml_content: str = Field(..., min_length=1)
    compile_html: bool = Field(default=True, description="Compile MJML to HTML immediately")


class TemplateUpdate(BaseModel):
    """Request to update a template."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    subject: Optional[str] = Field(None, min_length=1, max_length=500)
    mjml_content: Optional[str] = Field(None, min_length=1)
    recompile: bool = Field(default=True, description="Recompile MJML to HTML")


class TemplateResponse(BaseModel):
    """Template response."""
    id: str
    name: str
    subject: str
    mjml_content: str
    html_content: Optional[str] = None
    variables: list[str] = []
    owner_id: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class TemplateListResponse(BaseModel):
    """List of templates response."""
    templates: list[TemplateResponse]
    total: int
    limit: int
    offset: int


class PreviewRequest(BaseModel):
    """Request to preview a template with variables."""
    variables: dict[str, str] = Field(default_factory=dict)


class PreviewResponse(BaseModel):
    """Template preview response."""
    subject: str
    html: str
    variables_used: list[str]


class CompileRequest(BaseModel):
    """Request to compile MJML to HTML."""
    mjml_content: str


class CompileResponse(BaseModel):
    """MJML compilation response."""
    html: Optional[str]
    error: Optional[str]
    variables: list[str]


# ============================================================================
# Helper Functions
# ============================================================================


def template_to_response(template: EmailTemplate) -> TemplateResponse:
    """Convert EmailTemplate to response model."""
    return TemplateResponse(
        id=template.id,
        name=template.name,
        subject=template.subject,
        mjml_content=template.mjml_content,
        html_content=template.html_content,
        variables=template.variables,
        owner_id=template.owner_id,
        created_at=template.created_at.isoformat() if template.created_at else None,
        updated_at=template.updated_at.isoformat() if template.updated_at else None,
    )


# ============================================================================
# Endpoints
# ============================================================================


@router.post("", response_model=TemplateResponse, status_code=201)
async def create_template(
    request: TemplateCreate,
    user: TokenData = Depends(require_auth),
):
    """
    Create a new email template.

    The template can include variable placeholders using {{variable_name}} syntax.
    Common variables: {{first_name}}, {{last_name}}, {{company}}, {{title}}, {{unsubscribe_link}}

    If compile_html is true (default), MJML will be compiled to HTML immediately.
    """
    template = template_service.create_template(
        name=request.name,
        subject=request.subject,
        mjml_content=request.mjml_content,
        owner_id=user.user_id,
        compile_html=request.compile_html,
    )
    return template_to_response(template)


@router.get("", response_model=TemplateListResponse)
async def list_templates(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    my_templates: bool = Query(default=False, description="Only show my templates"),
    user: TokenData = Depends(require_auth),
):
    """
    List all available templates.

    Set my_templates=true to only see templates you own.
    """
    owner_id = user.user_id if my_templates else None
    templates = template_service.list_templates(
        owner_id=owner_id,
        limit=limit,
        offset=offset,
    )
    return TemplateListResponse(
        templates=[template_to_response(t) for t in templates],
        total=len(templates),  # TODO: Implement count query
        limit=limit,
        offset=offset,
    )


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: str,
    user: TokenData = Depends(require_auth),
):
    """
    Get a template by ID.
    """
    template = template_service.get_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template_to_response(template)


@router.put("/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: str,
    request: TemplateUpdate,
    user: TokenData = Depends(require_auth),
):
    """
    Update an existing template.

    Only provide the fields you want to update.
    If recompile is true (default) and mjml_content is provided, HTML will be regenerated.
    """
    # Check template exists and user owns it
    existing = template_service.get_template(template_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Template not found")

    if existing.owner_id != user.user_id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to modify this template")

    template = template_service.update_template(
        template_id=template_id,
        name=request.name,
        subject=request.subject,
        mjml_content=request.mjml_content,
        recompile=request.recompile,
    )

    if not template:
        raise HTTPException(status_code=500, detail="Failed to update template")

    return template_to_response(template)


@router.delete("/{template_id}", status_code=204)
async def delete_template(
    template_id: str,
    user: TokenData = Depends(require_auth),
):
    """
    Delete a template.

    Only the template owner or admin can delete.
    """
    existing = template_service.get_template(template_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Template not found")

    if existing.owner_id != user.user_id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to delete this template")

    success = template_service.delete_template(template_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete template")


@router.post("/{template_id}/preview", response_model=PreviewResponse)
async def preview_template(
    template_id: str,
    request: PreviewRequest,
    user: TokenData = Depends(require_auth),
):
    """
    Generate a preview of the template with variable substitution.

    Provide custom variable values or use defaults:
    - first_name: "John"
    - last_name: "Doe"
    - company: "Acme Inc"
    - title: "CEO"
    - email: "john@example.com"
    """
    result = template_service.render_preview(
        template_id=template_id,
        variables=request.variables,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Template not found")

    return PreviewResponse(
        subject=result['subject'],
        html=result['html'],
        variables_used=result['variables_used'],
    )


@router.post("/compile", response_model=CompileResponse)
async def compile_mjml_endpoint(
    request: CompileRequest,
    user: TokenData = Depends(require_auth),
):
    """
    Compile MJML to HTML without saving a template.

    Useful for live preview in the editor.
    Returns the compiled HTML and any variables found in the content.
    """
    html, error = compile_mjml(request.mjml_content)
    variables = extract_variables(request.mjml_content)

    return CompileResponse(
        html=html,
        error=error,
        variables=variables,
    )


@router.post("/validate")
async def validate_template(
    request: CompileRequest,
    user: TokenData = Depends(require_auth),
):
    """
    Validate MJML content without compiling.

    Returns list of variables found and any syntax issues.
    """
    variables = extract_variables(request.mjml_content)

    # Basic validation
    issues = []
    if '<mjml>' not in request.mjml_content:
        issues.append("Missing <mjml> root tag")
    if '</mjml>' not in request.mjml_content:
        issues.append("Missing closing </mjml> tag")
    if '<mj-body>' not in request.mjml_content:
        issues.append("Missing <mj-body> tag")

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "variables": variables,
    }
