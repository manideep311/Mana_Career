from __future__ import annotations

from typing import Annotated

import redis.asyncio as redis
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.redis import redis_from_settings

SettingsDep = Annotated[Settings, Depends(get_settings)]
DbDep = Annotated[AsyncSession, Depends(get_session)]


def _redis_dep(settings: SettingsDep) -> redis.Redis:
    return redis_from_settings(settings)


RedisDep = Annotated[redis.Redis, Depends(_redis_dep)]
