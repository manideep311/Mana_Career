import json

import pytest

from app.core.errors import AppError
from app.domain.jobs.extractor import JDSkill, JobExtraction, JobExtractor
from app.domain.llm.adapters.fake import FakeLLMProvider
from app.domain.llm.provider import LLMResult


async def test_extract_returns_empty_model_from_fake_provider():
    out = await JobExtractor(FakeLLMProvider(), model="fake").extract(
        "Senior ML Engineer at Acme. Remote. Python, PyTorch. $180k-$220k."
    )
    assert isinstance(out, JobExtraction)
    assert out.responsibilities == []
    assert out.required_skills == [] and out.preferred_skills == []


async def test_extract_validates_a_real_structured_payload():
    payload = JobExtraction(
        title="Senior ML Engineer", company="Acme", work_mode="remote",
        seniority="senior", salary_min=180000, salary_max=220000, salary_currency="USD",
        salary_period="year", responsibilities=["Ship models", "Mentor"],
        required_skills=[JDSkill(raw="Python", weight=0.9), JDSkill(raw="PyTorch", weight=0.8)],
        preferred_skills=[JDSkill(raw="Kubernetes", weight=0.4)],
    ).model_dump()

    class _Canned(FakeLLMProvider):
        async def complete(self, messages, *, schema=None, max_tokens=1024, temperature=0.2):
            base = await super().complete(messages, schema=None, max_tokens=max_tokens)
            return LLMResult(text=json.dumps(payload), model=base.model,
                             input_tokens=base.input_tokens, output_tokens=base.output_tokens,
                             cost_usd=0.0, structured=payload)

    out = await JobExtractor(_Canned(), model="fake").extract("...")
    assert out.title == "Senior ML Engineer"
    assert [s.raw for s in out.required_skills] == ["Python", "PyTorch"]
    assert out.preferred_skills[0].weight == 0.4


async def test_extract_raises_when_no_structured():
    class _NoStructured(FakeLLMProvider):
        async def complete(self, messages, *, schema=None, max_tokens=1024, temperature=0.2):
            return await super().complete(messages, schema=None, max_tokens=max_tokens)

    with pytest.raises(AppError):
        await JobExtractor(_NoStructured(), model="fake").extract("x")
