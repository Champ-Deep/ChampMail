"""GET /api/v1/domain-health/check: one-shot read-only public-DNS observation of a domain (no database, no writes)."""
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.v1.deps import require_api_key
from app.services import domain_probe, mx_checks

router = APIRouter(prefix="/domain-health", tags=["Domain health"], dependencies=[Depends(require_api_key)])


def get_lookup() -> mx_checks.Lookup:
    return mx_checks.resolver_lookup()


@router.get("/check")
async def check(domain: str, dkim_selector: list[str] = Query(default=[], max_length=5), lookup=Depends(get_lookup)) -> dict:
    """422 on a malformed domain or selector. 200 otherwise, even when DNS is unreachable: that is `unknown` per check."""
    try:
        return await domain_probe.probe(domain, lookup, dkim_selector)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
