"""Request-body size guard that holds without nginx and without Content-Length.

nginx caps bodies at 12 MB in production, but the API must stay safe when it
is reached directly (local dev, a misconfigured deploy). FastAPI parses a
multipart body before any dependency runs — before authentication — so the cap
has to be enforced while the body streams in, not after it is buffered.

- A declared ``Content-Length`` over the cap is rejected before reading.
- Otherwise the bytes are counted as they arrive and the request is stopped
  (413) as soon as the count passes the cap. FastAPI re-raises an
  ``HTTPException`` raised during body parsing, so the app's error handler
  renders the usual problem+json response.
"""

from __future__ import annotations

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import PROBLEM_MEDIA_TYPE, PayloadTooLargeError, to_problem

# Multipart framing (boundaries, part headers, the filename) on top of the file.
MULTIPART_OVERHEAD_BYTES = 64 * 1024
_MESSAGE = "This request is larger than the server accepts."


class BodySizeLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        default_limit: int,
        route_limits: dict[tuple[str, str], int] | None = None,
    ) -> None:
        self.app = app
        self.default_limit = default_limit
        self.route_limits = route_limits or {}

    def limit_for(self, method: str, path: str) -> int:
        return self.route_limits.get((method, path.rstrip("/") or "/"), self.default_limit)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit = self.limit_for(scope["method"], scope["path"])
        declared = _content_length(scope)
        if declared is not None and declared > limit:
            await _reject(scope, receive, send)
            return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise HTTPException(status_code=413, detail=_MESSAGE)
            return message

        await self.app(scope, limited_receive, send)


def _content_length(scope: Scope) -> int | None:
    for name, value in scope.get("headers", []):
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None


async def _reject(scope: Scope, receive: Receive, send: Send) -> None:
    path = scope.get("path", "")
    response = JSONResponse(
        to_problem(PayloadTooLargeError(_MESSAGE), instance=path),
        status_code=413,
        media_type=PROBLEM_MEDIA_TYPE,
    )
    await response(scope, receive, send)
