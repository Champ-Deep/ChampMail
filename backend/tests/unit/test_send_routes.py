"""
Regression tests for the send-surface consolidation (SUGGESTIONS 1.1 + 1.2).

1. Exactly one POST {api_v1_prefix}/send route exists. email_webhooks.py used to
   register a duplicate that shadowed send.py's canonical route (FastAPI matches
   in registration order, so the first one always won).
2. The send surface requires auth. send.py used get_current_user, which returns
   None when no credentials are supplied, so batch sends accepted anonymous
   requests.
"""

from app.main import app
from app.core.config import settings


def _send_routes():
    prefix = settings.api_v1_prefix
    return [
        r
        for r in app.routes
        if getattr(r, "path", None) and getattr(r, "methods", None)
        and r.path.startswith(f"{prefix}/send")
    ]


def test_exactly_one_post_send_route():
    posts = [r for r in _send_routes() if r.path == f"{settings.api_v1_prefix}/send" and "POST" in r.methods]
    assert len(posts) == 1, f"expected 1 POST /send route, found {len(posts)}"


def test_send_routes_require_auth():
    # * require_auth raises 401 when credentials are missing; get_current_user does not
    from app.core.security import require_auth

    for route in _send_routes():
        dependant = getattr(route, "dependant", None)
        assert dependant is not None
        deps = [d.call for d in dependant.dependencies]
        assert require_auth in deps, f"{route.path} {route.methods} is not behind require_auth"
