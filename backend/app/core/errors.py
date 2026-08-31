from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

log = get_logger("errors")
PROBLEM_MEDIA_TYPE = "application/problem+json"


class AppError(Exception):
    status: int = 500
    code: str = "internal_error"
    title: str = "Something went wrong"

    def __init__(
        self,
        detail: str | None = None,
        *,
        errors: list[dict[str, Any]] | None = None,
        code: str | None = None,
    ) -> None:
        super().__init__(detail or self.title)
        self.detail = detail
        self.errors = errors
        if code is not None:
            self.code = code


class NotFoundError(AppError):
    status, code, title = 404, "not_found", "Not found"


class ValidationAppError(AppError):
    status, code, title = 422, "validation_error", "Your input needs a change"


class AuthError(AppError):
    status, code, title = 401, "unauthorized", "Please sign in"


class ForbiddenError(AppError):
    status, code, title = 403, "forbidden", "You can't do that"


class ConflictError(AppError):
    status, code, title = 409, "conflict", "That conflicts with existing data"


class RateLimitedError(AppError):
    status, code, title = 429, "rate_limited", "Slow down a moment"

    def __init__(self, *, retry_after: int, detail: str | None = None) -> None:
        super().__init__(detail)
        self.retry_after = retry_after


_STATUS_TO_ERROR: dict[int, type[AppError]] = {
    401: AuthError,
    403: ForbiddenError,
    404: NotFoundError,
    409: ConflictError,
    422: ValidationAppError,
}


def to_problem(exc: AppError, *, instance: str) -> dict[str, Any]:
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": exc.title,
        "status": exc.status,
        "detail": exc.detail,
        "instance": instance,
        "code": exc.code,
    }
    if exc.errors:
        body["errors"] = exc.errors
    return body


def _response(exc: AppError, instance: str) -> JSONResponse:
    headers: dict[str, str] = {}
    if isinstance(exc, RateLimitedError):
        headers["Retry-After"] = str(exc.retry_after)
    return JSONResponse(
        status_code=exc.status,
        content=to_problem(exc, instance=instance),
        media_type=PROBLEM_MEDIA_TYPE,
        headers=headers,
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        level = "warning" if exc.status < 500 else "error"
        getattr(log, level)("app_error", code=exc.code, status=exc.status,
                            path=request.url.path)
        return _response(exc, str(request.url))

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        wrapped = ValidationAppError(
            detail="One or more fields are invalid.",
            errors=[{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]}
                    for e in exc.errors()],
        )
        return _response(wrapped, str(request.url))

    @app.exception_handler(StarletteHTTPException)
    async def _starlette_http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        err_cls = _STATUS_TO_ERROR.get(exc.status_code, AppError)
        detail = exc.detail if isinstance(exc.detail, str) else None
        err = err_cls(detail=detail)
        err.status = exc.status_code
        return _response(err, str(request.url))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_exception", path=request.url.path)
        return _response(AppError(), str(request.url))
