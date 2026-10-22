"""Tracking URLs end to end: build the real message through POST /api/v1/send, then GET what is in its HTML.

Calibrated against d22ea7c/6a6f37d: there /o/<message_id>.gif and /c/<message_id>?u=... answered 404 on
the real app, so none of these URLs ever produced an event.
"""
from __future__ import annotations

import os
import re
from urllib.parse import urlsplit

import httpx
import pytest
from sqlalchemy import update

from app.api.v1 import send as send_api
from app.api.v1 import tracking as tracking_api
from app.api.v1.deps import get_session
from app.main import app
from app.models import SendDispatch
from app.services import send as svc
from app.services import tracking
from tests.helpers import add_dispatch, outbox
from tests.test_send import HARBINGER, RedisUp, run, seed

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set")

HTML = ('<p>hi <a href="https://example.org/p?a=1&amp;b=2">one</a> <a href="http://other.example.net/x#frag">two</a> '
        '<a href="mailto:a@b.co">mail</a></p>')
BODY = {**HARBINGER, "brand_id": "b1", "html_body": HTML}


class CapSmtp:
    def __init__(self):
        self.msgs = []

    async def send(self, msg, **kw):
        self.msgs.append(msg)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(send_api, "redis_client", RedisUp())
    yield
    app.dependency_overrides.clear()


def wire(Session, monkeypatch):
    smtp = CapSmtp()

    async def session_dep():
        async with Session() as s:
            yield s
    app.dependency_overrides[send_api.get_session] = session_dep
    app.dependency_overrides[get_session] = session_dep
    monkeypatch.setattr(svc.aiosmtplib, "send", smtp.send)
    return smtp


async def send_one(Session, smtp, body=BODY):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://api") as c:
        r = await c.post("/api/v1/send", json=body)
    assert r.status_code == 200, r.text
    html = smtp.msgs[-1].get_body(("html",)).get_content()
    pixel = re.search(r'src="(https://[^"]+/o/[^"]+\.gif)"', html).group(1)
    links = re.findall(r'href="(https://[^"]+/c/[^"]+)"', html)
    return r.json()["message_id"], pixel, links


async def get(url, host=None):
    p = urlsplit(url)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=f"https://{host or p.netloc}") as c:
        return await c.get(p.path)


def kinds(rows):
    return sorted((r.event_type, r.message_id) for r in rows)


def test_generated_open_and_click_urls_work_and_emit_once_with_the_original_message_id(monkeypatch):
    async def go(Session):
        await seed(Session, tracking="trk.acme.io")
        smtp = wire(Session, monkeypatch)
        mid, pixel, links = await send_one(Session, smtp)
        assert len(links) == 2 and urlsplit(pixel).netloc == "trk.acme.io"  # mailto left alone
        out = {"open": [await get(pixel) for _ in range(3)]}
        out["clicks"] = [await get(links[0]), await get(links[0]), await get(links[1])]
        return mid, out, await outbox(Session)
    mid, out, rows = run(go)
    assert [r.status_code for r in out["open"]] == [200] * 3
    assert out["open"][0].headers["content-type"] == "image/gif" and out["open"][0].content[:6] == b"GIF89a"
    assert [r.status_code for r in out["clicks"]] == [302] * 3
    assert out["clicks"][0].headers["location"] == "https://example.org/p?a=1&b=2"  # &amp; undone, destination exact
    assert out["clicks"][2].headers["location"] == "http://other.example.net/x#frag"
    assert kinds(rows) == [("clicked", mid), ("opened", mid)]  # 3 opens + 3 clicks, two events
    assert all(r.status == "pending" and r.attempts == 0 for r in rows)


def test_message_html_no_longer_carries_a_raw_message_id_or_destination_query(monkeypatch):
    async def go(Session):
        await seed(Session)
        smtp = wire(Session, monkeypatch)
        mid, pixel, links = await send_one(Session, smtp)
        return mid, pixel, links
    mid, pixel, links = run(go)
    assert "?u=" not in "".join(links) and mid not in pixel and all(mid not in x for x in links)


def forged(**d):
    """A token carrying a valid signature over arbitrary content (what a stolen secret, or a bug, would make)."""
    import json
    body = tracking._b64(json.dumps(d, separators=(",", ":")).encode())
    return f"{body}.{tracking._mac(body)}"


def test_invalid_tokens_404_and_never_create_an_event(monkeypatch):
    async def go(Session):
        dom, (mb,) = await seed(Session, tracking="trk.acme.io")
        smtp = wire(Session, monkeypatch)
        mid, pixel, links = await send_one(Session, smtp)
        host = "https://trk.acme.io"
        click_tok = links[0].rsplit("/", 1)[1]
        open_tok = pixel.rsplit("/", 1)[1][:-4]
        body, sig = click_tok.rsplit(".", 1)
        evil_body = tracking._b64(b'{"k":"c","m":"%s","d":"%s","u":"https://evil.example"}' % (mid.encode(), str(dom).encode()))
        bad = {
            "garbage": f"{host}/c/not-a-token",
            "empty-sig": f"{host}/c/{body}.",
            "destination swapped, old signature": f"{host}/c/{evil_body}.{sig}",
            "flipped-body": f"{host}/c/{body[:-2]}xx.{sig}",
            "old-format message id + ?u=": f"{host}/c/{mid}?u=https%3A%2F%2Fevil.example",
            "old-format pixel": f"{host}/o/{mid}.gif",
            "click token on /o": f"{host}/o/{click_tok}.gif",
            "open token on /c": f"{host}/c/{open_tok}",
            "open token without .gif": f"{host}/o/{open_tok}",
            "javascript: destination": f"{host}/c/{forged(k='c', m=mid, d=str(dom), u='javascript:alert(1)')}",
            "click without destination": f"{host}/c/{forged(k='c', m=mid, d=str(dom), u=None)}",
            "open with destination": f"{host}/o/{forged(k='o', m=mid, d=str(dom), u='https://evil.example')}.gif",
            "unknown message": f"{host}/o/{tracking.sign('o', 'ghost@x.test', dom)}.gif",
            "domain id not a uuid": f"{host}/o/{forged(k='o', m=mid, d='nope', u=None)}.gif",
        }
        got = {name: (await get(u)).status_code for name, u in bad.items()}
        # signed with some other secret
        st = tracking.get_settings()
        real, st.tracking_secret = st.tracking_secret, "another-secret"
        try:
            other = tracking.sign("c", mid, dom, "https://evil.example")
        finally:
            st.tracking_secret = real
        got["other secret"] = (await get(f"{host}/c/{other}")).status_code
        return got, await outbox(Session)
    got, rows = run(go)
    assert set(got.values()) == {404}, got
    assert rows == []


