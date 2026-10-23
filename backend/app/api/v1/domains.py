"""Sending domains. Response keys mirror Harbinger's DomainStatus (email-infra/types.ts)
plus the health and send-accounting fields; ids and the operator gate are extras."""
import logging
import os
import re
from datetime import datetime
from uuid import UUID
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_session, require_api_key
from app.models.domain import Domain
from app.models.email_account import EmailAccount
from app.services.send import CANARY_DAILY_CAP
from app.services.inboxkit.client import InboxKitAPIError, get_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/domains", tags=["Domains"], dependencies=[Depends(require_api_key)])

_DOMAIN_RE = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$")
_USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_SENDABLE = {"ready", "sending", "warming", "active"}  # Harbinger's ACTIVE_DOMAIN_STATUSES plus our logical states
_DEFAULT_USERNAMES = ["alex", "sam", "jordan", "casey", "riley", "morgan", "taylor"]


class DomainCreate(BaseModel):
    domain: str
    brand_id: str = Field(min_length=1, max_length=64)
    mailbox_count: int = Field(ge=1, le=50)
    usernames: Optional[list[str]] = None

    @field_validator("domain")
    @classmethod
    def _domain(cls, v: str) -> str:
        v = v.strip().lower()
        if not _DOMAIN_RE.match(v):
            raise ValueError("not a valid domain name")
        return v

    @model_validator(mode="after")
    def _usernames(self):
        if self.usernames is not None:
            if len(self.usernames) != self.mailbox_count:
                raise ValueError("usernames must have exactly mailbox_count entries")
            self.usernames = [u.strip().lower() for u in self.usernames]
            if len(set(self.usernames)) != len(self.usernames) or not all(map(_USERNAME_RE.match, self.usernames)):
                raise ValueError("usernames must be unique and look like mailbox local-parts")
        return self


class StatusPatch(BaseModel):
    status: Literal["active", "paused", "retired"]
    reason: Optional[str] = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _reason(self):
        if self.status != "active" and not (self.reason or "").strip():
            raise ValueError("reason is required when pausing or retiring")
        return self


def _today():
    return datetime.utcnow().date()


def serialize_domain(d: Domain, mailboxes: list[EmailAccount]) -> dict:
    today = _today()
    dns_ok = bool(d.spf_verified and d.dkim_verified and d.dmarc_verified)
    problem = (
        f"domain {d.send_status}" if d.send_status != "active"
        else "auto-paused" if d.paused
        else "listed on a DNSBL" if d.blacklisted
        else f"status is {d.status}" if (d.status or "").lower() not in _SENDABLE
        else None if dns_ok
        else "SPF, DKIM and DMARC are not all verified"
    )
    out = {
        "id": str(d.id),
        "domain": d.domain_name,
        "status": d.status or "unknown",
        "spfVerified": bool(d.spf_verified),
        "dkimVerified": bool(d.dkim_verified),
        "dmarcVerified": bool(d.dmarc_verified),
        "healthy": problem is None,
        "send_status": d.send_status,
        "send_status_reason": d.send_status_reason,
        "brand_id": d.brand_id,
        "tracking_subdomain": d.tracking_subdomain,
        "dnsbl_listed": d.blacklisted,
        "complaint_rate": d.complaint_rate,
        "hard_bounce_rate": d.bounce_rate,
        "sends_today": sum(m.sent_today for m in mailboxes if m.sent_today_date == today),
        "cap": sum(m.daily_send_limit for m in mailboxes),
        "canary_sends_today": d.canary_sends_today if d.canary_sends_date == today else 0,
        "canary_cap": CANARY_DAILY_CAP,
    }
    if problem:  # TS `reason?: string`: absent when healthy, never null
        out["reason"] = problem
    return out


async def _mailboxes_by_domain(session: AsyncSession, domains: list[Domain]) -> dict:
    by: dict = {d.id: [] for d in domains}
    if by:
        rows = await session.execute(select(EmailAccount).where(EmailAccount.domain_id.in_(by)))
        for m in rows.scalars():
            by[m.domain_id].append(m)
    return by


