"""Test environment, set before any test module imports app.config.

get_settings() is lru_cached and bound at import time by the lifted modules,
so these must land before collection imports them (pytest loads conftest first).
"""
import os

import pytest

os.environ.setdefault("CHAMPMAIL_ENV", "development")
# Assigned, not setdefault: the stack's .env can leave these present-but-blank or real,
# and either one must not change what the tests see.
os.environ["CHAMPMAIL_API_KEY"] = ""  # keyless unless a test sets its own
os.environ["INBOXKIT_API_KEY"] = "test-key"
os.environ["INBOXKIT_WORKSPACE_ID"] = "ws_test"
# Blank or missing is a startup error now; the stack's value (if any) is kept.
os.environ["EMAIL_ENCRYPTION_KEY"] = os.environ.get("EMAIL_ENCRYPTION_KEY", "").strip() or "test-encryption-key"

os.environ["TRACKING_SECRET"] = os.environ.get("TRACKING_SECRET", "").strip() or "test-tracking-secret"


@pytest.fixture
def client(monkeypatch):
    """`await client(Session, scenario)`: ASGI client with the API key set, wired to the test Session and real Redis."""
    import httpx
    from app.api.v1 import deps, send as send_api
    from app.config import get_settings
    from app.db.redis import RedisClient
    from app.main import app

    monkeypatch.setattr(get_settings(), "champmail_api_key", "domain-gate-test-key")
    monkeypatch.setenv("EMAIL_ENCRYPTION_KEY", "test-encryption-key")

    async def exercise(Session, scenario):
        async def session_dep():
            async with Session() as session:
                yield session
        app.dependency_overrides[deps.get_session] = session_dep
        app.dependency_overrides[send_api.get_session] = session_dep
        redis = RedisClient()
        monkeypatch.setattr(send_api, "redis_client", redis)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test",
                                         headers={"X-API-Key": "domain-gate-test-key"}) as c:
                await scenario(c)
        finally:
            app.dependency_overrides.clear()
            await redis.close()
    return exercise
