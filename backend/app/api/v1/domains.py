from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from datetime import datetime

from app.db.postgres import async_session_maker as async_session
from app.services.cloudflare_client import cloudflare_client
from app.services.namecheap_client import namecheap_client
from app.services.domain_service import domain_service
from app.core.security import get_current_user
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Pydantic models ──────────────────────────────────────────────────────────

class DomainResponse(BaseModel):
    id: str
    domain_name: str
    status: str
    mx_verified: bool
    spf_verified: bool
    dkim_verified: bool
    dmarc_verified: bool
    dkim_selector: Optional[str] = None
    daily_send_limit: int
    sent_today: int
    warmup_enabled: bool
    warmup_day: int
    health_score: float
    bounce_rate: Optional[float] = 0.0
    complaint_rate: Optional[float] = 0.0
    blacklisted: Optional[bool] = False
    blacklist_hits: Optional[int] = 0
    paused: Optional[bool] = False
    created_at: datetime


class CreateDomainRequest(BaseModel):
    domain_name: str = Field(..., min_length=3)
    selector: Optional[str] = "champmail"


class VerifyDomainResponse(BaseModel):
    domain_name: str
    mx_verified: bool
    spf_verified: bool
    dkim_verified: bool
    dmarc_verified: bool
    all_verified: bool
    health_score: float


class DNSRecord(BaseModel):
    type: str
    name: str
    value: str
    priority: Optional[int] = None
    ttl: int


class DNSRecordsResponse(BaseModel):
    domain_id: str
    domain_name: str
    records: List[DNSRecord]


class DomainHealthResponse(BaseModel):
    domain_id: str
    domain_name: str
    health_score: float
    status: str
    all_verified: bool
    blacklisted: bool
    paused: bool
    details: dict


class DomainSearchRequest(BaseModel):
    keyword: str
    tlds: Optional[List[str]] = [".com", ".io", ".co"]


class DomainSearchResult(BaseModel):
    domain: str
    available: bool
    price: float
    currency: str = "USD"


class DomainSearchResponse(BaseModel):
    results: List[DomainSearchResult]


class PurchaseDomainRequest(BaseModel):
    domain: str
    years: int = 1
    nameservers: Optional[List[str]] = None


class PurchaseDomainResponse(BaseModel):
    success: bool
    order_id: str
    transaction_id: str
    domain: str
    error: Optional[str] = None


class SeedTestResponse(BaseModel):
    domain_id: str
    domain_name: str
    gmail_placement: Optional[str] = None
    outlook_placement: Optional[str] = None
    yahoo_placement: Optional[str] = None
    inbox_rate: float
    spam_rate: float
    missing_rate: float


# ── Helpers ──────────────────────────────────────────────────────────────────

def _health_status(score: float) -> str:
    if score >= 80:
        return "healthy"
    if score >= 50:
        return "degraded"
    return "critical"


def _domain_response(d: dict) -> DomainResponse:
    """Coerce a domain_service dict into a DomainResponse."""
    return DomainResponse(
        id=str(d.get("id", "")),
        domain_name=d.get("domain_name", ""),
        status=d.get("status", "pending"),
        mx_verified=bool(d.get("mx_verified", False)),
        spf_verified=bool(d.get("spf_verified", False)),
        dkim_verified=bool(d.get("dkim_verified", False)),
        dmarc_verified=bool(d.get("dmarc_verified", False)),
        dkim_selector=d.get("dkim_selector"),
        daily_send_limit=int(d.get("daily_send_limit", 0)),
        sent_today=int(d.get("sent_today", 0)),
        warmup_enabled=bool(d.get("warmup_enabled", False)),
        warmup_day=int(d.get("warmup_day", 0)),
        health_score=float(d.get("health_score", 100.0)),
        bounce_rate=float(d.get("bounce_rate", 0.0) or 0.0),
        complaint_rate=float(d.get("complaint_rate", 0.0) or 0.0),
        blacklisted=bool(d.get("blacklisted", False)),
        blacklist_hits=int(d.get("blacklist_hits", 0) or 0),
        paused=bool(d.get("paused", False)),
        created_at=d.get("created_at") or datetime.utcnow(),
    )


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/domains", response_model=List[DomainResponse])
async def list_domains(current_user=Depends(get_current_user)):
    try:
        async with async_session() as session:
            domains = await domain_service.get_all_domains(session)
        return [_domain_response(d) for d in domains]
    except Exception as e:
        logger.exception("list_domains failed")
        raise HTTPException(status_code=500, detail=f"Failed to list domains: {e}")


