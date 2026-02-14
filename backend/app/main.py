"""
ChampMail - FastAPI Backend

Main application entry point.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

logger = logging.getLogger(__name__)
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.db.falkordb import init_graph_db, close_graph_db
from app.db.postgres import init_db, close_db, get_db
from app.db.redis import redis_client
from app.services.user_service import user_service
from app.middleware.rate_limit import setup_rate_limiting

# Import routers
from app.api.v1 import auth, prospects, sequences, webhooks, graph, templates, campaigns, email_settings, email_accounts, teams, workflows, email_webhooks, health
from app.api.v1 import send, domains, tracking, analytics_api, utm, c1_chat
from app.api.v1.admin import router as admin_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    # Startup
    logger.info("Starting %s v%s", settings.app_name, settings.app_version)
    logger.info("Environment: %s", settings.environment)
    logger.info("FalkorDB: %s:%s", settings.falkordb_host, settings.falkordb_port)
    logger.info("PostgreSQL: %s:%s", settings.postgres_host, settings.postgres_port)

    # Validate production settings
    try:
        settings.validate_production_settings()
        logger.info("Production settings validated successfully")
    except ValueError as e:
        if settings.environment == "production":
            logger.error("CRITICAL: %s", e)
            raise  # Stop startup in production with invalid config
        else:
            logger.warning("Production settings validation: %s", e)

    # Initialize PostgreSQL
    try:
        await init_db()
        logger.info("PostgreSQL connected and tables created")

        # Create default admin user (development only)
        if settings.environment == "development":
            async with get_db() as session:
                await user_service.ensure_default_admin(session)
    except Exception as e:
        logger.error("PostgreSQL initialization failed: %s", e)
        logger.error("Auth will NOT work without database!")

    # Initialize FalkorDB
    if init_graph_db():
        logger.info("FalkorDB connected")
    else:
        logger.warning("FalkorDB unavailable - graph features disabled")

    # Check OpenRouter API key
    if settings.openrouter_api_key:
        logger.info("OpenRouter API key configured - AI features enabled")
    else:
        logger.warning("OPENROUTER_API_KEY not set - AI features will fail")

    # Check Thesys C1 API key
    if settings.thesys_api_key:
        logger.info("Thesys C1 API key configured - Generative UI enabled")
    else:
        logger.info("THESYS_API_KEY not set - AI Assistant will be disabled")

    yield

    # Shutdown
    await redis_client.close()
    logger.info("Redis disconnected")
    close_graph_db()
    logger.info("FalkorDB disconnected")
    await close_db()
    logger.info("PostgreSQL disconnected")
    logger.info("Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="""
    ChampMail API

    An enterprise-grade, AI-powered cold email outreach platform.

    ## Features

    - **Prospects**: Manage leads in the knowledge graph
    - **Sequences**: Create and manage multi-step email campaigns
    - **Webhooks**: Integration with n8n and BillionMail
    - **Knowledge Graph**: Query and explore prospect relationships

    ## Authentication

    Use `/api/v1/auth/login` to get a JWT token.
    Include it in requests as: `Authorization: Bearer <token>`

    Development credentials:
    - Admin: `admin@champions.dev` / `admin123`
    - User: `user@champions.dev` / `user123`
    """,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
# In production, only allow requests from the frontend domain
# In development, allow localhost variants
allowed_origins = [settings.frontend_url]
if settings.environment == "development":
    allowed_origins.extend([
        "http://localhost:3000",
        "http://localhost:5173",  # Vite default
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ])

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With", "Accept"],
)

# Rate limiting
setup_rate_limiting(app)


# Health check is now handled by the health router


# Root endpoint
@app.get("/", tags=["Root"])
async def root():
    """API root - returns basic info."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/health",
    }


# Include routers
app.include_router(health.router)  # Health check at /health (no /api/v1 prefix)
app.include_router(auth.router, prefix=settings.api_v1_prefix)
app.include_router(prospects.router, prefix=settings.api_v1_prefix)
app.include_router(sequences.router, prefix=settings.api_v1_prefix)
app.include_router(templates.router, prefix=settings.api_v1_prefix)
app.include_router(campaigns.router, prefix=settings.api_v1_prefix)
app.include_router(email_settings.router, prefix=settings.api_v1_prefix)
app.include_router(email_accounts.router, prefix=f"{settings.api_v1_prefix}/email-accounts", tags=["Email Accounts"])
app.include_router(teams.router, prefix=settings.api_v1_prefix)
app.include_router(webhooks.router, prefix=settings.api_v1_prefix)
app.include_router(workflows.router, prefix=settings.api_v1_prefix)
app.include_router(email_webhooks.router, prefix=settings.api_v1_prefix, tags=["Email Webhooks"])
app.include_router(graph.router, prefix=settings.api_v1_prefix)
app.include_router(send.router, prefix=settings.api_v1_prefix, tags=["Send"])
app.include_router(domains.router, prefix=settings.api_v1_prefix, tags=["Domains"])
app.include_router(tracking.router, prefix=settings.api_v1_prefix, tags=["Tracking"])
app.include_router(analytics_api.router, prefix=settings.api_v1_prefix, tags=["Analytics"])
app.include_router(utm.router, prefix=settings.api_v1_prefix, tags=["UTM"])
app.include_router(c1_chat.router, prefix=settings.api_v1_prefix, tags=["C1 Chat"])
app.include_router(admin_router, prefix=settings.api_v1_prefix)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )
