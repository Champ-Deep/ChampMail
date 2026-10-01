"""
Tests for the deliverability package ported from the `simplified` branch.

Two boundaries matter operationally and are what these cover:

1. The gate must never allow a suppressed or spam-trapped address through.
2. A Redis outage must never block a legitimate send. The authoritative
   suppression record is PostgreSQL (services/suppression_service.py), checked
   separately in the send path; this gate is the Redis fast path on top of it.

Redis is stubbed at `redis_client._get_client()`, which is the single access
point every module here uses, so nothing in this file opens a socket.
"""

import pytest

from app.services.deliverability import send_gate as send_gate_mod
from app.services.deliverability.send_gate import SUPPRESSION_KEY, SendGate


class FakeRedis:
    """In-memory stand-in for the async Redis surface these modules use."""

    def __init__(self):
        self.sets = {}
        self.strings = {}
        self.hashes = {}

    async def sismember(self, key, member):
        return 1 if member in self.sets.get(key, set()) else 0

    async def sadd(self, key, *members):
        cur = self.sets.setdefault(key, set())
        before = len(cur)
        cur.update(members)
        return len(cur) - before

    async def srem(self, key, *members):
        cur = self.sets.setdefault(key, set())
        before = len(cur)
        cur.difference_update(members)
        return before - len(cur)

    async def smembers(self, key):
        return set(self.sets.get(key, set()))

    async def incr(self, key, amount=1):
        self.strings[key] = self.strings.get(key, 0) + amount
        return self.strings[key]

    async def get(self, key):
        return self.strings.get(key)

    async def expire(self, *a, **k):
        return True

    async def hset(self, key, field=None, value=None, mapping=None):
        h = self.hashes.setdefault(key, {})
        if mapping:
            h.update(mapping)
        if field is not None:
            h[field] = value
        return 1

    async def hget(self, key, field):
        return self.hashes.get(key, {}).get(field)

    async def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    async def delete(self, key):
        self.strings.pop(key, None)
        self.hashes.pop(key, None)
        return 1


class _StubClient:
    """Mimics the app.db.redis wrapper: `_get_client()` is an awaitable."""

    def __init__(self, inner):
        self._inner = inner

    async def _get_client(self):
        return self._inner


@pytest.fixture
def fake_redis(monkeypatch):
    fr = FakeRedis()
    monkeypatch.setattr(
        send_gate_mod, "redis_client", _StubClient(fr), raising=False
    )
    return fr


@pytest.fixture
def permissive_gate(monkeypatch):
    """A SendGate with only the Redis-backed suppression check live."""
    gate = SendGate()

    async def no_spam_trap(email):
        return False

    async def not_blacklisted(domain_id):
        return False, ""

    monkeypatch.setattr(gate, "_is_spam_trap", no_spam_trap, raising=False)
    monkeypatch.setattr(gate, "_is_domain_blacklisted", not_blacklisted, raising=False)

    async def always_ok(domain_id):
        return True, ""

    monkeypatch.setattr(send_gate_mod, "rate_limiter", _StubLimiter(always_ok), raising=False)
    return gate


class _StubLimiter:
    def __init__(self, can_send):
        self._can_send = can_send

    async def can_send(self, domain_id):
        return await self._can_send(domain_id)


class TestSuppressionGate:
    @pytest.mark.asyncio
    async def test_clean_address_passes(self, fake_redis, permissive_gate):
        allowed, reason = await permissive_gate.check("d-1", "person@example.com")
        assert allowed is True
        assert reason == ""

    @pytest.mark.asyncio
    async def test_suppressed_address_is_denied(self, fake_redis, permissive_gate):
        await permissive_gate.add_to_suppression("blocked@example.com")
        allowed, reason = await permissive_gate.check("d-1", "blocked@example.com")
        assert allowed is False
        assert "suppression" in reason.lower()

    @pytest.mark.asyncio
    async def test_removal_reinstates_the_address(self, fake_redis, permissive_gate):
        await permissive_gate.add_to_suppression("x@example.com")
        await permissive_gate.remove_from_suppression("x@example.com")
        allowed, _ = await permissive_gate.check("d-1", "x@example.com")
        assert allowed is True

    @pytest.mark.asyncio
    async def test_suppression_is_case_and_space_insensitive(
        self, fake_redis, permissive_gate
    ):
        await permissive_gate.add_to_suppression("Mixed.Case@Example.com")
        allowed, _ = await permissive_gate.check("d-1", "  MIXED.case@EXAMPLE.com ")
        assert allowed is False

    @pytest.mark.asyncio
    async def test_empty_address_is_never_sendable(self, fake_redis, permissive_gate):
        allowed, _ = await permissive_gate.check("d-1", "")
        assert allowed is False

    @pytest.mark.asyncio
    async def test_suppression_writes_to_the_shared_key(self, fake_redis, permissive_gate):
        await permissive_gate.add_to_suppression("k@example.com")
        assert "k@example.com" in fake_redis.sets[SUPPRESSION_KEY]


