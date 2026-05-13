"""
DMARC aggregate report processor.

Gmail, Outlook, Yahoo send daily XML reports to your rua= address.
This task fetches them via IMAP, parses the XML, stores summaries in DB,
and alerts if SPF/DKIM failure rates spike.
"""

import asyncio
import email
import gzip
import imaplib
import io
import logging
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime

from celery import shared_task

logger = logging.getLogger(__name__)

# Alert threshold: if DKIM or SPF pass rate drops below this, send alert
PASS_RATE_ALERT_THRESHOLD = 0.95


def _parse_dmarc_xml(xml_bytes: bytes) -> dict:
    """Parse a DMARC aggregate report XML into a summary dict."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        logger.error("DMARC XML parse error: %s", e)
        return {}

    report_metadata = root.find("report_metadata")
    policy_domain = root.findtext("policy_published/domain") or ""

    total = 0
    dkim_pass = 0
    spf_pass = 0
    dkim_fail_ips = []

    for record in root.findall("record"):
        count = int(record.findtext("row/count") or 1)
        total += count

        dkim_result = record.findtext("row/policy_evaluated/dkim") or ""
        spf_result = record.findtext("row/policy_evaluated/spf") or ""
        source_ip = record.findtext("row/source_ip") or ""

        if dkim_result.lower() == "pass":
            dkim_pass += count
        else:
            dkim_fail_ips.append(source_ip)

        if spf_result.lower() == "pass":
            spf_pass += count

    return {
        "domain": policy_domain,
        "total_messages": total,
        "dkim_pass": dkim_pass,
        "dkim_fail": total - dkim_pass,
        "dkim_pass_rate": round(dkim_pass / total, 4) if total else 0,
        "spf_pass": spf_pass,
        "spf_fail": total - spf_pass,
        "spf_pass_rate": round(spf_pass / total, 4) if total else 0,
        "dkim_fail_ips": list(set(dkim_fail_ips)),
        "report_date": datetime.utcnow().isoformat(),
    }


def _extract_xml_from_attachment(part) -> bytes | None:
    """Extract XML bytes from .zip or .gz attachment."""
    payload = part.get_payload(decode=True)
    if not payload:
        return None

    filename = part.get_filename() or ""

    if filename.endswith(".zip"):
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as zf:
                for name in zf.namelist():
                    if name.endswith(".xml"):
                        return zf.read(name)
        except Exception:
            return None

    if filename.endswith(".gz"):
        try:
            return gzip.decompress(payload)
        except Exception:
            return None

    if filename.endswith(".xml"):
        return payload

    return None


@shared_task(bind=True, queue="domain")
def process_dmarc_reports(self):
    """
    Fetches unread DMARC report emails, parses XML, logs summaries, alerts on failures.
    Runs daily via Celery beat.
    """
    async def _process():
        from app.core.config import settings

        imap_host = settings.imap_host
        imap_user = settings.imap_username
        imap_pass = settings.imap_password
        dmarc_email = settings.dmarc_report_email

        if not all([imap_host, imap_user, imap_pass]):
            logger.warning("DMARC processing skipped — IMAP not configured")
            return

        try:
            server = imaplib.IMAP4_SSL(imap_host, settings.imap_port)
            server.login(imap_user, imap_pass)
            server.select("INBOX")

            # Search for DMARC report emails (from noreply-dmarc-support@google.com etc.)
            _, message_numbers = server.search(None, "UNSEEN", "SUBJECT", '"Report domain:"')
            ids = message_numbers[0].split()

            reports = []
            for msg_id in ids:
                _, msg_data = server.fetch(msg_id, "(RFC822)")
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)

                for part in msg.walk():
                    xml_bytes = _extract_xml_from_attachment(part)
                    if xml_bytes:
                        summary = _parse_dmarc_xml(xml_bytes)
                        if summary:
                            reports.append(summary)

                            # Alert on low pass rates
                            if summary["dkim_pass_rate"] < PASS_RATE_ALERT_THRESHOLD:
                                logger.error(
                                    "DMARC ALERT: %s DKIM pass rate %.1f%% (fail IPs: %s)",
                                    summary["domain"],
                                    summary["dkim_pass_rate"] * 100,
                                    summary["dkim_fail_ips"],
                                )
                            if summary["spf_pass_rate"] < PASS_RATE_ALERT_THRESHOLD:
                                logger.error(
                                    "DMARC ALERT: %s SPF pass rate %.1f%%",
                                    summary["domain"],
                                    summary["spf_pass_rate"] * 100,
                                )
                            else:
                                logger.info(
                                    "DMARC OK: %s — DKIM %.1f%% SPF %.1f%% (%d msgs)",
                                    summary["domain"],
                                    summary["dkim_pass_rate"] * 100,
                                    summary["spf_pass_rate"] * 100,
                                    summary["total_messages"],
                                )

                # Mark as read
                server.store(msg_id, "+FLAGS", "\\Seen")

            server.logout()
            logger.info("DMARC processing complete: %d reports parsed", len(reports))

        except Exception as e:
            logger.error("DMARC processing failed: %s", e)

    asyncio.run(_process())
