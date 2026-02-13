"""
Redis client for caching and Celery broker.
Provides async Redis connection with connection pooling.
"""

from __future__ import annotations

import json
from typing import Optional

import redis.asyncio as aioredis

from app.core.config import settings


class RedisClient:
    """Async Redis client wrapper with connection pooling."""

    def __init__(self):
        self._client: Optional[aioredis.Redis] = None

    async def _get_client(self) -> aioredis.Redis:
        """Get or create Redis client with connection pool."""
        if self._client is None:
            self._client = aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
            )
        return self._client

    async def get(self, key: str) -> Optional[str]:
        """Get value by key."""
        client = await self._get_client()
        return await client.get(key)

    async def set(self, key: str, value: str, ex: Optional[int] = None):
        """Set key-value pair with optional TTL."""
        client = await self._get_client()
        await client.set(key, value, ex=ex)

    async def setex(self, key: str, seconds: int, value: str):
        """Set key-value with expiration in seconds."""
        client = await self._get_client()
        await client.setex(key, seconds, value)

    async def delete(self, key: str):
        """Delete a key."""
        client = await self._get_client()
        await client.delete(key)

    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        client = await self._get_client()
        return bool(await client.exists(key))

    async def incr(self, key: str) -> int:
        """Increment key value."""
        client = await self._get_client()
        return await client.incr(key)

    async def expire(self, key: str, seconds: int):
        """Set TTL on a key."""
        client = await self._get_client()
        await client.expire(key, seconds)

    async def get_json(self, key: str) -> Optional[dict]:
        """Get and deserialize JSON value."""
        raw = await self.get(key)
        if raw:
            return json.loads(raw)
        return None

    async def set_json(self, key: str, value: dict, ex: Optional[int] = None):
        """Serialize and set JSON value."""
        await self.set(key, json.dumps(value), ex=ex)

    async def close(self):
        """Close the Redis connection."""
        if self._client:
            await self._client.close()
            self._client = None

    async def ping(self) -> bool:
        """Check Redis connectivity."""
        try:
            client = await self._get_client()
            return await client.ping()
        except Exception:
            return False


# Singleton instance
redis_client = RedisClient()
