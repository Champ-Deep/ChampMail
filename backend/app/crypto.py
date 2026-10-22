"""Credential encryption at rest.

Harbinger's pattern (ChampHarbinger src/lib/crypto.ts + mailbox/registry.ts):
one key from the environment, JSON in, one opaque token out. Fernet instead of
raw AES-GCM because it is the Python primitive that already does nonce and
auth tag for us.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os

from cryptography.fernet import Fernet


def _fernet() -> Fernet:
    secret = os.environ.get("EMAIL_ENCRYPTION_KEY", "")
    if not secret.strip():
        # Fail closed: minting a throwaway key here would write rows nobody
        # can decrypt after a restart.
        raise RuntimeError("EMAIL_ENCRYPTION_KEY is not set")
    # Harbinger pads the env secret to 32 bytes; hashing gives any-length
    # secret a valid 32-byte key.
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


def encrypt_secret(value: object) -> str:
    return _fernet().encrypt(json.dumps(value).encode()).decode()


def decrypt_secret(token: str) -> object:
    return json.loads(_fernet().decrypt(token.encode()))