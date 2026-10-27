from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.redis import redis_from_settings
from app.domain.llm.daily_cap import ai_paused

router = APIRouter(tags=["meta"])


class MetaOut(BaseModel):
    """What this deployment can do — the UI uses it to be honest about limits."""

    demo_mode: bool
    ai_writing: bool
    web_research: bool
    # Where approved application emails go: nowhere (console), the applicant's
    # own inbox (redirect), or the employer (live).
    email_delivery: Literal["console", "redirect", "live"]
    # The day's cap on model calls is used up (LLM_DAILY_CALL_LIMIT).
    ai_paused: bool
    # Accounts are deleted this many days after sign-up; 0 = kept.
    retention_days: int


@router.get("/meta", response_model=MetaOut)
async def meta() -> MetaOut:
    settings = get_settings()
    paused = settings.ai_generation_enabled and await ai_paused(
        redis_from_settings(settings), settings.llm_daily_call_limit
    )
    return MetaOut(
        demo_mode=settings.demo_mode,
        ai_writing=settings.ai_generation_enabled,
        web_research=settings.search_provider != "none",
        email_delivery=(
            "console" if settings.email_provider == "console" else settings.email_delivery
        ),
        ai_paused=paused,
        retention_days=settings.demo_retention_days,
    )
