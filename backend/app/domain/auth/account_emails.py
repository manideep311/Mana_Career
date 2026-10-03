"""Emailed account links: reset a forgotten password, confirm an email address.

Tokens are random, single-use and short-lived; only their sha256 is stored.
Issuing a new link retires any earlier unused one of the same kind, and each
account can request at most ``MAX_PER_HOUR`` links of a kind per hour. The
emails always go to the account's own address.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.domain.auth.tokens import hash_link_token, new_link_token
from app.domain.email.factory import get_email_sender
from app.domain.email.mime import InvalidEmailMessage
from app.domain.email.smtp import EmailDeliveryError
from app.domain.email.types import EmailMessage
from app.models.auth import AuthToken
from app.models.user import User

log = get_logger("auth.account_emails")

Purpose = Literal["password_reset", "email_verify"]

TTL: dict[Purpose, dt.timedelta] = {
    "password_reset": dt.timedelta(minutes=30),
    "email_verify": dt.timedelta(hours=48),
}
MAX_PER_HOUR = 3
_PAGE: dict[Purpose, str] = {"password_reset": "reset-password", "email_verify": "verify-email"}
_MAX_RAW_LEN = 200


class InvalidLinkError(AppError):
    status, code, title = 400, "invalid_link", "This link can't be used"

    def __init__(self) -> None:
        super().__init__("This link is invalid or has expired. Request a new one.")


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _greeting(name: str) -> str:
    first = name.strip().split(" ")[0] if name.strip() else ""
    return f"Hi {first}," if first else "Hi,"


def link_for(base_url: str, purpose: Purpose, raw: str) -> str:
    # The token rides in the fragment: browsers never send it to a server or
    # put it in a Referer header.
    return f"{base_url}/{_PAGE[purpose]}#token={raw}"


def reset_email(*, name: str, email: str, link: str, brand: str) -> EmailMessage:
    body = (
        f"{_greeting(name)}\n\n"
        f"Someone (hopefully you) asked to reset the password for your {brand} account.\n\n"
        f"Choose a new password here:\n{link}\n\n"
        "The link works once and expires in 30 minutes. Resetting signs you out on "
        "every device.\n\n"
        "If you didn't ask for this, you can ignore this email: your password won't "
        f"change.\n\n{brand}\n"
    )
    return EmailMessage(
        to_email=email, to_name=name.strip() or None,
        subject=f"Reset your {brand} password", body=body, from_name=brand,
    )


def verify_email(*, name: str, email: str, link: str, brand: str) -> EmailMessage:
    body = (
        f"{_greeting(name)}\n\n"
        f"Please confirm this is your email address, so {brand} can send applications "
        "you approve:\n"
        f"{link}\n\n"
        "The link expires in 48 hours.\n\n"
        f"If you didn't create a {brand} account, you can ignore this email.\n\n{brand}\n"
    )
    return EmailMessage(
        to_email=email, to_name=name.strip() or None,
        subject=f"Confirm your email for {brand}", body=body, from_name=brand,
    )


class AccountEmailService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._s = session
        self._settings = settings

    async def issue(self, user: User, purpose: Purpose) -> str | None:
        """A fresh raw token, or ``None`` when this account hit the hourly limit."""
        now = _now()
        recent = (
            await self._s.execute(
                select(func.count()).select_from(AuthToken).where(
                    AuthToken.user_id == user.id,
                    AuthToken.purpose == purpose,
                    AuthToken.created_at >= now - dt.timedelta(hours=1),
                )
            )
        ).scalar_one()
        if recent >= MAX_PER_HOUR:
            log.info("account_email_throttled", purpose=purpose)
            return None
        await self._s.execute(
            update(AuthToken)
            .where(
                AuthToken.user_id == user.id,
                AuthToken.purpose == purpose,
                AuthToken.used_at.is_(None),
            )
            .values(used_at=now)
        )
        raw, digest = new_link_token()
        self._s.add(
            AuthToken(
                user_id=user.id, purpose=purpose, token_hash=digest,
                expires_at=now + TTL[purpose],
            )
        )
        await self._s.flush()
        return raw

    async def consume(self, raw: str, purpose: Purpose) -> User:
        """The account a valid, unused, unexpired link belongs to; the link is spent."""
        if not raw or len(raw) > _MAX_RAW_LEN:
            raise InvalidLinkError()
        row = (
            await self._s.execute(
                select(AuthToken)
                .where(AuthToken.token_hash == hash_link_token(raw))
                .with_for_update()
            )
        ).scalar_one_or_none()
        now = _now()
        if (
            row is None or row.purpose != purpose or row.used_at is not None
            or row.expires_at <= now
        ):
            raise InvalidLinkError()
        user = await self._s.get(User, row.user_id)
        if user is None or user.status != "active":
            raise InvalidLinkError()
        row.used_at = now
        await self._s.flush()
        return user

    def message(self, user: User, purpose: Purpose, raw: str) -> EmailMessage:
        link = link_for(self._settings.app_base_url, purpose, raw)
        build = reset_email if purpose == "password_reset" else verify_email
        return build(
            name=user.full_name, email=user.email, link=link,
            brand=self._settings.email_from_name,
        )


async def deliver(message: EmailMessage, settings: Settings) -> None:
    """Send an account email (runs after the HTTP response). Failures are logged,
    never raised: the person can simply ask for another link."""
    if settings.email_provider == "console" and settings.env == "dev":
        # Local development without a mail server: show the link so the flow can
        # still be completed. Never in test or production logs.
        link = next((ln for ln in message.body.splitlines() if "#token=" in ln), None)
        log.info("account_email_link_dev_only", subject=message.subject, link=link)
    try:
        await get_email_sender(settings).send(message)
    except (EmailDeliveryError, InvalidEmailMessage) as exc:
        log.warning("account_email_failed", subject=message.subject, reason=str(exc))
