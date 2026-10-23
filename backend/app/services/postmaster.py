"""Google Postmaster Tools v1: yesterday's user-reported spam ratio and domain reputation for a Gmail-facing domain.

Optional: with POSTMASTER_SERVICE_ACCOUNT_JSON unset, `from_settings()` is None and the health columns stay null.
Auth is the service-account JWT bearer flow (RFC 7523) done directly with `cryptography` and httpx, which avoids
pulling google-auth and its sync HTTP stack into an async worker. The domain must be verified in Postmaster Tools
for the service account; an unverified domain is a 403/404 and reads as "no data", not an error.
"""
from __future__ import annotations

import base64
import json
import logging
import time
from typing import Optional

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from app.config import get_settings

log = logging.getLogger("champmail.postmaster")
SCOPE = "https://www.googleapis.com/auth/postmaster.readonly"
API = "https://gmailpostmastertools.googleapis.com/v1"


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


class Postmaster:
    def __init__(self, key_json: str, client: Optional[httpx.AsyncClient] = None):
        info = json.loads(key_json)
        self.email, self.token_uri = info["client_email"], info.get("token_uri", "https://oauth2.googleapis.com/token")
        self._key = serialization.load_pem_private_key(info["private_key"].encode(), password=None)
        self._http = client or httpx.AsyncClient(timeout=15)
        self._token: tuple[str, float] = ("", 0.0)

    async def _access_token(self) -> str:
        if self._token[1] > time.time() + 60:
            return self._token[0]
        now = int(time.time())
        head = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
        claims = _b64(json.dumps({"iss": self.email, "scope": SCOPE, "aud": self.token_uri, "iat": now, "exp": now + 3600}).encode())
        sig = self._key.sign(f"{head}.{claims}".encode(), padding.PKCS1v15(), hashes.SHA256())
        r = await self._http.post(self.token_uri, data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                                                        "assertion": f"{head}.{claims}.{_b64(sig)}"})
        r.raise_for_status()
        self._token = (r.json()["access_token"], time.time() + int(r.json().get("expires_in", 3600)))
        return self._token[0]

    async def stats(self, domain: str) -> Optional[dict]:
        """{spam_rate, reputation} from the newest day Postmaster has, or None (no data, domain not verified there)."""
        r = await self._http.get(f"{API}/domains/{domain}/trafficStats", params={"pageSize": 7},
                                 headers={"Authorization": f"Bearer {await self._access_token()}"})
        if r.status_code in (403, 404):
            return None
        r.raise_for_status()
        days = sorted(r.json().get("trafficStats", []), key=lambda t: t["name"])  # name ends in /trafficStats/YYYYMMDD
        if not days:
            return None
        d = days[-1]
        rep = d.get("domainReputation")
        return {"spam_rate": d.get("userReportedSpamRatio"), "reputation": None if rep in (None, "REPUTATION_CATEGORY_UNSPECIFIED") else rep}


def from_settings() -> Optional[Postmaster]:
    key = get_settings().postmaster_service_account_json.strip()
    if not key:
        return None
    try:
        return Postmaster(key)
    except Exception:
        log.exception("POSTMASTER_SERVICE_ACCOUNT_JSON is set but unusable; Postmaster fields stay null")
        return None
