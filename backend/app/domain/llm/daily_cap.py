"""A ceiling on model calls per UTC day, shared by every user and process.

The per-person limits (``LLM_LIMIT_PER_HOUR``) stop one visitor hogging the
model; this stops all of them together from using up a free provider quota.
Once the day's calls are spent, every model call raises
:class:`~app.core.errors.AIPausedError`: the AI features say they're paused,
while matching, career paths and skill plans (no model) carry on.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel
from redis.exceptions import RedisError

from app.core.errors import AIPausedError
from app.core.logging import get_logger
from app.domain.llm.provider import LLMCapabilities, LLMMessage, LLMProvider, LLMResult

log = get_logger("llm.daily_cap")

# Counters outlive their day by a little so a clock skew can't reset one early.
_KEY_TTL_SECONDS = 2 * 24 * 3600
_INCR_WITH_TTL = """
local count = redis.call('INCR', KEYS[1])
if redis.call('TTL', KEYS[1]) < 0 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""


def _today() -> dt.date:
    return dt.datetime.now(dt.UTC).date()


def day_key(day: dt.date) -> str:
    return f"llm:calls:{day.isoformat()}"


async def calls_today(redis: Any, *, today: Callable[[], dt.date] = _today) -> int:
    """How many model calls have started today (0 when Redis can't say)."""
    try:
        value = await redis.get(day_key(today()))
    except (RedisError, OSError):
        return 0
    return int(value or 0)


async def ai_paused(redis: Any, limit: int, *, today: Callable[[], dt.date] = _today) -> bool:
    return limit > 0 and await calls_today(redis, today=today) >= limit


class DailyCappedLLM:
    """Wraps a real provider; counts each call before making it."""

    def __init__(
        self,
        wrapped: LLMProvider,
        *,
        redis: Any,
        limit: int,
        today: Callable[[], dt.date] = _today,
    ) -> None:
        self.wrapped = wrapped
        self._redis = redis
        self._limit = limit
        self._today = today

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        schema: type[BaseModel] | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> LLMResult:
        try:
            count = int(
                await self._redis.eval(
                    _INCR_WITH_TTL, 1, day_key(self._today()), _KEY_TTL_SECONDS
                )
            )
        except (RedisError, OSError):
            # Fail open, like the rate limiter: a Redis outage must not stop the AI.
            log.warning("llm_daily_cap_unavailable")
            count = 0
        if count > self._limit:
            log.warning("llm_daily_cap_reached", limit=self._limit)
            raise AIPausedError()
        return await self.wrapped.complete(
            messages, schema=schema, max_tokens=max_tokens, temperature=temperature
        )

    def capabilities(self) -> LLMCapabilities:
        return self.wrapped.capabilities()
