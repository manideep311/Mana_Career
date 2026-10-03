from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings

router = APIRouter(tags=["meta"])


class MetaOut(BaseModel):
    """What this deployment can do — the UI uses it to be honest about limits."""

    demo_mode: bool
    ai_writing: bool
    web_research: bool
    # Where approved application emails go: nowhere (console), the applicant's
    # own inbox (redirect), or the employer (live).
    email_delivery: Literal["console", "redirect", "live"]


@router.get("/meta", response_model=MetaOut)
async def meta() -> MetaOut:
    settings = get_settings()
    return MetaOut(
        demo_mode=settings.demo_mode,
        ai_writing=settings.ai_generation_enabled,
        web_research=settings.search_provider != "none",
        email_delivery=(
            "console" if settings.email_provider == "console" else settings.email_delivery
        ),
    )
