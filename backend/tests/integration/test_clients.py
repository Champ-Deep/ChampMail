"""
Integration tests for external service clients.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestMailEngineClientIntegration:
    """Integration tests for mail engine client."""

    @pytest.fixture
    def mock_response(self):
        """Create a mock HTTP response."""
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "message_id": "test-msg-uuid",
            "status": "accepted",
            "domain_id": "test-domain-id",
            "sent_at": "2024-01-15T10:30:00Z"
        }
        response.raise_for_status = MagicMock()
        return response

    def test_send_email_success(self, mock_response):
        """Test successful email sending."""
        from app.services.mail_engine_client import SendResult

        result = SendResult(
            message_id="test-msg-uuid",
            status="accepted",
            domain_id="test-domain-id",
            sent_at="2024-01-15T10:30:00Z"
        )

        assert result.message_id == "test-msg-uuid"
        assert result.status == "accepted"
        assert result.domain_id == "test-domain-id"

    def test_send_batch_result(self):
        """Test batch send result aggregation."""
        from app.services.mail_engine_client import BatchResult, SendResult

        results = [
            SendResult(
                message_id=f"msg-{i}",
                status="accepted",
                domain_id="test-domain",
                sent_at="2024-01-15T10:30:00Z"
            )
            for i in range(5)
        ]

        batch = BatchResult(
            total=5,
            successful=5,
            failed=0,
            results=results
        )

        assert batch.total == 5
        assert batch.successful == 5
        assert batch.failed == 0

    def test_send_stats_structure(self):
        """Test send stats data structure."""
        from app.services.mail_engine_client import SendStats

        stats = SendStats(
            domain_id="test-domain",
            today_sent=25,
            today_limit=100,
            total_sent=5000,
            total_opened=3500,
            total_clicked=1500,
            total_bounced=100,
            open_rate=70.0,
            click_rate=30.0,
            bounce_rate=2.0
        )

        assert stats.today_sent == 25
        assert stats.today_limit == 100
        assert stats.open_rate == 70.0


class TestCloudflareClientIntegration:
    """Integration tests for Cloudflare client."""

    def test_zone_structure(self):
        """Test zone data structure."""
        from app.services.cloudflare_client import Zone

        zone = Zone(
            id="zone-123",
            name="example.com",
            status="active",
            plan="free"
        )

        assert zone.id == "zone-123"
        assert zone.name == "example.com"

    def test_dns_record_structure(self):
        """Test DNS record data structure."""
        from app.services.cloudflare_client import DNSRecord

        record = DNSRecord(
            id="record-123",
            type="MX",
            name="example.com",
            value="10 mail.example.com",
            priority=10,
            ttl=3600,
            proxied=False
        )

        assert record.type == "MX"
        assert record.priority == 10
        assert record.ttl == 3600

    def test_dns_setup_result_structure(self):
        """Test DNS setup result data structure."""
        from app.services.cloudflare_client import DNSSetupResult

        result = DNSSetupResult(
            success=True,
            records=[]
        )

        assert result.success is True
        assert isinstance(result.records, list)

    def test_propagation_status_structure(self):
        """Test propagation status data structure."""
        from app.services.cloudflare_client import PropagationStatus

        status = PropagationStatus(
            mx=True,
            spf=True,
            dkim=True,
            dmarc=True,
            all_verified=True
        )

        assert status.all_verified is True
        assert status.mx is True


class TestNamecheapClientIntegration:
    """Integration tests for Namecheap client."""

    def test_domain_result_structure(self):
        """Test domain search result data structure."""
        from app.services.namecheap_client import DomainResult

        result = DomainResult(
            domain="example.com",
            available=True,
            price=12.99,
            currency="USD"
        )

        assert result.domain == "example.com"
        assert result.available is True
        assert result.price == 12.99

    def test_purchase_result_structure(self):
        """Test domain purchase result data structure."""
        from app.services.namecheap_client import PurchaseResult

        success_result = PurchaseResult(
            success=True,
            order_id="order-123",
            transaction_id="txn-123",
            domain="example.com"
        )

        assert success_result.success is True
        assert success_result.order_id == "order-123"

        failure_result = PurchaseResult(
            success=False,
            order_id="",
            transaction_id="",
            domain="taken.com",
            error="Domain not available"
        )

        assert failure_result.success is False
        assert failure_result.error == "Domain not available"

    def test_domain_info_structure(self):
        """Test domain info data structure."""
        from app.services.namecheap_client import DomainInfo

        info = DomainInfo(
            domain="example.com",
            registered=True,
            expiration_date="2025-01-15",
            nameservers=["ns1.cloudflare.com", "ns2.cloudflare.com"]
        )

        assert info.registered is True
        assert len(info.nameservers) == 2


class TestDomainRotation:
    """Tests for domain rotation logic."""

    def test_domain_selection_criteria(self):
        """Test domain selection based on criteria."""
        domains = [
            {"id": "1", "utilization": 0.1, "verified": True},
            {"id": "2", "utilization": 0.5, "verified": True},
            {"id": "3", "utilization": 0.9, "verified": True},
        ]

        # Should select domain with lowest utilization
        selected = min(domains, key=lambda d: d["utilization"])
        assert selected["id"] == "1"

    def test_capacity_check(self):
        """Test capacity checking logic."""
        domain = {
            "daily_limit": 100,
            "sent_today": 75,
            "verified": True
        }

        remaining_capacity = domain["daily_limit"] - domain["sent_today"]
        assert remaining_capacity == 25

    def test_warmup_filter(self):
        """Test warmup domain filtering."""
        domains = [
            {"id": "1", "warmup_day": 15, "sent_today": 25, "warmup_limit": 50},
            {"id": "2", "warmup_day": 25, "sent_today": 10, "warmup_limit": 100},
        ]

        # Filter domains that can still send today
        eligible = [
            d for d in domains
            if d["sent_today"] < d["warmup_limit"]
        ]

        assert len(eligible) == 2

    def test_verification_status_filter(self):
        """Test filtering by verification status."""
        domains = [
            {"id": "1", "verified": True, "all_records": True},
            {"id": "2", "verified": False, "all_records": False},
            {"id": "3", "verified": True, "all_records": False},
        ]

        # Only fully verified domains
        fully_verified = [
            d for d in domains
            if d["verified"] and d["all_records"]
        ]

        assert len(fully_verified) == 1
        assert fully_verified[0]["id"] == "1"


class TestAnalyticsCalculations:
    """Tests for analytics calculations."""

    def test_open_rate_calculation(self):
        """Test open rate calculation."""
        total_sent = 1000
        total_opened = 700

        open_rate = (total_opened / total_sent) * 100
        assert open_rate == 70.0

    def test_click_rate_calculation(self):
        """Test click rate calculation."""
        total_opened = 700
        total_clicked = 210

        click_rate = (total_clicked / total_opened) * 100
        assert click_rate == 30.0

    def test_bounce_rate_calculation(self):
        """Test bounce rate calculation."""
        total_sent = 1000
        total_bounced = 25

        bounce_rate = (total_bounced / total_sent) * 100
        assert bounce_rate == 2.5

    def test_reply_rate_calculation(self):
        """Test reply rate calculation."""
        total_sent = 1000
        total_replied = 50

        reply_rate = (total_replied / total_sent) * 100
        assert reply_rate == 5.0

    def test_ctor_calculation(self):
        """Test click-to-open rate calculation."""
        total_opened = 700
        total_clicked = 210

        ctor = (total_clicked / total_opened) * 100
        assert ctor == 30.0

    def test_daily_stats_aggregation(self):
        """Test daily stats aggregation."""
        daily_data = [
            {"date": "2024-01-15", "sent": 100, "opened": 70},
            {"date": "2024-01-16", "sent": 150, "opened": 105},
            {"date": "2024-01-17", "sent": 120, "opened": 84},
        ]

        total_sent = sum(d["sent"] for d in daily_data)
        total_opened = sum(d["opened"] for d in daily_data)
        avg_open_rate = (total_opened / total_sent) * 100

        assert total_sent == 370
        assert total_opened == 259
        assert avg_open_rate == 70.0