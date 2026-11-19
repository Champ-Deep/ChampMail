"""domain_probe and GET /domain-health/check against a scripted resolver. Scripted answers are test fixtures, not live results."""
from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.api.v1.domain_health import get_lookup
from app.config import get_settings
from app.main import app
from app.services import domain_probe as dp

GOOD = {
    ("a.com", "TXT"): ["v=spf1 include:_spf.google.com -all"],
    ("google._domainkey.a.com", "TXT"): ["v=DKIM1; k=rsa; p=MIIB"],
    ("_dmarc.a.com", "TXT"): ["v=DMARC1; p=reject; rua=mailto:r@a.com"],
    ("a.com", "MX"): ["1 smtp.google.com."],
    ("_mta-sts.a.com", "TXT"): ["v=STSv1; id=1"],
    ("test.surbl.org.multi.surbl.org", "A"): ["127.0.0.254"],  # each list's always-listed test point answers
    ("dbltest.com.dbl.spamhaus.org", "A"): ["127.0.1.2"],
}


def scripted(answers, fail=()):
    """Missing key is NXDOMAIN ([]); names in `fail` raise the resolver-failure answer (None)."""
    asked = []

    async def look(name, rtype):
        asked.append((name, rtype))
        if name in fail or "*" in fail:
            return None
        return answers.get((name.lower(), rtype), [])
    look.asked = asked
    return look


def run(look, domain="a.com", sel=()):
    return asyncio.run(dp.probe(domain, look, sel))


def st(r):
    return {k: v["status"] for k, v in r["checks"].items()}


def test_all_pass_has_source_time_and_no_score():
    r = run(scripted(GOOD))
    assert st(r) == {"spf": "pass", "dkim": "pass", "dmarc": "pass", "mx": "info", "mta_sts": "info", "dnsbl": "pass"}
    assert r["attention"] == [] and r["it_recommendation"] is None
    assert r["checked_at"].endswith("+00:00") and "public DNS" in r["source"] and "inbox-placement" in r["note"]
    assert not any("score" in k for k in r)


@pytest.mark.parametrize("bad", ["", "  ", "not a domain", "a..com", "1.2.3.4", "localhost", "http://a.com", "a.com/x", "x" * 300 + ".com"])
def test_invalid_domain_rejected_before_any_lookup(bad):
    look = scripted(GOOD)
    with pytest.raises(ValueError):
        run(look, bad)
    assert look.asked == []


@pytest.mark.parametrize("bad", ["", "a b", "../x", "x" * 70])
def test_invalid_selector_rejected(bad):
    with pytest.raises(ValueError):
        run(scripted(GOOD), sel=[bad])


def test_domain_is_normalized():
    assert run(scripted(GOOD), "  A.COM. ")["domain"] == "a.com"


def test_absent_selector_is_unknown_never_pass_or_fail():
    answers = {k: v for k, v in GOOD.items() if k[0] != "google._domainkey.a.com"}
    for sel in ((), ("custom1",)):
        d = run(scripted(answers), sel=sel)["checks"]["dkim"]
        assert d["status"] == "unknown"
    assert "no selector supplied" in run(scripted(answers))["checks"]["dkim"]["detail"]
    assert "dkim" in run(scripted(answers))["attention"]


def test_supplied_selector_found_and_revoked():
    ans = {("custom1._domainkey.a.com", "TXT"): ["v=DKIM1; p=MIIB"]}
    r = run(scripted(ans), sel=["custom1"])["checks"]["dkim"]
    assert r["status"] == "pass" and r["selectors_found"] == ["custom1"]
    assert run(scripted({("custom1._domainkey.a.com", "TXT"): ["v=DKIM1; p="]}), sel=["custom1"])["checks"]["dkim"]["status"] == "fail"


def test_resolver_failure_everywhere_is_unknown_not_pass_and_no_recommendation():
    r = run(scripted(GOOD, fail={"*"}))
    assert set(st(r).values()) == {"unknown"}
    assert r["it_recommendation"] is None and len(r["attention"]) == 6


def test_resolver_failure_on_one_check_leaves_the_others_intact():
    r = run(scripted(GOOD, fail={"_dmarc.a.com"}))
    assert st(r)["dmarc"] == "unknown" and st(r)["spf"] == "pass"


def test_missing_records_fail_and_recommend_it_review_only():
    r = run(scripted({}))
    assert st(r)["spf"] == "fail" and st(r)["dmarc"] == "fail" and st(r)["dkim"] == "unknown"
    assert r["it_recommendation"].startswith("IT review recommended for: spf, dmarc")
    assert "nothing is paused, rotated or changed" in r["it_recommendation"]


def test_spf_two_records_and_lookup_limit_fail_and_dmarc_none_warns():
    two = {**GOOD, ("a.com", "TXT"): ["v=spf1 -all", "v=spf1 +all"]}
    assert run(scripted(two))["checks"]["spf"]["status"] == "fail"
    many = {**GOOD, ("a.com", "TXT"): ["v=spf1 " + " ".join(f"include:i{i}.net" for i in range(11)) + " -all"]}
    spf = run(scripted(many))["checks"]["spf"]
    assert spf["status"] == "fail" and spf["lookup_terms_top_level"] == 11
    none = {**GOOD, ("_dmarc.a.com", "TXT"): ["v=DMARC1; p=none"]}
    assert run(scripted(none))["checks"]["dmarc"]["status"] == "warn"


