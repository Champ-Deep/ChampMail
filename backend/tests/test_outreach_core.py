"""Offline unit tests for the new outreach cores (no DB / IMAP / app stack).

The DSN parser, ramp-governor, and reply-ingest cores are stdlib-only, so we load
them directly by path and test the pure logic.
"""
import importlib.util
import sys
from pathlib import Path

_SERVICES = Path(__file__).resolve().parent.parent / "app" / "services"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _SERVICES / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    # Register before exec so dataclasses can resolve cls.__module__ (py3.14).
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


dsn = _load("dsn_parser")
ramp = _load("ramp_governor")
reply = _load("reply_ingest")
identity = _load("identity_service")
events = _load("events")


# --- DSN parser ----------------------------------------------------------------

HARD_DSN = (
    "From: MAILER-DAEMON@mx.example.com\r\n"
    "To: bounce@championsmail.com\r\n"
    "Subject: Undelivered Mail Returned to Sender\r\n"
    "Content-Type: multipart/report; report-type=delivery-status; boundary=\"B\"\r\n"
    "\r\n"
    "--B\r\n"
    "Content-Type: text/plain\r\n\r\n"
    "Delivery failed.\r\n"
    "--B\r\n"
    "Content-Type: message/delivery-status\r\n\r\n"
    "Reporting-MTA: dns; mx.example.com\r\n"
    "\r\n"
    "Final-Recipient: rfc822; nobody@example.com\r\n"
    "Action: failed\r\n"
    "Status: 5.1.1\r\n"
    "Diagnostic-Code: smtp; 550 5.1.1 user unknown\r\n"
    "--B--\r\n"
)

SOFT_DSN = HARD_DSN.replace("5.1.1", "4.2.2").replace("550 5.1.1 user unknown", "452 4.2.2 mailbox full")


def test_dsn_hard_bounce():
    recs = dsn.parse_dsn(HARD_DSN)
    assert len(recs) == 1
    r = recs[0]
    assert r.recipient == "nobody@example.com"
    assert r.status == "5.1.1"
    assert r.classification == "hard" and r.is_hard


def test_dsn_soft_bounce():
    recs = dsn.parse_dsn(SOFT_DSN)
    assert recs[0].classification == "soft"
    assert not recs[0].is_hard


def test_dsn_fallback_nonstandard():
    raw = ("From: postmaster@x\r\nSubject: failure\r\n\r\n"
           "550 5.7.1 message rejected for user blocked@corp.com\r\n")
    recs = dsn.parse_dsn(raw)
    assert recs and recs[0].recipient == "blocked@corp.com" and recs[0].is_hard


# --- ramp-governor -------------------------------------------------------------

def _m(**kw):
    base = dict(bounce_rate=0.0, complaint_rate=0.0, seed_placement=1.0,
                warmup_day=2, sent_today=0, sample_size=100)
    base.update(kw)
    return ramp.DomainMetrics(**base)


def test_ramp_pause_on_complaints():
    d = ramp.evaluate_domain(_m(complaint_rate=0.004))
    assert d.action == ramp.RampAction.PAUSE and d.new_cap == 0


def test_ramp_pause_on_hard_bounce():
    d = ramp.evaluate_domain(_m(bounce_rate=0.05))
    assert d.action == ramp.RampAction.PAUSE


def test_ramp_throttle_caution_band():
    d = ramp.evaluate_domain(_m(bounce_rate=0.025))  # 2.5% — caution
    assert d.action == ramp.RampAction.THROTTLE
    assert d.new_cap == ramp.WARMUP_CAPS[1]  # stepped down from step 2 -> 1


def test_ramp_advance_when_healthy():
    d = ramp.evaluate_domain(_m(warmup_day=1, seed_placement=0.9, sample_size=100))
    assert d.action == ramp.RampAction.ADVANCE
    assert d.new_cap == ramp.WARMUP_CAPS[2]


def test_ramp_hold_low_seed():
    d = ramp.evaluate_domain(_m(seed_placement=0.7))
    assert d.action == ramp.RampAction.HOLD


# --- reply ingest --------------------------------------------------------------

def test_classify_bounce():
    k = reply.classify_inbound(return_path="<>", auto_submitted="", subject="x")
    assert k == reply.InboundKind.BOUNCE


def test_classify_auto_reply_header_and_subject():
    assert reply.classify_inbound(return_path="<a@b>", auto_submitted="auto-replied",
                                  subject="hi") == reply.InboundKind.AUTO_REPLY
    assert reply.classify_inbound(return_path="<a@b>", auto_submitted="",
                                  subject="Out of Office: back Monday") == reply.InboundKind.AUTO_REPLY


