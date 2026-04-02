"""
ChampMail CLI — Main entry point.

Usage:
    champmail [--json] COMMAND [ARGS]
    champmail repl          # Interactive REPL

Architecture (CLI-Anything pattern):
- Click for command groups / one-shot execution
- prompt_toolkit for interactive REPL
- Direct service-layer invocation (no HTTP round-trip)
- --json flag for machine-readable output (agent-native)
- Session state in ~/.champmail/session.json
"""

from __future__ import annotations

import json
import logging
import os
import shlex
import sys

import click

# Suppress noisy SQL / third-party INFO logs in CLI mode.
# Must be set BEFORE app.db.postgres is imported (it reads settings at import time).
os.environ.setdefault("DEBUG", "false")

logging.basicConfig(level=logging.WARNING)
for noisy in ("sqlalchemy", "sqlalchemy.engine", "sqlalchemy.pool",
              "asyncio", "httpx", "aiosqlite", "alembic"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

from cli.context import CliContext
from cli.config_store import apply_to_runtime
# Apply any stored admin config (SMTP, IMAP, AI key) to os.environ at startup
# so all commands automatically use the user's saved credentials.
apply_to_runtime()

from cli.repl_skin import (
    get_prompt_html,
    make_prompt_session,
    print_banner,
    print_error,
    print_info,
)
from cli.session import SESSION_DIR, HISTORY_FILE

# ── command groups ────────────────────────────────────────────────────────────
from cli.commands.auth import auth
from cli.commands.campaigns import campaigns
from cli.commands.prospects import prospects
from cli.commands.sequences import sequences
from cli.commands.domains import domains
from cli.commands.templates import templates
from cli.commands.analytics import analytics
from cli.commands.admin import admin
from cli.commands.health import health
from cli.commands.send import send
from cli.commands.tunnel import tunnel
from cli.commands.outreach import outreach
from cli.commands.setup import setup
from cli.commands.chat import chat


# ─────────────────────────────────────────────────────────────────────────────
# Root group
# ─────────────────────────────────────────────────────────────────────────────


@click.group()
@click.option("--json", "json_output", is_flag=True, default=False,
              help="Emit machine-readable JSON (agent-native mode).")
@click.version_option("0.1.0", prog_name="champmail")
@click.pass_context
def cli(ctx: click.Context, json_output: bool) -> None:
    """ChampMail — AI-powered cold-email outreach platform CLI.

    Run  champmail repl  for an interactive shell.

    Authenticate first:

        champmail auth login --email admin@champions.dev --password admin123
    """
    ctx.ensure_object(CliContext)
    ctx.obj.json_output = json_output


# ── attach sub-groups ─────────────────────────────────────────────────────────
cli.add_command(auth)
cli.add_command(campaigns)
cli.add_command(prospects)
cli.add_command(sequences)
cli.add_command(domains)
cli.add_command(templates)
cli.add_command(analytics)
cli.add_command(admin)
cli.add_command(health)
cli.add_command(send)
cli.add_command(tunnel)
cli.add_command(outreach)
cli.add_command(setup)
cli.add_command(chat)


# ─────────────────────────────────────────────────────────────────────────────
# Interactive REPL
# ─────────────────────────────────────────────────────────────────────────────


@cli.command("repl")
@click.pass_obj
def repl(obj: CliContext) -> None:
    """Launch the interactive ChampMail REPL."""
    from cli.session import get_email

    print_banner()
    print_info(f"Session directory: {SESSION_DIR}")

    session = make_prompt_session(str(SESSION_DIR / "history"))

    while True:
        project_label = get_email()
        try:
            raw = session.prompt(get_prompt_html(project_label))
        except KeyboardInterrupt:
            print()
            continue
        except EOFError:
            print_info("Goodbye.")
            break

        text = raw.strip()
        if not text:
            continue
        if text.lower() in ("exit", "quit", "q"):
            print_info("Goodbye.")
            break

        # Parse and dispatch through Click
        try:
            args = shlex.split(text)
        except ValueError as e:
            print_error(f"Parse error: {e}")
            continue

        try:
            # standalone_mode=False → Click won't sys.exit on --help
            cli.main(args=args, standalone_mode=False, obj=obj)
        except click.exceptions.Exit:
            pass
        except click.exceptions.Abort:
            print()
        except click.UsageError as e:
            print_error(str(e))
        except SystemExit:
            pass
        except Exception as e:
            print_error(f"Error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
