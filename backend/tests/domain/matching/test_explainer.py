import json

from app.domain.llm.adapters.fake import FakeLLMProvider
from app.domain.llm.provider import LLMResult
from app.domain.matching.explainer import GapRationaleWriter, MatchExplainer
from app.domain.matching.gaps import GapDraft
from app.domain.matching.scorer import Component, ScoreResult


def _score_result() -> ScoreResult:
    comp = Component(
        dimension="skill", raw_score=0.8, weight=0.22, contribution=17.6,
        detail={"matched": ["a"], "missing": ["b"]}, evidence=[],
    )
    return ScoreResult(
        score=72.0, band="good", components=(comp,),
        dimension_scores={"skill": 0.8, "seniority": 0.3},
        strengths=[{"dimension": "skill", "raw_score": 0.8, "contribution": 17.6}],
        gaps=[{"dimension": "seniority", "raw_score": 0.3, "weight": 0.08}],
        inputs_hash="abc",
    )


def _canned(payload: dict) -> type[FakeLLMProvider]:
    class _Canned(FakeLLMProvider):
        async def complete(self, messages, *, schema=None, max_tokens=1024, temperature=0.2):
            base = await super().complete(messages, schema=None, max_tokens=max_tokens)
            return LLMResult(
                text=json.dumps(payload), model=base.model,
                input_tokens=base.input_tokens, output_tokens=base.output_tokens,
                cost_usd=0.0, structured=payload,
            )

    return _Canned


async def test_explain_returns_none_from_fake_provider():
    explainer = MatchExplainer(FakeLLMProvider(), model="fake")
    out = await explainer.explain(
        job_title="Staff Engineer", company="Acme", result=_score_result()
    )
    assert out is None
    assert explainer.last_usage is not None


async def test_explain_returns_prose_from_canned_subclass():
    provider = _canned({"text": "Strong on skills, weak on seniority."})
    explainer = MatchExplainer(provider(), model="fake")
    out = await explainer.explain(
        job_title="Staff Engineer", company=None, result=_score_result()
    )
    assert out == "Strong on skills, weak on seniority."


async def test_explain_returns_none_when_no_structured():
    class _NoStructured(FakeLLMProvider):
        async def complete(self, messages, *, schema=None, max_tokens=1024, temperature=0.2):
            return await super().complete(messages, schema=None, max_tokens=max_tokens)

    out = await MatchExplainer(_NoStructured(), model="fake").explain(
        job_title="Staff Engineer", company=None, result=_score_result()
    )
    assert out is None


async def test_write_returns_empty_from_fake_provider():
    gaps = [GapDraft(skill_id="a", slug="rust", label="Rust", severity="critical")]
    out = await GapRationaleWriter(FakeLLMProvider(), model="fake").write(
        job_title="Staff Engineer", gaps=gaps
    )
    assert out == {}


async def test_write_returns_rationales_from_canned_subclass():
    provider = _canned(
        {"rationales": {"Rust": "Core to the serving layer.", "Ghost": "not requested"}}
    )
    gaps = [
        GapDraft(skill_id="a", slug="rust", label="Rust", severity="critical"),
        GapDraft(skill_id="b", slug="go", label="Go", severity="important"),
    ]
    out = await GapRationaleWriter(provider(), model="fake").write(
        job_title="Staff Engineer", gaps=gaps
    )
    assert out == {"Rust": "Core to the serving layer."}


async def test_write_returns_empty_for_no_gaps():
    out = await GapRationaleWriter(FakeLLMProvider(), model="fake").write(
        job_title="Staff Engineer", gaps=[]
    )
    assert out == {}


class _Boom(FakeLLMProvider):
    async def complete(self, messages, *, schema=None, max_tokens=1024, temperature=0.2):
        raise RuntimeError("transport blew up")


async def test_explain_returns_none_when_provider_raises():
    out = await MatchExplainer(_Boom(), model="fake").explain(
        job_title="Staff Engineer", company="Acme", result=_score_result()
    )
    assert out is None


async def test_write_returns_empty_when_provider_raises():
    gaps = [GapDraft(skill_id="a", slug="rust", label="Rust", severity="critical")]
    out = await GapRationaleWriter(_Boom(), model="fake").write(
        job_title="Staff Engineer", gaps=gaps
    )
    assert out == {}
