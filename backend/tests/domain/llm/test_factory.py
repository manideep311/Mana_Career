"""Which LLM provider the settings produce."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.domain.llm.adapters.anthropic import AnthropicAdapter
from app.domain.llm.adapters.fake import FakeLLMProvider
from app.domain.llm.adapters.openai_compat import OpenAICompatAdapter
from app.domain.llm.daily_cap import DailyCappedLLM
from app.domain.llm.factory import get_llm_provider
from app.domain.llm.provider import provider_name


def _settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return Settings(_env_file=None)  # type: ignore[call-arg]


def test_groq_through_the_openai_compatible_adapter(monkeypatch: pytest.MonkeyPatch):
    s = _settings(
        monkeypatch, LLM_PROVIDER="openai_compat", LLM_API_KEY="gsk_x",
        LLM_MODEL="openai/gpt-oss-20b", LLM_REASONING_EFFORT="medium",
    )
    llm = get_llm_provider(s)
    assert isinstance(llm, OpenAICompatAdapter)
    assert llm._model == "openai/gpt-oss-20b" and llm._reasoning_effort == "medium"
    assert llm._base_url == "https://api.groq.com/openai/v1"


def test_a_daily_cap_wraps_real_providers(monkeypatch: pytest.MonkeyPatch):
    s = _settings(
        monkeypatch, LLM_PROVIDER="openai_compat", LLM_API_KEY="gsk_x",
        LLM_DAILY_CALL_LIMIT="150",
    )
    llm = get_llm_provider(s)
    assert isinstance(llm, DailyCappedLLM) and isinstance(llm.wrapped, OpenAICompatAdapter)
    # Generated documents record the real adapter, not the wrapper.
    assert provider_name(llm) == "OpenAICompatAdapter"


def test_the_fake_is_never_capped(monkeypatch: pytest.MonkeyPatch):
    s = _settings(monkeypatch, LLM_PROVIDER="fake", LLM_DAILY_CALL_LIMIT="1")
    assert isinstance(get_llm_provider(s), FakeLLMProvider)


def test_anthropic_still_works(monkeypatch: pytest.MonkeyPatch):
    s = _settings(monkeypatch, LLM_PROVIDER="anthropic", ANTHROPIC_API_KEY="sk-ant-x")
    assert isinstance(get_llm_provider(s), AnthropicAdapter)
