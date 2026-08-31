from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response
from sqlalchemy import text

from app.api.deps import DbDep, RedisDep
from app.core.redis import ping_redis

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(response: Response, db: DbDep, r: RedisDep) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        checks["database"] = False
    checks["redis"] = await ping_redis(r)
    try:
        row = (await db.execute(text("SELECT version_num FROM alembic_version"))).first()
        checks["migrations"] = row is not None
    except Exception:
        checks["migrations"] = False
    ok = all(checks.values())
    response.status_code = 200 if ok else 503
    return {"status": "ready" if ok else "degraded", "checks": checks}
