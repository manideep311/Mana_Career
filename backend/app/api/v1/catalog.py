"""Public, read-only facts about the shared catalogue.

The landing page shows these instead of marketing numbers: how many career
paths, roles, skills and learning resources the guidance actually draws on.
Only catalogue rows (``user_id IS NULL``) are counted; no user data is read.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Response
from pydantic import BaseModel

from app.api.deps import DbDep
from app.domain.career.service import CareerService

router = APIRouter(prefix="/catalog", tags=["catalog"])


class CatalogStatsOut(BaseModel):
    career_paths: int
    roles: int
    skills: int
    learning_resources: int


# The catalogue only changes when it is re-seeded, but every landing-page view
# asks: answer from memory for a few minutes (per worker process) and let
# browsers and proxies keep the answer for as long.
STATS_TTL_SECONDS = 300
_stats_cache: dict[str, tuple[float, CatalogStatsOut]] = {}


def clear_stats_cache() -> None:
    _stats_cache.clear()


@router.get("/stats")
async def catalog_stats(db: DbDep, response: Response) -> CatalogStatsOut:
    now = time.monotonic()
    hit = _stats_cache.get("stats")
    if hit is None or now - hit[0] > STATS_TTL_SECONDS:
        s = await CareerService(db).catalog_stats()
        hit = (
            now,
            CatalogStatsOut(
                career_paths=s.career_paths, roles=s.roles, skills=s.skills,
                learning_resources=s.learning_resources,
            ),
        )
        _stats_cache["stats"] = hit
    response.headers["Cache-Control"] = f"public, max-age={STATS_TTL_SECONDS}"
    return hit[1]
