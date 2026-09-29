from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.client_ip import client_ip
from app.core.config import get_settings
from app.core.errors import PROBLEM_MEDIA_TYPE, RateLimitedError, to_problem
from app.core.logging import get_logger
from app.core.redis import redis_from_settings

log = get_logger("rate_limit")
_Handler = Callable[[Request], Awaitable[Response]]
AUTH_LIMIT_PER_MINUTE = 10

# INCR and the expiry run as one atomic script. The expiry is (re)applied
# whenever the key has none, so a counter can never be left without a TTL —
# which would lock its client out permanently.
_FIXED_WINDOW = """
local count = redis.call('INCR', KEYS[1])
local ttl = redis.call('TTL', KEYS[1])
if ttl < 0 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
  ttl = tonumber(ARGV[1])
end
return {count, ttl}
"""


@dataclass(frozen=True)
class RateLimitState:
    limit: int
    remaining: int
    reset: int
    allowed: bool


async def check_rate_limit(
    r: Any, *, key: str, limit: int, window_seconds: int = 60
) -> RateLimitState:
    """Atomic fixed-window counter. ``r`` is a Redis client (or any object
    exposing ``async eval`` — the test suite passes a fake)."""
    count, reset = await r.eval(_FIXED_WINDOW, 1, key, window_seconds)
    count, reset = int(count), int(reset)
    return RateLimitState(
        limit=limit, remaining=max(0, limit - count), reset=reset, allowed=count <= limit
    )


# POSTs that start model work (a new agent run, a roadmap, a tailored résumé,
# an application prepared by Mana AI). Everything else — including GETs and
# live event streams under /ai — is an ordinary read.
_LLM_POST_SUFFIXES = ("/reprocess", "/confirm-profile", "/tailor", "/messages", "/goal")


def _bucket(path: str, method: str) -> str:
    base = get_settings().api_base_path
    if path.startswith(f"{base}/auth"):
        return "auth"
    if method != "POST":
        return "read"
    if path in (f"{base}/resumes", f"{base}/jobs"):
        return "upload"
    if path in (
        f"{base}/matches",
        f"{base}/matches/recompute",
        f"{base}/roadmaps",
        f"{base}/applications",
    ):
        return "llm"
    if path.startswith(f"{base}/ai/") and path.endswith(_LLM_POST_SUFFIXES):
        return "llm"
    if path.startswith(f"{base}/resumes/") and path.endswith(_LLM_POST_SUFFIXES):
        return "llm"
    return "read"


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: _Handler) -> Response:
        path = request.url.path
        if path.startswith("/health") or path == "/api/openapi.json":
            return await call_next(request)

        settings = get_settings()
        bucket = _bucket(path, request.method)

        if bucket == "auth":
            limit = AUTH_LIMIT_PER_MINUTE
            window = 60
        elif bucket == "upload":
            limit = settings.upload_limit_per_hour
            window = 3600
        elif bucket == "llm":
            limit = settings.llm_limit_per_hour
            window = 3600
        else:
            limit = settings.rate_limit_default_per_minute
            window = 60

        try:
            state = await check_rate_limit(
                redis_from_settings(settings),
                key=f"rl:{client_ip(request, settings)}:{bucket}",
                limit=limit,
                window_seconds=window,
            )
        except (RedisError, OSError):
            # Fail open: a Redis outage must not take the API down.
            log.warning("rate_limit_unavailable", path=path)
            return await call_next(request)

        if not state.allowed:
            # BaseHTTPMiddleware runs outside FastAPI's exception handlers, so
            # emit the problem+json response directly instead of raising.
            exc = RateLimitedError(retry_after=state.reset)
            return JSONResponse(
                status_code=exc.status,
                content=to_problem(exc, instance=str(request.url)),
                media_type=PROBLEM_MEDIA_TYPE,
                headers={"Retry-After": str(state.reset)},
            )

        response = await call_next(request)
        response.headers["RateLimit-Limit"] = str(state.limit)
        response.headers["RateLimit-Remaining"] = str(state.remaining)
        response.headers["RateLimit-Reset"] = str(state.reset)
        return response
