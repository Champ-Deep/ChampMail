"""
Graph API — thin proxies onto Cham_Graph (SUGGESTIONS 4.4).

The old version of this router ran raw user-supplied Cypher against an embedded
FalkorDB (no validation, no rate limit, not read-only) and its one interesting
function had zero callers. The suite's single graph is Cham_Graph; these
endpoints proxy it and keep the old URL shapes that callers used. FalkorDB
remains only in the legacy prospect/sequence paths pending their migration.
"""

from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.security import TokenData, require_auth

router = APIRouter()


class GraphQueryRequest(BaseModel):
    query: str
    account: Optional[str] = "default"
    limit: Optional[int] = 20


class EmailContextRequest(BaseModel):
    account: str
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    subject: Optional[str] = None


class LogEmailRequest(BaseModel):
    account_name: str
    from_address: str
    to_address: str
    subject: str
    body: str
    direction: str  # inbound | outbound


async def _graph_request(method: str, path: str, **kwargs: Any) -> Any:
    settings = get_settings()
    if not settings.champgraph_url:
        raise HTTPException(status_code=503, detail="Cham_Graph not configured (CHAMPGRAPH_URL)")
    headers = {"Content-Type": "application/json"}
    if settings.champgraph_api_key:
        headers["X-API-Key"] = settings.champgraph_api_key
    url = f"{settings.champgraph_url.rstrip('/')}{path}"
    try:
        async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
            res = await client.request(method, url, **kwargs)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Cham_Graph unreachable: {e}") from e
    if res.status_code >= 400:
        raise HTTPException(status_code=res.status_code, detail=f"Cham_Graph: {res.text[:300]}")
    return res.json()


@router.post("/graph/query")
async def graph_query(request: GraphQueryRequest, user: TokenData = Depends(require_auth)):
    """Natural-language graph search (replaces raw Cypher — same URL, safe backend)."""
    return await _graph_request(
        "POST", "/api/query",
        json={"account": request.account, "query": request.query, "limit": request.limit},
    )


@router.post("/graph/search")
async def graph_search(request: GraphQueryRequest, user: TokenData = Depends(require_auth)):
    """Semantic search — Cham_Graph's query is already hybrid/semantic."""
    return await _graph_request(
        "POST", "/api/query",
        json={"account": request.account, "query": request.query, "limit": request.limit},
    )


@router.post("/graph/chat")
async def graph_chat(request: GraphQueryRequest, user: TokenData = Depends(require_auth)):
    """Conversational query — proxied to the same NL search (old canned patterns deleted)."""
    return await _graph_request(
        "POST", "/api/query",
        json={"account": request.account, "query": request.query, "limit": request.limit},
    )


@router.post("/graph/email-context")
async def graph_email_context(request: EmailContextRequest, user: TokenData = Depends(require_auth)):
    params = {k: v for k, v in request.model_dump().items() if v is not None and k != "account"}
    return await _graph_request("GET", f"/api/accounts/{request.account}/email-context", params=params)


@router.post("/graph/log-email")
async def graph_log_email(request: LogEmailRequest, user: TokenData = Depends(require_auth)):
    return await _graph_request("POST", "/api/hooks/email", json=request.model_dump())
