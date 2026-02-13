"""
Thesys C1 Generative UI service.
Handles all interactions with the Thesys C1 API for generating
interactive UI components from natural language.
"""

from __future__ import annotations

import logging
from typing import AsyncGenerator, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class ThesysC1Service:
    """Client for Thesys C1 Generative UI API.

    Uses the OpenAI-compatible Python SDK since C1 follows the
    OpenAI Chat Completions API format.
    """

    def __init__(self):
        self._client = None

    @property
    def client(self):
        """Lazy-init AsyncOpenAI client."""
        if self._client is None and settings.thesys_api_key:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(
                api_key=settings.thesys_api_key,
                base_url=settings.thesys_base_url,
            )
        return self._client

    @property
    def is_configured(self) -> bool:
        """Check if Thesys API key is configured."""
        return bool(settings.thesys_api_key)

    async def chat_stream(self, messages: list[dict]) -> AsyncGenerator[str, None]:
        """Yield content chunks from C1 streaming response."""
        if not self.client:
            raise RuntimeError("Thesys API key not configured")

        response = await self.client.chat.completions.create(
            model=settings.thesys_model,
            messages=messages,
            stream=True,
            max_tokens=settings.thesys_max_tokens,
        )
        async for chunk in response:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

    async def chat(self, messages: list[dict]) -> str:
        """Non-streaming completion, returns full content string."""
        if not self.client:
            raise RuntimeError("Thesys API key not configured")

        response = await self.client.chat.completions.create(
            model=settings.thesys_model,
            messages=messages,
            stream=False,
            max_tokens=settings.thesys_max_tokens,
        )
        return response.choices[0].message.content or ""


# Singleton
thesys_service = ThesysC1Service()
