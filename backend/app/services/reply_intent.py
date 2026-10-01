"""Reply-intent classifier — what a genuine human reply MEANS, and what to do next.

reply_ingest.py already discriminates bounce vs auto-reply (OOO) vs genuine human
reply, and auto-pauses + suppresses opt-outs. This adds the next layer: once a reply
is a genuine REPLY, classify its INTENT and recommend an action, so the SDR floor /
Champ IQ can route automatically (interested -> human/booking, objection -> handle,
not-interested -> suppress, referral -> re-target).

Pure + deterministic heuristic core (no LLM, no I/O) so it's unit-tested and runs on
the ingest hot path. `classify_intent_llm` is an optional hook for a model upgrade.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple


class Intent(str, Enum):
    MEETING = "meeting"            # wants to book / pick a time
    INTERESTED = "interested"     # positive, wants more
    QUESTION = "question"         # asking something before committing
    OBJECTION = "objection"       # not now / no budget / already have / send info
    NOT_INTERESTED = "not_interested"
    UNSUBSCRIBE = "unsubscribe"   # hard opt-out
    REFERRAL = "referral"         # not me, talk to X
    UNKNOWN = "unknown"


class Action(str, Enum):
    BOOK_MEETING = "book_meeting"        # hand to CloudMeet / scheduler
    ROUTE_HUMAN = "route_to_human"       # escalate to a rep
    HANDLE_OBJECTION = "handle_objection"
    ANSWER = "answer_question"
    RETARGET_REFERRAL = "retarget_referral"
    SUPPRESS = "suppress"                # add to suppression list, stop
    REVIEW = "review"


# Ordered patterns — first strong match wins (most decisive intents first).
_PATTERNS: List[Tuple[Intent, re.Pattern]] = [
    (Intent.UNSUBSCRIBE, re.compile(r"\b(unsubscribe|remove me|take me off|stop (emailing|contacting)|"
                                    r"do not (contact|email)|opt[\s-]?out|leave me alone)\b", re.I)),
    (Intent.NOT_INTERESTED, re.compile(r"\b(not interested|no thanks|no thank you|not a fit|"
                                       r"we'?re good|pass\b|not for us|no need)\b", re.I)),
    (Intent.REFERRAL, re.compile(r"\b(talk to|reach out to|right person is|you (?:should|want) to (?:speak|talk)|"
                                 r"forward(?:ed|ing)? (?:this )?to|cc'?ing|wrong person|not my (?:area|department)|"
                                 r"better (?:person|contact))\b", re.I)),
    (Intent.MEETING, re.compile(r"\b(book|schedule|calendar|what time|when (?:are|can|works)|"
                                r"available|set up a (?:call|time)|grab (?:some )?time|happy to (?:chat|jump on)|"
                                r"let'?s (?:do|set up) (?:a )?(?:call|meeting|time)|send (?:me )?(?:a )?(?:link|invite))\b", re.I)),
    (Intent.INTERESTED, re.compile(r"\b(interested|tell me more|sounds (?:good|interesting|great)|"
                                   r"learn more|keen|would love to|yes,? (?:please|let'?s)|count me in|"
                                   r"this (?:is|looks) (?:relevant|interesting|useful))\b", re.I)),
    (Intent.OBJECTION, re.compile(r"\b(not (?:the )?right time|no budget|already (?:have|use|using|got)|"
                                  r"too expensive|circle back|next (?:quarter|year)|check back|"
                                  r"send (?:me )?(?:more )?(?:info|information|details|a deck)|using (?:a )?competitor|"
                                  r"we use\b|busy right now)\b", re.I)),
]


@dataclass
class IntentResult:
    intent: Intent
    confidence: float
    action: Action
    matched: str = ""

    def as_dict(self):
        return {"intent": self.intent.value, "confidence": round(self.confidence, 2),
                "action": self.action.value, "matched": self.matched}


_ACTION = {
    Intent.MEETING: Action.BOOK_MEETING,
    Intent.INTERESTED: Action.ROUTE_HUMAN,
    Intent.QUESTION: Action.ANSWER,
    Intent.OBJECTION: Action.HANDLE_OBJECTION,
    Intent.NOT_INTERESTED: Action.SUPPRESS,
    Intent.UNSUBSCRIBE: Action.SUPPRESS,
    Intent.REFERRAL: Action.RETARGET_REFERRAL,
    Intent.UNKNOWN: Action.REVIEW,
}


def _strip_quoted(text: str) -> str:
    """Drop quoted history (lines after 'On ... wrote:' or leading '>')."""
    out = []
    for line in (text or "").splitlines():
        if re.match(r"\s*On .+wrote:\s*$", line) or line.strip().startswith(">"):
            break
        out.append(line)
    return "\n".join(out)


def classify_intent(body: str, subject: str = "") -> IntentResult:
    text = _strip_quoted(body or "")
    hay = f"{subject}\n{text}"
    for intent, pat in _PATTERNS:
        m = pat.search(hay)
        if m:
            # confidence: strong base, lifted a touch for short/direct replies
            conf = 0.8 if len(text.split()) <= 60 else 0.7
            return IntentResult(intent, conf, _ACTION[intent], matched=m.group(0))
    # fallback: a bare question with no decisive phrase
    if "?" in text:
        return IntentResult(Intent.QUESTION, 0.55, Action.ANSWER, matched="?")
    return IntentResult(Intent.UNKNOWN, 0.3, Action.REVIEW)


def classify_intent_llm(body: str, subject: str, llm_chat) -> IntentResult:
    """Optional model upgrade. `llm_chat(messages)->str`. Falls back to heuristic on any error."""
    base = classify_intent(body, subject)
    if llm_chat is None:
        return base
    try:
        labels = ", ".join(i.value for i in Intent if i != Intent.UNKNOWN)
        msg = [{"role": "system", "content": f"Classify the reply's intent as exactly one of: {labels}. "
                                             "Answer with only the label."},
               {"role": "user", "content": f"Subject: {subject}\n\n{_strip_quoted(body)[:1500]}"}]
        out = (llm_chat(msg) or "").strip().lower()
        for i in Intent:
            if i.value in out:
                return IntentResult(i, 0.85, _ACTION[i], matched="llm")
    except Exception:
        pass
    return base


if __name__ == "__main__":  # self-check
    cases = [
        ("Yes, this is relevant — happy to jump on a call. What time works Thursday?", Intent.MEETING),
        ("Interested, tell me more.", Intent.INTERESTED),
        ("Not the right time, we already use Apollo. Circle back next quarter.", Intent.OBJECTION),
        ("Please remove me from your list.", Intent.UNSUBSCRIBE),
        ("Not interested, thanks.", Intent.NOT_INTERESTED),
        ("I'm not the right person — reach out to our RevOps lead Siddharth.", Intent.REFERRAL),
        ("How does your data compare to ZoomInfo?", Intent.QUESTION),
    ]
    ok = 0
    for body, expect in cases:
        r = classify_intent(body)
        flag = "ok " if r.intent == expect else "FAIL"
        if r.intent == expect:
            ok += 1
        print(f"  [{flag}] {r.intent.value:15} -> {r.action.value:18} | {body[:42]}")
    # quoted-history must not leak old intent
    q = classify_intent("Thanks!\n\nOn Mon, Deep wrote:\n> not interested at all")
    assert q.intent != Intent.NOT_INTERESTED, q
    print(f"\n{ok}/{len(cases)} intents correct; quoted-history stripped OK")
    assert ok >= len(cases) - 1
