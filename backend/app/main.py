"""
ChampMail - FastAPI Backend

Main application entry point.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.db.falkordb import init_graph_db, close_graph_db
from app.db.postgres import init_db, close_db, get_db
from app.services.user_service import user_service

# Import routers
from app.api.v1 import auth, prospects, sequences, webhooks, graph, templates, campaigns, email_settings, email_accounts, teams, workflows, email_webhooks
from app.api.v1 import send, domains


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    # Startup
    print(f"Starting {settings.app_name} v{settings.app_version}")
    print(f"Environment: {settings.environment}")
    print(f"FalkorDB: {settings.falkordb_host}:{settings.falkordb_port}")
    print(f"PostgreSQL: {settings.postgres_host}:{settings.postgres_port}")

    # Initialize PostgreSQL
    try:
        await init_db()
        print("PostgreSQL connected and tables created")

        # Create default admin user
        async with get_db() as session:
            await user_service.ensure_default_admin(session)
            print("Default admin user ensured")
    except Exception as e:
        print(f"PostgreSQL initialization failed: {e}")
        print("Auth will NOT work without database!")

    # Initialize FalkorDB
    if init_graph_db():
        print("FalkorDB connected")
    else:
        print("FalkorDB unavailable - graph features disabled")

    yield

    # Shutdown
    close_graph_db()
    print("FalkorDB disconnected")
    await close_db()
    print("PostgreSQL disconnected")
    print("Shutdown complete")


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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure properly in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check endpoint
@app.get("/health", tags=["Health"])
async def health_check():
    """Check API and database health."""
    from app.db.falkordb import graph_db
    from sqlalchemy import text

    # Test FalkorDB connection
    try:
        graph_db.query("RETURN 1")
        falkordb_status = "healthy"
    except Exception as e:
        falkordb_status = f"unhealthy: {str(e)}"

    # Test PostgreSQL connection
    try:
        async with get_db() as session:
            await session.execute(text("SELECT 1"))
        postgres_status = "healthy"
    except Exception as e:
        postgres_status = f"unhealthy: {str(e)}"

    all_healthy = falkordb_status == "healthy" and postgres_status == "healthy"

    return {
        "status": "healthy" if all_healthy else "degraded",
        "version": settings.app_version,
        "environment": settings.environment,
        "services": {
            "falkordb": falkordb_status,
            "postgresql": postgres_status,
        },
    }


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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )
