"""
Graph Intelligence Service.
LLM-powered natural language queries for the knowledge graph.
"""

import logging
from typing import Dict, List, Optional, Any

from app.core.config import settings
from app.db.falkordb import graph_db, FALKORDB_AVAILABLE

logger = logging.getLogger(__name__)

GRAPH_SCHEMA = """
You are a FalkorDB graph database expert. Your task is to convert natural language questions into Cypher queries.

## Node Types and Properties:

### Prospect
- email (unique identifier)
- first_name
- last_name
- title
- company_name
- company_domain
- industry
- status (active, bounced, unsubscribed, do_not_contact)
- source
- created_at

### Company
- name
- domain (unique identifier)
- industry
- employee_count

### Sequence
- name
- status (draft, active, paused)
- owner_id
- steps_count
- created_at

### Email (if present)
- subject
- sent_at
- opened_at
- replied_at
- clicked_at

## Relationship Types:
- (p:Prospect)-[:WORKS_AT]->(c:Company) - prospect works at company
- (p:Prospect)-[:ENROLLED_IN]->(s:Sequence) - prospect enrolled in sequence
- (p:Prospect)-[:RECEIVED]->(e:Email) - prospect received email

## Guidelines:
1. Only generate MATCH queries (no CREATE, DELETE, or UPDATE)
2. Always use case-insensitive matching with toLower() for text searches
3. Use LIMIT to prevent returning too many results (default 50)
4. Return properties that answer the user's question
5. If the question is ambiguous, make reasonable assumptions
6. If you cannot generate a valid query, return a helpful error message

## Output Format:
Return a JSON object with this structure:
{
  "cypher": "MATCH ... RETURN ...",
  "params": {"key": "value"},
  "interpretation": "A brief description of what this query does"
}

Example user questions and expected queries:
- "Show me all prospects" -> MATCH (p:Prospect) RETURN p LIMIT 50
- "Find prospects at Google" -> MATCH (p:Prospect)-[:WORKS_AT]->(c:Company) WHERE toLower(c.name) CONTAINS 'google' RETURN p, c LIMIT 50
- "Which companies in fintech have we contacted?" -> MATCH (c:Company) WHERE toLower(c.industry) CONTAINS 'fintech' RETURN c LIMIT 50
"""


class GraphIntelligenceService:
    """Service for LLM-powered graph queries."""

    def __init__(self):
        self._client: Optional[Any] = None

    @property
    def client(self):
        """Lazy load OpenRouter client."""
        if self._client is None:
            from app.services.ai.openrouter_service import OpenRouterClient

            self._client = OpenRouterClient()
        return self._client

    async def chat(
        self, message: str, context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Convert natural language to Cypher and execute.

        Args:
            message: User's natural language question
            context: Optional context from previous messages

        Returns:
            Dict with interpretation, results, and metadata
        """
        if not FALKORDB_AVAILABLE:
            return {
                "interpretation": "Graph database is not available",
                "results": [],
                "error": "FalkorDB is not connected. Please ensure the graph database is provisioned.",
            }

        if not settings.openrouter_api_key:
            return {
                "interpretation": "AI service not configured",
                "results": [],
                "error": "OpenRouter API key is not configured. Set OPENROUTER_API_KEY to enable natural language queries.",
            }

        try:
            response = await self.client.chat_completion(
                model=settings.graph_llm_model,
                messages=[
                    {"role": "system", "content": GRAPH_SCHEMA},
                    {"role": "user", "content": message},
                ],
                max_tokens=2048,
                temperature=0.1,
                response_format={"type": "json_object"},
            )

            import json

            try:
                parsed = json.loads(response)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse LLM response as JSON: {response}")
                return {
                    "interpretation": "Failed to understand the query",
                    "results": [],
                    "error": "Could not generate a valid query. Please try rephrasing your question.",
                }

            cypher = parsed.get("cypher", "")
            params = parsed.get("params", {})
            interpretation = parsed.get("interpretation", "Query executed")

            if not cypher or "MATCH" not in cypher.upper():
                return {
                    "interpretation": interpretation,
                    "results": [],
                    "error": parsed.get(
                        "error", "Could not generate a valid MATCH query"
                    ),
                }

            results = graph_db.query(cypher, params)

            return {
                "interpretation": interpretation,
                "results": results[:50],
                "count": len(results),
                "cypher": cypher,
            }

        except Exception as e:
            logger.error(f"Graph chat error: {e}")
            return {
                "interpretation": "Error executing query",
                "results": [],
                "error": str(e),
            }

    async def path_analysis(self, from_email: str, to_email: str) -> Dict[str, Any]:
        """
        Find path between two prospects via their companies.

        Args:
            from_email: Starting prospect email
            to_email: Target prospect email

        Returns:
            Path information if found
        """
        if not FALKORDB_AVAILABLE:
            return {"path": [], "error": "Graph database not available"}

        cypher = """
        MATCH path = (p1:Prospect {email: $from_email})-[*1..3]-(p2:Prospect {email: $to_email})
        RETURN path
        LIMIT 1
        """

        try:
            results = graph_db.query(
                cypher,
                {
                    "from_email": from_email.lower(),
                    "to_email": to_email.lower(),
                },
            )

            if not results:
                return {
                    "path": [],
                    "message": f"No connection found between {from_email} and {to_email}",
                }

            return {
                "path": results[0].get("path", []),
                "message": "Connection found",
            }
        except Exception as e:
            logger.error(f"Path analysis error: {e}")
            return {"path": [], "error": str(e)}


graph_intelligence = GraphIntelligenceService()
