"""The daily job: one `domain_health_daily` row per non-retired domain per UTC day, plus the live bounce and
complaint rates `GET /api/v1/domains` reports.

Due-ness is derived from the table (a domain with no row for today is due), so the worker can call this on
every tick, a restart mid-day finishes the day instead of repeating it, and a missed day self-heals.
A failure on one domain is logged and leaves it due for the next tick; it never blocks the others.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Awaitable, Callable, Optional

from sqlalchemy import func, select

from app.config import get_settings
from app.models import Bounce, DmarcReport, DnsblZone, Domain, DomainHealthDaily, EmailAccount, OutboundEvent, SendDispatch
from app.services import mx_checks as mx

log = logging.getLogger("champmail.health")


def utc_today() -> date:
    return datetime.utcnow().date()


def _window(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min)
    return start, start + timedelta(days=1)


async def rates(session, domain_ids: list, day: date) -> dict:
    """{domain_id: (hard_bounce_rate, complaint_rate)} for one UTC day (00:00 to 24:00, the day the daily job runs).

    hard_bounce_rate = hard DSNs (bounces.kind = 'hard', by bounce time) / sends.
    complaint_rate   = `complained` outbound events (by event time) / sends.
    sends            = send_dispatches with status 'sent' created that day, canaries excluded.
    Zero sends gives 0.0 for both, never a division error. GET /domains serves the value the last job run
    stored on the domain row, so it is as fresh as that run (once per day, plus on a missed-day catch-up)."""
    if not domain_ids:
        return {}
    lo, hi = _window(day)
    sends = dict((await session.execute(
        select(SendDispatch.domain_id, func.count()).where(
            SendDispatch.domain_id.in_(domain_ids), SendDispatch.status == "sent", SendDispatch.canary.is_not(True),
            SendDispatch.created_at >= lo, SendDispatch.created_at < hi).group_by(SendDispatch.domain_id))).all())
    hard = dict((await session.execute(
        select(EmailAccount.domain_id, func.count(Bounce.id)).join(EmailAccount, Bounce.email_account_id == EmailAccount.id).where(
            EmailAccount.domain_id.in_(domain_ids), Bounce.kind == "hard",
            Bounce.created_at >= lo, Bounce.created_at < hi).group_by(EmailAccount.domain_id))).all())
    complained = dict((await session.execute(
        select(SendDispatch.domain_id, func.count(OutboundEvent.id)).join(SendDispatch, OutboundEvent.message_id == SendDispatch.message_id).where(
            SendDispatch.domain_id.in_(domain_ids), OutboundEvent.event_type == "complained",
            OutboundEvent.event_at >= lo, OutboundEvent.event_at < hi).group_by(SendDispatch.domain_id))).all())
    return {i: ((round(hard.get(i, 0) / sends[i], 6), round(complained.get(i, 0) / sends[i], 6)) if sends.get(i) else (0.0, 0.0))
            for i in domain_ids}


async def latest(session, domain_ids: list) -> dict:
    """{domain_id: newest DomainHealthDaily}."""
    if not domain_ids:
        return {}
    newest = select(DomainHealthDaily.domain_id, func.max(DomainHealthDaily.day).label("day")).where(
        DomainHealthDaily.domain_id.in_(domain_ids)).group_by(DomainHealthDaily.domain_id).subquery()
    rows = await session.execute(select(DomainHealthDaily).join(
        newest, (DomainHealthDaily.domain_id == newest.c.domain_id) & (DomainHealthDaily.day == newest.c.day)))
    return {r.domain_id: r for r in rows.scalars()}


async def _dmarc_yesterday(session, domain_id, day: date) -> tuple[int, int]:
    p, f = (await session.execute(
        select(func.coalesce(func.sum(DmarcReport.pass_count), 0), func.coalesce(func.sum(DmarcReport.fail_count), 0)).where(
            DmarcReport.domain_id == domain_id, DmarcReport.day == day - timedelta(days=1)))).one()
    return int(p), int(f)


async def check_domain(session, d: Domain, lookup: mx.Lookup, zones: list, postmaster, day: date) -> None:
    """Query DNS, DNSBLs, the DMARC ledger and Postmaster for one domain and upsert its row. Caller commits."""
    platforms = {p for (raw,) in (await session.execute(
        select(EmailAccount.platform).where(EmailAccount.domain_id == d.id).distinct())).all() if (p := mx.platform(raw))}
    ips = list(await lookup(d.domain_name, "A") or []) + ([d.sending_ip] if d.sending_ip else [])

    spf = await mx.spf_ok(d.domain_name, platforms, lookup)
    selectors = [x.strip() for x in [d.dkim_selector or "", *get_settings().dkim_selectors.split(",")] if x.strip()]
    dkim = await mx.dkim_ok(d.domain_name, platforms, selectors, lookup)
    policy = await mx.dmarc_policy(d.domain_name, lookup)
    sts = await mx.mta_sts_ok(d.domain_name, lookup)
    hits, errors = await mx.dnsbl_check(d.domain_name, ips, zones, lookup)
    if errors:
        log.warning("dnsbl: no answer from %s for %s", errors, d.domain_name)

    passed, failed = await _dmarc_yesterday(session, d.id, day)
    pm = None
    if postmaster is not None:
        try:
            pm = await postmaster.stats(d.domain_name)
        except Exception:  # a lagging signal: log and continue
            log.exception("postmaster failed for %s", d.domain_name)

    row = (await session.execute(select(DomainHealthDaily).where(
        DomainHealthDaily.domain_id == d.id, DomainHealthDaily.day == day))).scalar_one_or_none() or DomainHealthDaily(domain_id=d.id, day=day)
    row.spf_ok, row.dkim_ok, row.dmarc_policy, row.mta_sts_ok = spf, dkim, policy, sts
    row.dnsbl_listed = hits
    row.dmarc_reports_pass_count, row.dmarc_reports_fail_count = (passed, failed) if passed + failed else (None, None)
    row.dmarc_aligned = None if passed + failed == 0 else failed == 0
    row.postmaster_spam_rate = pm.get("spam_rate") if pm else None
    row.postmaster_reputation = pm.get("reputation") if pm else None
    row.source = "+".join(["dns"] + (["dmarc"] if passed + failed else []) + (["postmaster"] if pm else []))
    row.checked_at = datetime.utcnow()
    session.add(row)

    d.spf_verified, d.dkim_verified, d.dmarc_verified = spf, dkim, policy is not None
    if hits or not errors:  # every list answered, or one hit: otherwise the previous listing stands (unknown is not clean)
        d.blacklisted, d.blacklist_hits = bool(hits), len(hits)
    d.last_health_check = row.checked_at
    d.bounce_rate, d.complaint_rate = (await rates(session, [d.id], day))[d.id]


async def run_daily(Session, *, lookup: Optional[mx.Lookup] = None, postmaster=None,
                    ingest: Optional[Callable[..., Awaitable]] = None, today: Optional[date] = None) -> int:
    """Check every due domain. Returns how many were checked. `ingest` reads the DMARC mailbox first."""
    day = today or utc_today()
    async with Session() as s:
        done = select(DomainHealthDaily.domain_id).where(DomainHealthDaily.day == day)
        due = list((await s.execute(select(Domain.id).where(
            func.coalesce(Domain.send_status, "active") != "retired", Domain.id.not_in(done)))).scalars())
        zones = list((await s.execute(select(DnsblZone).where(DnsblZone.enabled.is_(True)))).scalars())
    if not due:
        return 0
    from app.services import dmarc_ingest, postmaster as pm_mod  # late: heavy import, and the ingest/postmaster tests patch them
    lookup = lookup or mx.resolver_lookup()
    postmaster = postmaster or pm_mod.from_settings()
    try:
        await (ingest or dmarc_ingest.ingest_from_settings)(Session)
    except Exception:
        log.exception("dmarc ingestion failed; health rows use the reports already stored")
    done_n = 0
    for domain_id in due:
        try:
            async with Session() as s:
                d = await s.get(Domain, domain_id)
                await check_domain(s, d, lookup, zones, postmaster, day)
                await s.commit()
            done_n += 1
        except Exception:
            log.exception("health check failed for domain %s", domain_id)
    return done_n
