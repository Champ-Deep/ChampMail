"""
FalkorDB connection and graph operations.
Provides the knowledge graph layer for the email engine.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, Optional, Dict, List

from falkordb import FalkorDB

from app.core.config import settings


class GraphDatabase:
    """FalkorDB graph database client."""

    def __init__(self):
        self._client: Optional[FalkorDB] = None
        self._graph = None

    def connect(self) -> None:
        """Establish connection to FalkorDB."""
        self._client = FalkorDB(
            host=settings.falkordb_host,
            port=settings.falkordb_port,
            password=settings.falkordb_password or None,
        )
        self._graph = self._client.select_graph(settings.falkordb_database)

    def disconnect(self) -> None:
        """Close FalkorDB connection."""
        # FalkorDB client handles connection pooling internally
        self._client = None
        self._graph = None

    @property
    def graph(self):
        """Get the graph instance."""
        if self._graph is None:
            self.connect()
        return self._graph

    def query(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict]:
        """
        Execute a Cypher query and return results.

        Args:
            cypher: Cypher query string
            params: Optional query parameters

        Returns:
            List of result dictionaries
        """
        result = self.graph.query(cypher, params or {})
        return self._parse_result(result)

    def _parse_result(self, result) -> list[dict]:
        """Parse FalkorDB result into list of dictionaries."""
        if not result.result_set:
            return []

        # Get column headers
        headers = result.header if hasattr(result, 'header') else []

        # Convert each row to dict
        rows = []
        for row in result.result_set:
            if headers:
                row_dict = {}
                for i, header in enumerate(headers):
                    value = row[i] if i < len(row) else None
                    # Handle Node objects
                    if hasattr(value, 'properties'):
                        row_dict[header] = {
                            'id': value.id if hasattr(value, 'id') else None,
                            'labels': list(value.labels) if hasattr(value, 'labels') else [],
                            'properties': dict(value.properties) if hasattr(value, 'properties') else {},
                        }
                    else:
                        row_dict[header] = value
                rows.append(row_dict)
            else:
                rows.append({'result': row})

        return rows

    def create_prospect(
        self,
        email: str,
        first_name: str = "",
        last_name: str = "",
        title: str = "",
        phone: str = "",
        linkedin_url: str = "",
        **extra_fields,
    ) -> dict:
        """
        Create a Prospect node in the graph.

        Returns:
            Created prospect data
        """
        # Build properties dynamically
        props = {
            'email': email.lower(),
            'first_name': first_name,
            'last_name': last_name,
            'title': title,
            'phone': phone,
            'linkedin_url': linkedin_url,
            'created_at': 'datetime()',
        }
        props.update(extra_fields)

        # Remove empty values
        props = {k: v for k, v in props.items() if v}

        # Build Cypher query
        prop_string = ', '.join(f'{k}: ${k}' for k in props.keys() if k != 'created_at')
        if 'created_at' in props:
            prop_string += ', created_at: datetime()'
            del props['created_at']

        query = f"""
            CREATE (p:Prospect {{{prop_string}}})
            RETURN p
        """

        result = self.query(query, props)
        return result[0] if result else {}

    def get_prospect_by_email(self, email: str) -> dict | None:
        """Get prospect by email address."""
        query = """
            MATCH (p:Prospect {email: $email})
            OPTIONAL MATCH (p)-[r:WORKS_AT]->(c:Company)
            RETURN p, r, c
        """
        result = self.query(query, {'email': email.lower()})
        return result[0] if result else None

    def get_prospect_by_id(self, prospect_id: int) -> dict | None:
        """Get prospect by internal ID."""
        query = """
            MATCH (p:Prospect)
            WHERE id(p) = $id
            OPTIONAL MATCH (p)-[r:WORKS_AT]->(c:Company)
            RETURN p, r, c
        """
        result = self.query(query, {'id': prospect_id})
        return result[0] if result else None

    def create_company(
        self,
        name: str,
        domain: str,
        industry: str = "",
        employee_count: int = 0,
        **extra_fields,
    ) -> dict:
        """Create a Company node in the graph."""
        props = {
            'name': name,
            'domain': domain.lower(),
            'industry': industry,
            'employee_count': employee_count,
        }
        props.update(extra_fields)
        props = {k: v for k, v in props.items() if v}

        prop_string = ', '.join(f'{k}: ${k}' for k in props.keys())
        query = f"""
            MERGE (c:Company {{domain: $domain}})
            ON CREATE SET {', '.join(f'c.{k} = ${k}' for k in props.keys())}
            RETURN c
        """

        result = self.query(query, props)
        return result[0] if result else {}

    def link_prospect_to_company(
        self,
        prospect_email: str,
        company_domain: str,
        title: str = "",
        is_current: bool = True,
    ) -> dict:
        """Create WORKS_AT relationship between Prospect and Company."""
        query = """
            MATCH (p:Prospect {email: $email})
            MATCH (c:Company {domain: $domain})
            MERGE (p)-[r:WORKS_AT]->(c)
            SET r.title = $title, r.is_current = $is_current
            RETURN p, r, c
        """
        result = self.query(query, {
            'email': prospect_email.lower(),
            'domain': company_domain.lower(),
            'title': title,
            'is_current': is_current,
        })
        return result[0] if result else {}

    def search_prospects(
        self,
        query_text: str = "",
        industry: str = "",
        limit: int = 50,
        skip: int = 0,
    ) -> list[dict]:
        """Search prospects with optional filters."""
        conditions = []
        params = {'limit': limit, 'skip': skip}

        if query_text:
            conditions.append(
                "(p.first_name CONTAINS $query OR p.last_name CONTAINS $query OR p.email CONTAINS $query)"
            )
            params['query'] = query_text.lower()

        if industry:
            conditions.append("c.industry = $industry")
            params['industry'] = industry

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        cypher = f"""
            MATCH (p:Prospect)
            OPTIONAL MATCH (p)-[r:WORKS_AT]->(c:Company)
            {where_clause}
            RETURN p, r, c
            ORDER BY p.created_at DESC
            SKIP $skip
            LIMIT $limit
        """

        return self.query(cypher, params)

    def create_sequence(
        self,
        name: str,
        owner_id: str,
        steps_count: int = 0,
    ) -> dict:
        """Create an email Sequence node."""
        query = """
            CREATE (s:Sequence {
                name: $name,
                owner_id: $owner_id,
                steps_count: $steps_count,
                status: 'draft',
                created_at: datetime()
            })
            RETURN s
        """
        result = self.query(query, {
            'name': name,
            'owner_id': owner_id,
            'steps_count': steps_count,
        })
        return result[0] if result else {}

    def enroll_prospect_in_sequence(
        self,
        prospect_email: str,
        sequence_id: int,
    ) -> dict:
        """Enroll a prospect in a sequence."""
        query = """
            MATCH (p:Prospect {email: $email})
            MATCH (s:Sequence)
            WHERE id(s) = $sequence_id
            MERGE (p)-[r:ENROLLED_IN]->(s)
            SET r.enrolled_at = datetime(),
                r.status = 'active',
                r.current_step = 1
            RETURN p, r, s
        """
        result = self.query(query, {
            'email': prospect_email.lower(),
            'sequence_id': sequence_id,
        })
        return result[0] if result else {}

    def record_email_sent(
        self,
        prospect_email: str,
        sequence_id: int,
        step_number: int,
        subject: str,
        body_hash: str,
    ) -> dict:
        """Record an email sent to a prospect."""
        query = """
            MATCH (p:Prospect {email: $email})
            CREATE (e:Email {
                subject: $subject,
                body_hash: $body_hash,
                sent_at: datetime(),
                step_number: $step_number,
                sequence_id: $sequence_id
            })
            CREATE (p)-[:RECEIVED]->(e)
            RETURN e
        """
        result = self.query(query, {
            'email': prospect_email.lower(),
            'subject': subject,
            'body_hash': body_hash,
            'step_number': step_number,
            'sequence_id': sequence_id,
        })
        return result[0] if result else {}


# Global database instance
graph_db = GraphDatabase()


@asynccontextmanager
async def get_graph_db():
    """Dependency for getting graph database connection."""
    try:
        if graph_db._client is None:
            graph_db.connect()
        yield graph_db
    finally:
        pass  # Connection pooling handles cleanup


def init_graph_db() -> bool:
    """Initialize graph database connection on startup.

    Returns:
        True if connection succeeded, False otherwise.
    """
    try:
        graph_db.connect()
        return True
    except Exception as e:
        print(f"Warning: Could not connect to FalkorDB: {e}")
        print("Running in degraded mode - graph features disabled")
        return False


def close_graph_db():
    """Close graph database connection on shutdown."""
    graph_db.disconnect()
