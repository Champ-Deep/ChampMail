"""
ChampMail CLI - Shared Click context object.

Passed through all commands via @click.pass_obj.
Holds DB session factory, graph_db reference, and auth identity.
"""

from __future__ import annotations

import asyncio
from typing import Optional


class CliContext:
    """Shared context carried through every CLI command."""

    def __init__(self, json_output: bool = False):
        self.json_output = json_output
        # Lazy-initialised async resources
        self._session_factory = None
        self._graph_db = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    # ------------------------------------------------------------------
    # Async helpers — CLI commands are sync Click functions; they call
    # run() to execute coroutines on a dedicated event loop.
    # ------------------------------------------------------------------

    def run(self, coro):
        """Run a coroutine from sync Click command."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                raise RuntimeError
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
