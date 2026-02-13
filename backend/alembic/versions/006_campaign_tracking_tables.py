"""Add campaign, prospect, sequence, tracking, and analytics tables

Revision ID: 006_campaign_tracking
Revises: 005_data_team
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
revision: str = "006_campaign_tracking"
down_revision: Union[str, None] = "005_data_team"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ----------------------------------------------------------------
    # Campaigns table
    # ----------------------------------------------------------------
    op.create_table(
        "campaigns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(50), default="draft", nullable=False),

        # Configuration
        sa.Column("from_name", sa.String(255), nullable=True),
        sa.Column("from_address", sa.String(255), nullable=True),
        sa.Column("reply_to", sa.String(255), nullable=True),

        # Template
        sa.Column("subject_template", sa.Text(), nullable=True),
        sa.Column("html_template", sa.Text(), nullable=True),
        sa.Column("plain_text_template", sa.Text(), nullable=True),

        # AI personalization
        sa.Column("use_ai_personalization", sa.Boolean(), default=False),
        sa.Column("ai_prompt", sa.Text(), nullable=True),

        # Targeting
        sa.Column("prospect_list_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_company_size", postgresql.JSON(), nullable=True),
        sa.Column("target_industries", postgresql.JSON(), nullable=True),

        # Domain rotation
        sa.Column("domain_ids", postgresql.JSON(), nullable=True),

        # Scheduling
        sa.Column("start_date", sa.DateTime(), nullable=True),
        sa.Column("end_date", sa.DateTime(), nullable=True),
        sa.Column("timezone", sa.String(50), default="UTC"),

        # Limits
        sa.Column("daily_limit", sa.Integer(), default=100),
        sa.Column("total_limit", sa.Integer(), nullable=True),

        # Statistics
        sa.Column("total_prospects", sa.Integer(), default=0),
        sa.Column("sent_count", sa.Integer(), default=0),
        sa.Column("opened_count", sa.Integer(), default=0),
        sa.Column("clicked_count", sa.Integer(), default=0),
        sa.Column("bounced_count", sa.Integer(), default=0),
        sa.Column("replied_count", sa.Integer(), default=0),
        sa.Column("unsubscribed_count", sa.Integer(), default=0),

        # Team association
        sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),

        # Timestamps
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column("activated_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )

    op.create_index("idx_campaigns_team_id", "campaigns", ["team_id"])
    op.create_index("idx_campaigns_status", "campaigns", ["status"])
    op.create_index("idx_campaigns_created_by", "campaigns", ["created_by"])

    # ----------------------------------------------------------------
    # Prospects table
    # ----------------------------------------------------------------
    op.create_table(
        "prospects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("first_name", sa.String(255), nullable=True),
        sa.Column("last_name", sa.String(255), nullable=True),
        sa.Column("full_name", sa.String(255), nullable=True),

        # Company information
        sa.Column("company_name", sa.String(255), nullable=True),
        sa.Column("company_domain", sa.String(255), nullable=True),
        sa.Column("company_size", sa.String(50), nullable=True),
        sa.Column("industry", sa.String(100), nullable=True),
        sa.Column("job_title", sa.String(255), nullable=True),

        # Personalization
        sa.Column("linkedin_url", sa.String(500), nullable=True),
        sa.Column("twitter_handle", sa.String(100), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("interests", postgresql.JSON(), nullable=True),

        # AI-generated content
        sa.Column("personalized_subject", sa.Text(), nullable=True),
        sa.Column("personalized_body", sa.Text(), nullable=True),

        # Status
        sa.Column("status", sa.String(50), default="active", nullable=False),

        # Source
        sa.Column("source", sa.String(100), nullable=True),
        sa.Column("import_batch_id", sa.String(100), nullable=True),

        # Team association
        sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),

        # Timestamps
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column("last_contacted_at", sa.DateTime(), nullable=True),
    )

    op.create_index("idx_prospects_team_id", "prospects", ["team_id"])
    op.create_index("idx_prospects_status", "prospects", ["status"])
    op.create_index("idx_prospects_company_domain", "prospects", ["company_domain"])

    # ----------------------------------------------------------------
    # Campaign-Prospect enrollment (junction table)
    # ----------------------------------------------------------------
    op.create_table(
        "campaign_prospects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prospect_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(50), default="enrolled", nullable=False),
        sa.Column("current_step", sa.Integer(), default=0),

        # Metrics
        sa.Column("email_sent", sa.Boolean(), default=False),
        sa.Column("opened", sa.Boolean(), default=False),
        sa.Column("clicked", sa.Boolean(), default=False),
        sa.Column("replied", sa.Boolean(), default=False),
        sa.Column("bounced", sa.Boolean(), default=False),
        sa.Column("unsubscribed", sa.Boolean(), default=False),

        # Message tracking
        sa.Column("last_message_id", sa.String(255), nullable=True),
        sa.Column("last_sent_at", sa.DateTime(), nullable=True),
        sa.Column("next_step_at", sa.DateTime(), nullable=True),

        # Timestamps
        sa.Column("enrolled_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )

    op.create_index("idx_cp_campaign_id", "campaign_prospects", ["campaign_id"])
    op.create_index("idx_cp_prospect_id", "campaign_prospects", ["prospect_id"])
    op.create_index("idx_cp_status", "campaign_prospects", ["status"])

    # ----------------------------------------------------------------
    # Sequences table
    # ----------------------------------------------------------------
    op.create_table(
        "sequences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(50), default="draft", nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # ----------------------------------------------------------------
    # Sequence Steps table
    # ----------------------------------------------------------------
    op.create_table(
        "sequence_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("sequence_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sequences.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_number", sa.Integer(), nullable=False),
        sa.Column("step_type", sa.String(50), default="email", nullable=False),
        sa.Column("subject", sa.Text(), nullable=True),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("delay_days", sa.Integer(), default=1),
        sa.Column("delay_hours", sa.Integer(), default=0),
        sa.Column("conditions", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # ----------------------------------------------------------------
    # Sequence Enrollments table
    # ----------------------------------------------------------------
    op.create_table(
        "sequence_enrollments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("sequence_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sequences.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prospect_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(50), default="active", nullable=False),
        sa.Column("current_step", sa.Integer(), default=0),
        sa.Column("enrolled_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("paused_at", sa.DateTime(), nullable=True),
    )

    # ----------------------------------------------------------------
    # Sequence Step Executions table
    # ----------------------------------------------------------------
    op.create_table(
        "sequence_step_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("enrollment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sequence_enrollments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sequence_steps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(50), default="pending", nullable=False),
        sa.Column("scheduled_at", sa.DateTime(), nullable=True),
        sa.Column("executed_at", sa.DateTime(), nullable=True),
        sa.Column("message_id", sa.String(255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
    )

    # ----------------------------------------------------------------
    # Alter send_logs to add missing columns from current model
    # Migration 004 created it with different column names; add the
    # columns that the current model needs if they don't exist.
    # ----------------------------------------------------------------
    # Add columns needed by the current model
    op.add_column("send_logs", sa.Column("recipient_email", sa.String(255), nullable=True))
    op.add_column("send_logs", sa.Column("from_address", sa.String(255), nullable=True))
    op.add_column("send_logs", sa.Column("prospect_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("send_logs", sa.Column("sequence_enrollment_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("send_logs", sa.Column("bounce_reason", sa.Text(), nullable=True))
    op.add_column("send_logs", sa.Column("smtp_response", sa.Text(), nullable=True))
    op.add_column("send_logs", sa.Column("reply_text", sa.Text(), nullable=True))
    op.add_column("send_logs", sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=True))

    # Rename columns to match model (first_opened_at -> first_open_at, etc.)
    op.alter_column("send_logs", "first_opened_at", new_column_name="first_open_at")
    op.alter_column("send_logs", "first_clicked_at", new_column_name="first_click_at")

    op.create_index("idx_send_logs_recipient_email", "send_logs", ["recipient_email"])
    op.create_index("idx_send_logs_prospect_id", "send_logs", ["prospect_id"])
    op.create_index("idx_send_logs_campaign_id", "send_logs", ["campaign_id"])
    op.create_index("idx_send_logs_team_id", "send_logs", ["team_id"])

    # ----------------------------------------------------------------
    # Bounce logs table
    # ----------------------------------------------------------------
    op.create_table(
        "bounce_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("send_log_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("send_logs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("prospect_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prospects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("email", sa.String(255), nullable=False, index=True),
        sa.Column("bounce_type", sa.String(50), nullable=False),
        sa.Column("bounce_category", sa.String(100), nullable=True),
        sa.Column("smtp_error_code", sa.String(20), nullable=True),
        sa.Column("smtp_response", sa.Text(), nullable=True),
        sa.Column("processed", sa.Boolean(), default=False),
        sa.Column("prospect_marked_bounced", sa.Boolean(), default=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    op.create_index("idx_bounce_logs_email", "bounce_logs", ["email"])
    op.create_index("idx_bounce_logs_send_log_id", "bounce_logs", ["send_log_id"])
    op.create_index("idx_bounce_logs_bounce_type", "bounce_logs", ["bounce_type"])

    # ----------------------------------------------------------------
    # Daily stats table
    # ----------------------------------------------------------------
    op.create_table(
        "daily_stats",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("domain_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("domains.id", ondelete="SET NULL"), nullable=True),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True),
        sa.Column("date", sa.DateTime(), nullable=False, index=True),
        sa.Column("total_sent", sa.Integer(), default=0),
        sa.Column("total_delivered", sa.Integer(), default=0),
        sa.Column("total_failed", sa.Integer(), default=0),
        sa.Column("total_opened", sa.Integer(), default=0),
        sa.Column("unique_opened", sa.Integer(), default=0),
        sa.Column("total_clicked", sa.Integer(), default=0),
        sa.Column("unique_clicked", sa.Integer(), default=0),
        sa.Column("total_replied", sa.Integer(), default=0),
        sa.Column("total_bounced", sa.Integer(), default=0),
        sa.Column("total_unsubscribed", sa.Integer(), default=0),
        sa.Column("open_rate", sa.Float(), default=0.0),
        sa.Column("click_rate", sa.Float(), default=0.0),
        sa.Column("bounce_rate", sa.Float(), default=0.0),
        sa.Column("reply_rate", sa.Float(), default=0.0),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # ----------------------------------------------------------------
    # API Keys table
    # ----------------------------------------------------------------
    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("key_hash", sa.String(255), unique=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("permissions", postgresql.JSON(), nullable=True),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    # ----------------------------------------------------------------
    # Email Settings table
    # ----------------------------------------------------------------
    op.create_table(
        "email_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("smtp_host", sa.String(255), nullable=True),
        sa.Column("smtp_port", sa.Integer(), nullable=True),
        sa.Column("smtp_username", sa.String(255), nullable=True),
        sa.Column("smtp_password", sa.String(500), nullable=True),
        sa.Column("smtp_use_tls", sa.Boolean(), default=True),
        sa.Column("imap_host", sa.String(255), nullable=True),
        sa.Column("imap_port", sa.Integer(), nullable=True),
        sa.Column("imap_username", sa.String(255), nullable=True),
        sa.Column("imap_password", sa.String(500), nullable=True),
        sa.Column("imap_use_ssl", sa.Boolean(), default=True),
        sa.Column("from_name", sa.String(255), nullable=True),
        sa.Column("from_email", sa.String(255), nullable=True),
        sa.Column("signature_html", sa.Text(), nullable=True),
        sa.Column("daily_send_limit", sa.Integer(), default=200),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # ----------------------------------------------------------------
    # Workflows table
    # ----------------------------------------------------------------
    op.create_table(
        "workflows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("workflow_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), default="draft", nullable=False),
        sa.Column("trigger_config", postgresql.JSON(), nullable=True),
        sa.Column("steps", postgresql.JSON(), nullable=True),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # ----------------------------------------------------------------
    # Workflow Executions table
    # ----------------------------------------------------------------
    op.create_table(
        "workflow_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workflow_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(50), default="running", nullable=False),
        sa.Column("trigger_data", postgresql.JSON(), nullable=True),
        sa.Column("result_data", postgresql.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("workflow_executions")
    op.drop_table("workflows")
    op.drop_table("email_settings")
    op.drop_table("api_keys")
    op.drop_table("daily_stats")

    op.drop_index("idx_bounce_logs_bounce_type", "bounce_logs")
    op.drop_index("idx_bounce_logs_send_log_id", "bounce_logs")
    op.drop_index("idx_bounce_logs_email", "bounce_logs")
    op.drop_table("bounce_logs")

    # Revert send_logs alterations
    op.drop_index("idx_send_logs_team_id", "send_logs")
    op.drop_index("idx_send_logs_campaign_id", "send_logs")
    op.drop_index("idx_send_logs_prospect_id", "send_logs")
    op.drop_index("idx_send_logs_recipient_email", "send_logs")
    op.alter_column("send_logs", "first_click_at", new_column_name="first_clicked_at")
    op.alter_column("send_logs", "first_open_at", new_column_name="first_opened_at")
    op.drop_column("send_logs", "team_id")
    op.drop_column("send_logs", "reply_text")
    op.drop_column("send_logs", "smtp_response")
    op.drop_column("send_logs", "bounce_reason")
    op.drop_column("send_logs", "sequence_enrollment_id")
    op.drop_column("send_logs", "prospect_id")
    op.drop_column("send_logs", "from_address")
    op.drop_column("send_logs", "recipient_email")

    op.drop_table("sequence_step_executions")
    op.drop_table("sequence_enrollments")
    op.drop_table("sequence_steps")
    op.drop_table("sequences")
    op.drop_table("campaign_prospects")
    op.drop_table("prospects")

    op.drop_index("idx_campaigns_created_by", "campaigns")
    op.drop_index("idx_campaigns_status", "campaigns")
    op.drop_index("idx_campaigns_team_id", "campaigns")
    op.drop_table("campaigns")
