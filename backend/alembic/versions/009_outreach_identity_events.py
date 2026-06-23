"""Outreach hardening: suppression list + prospect identity spine.

Revision ID: 009_outreach_identity
Revises: 008_add_job_title
Create Date: 2026-06-12

Adds:
  - `suppressions` table (centralized, team-scoped do-not-contact; the send-path
    gate consults it before every dispatch).
  - identity-spine columns on `prospects`: person_id, account_id, external_ids —
    so prospects are no longer email-keyed islands and join with the rest of the
    Champ suite.

Idempotent: guarded with existence checks.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "009_outreach_identity"
down_revision: Union[str, None] = "008_add_job_title"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    return sa_inspect(op.get_bind()).has_table(name)


def _has_column(table: str, column: str) -> bool:
    insp = sa_inspect(op.get_bind())
    if not insp.has_table(table):
        return False
    return column in [c["name"] for c in insp.get_columns(table)]


def upgrade() -> None:
    # 1. Suppression list.
    if not _has_table("suppressions"):
        op.create_table(
            "suppressions",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("team_id", UUID(as_uuid=True), sa.ForeignKey("teams.id"), nullable=True),
            sa.Column("email", sa.String(320), nullable=False),
            sa.Column("reason", sa.String(32), nullable=False, server_default="manual"),
            sa.Column("source", sa.String(255), nullable=True),
            sa.Column("note", sa.String(500), nullable=True),
            sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("team_id", "email", name="uq_suppression_team_email"),
        )
        op.create_index("ix_suppression_team_email", "suppressions", ["team_id", "email"])
        op.create_index("ix_suppressions_email", "suppressions", ["email"])

    # 2. Identity spine on prospects.
    if not _has_column("prospects", "person_id"):
        op.add_column("prospects", sa.Column("person_id", UUID(as_uuid=True), nullable=True))
        op.create_index("ix_prospects_person_id", "prospects", ["person_id"])
    if not _has_column("prospects", "account_id"):
        op.add_column("prospects", sa.Column("account_id", UUID(as_uuid=True), nullable=True))
        op.create_index("ix_prospects_account_id", "prospects", ["account_id"])
    if not _has_column("prospects", "external_ids"):
        op.add_column("prospects", sa.Column("external_ids", JSONB, server_default="{}"))


def downgrade() -> None:
    for idx in ("ix_prospects_account_id", "ix_prospects_person_id"):
        try:
            op.drop_index(idx, table_name="prospects")
        except Exception:
            pass
    for col in ("external_ids", "account_id", "person_id"):
        try:
            op.drop_column("prospects", col)
        except Exception:
            pass
    if _has_table("suppressions"):
        op.drop_table("suppressions")
