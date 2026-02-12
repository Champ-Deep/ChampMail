from fastapi import APIRouter, Depends, HTTPException
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
from app.services.mail_engine_client import mail_engine_client
from app.services.cloudflare_client import cloudflare_client
from app.services.namecheap_client import namecheap_client
from app.services.domain_service import domain_service
from app.core.security import get_current_user


router = APIRouter()


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
    created_at: datetime


class CreateDomainRequest(BaseModel):
    domain_name: str = Field(..., min_length=3)
    selector: Optional[str] = "champmail"


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
    health_score: float
    status: str
    all_verified: bool
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


@router.get("/domains", response_model=List[DomainResponse])
async def list_domains(current_user = Depends(get_current_user)):
    try:
        domains = await mail_engine_client.list_domains()
        return domains
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list domains: {str(e)}")


@router.post("/domains", response_model=dict)
async def create_domain(
    request: CreateDomainRequest,
    current_user = Depends(get_current_user),
):
    try:
        result = await mail_engine_client.create_domain(
            domain_name=request.domain_name,
            selector=request.selector,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create domain: {str(e)}")


@router.get("/domains/{domain_id}", response_model=DomainResponse)
async def get_domain(
    domain_id: str,
    current_user = Depends(get_current_user),
):
    try:
        domains = await mail_engine_client.list_domains()
        for d in domains:
            if d["id"] == domain_id:
                return d
        raise HTTPException(status_code=404, detail="Domain not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get domain: {str(e)}")


@router.delete("/domains/{domain_id}")
async def delete_domain(
    domain_id: str,
    current_user = Depends(get_current_user),
):
    try:
        from app.db.postgres import async_session
        from app.services.domain_service import domain_service

        async with async_session() as session:
            await domain_service.delete(session, domain_id)

        return {"message": "Domain deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete domain: {str(e)}")


@router.post("/domains/{domain_id}/verify", response_model=dict)
async def verify_domain(
    domain_id: str,
    current_user = Depends(get_current_user),
):
    try:
        result = await mail_engine_client.verify_domain(domain_id)
        return {
            "domain": result.domain,
            "mx_verified": result.mx_records,
            "spf_valid": result.spf_valid,
            "dkim_valid": result.dkim_valid,
            "dmarc_valid": result.dmarc_valid,
            "all_verified": result.all_verified,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to verify domain: {str(e)}")


@router.get("/domains/{domain_id}/dns-records", response_model=DNSRecordsResponse)
async def get_dns_records(
    domain_id: str,
    current_user = Depends(get_current_user),
):
    try:
        records = await mail_engine_client.get_dns_records(domain_id)

        from app.db.postgres import async_session
        from app.services.domain_service import domain_service

        async with async_session() as session:
            domain = await domain_service.get_by_id(session, domain_id)
            domain_name = domain.get("domain_name", "") if domain else ""

        return DNSRecordsResponse(
            domain_id=domain_id,
            domain_name=domain_name,
            records=[DNSRecord(**r) for r in records],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get DNS records: {str(e)}")


@router.get("/domains/{domain_id}/health", response_model=DomainHealthResponse)
async def get_domain_health(
    domain_id: str,
    current_user = Depends(get_current_user),
):
    try:
        health = await mail_engine_client.get_domain_health(domain_id)

        status = "healthy"
        if health["health_score"] < 70:
            status = "degraded"
        elif health["health_score"] < 50:
            status = "critical"

        return DomainHealthResponse(
            domain_id=domain_id,
            health_score=health["health_score"],
            status=status,
            all_verified=health["all_verified"],
            details=health.get("details", {}),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get health: {str(e)}")


@router.post("/domains/search", response_model=DomainSearchResponse)
async def search_domains(
    request: DomainSearchRequest,
    current_user = Depends(get_current_user),
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
        raise HTTPException(status_code=500, detail=f"Failed to search domains: {str(e)}")


@router.post("/domains/purchase", response_model=PurchaseDomainResponse)
async def purchase_domain(
    request: PurchaseDomainRequest,
    current_user = Depends(get_current_user),
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
        raise HTTPException(status_code=500, detail=f"Failed to purchase domain: {str(e)}")