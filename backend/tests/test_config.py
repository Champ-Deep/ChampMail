import os
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from app.config import Settings


def test_production_fails_closed_without_secrets():
    with pytest.raises(ValueError, match="CHAMPMAIL_API_KEY"):
        Settings(champmail_env="production", champmail_api_key="", champmail_webhook_secret="x", email_encryption_key="k", tracking_secret="t")
    with pytest.raises(ValueError, match="CHAMPMAIL_WEBHOOK_SECRET"):
        Settings(champmail_env="production", champmail_api_key="x", champmail_webhook_secret=" ", email_encryption_key="k", tracking_secret="t")


def test_production_ok_with_secrets_and_dev_ok_without():
    Settings(champmail_env="production", champmail_api_key="a", champmail_webhook_secret="b", email_encryption_key="k", tracking_secret="t")
    Settings(champmail_env="development", email_encryption_key="k", tracking_secret="t")


def test_healthz():
    from app.main import app

    assert TestClient(app).get("/healthz").json() == {"status": "ok"}


@pytest.mark.parametrize("env", ["development", "production"])
@pytest.mark.parametrize("key", ["", "   \t"])
def test_blank_encryption_key_is_refused_in_every_environment(env, key):
    with pytest.raises(ValueError, match="EMAIL_ENCRYPTION_KEY"):
        Settings(champmail_env=env, champmail_api_key="a", champmail_webhook_secret="b", email_encryption_key=key, tracking_secret="t")


@pytest.mark.parametrize("module", ["app.main", "app.worker"])
@pytest.mark.parametrize("key", ["", "  "])
def test_process_exits_nonzero_at_startup_without_encryption_key(module, key):
    """Real interpreter, real import: the API and the worker both refuse to start."""
    env = {**os.environ, "EMAIL_ENCRYPTION_KEY": key, "CHAMPMAIL_ENV": "production",
           "CHAMPMAIL_API_KEY": "a", "CHAMPMAIL_WEBHOOK_SECRET": "b", "TRACKING_SECRET": "t"}
    p = subprocess.run([sys.executable, "-c", f"import {module}"], capture_output=True, text=True, env=env)
    assert p.returncode != 0 and "EMAIL_ENCRYPTION_KEY" in p.stderr


def test_process_starts_with_a_key():
    env = {**os.environ, "EMAIL_ENCRYPTION_KEY": "k", "CHAMPMAIL_ENV": "production",
           "CHAMPMAIL_API_KEY": "a", "CHAMPMAIL_WEBHOOK_SECRET": "b", "TRACKING_SECRET": "t"}
    assert subprocess.run([sys.executable, "-c", "import app.main, app.worker"], env=env).returncode == 0


@pytest.mark.parametrize("module", ["app.main", "app.worker"])
@pytest.mark.parametrize("secret", ["", "  "])
def test_process_exits_nonzero_at_startup_without_tracking_secret(module, secret):
    env = {**os.environ, "EMAIL_ENCRYPTION_KEY": "k", "TRACKING_SECRET": secret, "CHAMPMAIL_ENV": "development"}
    p = subprocess.run([sys.executable, "-c", f"import {module}"], capture_output=True, text=True, env=env)
    assert p.returncode != 0 and "TRACKING_SECRET" in p.stderr
