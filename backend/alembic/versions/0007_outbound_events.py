"""outbound_events: durable outbox for the events webhook

Revision ID: 0007
Revises: 0006

Unique(message_id, event_type) makes event creation idempotent in one INSERT ... ON CONFLICT. The FK
to send_dispatches.message_id means only events for a known send can exist. Replaces the Redis
queue and SET NX markers (events there were lost on cancellation); in-flight Redis entries from the
old worker are not migrated (the v3 stack has no production traffic yet).
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

EVENT_TYPES = ("delivered", "opened", "clicked", "replied", "bounced", "complained", "unsubscribed")
STATUSES = ("pending", "leased", "delivered", "dead")


def _in(col, values):
    return f"{col} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    op.create_table(
        "outbound_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("message_id", sa.String(998), sa.ForeignKey("send_dispatches.message_id"), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("event_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime()),
        sa.Column("last_error", sa.Text()),
        sa.Column("delivered_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("message_id", "event_type", name="uq_outbound_events_message_event"),
        sa.CheckConstraint(_in("event_type", EVENT_TYPES), name="ck_outbound_events_event_type"),
        sa.CheckConstraint(_in("status", STATUSES), name="ck_outbound_events_status"),
    )
    op.create_index("ix_outbound_events_status_next", "outbound_events", ["status", "next_attempt_at"])


def downgrade() -> None:
    op.drop_table("outbound_events")
