"""
Template management service.

Handles email template storage, MJML compilation, and variable substitution.
"""

from __future__ import annotations

import logging
import re
import subprocess
import json
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional
from uuid import uuid4

from app.db.falkordb import graph_db

logger = logging.getLogger(__name__)


@dataclass
class EmailTemplate:
    """Email template data structure."""
    id: str
    name: str
    subject: str
    mjml_content: str
    html_content: Optional[str] = None
    text_content: Optional[str] = None
    variables: list[str] = field(default_factory=list)
    owner_id: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


def compile_mjml(mjml_content: str) -> tuple[str, Optional[str]]:
    """
    Compile MJML to HTML.

    Tries multiple methods:
    1. mjml npm package via subprocess
    2. Fall back to returning MJML as-is (for development)

    Args:
        mjml_content: MJML markup string

    Returns:
        Tuple of (html_content, error_message)
    """
    try:
        # Try using mjml CLI (requires: npm install -g mjml)
        result = subprocess.run(
            ['mjml', '-s', '-i'],
            input=mjml_content.encode('utf-8'),
            capture_output=True,
            timeout=30,
        )

        if result.returncode == 0:
            return result.stdout.decode('utf-8'), None
        else:
            error = result.stderr.decode('utf-8')
            return None, f"MJML compilation error: {error}"

    except FileNotFoundError:
        # mjml CLI not installed, try node directly
        try:
            node_script = """
            const mjml = require('mjml');
            let input = '';
            process.stdin.on('data', d => input += d);
            process.stdin.on('end', () => {
                const result = mjml(input);
                if (result.errors.length) {
                    console.error(JSON.stringify(result.errors));
                    process.exit(1);
                }
                console.log(result.html);
            });
            """
            result = subprocess.run(
                ['node', '-e', node_script],
                input=mjml_content.encode('utf-8'),
                capture_output=True,
                timeout=30,
            )

            if result.returncode == 0:
                return result.stdout.decode('utf-8'), None
            else:
                return None, "Node MJML compilation failed"

        except FileNotFoundError:
            # No mjml or node available
            # Return a basic HTML wrapper for development
            return _fallback_html_wrap(mjml_content), "MJML compiler not available - using fallback"

    except subprocess.TimeoutExpired:
        return None, "MJML compilation timed out"
    except Exception as e:
        return None, f"MJML compilation error: {str(e)}"


def _fallback_html_wrap(mjml_content: str) -> str:
    """
    Create basic HTML from MJML for development when mjml is not installed.

    This is a simple extraction - not a full MJML compiler.
    """
    # Try to extract content from mj-text elements
    html_parts = []

    # Simple regex extraction of text content
    text_matches = re.findall(r'<mj-text[^>]*>(.*?)</mj-text>', mjml_content, re.DOTALL)
    for match in text_matches:
        html_parts.append(f'<p>{match.strip()}</p>')

    # If no mj-text found, wrap the whole thing
    if not html_parts:
        html_parts = [f'<pre>{mjml_content}</pre>']

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; }}
        p {{ margin: 10px 0; }}
    </style>
</head>
<body>
    {''.join(html_parts)}
