"""Add send_mode and domain_id to campaigns table

Revision ID: 009_add_campaign_send_mode
Revises: 008_add_job_title
Create Date: 2026-02-28

Adds support for dual sending modes (user_smtp vs server) and domain selection.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect

revision: str = "009_add_campaign_send_mode"
down_revision: Union[str, None] = "008_add_job_title"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    cols = [c["name"] for c in sa_inspect(op.get_bind()).get_columns(table)]
    return column in cols


def upgrade() -> None:
    if not _column_exists("campaigns", "send_mode"):
        op.add_column(
            "campaigns",
            sa.Column(
                "send_mode", sa.String(20), nullable=True, server_default="user_smtp"
            ),
        )

    if not _column_exists("campaigns", "domain_id"):
        op.add_column(
            "campaigns",
            sa.Column(
                "domain_id", sa.UUID(), sa.ForeignKey("domains.id"), nullable=True
            ),
        )


def downgrade() -> None:
    if _column_exists("campaigns", "domain_id"):
        op.drop_column("campaigns", "domain_id")

    if _column_exists("campaigns", "send_mode"):
        op.drop_column("campaigns", "send_mode")
