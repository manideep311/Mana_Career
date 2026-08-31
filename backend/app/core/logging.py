from __future__ import annotations

import logging
import re
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog

from app.core.config import Settings

SECRET_KEYS: frozenset[str] = frozenset({
    "password", "token", "authorization", "api_key", "apikey", "jwt_secret",
    "secret", "refresh_token", "access_token", "set-cookie", "cookie",
})
SECRET_PATTERN: re.Pattern[str] = re.compile(
    r"(sk-[A-Za-z0-9_\-]{8,})|(Bearer\s+[A-Za-z0-9._\-]{10,})|([A-Fa-f0-9]{24,})"
)


def redact_secrets(
    _: Any, __: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    for key, value in list(event_dict.items()):
        if key.lower() in SECRET_KEYS:
            event_dict[key] = "***"
        elif isinstance(value, str) and SECRET_PATTERN.search(value):
            event_dict[key] = "***"
    return event_dict


def configure_logging(settings: Settings) -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    shared: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        timestamper,
        redact_secrets,
    ]
    renderer: structlog.types.Processor = (
        structlog.dev.ConsoleRenderer() if settings.env == "dev"
        else structlog.processors.JSONRenderer()
    )
    structlog.configure(
        processors=[*shared, structlog.processors.StackInfoRenderer(),
                    structlog.processors.format_exc_info, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)


def current_request_id() -> str | None:
    """The request id bound by RequestIDMiddleware, or None outside a request."""
    value = structlog.contextvars.get_contextvars().get("request_id")
    return value if isinstance(value, str) else None