def test_token_is_bound_to_its_domain_and_its_tracking_host(monkeypatch):
    async def go(Session):
        dom_a, _ = await seed(Session, tracking="trk.a-corp.io")
        dom_b, (mb_b,) = await seed(Session, tracking="trk.b-corp.io")
        smtp = wire(Session, monkeypatch)
        mid, pixel, links = await send_one(Session, smtp, {**BODY, "domain_id": str(dom_a), "brand_id": None})
        res = {
            "own host": (await get(pixel)).status_code,
            "own host with port": (await get(pixel, host="trk.a-corp.io:8443")).status_code,
            "own host, other case": (await get(pixel, host="TRK.A-CORP.IO")).status_code,
            "other domain's tracking host": (await get(pixel, host="trk.b-corp.io")).status_code,
            "api host": (await get(pixel, host="api.champmail.test")).status_code,
            "click on other host": (await get(links[0], host="trk.b-corp.io")).status_code,
        }
        n = len(await outbox(Session))
        # genuinely signed, but names domain B for a message dispatched from domain A
        res["token names wrong domain"] = (await get(f"https://trk.b-corp.io/o/{tracking.sign('o', mid, dom_b)}.gif")).status_code
        res["wrong domain on right host"] = (await get(f"https://trk.a-corp.io/o/{tracking.sign('o', mid, dom_b)}.gif")).status_code
        # a message that really belongs to domain B is fine on B's host and only there
        mid_b = await add_dispatch(Session, dom_b, mb_b)
        tok_b = tracking.sign("o", mid_b, dom_b)
        res["B message on B host"] = (await get(f"https://trk.b-corp.io/o/{tok_b}.gif")).status_code
        res["B message on A host"] = (await get(f"https://trk.a-corp.io/o/{tok_b}.gif")).status_code
        return res, n, await outbox(Session), mid, mid_b
    res, n, rows, mid, mid_b = run(go)
    assert res == {"own host": 200, "own host with port": 200, "own host, other case": 200,
                   "other domain's tracking host": 404, "api host": 404, "click on other host": 404,
                   "token names wrong domain": 404, "wrong domain on right host": 404,
                   "B message on B host": 200, "B message on A host": 404}
    assert n == 1 and kinds(rows) == sorted([("opened", mid), ("opened", mid_b)])


def test_a_domain_whose_tracking_subdomain_was_removed_serves_nothing(monkeypatch):
    async def go(Session):
        dom, _ = await seed(Session, tracking="trk.acme.io")
        smtp = wire(Session, monkeypatch)
        _, pixel, links = await send_one(Session, smtp)
        from app.models import Domain
        async with Session() as s:
            await s.execute(update(Domain).values(tracking_subdomain=None))
            await s.commit()
        return (await get(pixel)).status_code, (await get(links[0])).status_code, await outbox(Session)
    assert run(go) == (404, 404, [])


def test_dispatch_that_never_reached_smtp_is_not_trackable(monkeypatch):
    async def go(Session):
        await seed(Session, tracking="trk.acme.io")
        smtp = wire(Session, monkeypatch)
        _, pixel, _ = await send_one(Session, smtp)
        async with Session() as s:
            await s.execute(update(SendDispatch).values(status="failed"))
            await s.commit()
        return (await get(pixel)).status_code, await outbox(Session)
    assert run(go) == (404, [])


def test_bookkeeping_failure_never_breaks_the_recipients_image_or_redirect(monkeypatch):
    async def go(Session):
        await seed(Session, tracking="trk.acme.io")
        smtp = wire(Session, monkeypatch)
        _, pixel, links = await send_one(Session, smtp)

        async def boom(*a, **k):
            raise RuntimeError("db down")
        monkeypatch.setattr(tracking_api, "emit", boom)
        return (await get(pixel)).status_code, (await get(links[0])).status_code, await outbox(Session)
    assert run(go) == (200, 302, [])


def test_sign_refuses_what_verify_would_refuse():
    for args in (("c", "m", "d", None), ("o", "m", "d", "https://x.example"), ("c", "m", "d", "ftp://x.example"),
                 ("c", "m", "d", "javascript:alert(1)"), ("x", "m", "d", None)):
        with pytest.raises(ValueError):
            tracking.sign(*args)
    t = tracking.sign("c", "m1", "d1", "https://x.example/a?b=c")
    assert tracking.verify(t, "c") == {"message_id": "m1", "domain_id": "d1", "url": "https://x.example/a?b=c"}
    assert tracking.verify(t, "o") is None and tracking.verify(t + "A", "c") is None
