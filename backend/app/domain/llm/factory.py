from __future__ import annotations

from app.core.config import Settings
from app.core.redis import redis_from_settings
from app.domain.llm.adapters.anthropic import AnthropicAdapter
from app.domain.llm.adapters.fake import FakeLLMProvider
from app.domain.llm.adapters.openai_compat import OpenAICompatAdapter
from app.domain.llm.daily_cap import DailyCappedLLM
from app.domain.llm.provider import LLMProvider


def get_llm_provider(settings: Settings) -> LLMProvider:
    provider = _adapter(settings)
    # The fake costs nothing, so only real providers count toward the daily cap.
    if not isinstance(provider, FakeLLMProvider) and settings.llm_daily_call_limit > 0:
        return DailyCappedLLM(
            provider, redis=redis_from_settings(settings), limit=settings.llm_daily_call_limit
        )
    return provider


def _adapter(settings: Settings) -> LLMProvider:
    # Settings validation restricts the provider to shipped adapters and
    # guarantees each real provider's key is present.
    if settings.llm_provider == "anthropic" and settings.anthropic_api_key is not None:
        return AnthropicAdapter(
            settings.anthropic_api_key.get_secret_value(),
            default_model=settings.llm_model_extraction,
        )
    if settings.llm_provider == "openai_compat" and settings.llm_api_key is not None:
        return OpenAICompatAdapter(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key.get_secret_value(),
            model=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
            reasoning_effort=settings.llm_reasoning_effort,
        )
    return FakeLLMProvider()
