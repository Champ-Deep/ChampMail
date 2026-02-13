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

    # Check Redis cache
    try:
        await redis_client.ping()
        health_status["checks"]["redis"] = {
            "status": "healthy",
            "host": settings.redis_host,
            "port": settings.redis_port
        }
    except Exception as e:
        health_status["checks"]["redis"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health_status["status"] = "unhealthy"

    # Check FalkorDB (optional - may not be available in MVP)
    try:
        from app.db.falkordb import graph_db
        if graph_db:
            graph_db.query("RETURN 1")
            health_status["checks"]["falkordb"] = {
                "status": "healthy",
                "host": settings.falkordb_host,
                "port": settings.falkordb_port
            }
        else:
            health_status["checks"]["falkordb"] = {
                "status": "unavailable",
                "message": "FalkorDB not configured (optional for MVP)"
            }
    except Exception as e:
        health_status["checks"]["falkordb"] = {
            "status": "unavailable",
            "error": str(e),
            "message": "FalkorDB optional for MVP"
        }
        # Don't mark overall status as unhealthy for FalkorDB in MVP

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


@router.get("/live")
async def liveness_check():
    """
    Kubernetes-style liveness probe.
    Returns 200 if the service is alive (no deadlock, no infinite loop).
    """
    return {"status": "alive", "version": settings.app_version}
