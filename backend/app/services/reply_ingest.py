"""Inbound reply ingestion + prospect-level auto-pause.

Polls connected mailboxes for inbound mail and, for each message:
  1. discriminates bounce vs auto-reply (OOO) vs genuine human reply;
  2. matches a genuine reply back to the originating send via In-Reply-To /
     References → the stored outbound Message-ID;
  3. pauses ONLY that prospect's remaining sequence steps (not the whole
     campaign), and — if the reply text is an opt-out — suppresses the address.

The classification + thread-matching cores are pure (no IMAP, no DB) so they are
unit-tested offline; `ReplyIngestService` wraps them with an injectable mailbox
client and a pause callback.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Iterable, Optional, Protocol


class InboundKind(str, Enum):
    BOUNCE = "bounce"
    AUTO_REPLY = "auto_reply"   # out-of-office / vacation / system auto-response
    REPLY = "reply"            # genuine human reply


_OOO_SUBJECT = re.compile(
    r"^\s*(out of office|automatic reply|auto[\s-]?reply|auto:|abwesenheit|"
    r"on vacation|away from)\b", re.IGNORECASE,
)
_OPTOUT_RE = re.compile(
    r"\b(unsubscribe|remove me|opt[\s-]?out|take me off|stop emailing|do not (?:contact|email))\b",
    re.IGNORECASE,
)
_MSGID_RE = re.compile(r"<[^>]+>")


def classify_inbound(*, return_path: str, auto_submitted: str, subject: str,
                     precedence: str = "") -> InboundKind:
    """Discriminate inbound mail. Order matters: bounces and automated mail must
    be excluded before anything is treated as a real reply (RFC 3834)."""
    # Bounce: a null Return-Path (<>) is the canonical DSN envelope sender.
    if return_path.strip() in ("<>", "<>;", "<MAILER-DAEMON>", ""):
        # empty return-path or none -> treat as bounce only when also empty-ish
        if return_path.strip() in ("<>", "<>;", "<MAILER-DAEMON>"):
            return InboundKind.BOUNCE
    # Automated: Auto-Submitted header (anything but "no") or bulk precedence.
    if auto_submitted and auto_submitted.strip().lower() not in ("no", ""):
        return InboundKind.AUTO_REPLY
    if precedence.strip().lower() in ("auto_reply", "bulk", "junk"):
        return InboundKind.AUTO_REPLY
    if _OOO_SUBJECT.search(subject or ""):
        return InboundKind.AUTO_REPLY
    return InboundKind.REPLY


def is_optout(body: str) -> bool:
    """A free-text opt-out request must be honored even without a header click."""
    return bool(_OPTOUT_RE.search(body or ""))


def match_thread(in_reply_to: str, references: str, known_ids: set[str]) -> Optional[str]:
    """Return the outbound Message-ID this reply belongs to, or None.

    Prefers In-Reply-To; falls back to the most recent matching id in References.
    Ids are compared with angle brackets stripped, case-insensitively."""
    norm = {k.strip("<> ").lower() for k in known_ids}

    def _hit(token: str) -> Optional[str]:
        t = token.strip("<> ").lower()
        return t if t in norm else None

    for tok in _MSGID_RE.findall(in_reply_to or ""):
        if h := _hit(tok):
            return h
    # References lists oldest→newest; scan newest first.
    refs = _MSGID_RE.findall(references or "")
    for tok in reversed(refs):
        if h := _hit(tok):
            return h
    return None


# --- service wrapper (I/O-bound; injectable for tests) -------------------------

@dataclass
class InboundMessage:
    return_path: str
    auto_submitted: str
    precedence: str
    subject: str
    in_reply_to: str
    references: str
    from_addr: str
    body: str


class MailboxClient(Protocol):
    def fetch_unseen(self) -> Iterable[InboundMessage]: ...


@dataclass
class ReplyOutcome:
    kind: InboundKind
    matched_message_id: Optional[str]
    optout: bool
    from_addr: str
    intent: Optional[str] = None          # reply-intent (set for genuine REPLYs)
    intent_action: Optional[str] = None   # recommended routing action


class ReplyIngestService:
    """Drives reply ingestion. `resolve_message_ids` returns the set of known
    outbound Message-IDs (e.g. recent send_logs); `on_reply` pauses the prospect's
    sequence; `on_optout` suppresses. All injected so the loop is testable."""

    def __init__(
        self,
        client: MailboxClient,
        resolve_message_ids: Callable[[], set[str]],
        on_reply: Callable[[str, str], None],   # (message_id, from_addr)
        on_optout: Callable[[str], None],        # (from_addr)
    ) -> None:
        self.client = client
        self.resolve_message_ids = resolve_message_ids
        self.on_reply = on_reply
        self.on_optout = on_optout
        # ReplyIQ feed: genuine replies (body, subject) collected each run for the
        # campaign/persona-level intelligence layer (services/replyiq.py).
        self.recent_replies: list[tuple[str, str]] = []

    def run_once(self) -> list[ReplyOutcome]:
        known = self.resolve_message_ids()
        outcomes: list[ReplyOutcome] = []
        self.recent_replies = []  # reset the ReplyIQ batch for this run
        for m in self.client.fetch_unseen():
            kind = classify_inbound(
                return_path=m.return_path, auto_submitted=m.auto_submitted,
                subject=m.subject, precedence=m.precedence,
            )
            matched = None
            optout = False
            intent = intent_action = None
            if kind == InboundKind.REPLY:
                self.recent_replies.append((m.body, m.subject))  # feed ReplyIQ
                matched = match_thread(m.in_reply_to, m.references, known)
                if is_optout(m.body):
                    optout = True
                    self.on_optout(m.from_addr)
                elif matched:
                    # Genuine human reply → pause that prospect's remaining steps.
                    self.on_reply(matched, m.from_addr)
                # Classify intent on any genuine reply so the floor can route
                # (meeting→book, interested→rep, objection→handle, not-interested→suppress).
                try:
                    from app.services.reply_intent import classify_intent
                    ir = classify_intent(m.body, m.subject)
                    intent, intent_action = ir.intent.value, ir.action.value
                except Exception:
                    pass
            outcomes.append(ReplyOutcome(kind=kind, matched_message_id=matched,
                                         optout=optout, from_addr=m.from_addr,
                                         intent=intent, intent_action=intent_action))
        return outcomes
