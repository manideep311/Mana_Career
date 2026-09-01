from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings
from app.core.errors import PROBLEM_MEDIA_TYPE, RateLimitedError, to_problem
from app.core.logging import get_logger
from app.core.redis import redis_from_settings

log = get_logger("rate_limit")
_Handler = Callable[[Request], Awaitable[Response]]
AUTH_LIMIT_PER_MINUTE = 10


@dataclass(frozen=True)
class RateLimitState:
    limit: int
    remaining: int
    reset: int
    allowed: bool


async def check_rate_limit(
    r: Any, *, key: str, limit: int, window_seconds: int = 60
) -> RateLimitState:
    """Fixed-window counter. `r` is a Redis client (or any object exposing
    async incr/expire/ttl — the test suite passes a fake)."""
    count = int(await r.incr(key))
    if count == 1:
        await r.expire(key, window_seconds)
    reset = await r.ttl(key)
    if reset is None or reset < 0:
        reset = window_seconds
    remaining = max(0, limit - count)
    return RateLimitState(
        limit=limit, remaining=remaining, reset=reset, allowed=count <= limit
    )


def _bucket(path: str, method: str) -> str:
    base = get_settings().api_base_path
    if method == "POST" and path in (f"{base}/resumes", f"{base}/jobs"):
        return "upload"
    if method == "POST" and (
        path.endswith("/reprocess") or path.endswith("/confirm-profile")
    ):
        return "llm"
    if path.startswith(f"{base}/auth"):
        return "auth"
    return "read"


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: _Handler) -> Response:
        path = request.url.path
        if path.startswith("/health") or path == "/api/openapi.json":
            return await call_next(request)

        settings = get_settings()
        client_ip = request.client.host if request.client else "unknown"
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
                key=f"rl:{client_ip}:{bucket}",
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
