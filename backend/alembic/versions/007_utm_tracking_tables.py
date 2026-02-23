"""Add UTM tracking tables: utm_presets, campaign_utm_configs, link_clicks

Revision ID: 007_utm_tracking
Revises: 006_campaign_tracking
Create Date: 2026-02-13

Note: These tables are also created by SQLAlchemy's Base.metadata.create_all()
in app startup. This migration exists for proper schema versioning and
production upgrade paths. On a fresh deploy, create_all handles everything.

All DDL operations are guarded with existence checks so the migration is
idempotent — it can safely run even if create_all() already created the tables.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect as sa_inspect

# revision identifiers, used by Alembic.
revision: str = "007_utm_tracking"
down_revision: Union[str, None] = "006_campaign_tracking"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# --------------- idempotency helpers ---------------

def _table_exists(name: str) -> bool:
    return name in sa_inspect(op.get_bind()).get_table_names()

def _index_exists(name: str) -> bool:
    result = op.get_bind().execute(
        sa.text("SELECT 1 FROM pg_indexes WHERE indexname = :n"),
        {"n": name},
    )
    return result.fetchone() is not None


def upgrade() -> None:
    # ----------------------------------------------------------------
    # UTM Presets table
    # ----------------------------------------------------------------
    if not _table_exists("utm_presets"):
        op.create_table(
            "utm_presets",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("is_default", sa.Boolean(), default=False),
            sa.Column("utm_source", sa.String(255), nullable=True),
            sa.Column("utm_medium", sa.String(255), nullable=True),
            sa.Column("utm_campaign", sa.String(255), nullable=True),
            sa.Column("utm_content", sa.String(255), nullable=True),
            sa.Column("utm_term", sa.String(255), nullable=True),
            sa.Column("custom_params", postgresql.JSON(), nullable=True),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        )

    if not _index_exists("idx_utm_presets_team_id"):
        op.create_index("idx_utm_presets_team_id", "utm_presets", ["team_id"])
    if not _index_exists("idx_utm_presets_team_id_is_default"):
        op.create_index("idx_utm_presets_team_id_is_default", "utm_presets", ["team_id", "is_default"])

    # ----------------------------------------------------------------
    # Campaign UTM Configs table
    # ----------------------------------------------------------------
    if not _table_exists("campaign_utm_configs"):
        op.create_table(
            "campaign_utm_configs",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), unique=True, nullable=False),
            sa.Column("preset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("utm_presets.id", ondelete="SET NULL"), nullable=True),
            sa.Column("enabled", sa.Boolean(), default=True),
            sa.Column("utm_source", sa.String(255), nullable=True),
            sa.Column("utm_medium", sa.String(255), nullable=True),
            sa.Column("utm_campaign", sa.String(255), nullable=True),
            sa.Column("utm_content", sa.String(255), nullable=True),
            sa.Column("utm_term", sa.String(255), nullable=True),
            sa.Column("custom_params", postgresql.JSON(), nullable=True),
            sa.Column("link_overrides", postgresql.JSON(), nullable=True),
            sa.Column("preserve_existing_utm", sa.Boolean(), default=True),
            sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        )

    if not _index_exists("idx_campaign_utm_configs_campaign_id"):
        op.create_index("idx_campaign_utm_configs_campaign_id", "campaign_utm_configs", ["campaign_id"])
    if not _index_exists("idx_campaign_utm_configs_team_id"):
        op.create_index("idx_campaign_utm_configs_team_id", "campaign_utm_configs", ["team_id"])

    # ----------------------------------------------------------------
    # Link Clicks table
    # ----------------------------------------------------------------
    if not _table_exists("link_clicks"):
        op.create_table(
            "link_clicks",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
            sa.Column("prospect_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prospects.id", ondelete="SET NULL"), nullable=True),
            sa.Column("send_log_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("send_logs.id", ondelete="SET NULL"), nullable=True),
            sa.Column("original_url", sa.Text(), nullable=False),
            sa.Column("tracked_url", sa.Text(), nullable=True),
            sa.Column("anchor_text", sa.String(500), nullable=True),
            sa.Column("link_position", sa.Integer(), nullable=True),
            sa.Column("utm_source", sa.String(255), nullable=True),
            sa.Column("utm_medium", sa.String(255), nullable=True),
            sa.Column("utm_campaign", sa.String(255), nullable=True),
            sa.Column("utm_content", sa.String(255), nullable=True),
            sa.Column("utm_term", sa.String(255), nullable=True),
            sa.Column("click_count", sa.Integer(), default=0),
            sa.Column("unique_clicks", sa.Integer(), default=0),
            sa.Column("first_clicked_at", sa.DateTime(), nullable=True),
            sa.Column("last_clicked_at", sa.DateTime(), nullable=True),
            sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )

    if not _index_exists("idx_link_clicks_campaign_id"):
        op.create_index("idx_link_clicks_campaign_id", "link_clicks", ["campaign_id"])
    if not _index_exists("idx_link_clicks_prospect_id"):
        op.create_index("idx_link_clicks_prospect_id", "link_clicks", ["prospect_id"])
    if not _index_exists("idx_link_clicks_team_id_created_at"):
        op.create_index("idx_link_clicks_team_id_created_at", "link_clicks", ["team_id", "created_at"])
    if not _index_exists("idx_link_clicks_utm_source"):
        op.create_index("idx_link_clicks_utm_source", "link_clicks", ["utm_source"])
    if not _index_exists("idx_link_clicks_utm_campaign"):
        op.create_index("idx_link_clicks_utm_campaign", "link_clicks", ["utm_campaign"])

    # clicked_urls already exists from migration 004 — skip duplicate add


def downgrade() -> None:
    # clicked_urls owned by migration 004 — don't drop here

    # Drop link_clicks indexes and table
    op.drop_index("idx_link_clicks_utm_campaign", "link_clicks")
    op.drop_index("idx_link_clicks_utm_source", "link_clicks")
    op.drop_index("idx_link_clicks_team_id_created_at", "link_clicks")
    op.drop_index("idx_link_clicks_prospect_id", "link_clicks")
    op.drop_index("idx_link_clicks_campaign_id", "link_clicks")
    op.drop_table("link_clicks")

    # Drop campaign_utm_configs indexes and table
    op.drop_index("idx_campaign_utm_configs_team_id", "campaign_utm_configs")
    op.drop_index("idx_campaign_utm_configs_campaign_id", "campaign_utm_configs")
    op.drop_table("campaign_utm_configs")

    # Drop utm_presets indexes and table
    op.drop_index("idx_utm_presets_team_id_is_default", "utm_presets")
    op.drop_index("idx_utm_presets_team_id", "utm_presets")
    op.drop_table("utm_presets")