class TestRateLimitGate:
    @pytest.mark.asyncio
    async def test_rate_limited_domain_is_denied(self, fake_redis, monkeypatch):
        gate = SendGate()

        async def no_spam_trap(email):
            return False

        async def not_blacklisted(domain_id):
            return False, ""

        async def limited(domain_id):
            return False, "daily limit reached"

        monkeypatch.setattr(gate, "_is_spam_trap", no_spam_trap, raising=False)
        monkeypatch.setattr(gate, "_is_domain_blacklisted", not_blacklisted, raising=False)
        monkeypatch.setattr(send_gate_mod, "rate_limiter", _StubLimiter(limited), raising=False)

        allowed, reason = await gate.check("d-1", "person@example.com")
        assert allowed is False
        assert "limit" in reason.lower()

    @pytest.mark.asyncio
    async def test_blacklisted_domain_is_denied(self, fake_redis, monkeypatch):
        gate = SendGate()

        async def no_spam_trap(email):
            return False

        async def listed(domain_id):
            return True, "domain is on a DNSBL"

        async def unlimited(domain_id):
            return True, ""

        monkeypatch.setattr(gate, "_is_spam_trap", no_spam_trap, raising=False)
        monkeypatch.setattr(gate, "_is_domain_blacklisted", listed, raising=False)
        monkeypatch.setattr(send_gate_mod, "rate_limiter", _StubLimiter(unlimited), raising=False)

        allowed, reason = await gate.check("d-1", "person@example.com")
        assert allowed is False
        assert "DNSBL" in reason

    @pytest.mark.asyncio
    async def test_spam_trap_is_denied(self, fake_redis, monkeypatch):
        gate = SendGate()

        async def trapped(email):
            return True

        async def not_blacklisted(domain_id):
            return False, ""

        async def unlimited(domain_id):
            return True, ""

        monkeypatch.setattr(gate, "_is_spam_trap", trapped, raising=False)
        monkeypatch.setattr(gate, "_is_domain_blacklisted", not_blacklisted, raising=False)
        monkeypatch.setattr(send_gate_mod, "rate_limiter", _StubLimiter(unlimited), raising=False)

        allowed, reason = await gate.check("d-1", "trap@spam.example")
        assert allowed is False
        assert "spam trap" in reason.lower()


class TestFailOpen:
    @pytest.mark.asyncio
    async def test_redis_outage_surfaces_for_the_call_site_to_catch(self, monkeypatch):
        """SendGate.check does not swallow transport errors itself.

        The fail-open guarantee belongs to the call site in tasks/sending.py,
        which wraps the gate in try/except so a dead Redis degrades to "no
        fast-path signal" rather than "block". PostgreSQL remains the
        authoritative suppression check and runs before the gate.

        This pins the real contract: an outage surfaces as an exception the
        caller can catch, instead of silently becoming a block decision.
        """
        class DeadRedis:
            async def sismember(self, *a, **k):
                raise ConnectionError("redis down")

        monkeypatch.setattr(
            send_gate_mod, "redis_client", _StubClient(DeadRedis()), raising=False
        )
        gate = SendGate()
        with pytest.raises(ConnectionError):
            await gate.check("d-1", "person@example.com")

    def test_send_path_wraps_the_gate_and_fails_open(self):
        """The send path must call the gate inside a try/except that continues."""
        import inspect

        from app.tasks import sending

        src = inspect.getsource(sending.send_email_task)
        assert "send_gate.check(" in src, "send path no longer consults the send gate"

        gate_import = src.rindex(
            "from app.services.deliverability.send_gate import send_gate", 0,
            src.index("send_gate.check("),
        )
        tail = src[gate_import:]
        except_at = tail.index("except Exception")
        # Nothing between the gate import and its handler may return early.
        assert "return {" not in tail[:except_at].split("if not _allowed")[0], (
            "gate call returns inside the try, which would not fail open"
        )
        assert "failing open" in tail[except_at:]


class TestSpamTrapCheckerNormalisation:
    def test_exact_and_domain_traps_are_loaded(self, tmp_path, monkeypatch):
        from app.services.deliverability import spam_trap_checker as stc_mod

        trap_file = tmp_path / "spam_traps.txt"
        trap_file.write_text("exact@trap.test\n@domain-trap.test\n")
        # TRAP_FILE is a pathlib.Path in the module and is used via .exists().
        monkeypatch.setattr(stc_mod, "TRAP_FILE", trap_file)

        checker = stc_mod.SpamTrapChecker()
        checker._load_file()
        assert "exact@trap.test" in checker._exact_traps
        # The module stores domains without the leading "@".
        assert "domain-trap.test" in checker._domain_traps

    def test_missing_file_is_not_fatal(self, tmp_path, monkeypatch):
        from app.services.deliverability import spam_trap_checker as stc_mod

        monkeypatch.setattr(stc_mod, "TRAP_FILE", tmp_path / "absent.txt")
        checker = stc_mod.SpamTrapChecker()
        checker._load_file()  # must not raise
        assert checker._exact_traps == set()