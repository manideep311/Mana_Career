from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import audit
from app.core.config import Settings, get_settings
from app.core.errors import AuthError, ConflictError, ForbiddenError
from app.core.logging import current_request_id
from app.domain.auth.passwords import hash_password, verify_password
from app.domain.auth.tokens import (
    create_access_token,
    hash_refresh_token,
    new_refresh_token,
)
from app.models.auth import RefreshToken
from app.models.user import User


@dataclass(frozen=True)
class AuthResult:
    user: User
    access_token: str
    expires_in: int
    refresh_token: str


@dataclass(frozen=True)
class AccessResult:
    access_token: str
    expires_in: int
    refresh_token: str


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    async def _by_email(self, email: str) -> User | None:
        return (
            await self.session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()

    async def _revoke_family(self, family_id: uuid.UUID) -> None:
        await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=_now())
        )

    async def _issue(
        self,
        user: User,
        *,
        ip: str | None,
        user_agent: str | None,
        family_id: uuid.UUID | None = None,
    ) -> tuple[str, int, str, RefreshToken]:
        fam = family_id or uuid.uuid4()
        raw, digest = new_refresh_token()
        row = RefreshToken(
            user_id=user.id,
            token_hash=digest,
            family_id=fam,
            expires_at=_now() + dt.timedelta(seconds=self.settings.jwt_refresh_ttl_seconds),
            ip=ip,
            user_agent=user_agent,
        )
        self.session.add(row)
        await self.session.flush()
        access, expires_in = create_access_token(user.id, settings=self.settings)
        return access, expires_in, raw, row

    async def _audit(
        self,
        action: str,
        *,
        user_id: uuid.UUID | None,
        ip: str | None,
        user_agent: str | None,
        result: Literal["success", "failure"] = "success",
    ) -> None:
        await audit(
            self.session,
            actor_type="user",
            action=action,
            result=result,
            actor_user_id=user_id,
            ip=ip,
            user_agent=user_agent,
            request_id=current_request_id(),
        )

    async def register(
        self, email: str, password: str, full_name: str, *,
        ip: str | None, user_agent: str | None,
    ) -> AuthResult:
        if await self._by_email(email) is not None:
            raise ConflictError(
                detail="That email is already registered.", code="email_taken"
            )
        user = User(email=email, password_hash=hash_password(password), full_name=full_name)
        self.session.add(user)
        await self.session.flush()
        access, expires_in, raw, _ = await self._issue(user, ip=ip, user_agent=user_agent)
        await self._audit("auth.register", user_id=user.id, ip=ip, user_agent=user_agent)
        return AuthResult(user, access, expires_in, raw)

    async def authenticate(
        self, email: str, password: str, *, ip: str | None, user_agent: str | None,
    ) -> AuthResult:
        user = await self._by_email(email)
        if user is None or not verify_password(user.password_hash, password):
            await self._audit(
                "auth.login_failed",
                user_id=user.id if user else None,
                ip=ip, user_agent=user_agent, result="failure",
            )
            raise AuthError(
                detail="That email or password is not right.", code="invalid_credentials"
            )
        if user.status != "active":
            raise ForbiddenError(
                detail="This account is disabled.", code="account_disabled"
            )
        user.last_login_at = _now()
        access, expires_in, raw, _ = await self._issue(user, ip=ip, user_agent=user_agent)
        await self._audit("auth.login", user_id=user.id, ip=ip, user_agent=user_agent)
        return AuthResult(user, access, expires_in, raw)

    async def rotate(
        self, raw_refresh: str, *, ip: str | None, user_agent: str | None,
    ) -> AccessResult:
        row = (
            await self.session.execute(
                select(RefreshToken).where(
                    RefreshToken.token_hash == hash_refresh_token(raw_refresh)
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise AuthError(detail="Please sign in again.", code="invalid_refresh")
        if row.revoked_at is not None:
            # Reuse of an already-rotated token => the family is compromised.
            # Persist the revoke BEFORE raising: get_session rolls back on the
            # exception, and a rolled-back revoke would leave the stolen family
            # usable — defeating reuse detection entirely.
            await self._revoke_family(row.family_id)
            await self._audit(
                "auth.refresh_reuse_detected", user_id=row.user_id,
                ip=ip, user_agent=user_agent, result="failure",
            )
            await self.session.commit()
            raise AuthError(detail="Please sign in again.", code="refresh_reuse")
        if row.expires_at <= _now():
            raise AuthError(detail="Please sign in again.", code="expired_refresh")
        user = await self.session.get(User, row.user_id)
        assert user is not None
        access, expires_in, raw, new_row = await self._issue(
            user, ip=ip, user_agent=user_agent, family_id=row.family_id
        )
        row.revoked_at = _now()
        row.replaced_by_id = new_row.id
        await self._audit("auth.refresh", user_id=row.user_id, ip=ip, user_agent=user_agent)
        return AccessResult(access, expires_in, raw)

    async def logout(self, raw_refresh: str | None) -> None:
        if not raw_refresh:
            return
        row = (
            await self.session.execute(
                select(RefreshToken).where(
                    RefreshToken.token_hash == hash_refresh_token(raw_refresh)
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return
        await self._revoke_family(row.family_id)
        await self._audit("auth.logout", user_id=row.user_id, ip=None, user_agent=None)

    async def change_password(
        self, user: User, current: str, new: str, *,
        ip: str | None, user_agent: str | None,
    ) -> AuthResult:
        if not verify_password(user.password_hash, current):
            raise AuthError(
                detail="That email or password is not right.", code="invalid_credentials"
            )
        user.password_hash = hash_password(new)
        await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=_now())
        )
        access, expires_in, raw, _ = await self._issue(user, ip=ip, user_agent=user_agent)
        await self._audit(
            "auth.password_change", user_id=user.id, ip=ip, user_agent=user_agent
        )
        return AuthResult(user, access, expires_in, raw)
