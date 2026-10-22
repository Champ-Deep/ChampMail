"""Test environment, set before any test module imports app.config.

get_settings() is lru_cached and bound at import time by the lifted modules,
so these must land before collection imports them (pytest loads conftest first).
"""
import os

os.environ.setdefault("CHAMPMAIL_ENV", "development")
# Assigned, not setdefault: the stack's .env can leave these present-but-blank or real,
# and either one must not change what the tests see.
os.environ["CHAMPMAIL_API_KEY"] = ""  # keyless unless a test sets its own
os.environ["INBOXKIT_API_KEY"] = "test-key"
os.environ["INBOXKIT_WORKSPACE_ID"] = "ws_test"
# Blank or missing is a startup error now; the stack's value (if any) is kept.
os.environ["EMAIL_ENCRYPTION_KEY"] = os.environ.get("EMAIL_ENCRYPTION_KEY", "").strip() or "test-encryption-key"