def test_dnsbl_listing_blocked_resolver_and_clean():
    listed = run(scripted({**GOOD, ("a.com.dbl.spamhaus.org", "A"): ["127.0.1.2"]}))["checks"]["dnsbl"]
    assert listed["status"] == "fail" and listed["zones"] == {"surbl": "not_listed", "spamhaus_dbl": "listed"}
    assert listed["answers"] == {"spamhaus_dbl": ["127.0.1.2"]}
    blocked = run(scripted({**GOOD, ("a.com.dbl.spamhaus.org", "A"): ["127.255.255.254"]}))["checks"]["dnsbl"]
    assert blocked["status"] == "unknown" and blocked["zones"]["spamhaus_dbl"] == "unknown"


def dnsbl(answers):
    return run(scripted({**GOOD, **answers}))["checks"]["dnsbl"]


def test_dbl_control_not_listed_means_resolver_refused_so_unknown_not_pass():
    # Google-style: NXDOMAIN for everything on Spamhaus, including dbltest.com. A clean answer for a.com proves nothing.
    d = dnsbl({("dbltest.com.dbl.spamhaus.org", "A"): []})
    assert d["status"] == "unknown" and d["zones"] == {"surbl": "not_listed", "spamhaus_dbl": "unknown"}


def test_surbl_control_failure_is_unknown_even_if_the_domain_looks_clean():
    d = dnsbl({("test.surbl.org.multi.surbl.org", "A"): None})
    assert d["status"] == "unknown" and d["zones"]["surbl"] == "unknown"


def test_surbl_127_0_0_1_is_blocked_not_a_listing():
    d = dnsbl({("a.com.multi.surbl.org", "A"): ["127.0.0.1"]})
    assert d["status"] == "unknown" and d["zones"]["surbl"] == "unknown"
    # the same code on the control also means blocked: never a listing, never a control pass
    d = dnsbl({("test.surbl.org.multi.surbl.org", "A"): ["127.0.0.1"]})
    assert d["zones"]["surbl"] == "unknown"


def test_both_controls_listed_and_domain_clean_is_the_only_pass_path():
    d = dnsbl({})
    assert d["status"] == "pass" and d["zones"] == {"surbl": "not_listed", "spamhaus_dbl": "not_listed"}
    assert d["controls"] == {"surbl": ["127.0.0.254"], "spamhaus_dbl": ["127.0.1.2"]}
    listed = dnsbl({("a.com.multi.surbl.org", "A"): ["127.0.0.64"]})  # SURBL ABUSE bit
    assert listed["status"] == "fail" and listed["answers"] == {"surbl": ["127.0.0.64"]}


def test_source_names_the_nameservers_actually_used():
    look = scripted(GOOD)
    look.nameservers = ["9.9.9.9"]
    s = run(look)["source"]
    assert "nameservers used: 9.9.9.9" in s and "host" in s
    assert "unspecified" in run(scripted(GOOD))["source"]


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(get_settings(), "champmail_api_key", "")
    monkeypatch.setattr(get_settings(), "champmail_env", "development")
    look = scripted(GOOD)
    app.dependency_overrides[get_lookup] = lambda: look
    yield TestClient(app), look
    app.dependency_overrides.clear()


def test_api_contract(api):
    c, _ = api
    r = c.get("/api/v1/domain-health/check", params={"domain": "a.com", "dkim_selector": "google"})
    assert r.status_code == 200
    j = r.json()
    assert set(j) == {"domain", "checked_at", "source", "note", "checks", "attention", "it_recommendation"}
    assert j["checks"]["dkim"]["selectors_found"] == ["google"]


def test_api_422_on_invalid_input_and_no_lookup(api):
    c, look = api
    assert c.get("/api/v1/domain-health/check", params={"domain": "not a domain"}).status_code == 422
    assert c.get("/api/v1/domain-health/check", params={"domain": "a.com", "dkim_selector": "../x"}).status_code == 422
    assert c.get("/api/v1/domain-health/check").status_code == 422
    assert c.get("/api/v1/domain-health/check", params={"domain": "a.com", "dkim_selector": list("abcdef")}).status_code == 422
    assert look.asked == []


def test_api_resolver_failure_is_200_unknown(api, monkeypatch):
    c, _ = api
    app.dependency_overrides[get_lookup] = lambda: scripted(GOOD, fail={"*"})
    r = c.get("/api/v1/domain-health/check", params={"domain": "a.com"})
    assert r.status_code == 200 and {v["status"] for v in r.json()["checks"].values()} == {"unknown"}


def test_api_key_enforced_when_configured(api, monkeypatch):
    c, _ = api
    monkeypatch.setattr(get_settings(), "champmail_api_key", "k")
    assert c.get("/api/v1/domain-health/check", params={"domain": "a.com"}).status_code == 401
    assert c.get("/api/v1/domain-health/check", params={"domain": "a.com"}, headers={"X-API-Key": "k"}).status_code == 200
