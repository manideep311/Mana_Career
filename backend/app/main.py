from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, cast

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.v1 import health
from app.api.v1.router import api_router
from app.core.body_limit import MULTIPART_OVERHEAD_BYTES, BodySizeLimitMiddleware
from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.core.rate_limit import RateLimitMiddleware

_Handler = Callable[[Request], Awaitable[Response]]


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: _Handler) -> Response:
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        structlog.contextvars.bind_contextvars(request_id=rid, path=request.url.path)
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.clear_contextvars()
        response.headers["X-Request-ID"] = rid
        return response


def _start_worker() -> Any:
    """The background worker, started inside this process (RUN_WORKER_IN_API).

    Imported lazily so an API-only process never loads the worker. Signals stay
    with Uvicorn; the lifespan below closes the worker on shutdown."""
    from arq.worker import create_worker

    from app.worker.main import WorkerSettings

    # WorkerSettings is a plain settings class (what the `arq` CLI accepts too).
    return create_worker(cast(Any, WorkerSettings), handle_signals=False)


@contextlib.asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    worker = _start_worker() if get_settings().run_worker_in_api else None
    task = asyncio.create_task(worker.async_run()) if worker is not None else None
    try:
        yield
    finally:
        if worker is not None and task is not None:
            await worker.close()  # stops polling, lets running jobs finish
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings)
    # Interactive API docs are a development aid; production does not publish
    # the schema or the Swagger/ReDoc UIs.
    docs_enabled = settings.env != "prod"
    app = FastAPI(
        title="Mana Career API",
        version="0.0.0",
        openapi_url="/api/openapi.json" if docs_enabled else None,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        lifespan=_lifespan,
    )
    # add_middleware prepends, so the last added runs outermost:
    # RequestID -> CORS -> RateLimit -> BodySizeLimit -> router.
    app.add_middleware(
        BodySizeLimitMiddleware,
        default_limit=settings.max_request_body_bytes,
        route_limits={
            ("POST", f"{settings.api_base_path}/resumes"): settings.resume_max_bytes
            + MULTIPART_OVERHEAD_BYTES,
        },
    )
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        # Readable by the web app across origins: the export's file name, how
        # long to wait after a rate limit, and the id support asks for.
        expose_headers=["Content-Disposition", "Retry-After", "X-Request-ID"],
    )
    app.add_middleware(RequestIDMiddleware)
    install_error_handlers(app)
    app.include_router(api_router, prefix=settings.api_base_path)
    # Health is also reachable at the root for container / uptime probes.
    app.include_router(health.router, include_in_schema=False)
    return app


app = create_app()
