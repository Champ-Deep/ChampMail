"""
Template management service.

Handles email template storage, MJML compilation, and variable substitution.
Templates are stored in-memory (backed by ChampGraph for persistence hints).
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
    """Compile MJML to HTML."""
    try:
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
            return _fallback_html_wrap(mjml_content), "MJML compiler not available - using fallback"
    except subprocess.TimeoutExpired:
        return None, "MJML compilation timed out"
    except Exception as e:
        return None, f"MJML compilation error: {str(e)}"


def _fallback_html_wrap(mjml_content: str) -> str:
    """Create basic HTML from MJML for development."""
    html_parts = []
    text_matches = re.findall(r'<mj-text[^>]*>(.*?)</mj-text>', mjml_content, re.DOTALL)
    for match in text_matches:
        html_parts.append(f'<p>{match.strip()}</p>')
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
    """Extract variable placeholders from template content."""
    pattern = r'\{\{([a-zA-Z_][a-zA-Z0-9_\.]*)\}\}'
    matches = re.findall(pattern, content)
    return list(set(matches))


def substitute_variables(content: str, variables: dict[str, str]) -> str:
    """Replace variable placeholders with actual values."""
    def replace_var(match):
        var_name = match.group(1)
        return variables.get(var_name, match.group(0))
    pattern = r'\{\{([a-zA-Z_][a-zA-Z0-9_\.]*)\}\}'
    return re.sub(pattern, replace_var, content)


class TemplateService:
    """Service for managing email templates (in-memory store)."""

    def __init__(self):
        self._templates: dict[str, EmailTemplate] = {}

    def create_template(
        self,
        name: str,
        subject: str,
        mjml_content: str,
        owner_id: str,
        compile_html: bool = True,
    ) -> EmailTemplate:
        """Create a new email template."""
        template_id = str(uuid4())

        variables = extract_variables(subject) + extract_variables(mjml_content)
        variables = list(set(variables))

        html_content = None
        if compile_html:
            html_content, error = compile_mjml(mjml_content)
            if error:
                logger.warning("Template compilation warning: %s", error)

        template = EmailTemplate(
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

        self._templates[template_id] = template
        return template

    def get_template(self, template_id: str) -> Optional[EmailTemplate]:
        """Get template by ID."""
        return self._templates.get(template_id)

    def list_templates(
        self,
        owner_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[EmailTemplate]:
        """List templates with optional filtering."""
        templates = list(self._templates.values())
        if owner_id:
            templates = [t for t in templates if t.owner_id == owner_id]
        templates.sort(key=lambda t: t.created_at or datetime.min, reverse=True)
        return templates[offset:offset + limit]

    def update_template(
        self,
        template_id: str,
        name: Optional[str] = None,
        subject: Optional[str] = None,
        mjml_content: Optional[str] = None,
        recompile: bool = True,
    ) -> Optional[EmailTemplate]:
        """Update an existing template."""
        template = self._templates.get(template_id)
        if not template:
            return None

        if name is not None:
            template.name = name
        if subject is not None:
            template.subject = subject
        if mjml_content is not None:
            template.mjml_content = mjml_content
            template.variables = extract_variables(mjml_content)
            if subject:
                template.variables += extract_variables(subject)
            template.variables = list(set(template.variables))
            if recompile:
                html_content, _ = compile_mjml(mjml_content)
                if html_content:
                    template.html_content = html_content

        template.updated_at = datetime.now()
        return template

    def delete_template(self, template_id: str) -> bool:
        """Delete a template by ID."""
        if template_id in self._templates:
            del self._templates[template_id]
            return True
        return False

    def render_preview(
        self,
        template_id: str,
        variables: Optional[dict[str, str]] = None,
    ) -> Optional[dict[str, str]]:
        """Render a template preview with sample variables."""
        template = self.get_template(template_id)
        if not template:
            return None

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
