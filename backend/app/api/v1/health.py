"""
Health check endpoint for monitoring and load balancers.
Checks database, Redis, and other critical services.
"""

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from app.core.config import settings
from app.db.postgres import async_session_maker
from app.db.redis import redis_client

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("")
async def health_check():
    """
    Comprehensive health check for all critical services.

    Returns:
        - status: "healthy" if all checks pass, "unhealthy" otherwise
        - checks: Dict of individual service statuses
        - version: App version
        - environment: Current environment (development/production)

    HTTP Status Codes:
        - 200: All services healthy
        - 503: One or more services unhealthy
    """
    health_status = {
        "status": "healthy",
        "version": settings.app_version,
        "environment": settings.environment,
        "checks": {}
    }

    # Check PostgreSQL database
    try:
        async with async_session_maker() as session:
            result = await session.execute(text("SELECT 1"))
            result.scalar()
        health_status["checks"]["postgres"] = {
            "status": "healthy",
            "host": settings.postgres_host,
            "port": settings.postgres_port,
            "database": settings.postgres_db
        }
    except Exception as e:
        health_status["checks"]["postgres"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health_status["status"] = "unhealthy"

    # Check Redis cache (non-critical — app works without cache)
    try:
        await redis_client.ping()
        health_status["checks"]["redis"] = {
            "status": "healthy",
            "host": settings.redis_host,
            "port": settings.redis_port
        }
    except Exception as e:
        health_status["checks"]["redis"] = {
            "status": "degraded",
            "error": str(e),
            "message": "Redis unavailable — caching disabled"
        }

    # Check ChampGraph (optional — graph features degrade gracefully)
    try:
        from app.db.champgraph import graph_db
        if graph_db and graph_db._connected:
            result = await graph_db._get("/health")
            health_status["checks"]["champgraph"] = {
                "status": result.get("status", "unknown"),
                "url": settings.champgraph_url,
                "neo4j_connected": result.get("neo4j_connected", False),
            }
        else:
            health_status["checks"]["champgraph"] = {
                "status": "unavailable",
                "message": "ChampGraph not connected"
            }
    except Exception as e:
        health_status["checks"]["champgraph"] = {
            "status": "unavailable",
            "error": str(e),
            "message": "ChampGraph optional — graph features disabled"
        }
        # Don't mark overall status as unhealthy for ChampGraph

    # Return 503 if any critical service is unhealthy
    if health_status["status"] == "unhealthy":
        raise HTTPException(status_code=503, detail=health_status)

    return health_status


@router.get("/ready")
async def readiness_check():
    """
    Kubernetes-style readiness probe.
    Returns 200 if the service is ready to accept traffic.
    """
    try:
        # Quick check - just verify database is responsive
        async with async_session_maker() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail={"status": "not_ready", "error": str(e)}
        )


@router.get("/db-schema")
async def db_schema_check():
    """
    Diagnostic endpoint: report all tables and alembic migration version.
    Useful for verifying schema state on Railway without SSH.
    """
    result = {"tables": [], "alembic_version": None}
    try:
        async with async_session_maker() as session:
            tables = await session.execute(text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' ORDER BY table_name"
            ))
            result["tables"] = [r[0] for r in tables.fetchall()]
            try:
                ver = await session.execute(text("SELECT version_num FROM alembic_version"))
                row = ver.fetchone()
                result["alembic_version"] = row[0] if row else "no rows"
            except Exception:
                result["alembic_version"] = "table not found"
    except Exception as e:
        raise HTTPException(status_code=503, detail={"error": str(e)})
    return result


@router.get("/live")
async def liveness_check():
    """
    Kubernetes-style liveness probe.
    Returns 200 if the service is alive (no deadlock, no infinite loop).
    """
    return {"status": "alive", "version": settings.app_version}
