"""DMARC aggregate ingestion: real parsedmarc over a real aggregate XML, then a real IMAP mailbox (GreenMail)."""
from __future__ import annotations

import asyncio
import os
import smtplib
import uuid
from datetime import date
from email.message import EmailMessage
from pathlib import Path

import parsedmarc
import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import DmarcReport
from app.services import dmarc_ingest
from tests.test_send import run, seed

XML = Path(__file__).parent / "fixtures" / "dmarc_aggregate.xml"
NAME = "acme-mail.test"
needs_db = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set")
needs_imap = pytest.mark.skipif(not os.environ.get("TEST_IMAP"), reason="TEST_IMAP not set")


def parsed() -> dict:
    return parsedmarc.parse_report_file(str(XML), offline=True)["report"]


def test_summary_counts_aligned_messages_by_record_count_and_names_the_failing_ips():
    s = dmarc_ingest.summarise(parsed())
    assert (s["org"], s["report_id"], s["domain"], s["day"]) == ("google.com", "17459823650123456789", NAME, date(2025, 10, 22))
    assert (s["pass"], s["fail"], s["fail_ips"]) == (3, 2, {"203.0.113.9": 2})   # 3 pass (one on SPF alone), 2 fail


@needs_db
def test_store_is_idempotent_and_ignores_domains_we_do_not_own():
    async def go(Session):
        await seed(Session, dom_kw={"domain_name": NAME})
        foreign = parsed() | {"policy_published": {**parsed()["policy_published"], "domain": "stranger.test"}}
        first = await dmarc_ingest.store(Session, [parsed(), foreign])
        again = await dmarc_ingest.store(Session, [parsed()])
        async with Session() as s:
            rows = list((await s.execute(select(DmarcReport))).scalars())
        return first, again, [(r.org_name, r.pass_count, r.fail_count) for r in rows]
    assert run(go) == (1, 0, [("google.com", 3, 2)])


def _imap():
    host, port = os.environ["TEST_IMAP"].split(":")
    return host, int(port)


def _deliver(user: str, subject: str, body: str, attach: bytes | None):
    host, port = os.environ["TEST_GREENMAIL_SMTP"].split(":")
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = "noreply-dmarc-support@google.com", f"{user}@x.test", subject
    m.set_content(body)
    if attach:
        m.add_attachment(attach, maintype="application", subtype="xml", filename="google.com!acme-mail.test!1761091200!1761177599.xml")
    with smtplib.SMTP(host, int(port)) as s:
        s.send_message(m)


@needs_db
@needs_imap
def test_ingest_from_a_real_imap_mailbox_stores_the_report_and_archives_it(monkeypatch):
    user = f"a{uuid.uuid4().hex[:6]}"
    import httpx
    httpx.post(f"{os.environ['TEST_GREENMAIL_API']}/api/user", json={"login": user, "email": f"{user}@x.test", "password": "pw"}).raise_for_status()
    host, port = _imap()
    cfg = get_settings()
    for k, v in dict(dmarc_imap_host=host, dmarc_imap_port=port, dmarc_imap_ssl=False, dmarc_imap_user=user,
                     dmarc_imap_password="pw", dmarc_imap_folder="INBOX").items():
        monkeypatch.setattr(cfg, k, v)
    _deliver(user, "Report domain: acme-mail.test Submitter: google.com Report-ID: 1", "DMARC aggregate", XML.read_bytes())
    _deliver(user, "lunch?", "not a report", None)
    _deliver(user, "Report domain: acme-mail.test Submitter: google.com Report-ID: 2", "DMARC aggregate", b"<feedback><oops")  # malformed

    async def go(Session):
        await seed(Session, dom_kw={"domain_name": NAME})
        n = await dmarc_ingest.ingest_from_settings(Session)
        second = await dmarc_ingest.ingest_from_settings(Session)   # archived, so nothing left to read
        async with Session() as s:
            rows = list((await s.execute(select(DmarcReport))).scalars())
        return n, second, [(r.pass_count, r.fail_count) for r in rows]
    assert run(go) == (1, 0, [(3, 2)])   # the good report is stored; the malformed one and the chat message are skipped, not fatal


def test_no_mailbox_configured_is_a_quiet_zero(monkeypatch):
    monkeypatch.setattr(get_settings(), "dmarc_imap_host", "")
    assert asyncio.run(dmarc_ingest.ingest_from_settings(None)) == 0
