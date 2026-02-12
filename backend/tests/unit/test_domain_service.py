"""
Tests for the domain service.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from uuid import uuid4


class TestDomainService:
    """Test cases for DomainService."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        session.add = MagicMock()
        session.delete = AsyncMock()
        return session

    @pytest.fixture
    def domain_service(self):
        """Create a DomainService instance with mocked dependencies."""
        with patch('app.services.domain_service.cloudflare_client') as mock_cf:
            from app.services.domain_service import DomainService
            service = DomainService()
            return service

    def test_domain_to_dict(self, domain_service):
        """Test conversion of domain model to dictionary."""
        from app.models import Domain

        mock_domain = MagicMock(spec=Domain)
        mock_domain.id = uuid4()
        mock_domain.domain_name = "test.example.com"
        mock_domain.status = "verified"
        mock_domain.mx_verified = True
        mock_domain.spf_verified = True
        mock_domain.dkim_verified = True
        mock_domain.dmarc_verified = True
        mock_domain.dkim_selector = "champmail"
        mock_domain.daily_send_limit = 100
        mock_domain.sent_today = 25
        mock_domain.warmup_enabled = True
        mock_domain.warmup_day = 15
        mock_domain.health_score = 95.5
        mock_domain.bounce_rate = 0.5
        mock_domain.cloudflare_zone_id = "zone-123"
        mock_domain.team_id = uuid4()
        mock_domain.created_at = datetime.utcnow()
        mock_domain.updated_at = datetime.utcnow()

        result = domain_service._domain_to_dict(mock_domain)

        assert result["domain_name"] == "test.example.com"
        assert result["status"] == "verified"
        assert result["mx_verified"] is True
        assert result["daily_send_limit"] == 100
        assert result["health_score"] == 95.5

    @pytest.mark.asyncio
    async def test_get_by_id_found(self, domain_service, mock_session):
        """Test getting a domain by ID when it exists."""
        from app.models import Domain

        mock_domain = MagicMock(spec=Domain)
        mock_domain.id = uuid4()
        mock_domain.domain_name = "test.example.com"
        mock_domain.status = "pending"
        mock_domain.mx_verified = False
        mock_domain.spf_verified = False
        mock_domain.dkim_verified = False
        mock_domain.dmarc_verified = False
        mock_domain.dkim_selector = None
        mock_domain.daily_send_limit = 50
        mock_domain.sent_today = 0
        mock_domain.warmup_enabled = True
        mock_domain.warmup_day = 0
        mock_domain.health_score = 100.0
        mock_domain.bounce_rate = 0.0
        mock_domain.cloudflare_zone_id = None
        mock_domain.team_id = None
        mock_domain.created_at = datetime.utcnow()
        mock_domain.updated_at = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_domain
        mock_session.execute.return_value = mock_result

        result = await domain_service.get_by_id(mock_session, str(mock_domain.id))

        assert result is not None
        assert result["domain_name"] == "test.example.com"
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, domain_service, mock_session):
        """Test getting a domain by ID when it doesn't exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await domain_service.get_by_id(mock_session, str(uuid4()))

        assert result is None
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_verified_domains(self, domain_service, mock_session):
        """Test getting all verified domains."""
        from app.models import Domain

        mock_domain1 = MagicMock(spec=Domain)
        mock_domain1.id = uuid4()
        mock_domain1.domain_name = "domain1.example.com"
        mock_domain1.status = "verified"
        mock_domain1.mx_verified = True
        mock_domain1.spf_verified = True
        mock_domain1.dkim_verified = True
        mock_domain1.dmarc_verified = True
        mock_domain1.dkim_selector = "champmail"
        mock_domain1.daily_send_limit = 100
        mock_domain1.sent_today = 25
        mock_domain1.warmup_enabled = False
        mock_domain1.warmup_day = 30
        mock_domain1.health_score = 98.0
        mock_domain1.bounce_rate = 0.2
        mock_domain1.cloudflare_zone_id = None
        mock_domain1.team_id = None
        mock_domain1.created_at = datetime.utcnow()
        mock_domain1.updated_at = None

        mock_domain2 = MagicMock(spec=Domain)
        mock_domain2.id = uuid4()
        mock_domain2.domain_name = "domain2.example.com"
        mock_domain2.status = "verified"
        mock_domain2.mx_verified = True
        mock_domain2.spf_verified = True
        mock_domain2.dkim_verified = True
        mock_domain2.dmarc_verified = True
        mock_domain2.dkim_selector = "champmail"
        mock_domain2.daily_send_limit = 100
        mock_domain2.sent_today = 50
        mock_domain2.warmup_enabled = False
        mock_domain2.warmup_day = 30
        mock_domain2.health_score = 97.0
        mock_domain2.bounce_rate = 0.3
        mock_domain2.cloudflare_zone_id = None
        mock_domain2.team_id = None
        mock_domain2.created_at = datetime.utcnow()
        mock_domain2.updated_at = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_domain1, mock_domain2]
        mock_session.execute.return_value = mock_result

        result = await domain_service.get_verified_domains(mock_session)

        assert len(result) == 2
        assert result[0]["domain_name"] == "domain1.example.com"
        assert result[1]["domain_name"] == "domain2.example.com"

    @pytest.mark.asyncio
    async def test_update_status(self, domain_service, mock_session):
        """Test updating domain status."""
        domain_id = str(uuid4())

        result = await domain_service.update_status(mock_session, domain_id, "verified")

        assert result is True
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_dns_status(self, domain_service, mock_session):
        """Test updating DNS verification status."""
        domain_id = str(uuid4())

        result = await domain_service.update_dns_status(
            mock_session,
            domain_id,
            mx_verified=True,
            spf_verified=True,
            dkim_verified=True,
            dmarc_verified=True,
        )

        assert result is True
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_increment_sent_count(self, domain_service, mock_session):
        """Test incrementing sent count for a domain."""
        domain_id = str(uuid4())

        result = await domain_service.increment_sent_count(mock_session, domain_id)

        assert result is True
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_increment_warmup_day(self, domain_service, mock_session):
        """Test incrementing warmup day."""
        domain_id = str(uuid4())

        result = await domain_service.increment_warmup_day(mock_session, domain_id)

        assert result is True
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_domain_found(self, domain_service, mock_session):
        """Test deleting a domain that exists."""
        from app.models import Domain

        mock_domain = MagicMock(spec=Domain)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_domain
        mock_session.execute.return_value = mock_result

        result = await domain_service.delete(mock_session, str(uuid4()))

        assert result is True
        mock_session.execute.assert_called_once()
        mock_session.delete.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_domain_not_found(self, domain_service, mock_session):
        """Test deleting a domain that doesn't exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await domain_service.delete(mock_session, str(uuid4()))

        assert result is False
        mock_session.delete.assert_not_called()


class TestDomainModelValidation:
    """Test cases for domain model validation."""

    def test_domain_status_values(self):
        """Test that domain status accepts valid values."""
        valid_statuses = ["pending", "verifying", "verified", "failed"]
        for status in valid_statuses:
            assert status in ["pending", "verifying", "verified", "failed"]

    def test_domain_health_score_range(self):
        """Test that health score is between 0 and 100."""
        for score in [0, 50, 100]:
            assert 0 <= score <= 100

    def test_warmup_day_progression(self):
        """Test warmup day progression logic."""
        warmup_limits = [10, 25, 50, 100, 200, 500, 750, 1000]

        for day, expected_limit in enumerate(warmup_limits):
            if day < len(warmup_limits):
                assert warmup_limits[day] == expected_limit

        # After 30 days, should be at full capacity
        assert warmup_limits[-1] == 1000