"""Add UTM tracking tables: utm_presets, campaign_utm_configs, link_clicks

Revision ID: 007_utm_tracking
Revises: 006_campaign_tracking
Create Date: 2026-02-13

Note: These tables are also created by SQLAlchemy's Base.metadata.create_all()
in app startup. This migration exists for proper schema versioning and
production upgrade paths. On a fresh deploy, create_all handles everything.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "007_utm_tracking"
down_revision: Union[str, None] = "006_campaign_tracking"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ----------------------------------------------------------------
    # UTM Presets table
    # ----------------------------------------------------------------
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

    op.create_index("idx_utm_presets_team_id", "utm_presets", ["team_id"])
    op.create_index("idx_utm_presets_team_id_is_default", "utm_presets", ["team_id", "is_default"])

    # ----------------------------------------------------------------
    # Campaign UTM Configs table
    # ----------------------------------------------------------------
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

    op.create_index("idx_campaign_utm_configs_campaign_id", "campaign_utm_configs", ["campaign_id"])
    op.create_index("idx_campaign_utm_configs_team_id", "campaign_utm_configs", ["team_id"])

    # ----------------------------------------------------------------
    # Link Clicks table
    # ----------------------------------------------------------------
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

    op.create_index("idx_link_clicks_campaign_id", "link_clicks", ["campaign_id"])
    op.create_index("idx_link_clicks_prospect_id", "link_clicks", ["prospect_id"])
    op.create_index("idx_link_clicks_team_id_created_at", "link_clicks", ["team_id", "created_at"])
    op.create_index("idx_link_clicks_utm_source", "link_clicks", ["utm_source"])
    op.create_index("idx_link_clicks_utm_campaign", "link_clicks", ["utm_campaign"])

    # ----------------------------------------------------------------
    # Add clicked_urls column to send_logs
    # ----------------------------------------------------------------
    op.add_column("send_logs", sa.Column("clicked_urls", postgresql.JSON(), nullable=True))


def downgrade() -> None:
    # Remove clicked_urls from send_logs
    op.drop_column("send_logs", "clicked_urls")

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
