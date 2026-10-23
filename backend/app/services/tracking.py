"""Signed open/click tokens. The token carries message_id, sending domain and (clicks) the destination.

token = base64url(json) "." base64url(HMAC-SHA256(TRACKING_SECRET, json)). The destination is inside
the signature, so /c/<token> can only redirect where ChampMail itself put a link: no open redirect.
Rotating TRACKING_SECRET invalidates every link already sent.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Optional
from urllib.parse import urlsplit

from app.config import get_settings

KINDS = ("o", "c", "u")  # open, click, one-click unsubscribe (/u/<token>, no destination)


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _mac(body: str) -> str:
    key = get_settings().tracking_secret.strip().encode()
    return _b64(hmac.new(key, b"champmail-tracking-v1." + body.encode(), hashlib.sha256).digest())


def is_http_url(url: str) -> bool:
    p = urlsplit(url)
    return p.scheme in ("http", "https") and bool(p.netloc)


def sign(kind: str, message_id: str, domain_id, url: Optional[str] = None) -> str:
    if kind not in KINDS or (kind == "c") != bool(url):
        raise ValueError("clicks need a destination and opens must not have one")
    if url and not is_http_url(url):
        raise ValueError("destination must be http(s)")
    body = _b64(json.dumps({"k": kind, "m": message_id, "d": str(domain_id), "u": url}, separators=(",", ":")).encode())
    return f"{body}.{_mac(body)}"


def verify(token: str, kind: str) -> Optional[dict]:
    """Return {message_id, domain_id, url} for a genuine token of this kind, else None."""
    try:
        body, sig = token.split(".")
        if not hmac.compare_digest(sig.encode(), _mac(body).encode()):
            return None
        d = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if d["k"] != kind or not d["m"] or not d["d"] or (kind == "c") != bool(d["u"]):
            return None
        if d["u"] and not is_http_url(d["u"]):
            return None
        return {"message_id": d["m"], "domain_id": d["d"], "url": d["u"]}
    except Exception:  # malformed, truncated, wrong types: all the same answer
        return None
