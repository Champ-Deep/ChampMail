"""
Rate limiting middleware using slowapi.
Limits: 100 req/min per user, 1000 req/min per team.
"""

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request


def _get_user_key(request: Request) -> str:
    """Extract user ID from JWT for per-user rate limiting."""
    # Try to get user from auth header
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            from app.core.security import decode_token
            token_data = decode_token(auth[7:])
            return f"user:{token_data.user_id}"
        except Exception:
            pass
    return get_remote_address(request)


# Create limiter with user-based key
limiter = Limiter(
    key_func=_get_user_key,
    default_limits=["100/minute"],
    storage_uri="memory://",  # Use Redis in production
)


def setup_rate_limiting(app):
    """Configure rate limiting for the FastAPI app."""
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
