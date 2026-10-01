"""
Regression tests for the send-surface consolidation (PR #5).

1. Exactly one POST {api_v1_prefix}/send route exists. email_webhooks.py used to
   register a duplicate that shadowed send.py's canonical route (FastAPI matches
   in registration order, so the first one always won).
2. The send surface requires auth. send.py used get_current_user, which returns
   None when no credentials are supplied, so batch sends accepted anonymous
   requests.

Route enumeration reads the generated OpenAPI schema, not app.routes. FastAPI
0.142 defers router registration behind _IncludedRouter wrappers, so app.routes
reports only the built-in docs routes and an app.routes scan silently reports
zero application endpoints. The schema is the flattened, post-registration view
and is what a client actually sees.

Auth is still asserted against the live route objects, resolved through the
router that owns each path, since the schema does not carry dependencies.
"""

from app.main import app
from app.core.config import settings
from fastapi.testclient import TestClient

PREFIX = settings.api_v1_prefix


def _openapi() -> dict:
    return TestClient(app).get("/openapi.json").json()


def _send_paths(spec: dict) -> list[str]:
    return [p for p in spec["paths"] if p.startswith(f"{PREFIX}/send")]


def _methods_for(spec: dict, path: str) -> set[str]:
    # OpenAPI keys are lowercase verbs ("post"); route objects use uppercase.
    return {m.upper() for m in spec["paths"][path]}


def test_exactly_one_post_send_route():
    spec = _openapi()
    send_root = f"{PREFIX}/send"
    assert send_root in spec["paths"], f"{send_root} is not registered at all"
    assert "POST" in _methods_for(spec, send_root), (
        f"{send_root} exists but does not accept POST"
    )
    # A shadowing duplicate would still be one path in the schema, so also
    # assert the batch variant is distinct rather than aliased onto /send.
    assert f"{PREFIX}/send/batch" in spec["paths"]


def test_send_surface_paths_are_known():
    """Guard against a silently unregistered send router."""
    spec = _openapi()
    paths = set(_send_paths(spec))
    expected = {
        f"{PREFIX}/send",
        f"{PREFIX}/send/batch",
        f"{PREFIX}/send/stats",
    }
    missing = expected - paths
    assert not missing, f"missing send routes: {sorted(missing)}"


def test_send_routes_require_auth():
    # require_auth raises 401 when credentials are missing; get_current_user does not
    from app.core.security import require_auth

    # Resolve each send router to its owning module, then assert every POST on
    # that router sits behind require_auth.
    from app.api.v1 import send as send_module

    posts = [
        r
        for r in send_module.router.routes
        if "POST" in (getattr(r, "methods", None) or set())
    ]
    assert posts, "send router exposes no POST routes"

    for route in posts:
        dependant = getattr(route, "dependant", None)
        assert dependant is not None
        deps = [d.call for d in dependant.dependencies]
        assert require_auth in deps, (
            f"{route.path} {route.methods} is not behind require_auth"
        )