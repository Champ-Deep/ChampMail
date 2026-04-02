"""
ChampMail CLI — Persistent configuration store.

Stores admin-configured settings in ~/.champmail/config.json:
  - domain (sending domain name, provider)
  - smtp (host, port, user, password, tls, from_name, from_email)
  - imap (host, port, user, password, ssl, mailbox)
  - prospect_defaults (default industry, company, title)
  - campaign_defaults (daily_limit, from_name, from_email, reply_to)
  - ai (openrouter_api_key, model)

All settings here OVERRIDE .env / app.core.config at CLI runtime.
They are written to .env automatically so the backend picks them up too.
"""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
from typing import Any, Optional

SESSION_DIR = Path.home() / ".champmail"
CONFIG_FILE = SESSION_DIR / "config.json"

# Path to project .env (auto-detected)
_ENV_CANDIDATES = [
    Path(__file__).parent.parent.parent / ".env",          # repo root
    Path(__file__).parent.parent / ".env",                  # backend/
    Path.cwd() / ".env",
]


def _env_path() -> Optional[Path]:
    for p in _ENV_CANDIDATES:
        if p.exists():
            return p
    # Default to repo root
    return _ENV_CANDIDATES[0]


# ── low-level load/save ───────────────────────────────────────────────────────

def load_config() -> dict:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        return {}
    try:
        with open(CONFIG_FILE) as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            data = json.load(f)
            fcntl.flock(f, fcntl.LOCK_UN)
            return data
    except (json.JSONDecodeError, OSError):
        return {}


def save_config(data: dict) -> None:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        json.dump(data, f, indent=2)
        fcntl.flock(f, fcntl.LOCK_UN)


def get_section(section: str) -> dict:
    return load_config().get(section, {})


def set_section(section: str, values: dict) -> None:
    cfg = load_config()
    cfg.setdefault(section, {}).update(values)
    save_config(cfg)


def get_value(section: str, key: str, default: Any = None) -> Any:
    return get_section(section).get(key, default)


# ── .env sync ─────────────────────────────────────────────────────────────────

# Maps config section.key → .env variable name
_ENV_MAP = {
    "smtp.host":        "SMTP_HOST",
    "smtp.port":        "SMTP_PORT",
    "smtp.username":    "SMTP_USERNAME",
    "smtp.password":    "SMTP_PASSWORD",
    "smtp.use_tls":     "SMTP_USE_TLS",
    "smtp.from_email":  "MAIL_FROM_EMAIL",
    "smtp.from_name":   "MAIL_FROM_NAME",
    "imap.host":        "IMAP_HOST",
    "imap.port":        "IMAP_PORT",
    "imap.username":    "IMAP_USERNAME",
    "imap.password":    "IMAP_PASSWORD",
    "imap.use_ssl":     "IMAP_USE_SSL",
    "imap.mailbox":     "IMAP_MAILBOX",
    "ai.openrouter_api_key": "OPENROUTER_API_KEY",
    "ai.model":         "GENERAL_MODEL",
}


def sync_to_env() -> None:
    """Write config values back to .env so the FastAPI backend picks them up."""
    env_file = _env_path()
    cfg = load_config()

    # Read existing .env
    existing: dict[str, str] = {}
    lines: list[str] = []
    if env_file and env_file.exists():
        with open(env_file) as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    k, _, v = stripped.partition("=")
                    existing[k.strip()] = v.strip()
                lines.append(line.rstrip("\n"))

    # Build update map
    updates: dict[str, str] = {}
    for dotted_key, env_var in _ENV_MAP.items():
        section, _, key = dotted_key.partition(".")
        val = cfg.get(section, {}).get(key)
        if val is not None:
            updates[env_var] = str(val)

    if not updates:
        return

    # Apply updates
    new_lines = []
    updated_vars: set[str] = set()
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k, _, _ = stripped.partition("=")
            k = k.strip()
            if k in updates:
                new_lines.append(f"{k}={updates[k]}")
                updated_vars.add(k)
                continue
        new_lines.append(line)

    # Append any vars not already in .env
    for k, v in updates.items():
        if k not in updated_vars:
            new_lines.append(f"{k}={v}")

    if env_file:
        env_file.parent.mkdir(parents=True, exist_ok=True)
        with open(env_file, "w") as f:
            f.write("\n".join(new_lines) + "\n")


def apply_to_runtime() -> None:
    """Apply stored config to os.environ so the current process picks them up."""
    cfg = load_config()
    for dotted_key, env_var in _ENV_MAP.items():
        section, _, key = dotted_key.partition(".")
        val = cfg.get(section, {}).get(key)
        if val is not None:
            os.environ[env_var] = str(val)
