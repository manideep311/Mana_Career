"""The refresh-token cookie, shared by the routes that sign people in and out.

Scoped to the auth routes' path, httpOnly, SameSite=Strict, and Secure in
production: the browser sends it only to refresh or end a session.
"""

from __future__ import annotations

from fastapi import Response

from app.core.config import Settings


def _path(settings: Settings) -> str:
    return f"{settings.api_base_path}/auth"


def set_refresh_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=token,
        max_age=settings.jwt_refresh_ttl_seconds,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="strict",
        path=_path(settings),
    )


def clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path=_path(settings),
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="strict",
    )
