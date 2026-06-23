"""InboxLint — pre-send compliance + deliverability gate (vendored into ChampMail).

The Champ-suite "send + deliverability" rail (Vision §3) protects an owned-reseller inbox
reputation moat. A single spammy / non-compliant blast can burn that domain reputation — the
exact asset the moat depends on. InboxLint is the pre-flight gate that stops it: every email is
checked for spam-triggers + CAN-SPAM/GDPR + deliverability risk BEFORE `mail_engine_client`
dispatches. `block` → don't send; `warn` → log; `pass` → proceed.

Deterministic + stdlib-only (no new dependency). Source of truth: github fork `inboxlint`; this
is a vendored copy so ChampMail stays self-contained. Shared by design — ChampConnect/ChampOps
can call the same `lint()`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_SPAM_WORDS = [
    "free", "guarantee", "guaranteed", "act now", "limited time", "click here", "buy now",
    "risk free", "100%", "cash", "earn money", "make money", "no cost", "winner", "congratulations",
    "urgent", "apply now", "order now", "cheap", "discount", "offer expires", "increase sales",
    "double your", "best price", "lowest price", "amazing", "incredible deal", "miracle",
]
_LINK = re.compile(r"https?://", re.I)
_IMG = re.compile(r"<img\b|\.(png|jpg|jpeg|gif)\b", re.I)
_UNSUB = re.compile(r"unsubscribe|opt.?out|stop receiving|email preferences", re.I)
_EXCLAM = re.compile(r"!")
_MONEY = re.compile(r"[$£€]\s?\d")


@dataclass
class Issue:
    rule: str
    severity: str
    message: str
    fix: str


@dataclass
class LintReport:
    score: int = 100
    level: str = "pass"
    issues: list = field(default_factory=list)

    def add(self, rule, severity, message, fix, penalty):
        self.issues.append(Issue(rule, severity, message, fix))
        self.score = max(0, self.score - penalty)

    def to_dict(self):
        return {"score": self.score, "level": self.level,
                "issues": [vars(i) for i in self.issues]}


def lint(subject: str, body: str, *, has_unsubscribe=None,
         has_physical_address: bool = False, is_cold: bool = True) -> LintReport:
    r = LintReport()
    text = f"{subject}\n{body}"
    low = text.lower()

    hits = [w for w in _SPAM_WORDS if re.search(r"\b" + re.escape(w) + r"\b", low)]
    if hits:
        r.add("spam-words", "warn" if len(hits) < 3 else "block",
              f"spam-trigger phrases: {', '.join(hits[:6])}", "rephrase to plain language",
              min(40, 8 * len(hits)))

    caps_words = [w for w in re.findall(r"[A-Za-z]{3,}", subject + " " + body) if w.isupper()]
    if len(caps_words) >= 2:
        r.add("all-caps", "warn", f"{len(caps_words)} ALL-CAPS words", "use normal case",
              min(20, 5 * len(caps_words)))
    excl = len(_EXCLAM.findall(text))
    if excl >= 2:
        r.add("exclamation", "warn", f"{excl} exclamation marks", "at most one", min(15, 5 * excl))
    if _MONEY.search(text):
        r.add("money", "warn", "money amount in copy", "lead with value, not price", 10)

    links = len(_LINK.findall(body))
    if links > 2:
        r.add("links", "warn", f"{links} links (≤1-2 for cold)", "keep one CTA link",
              min(25, 8 * (links - 2)))
    words = max(1, len(re.findall(r"\w+", body)))
    if _IMG.search(body) and words < 30:
        r.add("image-heavy", "block", "image-heavy with little text", "lead with plain text", 30)

    if not subject.strip():
        r.add("subject-empty", "block", "empty subject", "add a specific subject", 40)
    elif len(subject) > 70:
        r.add("subject-long", "warn", f"subject {len(subject)} chars (>70)", "tighten to ≤50", 10)
    if re.search(r"\bre:\s", subject, re.I) and is_cold:
        r.add("deceptive-subject", "block", "fake 'Re:' on a cold email (CAN-SPAM deceptive)",
              "use an honest subject", 35)

    has_unsub = _UNSUB.search(body) is not None if has_unsubscribe is None else has_unsubscribe
    if is_cold and not has_unsub:
        r.add("can-spam-unsub", "block", "no unsubscribe / opt-out (CAN-SPAM)",
              "add a working unsubscribe line", 35)
    if is_cold and not has_physical_address:
        r.add("can-spam-address", "warn", "no physical mailing address (CAN-SPAM)",
              "add postal address to footer", 15)

    if any(i.severity == "block" for i in r.issues) or r.score < 50:
        r.level = "block"
    elif r.issues:
        r.level = "warn"
    return r
