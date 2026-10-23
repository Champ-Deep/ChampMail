"""The daily domain health job and what GET /api/v1/domains reports from it. Real Postgres, scripted DNS."""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import Bounce, DmarcReport, DnsblZone, Domain, DomainHealthDaily
from app.services import domain_health as dh
from app.services.outbound_events import emit
from tests.helpers import add_dispatch
from tests.test_mx_checks import Script
from tests.test_send import run, seed

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set")
NAME = "acme-mail.test"
HEALTHY = {
    (NAME, "TXT"): ["v=spf1 include:_spf.google.com ~all"],
    (f"google._domainkey.{NAME}", "TXT"): ["v=DKIM1; k=rsa; p=MIIBIjAN"],
    (f"_dmarc.{NAME}", "TXT"): ["v=DMARC1; p=quarantine; rua=mailto:r@x.test"],
}
LISTED = {**HEALTHY, (NAME, "A"): ["198.51.100.7"], ("7.100.51.198.zen.spamhaus.org", "A"): ["127.0.0.2"]}


async def noingest(*_a, **_k):
    return 0


async def world(Session, answers, *, box_kw=None, dom_kw=None):
    dom, boxes = await seed(Session, n=2, dom_kw={"domain_name": NAME, **(dom_kw or {})}, box_kw={"platform": "google", **(box_kw or {})})
    async with Session() as s:
        s.add_all([DnsblZone(name="spamhaus_zen", zone="zen.spamhaus.org", kind="ip", enabled=True),
                   DnsblZone(name="surbl", zone="multi.surbl.org", kind="domain", enabled=True)])
        await s.commit()
    return dom, boxes, Script(answers)


async def job(Session, lookup, **kw):
    return await dh.run_daily(Session, lookup=lookup, ingest=noingest, **kw)


def test_listed_domain_shows_dnsbl_listed_on_get_domains_after_one_job_run(client):
    async def go(Session):
        async def scenario(c):
            dom, _, lookup = await world(Session, LISTED)
            assert (await c.get("/api/v1/domains")).json()[0]["dnsbl_listed"] is False   # before any run
            assert await job(Session, lookup) == 1
            d = (await c.get("/api/v1/domains")).json()[0]
            assert d["dnsbl_listed"] is True and d["dnsbl_lists"] == ["spamhaus_zen"]
            assert (d["spfVerified"], d["dkimVerified"], d["dmarcVerified"]) == (True, True, True)
            assert d["dmarc_policy"] == "quarantine" and d["mta_sts_ok"] is False and d["healthy"] is False
            assert "DNSBL" in d["reason"]
            async with Session() as s:
                row = (await s.execute(select(DomainHealthDaily))).scalar_one()
                assert (row.domain_id, row.day, row.dnsbl_listed, row.source) == (dom, datetime.utcnow().date(), ["spamhaus_zen"], "dns")
        await client(Session, scenario)
    run(go)


def test_clean_domain_is_healthy_and_a_listing_clears_on_a_later_run(client):
    async def go(Session):
        async def scenario(c):
            dom, _, lookup = await world(Session, LISTED)
            await job(Session, lookup)
            async with Session() as s:  # next day, the listing is gone
                lookup2 = Script(HEALTHY)
                tomorrow = datetime.utcnow().date() + timedelta(days=1)
                await dh.run_daily(Session, lookup=lookup2, ingest=noingest, today=tomorrow)
                d = await s.get(Domain, dom)
                await s.refresh(d)
                assert d.blacklisted is False and d.blacklist_hits == 0
            listed = (await c.get("/api/v1/domains")).json()[0]
            assert listed["dnsbl_listed"] is False and listed["dnsbl_lists"] == []
            assert listed["healthy"] is False  # status is still `verified` in the seed, which is not a sendable state
        await client(Session, scenario)
    run(go)


def test_one_run_per_domain_per_day_and_retired_domains_are_skipped():
    async def go(Session):
        dom, _, lookup = await world(Session, HEALTHY)
        retired, _ = await seed(Session, dom_kw={"send_status": "retired"})
        assert await job(Session, lookup) == 1
        asked = len(lookup.asked)
        assert await job(Session, lookup) == 0 and len(lookup.asked) == asked   # nothing due, nothing queried
        async with Session() as s:
            ids = [r.domain_id for r in (await s.execute(select(DomainHealthDaily))).scalars()]
        return ids == [dom] and retired not in ids
    assert run(go)


def test_a_resolver_failure_on_one_domain_does_not_stop_the_others(monkeypatch):
    async def go(Session):
        a, _, lookup = await world(Session, HEALTHY)
        b, _ = await seed(Session, dom_kw={"domain_name": "other.test"})
        real = dh.mx.spf_ok

        async def flaky(domain, *a_, **k):
            if domain == "other.test":
                raise RuntimeError("boom")
            return await real(domain, *a_, **k)
        monkeypatch.setattr(dh.mx, "spf_ok", flaky)
        done = await job(Session, lookup)
        async with Session() as s:
            return done, {r.domain_id for r in (await s.execute(select(DomainHealthDaily))).scalars()} == {a}
    assert run(go) == (1, True)


