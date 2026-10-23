"""Cloudflare DNS automation on POST /api/v1/domains: mocked Cloudflare API (respx), scripted public resolvers."""
from __future__ import annotations

import asyncio
import json
from itertools import count

import httpx
import pytest
import respx
from sqlalchemy import select

from app.config import get_settings
from app.models import Domain
from app.services import cloudflare_dns as cf
from tests import test_domains_mailboxes_api as base
from tests.test_domains_mailboxes_api import mock_inboxkit, order_domain
from tests.test_mx_checks import Script, run

api = base.api  # the sqlite-backed TestClient fixture, shared rather than copied

CF = "https://api.cloudflare.com/client/v4"
DKIM = [{"name": "google._domainkey", "value": "google.dkim.example.net"}]
WITH_DKIM = [{"uid": "dom_1", "name": "acme-mail.com", "dkim_records": DKIM}]
ZONE = {"success": True, "result": [{"id": "z1"}]}


@pytest.fixture(autouse=True)
def _cloudflare_on(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "cloudflare_api_token", "cf-token")
    monkeypatch.setattr(s, "edge_worker_hostname", "champmail-edge.acme.workers.dev")
    monkeypatch.setattr(s, "dmarc_rua_address", "dmarc+{brand}@rua.example")

    async def visible(domain, lookups=None):
        return True
    monkeypatch.setattr(cf, "propagated", visible)


def cloudflare(mock, *, fail_post_number=None, existing_txt=(), zones=ZONE):
    """Mock the API; returns (posts, deletes). The Nth POST to dns_records (1-based) or `route` fails when asked."""
    posts, deletes, ids = [], [], count(1)
    mock.get(f"{CF}/zones").mock(return_value=httpx.Response(200, json=zones))
    mock.get(f"{CF}/zones/z1/dns_records").mock(return_value=httpx.Response(200, json={"success": True, "result": list(existing_txt)}))

    def create(request):
        body = json.loads(request.content)
        posts.append(body)
        if fail_post_number == len(posts):
            return httpx.Response(400, json={"success": False, "errors": [{"code": 1004, "message": "boom"}]})
        return httpx.Response(200, json={"success": True, "result": {"id": f"r{next(ids)}"}})
    mock.post(f"{CF}/zones/z1/dns_records").mock(side_effect=create)
    mock.post(f"{CF}/zones/z1/workers/routes").mock(side_effect=lambda r: (posts.append({"route": json.loads(r.content)}) or
                                                    httpx.Response(200, json={"success": True, "result": {"id": "route1"}})))

    def delete(request):
        deletes.append(request.url.path.removeprefix("/client/v4"))
        return httpx.Response(200, json={"success": True, "result": {}})
    mock.route(method="DELETE").mock(side_effect=delete)
    return posts, deletes


def test_post_domains_creates_spf_dmarc_dkim_and_track_records_and_the_worker_route(api):
    with respx.mock(assert_all_called=False) as mock:
        mock_inboxkit(mock, order_domains=WITH_DKIM)
        posts, deletes = cloudflare(mock)
        r = order_domain(api)
    assert r.status_code == 201, r.text
    assert posts[:4] == [
        {"type": "TXT", "name": "acme-mail.com", "content": "v=spf1 include:_spf.google.com ~all", "ttl": 1, "proxied": False},
        {"type": "TXT", "name": "_dmarc.acme-mail.com", "content": "v=DMARC1; p=quarantine; rua=mailto:dmarc+brand_1@rua.example", "ttl": 1, "proxied": False},
        {"type": "CNAME", "name": "google._domainkey.acme-mail.com", "content": "google.dkim.example.net", "ttl": 1, "proxied": False},
        {"type": "CNAME", "name": "track.acme-mail.com", "content": "champmail-edge.acme.workers.dev", "ttl": 1, "proxied": True},
    ]
    assert posts[4] == {"route": {"pattern": "track.acme-mail.com/*", "script": "champmail-edge"}} and deletes == []
    assert r.json()["dns_status"] == "propagated" and r.json()["status"] == "ready"


def test_a_failure_on_the_third_record_deletes_the_first_two_and_returns_502_keeping_the_paid_order(api):
    with respx.mock(assert_all_called=False) as mock:
        mock_inboxkit(mock, order_domains=WITH_DKIM)
        posts, deletes = cloudflare(mock, fail_post_number=3)
        r = order_domain(api)
    assert r.status_code == 502 and "rolled back" in r.json()["detail"]["error"]
    assert r.json()["detail"]["order_uid"] == "ord_1"                       # the operator can still find the paid order
    assert len(posts) == 3                                                   # nothing after the failure was attempted
    assert deletes == ["/zones/z1/dns_records/r2", "/zones/z1/dns_records/r1"]
    d = api.get("/api/v1/domains").json()[0]
    assert d["dns_status"] == "failed" and d["status"] == "ordered"


def test_a_failed_worker_route_deletes_all_four_records(api):
    with respx.mock(assert_all_called=False) as mock:
        mock_inboxkit(mock, order_domains=WITH_DKIM)
        posts, deletes = cloudflare(mock)
        mock.post(f"{CF}/zones/z1/workers/routes").mock(return_value=httpx.Response(403, json={"success": False, "errors": [{"message": "no"}]}))
        r = order_domain(api)
    assert r.status_code == 502
    assert deletes == [f"/zones/z1/dns_records/r{i}" for i in (4, 3, 2, 1)]


