import hmac
from typing import AsyncIterator, Optional

from fastapi import Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.postgres import async_session_maker


async def get_session() -> AsyncIterator[AsyncSession]:
    async with async_session_maker() as session:
        yield session


def require_api_key(x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")) -> None:
    """X-API-Key, as Harbinger's ChampMail client sends it. Empty key is allowed in development only."""
    s = get_settings()
    if not s.champmail_api_key:
        if s.champmail_env.strip().lower() == "development":
            return
        raise HTTPException(status_code=401, detail="api key not configured")
    if not x_api_key or not hmac.compare_digest(x_api_key, s.champmail_api_key):
        raise HTTPException(status_code=401, detail="invalid api key")