def test_hard_bounce_and_complaint_rates_come_from_todays_dispatch_bounce_and_event_rows(client):
    async def go(Session):
        async def scenario(c):
            dom, (mb, _), lookup = await world(Session, HEALTHY)
            mids = [await add_dispatch(Session, dom, mb) for _ in range(10)]
            await add_dispatch(Session, dom, mb, status="failed")                     # never sent: not in the denominator
            async with Session() as s:
                n = 0
                for kind in ("hard", "soft"):                                          # soft bounces do not count
                    n += 1
                    s.add(Bounce(email_account_id=mb, dsn_hash=f"{n:064d}", message_id=mids[n], status_code="5.1.1" if kind == "hard" else "4.2.2", kind=kind))
                await emit(s, "complained", mids[2])
                await s.commit()
            await job(Session, lookup)
            d = (await c.get("/api/v1/domains")).json()[0]
            assert (d["hard_bounce_rate"], d["complaint_rate"]) == (0.1, 0.1)
        await client(Session, scenario)
    run(go)


def test_dmarc_counts_of_the_previous_day_land_on_the_row():
    async def go(Session):
        dom, _, lookup = await world(Session, HEALTHY)
        yday = datetime.utcnow().date() - timedelta(days=1)
        async with Session() as s:
            s.add(DmarcReport(org_name="google.com", report_id="r1", domain_id=dom, day=yday, pass_count=3, fail_count=2, fail_ips={"203.0.113.9": 2}))
            s.add(DmarcReport(org_name="google.com", report_id="old", domain_id=dom, day=yday - timedelta(days=5), pass_count=9, fail_count=9, fail_ips={}))
            await s.commit()
        await job(Session, lookup)
        async with Session() as s:
            r = (await s.execute(select(DomainHealthDaily))).scalar_one()
            return (r.dmarc_reports_pass_count, r.dmarc_reports_fail_count, r.dmarc_aligned, r.source)
    assert run(go) == (3, 2, False, "dns+dmarc")


def test_no_dmarc_reports_means_aligned_is_unknown_not_false():
    async def go(Session):
        _, _, lookup = await world(Session, HEALTHY)
        await job(Session, lookup)
        async with Session() as s:
            r = (await s.execute(select(DomainHealthDaily))).scalar_one()
            return (r.dmarc_aligned, r.dmarc_reports_fail_count, r.source)
    assert run(go) == (None, None, "dns")


def test_a_second_check_the_same_day_updates_the_row_instead_of_adding_one():
    async def go(Session):
        dom, _, lookup = await world(Session, LISTED)
        zones = []
        async with Session() as s:
            zones = list((await s.execute(select(DnsblZone))).scalars())
        for answers in (LISTED, HEALTHY):
            lookup = Script(answers)
            async with Session() as s:
                await dh.check_domain(s, await s.get(Domain, dom), lookup, zones, None, datetime.utcnow().date())
                await s.commit()
        async with Session() as s:
            rows = (await s.execute(select(DomainHealthDaily))).scalars().all()
            return len(rows), rows[0].dnsbl_listed
    assert run(go) == (1, [])


def test_dkim_selectors_come_from_the_domain_record_and_the_config(monkeypatch):
    from app.config import get_settings
    async def go(Session):
        _, _, _ = await world(Session, HEALTHY, box_kw={"platform": "self-hosted"}, dom_kw={"dkim_selector": "own"})
        answers = {(NAME, "TXT"): ["v=spf1 -all"], (f"extra._domainkey.{NAME}", "TXT"): ["v=DKIM1; p=KEY"]}
        await job(Session, Script(answers))
        async with Session() as s:
            return (await s.execute(select(DomainHealthDaily.dkim_ok))).scalar_one()
    monkeypatch.setattr(get_settings(), "dkim_selectors", "other, extra")
    assert run(go) is True


class FakePostmaster:
    def __init__(self, result=None, boom=False):
        self.result, self.boom, self.asked = result, boom, []

    async def stats(self, domain):
        self.asked.append(domain)
        if self.boom:
            raise RuntimeError("postmaster down")
        return self.result


def test_postmaster_fields_fill_when_configured_and_stay_null_when_not_or_failing(client):
    async def go(Session):
        async def scenario(c):
            dom, _, lookup = await world(Session, HEALTHY)
            await job(Session, lookup, postmaster=FakePostmaster({"spam_rate": 0.002, "reputation": "HIGH"}))
            d = (await c.get("/api/v1/domains")).json()[0]
            assert (d["postmaster_spam_rate"], d["postmaster_reputation"]) == (0.002, "HIGH")
            tomorrow = datetime.utcnow().date() + timedelta(days=1)
            for pm in (None, FakePostmaster(boom=True), FakePostmaster(None)):
                await dh.run_daily(Session, lookup=lookup, ingest=noingest, postmaster=pm, today=tomorrow)
                async with Session() as s:
                    row = (await s.execute(select(DomainHealthDaily).where(DomainHealthDaily.day == tomorrow))).scalar_one()
                    assert (row.postmaster_spam_rate, row.postmaster_reputation, row.source) == (None, None, "dns")
                    await s.delete(row)
                    await s.commit()
        await client(Session, scenario)
    run(go)


def test_a_domain_never_checked_reports_null_health(client):
    async def go(Session):
        async def scenario(c):
            await world(Session, HEALTHY)
            d = (await c.get("/api/v1/domains")).json()[0]
            assert d["health_checked_at"] is None and d["dmarc_policy"] is None and d["postmaster_spam_rate"] is None
        await client(Session, scenario)
    run(go)


def test_today_defaults_to_the_utc_date():
    assert dh.utc_today() == datetime.utcnow().date() and isinstance(dh.utc_today(), date)
