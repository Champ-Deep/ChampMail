"""
Knowledge Graph API endpoints.
Routes to ChampGraph for semantic search, natural language queries,
and account intelligence.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.core.security import require_auth, TokenData
from app.core.admin_security import require_admin
from app.db.champgraph import graph_db

router = APIRouter(prefix="/graph", tags=["Knowledge Graph"])


class SearchRequest(BaseModel):
    """Semantic search request."""
    query: str
    entity_types: list[str] = []  # e.g., ["Prospect", "Company"]
    limit: int = 20
    account: str = "champmail"


class ChatRequest(BaseModel):
    """Conversational query request."""
    message: str
    account: str = "champmail"
    context: dict[str, Any] = {}


class CypherQuery(BaseModel):
    """Direct query request (now semantic, kept for API compat)."""
    query: str
    params: dict[str, Any] = {}
    account: str = "champmail"


@router.post("/query")
async def execute_query(request: CypherQuery, user: TokenData = Depends(require_admin)):
    """
    Execute a query against the knowledge graph via ChampGraph.

    This now performs semantic search rather than raw Cypher.
    """
    try:
        results = await graph_db.query(request.query, account_name=request.account)
        return {
            "success": True,
            "results": results,
            "count": len(results),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Query error: {str(e)}")


@router.post("/search")
async def semantic_search(request: SearchRequest, user: TokenData = Depends(require_auth)):
    """
    Semantic search across the knowledge graph via ChampGraph.
    """
    search_query = request.query
    if request.entity_types:
        search_query += f" (entity types: {', '.join(request.entity_types)})"

    results = await graph_db.query(search_query, account_name=request.account)
    return {
        "query": request.query,
        "results": results[:request.limit],
        "count": len(results[:request.limit]),
    }


@router.post("/chat")
async def conversational_query(request: ChatRequest, user: TokenData = Depends(require_auth)):
    """
    Natural language interface to the knowledge graph via ChampGraph.

    ChampGraph handles NL→graph resolution using Graphiti + LLM.
    """
    results = await graph_db.query(request.message, account_name=request.account)

    if not results:
        return {
            "interpretation": "No results found for that query.",
            "results": [],
            "suggestions": [
                "Show me all prospects",
                "Which companies are in fintech?",
                "List active sequences",
                "Find prospects who opened emails but didn't reply",
            ],
        }

    return {
        "interpretation": f"Results for: {request.message}",
        "results": results,
    }


@router.get("/accounts/{account_name}/email-context")
async def get_email_context(
    account_name: str,
    contact_email: str | None = Query(default=None),
    contact_name: str | None = Query(default=None),
    subject: str | None = Query(default=None),
    user: TokenData = Depends(require_auth),
):
    """Get full context for composing an email to a contact at an account."""
    result = await graph_db.get_email_context(
        account_name=account_name,
        contact_email=contact_email,
        contact_name=contact_name,
        subject=subject,
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail="Failed to get email context")
    return result


@router.get("/accounts/{account_name}/briefing")
async def get_account_briefing(
    account_name: str,
    user: TokenData = Depends(require_auth),
):
    """Get a comprehensive pre-interaction briefing for an account."""
    result = await graph_db.get_account_briefing(account_name)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail="Failed to get briefing")
    return result


@router.get("/accounts/{account_name}/stakeholders")
async def get_stakeholder_map(
    account_name: str,
    user: TokenData = Depends(require_auth),
):
    """Get stakeholder mapping: champions, blockers, decision-makers."""
    result = await graph_db.get_stakeholder_map(account_name)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail="Failed to get stakeholder map")
    return result


@router.get("/accounts/{account_name}/engagement-gaps")
async def get_engagement_gaps(
    account_name: str,
    days: int = Query(default=30),
    user: TokenData = Depends(require_auth),
):
    """Find contacts not interacted with recently."""
    result = await graph_db.get_engagement_gaps(account_name, days=days)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail="Failed to get engagement gaps")
    return result


@router.get("/stats")
async def get_graph_stats(user: TokenData = Depends(require_auth)):
    """
    Get statistics about the knowledge graph.
    Queries ChampGraph health for connectivity info.
    """
    try:
        health = await graph_db._get("/health")
        return {
            "service": health.get("service"),
            "status": health.get("status"),
            "neo4j_connected": health.get("neo4j_connected"),
            "version": health.get("version"),
        }
    except Exception as e:
        return {"status": "unavailable", "error": str(e)}