</body>
</html>"""


def extract_variables(content: str) -> list[str]:
    """
    Extract variable placeholders from template content.

    Supports formats:
    - {{variable_name}}
    - {{first_name}}
    - {{company.name}}

    Args:
        content: Template content with variables

    Returns:
        List of unique variable names
    """
    pattern = r'\{\{([a-zA-Z_][a-zA-Z0-9_\.]*)\}\}'
    matches = re.findall(pattern, content)
    return list(set(matches))


def substitute_variables(content: str, variables: dict[str, str]) -> str:
    """
    Replace variable placeholders with actual values.

    Args:
        content: Template content with {{variable}} placeholders
        variables: Dictionary mapping variable names to values

    Returns:
        Content with variables substituted
    """
    def replace_var(match):
        var_name = match.group(1)
        return variables.get(var_name, match.group(0))

    pattern = r'\{\{([a-zA-Z_][a-zA-Z0-9_\.]*)\}\}'
    return re.sub(pattern, replace_var, content)


class TemplateService:
    """Service for managing email templates."""

    def create_template(
        self,
        name: str,
        subject: str,
        mjml_content: str,
        owner_id: str,
        compile_html: bool = True,
    ) -> EmailTemplate:
        """
        Create a new email template.

        Args:
            name: Template name
            subject: Email subject line (supports variables)
            mjml_content: MJML markup
            owner_id: ID of the template owner
            compile_html: Whether to compile MJML to HTML immediately

        Returns:
            Created template
        """
        template_id = str(uuid4())

        # Extract variables from both subject and content
        variables = extract_variables(subject) + extract_variables(mjml_content)
        variables = list(set(variables))

        # Compile MJML if requested
        html_content = None
        if compile_html:
            html_content, error = compile_mjml(mjml_content)
            if error:
                logger.warning("Template compilation warning: %s", error)

        # Store in FalkorDB
        try:
            query = """
                CREATE (t:EmailTemplate {
                    id: $id,
                    name: $name,
                    subject: $subject,
                    mjml_content: $mjml_content,
                    html_content: $html_content,
                    variables: $variables,
                    owner_id: $owner_id,
                    created_at: datetime(),
                    updated_at: datetime()
                })
                RETURN t
            """
            graph_db.query(query, {
                'id': template_id,
                'name': name,
                'subject': subject,
                'mjml_content': mjml_content,
                'html_content': html_content or '',
                'variables': variables,
                'owner_id': owner_id,
            })
        except Exception as e:
            logger.error("FalkorDB error (template may only exist in memory): %s", e)

        return EmailTemplate(
            id=template_id,
            name=name,
            subject=subject,
            mjml_content=mjml_content,
            html_content=html_content,
            variables=variables,
            owner_id=owner_id,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

    def get_template(self, template_id: str) -> Optional[EmailTemplate]:
        """Get template by ID."""
        try:
            query = """
                MATCH (t:EmailTemplate {id: $id})
                RETURN t
            """
            result = graph_db.query(query, {'id': template_id})
            if not result:
                return None

            t = result[0].get('t', {}).get('properties', {})
            return EmailTemplate(
                id=t.get('id', ''),
                name=t.get('name', ''),
                subject=t.get('subject', ''),
                mjml_content=t.get('mjml_content', ''),
                html_content=t.get('html_content'),
                variables=t.get('variables', []),
                owner_id=t.get('owner_id', ''),
            )
        except Exception as e:
            logger.error("Error getting template: %s", e)
            return None

    def list_templates(
        self,
        owner_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[EmailTemplate]:
        """List templates with optional filtering."""
        try:
            if owner_id:
                query = """
                    MATCH (t:EmailTemplate {owner_id: $owner_id})
                    RETURN t
                    ORDER BY t.created_at DESC
                    SKIP $offset
                    LIMIT $limit
                """
                params = {'owner_id': owner_id, 'offset': offset, 'limit': limit}
            else:
                query = """
                    MATCH (t:EmailTemplate)
                    RETURN t
                    ORDER BY t.created_at DESC
                    SKIP $offset
                    LIMIT $limit
                """
                params = {'offset': offset, 'limit': limit}

            results = graph_db.query(query, params)

            templates = []
            for row in results:
                t = row.get('t', {}).get('properties', {})
                templates.append(EmailTemplate(
                    id=t.get('id', ''),
                    name=t.get('name', ''),
                    subject=t.get('subject', ''),
                    mjml_content=t.get('mjml_content', ''),
                    html_content=t.get('html_content'),
                    variables=t.get('variables', []),
                    owner_id=t.get('owner_id', ''),
                ))
            return templates
        except Exception as e:
            logger.error("Error listing templates: %s", e)
            return []

    def update_template(
        self,
        template_id: str,
        name: Optional[str] = None,
        subject: Optional[str] = None,
        mjml_content: Optional[str] = None,
        recompile: bool = True,
    ) -> Optional[EmailTemplate]:
        """Update an existing template."""
        try:
            # Build update query dynamically
            updates = ['t.updated_at = datetime()']
            params = {'id': template_id}

            if name is not None:
                updates.append('t.name = $name')
                params['name'] = name

            if subject is not None:
                updates.append('t.subject = $subject')
                params['subject'] = subject

            if mjml_content is not None:
                updates.append('t.mjml_content = $mjml_content')
                params['mjml_content'] = mjml_content

                # Extract variables from new content
                variables = extract_variables(mjml_content)
                if subject:
                    variables += extract_variables(subject)
                variables = list(set(variables))
                updates.append('t.variables = $variables')
                params['variables'] = variables

                # Recompile if requested
                if recompile:
                    html_content, _ = compile_mjml(mjml_content)
                    if html_content:
                        updates.append('t.html_content = $html_content')
                        params['html_content'] = html_content

            query = f"""
                MATCH (t:EmailTemplate {{id: $id}})
                SET {', '.join(updates)}
                RETURN t
            """
            result = graph_db.query(query, params)

            if not result:
                return None

            return self.get_template(template_id)
        except Exception as e:
            logger.error("Error updating template: %s", e)
            return None

    def delete_template(self, template_id: str) -> bool:
        """Delete a template by ID."""
        try:
            query = """
                MATCH (t:EmailTemplate {id: $id})
                DELETE t
                RETURN count(t) as deleted
            """
            result = graph_db.query(query, {'id': template_id})
            return result and result[0].get('deleted', 0) > 0
        except Exception as e:
            logger.error("Error deleting template: %s", e)
            return False

    def render_preview(
        self,
        template_id: str,
        variables: Optional[dict[str, str]] = None,
    ) -> Optional[dict[str, str]]:
        """
        Render a template preview with sample variables.

        Args:
            template_id: Template ID
            variables: Variable values to substitute

        Returns:
            Dict with 'subject' and 'html' keys, or None if template not found
        """
        template = self.get_template(template_id)
        if not template:
            return None

        # Default sample variables
        sample_vars = {
            'first_name': 'John',
            'last_name': 'Doe',
            'company': 'Acme Inc',
            'title': 'CEO',
            'email': 'john@example.com',
            'unsubscribe_link': '#unsubscribe',
        }

        if variables:
            sample_vars.update(variables)

        subject = substitute_variables(template.subject, sample_vars)
        html = template.html_content or template.mjml_content

        if html:
            html = substitute_variables(html, sample_vars)

        return {
            'subject': subject,
            'html': html,
            'variables_used': template.variables,
        }


# Global service instance
template_service = TemplateService()
