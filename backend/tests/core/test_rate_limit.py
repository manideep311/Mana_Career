import os
import uuid

import pytest
from starlette.requests import Request

from app.core.client_ip import client_ip
from app.core.config import get_settings
from app.core.rate_limit import _bucket, check_rate_limit


class _R:
    """Models the limiter's Lua script: INCR, then set a TTL if the key has none."""

    def __init__(self, default_ttl: int = 42) -> None:
        self.n: dict[str, int] = {}
        self.ttls: dict[str, int] = {}
        self.default_ttl = default_ttl

    async def eval(self, script: str, numkeys: int, key: str, window: int) -> list[int]:
        self.n[key] = self.n.get(key, 0) + 1
        if self.ttls.get(key, -1) < 0:
            self.ttls[key] = window
        return [self.n[key], self.ttls[key]]


async def test_allows_up_to_limit_then_blocks():
    r = _R()
    states = [await check_rate_limit(r, key="k", limit=3, window_seconds=42) for _ in range(4)]
    assert [s.allowed for s in states] == [True, True, True, False]
    assert states[2].remaining == 0
    assert states[3].reset == 42


async def test_a_key_that_lost_its_expiry_gets_one_again():
    r = _R()
    r.n["k"], r.ttls["k"] = 999, -1  # e.g. written by an older, non-atomic limiter
    state = await check_rate_limit(r, key="k", limit=5, window_seconds=60)
    assert not state.allowed
    assert r.ttls["k"] == 60  # the lock-out ends when the window does


# --------------------------------------------------------------------------- #
# Real Redis: the Lua script itself (CI-required; skips locally without Redis)
# --------------------------------------------------------------------------- #
@pytest.fixture
async def real_redis():
    import redis.asyncio as redis

    client = redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/1"),
                            decode_responses=True, socket_connect_timeout=2)
    try:
        await client.ping()
    except Exception as exc:  # any connection failure means "no Redis"
        await client.aclose()
        if os.environ.get("CI"):
            raise
        pytest.skip(f"Redis unavailable locally ({exc!r}); runs in CI")
    yield client
    await client.aclose()


async def test_real_redis_counter_always_has_an_expiry(real_redis):
    key = f"test:rl:{uuid.uuid4().hex}"
    try:
        first = await check_rate_limit(real_redis, key=key, limit=2, window_seconds=30)
        assert first.allowed and 0 < await real_redis.ttl(key) <= 30
        await real_redis.persist(key)  # simulate a key stranded without a TTL
        assert await real_redis.ttl(key) == -1
        again = await check_rate_limit(real_redis, key=key, limit=2, window_seconds=30)
        assert again.allowed and 0 < await real_redis.ttl(key) <= 30
        blocked = await check_rate_limit(real_redis, key=key, limit=2, window_seconds=30)
        assert not blocked.allowed
    finally:
        await real_redis.delete(key)


# --------------------------------------------------------------------------- #
# Buckets: only requests that start model work spend the LLM budget
# --------------------------------------------------------------------------- #
def test_bucket_classifies_uploads():
    assert _bucket("/api/v1/resumes", "POST") == "upload"
    assert _bucket("/api/v1/jobs", "POST") == "upload"
    assert _bucket("/api/v1/resumes", "GET") == "read"
    assert _bucket("/api/v1/auth/login", "POST") == "auth"
    assert _bucket("/api/v1/auth/refresh", "POST") == "auth"


def test_bucket_classifies_llm_tier():
    uid = "11111111-1111-1111-1111-111111111111"
    for path in (
        f"/api/v1/resumes/{uid}/reprocess",
        f"/api/v1/resumes/{uid}/confirm-profile",
        f"/api/v1/resumes/{uid}/tailor",
        "/api/v1/matches",
        "/api/v1/matches/recompute",
        "/api/v1/roadmaps",
        "/api/v1/applications",
        f"/api/v1/ai/sessions/{uid}/messages",
        f"/api/v1/ai/sessions/{uid}/goal",
    ):
        assert _bucket(path, "POST") == "llm", path


def test_reading_ai_state_does_not_spend_the_llm_budget():
    uid = "11111111-1111-1111-1111-111111111111"
    for path in (
        "/api/v1/ai/sessions",
        f"/api/v1/ai/sessions/{uid}",
        f"/api/v1/ai/sessions/{uid}/events",
        "/api/v1/ai/actions",
    ):
        assert _bucket(path, "GET") == "read", path
    # Creating or stopping a session starts no model work either.
    assert _bucket("/api/v1/ai/sessions", "POST") == "read"
    assert _bucket(f"/api/v1/ai/sessions/{uid}/stop", "POST") == "read"
    assert _bucket(f"/api/v1/resumes/{uid}/reprocess", "GET") == "read"


# --------------------------------------------------------------------------- #
# Client address: CF-Connecting-IP only from a trusted tunnel peer
# --------------------------------------------------------------------------- #
def _request(peer: str, cf: str | None = None) -> Request:
    headers = [(b"cf-connecting-ip", cf.encode())] if cf is not None else []
    return Request({"type": "http", "headers": headers, "client": (peer, 1234)})


def _settings(cidrs: list[str]):
    return get_settings().model_copy(update={"trusted_proxy_cidrs": cidrs})


def test_cf_header_ignored_without_trusted_proxies():
    assert client_ip(_request("203.0.113.9", "1.2.3.4"), _settings([])) == "203.0.113.9"


def test_cf_header_ignored_from_an_untrusted_peer():
    s = _settings(["172.30.0.0/24"])
    assert client_ip(_request("203.0.113.9", "1.2.3.4"), s) == "203.0.113.9"


def test_cf_header_used_from_the_tunnel_peer():
    s = _settings(["172.30.0.0/24"])
    assert client_ip(_request("172.30.0.1", "198.51.100.7"), s) == "198.51.100.7"


def test_malformed_cf_header_falls_back_to_the_peer():
    s = _settings(["172.30.0.0/24"])
    assert client_ip(_request("172.30.0.1", "not-an-ip"), s) == "172.30.0.1"
