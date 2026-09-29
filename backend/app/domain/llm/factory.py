from __future__ import annotations

from app.core.config import Settings
from app.domain.llm.adapters.anthropic import AnthropicAdapter
from app.domain.llm.adapters.fake import FakeLLMProvider
from app.domain.llm.provider import LLMProvider


def get_llm_provider(settings: Settings) -> LLMProvider:
    # Settings validation restricts the provider to shipped adapters and
    # guarantees the Anthropic key is present.
    if settings.llm_provider == "anthropic" and settings.anthropic_api_key is not None:
        return AnthropicAdapter(
            settings.anthropic_api_key.get_secret_value(),
            default_model=settings.llm_model_extraction,
        )
    return FakeLLMProvider()
