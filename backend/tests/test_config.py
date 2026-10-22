import pytest
from fastapi.testclient import TestClient

from app.config import Settings


def test_production_fails_closed_without_secrets():
    with pytest.raises(ValueError, match="CHAMPMAIL_API_KEY"):
        Settings(champmail_env="production", champmail_api_key="", champmail_webhook_secret="x")
    with pytest.raises(ValueError, match="CHAMPMAIL_WEBHOOK_SECRET"):
        Settings(champmail_env="production", champmail_api_key="x", champmail_webhook_secret=" ")


def test_production_ok_with_secrets_and_dev_ok_without():
    Settings(champmail_env="production", champmail_api_key="a", champmail_webhook_secret="b")
    Settings(champmail_env="development")


def test_healthz():
    from app.main import app

    assert TestClient(app).get("/healthz").json() == {"status": "ok"}
