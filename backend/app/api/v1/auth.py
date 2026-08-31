from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from app.api.deps import CurrentUser, DbDep, SettingsDep
from app.api.v1.schemas.auth import (
    AccessResponse,
    AuthResponse,
    LoginIn,
    PasswordChangeIn,
    RegisterIn,
    UserOut,
)
from app.core.config import Settings
from app.core.errors import AuthError
from app.domain.auth.service import AccessResult, AuthResult, AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _set_refresh_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=token,
        max_age=settings.jwt_refresh_ttl_seconds,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="strict",
        path=f"{settings.api_base_path}/auth",
    )


def _clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path=f"{settings.api_base_path}/auth",
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="strict",
    )


def _auth_response(result: AuthResult) -> AuthResponse:
    return AuthResponse(
        access_token=result.access_token,
        expires_in=result.expires_in,
        user=UserOut.model_validate(result.user),
    )


def _access_response(result: AccessResult | AuthResult) -> AccessResponse:
    return AccessResponse(access_token=result.access_token, expires_in=result.expires_in)


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterIn, request: Request, response: Response, db: DbDep, settings: SettingsDep
) -> AuthResponse:
    result = await AuthService(db, settings).register(
        body.email, body.password, body.full_name,
        ip=_client_ip(request), user_agent=request.headers.get("user-agent"),
    )
    _set_refresh_cookie(response, result.refresh_token, settings)
    return _auth_response(result)


@router.post("/login")
async def login(
    body: LoginIn, request: Request, response: Response, db: DbDep, settings: SettingsDep
) -> AuthResponse:
    result = await AuthService(db, settings).authenticate(
        body.email, body.password,
        ip=_client_ip(request), user_agent=request.headers.get("user-agent"),
    )
    _set_refresh_cookie(response, result.refresh_token, settings)
    return _auth_response(result)


@router.post("/refresh")
async def refresh(
    request: Request, response: Response, db: DbDep, settings: SettingsDep
) -> AccessResponse:
    raw = request.cookies.get(settings.refresh_cookie_name)
    if not raw:
        raise AuthError(detail="Please sign in again.", code="missing_refresh")
    result = await AuthService(db, settings).rotate(
        raw, ip=_client_ip(request), user_agent=request.headers.get("user-agent")
    )
    _set_refresh_cookie(response, result.refresh_token, settings)
    return _access_response(result)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request, response: Response, db: DbDep, settings: SettingsDep
) -> None:
    await AuthService(db, settings).logout(
        request.cookies.get(settings.refresh_cookie_name)
    )
    _clear_refresh_cookie(response, settings)


@router.get("/me")
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.post("/password/change")
async def change_password(
    body: PasswordChangeIn,
    request: Request,
    response: Response,
    db: DbDep,
    settings: SettingsDep,
    user: CurrentUser,
) -> AccessResponse:
    result = await AuthService(db, settings).change_password(
        user, body.current_password, body.new_password,
        ip=_client_ip(request), user_agent=request.headers.get("user-agent"),
    )
    _set_refresh_cookie(response, result.refresh_token, settings)
    return _access_response(result)
