"""Credential encryption at rest: key from env only, fail closed, round-trips."""
import os

import pytest

from app.crypto import decrypt_secret, encrypt_secret


def test_missing_key_fails_closed(monkeypatch):
    monkeypatch.delenv("EMAIL_ENCRYPTION_KEY", raising=False)
    with pytest.raises(RuntimeError, match="EMAIL_ENCRYPTION_KEY"):
        encrypt_secret("hunter2")


def test_round_trip_and_no_plaintext_at_rest(monkeypatch):
    monkeypatch.setenv("EMAIL_ENCRYPTION_KEY", "unit-test-key")
    token = encrypt_secret({"password": "hunter2"})
    assert "hunter2" not in token
    assert decrypt_secret(token) == {"password": "hunter2"}


def test_keys_from_a_different_env_do_not_decrypt(monkeypatch):
    monkeypatch.setenv("EMAIL_ENCRYPTION_KEY", "unit-test-key")
    token = encrypt_secret("secret")
    monkeypatch.setenv("EMAIL_ENCRYPTION_KEY", "some-other-key")
    with pytest.raises(Exception):
        decrypt_secret(token)