"""
ChampMail CLI - Session state management.

Persists auth token and active context between CLI invocations.
Stored in ~/.champmail/session.json with file-locking for safety.
"""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
from typing import Optional

SESSION_DIR = Path.home() / ".champmail"
SESSION_FILE = SESSION_DIR / "session.json"
HISTORY_FILE = SESSION_DIR / "history"


def _ensure_dir() -> None:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)


def load_session() -> dict:
    _ensure_dir()
    if not SESSION_FILE.exists():
        return {}
    try:
        with open(SESSION_FILE, "r") as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            data = json.load(f)
            fcntl.flock(f, fcntl.LOCK_UN)
            return data
    except (json.JSONDecodeError, OSError):
        return {}


def save_session(data: dict) -> None:
    _ensure_dir()
    with open(SESSION_FILE, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        json.dump(data, f, indent=2)
        fcntl.flock(f, fcntl.LOCK_UN)


def get_token() -> Optional[str]:
    return load_session().get("token")


def get_user_id() -> Optional[str]:
    return load_session().get("user_id")


def get_email() -> Optional[str]:
    return load_session().get("email")


def get_role() -> Optional[str]:
    return load_session().get("role")


def set_auth(token: str, user_id: str, email: str, role: str) -> None:
    data = load_session()
    data.update({"token": token, "user_id": user_id, "email": email, "role": role})
    save_session(data)


def clear_auth() -> None:
    data = load_session()
    for key in ("token", "user_id", "email", "role"):
        data.pop(key, None)
    save_session(data)


def is_logged_in() -> bool:
    return bool(get_token())