def test_a_rollback_delete_that_fails_does_not_hide_the_original_error(api, caplog):
    with respx.mock(assert_all_called=False) as mock:
        mock_inboxkit(mock, order_domains=WITH_DKIM)
        cloudflare(mock, fail_post_number=2)
        mock.route(method="DELETE").mock(return_value=httpx.Response(500, json={"success": False, "errors": []}))
        r = order_domain(api)
    assert r.status_code == 502 and "boom" in r.json()["detail"]["error"]
    assert "rollback could not delete /zones/z1/dns_records/r1" in caplog.text    # logged, not swallowed silently


def test_records_not_yet_visible_leave_the_domain_pending_until_the_worker_promotes_it(api, monkeypatch):
    calls = []

    async def not_yet(domain, lookups=None):
        calls.append(domain)
        return False
    monkeypatch.setattr(cf, "PROPAGATION_DELAY", 0)
    monkeypatch.setattr(cf, "propagated", not_yet)
    with respx.mock(assert_all_called=False) as mock:
        mock_inboxkit(mock)
        cloudflare(mock)
        r = order_domain(api)
    assert (r.json()["dns_status"], r.json()["status"]) == ("pending", "ordered")
    assert len(calls) == cf.PROPAGATION_ATTEMPTS                            # retried, bounded, then left to the worker

    seen = {"v=spf1 include:_spf.google.com ~all"}
    full = Script({("acme-mail.com", "TXT"): list(seen), ("_dmarc.acme-mail.com", "TXT"): ["v=DMARC1; p=quarantine"], ("track.acme-mail.com", "A"): ["104.16.0.1"]})
    monkeypatch.undo()  # back to the real propagated(), driven by scripted resolvers
    assert asyncio.run(cf.promote_pending(api.maker, [Script({})])) == 0     # one resolver sees nothing: still pending
    assert asyncio.run(cf.promote_pending(api.maker, [full, full])) == 1

    async def read():
        async with api.maker() as s:
            d = (await s.execute(select(Domain))).scalar_one()
            return d.dns_status, d.status
    assert asyncio.run(read()) == ("propagated", "ready")


def test_promotion_never_overwrites_a_later_inboxkit_state(api, monkeypatch):
    async def not_yet(domain, lookups=None):
        return False
    monkeypatch.setattr(cf, "propagated", not_yet)
    with respx.mock(assert_all_called=False) as mock:
        mock_inboxkit(mock)
        cloudflare(mock)
        order_domain(api)

    async def provisioning():
        async with api.maker() as s:
            (await s.execute(select(Domain))).scalar_one().status = "provisioning"
            await s.commit()
    asyncio.run(provisioning())
    full = Script({("acme-mail.com", "TXT"): ["v=spf1 include:_spf.google.com ~all"], ("_dmarc.acme-mail.com", "TXT"): ["v=DMARC1; p=quarantine"], ("track.acme-mail.com", "A"): ["1.1.1.1"]})
    monkeypatch.undo()
    assert asyncio.run(cf.promote_pending(api.maker, [full])) == 1

    async def read():
        async with api.maker() as s:
            return (await s.execute(select(Domain))).scalar_one().status
    assert asyncio.run(read()) == "provisioning"


def test_propagation_needs_spf_dmarc_and_the_track_host_on_every_resolver(monkeypatch):
    monkeypatch.undo()
    spf, dmarc = ("acme-mail.com", "TXT"), ("_dmarc.acme-mail.com", "TXT")
    good = {spf: ["v=spf1 include:_spf.google.com ~all"], dmarc: ["v=DMARC1; p=quarantine"], ("track.acme-mail.com", "A"): ["1.2.3.4"]}
    assert run(cf.propagated("acme-mail.com", [Script(good), Script(good)])) is True
    for missing in good:
        partial = {k: v for k, v in good.items() if k != missing}
        assert run(cf.propagated("acme-mail.com", [Script(good), Script(partial)])) is False


def test_an_existing_spf_is_left_alone_not_duplicated(api):
    with respx.mock(assert_all_called=False) as mock:
        mock_inboxkit(mock)
        posts, _ = cloudflare(mock, existing_txt=[{"content": '"v=spf1 include:mailgun.org ~all"'}])
        # the same list answers the _dmarc lookup too, so only SPF-shaped content should suppress: DMARC is still created
        r = order_domain(api)
    assert r.status_code == 201
    assert [p["name"] for p in posts if "type" in p] == ["_dmarc.acme-mail.com", "track.acme-mail.com"]


def test_without_a_token_or_without_the_zone_nothing_is_created_and_nothing_fails(api, monkeypatch):
    with respx.mock(assert_all_called=False) as mock:
        mock_inboxkit(mock)
        posts, _ = cloudflare(mock, zones={"success": True, "result": []})
        r = order_domain(api)                                               # zone not in the account
        assert r.status_code == 201 and r.json()["dns_status"] is None and posts == []
        monkeypatch.setattr(get_settings(), "cloudflare_api_token", "")
        r = order_domain(api, domain="other-mail.com")                      # automation off: Cloudflare is never called
        assert r.status_code == 201 and posts == []
        assert [c.request.url.path for c in mock.calls if c.request.url.host == "api.cloudflare.com"] == ["/client/v4/zones"]
