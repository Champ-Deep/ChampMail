"""Suppression list — centralized, team-scoped do-not-contact.

A prospect that bounces, complains, or unsubscribes in ONE campaign must never be
emailed again from ANY campaign for that team. ChampMail previously tracked
unsubscribe/bounce only as per-prospect status flags; this is the cross-campaign
suppression backbone the send path consults before every dispatch (a hard
requirement for compliant bulk sending — Gmail/Yahoo bulk-sender rules cap
complaint rates, and CAN-SPAM/DPDP require honoring opt-outs).
"""
from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint, Index, text
from sqlalchemy.dialects.postgresql import UUID

from app.db.postgres import Base


class Suppression(Base):
    """A single suppressed address, scoped to a team (or global when team_id IS NULL)."""

    __tablename__ = "suppressions"
    __table_args__ = (
        UniqueConstraint("team_id", "email", name="uq_suppression_team_email"),
        Index("ix_suppression_team_email", "team_id", "email"),
        # Global suppression (team_id IS NULL) is single-rowed per email so one
        # global opt-out suppresses every team (plan Q6 — NULLs are distinct in a
        # plain unique constraint, hence a partial unique index).
        Index("uq_suppression_global_email", "email", unique=True,
              postgresql_where=text("team_id IS NULL")),
        Index("ix_suppression_person", "person_id"),
        Index("ix_suppression_sha256", "email_sha256"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=True, index=True)
    email = Column(String(320), nullable=False, index=True)

    # Person-awareness (plan Q7): an opt-out follows the human across job changes /
    # email changes; email_sha256 allows privacy-preserving match + storage.
    person_id = Column(UUID(as_uuid=True), nullable=True)
    email_sha256 = Column(String(64), nullable=True)

    # why the address is suppressed
    reason = Column(String(32), nullable=False, default="manual")
    # bounce_hard | bounce_soft_exhausted | complaint | unsubscribe | manual | reply_optout

    # where the suppression came from (campaign id, "tracking", "imap", "import", …)
    source = Column(String(255), nullable=True)
    note = Column(String(500), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
