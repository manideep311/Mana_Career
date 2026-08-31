from __future__ import annotations

from app.core.config import Settings
from app.domain.llm.adapters.fake import FakeLLMProvider
from app.domain.llm.provider import LLMProvider


def get_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "fake":
        return FakeLLMProvider()
    raise NotImplementedError(
        f"{settings.llm_provider!r} LLM adapter lands in Phase 7"
    )
