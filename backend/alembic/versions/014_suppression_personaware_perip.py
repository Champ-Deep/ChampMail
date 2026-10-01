"""Suppression person-awareness + global-unique, and per-IP ramp.

Revision ID: 014_suppression_perip
Revises: 013_outreach_identity
Create Date: 2026-06-24

Brings the schema up to the system-design plan (plan.md §1):
  - suppressions: add `person_id` + `email_sha256` (opt-out follows the human),
    and a PARTIAL UNIQUE index on `email WHERE team_id IS NULL` so a global
    suppression is single-rowed and blocks every team (Q6/Q7).
  - domains: add `sending_ip` so the ramp-governor can key reputation per IP (H).

Idempotent: guarded with existence checks.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.dialects.postgresql import UUID

revision = "014_suppression_perip"
down_revision = "013_outreach_identity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _insp():
    return sa_inspect(op.get_bind())


def _has_column(table: str, column: str) -> bool:
    insp = _insp()
    if not insp.has_table(table):
        return False
    return column in [c["name"] for c in insp.get_columns(table)]


def _has_index(table: str, name: str) -> bool:
    insp = _insp()
    if not insp.has_table(table):
        return False
    return name in [i["name"] for i in insp.get_indexes(table)]


def upgrade() -> None:
    # 1. Suppression person-awareness.
    if not _has_column("suppressions", "person_id"):
        op.add_column("suppressions", sa.Column("person_id", UUID(as_uuid=True), nullable=True))
        op.create_index("ix_suppression_person", "suppressions", ["person_id"])
    if not _has_column("suppressions", "email_sha256"):
        op.add_column("suppressions", sa.Column("email_sha256", sa.String(64), nullable=True))
        op.create_index("ix_suppression_sha256", "suppressions", ["email_sha256"])

    # 2. Global suppression is single-rowed per email (partial unique index) —
    #    NULLs are distinct in a plain unique constraint, so this is required for
    #    "global opt-out suppresses everyone" to hold.
    if not _has_index("suppressions", "uq_suppression_global_email"):
        op.create_index(
            "uq_suppression_global_email", "suppressions", ["email"],
            unique=True, postgresql_where=sa.text("team_id IS NULL"),
        )

    # 3. Per-IP ramp.
    if not _has_column("domains", "sending_ip"):
        op.add_column("domains", sa.Column("sending_ip", sa.String(45), nullable=True))


def downgrade() -> None:
    for idx in ("uq_suppression_global_email", "ix_suppression_sha256", "ix_suppression_person"):
        try:
            op.drop_index(idx, table_name="suppressions")
        except Exception:
            pass
    for col in ("email_sha256", "person_id"):
        try:
            op.drop_column("suppressions", col)
        except Exception:
            pass
    try:
        op.drop_column("domains", "sending_ip")
    except Exception:
        pass
