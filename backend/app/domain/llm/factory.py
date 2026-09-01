from __future__ import annotations

from app.core.config import Settings
from app.core.errors import AppError
from app.domain.llm.adapters.anthropic import AnthropicAdapter
from app.domain.llm.adapters.fake import FakeLLMProvider
from app.domain.llm.provider import LLMProvider


def get_llm_provider(settings: Settings) -> LLMProvider:
    provider = settings.llm_provider
    if provider == "fake":
        return FakeLLMProvider()
    if provider == "anthropic":
        if settings.anthropic_api_key is None:
            raise AppError(code="llm.not_configured")
        return AnthropicAdapter(
            settings.anthropic_api_key.get_secret_value(),
            default_model=settings.llm_model_extraction,
        )
    raise NotImplementedError(f"{provider} LLM adapter lands in Phase 7")
