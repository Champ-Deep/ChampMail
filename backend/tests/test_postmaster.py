"""Google Postmaster Tools client: a real RSA service-account key signing a real JWT, Google endpoints mocked (respx)."""
from __future__ import annotations

import asyncio
import base64
import json

import httpx
import respx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app.config import get_settings
from app.services import postmaster

TOKEN = "https://oauth2.example/token"
API = postmaster.API


def key_json():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    return json.dumps({"client_email": "svc@proj.iam.example", "private_key": pem, "token_uri": TOKEN}), key.public_key()


def test_unset_means_no_client_and_garbage_means_no_client_not_a_crash(monkeypatch):
    monkeypatch.setattr(get_settings(), "postmaster_service_account_json", "")
    assert postmaster.from_settings() is None
    monkeypatch.setattr(get_settings(), "postmaster_service_account_json", "{not json")
    assert postmaster.from_settings() is None


def test_newest_day_wins_the_assertion_is_a_valid_rs256_jwt_and_unspecified_reputation_is_null():
    kj, public = key_json()
    pm = postmaster.Postmaster(kj)
    with respx.mock() as mock:
        tok = mock.post(TOKEN).mock(return_value=httpx.Response(200, json={"access_token": "ya29.x", "expires_in": 3600}))
        stats = mock.get(f"{API}/domains/acme-mail.test/trafficStats").mock(return_value=httpx.Response(200, json={"trafficStats": [
            {"name": "domains/acme-mail.test/trafficStats/20261021", "userReportedSpamRatio": 0.5, "domainReputation": "LOW"},
            {"name": "domains/acme-mail.test/trafficStats/20261022", "userReportedSpamRatio": 0.003, "domainReputation": "HIGH"}]}))
        assert asyncio.run(pm.stats("acme-mail.test")) == {"spam_rate": 0.003, "reputation": "HIGH"}
        assert stats.calls.last.request.headers["authorization"] == "Bearer ya29.x"
        form = dict(p.split("=") for p in tok.calls.last.request.content.decode().split("&"))
        head, claims, sig = form["assertion"].split(".")
        pad = lambda s: s + "=" * (-len(s) % 4)  # noqa: E731
        public.verify(base64.urlsafe_b64decode(pad(sig)), f"{head}.{claims}".encode(), padding.PKCS1v15(), hashes.SHA256())  # raises if forged
        assert json.loads(base64.urlsafe_b64decode(pad(claims)))["scope"] == postmaster.SCOPE
        asyncio.run(pm.stats("acme-mail.test"))
        assert tok.call_count == 1                                       # the token is cached
        stats.mock(return_value=httpx.Response(200, json={"trafficStats": [{"name": "domains/x/trafficStats/20261022", "domainReputation": "REPUTATION_CATEGORY_UNSPECIFIED"}]}))
        assert asyncio.run(pm.stats("acme-mail.test")) == {"spam_rate": None, "reputation": None}


def test_a_domain_not_verified_in_postmaster_or_with_no_data_is_none_and_an_outage_raises():
    pm = postmaster.Postmaster(key_json()[0])
    with respx.mock() as mock:
        mock.post(TOKEN).mock(return_value=httpx.Response(200, json={"access_token": "t", "expires_in": 3600}))
        route = mock.get(f"{API}/domains/acme-mail.test/trafficStats")
        route.mock(return_value=httpx.Response(403, json={}))
        assert asyncio.run(pm.stats("acme-mail.test")) is None
        route.mock(return_value=httpx.Response(200, json={}))
        assert asyncio.run(pm.stats("acme-mail.test")) is None
        route.mock(return_value=httpx.Response(503))
        try:
            asyncio.run(pm.stats("acme-mail.test"))
        except httpx.HTTPStatusError:
            pass
        else:
            raise AssertionError("a 5xx must surface so the daily job logs it and leaves the fields null")
