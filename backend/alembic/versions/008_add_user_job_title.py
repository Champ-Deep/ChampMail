"""Add job_title column to users table

Revision ID: 008_add_job_title
Revises: 007_utm_tracking
Create Date: 2026-02-16

The User model defines job_title but migration 001 omitted it.
Without this column, any SQLAlchemy query on User fails with
"column users.job_title does not exist" — causing 500 errors on login.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "008_add_job_title"
down_revision: Union[str, None] = "007_utm_tracking"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("job_title", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "job_title")
