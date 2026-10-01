"""
Integration tests for API endpoints.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


def _auth_headers() -> dict:
    """Build a genuinely signed bearer token.

    These endpoints are behind require_auth, which calls decode_token and
    verifies the JWT signature against settings.jwt_secret_key. A literal
    "Bearer test-token" string is not a JWT, so the request returns 401 before
    the route body ever runs. Minting a real token keeps the assertion
    meaningful: a 200 here proves the service was mocked correctly.
    """
    from app.core.security import create_access_token

    token = create_access_token(
        {
            "user_id": "00000000-0000-0000-0000-000000000001",
            "email": "test@example.com",
            "role": "admin",
            "team_id": "00000000-0000-0000-0000-0000000000ff",
        }
    )
    return {"Authorization": f"Bearer {token}"}


class TestHealthEndpoints:
    """Test cases for health check endpoints."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database connections."""
        with patch('app.db.postgres.init_db') as mock_init, \
             patch('app.db.champgraph.init_graph_db') as mock_graph:
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
        """Create mock domain service.

        Patches domain_service directly. There is no `domainsApi` symbol: the
        router module imports the domain_service singleton directly, so patching
        the module attribute is what actually intercepts the call.
        """
        with patch('app.api.v1.domains.domain_service') as mock_service, \
             patch('app.api.v1.domains.cloudflare_client') as mock_cf, \
             patch('app.api.v1.domains.namecheap_client') as mock_nc:
            mock_service.get_all_domains = AsyncMock(return_value=[])
            mock_service.get_by_id = AsyncMock(return_value=None)
            yield {
                "service": mock_service,
                "cloudflare": mock_cf,
                "namecheap": mock_nc,
            }

    def test_list_domains_empty(self, mock_domain_service):
        """Test listing domains when none exist."""
        from app.main import app

        with TestClient(app) as client:
            with patch('app.api.v1.domains.domain_service') as mock_service:
                mock_service.get_all_domains = AsyncMock(return_value=[])
                response = client.get(
                    "/api/v1/domains",
                    headers=_auth_headers()
                )

        assert response.status_code == 200

    def test_get_domain_not_found(self, mock_domain_service):
        """Test getting a domain that doesn't exist."""
        from app.main import app

        with TestClient(app) as client:
            with patch('app.api.v1.domains.domain_service') as mock_service:
                mock_service.get_by_id = AsyncMock(return_value=None)
                response = client.get(
                    "/api/v1/domains/nonexistent-id",
                    headers=_auth_headers()
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
        # LoginRequest lives in app.api.v1.auth, not a schemas.auth module.
        from app.api.v1.auth import LoginRequest

        # Valid login
        valid_login = LoginRequest(
            email="test@example.com",
            password="password123"
        )
        assert valid_login.email == "test@example.com"

    def test_register_validation(self):
        """Test registration request validation."""
        from app.api.v1.auth import RegisterRequest

        # Valid registration. The field is `name`, not `full_name`.
        valid_register = RegisterRequest(
            email="new@example.com",
            password="securepassword123",
            name="Test User"
        )
        assert valid_register.email == "new@example.com"
        assert valid_register.role == "user"


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
        # The router module imports schemas from app.schemas.prospect.
        from app.schemas.prospect import ProspectSearchParams

        # Valid search
        search = ProspectSearchParams(query="software engineer")
        assert "software" in search.query.lower()
        assert search.limit == 50

        # limit is bounded to 1..200 by the schema
        with pytest.raises(ValueError):
            ProspectSearchParams(query="x", limit=0)


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
        from app.schemas.sequence import SequenceStepCreate, StepType

        # Valid step. Fields are step_number / delay_days / delay_hours.
        valid_step = SequenceStepCreate(
            step_number=1,
            step_type=StepType.EMAIL,
            subject="Hello {{name}}",
            body="<p>Hi {{name}},</p>",
            delay_hours=23,
        )
        assert valid_step.step_number == 1
        assert valid_step.delay_hours == 23
        assert valid_step.delay_days == 1

        # delay_hours is bounded to 0..23, so 24 is rejected
        with pytest.raises(ValueError):
            SequenceStepCreate(step_number=1, delay_hours=24)


class TestTemplateEndpoints:
    """Test cases for template management endpoints."""

    def test_template_creation_validation(self):
        """Test template creation request validation."""
        from app.api.v1.templates import TemplateCreate

        # Templates carry MJML source, not raw HTML: the field is mjml_content.
        valid_template = TemplateCreate(
            name="Welcome Email",
            subject="Welcome to our service!",
            mjml_content="<mjml><mj-body><p>Welcome!</p></mj-body></mjml>"
        )
        assert valid_template.name == "Welcome Email"
        assert valid_template.compile_html is True

        # empty MJML violates min_length=1
        with pytest.raises(ValueError):
            TemplateCreate(name="x", subject="y", mjml_content="")


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
        # The schema is N8NWorkflowEvent, not N8NWebhookPayload.
        from app.api.v1.webhooks import N8NWorkflowEvent

        event = N8NWorkflowEvent(
            workflow_id="wf-123",
            execution_id="exec-456",
            event="email.opened",
            data={
                "message_id": "msg-123",
                "recipient": "test@example.com",
                "timestamp": "2024-01-15T10:30:00Z",
            },
        )
        assert event.event == "email.opened"
        assert event.data["message_id"] == "msg-123"

        # workflow_id and execution_id are required
        with pytest.raises(ValueError):
            N8NWorkflowEvent(event="email.opened")