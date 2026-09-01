import json

import pytest

from app.core.errors import AppError
from app.domain.llm.adapters.fake import FakeLLMProvider
from app.domain.llm.provider import LLMResult
from app.domain.resume.extractor import (
    ExtractedExperience,
    ResumeExtraction,
    ResumeExtractor,
)


async def test_extract_returns_validated_model_from_fake():
    ex = ResumeExtractor(FakeLLMProvider(), model="fake")
    out = await ex.extract("Jane Doe\nSenior ML Engineer at Acme 2021-2024\nPython, PyTorch")
    assert isinstance(out, ResumeExtraction)
    assert out.skills == [] and out.experiences == []  # fake returns schema stubs


async def test_extract_validates_a_real_structured_payload():
    payload = ResumeExtraction(
        full_name="Jane Doe", skills=["Python", "PyTorch"],
        experiences=[ExtractedExperience(company="Acme", title="ML Eng")],
    ).model_dump()

    class _Canned(FakeLLMProvider):
        async def complete(self, messages, *, schema=None, max_tokens=1024, temperature=0.2):
            base = await super().complete(messages, schema=None, max_tokens=max_tokens)
            return LLMResult(text=json.dumps(payload), model=base.model,
                             input_tokens=base.input_tokens, output_tokens=base.output_tokens,
                             cost_usd=0.0, structured=payload)

    out = await ResumeExtractor(_Canned(), model="fake").extract("...")
    assert out.full_name == "Jane Doe"
    assert out.skills == ["Python", "PyTorch"]
    assert [e.company for e in out.experiences] == ["Acme"]


async def test_extract_raises_when_no_structured():
    class _NoStructured(FakeLLMProvider):
        async def complete(self, messages, *, schema=None, max_tokens=1024, temperature=0.2):
            r = await super().complete(messages, schema=None, max_tokens=max_tokens)
            return r  # structured is None

    with pytest.raises(AppError):
        await ResumeExtractor(_NoStructured(), model="fake").extract("x")
