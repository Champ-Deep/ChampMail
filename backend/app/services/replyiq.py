"""ReplyIQ — campaign- + persona-level reply intelligence for ChampMail.

`reply_ingest` classifies ONE reply (intent/action) as it arrives. ReplyIQ is the
aggregation layer on top: across a batch of replies it computes the intent mix, the
positive-reply rate, and mines recurring OBJECTION themes — **per campaign and per
marketing persona** — so the outreach copy + cadence get tuned, not just the
prospect routed. This is the "listen/learn" half of the send rail (the awesome-
lead-generation list flags reply-intelligence as absent).

Deterministic + stdlib-only (no new dependency). Per-reply classification reuses
`reply_intent.classify_intent` when available (so ReplyIQ and the ingest gate
agree), else a local keyword fallback. Vendored like InboxLint; shared by design —
ChampConnect/ChampOps can call the same `analyze()`.

    analyze([(body, subject), ...])                 -> ReplyReport
    analyze_by_persona([(persona, body, subject)])  -> {persona: report_dict}
    from_service(reply_ingest_service)              -> ReplyReport over its recent replies
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

# Fallback classifier (priority order; negatives before positives) — only used when
# reply_intent is unavailable, so the two never disagree in production.
_RULES: list[tuple[str, re.Pattern]] = [
    ("unsubscribe", re.compile(r"\b(unsubscribe|remove me|take me off|stop emailing|opt.?out|do not (contact|email))\b", re.I)),
    ("auto_reply", re.compile(r"\b(out of office|automatic reply|auto.?reply|on (leave|vacation|holiday))\b", re.I)),
    ("referral", re.compile(r"\b(reach out to|right person|forward(ing)? (this|you)|loop in|cc'?ing|connect you with)\b", re.I)),
    ("not_interested", re.compile(r"\b(not interested|no th(ank)?s|we'?re (all set|good)|no need|already (have|sorted))\b", re.I)),
    ("not_now", re.compile(r"\b(not right now|next (quarter|year|month)|circle back|revisit|too early|q[1-4])\b", re.I)),
    ("objection", re.compile(r"\b(too expensive|pric(e|ing)|budget|we (use|have)|competitor|how is this different|already using|cost|not sure)\b", re.I)),
    ("meeting", re.compile(r"\b(book|calendar|schedule|set up a (call|time)|demo|let'?s (chat|talk|meet)|calendly)\b", re.I)),
    ("interested", re.compile(r"\b(interested|tell me more|sounds (good|interesting)|keen|send (me )?(more|info)|curious)\b", re.I)),
]

_POSITIVE = {"interested", "meeting"}
_OBJECTION = {"objection", "not_interested"}
_THEMES = {
    "price/budget": r"price|pricing|expensive|budget|cost",
    "incumbent": r"we (use|have)|already|competitor|using",
    "timing": r"not (now|right)|later|next quarter|too early",
    "differentiation": r"different|why|how is|not sure",
}


def classify(text: str, subject: str = "") -> str:
    """Single-reply intent. Reuses the ingest gate's classifier for consistency."""
    try:
        from app.services.reply_intent import classify_intent  # shared core
        return classify_intent(text, subject).intent.value
    except Exception:
        for intent, pat in _RULES:
            if pat.search(text or ""):
                return intent
        return "neutral"


@dataclass
class ReplyReport:
    total: int = 0
    intents: dict = field(default_factory=dict)
    positive_rate: float = 0.0
    objection_themes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"total": self.total, "intents": self.intents,
                "positive_rate": round(self.positive_rate, 3),
                "objection_themes": self.objection_themes}


def _themes(objection_texts: list[str]) -> list[dict]:
    out = []
    for theme, pat in _THEMES.items():
        n = sum(1 for t in objection_texts if re.search(pat, t, re.I))
        if n:
            out.append({"theme": theme, "count": n})
    return sorted(out, key=lambda x: -x["count"])


def _pair(item) -> tuple[str, str]:
    return item if isinstance(item, tuple) else (item, "")


def analyze(replies) -> ReplyReport:
    """Aggregate a batch of replies → intent mix + positive rate + objection themes.
    `replies` = iterable of (body, subject) tuples or plain body strings."""
    r = ReplyReport()
    objections: list[str] = []
    for item in replies:
        body, subject = _pair(item)
        intent = classify(body, subject)
        r.total += 1
        r.intents[intent] = r.intents.get(intent, 0) + 1
        if intent in _OBJECTION:
            objections.append(body)
    if r.total:
        r.positive_rate = sum(r.intents.get(i, 0) for i in _POSITIVE) / r.total
    r.objection_themes = _themes(objections)
    return r


def analyze_by_persona(replies) -> dict:
    """Per-persona reports. `replies` = iterable of (persona, body, subject?).
    Different marketing personas (Economic Buyer / Champion / Technical Evaluator)
    object differently — segmenting tells you which copy to fix for whom."""
    buckets: dict[str, list] = defaultdict(list)
    for persona, body, *rest in replies:
        buckets[persona].append((body, rest[0] if rest else ""))
    return {p: analyze(items).to_dict() for p, items in buckets.items()}


def from_service(service) -> ReplyReport:
    """Report over the genuine replies a ReplyIngestService collected this run."""
    return analyze(getattr(service, "recent_replies", []))


if __name__ == "__main__":  # offline, deterministic self-check
    batch = [
        ("Not interested, too expensive for us right now", "re: idea"),
        ("We already use a competitor for this", "re: idea"),
        ("what's the pricing? seems costly", "re: idea"),
        ("book a demo please!", "re: idea"),
        ("interested, tell me more", "re: idea"),
        ("circle back in Q3", "re: idea"),
    ]
    rep = analyze(batch)
    assert rep.total == 6, rep.total
    assert rep.positive_rate > 0, rep.to_dict()       # meeting + interested
    assert rep.objection_themes, rep.to_dict()
    by = analyze_by_persona([
        ("Economic Buyer", "too expensive, no budget", ""),
        ("Economic Buyer", "pricing is high", ""),
        ("Champion", "love it, book a demo", ""),
    ])
    assert by["Economic Buyer"]["objection_themes"], by
    assert by["Champion"]["positive_rate"] > 0, by
    print("replyiq.py self-check OK")
    print("  intents:", rep.intents)
    print("  positive rate:", f"{rep.positive_rate:.0%}")
    print("  objection themes:", rep.objection_themes)
    print("  per-persona:", {k: v["objection_themes"] for k, v in by.items()})
