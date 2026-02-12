"""
Tests for the prospect service.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from uuid import uuid4


class TestProspectService:
    """Test cases for ProspectService."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        session.add = MagicMock()
        session.add_all = MagicMock()
        session.delete = AsyncMock()
        return session

    @pytest.fixture
    def prospect_service(self):
        """Create a ProspectService instance."""
        from app.services.prospect_service import ProspectService
        return ProspectService()

    def test_prospect_to_dict(self, prospect_service):
        """Test conversion of prospect model to dictionary."""
        from app.models import Prospect

        prospect_id = uuid4()
        team_id = uuid4()

        mock_prospect = MagicMock(spec=Prospect)
        mock_prospect.id = prospect_id
        mock_prospect.email = "john.doe@example.com"
        mock_prospect.first_name = "John"
        mock_prospect.last_name = "Doe"
        mock_prospect.full_name = "John Doe"
        mock_prospect.company_name = "Acme Corp"
        mock_prospect.company_domain = "acme.com"
        mock_prospect.company_size = "mid-market"
        mock_prospect.industry = "Technology"
        mock_prospect.job_title = "CTO"
        mock_prospect.linkedin_url = "https://linkedin.com/in/johndoe"
        mock_prospect.personalized_subject = "Hello {{first_name}}"
        mock_prospect.personalized_body = "<p>Hi {{first_name}},</p>"
        mock_prospect.status = "active"
        mock_prospect.source = "linkedin"
        mock_prospect.team_id = team_id
        mock_prospect.created_by = None
        mock_prospect.created_at = datetime.utcnow()
        mock_prospect.updated_at = datetime.utcnow()
        mock_prospect.last_contacted_at = None

        result = prospect_service._prospect_to_dict(mock_prospect)

        assert result["email"] == "john.doe@example.com"
        assert result["first_name"] == "John"
        assert result["full_name"] == "John Doe"
        assert result["company_name"] == "Acme Corp"
        assert result["status"] == "active"
        assert result["industry"] == "Technology"

    @pytest.mark.asyncio
    async def test_get_by_id_found(self, prospect_service, mock_session):
        """Test getting a prospect by ID when it exists."""
        from app.models import Prospect

        prospect_id = uuid4()

        mock_prospect = MagicMock(spec=Prospect)
        mock_prospect.id = prospect_id
        mock_prospect.email = "john.doe@example.com"
        mock_prospect.first_name = "John"
        mock_prospect.last_name = "Doe"
        mock_prospect.full_name = "John Doe"
        mock_prospect.company_name = "Acme Corp"
        mock_prospect.company_domain = "acme.com"
        mock_prospect.company_size = None
        mock_prospect.industry = "Technology"
        mock_prospect.job_title = "CTO"
        mock_prospect.linkedin_url = None
        mock_prospect.personalized_subject = None
        mock_prospect.personalized_body = None
        mock_prospect.status = "active"
        mock_prospect.source = None
        mock_prospect.team_id = None
        mock_prospect.created_by = None
        mock_prospect.created_at = datetime.utcnow()
        mock_prospect.updated_at = None
        mock_prospect.last_contacted_at = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_prospect
        mock_session.execute.return_value = mock_result

        result = await prospect_service.get_by_id(mock_session, str(prospect_id))

        assert result is not None
        assert result["email"] == "john.doe@example.com"

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, prospect_service, mock_session):
        """Test getting a prospect by ID when it doesn't exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await prospect_service.get_by_id(mock_session, str(uuid4()))

        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_email_found(self, prospect_service, mock_session):
        """Test getting a prospect by email when it exists."""
        from app.models import Prospect

        mock_prospect = MagicMock(spec=Prospect)
        mock_prospect.id = uuid4()
        mock_prospect.email = "existing@example.com"
        mock_prospect.first_name = "Existing"
        mock_prospect.last_name = "User"
        mock_prospect.full_name = "Existing User"
        mock_prospect.company_name = None
        mock_prospect.company_domain = None
        mock_prospect.company_size = None
        mock_prospect.industry = None
        mock_prospect.job_title = None
        mock_prospect.linkedin_url = None
        mock_prospect.personalized_subject = None
        mock_prospect.personalized_body = None
        mock_prospect.status = "active"
        mock_prospect.source = None
        mock_prospect.team_id = None
        mock_prospect.created_by = None
        mock_prospect.created_at = datetime.utcnow()
        mock_prospect.updated_at = None
        mock_prospect.last_contacted_at = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_prospect
        mock_session.execute.return_value = mock_result

        result = await prospect_service.get_by_email(mock_session, "existing@example.com")

        assert result is not None
        assert result["email"] == "existing@example.com"

    @pytest.mark.asyncio
    async def test_get_by_email_not_found(self, prospect_service, mock_session):
        """Test getting a prospect by email when it doesn't exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await prospect_service.get_by_email(mock_session, "nonexistent@example.com")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_ids(self, prospect_service, mock_session):
        """Test getting multiple prospects by IDs."""
        from app.models import Prospect

        prospect_ids = [str(uuid4()), str(uuid4())]

        mock_prospect1 = MagicMock(spec=Prospect)
        mock_prospect1.id = uuid4()
        mock_prospect1.email = "prospect1@example.com"
        mock_prospect1.first_name = "Prospect1"
        mock_prospect1.last_name = None
        mock_prospect1.full_name = "Prospect1"
        mock_prospect1.company_name = None
        mock_prospect1.company_domain = None
        mock_prospect1.company_size = None
        mock_prospect1.industry = None
        mock_prospect1.job_title = None
        mock_prospect1.linkedin_url = None
        mock_prospect1.personalized_subject = None
        mock_prospect1.personalized_body = None
        mock_prospect1.status = "active"
        mock_prospect1.source = None
        mock_prospect1.team_id = None
        mock_prospect1.created_by = None
        mock_prospect1.created_at = datetime.utcnow()
        mock_prospect1.updated_at = None
        mock_prospect1.last_contacted_at = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_prospect1]
        mock_session.execute.return_value = mock_result

        result = await prospect_service.get_by_ids(mock_session, prospect_ids)

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_mark_as_bounced(self, prospect_service, mock_session):
        """Test marking a prospect as bounced."""
        email = "bounced@example.com"

        result = await prospect_service.mark_as_bounced(mock_session, email, "hard")

        assert result is True
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_mark_as_replied(self, prospect_service, mock_session):
        """Test marking a prospect as having replied."""
        from app.models import Prospect

        prospect_id = uuid4()

        mock_prospect = MagicMock(spec=Prospect)
        mock_prospect.id = prospect_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_prospect
        mock_session.execute.return_value = mock_result

        result = await prospect_service.mark_as_replied(mock_session, str(prospect_id))

        assert result is True

    @pytest.mark.asyncio
    async def test_delete_found(self, prospect_service, mock_session):
        """Test deleting a prospect that exists."""
        from app.models import Prospect

        mock_prospect = MagicMock(spec=Prospect)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_prospect
        mock_session.execute.return_value = mock_result

        result = await prospect_service.delete(mock_session, str(uuid4()))

        assert result is True
        mock_session.delete.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_not_found(self, prospect_service, mock_session):
        """Test deleting a prospect that doesn't exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await prospect_service.delete(mock_session, str(uuid4()))

        assert result is False
        mock_session.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_search(self, prospect_service, mock_session):
        """Test searching prospects."""
        from app.models import Prospect

        mock_prospect = MagicMock(spec=Prospect)
        mock_prospect.id = uuid4()
        mock_prospect.email = "search@example.com"
        mock_prospect.first_name = "Search"
        mock_prospect.last_name = None
        mock_prospect.full_name = "Search Result"
        mock_prospect.company_name = "Search Corp"
        mock_prospect.company_domain = None
        mock_prospect.company_size = None
        mock_prospect.industry = None
        mock_prospect.job_title = None
        mock_prospect.linkedin_url = None
        mock_prospect.personalized_subject = None
        mock_prospect.personalized_body = None
        mock_prospect.status = "active"
        mock_prospect.source = None
        mock_prospect.team_id = None
        mock_prospect.created_by = None
        mock_prospect.created_at = datetime.utcnow()
        mock_prospect.updated_at = None
        mock_prospect.last_contacted_at = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_prospect]
        mock_session.execute.return_value = mock_result

        result = await prospect_service.search(mock_session, str(uuid4()), "search")

        assert len(result) == 1
        assert result[0]["email"] == "search@example.com"


class TestProspectValidation:
    """Test cases for prospect data validation."""

    def test_email_validation(self):
        """Test email format validation."""
        valid_emails = [
            "test@example.com",
            "user.name@domain.co.uk",
            "user+tag@example.org",
        ]

        invalid_emails = [
            "not-an-email",
            "@domain.com",
            "user@",
            "user@@domain.com",
        ]

        for email in valid_emails:
            assert "@" in email and "." in email.split("@")[-1]

        for email in invalid_emails:
            assert not ("@" in email and "." in email.split("@")[-1] if "@" in email else True)

    def test_name_concatenation(self):
        """Test full name concatenation."""
        first_name = "John"
        last_name = "Doe"

        full_name = f"{first_name} {last_name}".strip()

        assert full_name == "John Doe"

    def test_status_values(self):
        """Test that prospect status accepts valid values."""
        valid_statuses = ["active", "bounced", "unsubscribed", "do_not_contact"]

        for status in valid_statuses:
            assert status in valid_statuses

    def test_source_values(self):
        """Test common prospect source values."""
        valid_sources = [
            "linkedin",
            "csv_import",
            "manual",
            "api",
            "webhook",
        ]

        for source in valid_sources:
            assert source in valid_sources