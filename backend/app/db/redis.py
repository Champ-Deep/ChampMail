"""Async Redis client (lifted from v2, trimmed to what the webhook ingress needs)."""
from __future__ import annotations

from typing import Optional

import redis.asyncio as aioredis

from app.config import get_settings


class RedisClient:
    def __init__(self) -> None:
        self._client: Optional[aioredis.Redis] = None

    async def _get_client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = aioredis.from_url(
                get_settings().redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


redis_client = RedisClient()