@router.post("/domains", response_model=dict)
async def create_domain(
    request: CreateDomainRequest,
    current_user=Depends(get_current_user),
):
    """Provision a new sending domain: generate DKIM keys, write to OpenDKIM, reload."""
    try:
        from app.tasks.domains import provision_new_domain
        result = provision_new_domain.delay(
            domain_name=request.domain_name,
            selector=request.selector or settings.dkim_selector,
        )
        return {
            "message": f"Domain provisioning started for {request.domain_name}",
            "task_id": result.id,
            "domain_name": request.domain_name,
        }
    except Exception as e:
        logger.exception("create_domain failed")
        raise HTTPException(status_code=500, detail=f"Failed to create domain: {e}")


@router.get("/domains/{domain_id}", response_model=DomainResponse)
async def get_domain(domain_id: str, current_user=Depends(get_current_user)):
    try:
        async with async_session() as session:
            domain = await domain_service.get_by_id(session, domain_id)
        if not domain:
            raise HTTPException(status_code=404, detail="Domain not found")
        return _domain_response(domain)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("get_domain failed")
        raise HTTPException(status_code=500, detail=f"Failed to get domain: {e}")


@router.delete("/domains/{domain_id}")
async def delete_domain(domain_id: str, current_user=Depends(get_current_user)):
    try:
        async with async_session() as session:
            await domain_service.delete(session, domain_id)
        return {"message": "Domain deleted successfully"}
    except Exception as e:
        logger.exception("delete_domain failed")
        raise HTTPException(status_code=500, detail=f"Failed to delete domain: {e}")


