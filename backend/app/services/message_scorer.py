"""Message scorer — Lavender-style pre-send deliverability + quality coach.

Scores a cold email BEFORE it sends: spam-trigger words, length, reading grade,
link/image ratio, personalization, question presence, CTA clarity, subject quality,
shouting/punctuation. Returns a 0..1 score + per-dimension breakdown + concrete
suggestions. Pure + deterministic (no deps, no I/O) so it's unit-tested and safe to
call on the hot send path.

Two consumers:
  * ChampMail send/sequence — gate or warn on low-scoring drafts (protect reputation).
  * ChampOracle SSR sim — use the 0..1 score as the REAL content_quality signal,
    replacing the hardcoded 0.6 (champoracle backend/app/sim).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Dict, List

# Spam-trigger words/phrases (cold-email subset; weighted by how strongly they hurt).
_SPAM = {
    3: ["free", "100% free", "guarantee", "guaranteed", "act now", "limited time", "click here",
        "buy now", "order now", "$$$", "cash", "winner", "congratulations", "risk-free", "no cost",
        "earn money", "make money", "double your", "incredible deal", "best price"],
    2: ["offer", "discount", "promo", "deal", "save big", "exclusive", "urgent", "instant",
        "cheap", "amazing", "apply now", "sign up free", "trial", "bonus"],
    1: ["opportunity", "solution", "revolutionary", "cutting-edge", "synergy", "leverage", "unlock"],
}
_GREETING = re.compile(r"^\s*(hi|hey|hello|dear)\b", re.I)
_SIGNOFF = re.compile(r"\b(thanks|regards|cheers|best|sincerely|talk soon)\b", re.I)
_TOKEN = re.compile(r"\{\{[^}]+\}\}|\[\[?[A-Za-z_ ]+\]\]?|<[A-Za-z_ ]+>")  # un-rendered merge tags
_LINK = re.compile(r"https?://\S+")
_NAME = re.compile(r"\bhi\s+[A-Z][a-z]+", re.I)


@dataclass
class ScoreBreakdown:
    spam: float = 0.0
    length: float = 0.0
    readability: float = 0.0
    links: float = 0.0
    personalization: float = 0.0
    question: float = 0.0
    cta: float = 0.0
    subject: float = 0.0
    formatting: float = 0.0


@dataclass
class MessageScore:
    score: float                       # 0..1 overall (weighted)
    grade: str                         # A..F
    breakdown: ScoreBreakdown
    suggestions: List[str] = field(default_factory=list)
    stats: Dict[str, float] = field(default_factory=dict)

    def as_dict(self):
        d = asdict(self)
        return d


def _syllables(word: str) -> int:
    word = word.lower()
    vowels = "aeiouy"
    count, prev = 0, False
    for ch in word:
        is_v = ch in vowels
        if is_v and not prev:
            count += 1
        prev = is_v
    if word.endswith("e") and count > 1:
        count -= 1
    return max(1, count)


def _flesch_kincaid_grade(text: str) -> float:
    sentences = max(1, len(re.findall(r"[.!?]+", text)))
    words = re.findall(r"[A-Za-z']+", text)
    if not words:
        return 0.0
    syll = sum(_syllables(w) for w in words)
    return 0.39 * (len(words) / sentences) + 11.8 * (syll / len(words)) - 15.59


def score_email(subject: str, body: str) -> MessageScore:
    sug: List[str] = []
    b = ScoreBreakdown()
    text = body or ""
    low = text.lower()
    words = re.findall(r"[A-Za-z']+", text)
    n_words = len(words)

    # --- spam words (weighted) ---
    spam_hits = 0
    for weight, terms in _SPAM.items():
        for t in terms:
            if t in low:
                spam_hits += weight
    b.spam = max(0.0, 1.0 - spam_hits * 0.12)
    if spam_hits:
        flagged = [t for terms in _SPAM.values() for t in terms if t in low][:4]
        sug.append(f"Remove spam-trigger words: {', '.join(flagged)}")

    # --- length (ideal 50-125 words for cold email) ---
    if 50 <= n_words <= 125:
        b.length = 1.0
    elif n_words < 50:
        b.length = max(0.3, n_words / 50)
        sug.append(f"Body is short ({n_words} words) — aim 50-125 with one specific, relevant line")
    else:
        b.length = max(0.2, 1.0 - (n_words - 125) / 200)
        sug.append(f"Body is long ({n_words} words) — cut to 50-125; long cold emails get skimmed")

    # --- readability (ideal <= grade 7) ---
    grade = _flesch_kincaid_grade(text)
    b.readability = 1.0 if grade <= 7 else max(0.2, 1.0 - (grade - 7) * 0.1)
    if grade > 9:
        sug.append(f"Reading grade {grade:.0f} is high — shorten sentences, simpler words (aim grade 6-7)")

    # --- links (ideal 0-1 in a cold email) ---
    n_links = len(_LINK.findall(text))
    b.links = 1.0 if n_links <= 1 else max(0.2, 1.0 - (n_links - 1) * 0.3)
    if n_links > 1:
        sug.append(f"{n_links} links — cold emails with multiple links hurt deliverability; keep ≤1")

    # --- personalization ---
    unrendered = _TOKEN.findall(text) + _TOKEN.findall(subject or "")
    has_name = bool(_NAME.search(text))
    if unrendered:
        b.personalization = 0.0
        sug.append(f"Un-rendered merge tags will send literally: {unrendered[:3]} — render before send")
    elif has_name:
        b.personalization = 1.0
    else:
        b.personalization = 0.5
        sug.append("No personalization detected — reference the prospect's name/company/a specific signal")

    # --- question (a genuine question lifts replies) ---
    has_q = "?" in text
    b.question = 1.0 if has_q else 0.4
    if not has_q:
        sug.append("No question — end with one soft, specific ask to invite a reply")

    # --- CTA clarity (exactly one ask; many = decision fatigue) ---
    cta_phrases = len(re.findall(r"\b(book|schedule|call|demo|meeting|reply|interested|worth a|open to|grab time|chat)\b", low))
    if cta_phrases == 0:
        b.cta = 0.3
        sug.append("No clear CTA — add one low-friction ask (e.g. 'worth a quick look?')")
    elif cta_phrases <= 3:
        b.cta = 1.0
    else:
        b.cta = 0.5
        sug.append("Multiple competing CTAs — keep a single clear ask")

    # --- subject ---
    sub = subject or ""
    sw = len(sub.split())
    if not sub:
        b.subject = 0.0
        sug.append("Empty subject")
    elif sub.isupper():
        b.subject = 0.3
        sug.append("Subject is ALL CAPS — reads as spam; use sentence case")
    elif 2 <= sw <= 8 and len(sub) <= 55:
        b.subject = 1.0
    else:
        b.subject = 0.6
        sug.append(f"Subject is {sw} words / {len(sub)} chars — aim 2-8 words, lowercase, no punctuation")

    # --- formatting (shouting, excessive punctuation, missing greeting/signoff) ---
    fmt = 1.0
    if re.search(r"[!?]{2,}", text):
        fmt -= 0.3; sug.append("Remove repeated punctuation (!!/??) — spammy")
    caps = [w for w in words if len(w) > 2 and w.isupper()]
    if len(caps) >= 2:
        fmt -= 0.3; sug.append(f"Avoid ALL-CAPS words ({', '.join(caps[:3])})")
    if not _GREETING.search(text):
        fmt -= 0.2; sug.append("Add a short greeting (Hi {name})")
    if not _SIGNOFF.search(text):
        fmt -= 0.1
    b.formatting = max(0.0, fmt)

    # --- weighted overall ---
    weights = {"spam": .18, "length": .12, "readability": .10, "links": .10,
               "personalization": .16, "question": .08, "cta": .10, "subject": .10, "formatting": .06}
    bd = asdict(b)
    score = sum(bd[k] * w for k, w in weights.items())
    grade_letter = "A" if score >= .9 else "B" if score >= .8 else "C" if score >= .65 else "D" if score >= .5 else "F"
    return MessageScore(
        score=round(score, 3), grade=grade_letter, breakdown=b,
        suggestions=sug,
        stats={"words": n_words, "links": n_links, "reading_grade": round(grade, 1),
               "spam_weight": spam_hits, "has_question": float(has_q)},
    )


def content_quality(subject: str, body: str) -> float:
    """0..1 signal for ChampOracle SSR (replaces the hardcoded content_quality=0.6)."""
    return score_email(subject, body).score


if __name__ == "__main__":  # self-check / demo
    good = score_email(
        "quick question on your Q3 pipeline",
        "Hi Priya, saw Helios is scaling the SDR team. Teams your size often see 10-15% of sends "
        "bounce, which quietly tanks domain reputation. We rebuild your list against live data before "
        "you sequence. Worth a quick look on your own data?\n\nThanks,\nDeep")
    bad = score_email(
        "FREE GUARANTEED LEADS!!! ACT NOW",
        "CLICK HERE for our 100% free risk-free amazing offer!!! Limited time only. "
        "Buy now and SAVE BIG $$$. http://a.com http://b.com http://c.com Visit {{company}} now!!!")
    assert good.score > 0.75, good
    assert bad.score < 0.4, bad
    assert good.grade in ("A", "B") and bad.grade in ("D", "F")
    assert any("spam" in s.lower() for s in bad.suggestions)
    print(f"GOOD: score={good.score} grade={good.grade}  stats={good.stats}")
    print(f"BAD:  score={bad.score} grade={bad.grade}")
    print("  bad suggestions:", bad.suggestions[:4])
    print("message_scorer.py self-check OK")
