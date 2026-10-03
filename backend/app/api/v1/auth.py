from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, BackgroundTasks, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.cookies import clear_refresh_cookie, set_refresh_cookie
from app.api.deps import CurrentUser, DbDep, SettingsDep
from app.api.v1.schemas.auth import (
    AccessResponse,
    AuthResponse,
    ForgotPasswordIn,
    LoginIn,
    MessageOut,
    PasswordChangeIn,
    RegisterIn,
    ResetPasswordIn,
    UserOut,
    VerifyEmailIn,
)
from app.core.client_ip import client_ip
from app.core.config import Settings, get_settings
from app.core.errors import AuthError
from app.domain.auth.account_emails import AccountEmailService, Purpose, deliver
from app.domain.auth.service import AccessResult, AuthResult, AuthService
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])

# The same words whether or not the account exists, so the form can't be used
# to find out who has one.
FORGOT_SENT = (
    "If an account exists for that address, we've sent a link to reset the password. "
    "It expires in 30 minutes."
)


# Both answers to "forgot password" take at least this long. Issuing a link
# for a real account costs a few extra queries; padding every answer to the
# same floor means response time can't reveal whether an address has one.
FORGOT_MIN_SECONDS = 0.5
_sleep = asyncio.sleep  # test seam


async def _send_link(
    db: AsyncSession, settings: Settings, background: BackgroundTasks,
    user: User, purpose: Purpose,
) -> bool:
    """Issue a link and email it after the response. False when throttled."""
    svc = AccountEmailService(db, settings)
    raw = await svc.issue(user, purpose)
    if raw is None:
        return False
    message = svc.message(user, purpose, raw)
    await db.commit()  # the link must exist before anyone can click it
    background.add_task(deliver, message, settings)
    return True


def _client_ip(request: Request) -> str | None:
    ip = client_ip(request, get_settings())
    return None if ip == "unknown" else ip


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
    body: RegisterIn, request: Request, response: Response, db: DbDep, settings: SettingsDep,
    background: BackgroundTasks,
) -> AuthResponse:
    result = await AuthService(db, settings).register(
        body.email, body.password, body.full_name,
        ip=_client_ip(request), user_agent=request.headers.get("user-agent"),
    )
    await _send_link(db, settings, background, result.user, "email_verify")
    set_refresh_cookie(response, result.refresh_token, settings)
    return _auth_response(result)


@router.post("/login")
async def login(
    body: LoginIn, request: Request, response: Response, db: DbDep, settings: SettingsDep
) -> AuthResponse:
    result = await AuthService(db, settings).authenticate(
        body.email, body.password,
        ip=_client_ip(request), user_agent=request.headers.get("user-agent"),
    )
    set_refresh_cookie(response, result.refresh_token, settings)
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
    set_refresh_cookie(response, result.refresh_token, settings)
    return _access_response(result)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request, response: Response, db: DbDep, settings: SettingsDep
) -> None:
    await AuthService(db, settings).logout(
        request.cookies.get(settings.refresh_cookie_name)
    )
    clear_refresh_cookie(response, settings)


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
    set_refresh_cookie(response, result.refresh_token, settings)
    return _access_response(result)


@router.post("/password/forgot", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(
    body: ForgotPasswordIn, db: DbDep, settings: SettingsDep, background: BackgroundTasks,
) -> MessageOut:
    started = time.monotonic()
    user = await AuthService(db, settings).find_active_by_email(body.email)
    if user is not None:
        await _send_link(db, settings, background, user, "password_reset")
    await _sleep(max(0.0, FORGOT_MIN_SECONDS - (time.monotonic() - started)))
    return MessageOut(detail=FORGOT_SENT)


@router.post("/password/reset", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    body: ResetPasswordIn, request: Request, db: DbDep, settings: SettingsDep,
) -> None:
    user = await AccountEmailService(db, settings).consume(body.token, "password_reset")
    await AuthService(db, settings).reset_password(
        user, body.new_password,
        ip=_client_ip(request), user_agent=request.headers.get("user-agent"),
    )


@router.post("/email/verify", status_code=status.HTTP_204_NO_CONTENT)
async def verify_email(
    body: VerifyEmailIn, request: Request, db: DbDep, settings: SettingsDep,
) -> None:
    user = await AccountEmailService(db, settings).consume(body.token, "email_verify")
    await AuthService(db, settings).mark_email_verified(
        user, ip=_client_ip(request), user_agent=request.headers.get("user-agent"),
    )


@router.post("/email/verify/resend", status_code=status.HTTP_202_ACCEPTED)
async def resend_verification(
    db: DbDep, settings: SettingsDep, background: BackgroundTasks, user: CurrentUser,
) -> MessageOut:
    if user.email_verified:
        return MessageOut(detail="Your email address is already confirmed.")
    if not await _send_link(db, settings, background, user, "email_verify"):
        return MessageOut(
            detail="You've asked for several links recently. Use the latest one, or try "
            "again in an hour."
        )
    return MessageOut(
        detail=f"We've sent a new link to {user.email}. It expires in 48 hours."
    )
