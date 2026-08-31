from __future__ import annotations

import uuid
from typing import Annotated

import redis.asyncio as redis
from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.errors import AuthError, ForbiddenError
from app.core.redis import redis_from_settings
from app.domain.auth.tokens import decode_access_token
from app.models.user import User

SettingsDep = Annotated[Settings, Depends(get_settings)]
DbDep = Annotated[AsyncSession, Depends(get_session)]


def _redis_dep(settings: SettingsDep) -> redis.Redis:
    return redis_from_settings(settings)


RedisDep = Annotated[redis.Redis, Depends(_redis_dep)]


async def get_current_user(
    db: DbDep,
    settings: SettingsDep,
    authorization: str | None = Header(default=None),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthError(detail="Please sign in.", code="missing_token")
    user_id: uuid.UUID = decode_access_token(authorization[7:].strip(), settings=settings)
    user = await db.get(User, user_id)
    if user is None:
        raise AuthError(detail="Please sign in.", code="invalid_token")
    if user.status != "active":
        raise ForbiddenError(detail="This account is disabled.", code="account_disabled")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_admin(user: CurrentUser) -> User:
    if not user.is_admin:
        raise ForbiddenError(detail="Admins only.", code="forbidden")
    return user


CurrentAdmin = Annotated[User, Depends(get_current_admin)]
