"""
Knowledge Graph API endpoints.
Direct graph queries and conversational interface.
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.db.falkordb import graph_db

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
async def execute_cypher_query(request: CypherQuery):
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
async def semantic_search(request: SearchRequest):
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

        results = graph_db.query(query, {
            'query': request.query,
            'limit': request.limit,
        })
        all_results.extend(results)

    return {
        "query": request.query,
        "results": all_results[:request.limit],
        "count": len(all_results[:request.limit]),
    }


@router.post("/chat")
async def conversational_query(request: ChatRequest):
    """
    Natural language interface to the knowledge graph.

    Examples:
    - "Show me all prospects who opened emails but didn't reply"
    - "Which companies in fintech have we contacted?"
    - "Find prospects at Series A startups"

    TODO: Integrate with Claude API for natural language to Cypher translation.
    """
    message = request.message.lower()

    # Simple pattern matching for common queries
    # TODO: Replace with Claude-powered NL to Cypher

    if "opened" in message and ("not" in message or "didn't" in message) and "reply" in message:
        # Prospects who opened but didn't reply
        query = """
            MATCH (p:Prospect)-[:RECEIVED]->(e:Email)
            WHERE e.opened_at IS NOT NULL AND e.replied_at IS NULL
            RETURN DISTINCT p.email, p.first_name, p.last_name
            LIMIT 50
        """
        results = graph_db.query(query)
        return {
            "interpretation": "Finding prospects who opened emails but didn't reply",
            "results": results,
        }

    elif "company" in message or "companies" in message:
        # Get companies with optional industry filter
        industry = None
        for ind in ["fintech", "saas", "healthcare", "technology"]:
            if ind in message:
                industry = ind
                break

        if industry:
            query = """
                MATCH (c:Company)
                WHERE toLower(c.industry) CONTAINS $industry
                RETURN c.name, c.domain, c.industry
                LIMIT 50
            """
            results = graph_db.query(query, {'industry': industry})
            return {
                "interpretation": f"Finding companies in {industry}",
                "results": results,
            }
        else:
            query = "MATCH (c:Company) RETURN c.name, c.domain, c.industry LIMIT 50"
            results = graph_db.query(query)
            return {
                "interpretation": "Listing companies",
                "results": results,
            }

    elif "prospect" in message or "contact" in message:
        # Generic prospect query
        query = """
            MATCH (p:Prospect)
            OPTIONAL MATCH (p)-[:WORKS_AT]->(c:Company)
            RETURN p.email, p.first_name, p.last_name, p.title, c.name as company
            LIMIT 50
        """
        results = graph_db.query(query)
        return {
            "interpretation": "Listing prospects",
            "results": results,
        }

    elif "sequence" in message:
        query = """
            MATCH (s:Sequence)
            OPTIONAL MATCH (p:Prospect)-[e:ENROLLED_IN]->(s)
            RETURN s.name, s.status, count(e) as enrolled
            LIMIT 20
        """
        results = graph_db.query(query)
        return {
            "interpretation": "Listing sequences",
            "results": results,
        }

    else:
        return {
            "interpretation": "I couldn't understand that query. Try asking about prospects, companies, or sequences.",
            "results": [],
            "suggestions": [
                "Show me all prospects",
                "Which companies are in fintech?",
                "List active sequences",
                "Find prospects who opened emails but didn't reply",
            ],
        }


@router.get("/entities/{entity_id}")
async def get_entity(
    entity_id: int,
    include_relations: bool = Query(default=True),
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
    result = graph_db.query(type_query, {'id': entity_id})

    if not result:
        raise HTTPException(status_code=404, detail="Entity not found")

    entity = result[0]
    labels = entity.get('labels', [])

    if not include_relations:
        return entity

    # Get relationships based on entity type
    if 'Prospect' in labels:
        rel_query = """
            MATCH (p:Prospect)
            WHERE id(p) = $id
            OPTIONAL MATCH (p)-[r]->(related)
            RETURN p, type(r) as relationship, labels(related) as related_type, related
        """
    elif 'Company' in labels:
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

    relations = graph_db.query(rel_query, {'id': entity_id})

    return {
        "entity": entity,
        "relationships": relations,
    }


@router.get("/stats")
async def get_graph_stats():
    """
    Get statistics about the knowledge graph.
    """
    stats = {}

    # Count each node type
    for label in ["Prospect", "Company", "Sequence", "Email", "IntentSignal"]:
        query = f"MATCH (n:{label}) RETURN count(n) as count"
        result = graph_db.query(query)
        stats[label.lower() + "_count"] = result[0].get('count', 0) if result else 0

    # Count relationships
    rel_query = """
        MATCH ()-[r]->()
        RETURN type(r) as type, count(r) as count
    """
    rel_results = graph_db.query(rel_query)
    stats["relationships"] = {r.get('type', 'unknown'): r.get('count', 0) for r in rel_results}

    return stats
