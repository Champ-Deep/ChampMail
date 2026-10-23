"""DMARC ingestion over a mocked IMAP mailbox (no network, no GreenMail): fixture XML in, daily counts out."""
from __future__ import annotations

import logging
import os
from datetime import date
from email.message import EmailMessage
from pathlib import Path

import parsedmarc
import pytest
from parsedmarc.mail import MailboxConnection

from app.config import get_settings
from app.services import dmarc_ingest
from tests.test_send import run, seed

XML = (Path(__file__).parent / "fixtures" / "dmarc_aggregate.xml").read_text()
NAME, DAY = "acme-mail.test", date(2025, 10, 22)
pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set")


def mail(xml: str, n: int) -> str:
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = "noreply-dmarc-support@google.com", "rua@x.test", f"Report domain: {NAME} Submitter: google.com Report-ID: {n}"
    m.set_content("DMARC aggregate")
    m.add_attachment(xml.encode(), maintype="application", subtype="xml", filename=f"google.com!{NAME}!1761091200!1761177599-{n}.xml")
    return m.as_string()


class FakeMailbox(MailboxConnection):
    def __init__(self, *raw: str):
        self.folders = {"INBOX": dict(enumerate(raw))}

    def create_folder(self, name): self.folders.setdefault(name, {})
    def folder_exists(self, name): return name in self.folders
    def fetch_messages(self, folder, **_): return list(self.folders.get(folder, {}))
    def fetch_message(self, mid, **_): return self.folders["INBOX"][int(mid)]
    def delete_message(self, mid): self.folders["INBOX"].pop(int(mid), None)
    def move_message(self, mid, folder): self.folders.setdefault(folder, {})[int(mid)] = self.folders["INBOX"].pop(int(mid))
    def keepalive(self): pass


def ingest(monkeypatch, *boxes: FakeMailbox):
    """Run ingestion once per mailbox state, against one database. Returns ([new rows per run], fail count, top IPs, other-day fail count, IMAP kwargs)."""
    seen, queue = {}, list(boxes)
    monkeypatch.setattr(dmarc_ingest, "IMAPConnection", lambda **kw: seen.update(kw) or queue.pop(0))
    cfg = get_settings()
    for k, v in dict(dmarc_imap_host="imap.test", dmarc_imap_port=143, dmarc_imap_ssl=False, dmarc_imap_user="rua",
                     dmarc_imap_password="pw", dmarc_imap_folder="INBOX").items():
        monkeypatch.setattr(cfg, k, v)

    async def go(Session):
        await seed(Session, dom_kw={"domain_name": NAME})
        runs = []
        for _ in boxes:
            parsedmarc.SEEN_AGGREGATE_REPORT_IDS.clear()  # parsedmarc's in-process dedup cache; the DB key is what we test
            runs.append(await dmarc_ingest.ingest_from_settings(Session))
        return (runs, await dmarc_ingest.get_fail_count(Session, NAME, DAY), await dmarc_ingest.top_failing_ips(Session, NAME, DAY),
                await dmarc_ingest.get_fail_count(Session, NAME, date(2025, 1, 1)), seen)
    return run(go)


def test_fixture_report_gives_fail_count_and_top_failing_ips(monkeypatch):
    box = FakeMailbox(mail(XML, 1))
    runs, fails, ips, other_day, seen = ingest(monkeypatch, box)
    assert (runs, fails, ips, other_day) == ([1], 2, [("203.0.113.9", 2)], None)   # 3 pass / 2 fail rows; no report for another day
    assert (seen["host"], seen["port"], seen["user"], seen["ssl"]) == ("imap.test", 143, "rua", False)   # env reaches the IMAP login
    assert not box.folders["INBOX"] and len(box.folders["DMARC-processed/Aggregate"]) == 1               # processed mail is archived


def test_malformed_report_is_logged_and_skipped_while_valid_ones_ingest(monkeypatch, caplog):
    caplog.set_level(logging.WARNING)
    box = FakeMailbox(mail("<feedback><oops", 1), mail(XML.replace("17459823650123456789", "77"), 2))
    runs, fails, *_ = ingest(monkeypatch, box)
    assert (runs, fails) == ([1], 2)
    assert any("parsedmarc" in r.name and r.levelno >= logging.WARNING for r in caplog.records), "the malformed report left no log line"


def test_duplicate_report_does_not_double_count(monkeypatch):
    runs, fails, *_ = ingest(monkeypatch, FakeMailbox(mail(XML, 1)), FakeMailbox(mail(XML, 2)))   # same org + report_id delivered twice
    assert (runs, fails) == ([1, 0], 2)


def test_empty_mailbox_ingests_nothing(monkeypatch):
    runs, fails, ips, *_ = ingest(monkeypatch, FakeMailbox())
    assert (runs, fails, ips) == ([0], None, [])
