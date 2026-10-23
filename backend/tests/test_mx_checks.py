"""DNS fact checks against a scripted resolver: no network, no database."""
from __future__ import annotations

import asyncio

import pytest

from app.models import DnsblZone
from app.services import mx_checks as mx


class Script:
    """A resolver that answers from a dict {(name, rtype): answers}. Missing is NXDOMAIN ([]), None is a resolver failure."""

    def __init__(self, answers):
        self.answers, self.asked = {(k[0].lower(), k[1]): v for k, v in answers.items()}, []

    async def __call__(self, name, rtype):
        self.asked.append((name.lower(), rtype))
        return self.answers.get((name.lower().rstrip("."), rtype), [])


def run(coro):
    return asyncio.run(coro)


GOOGLE_SPF = "v=spf1 include:_spf.google.com ~all"


@pytest.mark.parametrize("txt,platforms,ok", [
    ([GOOGLE_SPF], {"google"}, True),
    (["v=spf1 include:spf.protection.outlook.com -all"], {"microsoft"}, True),
    (["v=spf1 include:spf.protection.outlook.com -all"], {"google"}, False),           # wrong provider
    ([GOOGLE_SPF, "v=spf1 ip4:1.2.3.4 -all"], {"google"}, False),                      # two SPF records is a permerror
    (["google-site-verification=abc"], {"google"}, False),                              # no SPF at all
    ([GOOGLE_SPF], set(), True),                                                        # provider unknown: any SPF counts
    (["v=spf1 include:_spf.google.com include:spf.protection.outlook.com ~all"], {"google", "microsoft"}, True),
])
def test_spf(txt, platforms, ok):
    assert run(mx.spf_ok("a.com", platforms, Script({("a.com", "TXT"): txt}))) is ok


def test_dkim_needs_a_live_key_at_a_selector_for_the_provider():
    live = Script({("google._domainkey.a.com", "TXT"): ["v=DKIM1; k=rsa; p=MIIBIjANBg"]})
    assert run(mx.dkim_ok("a.com", {"google"}, ["champmail"], live)) is True
    assert ("selector1._domainkey.a.com", "TXT") not in live.asked          # only the provider's selectors are asked
    revoked = Script({("google._domainkey.a.com", "TXT"): ["v=DKIM1; k=rsa; p="]})
    assert run(mx.dkim_ok("a.com", {"google"}, [], revoked)) is False
    assert run(mx.dkim_ok("a.com", {"google"}, [], Script({}))) is False
    ms = Script({("selector2._domainkey.a.com", "TXT"): ["v=DKIM1; p=KEY"]})  # M365 publishes CNAMEs; TXT resolves through them
    assert run(mx.dkim_ok("a.com", {"microsoft"}, [], ms)) is True


def test_dmarc_policy_is_the_p_tag_of_the_dmarc_record_only():
    q = Script({("_dmarc.a.com", "TXT"): ["v=DMARC1; p=Quarantine; rua=mailto:r@x.com"]})
    assert run(mx.dmarc_policy("a.com", q)) == "quarantine"
    assert run(mx.dmarc_policy("a.com", Script({("_dmarc.a.com", "TXT"): ["something else"]}))) is None
    assert run(mx.dmarc_policy("a.com", Script({}))) is None
    assert run(mx.dmarc_policy("a.com", Script({("_dmarc.a.com", "TXT"): ["v=DMARC1; rua=mailto:r@x.com"]}))) is None  # no p: invalid


def test_mta_sts_is_a_stsv1_record_with_an_id():
    assert run(mx.mta_sts_ok("a.com", Script({("_mta-sts.a.com", "TXT"): ["v=STSv1; id=20261023"]}))) is True
    assert run(mx.mta_sts_ok("a.com", Script({("_mta-sts.a.com", "TXT"): ["v=STSv1"]}))) is False
    assert run(mx.mta_sts_ok("a.com", Script({}))) is False


ZEN = DnsblZone(name="spamhaus_zen", zone="zen.spamhaus.org", kind="ip", enabled=True)
SURBL = DnsblZone(name="surbl", zone="multi.surbl.org", kind="domain", enabled=True)
BARRACUDA = DnsblZone(name="barracuda", zone="b.barracudacentral.org", kind="ip", enabled=True)


def test_dnsbl_lists_hit_by_fixture_answer_are_named():
    s = Script({("4.3.2.1.zen.spamhaus.org", "A"): ["127.0.0.2"], ("a.com.multi.surbl.org", "A"): ["127.0.0.64"]})
    hits, errors = run(mx.dnsbl_check("a.com", ["1.2.3.4"], [ZEN, SURBL, BARRACUDA], s))
    assert (hits, errors) == (["spamhaus_zen", "surbl"], [])


def test_spamhaus_error_codes_are_not_listings_and_resolver_failures_are_errors_not_hits():
    s = Script({("4.3.2.1.zen.spamhaus.org", "A"): ["127.255.255.254"], ("4.3.2.1.b.barracudacentral.org", "A"): None})
    hits, errors = run(mx.dnsbl_check("a.com", ["1.2.3.4"], [ZEN, BARRACUDA], s))
    assert hits == [] and errors == ["spamhaus_zen", "barracuda"]


def test_disabled_zones_and_ip_zones_without_ips_are_not_queried():
    off = DnsblZone(name="off", zone="off.example", kind="domain", enabled=False)
    s = Script({})
    assert run(mx.dnsbl_check("a.com", [], [ZEN, off], s)) == ([], [])
    assert s.asked == []
    assert run(mx.dnsbl_check("a.com", ["2001:db8::1"], [ZEN], s)) == ([], [])  # IPv4 zones only


@pytest.mark.parametrize("raw,norm", [("google", "google"), ("GOOGLE_WORKSPACE", "google"), ("microsoft", "microsoft"),
                                      ("azure", "microsoft"), ("smtp", None), (None, None)])
def test_platform_normalisation(raw, norm):
    assert mx.platform(raw) == norm
