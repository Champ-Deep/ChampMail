"""DMARC aggregate reports -> `dmarc_reports`, parsed by parsedmarc (Apache-2.0), offline (no DNS or GeoIP lookups).

`ingest_from_settings` reads the rua mailbox over IMAP. parsedmarc moves each processed message to the
archive folder, and the (org, report_id, domain) unique key makes a second read of the same report a no-op,
so a crash between "stored" and "archived" cannot double count. Reports for domains we do not own are dropped.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime

import parsedmarc
from parsedmarc.mail import IMAPConnection
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.config import get_settings
from app.models import DmarcReport, Domain

log = logging.getLogger("champmail.dmarc")
ARCHIVE_FOLDER = "DMARC-processed"


def summarise(report: dict) -> dict:
    """One parsedmarc aggregate report as {org, report_id, domain, day, pass, fail, fail_ips}. `pass` counts
    messages whose DMARC alignment passed (SPF or DKIM aligned), weighted by the record's message count."""
    meta, recs = report["report_metadata"], report["records"]
    fail_ips: dict[str, int] = {}
    for r in recs:
        if not r["alignment"]["dmarc"]:
            ip = r["source"]["ip_address"]
            fail_ips[ip] = fail_ips.get(ip, 0) + r["count"]
    # Records carry a UTC interval_begin; the metadata dates are rendered in the host's timezone.
    day = datetime.strptime((recs[0]["interval_begin"] if recs else meta["begin_date"])[:10], "%Y-%m-%d").date()
    return {"org": meta["org_name"], "report_id": meta["report_id"], "domain": report["policy_published"]["domain"].lower(),
            "day": day, "pass": sum(r["count"] for r in recs if r["alignment"]["dmarc"]), "fail": sum(fail_ips.values()), "fail_ips": fail_ips}


async def store(Session, reports: list[dict]) -> int:
    """Insert reports for domains we own; returns how many were new."""
    rows = []
    for r in reports:
        try:
            rows.append(summarise(r))
        except (KeyError, TypeError, ValueError):  # one odd report must not abort the batch
            log.warning("skipping unreadable DMARC report %r", (r.get("report_metadata") or {}).get("report_id"), exc_info=True)
    if not rows:
        return 0
    async with Session() as s:
        ours = dict((await s.execute(select(Domain.domain_name, Domain.id).where(
            Domain.domain_name.in_({r["domain"] for r in rows})))).all())
        new = 0
        for r in rows:
            if r["domain"] not in ours:
                continue
            res = await s.execute(insert(DmarcReport).values(
                org_name=r["org"], report_id=r["report_id"], domain_id=ours[r["domain"]], day=r["day"],
                pass_count=r["pass"], fail_count=r["fail"], fail_ips=r["fail_ips"], created_at=datetime.utcnow(),
            ).on_conflict_do_nothing(constraint="uq_dmarc_reports_org_report_domain").returning(DmarcReport.id))
            new += len(res.all())
        await s.commit()
    return new


def read_mailbox(host: str, user: str, password: str, *, port: int = 993, ssl: bool = True, folder: str = "INBOX") -> list[dict]:
    """Blocking: every aggregate report waiting in `folder`, which parsedmarc then archives."""
    conn = IMAPConnection(host=host, user=user, password=password, port=port, ssl=ssl, verify=ssl, timeout=15, max_retries=1)
    return read_reports(conn, folder)


def read_reports(conn, folder: str) -> list[dict]:
    """Aggregate reports in `folder` of any parsedmarc MailboxConnection. parsedmarc logs and skips a message
    it cannot parse, so one malformed report never aborts the batch."""
    out = parsedmarc.get_dmarc_reports_from_mailbox(conn, reports_folder=folder, archive_folder=ARCHIVE_FOLDER, offline=True)
    return out["aggregate_reports"]


async def ingest_from_settings(Session) -> int:
    """Pull and store. 0 when no mailbox is configured. A mailbox failure raises; the caller logs and carries on."""
    s = get_settings()
    if not s.dmarc_imap_host:
        return 0
    reports = await asyncio.to_thread(read_mailbox, s.dmarc_imap_host, s.dmarc_imap_user, s.dmarc_imap_password,
                                      port=s.dmarc_imap_port, ssl=s.dmarc_imap_ssl, folder=s.dmarc_imap_folder)
    return await store(Session, reports)


async def get_fail_count(Session, domain: str, day: date) -> int | None:
    """Failing message count for `domain` on `day` (UTC), summed over reports. None when no report covers it,
    so the daily job can tell \"no data\" from \"zero failures\"."""
    async with Session() as s:
        return (await s.execute(select(func.sum(DmarcReport.fail_count)).join(Domain, Domain.id == DmarcReport.domain_id)
                                .where(Domain.domain_name == domain.lower(), DmarcReport.day == day))).scalar()


async def top_failing_ips(Session, domain: str, day: date, n: int = 5) -> list[tuple[str, int]]:
    """The `n` source IPs with the most failing messages for `domain` on `day`, as (ip, count)."""
    async with Session() as s:
        rows = (await s.execute(select(DmarcReport.fail_ips).join(Domain, Domain.id == DmarcReport.domain_id)
                                .where(Domain.domain_name == domain.lower(), DmarcReport.day == day))).scalars()
        totals: dict[str, int] = {}
        for ips in rows:
            for ip, c in ips.items():
                totals[ip] = totals.get(ip, 0) + c
    return sorted(totals.items(), key=lambda t: (-t[1], t[0]))[:n]
