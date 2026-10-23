"""Cross-language contract: the tokens ChampMail signs are the tokens the edge Worker verifies.

edge/test/fixtures/tokens.json is the one shared file. This test fails when the Python scheme changes
without the fixture being regenerated (`python tests/test_edge_contract.py`), and the Worker's vitest
suite then fails if the TypeScript verifier did not follow.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.config import get_settings
from app.services import tracking

FIXTURE = Path(__file__).resolve().parents[2] / "edge" / "test" / "fixtures" / "tokens.json"
SECRET = "edge-contract-secret"
MESSAGE_ID = "9f2c1e7a@sender.example"
DOMAIN_ID = "6b1f0c3e-52a4-4c8e-9d11-0a5e2f7b9c44"
CLICK_URL = "https://dest.example/pricing?plan=pro&ref=caf\u00e9#top"  # non-ASCII and a fragment on purpose


def build() -> dict:
    return {
        "secret": SECRET,
        "message_id": MESSAGE_ID,
        "domain_id": DOMAIN_ID,
        "click_url": CLICK_URL,
        "tokens": {
            "o": tracking.sign("o", MESSAGE_ID, DOMAIN_ID),
            "c": tracking.sign("c", MESSAGE_ID, DOMAIN_ID, CLICK_URL),
            "u": tracking.sign("u", MESSAGE_ID, DOMAIN_ID),
        },
    }


def test_fixture_matches_what_the_python_send_path_signs(monkeypatch):
    monkeypatch.setattr(get_settings(), "tracking_secret", SECRET)
    assert json.loads(FIXTURE.read_text()) == build()


def test_python_still_verifies_its_own_fixture(monkeypatch):
    monkeypatch.setattr(get_settings(), "tracking_secret", SECRET)
    t = json.loads(FIXTURE.read_text())["tokens"]
    assert tracking.verify(t["c"], "c") == {"message_id": MESSAGE_ID, "domain_id": DOMAIN_ID, "url": CLICK_URL}
    assert tracking.verify(t["o"], "c") is None and tracking.verify(t["u"], "o") is None


if __name__ == "__main__":  # regenerate the fixture
    get_settings().tracking_secret = SECRET
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(json.dumps(build(), indent=2, ensure_ascii=True) + "\n")
    print("wrote", FIXTURE)
