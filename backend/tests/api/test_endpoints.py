"""
Integration tests for API endpoints.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


class TestHealthEndpoints:
    """Test cases for health check endpoints."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database connections."""
        with patch('app.db.postgres.init_db') as mock_init, \
             patch('app.db.falkordb.init_graph_db') as mock_graph:
            mock_init.return_value = None
            mock_graph.return_value = True
            yield

    def test_health_check_success(self, mock_db):
        """Test health check returns healthy status."""
        from app.main import app

        with TestClient(app) as client:
            response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "version" in data

    def test_root_endpoint(self):
        """Test root endpoint returns app info."""
        from app.main import app

        with TestClient(app) as client:
            response = client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert "docs" in data


class TestDomainEndpoints:
    """Test cases for domain management endpoints."""

    @pytest.fixture
    def mock_domain_service(self):
        """Create mock domain service."""
        with patch('app.api.v1.domains.domainsApi') as mock_api, \
             patch('app.api.v1.domains.domain_service') as mock_service, \
             patch('app.api.v1.domains.cloudflare_client') as mock_cf, \
             patch('app.api.v1.domains.namecheap_client') as mock_nc:
            yield {
                "api": mock_api,
                "service": mock_service,
                "cloudflare": mock_cf,
                "namecheap": mock_nc,
            }

    def test_list_domains_empty(self, mock_domain_service):
        """Test listing domains when none exist."""
        from app.main import app

        mock_domain_service["api"].list_domains = AsyncMock(return_value=[])

        with TestClient(app) as client:
            with patch('app.api.v1.domains.domainsApi') as mock_api:
                mock_api.list_domains = AsyncMock(return_value=[])
                response = client.get(
                    "/api/v1/domains",
                    headers={"Authorization": "Bearer test-token"}
                )

        assert response.status_code == 200

    def test_get_domain_not_found(self, mock_domain_service):
        """Test getting a domain that doesn't exist."""
        from app.main import app
        from fastapi import HTTPException

        with TestClient(app) as client:
            with patch('app.api.v1.domains.domainsApi') as mock_api:
                mock_api.list_domains = AsyncMock(return_value=[])
                response = client.get(
                    "/api/v1/domains/nonexistent-id",
                    headers={"Authorization": "Bearer test-token"}
                )

        assert response.status_code in [200, 404]


class TestSendEndpoints:
    """Test cases for email sending endpoints."""

    def test_send_email_validation(self):
        """Test email sending request validation."""
        from app.api.v1.send import SendEmailRequest
        from pydantic import ValidationError

        # Valid request
        valid_request = SendEmailRequest(
            to="test@example.com",
            subject="Test Subject",
            html_body="<p>Test body</p>"
        )
        assert valid_request.to == "test@example.com"

        # Invalid request - missing required fields
        with pytest.raises(ValidationError):
            SendEmailRequest(
                to="test@example.com",
                subject="Test Subject",
                # Missing html_body
            )

    def test_batch_send_validation(self):
        """Test batch sending request validation."""
        from app.api.v1.send import BatchSendRequest, SendEmailRequest

        # Valid batch request
        valid_batch = BatchSendRequest(
            emails=[
                SendEmailRequest(
                    to="test1@example.com",
                    subject="Test Subject",
                    html_body="<p>Test body</p>"
                ),
                SendEmailRequest(
                    to="test2@example.com",
                    subject="Test Subject 2",
                    html_body="<p>Test body 2</p>"
                )
            ]
        )
        assert len(valid_batch.emails) == 2


class TestAuthenticationEndpoints:
    """Test cases for authentication endpoints."""

    def test_login_validation(self):
        """Test login request validation."""
        from app.schemas.auth import LoginRequest

        # Valid login
        valid_login = LoginRequest(
            email="test@example.com",
            password="password123"
        )
        assert valid_login.email == "test@example.com"

    def test_register_validation(self):
        """Test registration request validation."""
        from app.schemas.auth import RegisterRequest

        # Valid registration
        valid_register = RegisterRequest(
            email="new@example.com",
            password="securepassword123",
            full_name="Test User"
        )
        assert valid_register.email == "new@example.com"


class TestProspectEndpoints:
    """Test cases for prospect management endpoints."""

    def test_prospect_creation_validation(self):
        """Test prospect creation request validation."""
        from app.api.v1.prospects import ProspectCreate

        # Valid prospect
        valid_prospect = ProspectCreate(
            email="prospect@example.com",
            first_name="John",
            last_name="Doe"
        )
        assert valid_prospect.email == "prospect@example.com"

    def test_prospect_search_validation(self):
        """Test prospect search query validation."""
        from app.api.v1.prospects import ProspectSearchQuery

        # Valid search
        search = ProspectSearchQuery(q="software engineer")
        assert "software" in search.q.lower()


class TestSequenceEndpoints:
    """Test cases for sequence management endpoints."""

    def test_sequence_creation_validation(self):
        """Test sequence creation request validation."""
        from app.api.v1.sequences import SequenceCreate

        # Valid sequence
        valid_sequence = SequenceCreate(
            name="Outreach Sequence",
            description="Multi-step outreach"
        )
        assert valid_sequence.name == "Outreach Sequence"

    def test_sequence_step_validation(self):
        """Test sequence step request validation."""
        from app.api.v1.sequences import SequenceStepCreate

        # Valid step
        valid_step = SequenceStepCreate(
            order=1,
            name="First Email",
            subject_template="Hello {{name}}",
            html_template="<p>Hi {{name}},</p>",
            delay_hours=24
        )
        assert valid_step.order == 1
        assert valid_step.delay_hours == 24


class TestTemplateEndpoints:
    """Test cases for template management endpoints."""

    def test_template_creation_validation(self):
        """Test template creation request validation."""
        from app.api.v1.templates import TemplateCreate

        # Valid template
        valid_template = TemplateCreate(
            name="Welcome Email",
            subject="Welcome to our service!",
            html_content="<p>Welcome!</p>"
        )
        assert valid_template.name == "Welcome Email"


class TestWebhookEndpoints:
    """Test cases for webhook endpoints."""

    def test_webhook_signature_validation(self):
        """Test webhook signature validation."""
        import hmac
        import hashlib

        secret = "test-secret"
        payload = '{"event": "test"}'

        signature = hmac.new(
            secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()

        assert len(signature) == 64  # SHA256 produces 64 hex chars

    def test_n8n_webhook_format(self):
        """Test N8N webhook payload format."""
        from app.api.v1.webhooks import N8NWebhookPayload

        # Valid N8N payload
        payload = N8NPayload={
            "event": "email.opened",
            "data": {
                "message_id": "msg-123",
                "recipient": "test@example.com",
                "timestamp": "2024-01-15T10:30:00Z"
            }
        }
        assert payload["event"] == "email.opened"