@router.post("/domains/{domain_id}/verify", response_model=VerifyDomainResponse)
async def verify_domain(domain_id: str, current_user=Depends(get_current_user)):
    """Re-check DNS records and update verification flags on the domain."""
    try:
        async with async_session() as session:
            domain = await domain_service.get_by_id(session, domain_id)
            if not domain:
                raise HTTPException(status_code=404, detail="Domain not found")

            # Check DNS via Cloudflare zone if zone_id is stored, else just check flags
            zone_id = domain.get("cloudflare_zone_id", "")
            if zone_id:
                health = await cloudflare_client.check_domain_health(zone_id)
                details = health.get("details", {})
                updates = {
                    "mx_verified": details.get("mx", False),
                    "spf_verified": details.get("spf", False),
                    "dkim_verified": details.get("dkim", False),
                    "dmarc_verified": details.get("dmarc", False),
                    "health_score": health.get("score", domain.get("health_score", 0)),
                }
                await domain_service.update(session, domain_id, updates)
                domain.update(updates)

        all_verified = all([
            domain.get("mx_verified"), domain.get("spf_verified"),
            domain.get("dkim_verified"), domain.get("dmarc_verified"),
        ])
        return VerifyDomainResponse(
            domain_name=domain["domain_name"],
            mx_verified=bool(domain.get("mx_verified")),
            spf_verified=bool(domain.get("spf_verified")),
            dkim_verified=bool(domain.get("dkim_verified")),
            dmarc_verified=bool(domain.get("dmarc_verified")),
            all_verified=all_verified,
            health_score=float(domain.get("health_score", 100.0)),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("verify_domain failed")
        raise HTTPException(status_code=500, detail=f"Failed to verify domain: {e}")


@router.get("/domains/{domain_id}/dns-records", response_model=DNSRecordsResponse)
async def get_dns_records(domain_id: str, current_user=Depends(get_current_user)):
    """Return the DNS records this domain needs configured."""
    try:
        async with async_session() as session:
            domain = await domain_service.get_by_id(session, domain_id)
        if not domain:
            raise HTTPException(status_code=404, detail="Domain not found")

        domain_name = domain["domain_name"]
        selector = domain.get("dkim_selector") or settings.dkim_selector
        server_ip = settings.vps_public_ip or "YOUR_SERVER_IP"
        dmarc_email = settings.dmarc_report_email or f"dmarc@{domain_name}"

        records = [
            DNSRecord(type="A",   name=f"mail.{domain_name}",               value=server_ip,           ttl=3600),
            DNSRecord(type="A",   name=f"track.{domain_name}",              value=server_ip,           ttl=3600),
            DNSRecord(type="MX",  name=domain_name,                          value=f"mail.{domain_name}", priority=10, ttl=3600),
            DNSRecord(type="TXT", name=domain_name,                          value=f"v=spf1 ip4:{server_ip} -all", ttl=3600),
            DNSRecord(type="TXT", name=f"{selector}._domainkey.{domain_name}", value="(run /api/v1/domains/{id}/dkim-pubkey to get value)", ttl=3600),
            DNSRecord(type="TXT", name=f"_dmarc.{domain_name}",             value=f"v=DMARC1; p=none; rua=mailto:{dmarc_email}", ttl=3600),
        ]
        return DNSRecordsResponse(domain_id=domain_id, domain_name=domain_name, records=records)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("get_dns_records failed")
        raise HTTPException(status_code=500, detail=f"Failed to get DNS records: {e}")


@router.get("/domains/{domain_id}/health", response_model=DomainHealthResponse)
async def get_domain_health(domain_id: str, current_user=Depends(get_current_user)):
    try:
        async with async_session() as session:
            domain = await domain_service.get_by_id(session, domain_id)
        if not domain:
            raise HTTPException(status_code=404, detail="Domain not found")

        score = float(domain.get("health_score", 100.0))
        return DomainHealthResponse(
            domain_id=domain_id,
            domain_name=domain["domain_name"],
            health_score=score,
            status=_health_status(score),
            all_verified=all([
                domain.get("mx_verified"), domain.get("spf_verified"),
                domain.get("dkim_verified"), domain.get("dmarc_verified"),
            ]),
            blacklisted=bool(domain.get("blacklisted", False)),
            paused=bool(domain.get("paused", False)),
            details={
                "mx": domain.get("mx_verified", False),
                "spf": domain.get("spf_verified", False),
                "dkim": domain.get("dkim_verified", False),
                "dmarc": domain.get("dmarc_verified", False),
                "bounce_rate": domain.get("bounce_rate", 0.0),
                "complaint_rate": domain.get("complaint_rate", 0.0),
                "blacklist_hits": domain.get("blacklist_hits", 0),
                "warmup_day": domain.get("warmup_day", 0),
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("get_domain_health failed")
        raise HTTPException(status_code=500, detail=f"Failed to get health: {e}")


@router.post("/domains/{domain_id}/pause")
async def pause_domain(domain_id: str, current_user=Depends(get_current_user)):
    """Manually pause sending on a domain."""
    try:
        async with async_session() as session:
            domain = await domain_service.get_by_id(session, domain_id)
            if not domain:
                raise HTTPException(status_code=404, detail="Domain not found")
            await domain_service.pause_domain(session, domain_id)
        return {"message": f"Domain {domain['domain_name']} paused"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to pause domain: {e}")


@router.post("/domains/{domain_id}/unpause")
async def unpause_domain(domain_id: str, current_user=Depends(get_current_user)):
    """Resume sending on a paused domain."""
    try:
        async with async_session() as session:
            domain = await domain_service.get_by_id(session, domain_id)
            if not domain:
                raise HTTPException(status_code=404, detail="Domain not found")
            await domain_service.update(session, domain_id, {"paused": False})
        return {"message": f"Domain {domain['domain_name']} resumed"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to unpause domain: {e}")


@router.post("/domains/{domain_id}/seed-test", response_model=SeedTestResponse)
async def run_seed_test(domain_id: str, current_user=Depends(get_current_user)):
    """Send test emails to seed inboxes and report inbox/spam placement."""
    try:
        async with async_session() as session:
            domain = await domain_service.get_by_id(session, domain_id)
        if not domain:
            raise HTTPException(status_code=404, detail="Domain not found")

        from app.services.seed_tester import seed_tester
        report = await seed_tester.run_placement_test(domain["domain_name"])

        total = max(report.total_sent, 1)
        return SeedTestResponse(
            domain_id=domain_id,
            domain_name=domain["domain_name"],
            gmail_placement=report.gmail_placement,
            outlook_placement=report.outlook_placement,
            yahoo_placement=report.yahoo_placement,
            inbox_rate=round(report.inbox_count / total, 3),
            spam_rate=round(report.spam_count / total, 3),
            missing_rate=round(report.missing_count / total, 3),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("seed_test failed")
        raise HTTPException(status_code=500, detail=f"Seed test failed: {e}")


# ── Namecheap domain search / purchase ───────────────────────────────────────

@router.post("/domains/search", response_model=DomainSearchResponse)
async def search_domains(
    request: DomainSearchRequest,
    current_user=Depends(get_current_user),
):
    try:
        results = await namecheap_client.search_domains(
            keyword=request.keyword,
            tlds=request.tlds,
        )
        return DomainSearchResponse(
            results=[
                DomainSearchResult(
                    domain=r.domain,
                    available=r.available,
                    price=r.price,
                    currency=r.currency,
                )
                for r in results
            ],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to search domains: {e}")


@router.post("/domains/purchase", response_model=PurchaseDomainResponse)
async def purchase_domain(
    request: PurchaseDomainRequest,
    current_user=Depends(get_current_user),
):
    try:
        result = await namecheap_client.purchase_domain(
            domain=request.domain,
            years=request.years,
            nameservers=request.nameservers,
        )
        return PurchaseDomainResponse(
            success=result.success,
            order_id=result.order_id,
            transaction_id=result.transaction_id,
            domain=result.domain,
            error=result.error,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to purchase domain: {e}")
