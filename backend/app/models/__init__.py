"""
SQLAlchemy models for PostgreSQL persistence.
"""

from app.models.user import User, Team, TeamInvite
from app.models.email_settings import EmailSettings
from app.models.email_account import EmailAccount
from app.models.workflow import Workflow, WorkflowExecution, WorkflowType, WorkflowStatus
from app.models.domain import Domain, DNSCheckLog
from app.models.campaign import Campaign, CampaignProspect, Prospect
from app.models.sequence import Sequence, SequenceStep, SequenceEnrollment, SequenceStepExecution, SequenceStepLog
from app.models.send_log import SendLog, DailyStats, BounceLog, APIKey
from app.models.utm import CampaignUTMConfig, LinkClick, UTMPreset
# Union of both sides: production-email-engine added the UTM models, the PR
# stack added the team-scoped Suppression model.
from app.models.suppression import Suppression

__all__ = [
    "Suppression",
    "User",
    "Team",
    "TeamInvite",
    "EmailSettings",
    "EmailAccount",
    "Workflow",
    "WorkflowExecution",
    "WorkflowType",
    "WorkflowStatus",
    "Domain",
    "DNSCheckLog",
    "Campaign",
    "CampaignProspect",
    "Prospect",
    "Sequence",
    "SequenceStep",
    "SequenceEnrollment",
    "SequenceStepExecution",
    "SequenceStepLog",
    "SendLog",
    "DailyStats",
    "BounceLog",
    "APIKey",
    "CampaignUTMConfig",
    "LinkClick",
    "UTMPreset",
]