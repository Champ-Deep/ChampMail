"""PostgreSQL engine and session factory (lifted from v2, trimmed to v3)."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""


engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)

async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)