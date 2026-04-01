"""
ChampMail CLI - Unified REPL skin.

Provides branded interactive shell with history, auto-suggest,
completion, and consistent message formatting.
Follows CLI-Anything repl_skin pattern.
"""

from __future__ import annotations

import sys
from typing import Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style

# ChampMail brand colours
BRAND_PRIMARY = "ansibrightcyan"
BRAND_ACCENT = "ansicyan"
BRAND_DIM = "ansidarkgray"

REPL_STYLE = Style.from_dict(
    {
        "prompt": "bold ansicyan",
        "prompt.project": "ansidarkgray",
        "completion-menu.completion": "bg:ansidarkgray ansiwhite",
        "completion-menu.completion.current": "bg:ansicyan ansiblack bold",
        "auto-suggestion": "ansidarkgray italic",
        "bottom-toolbar": "bg:ansidarkgray ansicyan",
    }
)

BANNER = """\
\033[1;36m
  ██████╗██╗  ██╗ █████╗ ███╗   ███╗██████╗ ███╗   ███╗ █████╗ ██╗██╗
 ██╔════╝██║  ██║██╔══██╗████╗ ████║██╔══██╗████╗ ████║██╔══██╗██║██║
 ██║     ███████║███████║██╔████╔██║██████╔╝██╔████╔██║███████║██║██║
 ██║     ██╔══██║██╔══██║██║╚██╔╝██║██╔═══╝ ██║╚██╔╝██║██╔══██║██║██║
 ╚██████╗██║  ██║██║  ██║██║ ╚═╝ ██║██║     ██║ ╚═╝ ██║██║  ██║██║███████╗
  ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝     ╚═╝     ╚═╝╚═╝  ╚═╝╚═╝╚══════╝
\033[0m\033[36m  Enterprise Cold-Email Outreach Platform — CLI Interface\033[0m
\033[2m  Type  help  for commands,  exit  to quit.\033[0m
"""


def print_banner() -> None:
    print(BANNER)


def print_success(msg: str) -> None:
    print(f"\033[1;32m✓\033[0m  {msg}")


def print_error(msg: str) -> None:
    print(f"\033[1;31m✗\033[0m  {msg}", file=sys.stderr)


def print_warning(msg: str) -> None:
    print(f"\033[1;33m⚠\033[0m  {msg}")


def print_info(msg: str) -> None:
    print(f"\033[1;36m→\033[0m  {msg}")


def print_kv(key: str, value: str, width: int = 22) -> None:
    print(f"  \033[36m{key:<{width}}\033[0m {value}")


def print_section(title: str) -> None:
    bar = "─" * (len(title) + 4)
    print(f"\n\033[1;36m┌{bar}┐\033[0m")
    print(f"\033[1;36m│  {title}  │\033[0m")
    print(f"\033[1;36m└{bar}┘\033[0m")


def print_table(headers: list[str], rows: list[list[str]]) -> None:
    """Simple ASCII table."""
    if not rows:
        print_warning("No results.")
        return
    col_widths = [max(len(str(h)), max((len(str(r[i])) for r in rows), default=0)) for i, h in enumerate(headers)]
    sep = "  ".join("─" * w for w in col_widths)
    header_line = "  ".join(f"\033[1;36m{h:<{w}}\033[0m" for h, w in zip(headers, col_widths))
    print(f"\n  {header_line}")
    print(f"  {sep}")
    for row in rows:
        print("  " + "  ".join(f"{str(v):<{w}}" for v, w in zip(row, col_widths)))
    print()


def make_prompt_session(history_file: Optional[str] = None) -> PromptSession:
    history = FileHistory(history_file) if history_file else None
    return PromptSession(
        history=history,
        auto_suggest=AutoSuggestFromHistory(),
        style=REPL_STYLE,
        mouse_support=False,
    )


def get_prompt_html(project_name: Optional[str] = None) -> HTML:
    if project_name:
        return HTML(f'<prompt>champmail</prompt><prompt.project> ({project_name})</prompt.project> <prompt>❯</prompt> ')
    return HTML('<prompt>champmail ❯ </prompt>')
