"""Suppression service — the gate every send must pass through.

`is_suppressed` is checked in the send path before dispatch; `add` is called from
the unsubscribe handler, the bounce processor, and complaint webhooks so an
opt-out anywhere suppresses everywhere.

Two correctness rules from the design grilling (plan Q6/Q7):
  - team scope = `team_id == team OR team_id IS NULL` — a GLOBAL suppression
    (team_id NULL) blocks every team, not just one.
  - person-aware = match on canonical `email OR person_id`, so an opt-out follows
    the human across job/email changes. Addresses are canonicalized (lowercased,
    +tag stripped, gmail dots removed) so tagged/dotted variants can't slip past.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Iterable

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.suppression import Suppression

logger = logging.getLogger(__name__)

_GMAIL = {"gmail.com", "googlemail.com"}


def _canon(email: str) -> str:
    """Canonicalize for matching: lowercase + trim, strip the +tag (suppression
    honors the base address), and for gmail drop dots + fold googlemail→gmail."""
    e = (email or "").strip().lower()
    if "@" not in e:
        return e
    local, _, domain = e.partition("@")
    local = local.split("+", 1)[0]  # plus-addressing → base address
    if domain in _GMAIL:
        local = local.replace(".", "")  # gmail ignores dots
        domain = "gmail.com"
    return f"{local}@{domain}" if local else e


def _sha256(canon_email: str) -> str:
    return hashlib.sha256(canon_email.encode()).hexdigest()


class SuppressionService:
    async def is_suppressed(
        self, session: AsyncSession, team_id, email: str, person_id=None
    ) -> bool:
        email = _canon(email)
        if not email:
            return True  # never send to an empty address
        ident = [Suppression.email == email]
        if person_id is not None:
            ident.append(Suppression.person_id == person_id)
        stmt = (
            select(Suppression.id)
            .where(or_(*ident))
            .where(or_(Suppression.team_id == team_id, Suppression.team_id.is_(None)))
            .limit(1)
        )
        result = await session.execute(stmt)
        return result.first() is not None

    async def filter_sendable(
        self, session: AsyncSession, team_id, emails: Iterable[str]
    ) -> set[str]:
        """Return the subset of `emails` (originals) that are NOT suppressed —
        matched on the canonical form, against this team OR a global suppression."""
        pairs = {}
        for e in emails:
            c = _canon(e)
            if c:
                pairs.setdefault(c, e)
        if not pairs:
            return set()
        stmt = (
            select(Suppression.email)
            .where(Suppression.email.in_(set(pairs)))
            .where(or_(Suppression.team_id == team_id, Suppression.team_id.is_(None)))
        )
        rows = await session.execute(stmt)
        suppressed = {r[0] for r in rows.all()}
        return {orig for canon, orig in pairs.items() if canon not in suppressed}

    async def add(
        self,
        session: AsyncSession,
        team_id,
        email: str,
        reason: str = "manual",
        source: str | None = None,
        note: str | None = None,
        person_id=None,
    ) -> bool:
        """Idempotently suppress an address. Returns True if newly added.
        ON CONFLICT DO NOTHING (no target) covers both the team unique constraint
        and the partial global-unique index."""
        email = _canon(email)
        if not email:
            return False
        stmt = (
            pg_insert(Suppression)
            .values(
                team_id=team_id,
                email=email,
                email_sha256=_sha256(email),
                person_id=person_id,
                reason=reason,
                source=source,
                note=note,
            )
            .on_conflict_do_nothing()
            .returning(Suppression.id)
        )
        result = await session.execute(stmt)
        await session.commit()
        added = result.first() is not None
        if added:
            logger.info("suppressed %s (team=%s reason=%s)", email, team_id, reason)
        return added

    async def remove(self, session: AsyncSession, team_id, email: str) -> None:
        """Re-permit an address (e.g. a re-confirmed opt-in)."""
        from sqlalchemy import delete

        email = _canon(email)
        stmt = delete(Suppression).where(Suppression.email == email)
        if team_id is not None:
            stmt = stmt.where(Suppression.team_id == team_id)
        await session.execute(stmt)
        await session.commit()


suppression_service = SuppressionService()


if __name__ == "__main__":  # pure self-check for the canonicalizer (no DB)
    assert _canon("Foo.Bar+promo@Gmail.com") == "foobar@gmail.com", _canon("Foo.Bar+promo@Gmail.com")
    assert _canon("a.b.c@googlemail.com") == "abc@gmail.com"
    assert _canon("User+x@Acme.CO") == "user@acme.co"   # non-gmail: dots kept, tag stripped
    assert _canon("  Plain@Example.com ") == "plain@example.com"
    assert _canon("notanemail") == "notanemail"
    assert _sha256(_canon("foo@gmail.com")) == _sha256("foo@gmail.com")
    print("suppression_service canon self-check OK")
