"""
Knowledge Graph API endpoints.
Direct graph queries, conversational interface, and AI-powered insights.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.core.security import require_auth, TokenData
from app.core.admin_security import require_admin
from app.db.falkordb import graph_db, FALKORDB_AVAILABLE
from app.services.graph_intelligence import graph_intelligence

router = APIRouter(prefix="/graph", tags=["Knowledge Graph"])


class CypherQuery(BaseModel):
    """Direct Cypher query request."""

    query: str
    params: dict[str, Any] = {}


class SearchRequest(BaseModel):
    """Semantic search request."""

    query: str
    entity_types: list[str] = []  # e.g., ["Prospect", "Company"]
    limit: int = 20


class ChatRequest(BaseModel):
    """Conversational query request."""

    message: str
    context: dict[str, Any] = {}


@router.post("/query")
async def execute_cypher_query(
    request: CypherQuery, user: TokenData = Depends(require_admin)
):
    """
    Execute a raw Cypher query against the knowledge graph.

    WARNING: This endpoint is for admin/development use only.
    Should be protected in production.

    Example queries:
    - "MATCH (p:Prospect) RETURN p LIMIT 10"
    - "MATCH (p:Prospect)-[:WORKS_AT]->(c:Company) RETURN p.email, c.name"
    """
    # TODO: Add query validation and sanitization
    # TODO: Add rate limiting
    # TODO: Restrict to read-only queries in production

    try:
        results = graph_db.query(request.query, request.params)
        return {
            "success": True,
            "results": results,
            "count": len(results),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Query error: {str(e)}")


@router.post("/search")
async def semantic_search(
    request: SearchRequest, user: TokenData = Depends(require_auth)
):
    """
    Semantic search across the knowledge graph.

    Searches across specified entity types (or all if not specified).
    Uses text matching on relevant fields.

    TODO: Integrate with Graphiti for true semantic/embedding-based search.
    """
    entity_types = request.entity_types or ["Prospect", "Company"]
    all_results = []

    for entity_type in entity_types:
        if entity_type == "Prospect":
            query = """
                MATCH (p:Prospect)
                WHERE toLower(p.email) CONTAINS toLower($query)
                   OR toLower(p.first_name) CONTAINS toLower($query)
                   OR toLower(p.last_name) CONTAINS toLower($query)
                   OR toLower(p.title) CONTAINS toLower($query)
                RETURN p, 'Prospect' as type
                LIMIT $limit
            """
        elif entity_type == "Company":
            query = """
                MATCH (c:Company)
                WHERE toLower(c.name) CONTAINS toLower($query)
                   OR toLower(c.domain) CONTAINS toLower($query)
                   OR toLower(c.industry) CONTAINS toLower($query)
                RETURN c, 'Company' as type
                LIMIT $limit
            """
        elif entity_type == "Sequence":
            query = """
                MATCH (s:Sequence)
                WHERE toLower(s.name) CONTAINS toLower($query)
                RETURN s, 'Sequence' as type
                LIMIT $limit
            """
        else:
            continue

        results = graph_db.query(
            query,
            {
                "query": request.query,
                "limit": request.limit,
            },
        )
        all_results.extend(results)

    return {
        "query": request.query,
        "results": all_results[: request.limit],
        "count": len(all_results[: request.limit]),
    }


@router.post("/chat")
async def conversational_query(
    request: ChatRequest, user: TokenData = Depends(require_auth)
):
    """
    Natural language interface to the knowledge graph.

    Uses LLM (Gemini Flash via OpenRouter) to convert natural language to Cypher queries.

    Examples:
    - "Show me all prospects who opened emails but didn't reply"
    - "Which companies in fintech have we contacted?"
    - "Find prospects at Series A startups"
    - "List all sequences with their enrollment counts"
    """
    if not FALKORDB_AVAILABLE:
        return {
            "interpretation": "Graph database not available",
            "results": [],
            "error": "FalkorDB is not connected. Please ensure the graph database is provisioned.",
        }

    result = await graph_intelligence.chat(request.message, request.context or {})
    return result


@router.get("/entities/{entity_id}")
async def get_entity(
    entity_id: int,
    include_relations: bool = Query(default=True),
    user: TokenData = Depends(require_auth),
):
    """
    Get any entity by its internal ID with optional relationships.
    """
    # First find what type of entity this is
    type_query = """
        MATCH (n)
        WHERE id(n) = $id
        RETURN labels(n) as labels, n
    """
    result = graph_db.query(type_query, {"id": entity_id})

    if not result:
        raise HTTPException(status_code=404, detail="Entity not found")

    entity = result[0]
    labels = entity.get("labels", [])

    if not include_relations:
        return entity

    # Get relationships based on entity type
    if "Prospect" in labels:
        rel_query = """
            MATCH (p:Prospect)
            WHERE id(p) = $id
            OPTIONAL MATCH (p)-[r]->(related)
            RETURN p, type(r) as relationship, labels(related) as related_type, related
        """
    elif "Company" in labels:
        rel_query = """
            MATCH (c:Company)
            WHERE id(c) = $id
            OPTIONAL MATCH (related)-[r]->(c)
            RETURN c, type(r) as relationship, labels(related) as related_type, related
        """
    else:
        rel_query = """
            MATCH (n)
            WHERE id(n) = $id
            OPTIONAL MATCH (n)-[r]-(related)
            RETURN n, type(r) as relationship, labels(related) as related_type, related
        """

    relations = graph_db.query(rel_query, {"id": entity_id})

    return {
        "entity": entity,
        "relationships": relations,
    }


@router.get("/stats")
async def get_graph_stats(user: TokenData = Depends(require_auth)):
    """
    Get statistics about the knowledge graph.
    """
    stats = {}

    # Count each node type
    for label in ["Prospect", "Company", "Sequence", "Email", "IntentSignal"]:
        query = f"MATCH (n:{label}) RETURN count(n) as count"
        result = graph_db.query(query)
        stats[label.lower() + "_count"] = result[0].get("count", 0) if result else 0

    # Count relationships
    rel_query = """
        MATCH ()-[r]->()
        RETURN type(r) as type, count(r) as count
    """
    rel_results = graph_db.query(rel_query)
    stats["relationships"] = {
        r.get("type", "unknown"): r.get("count", 0) for r in rel_results
    }

    return stats


@router.get("/path")
async def get_path(
    from_email: str = Query(..., description="Starting prospect email"),
    to_email: str = Query(..., description="Target prospect email"),
    user: TokenData = Depends(require_auth),
):
    """
    Find the connection path between two prospects.

    Shows how two prospects are connected through companies or sequences.
    Example: prospect A works at Company X, prospect B also works at Company X
    """
    if not FALKORDB_AVAILABLE:
        return {"path": [], "error": "Graph database not available"}

    result = await graph_intelligence.path_analysis(from_email, to_email)
    return result