@router.get("")
async def list_domains(session: AsyncSession = Depends(get_session)) -> list[dict]:
    domains = list((await session.execute(select(Domain).order_by(Domain.domain_name))).scalars())
    by = await _mailboxes_by_domain(session, domains)
    return [serialize_domain(d, by[d.id]) for d in domains]


def _contact() -> dict:
    # Same env names and defaults as Harbinger's registrantContact().
    e = os.environ.get
    return {
        "first_name": e("INBOXKIT_CONTACT_FIRST_NAME") or "Champions",
        "last_name": e("INBOXKIT_CONTACT_LAST_NAME") or "Mail",
        "email": e("INBOXKIT_CONTACT_EMAIL") or "admin@championsmail.com",
        "phone": e("INBOXKIT_CONTACT_PHONE") or "+1.5555555555",
        "address": e("INBOXKIT_CONTACT_ADDRESS") or "1 Market St",
        "city": e("INBOXKIT_CONTACT_CITY") or "San Francisco",
        "state": e("INBOXKIT_CONTACT_STATE") or "CA",
        "zip": e("INBOXKIT_CONTACT_ZIP") or "94105",
        "country": e("INBOXKIT_CONTACT_COUNTRY") or "US",
    }


def _first(order) -> dict:
    row = order[0] if isinstance(order, list) and order else order
    return row if isinstance(row, dict) else {}


@router.post("", status_code=201)
async def create_domain(body: DomainCreate, session: AsyncSession = Depends(get_session)) -> dict:
    client = get_client()
    if not client.configured:
        raise HTTPException(503, "InboxKit is not configured (INBOXKIT_API_KEY / INBOXKIT_WORKSPACE_ID)")
    if (await session.execute(select(Domain.id).where(Domain.domain_name == body.domain))).first():
        raise HTTPException(409, "domain already exists")
    usernames = body.usernames or [
        _DEFAULT_USERNAMES[i] if i < len(_DEFAULT_USERNAMES) else f"outreach{i + 1}"
        for i in range(body.mailbox_count)
    ]

    # Row is flushed before the paid call, committed after it: a failed order leaves no row.
    d = Domain(
        domain_name=body.domain, brand_id=body.brand_id, status="ordered",
        tracking_subdomain=f"track.{body.domain}",  # full host, the per-domain tracking subdomain
        inboxkit_workspace_uid=client._workspace_id,
    )
    session.add(d)
    try:
        await session.flush()
    except IntegrityError:
        raise HTTPException(409, "domain already exists")
    try:
        order = await client.create_order(
            body.domain, usernames, _contact(),
            redirect_url=os.environ.get("INBOXKIT_DEFAULT_REDIRECT_URL") or f"https://{body.domain}",
            platform=os.environ.get("INBOXKIT_MAILBOX_PLATFORM") or "google",
        )
    except InboxKitAPIError as e:
        await session.rollback()
        logger.error("inboxkit order for %s failed: %s", body.domain, e)
        raise HTTPException(502, f"InboxKit order failed: HTTP {e.status}")
    row = _first(order)
    d.inboxkit_order_uid = row.get("uid") or row.get("id") or row.get("order_id")
    domains = row.get("domains") or []
    if domains and isinstance(domains[0], dict):  # else the domain webhook adopts the row by name
        d.inboxkit_domain_uid = domains[0].get("uid")
    await session.commit()
    return {**serialize_domain(d, []), "order_uid": d.inboxkit_order_uid, "mailbox_count": body.mailbox_count}


@router.patch("/{domain_id}")
async def patch_domain(domain_id: str, body: StatusPatch, session: AsyncSession = Depends(get_session)) -> dict:
    try:
        d = await session.get(Domain, UUID(domain_id))
    except ValueError:
        d = None
    if d is None:
        raise HTTPException(404, "domain not found")
    if d.send_status == "retired" and body.status != "retired":
        raise HTTPException(409, "retired is terminal")
    # Domain and mailbox holds are independent; the atomic claim enforces both.
    d.send_status, d.send_status_reason = body.status, body.reason
    await session.commit()
    mailboxes = (await _mailboxes_by_domain(session, [d]))[d.id]
    return serialize_domain(d, mailboxes)
