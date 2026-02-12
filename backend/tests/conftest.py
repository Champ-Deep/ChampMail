"""
pytest configuration and fixtures for ChampMail backend tests.
"""

import asyncio
import pytest
import pytest_asyncio
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

# Set environment variables before importing app modules
import os
os.environ["TESTING"] = "true"
os.environ["DATABASE_URL"] = "postgresql+asyncpg://champmail:champmail_dev@localhost:5432/champmail"
os.environ["REDIS_URL"] = "redis://localhost:6379/15"
os.environ["FALKORDB_HOST"] = "localhost"
os.environ["FALKORDB_PORT"] = "6379"
os.environ["MAIL_ENGINE_URL"] = "http://localhost:8025"
os.environ["JWT_SECRET_KEY"] = "test-jwt-secret-key"
os.environ["DEBUG"] = "true"


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_domain_data() -> dict:
    """Sample domain data for testing."""
    return {
        "id": "test-domain-uuid-1234",
        "domain_name": "test.example.com",
        "status": "verified",
        "mx_verified": True,
        "spf_verified": True,
        "dkim_verified": True,
        "dmarc_verified": True,
        "dkim_selector": "champmail",
        "daily_send_limit": 100,
        "sent_today": 25,
        "warmup_enabled": True,
        "warmup_day": 15,
        "health_score": 95.5,
        "bounce_rate": 0.5,
    }


@pytest.fixture
def mock_prospect_data() -> dict:
    """Sample prospect data for testing."""
    return {
        "id": "test-prospect-uuid-1234",
        "email": "john.doe@example.com",
        "first_name": "John",
        "last_name": "Doe",
        "full_name": "John Doe",
        "company_name": "Acme Corp",
        "company_domain": "acme.com",
        "job_title": "CTO",
        "industry": "Technology",
        "status": "active",
    }


@pytest.fixture
def mock_sequence_data() -> dict:
    """Sample sequence data for testing."""
    return {
        "id": "test-sequence-uuid-1234",
        "name": "Outreach Sequence",
        "description": "Multi-step outreach campaign",
        "status": "active",
        "default_delay_hours": 24,
        "auto_pause_on_reply": True,
        "daily_limit": 100,
    }


@pytest.fixture
def mock_campaign_data() -> dict:
    """Sample campaign data for testing."""
    return {
        "id": "test-campaign-uuid-1234",
        "name": "Product Launch Campaign",
        "description": "Launch email campaign",
        "status": "draft",
        "from_name": "ChampMail Team",
        "daily_limit": 500,
        "total_prospects": 1000,
    }


@pytest.fixture
def mock_send_stats() -> dict:
    """Sample send stats for testing."""
    return {
        "domain_id": "test-domain-uuid",
        "today_sent": 25,
        "today_limit": 100,
        "total_sent": 5000,
        "total_opened": 3500,
        "total_clicked": 1500,
        "total_bounced": 100,
        "open_rate": 70.0,
        "click_rate": 30.0,
        "bounce_rate": 2.0,
    }


@pytest.fixture
def mock_dns_records() -> list:
    """Sample DNS records for testing."""
    return [
        {"type": "MX", "name": "example.com", "value": "10 mail.example.com", "priority": 10, "ttl": 3600},
        {"type": "TXT", "name": "example.com", "value": "v=spf1 include:_spf.example.com ~all", "ttl": 3600},
        {"type": "TXT", "name": "_dmarc.example.com", "value": "v=DMARC1; p=none", "ttl": 3600},
    ]


@pytest.fixture
def mock_health_check() -> dict:
    """Sample health check response."""
    return {
        "status": "healthy",
        "postgresql": True,
        "redis": True,
        "version": "1.0.0",
    }


class MockMailEngineClient:
    """Mock mail engine client for testing."""

    async def send_email(self, **kwargs) -> dict:
        return {
            "message_id": "test-msg-uuid-1234",
            "status": "accepted",
            "domain_id": kwargs.get("domain_id", ""),
            "sent_at": "2024-01-15T10:30:00Z",
        }

    async def send_batch(self, emails: list, domain_id: str = "") -> dict:
        return {
            "total": len(emails),
            "successful": len(emails),
            "failed": 0,
            "results": [
                {
                    "message_id": f"test-msg-{i}",
                    "status": "accepted",
                    "domain_id": domain_id,
                    "sent_at": "2024-01-15T10:30:00Z",
                }
                for i in range(len(emails))
            ],
        }

    async def list_domains(self) -> list:
        return []

    async def verify_domain(self, domain_id: str) -> dict:
        return {
            "domain": "test.example.com",
            "mx_verified": True,
            "spf_valid": True,
            "dkim_valid": True,
            "dmarc_valid": True,
            "all_verified": True,
        }

    async def get_send_stats(self, domain_id: str = "") -> dict:
        return {
            "domain_id": domain_id or "default",
            "today_sent": 25,
            "today_limit": 100,
            "total_sent": 5000,
            "total_opened": 3500,
            "total_clicked": 1500,
            "total_bounced": 100,
            "open_rate": 70.0,
            "click_rate": 30.0,
            "bounce_rate": 2.0,
        }


class MockCloudflareClient:
    """Mock Cloudflare client for testing."""

    async def verify_dns_propagation(self, zone_id: str) -> dict:
        return {
            "mx": True,
            "spf": True,
            "dkim": True,
            "dmarc": True,
            "all_verified": True,
        }

    async def check_domain_health(self, zone_id: str) -> dict:
        return {
            "score": 100.0,
            "all_verified": True,
            "details": {"mx": True, "spf": True, "dkim": True, "dmarc": True},
        }


class MockNamecheapClient:
    """Mock Namecheap client for testing."""

    async def search_domains(self, keyword: str, tlds: list = None) -> list:
        return [
            {"domain": f"{keyword}.com", "available": True, "price": 12.99, "currency": "USD"},
            {"domain": f"{keyword}.io", "available": True, "price": 39.99, "currency": "USD"},
        ]

    async def purchase_domain(self, domain: str, years: int = 1) -> dict:
        return {
            "success": True,
            "order_id": "order-12345",
            "transaction_id": "txn-12345",
            "domain": domain,
        }


@pytest.fixture
def mock_mail_engine_client() -> MockMailEngineClient:
    """Provide mock mail engine client."""
    return MockMailEngineClient()


@pytest.fixture
def mock_cloudflare_client() -> MockCloudflareClient:
    """Provide mock Cloudflare client."""
    return MockCloudflareClient()


@pytest.fixture
def mock_namecheap_client() -> MockNamecheapClient:
    """Provide mock Namecheap client."""
    return MockNamecheapClient()


def create_mock_response(status_code: int = 200, json_data: dict = None, text_data: str = None):
    """Create a mock httpx response."""
    response = MagicMock()
    response.status_code = status_code
    response.is_success = status_code >= 200 and status_code < 300
    if json_data:
        response.json.return_value = json_data
    if text_data:
        response.text = text_data
    return response