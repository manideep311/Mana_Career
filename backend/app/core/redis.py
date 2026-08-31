from __future__ import annotations

from functools import lru_cache

import redis.asyncio as redis

from app.core.config import Settings


@lru_cache
def get_redis_pool(url: str) -> redis.Redis:
    # redis-py's async from_url lacks type coverage under strict mypy.
    pool: redis.Redis = redis.from_url(  # type: ignore[no-untyped-call]
        url, encoding="utf-8", decode_responses=True
    )
    return pool


def redis_from_settings(settings: Settings) -> redis.Redis:
    return get_redis_pool(settings.redis_url)


async def ping_redis(r: redis.Redis) -> bool:
    try:
        return bool(await r.ping())
    except Exception:
        return False
