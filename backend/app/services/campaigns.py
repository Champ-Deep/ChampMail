"""
Campaign orchestration service.

Handles campaign creation, sending, and tracking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from app.db.falkordb import graph_db
from app.services.email_provider import (
    get_email_provider,
    EmailMessage,
    SendResult,
)
from app.services.templates import template_service, substitute_variables


class CampaignStatus(str, Enum):
    """Campaign status values."""
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Campaign:
    """Campaign data structure."""
    id: str
    name: str
    template_id: str
    sequence_id: Optional[str] = None
    status: CampaignStatus = CampaignStatus.DRAFT
    owner_id: str = ""
    sent_count: int = 0
    delivered_count: int = 0
    opened_count: int = 0
    clicked_count: int = 0
    replied_count: int = 0
    bounced_count: int = 0
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class CampaignRecipient:
    """Recipient in a campaign."""
    prospect_id: str
    email: str
    first_name: str = ""
    last_name: str = ""
    company: str = ""
    title: str = ""
    status: str = "pending"  # pending, sent, delivered, opened, clicked, replied, bounced
    sent_at: Optional[datetime] = None
    message_id: Optional[str] = None


class CampaignService:
    """Service for managing email campaigns."""

    def create_campaign(
        self,
        name: str,
        template_id: str,
        owner_id: str,
        sequence_id: Optional[str] = None,
    ) -> Campaign:
        """
        Create a new campaign.

        Args:
            name: Campaign name
            template_id: ID of the email template to use
            owner_id: ID of the campaign owner
            sequence_id: Optional sequence ID to link to

        Returns:
            Created campaign
        """
        campaign_id = str(uuid4())

        # Verify template exists
        template = template_service.get_template(template_id)
        if not template:
            raise ValueError(f"Template {template_id} not found")

        try:
            query = """
                CREATE (c:Campaign {
                    id: $id,
                    name: $name,
                    template_id: $template_id,
                    sequence_id: $sequence_id,
                    status: $status,
                    owner_id: $owner_id,
                    sent_count: 0,
                    delivered_count: 0,
                    opened_count: 0,
                    clicked_count: 0,
                    replied_count: 0,
                    bounced_count: 0,
                    created_at: datetime(),
                    updated_at: datetime()
                })
                RETURN c
            """
            graph_db.query(query, {
                'id': campaign_id,
                'name': name,
                'template_id': template_id,
                'sequence_id': sequence_id or '',
                'status': CampaignStatus.DRAFT.value,
                'owner_id': owner_id,
            })
        except Exception as e:
            print(f"FalkorDB error (campaign created in memory): {e}")

        return Campaign(
            id=campaign_id,
            name=name,
            template_id=template_id,
            sequence_id=sequence_id,
            status=CampaignStatus.DRAFT,
            owner_id=owner_id,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

    def get_campaign(self, campaign_id: str) -> Optional[Campaign]:
        """Get campaign by ID."""
        try:
            query = """
                MATCH (c:Campaign {id: $id})
                RETURN c
            """
            result = graph_db.query(query, {'id': campaign_id})
            if not result:
                return None

            props = result[0].get('c', {}).get('properties', {})
            return self._props_to_campaign(props)
        except Exception as e:
            print(f"Error getting campaign: {e}")
            return None

    def list_campaigns(
        self,
        owner_id: Optional[str] = None,
        status: Optional[CampaignStatus] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Campaign]:
        """List campaigns with optional filtering."""
        try:
            conditions = []
            params = {'limit': limit, 'offset': offset}

            if owner_id:
                conditions.append("c.owner_id = $owner_id")
                params['owner_id'] = owner_id

            if status:
                conditions.append("c.status = $status")
                params['status'] = status.value

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            query = f"""
                MATCH (c:Campaign)
                {where_clause}
                RETURN c
                ORDER BY c.created_at DESC
                SKIP $offset
                LIMIT $limit
            """
            results = graph_db.query(query, params)

            return [
                self._props_to_campaign(row.get('c', {}).get('properties', {}))
                for row in results
            ]
        except Exception as e:
            print(f"Error listing campaigns: {e}")
            return []

    def update_campaign_status(
        self,
        campaign_id: str,
        status: CampaignStatus,
    ) -> Optional[Campaign]:
        """Update campaign status."""
        try:
            updates = ['c.status = $status', 'c.updated_at = datetime()']
            params = {'id': campaign_id, 'status': status.value}

            # Add timestamp based on status
            if status == CampaignStatus.RUNNING:
                updates.append('c.started_at = datetime()')
            elif status == CampaignStatus.COMPLETED:
                updates.append('c.completed_at = datetime()')

            query = f"""
                MATCH (c:Campaign {{id: $id}})
                SET {', '.join(updates)}
                RETURN c
            """
            result = graph_db.query(query, params)

            if not result:
                return None

            return self.get_campaign(campaign_id)
        except Exception as e:
            print(f"Error updating campaign: {e}")
            return None

    def add_recipients(
        self,
        campaign_id: str,
        prospect_ids: list[str],
    ) -> int:
        """
        Add prospects as campaign recipients.

        Args:
            campaign_id: Campaign ID
            prospect_ids: List of prospect IDs to add

        Returns:
            Number of recipients added
        """
        try:
            added = 0
            for prospect_id in prospect_ids:
                query = """
                    MATCH (c:Campaign {id: $campaign_id})
                    MATCH (p:Prospect)
                    WHERE id(p) = $prospect_id OR p.id = $prospect_id
                    MERGE (p)-[r:TARGETED_BY]->(c)
                    ON CREATE SET r.status = 'pending', r.added_at = datetime()
                    RETURN count(r) as count
                """
                result = graph_db.query(query, {
                    'campaign_id': campaign_id,
                    'prospect_id': prospect_id,
                })
                if result and result[0].get('count', 0) > 0:
                    added += 1
            return added
        except Exception as e:
            print(f"Error adding recipients: {e}")
            return 0

    def get_recipients(
        self,
        campaign_id: str,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> list[CampaignRecipient]:
        """Get campaign recipients."""
        try:
            where_status = f"AND r.status = '{status}'" if status else ""

            query = f"""
                MATCH (p:Prospect)-[r:TARGETED_BY]->(c:Campaign {{id: $campaign_id}})
                {where_status}
                RETURN p, r
                LIMIT $limit
            """
            results = graph_db.query(query, {
                'campaign_id': campaign_id,
                'limit': limit,
            })

            recipients = []
            for row in results:
                p = row.get('p', {}).get('properties', {})
                r = row.get('r', {}).get('properties', {})

                recipients.append(CampaignRecipient(
                    prospect_id=p.get('id', ''),
                    email=p.get('email', ''),
                    first_name=p.get('first_name', ''),
                    last_name=p.get('last_name', ''),
                    company=p.get('company', ''),
                    title=p.get('title', ''),
                    status=r.get('status', 'pending'),
                    message_id=r.get('message_id'),
                ))
            return recipients
        except Exception as e:
            print(f"Error getting recipients: {e}")
            return []

    async def send_to_recipient(
        self,
        campaign_id: str,
        recipient: CampaignRecipient,
    ) -> SendResult:
        """
        Send campaign email to a single recipient.

        Args:
            campaign_id: Campaign ID
            recipient: Recipient to send to

        Returns:
            Send result
        """
        campaign = self.get_campaign(campaign_id)
        if not campaign:
            return SendResult(success=False, error="Campaign not found")

        template = template_service.get_template(campaign.template_id)
        if not template:
            return SendResult(success=False, error="Template not found")

        # Build variable context for this recipient
        variables = {
            'first_name': recipient.first_name,
            'last_name': recipient.last_name,
            'email': recipient.email,
            'company': recipient.company,
            'title': recipient.title,
            'unsubscribe_link': f'#unsubscribe?c={campaign_id}&p={recipient.prospect_id}',
        }

        # Substitute variables in subject and body
        subject = substitute_variables(template.subject, variables)
        html_body = substitute_variables(
            template.html_content or template.mjml_content,
            variables,
        )

        # Send via email provider
        tracking_id = f"{campaign_id}_{recipient.prospect_id}"
        provider = get_email_provider()

        result = await provider.send_email(EmailMessage(
            to=recipient.email,
            subject=subject,
            html_body=html_body,
            tracking_id=tracking_id,
        ))

        # Update recipient status in graph
        if result.success:
            self._update_recipient_status(
                campaign_id,
                recipient.prospect_id,
                'sent',
                result.message_id,
            )
            self._increment_campaign_stat(campaign_id, 'sent_count')

        return result

    def _update_recipient_status(
        self,
        campaign_id: str,
        prospect_id: str,
        status: str,
        message_id: Optional[str] = None,
    ):
        """Update recipient status in the graph."""
        try:
            updates = ['r.status = $status', 'r.updated_at = datetime()']
            params = {
                'campaign_id': campaign_id,
                'prospect_id': prospect_id,
                'status': status,
            }

            if status == 'sent':
                updates.append('r.sent_at = datetime()')

            if message_id:
                updates.append('r.message_id = $message_id')
                params['message_id'] = message_id

            query = f"""
                MATCH (p:Prospect)-[r:TARGETED_BY]->(c:Campaign {{id: $campaign_id}})
                WHERE id(p) = $prospect_id OR p.id = $prospect_id
                SET {', '.join(updates)}
            """
            graph_db.query(query, params)
        except Exception as e:
            print(f"Error updating recipient status: {e}")

    def _increment_campaign_stat(self, campaign_id: str, stat_name: str):
        """Increment a campaign statistic."""
        try:
            query = f"""
                MATCH (c:Campaign {{id: $id}})
                SET c.{stat_name} = coalesce(c.{stat_name}, 0) + 1,
                    c.updated_at = datetime()
            """
            graph_db.query(query, {'id': campaign_id})
        except Exception as e:
            print(f"Error incrementing stat: {e}")

    def get_campaign_stats(self, campaign_id: str) -> dict:
        """Get campaign statistics."""
        campaign = self.get_campaign(campaign_id)
        if not campaign:
            return {}

        return {
            'sent': campaign.sent_count,
            'delivered': campaign.delivered_count,
            'opened': campaign.opened_count,
            'clicked': campaign.clicked_count,
            'replied': campaign.replied_count,
            'bounced': campaign.bounced_count,
            'open_rate': (
                campaign.opened_count / campaign.sent_count * 100
                if campaign.sent_count > 0 else 0
            ),
            'click_rate': (
                campaign.clicked_count / campaign.sent_count * 100
                if campaign.sent_count > 0 else 0
            ),
            'reply_rate': (
                campaign.replied_count / campaign.sent_count * 100
                if campaign.sent_count > 0 else 0
            ),
        }

    def _props_to_campaign(self, props: dict) -> Campaign:
        """Convert graph properties to Campaign object."""
        status_str = props.get('status', 'draft')
        try:
            status = CampaignStatus(status_str)
        except ValueError:
            status = CampaignStatus.DRAFT

        return Campaign(
            id=props.get('id', ''),
            name=props.get('name', ''),
            template_id=props.get('template_id', ''),
            sequence_id=props.get('sequence_id') or None,
            status=status,
            owner_id=props.get('owner_id', ''),
            sent_count=props.get('sent_count', 0),
            delivered_count=props.get('delivered_count', 0),
            opened_count=props.get('opened_count', 0),
            clicked_count=props.get('clicked_count', 0),
            replied_count=props.get('replied_count', 0),
            bounced_count=props.get('bounced_count', 0),
        )


# Global service instance
campaign_service = CampaignService()
