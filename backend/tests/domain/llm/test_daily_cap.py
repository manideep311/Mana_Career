"""The global daily cap on model calls (DailyCappedLLM)."""

from __future__ import annotations

import datetime as dt

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.errors import AIPausedError
from app.domain.llm.adapters.fake import FakeLLMProvider
from app.domain.llm.daily_cap import DailyCappedLLM, ai_paused, calls_today, day_key

DAY = dt.date(2026, 10, 27)


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, int] = {}
        self.ttls: dict[str, int] = {}
        self.down = False

    async def eval(self, script: str, nkeys: int, key: str, ttl: int) -> int:
        if self.down:
            raise RedisConnectionError("down")
        self.store[key] = self.store.get(key, 0) + 1
        self.ttls.setdefault(key, ttl)
        return self.store[key]

    async def get(self, key: str) -> str | None:
        if self.down:
            raise RedisConnectionError("down")
        value = self.store.get(key)
        return None if value is None else str(value)


def _capped(redis: FakeRedis, limit: int, day: dt.date = DAY) -> DailyCappedLLM:
    return DailyCappedLLM(FakeLLMProvider(), redis=redis, limit=limit, today=lambda: day)


async def test_calls_pass_until_the_cap_then_pause():
    redis = FakeRedis()
    llm = _capped(redis, limit=2)
    for _ in range(2):
        await llm.complete([{"role": "user", "content": "hi"}])
    with pytest.raises(AIPausedError):
        await llm.complete([{"role": "user", "content": "hi"}])
    assert redis.store[day_key(DAY)] == 3
    # The counter expires on its own, after the day is over.
    assert redis.ttls[day_key(DAY)] >= 24 * 3600
    assert await ai_paused(redis, 2, today=lambda: DAY)


async def test_the_cap_is_per_utc_day():
    redis = FakeRedis()
    await _capped(redis, limit=1).complete([{"role": "user", "content": "hi"}])
    tomorrow = DAY + dt.timedelta(days=1)
    await _capped(redis, limit=1, day=tomorrow).complete([{"role": "user", "content": "hi"}])
    assert await calls_today(redis, today=lambda: tomorrow) == 1
    assert not await ai_paused(redis, 2, today=lambda: tomorrow)


async def test_a_redis_outage_never_blocks_the_ai():
    redis = FakeRedis()
    redis.down = True
    out = await _capped(redis, limit=1).complete([{"role": "user", "content": "hi"}])
    assert out.model == "fake-llm-1"
    assert await calls_today(redis, today=lambda: DAY) == 0


async def test_no_cap_means_never_paused():
    redis = FakeRedis()
    redis.store[day_key(DAY)] = 10_000
    assert not await ai_paused(redis, 0, today=lambda: DAY)


def test_capabilities_pass_through():
    assert _capped(FakeRedis(), 1).capabilities() == FakeLLMProvider().capabilities()
