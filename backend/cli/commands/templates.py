"""
champmail templates — Email template commands.

  templates list
  templates get    TEMPLATE_ID
  templates create --name NAME --subject SUBJECT --html-file body.html
  templates delete TEMPLATE_ID
  templates preview TEMPLATE_ID [--output out.html]
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from cli.context import CliContext
from cli.repl_skin import print_error, print_info, print_kv, print_section, print_success, print_table
from cli.session import get_user_id, is_logged_in


def _require_login(obj):
    if not is_logged_in():
        print_error("Not logged in.  Run: champmail auth login")
        raise SystemExit(1)


@click.group()
def templates() -> None:
    """Email template management."""


@templates.command("list")
@click.option("--limit", default=50, show_default=True)
@click.pass_obj
def list_templates(obj, limit) -> None:
    """List email templates."""
    _require_login(obj)

    # template_service is in-memory (not async/DB-backed)
    from app.services.templates import template_service

    rows = template_service.list_templates(owner_id=get_user_id(), limit=limit)
    data = [
        {
            "id": t.id,
            "name": t.name,
            "subject": t.subject,
            "variables": ", ".join(t.variables),
            "created_at": t.created_at.isoformat()[:10] if t.created_at else "",
        }
        for t in rows
    ]

    if obj.json_output:
        print(json.dumps({"ok": True, "templates": data, "total": len(data)}))
    else:
        print_table(
            ["ID", "Name", "Subject", "Variables", "Created"],
            [[d["id"][:8] + "…", d["name"][:28], d["subject"][:35], d["variables"][:25], d["created_at"]] for d in data],
        )


@templates.command("get")
@click.argument("template_id")
@click.pass_obj
def get_template(obj, template_id) -> None:
    """Show template details."""
    _require_login(obj)

    from app.services.templates import template_service

    t = template_service.get_template(template_id)
    if not t:
        if obj.json_output:
            print(json.dumps({"ok": False, "error": "Template not found"}))
        else:
            print_error("Template not found.")
        raise SystemExit(1)

    preview = (t.html_content or t.mjml_content or "")
    preview = preview[:300] + "…" if len(preview) > 300 else preview

    if obj.json_output:
        print(json.dumps({
            "ok": True,
            "id": t.id, "name": t.name, "subject": t.subject,
            "variables": t.variables,
            "html_preview": preview,
            "created_at": t.created_at.isoformat() if t.created_at else "",
        }))
    else:
        print_section(f"Template: {t.name}")
        print_kv("ID", t.id)
        print_kv("Subject", t.subject)
        print_kv("Variables", ", ".join(t.variables) or "(none)")
        print_kv("Created", t.created_at.isoformat()[:10] if t.created_at else "")
        print_info("\nHTML preview (truncated):")
        print(f"  {preview}")


@templates.command("create")
@click.option("--name", required=True)
@click.option("--subject", required=True)
@click.option("--html-file", "html_file", default=None, type=click.Path(exists=True),
              help="Path to HTML/MJML body file.")
@click.option("--body", default=None, help="HTML body as inline string.")
@click.pass_obj
def create_template(obj, name, subject, html_file, body) -> None:
    """Create a new email template from an HTML file or inline body."""
    _require_login(obj)

    if not html_file and not body:
        print_error("Provide --html-file or --body.")
        raise SystemExit(1)

    content = body if body else Path(html_file).read_text()

    from app.services.templates import template_service

    t = template_service.create_template(
        name=name,
        subject=subject,
        mjml_content=content,
        owner_id=get_user_id(),
    )

    if obj.json_output:
        print(json.dumps({"ok": True, "id": t.id, "name": t.name, "variables": t.variables}))
    else:
        print_success(f"Template created: {t.name}  id={t.id}")
        if t.variables:
            print_info(f"  Variables detected: {', '.join(t.variables)}")


@templates.command("delete")
@click.argument("template_id")
@click.option("--yes", is_flag=True, default=False)
@click.pass_obj
def delete_template(obj, template_id, yes) -> None:
    """Delete a template."""
    _require_login(obj)
    if not yes:
        click.confirm(f"Delete template {template_id}?", abort=True)

    from app.services.templates import template_service

    ok = template_service.delete_template(template_id)
    if not ok:
        print_error("Template not found.")
        raise SystemExit(1)

    if obj.json_output:
        print(json.dumps({"ok": True, "template_id": template_id}))
    else:
        print_success(f"Template {template_id} deleted.")


@templates.command("preview")
@click.argument("template_id")
@click.option("--output", "-o", default=None, help="Save rendered HTML to file.")
@click.pass_obj
def preview_template(obj, template_id, output) -> None:
    """Render template preview (optionally save to HTML file)."""
    _require_login(obj)

    from app.services.templates import template_service

    t = template_service.get_template(template_id)
    if not t:
        print_error("Template not found.")
        raise SystemExit(1)

    html = t.html_content or t.mjml_content or ""

    if output:
        Path(output).write_text(html)
        print_success(f"Preview saved to {output}")
    elif obj.json_output:
        print(json.dumps({"ok": True, "id": t.id, "html": html}))
    else:
        print_section(f"Preview: {t.name}")
        print(html[:2000])
        if len(html) > 2000:
            print_info(f"  … ({len(html) - 2000} more chars) — use --output to save full HTML")
