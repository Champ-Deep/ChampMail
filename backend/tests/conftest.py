"""Test environment, set before any test module imports app.config.

get_settings() is lru_cached and bound at import time by the lifted modules,
so these must land before collection imports them (pytest loads conftest first).
"""
import os

os.environ.setdefault("CHAMPMAIL_ENV", "development")
os.environ.setdefault("INBOXKIT_API_KEY", "test-key")
os.environ.setdefault("INBOXKIT_WORKSPACE_ID", "ws_test")