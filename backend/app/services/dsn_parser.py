"""RFC 3464 DSN (Delivery Status Notification) bounce parser.

Bounces arrive as a multipart/report; the machine-readable truth is the
`message/delivery-status` part, NOT the human-readable text. This parses that
part per RFC 3464/3463 and classifies each recipient as a hard (5.x.x) or soft
(4.x.x) failure so the bounce processor can suppress hard bounces immediately and
retry-then-suppress soft ones. Pure stdlib (no app imports) so it is unit-tested
offline.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from email import message_from_bytes, message_from_string
from email.message import Message


@dataclass
class BounceRecord:
    recipient: str
    action: str            # failed | delayed | delivered | relayed | expanded
    status: str            # RFC 3463 "class.subject.detail", e.g. "5.1.1"
    diagnostic: str        # the SMTP reply / diagnostic code
    classification: str    # hard | soft | other

    @property
    def is_hard(self) -> bool:
        return self.classification == "hard"


_STATUS_RE = re.compile(r"\b([245])\.\d{1,3}\.\d{1,3}\b")
_ADDR_RE = re.compile(r"<?([^<>\s;]+@[^<>\s;]+)>?")


def _classify(status: str, action: str) -> str:
    if status.startswith("5"):
        return "hard"
    if status.startswith("4"):
        return "soft"
    if action == "failed":
        return "hard"
    return "other"


def _addr(value: str) -> str:
    # Final-Recipient: rfc822; user@host
    if ";" in value:
        value = value.split(";", 1)[1]
    m = _ADDR_RE.search(value)
    return m.group(1).strip().lower() if m else value.strip().lower()


def _record_from_fields(fields: dict[str, str]) -> BounceRecord | None:
    if "final-recipient" not in fields and "original-recipient" not in fields:
        return None
    recipient = _addr(fields.get("final-recipient") or fields.get("original-recipient", ""))
    action = (fields.get("action") or "").lower()
    status = fields.get("status", "")
    diag = fields.get("diagnostic-code", "")
    if not status:
        m = _STATUS_RE.search(diag)
        status = m.group(0) if m else ""
    return BounceRecord(recipient=recipient, action=action, status=status,
                        diagnostic=diag, classification=_classify(status, action))


def _parse_status_part(part: Message) -> list[BounceRecord]:
    """Parse a message/delivery-status body. Python's email module parses this
    type into a LIST of sub-Messages (one per RFC 3464 field-group), so handle
    that first; fall back to raw-text splitting for odd encodings."""
    payload = part.get_payload()
    if isinstance(payload, list):
        records: list[BounceRecord] = []
        for block in payload:
            fields = {k.lower(): v for k, v in block.items()}
            if rec := _record_from_fields(fields):
                records.append(rec)
        if records:
            return records

    decoded = part.get_payload(decode=True)
    text = decoded.decode("utf-8", "replace") if decoded else payload
    if not isinstance(text, str):
        return []

    # Split into field-groups on blank lines.
    groups = re.split(r"\n\s*\n", text.strip())
    records: list[BounceRecord] = []
    for g in groups:
        fields: dict[str, str] = {}
        for line in g.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                fields[k.strip().lower()] = v.strip()
        if "final-recipient" not in fields and "original-recipient" not in fields:
            continue  # per-message group, skip
        recipient = _addr(fields.get("final-recipient") or fields.get("original-recipient", ""))
        action = (fields.get("action") or "").lower()
        status = fields.get("status", "")
        diag = fields.get("diagnostic-code", "")
        if not status:
            m = _STATUS_RE.search(diag)
            status = m.group(0) if m else ""
        records.append(BounceRecord(
            recipient=recipient, action=action, status=status,
            diagnostic=diag, classification=_classify(status, action),
        ))
    return records


def parse_dsn(raw) -> list[BounceRecord]:
    """Parse a raw DSN message (bytes or str) into per-recipient BounceRecords.

    Falls back to scanning the whole message for a status code + address when no
    structured delivery-status part is present (non-standard bounces)."""
    msg = message_from_bytes(raw) if isinstance(raw, (bytes, bytearray)) else message_from_string(raw)

    records: list[BounceRecord] = []
    for part in msg.walk():
        if part.get_content_type() == "message/delivery-status":
            records.extend(_parse_status_part(part))

    if records:
        return records

    # Fallback: best-effort scrape (some MTAs emit non-RFC bounces).
    body = msg.get_payload(decode=True)
    text = body.decode("utf-8", "replace") if body else str(msg.get_payload())
    sm = _STATUS_RE.search(text)
    am = _ADDR_RE.search(text)
    if sm and am:
        status = sm.group(0)
        records.append(BounceRecord(
            recipient=am.group(1).lower(), action="failed", status=status,
            diagnostic=text[:200], classification=_classify(status, "failed"),
        ))
    return records