def test_classify_genuine_reply():
    assert reply.classify_inbound(return_path="<p@co.com>", auto_submitted="no",
                                  subject="Re: a quick idea") == reply.InboundKind.REPLY


def test_match_thread_in_reply_to_and_references():
    known = {"<m1@d.com>", "<m2@d.com>"}
    assert reply.match_thread("<m2@d.com>", "", known) == "m2@d.com"
    assert reply.match_thread("", "<x@d.com> <m1@d.com>", known) == "m1@d.com"
    assert reply.match_thread("<nope@d.com>", "", known) is None


def test_is_optout():
    assert reply.is_optout("please unsubscribe me")
    assert reply.is_optout("take me off your list")
    assert not reply.is_optout("sure, let's chat next week")


# --- identity spine ------------------------------------------------------------

def test_person_id_stable_by_linkedin():
    a = identity.derive_person_id({"linkedin_urn": "https://linkedin.com/in/priya-sharma"}, "old@a.com")
    b = identity.derive_person_id({"linkedin_urn": "linkedin.com/in/Priya-Sharma/"}, "new@b.com")
    assert a == b  # same person across a job-change (email changed) → same id


def test_person_id_falls_back_to_email():
    a = identity.derive_person_id({}, "Deep@Championsmail.com")
    b = identity.derive_person_id({}, "deep@championsmail.com")
    assert a == b  # case-insensitive email
    c = identity.derive_person_id({}, "other@x.com")
    assert a != c


def test_account_id_by_domain():
    a = identity.derive_account_id("", "p@stripe.com")
    b = identity.derive_account_id("stripe.com", "")
    assert a == b and a != ""


def test_resolve_identity_builds_external_ids():
    out = identity.resolve_identity(
        email="priya@stripe.com", linkedin_url="linkedin.com/in/priya",
        lake_id="lk_123", company_domain="stripe.com",
    )
    assert out["person_id"] and out["account_id"]
    ext = out["external_ids"]
    assert ext["lake_id"] == "lk_123"
    assert ext["linkedin_urn"] == "in/priya"
    assert ext["domain"] == "stripe.com"
    assert len(ext["email_sha256"]) == 64
    # linkedin is the strongest key → person_id keyed on it
    assert out["person_id"] == identity.derive_person_id({"linkedin_urn": "in/priya"}, "")


# --- event envelope ------------------------------------------------------------

def test_event_envelope_shape():
    e = events.build_event(
        events.EmailEventType.SENT,
        person_id="p1", account_id="a1", campaign_id="c1",
        send_log_id="m1", email="x@y.com", payload={"k": "v"},
    )
    assert e["schema"] == "champ.email.v1"
    assert e["type"] == "email.sent"
    assert e["person_id"] == "p1" and e["send_log_id"] == "m1"
    assert e["payload"] == {"k": "v"}
    assert e["id"] and e["ts"]


def test_event_types_cover_lifecycle():
    types = {t.value for t in events.EmailEventType}
    assert {"email.sent", "email.opened", "email.clicked", "email.bounced",
            "email.replied", "email.unsubscribed", "email.complained"} <= types


def test_reply_service_pauses_and_suppresses():
    paused, suppressed = [], []

    class FakeBox:
        def fetch_unseen(self):
            return [
                reply.InboundMessage(return_path="<p@co.com>", auto_submitted="no",
                                     precedence="", subject="Re: idea",
                                     in_reply_to="<m1@d.com>", references="",
                                     from_addr="p@co.com", body="Sounds good, tell me more"),
                reply.InboundMessage(return_path="<q@co.com>", auto_submitted="no",
                                     precedence="", subject="Re: idea",
                                     in_reply_to="<m2@d.com>", references="",
                                     from_addr="q@co.com", body="unsubscribe me please"),
                reply.InboundMessage(return_path="<>", auto_submitted="",
                                     precedence="", subject="failure",
                                     in_reply_to="", references="",
                                     from_addr="mailer", body=""),
            ]

    svc = reply.ReplyIngestService(
        FakeBox(),
        resolve_message_ids=lambda: {"<m1@d.com>", "<m2@d.com>"},
        on_reply=lambda mid, frm: paused.append((mid, frm)),
        on_optout=lambda frm: suppressed.append(frm),
    )
    outcomes = svc.run_once()
    assert paused == [("m1@d.com", "p@co.com")]      # genuine reply paused
    assert suppressed == ["q@co.com"]                 # opt-out suppressed
    kinds = [o.kind for o in outcomes]
    assert reply.InboundKind.BOUNCE in kinds          # bounce not treated as reply
