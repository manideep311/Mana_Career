"""LLM prose for a match: a narrative and one batched per-gap rationale call.

Both classes mirror :class:`app.domain.jobs.extractor.JobExtractor` in shape but
differ in one contract: these calls are **non-fatal**. They return only prose --
never a number -- and on *any* failure -- a transport/provider exception from
``complete()``, ``result.structured is None``, or an empty payload -- they return
``None`` / ``{}`` rather than raising, so the deterministic score always stands.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.domain.llm.provider import LLMMessage, LLMProvider, LLMResult
from app.domain.matching.gaps import GapDraft
from app.domain.matching.scorer import ScoreResult

log = get_logger("domain.matching.explainer")

EXPLAIN_SYSTEM_PROMPT = (
    "You are handed a pre-computed match score and its component breakdown. "
    "Write 2-4 sentences, plain and specific, explaining why this candidate "
    "profile does or doesn't fit this role. Reference the strongest and weakest "
    "dimensions by name. NEVER state a numeric score, NEVER contradict the "
    "breakdown, NEVER invent facts not in the inputs."
)

RATIONALE_SYSTEM_PROMPT = (
    "For each listed skill, write ONE sentence on why it matters for this "
    "specific role. Return a JSON object mapping the exact skill label to its "
    "sentence. No score, no fluff."
)


class NarrativeOut(BaseModel):
    text: str = ""


class RationalesOut(BaseModel):
    rationales: dict[str, str] = Field(default_factory=dict)


class MatchExplainer:
    def __init__(self, llm: LLMProvider, *, model: str) -> None:
        self._llm = llm
        self._model = model
        self.last_usage: LLMResult | None = None

    async def explain(
        self, *, job_title: str, company: str | None, result: ScoreResult
    ) -> str | None:
        messages: list[LLMMessage] = [
            {"role": "system", "content": EXPLAIN_SYSTEM_PROMPT},
            {"role": "user", "content": _explain_user_message(job_title, company, result)},
        ]
        try:
            llm_result = await self._llm.complete(
                messages, schema=NarrativeOut, max_tokens=512
            )
        except Exception:
            # Non-fatal: a provider/transport failure just means no narrative.
            log.warning("match_explain_failed", exc_info=True)
            return None
        self.last_usage = llm_result
        if llm_result.structured is None:
            return None
        text = str(llm_result.structured.get("text", "")).strip()
        return text or None


class GapRationaleWriter:
    def __init__(self, llm: LLMProvider, *, model: str) -> None:
        self._llm = llm
        self._model = model
        self.last_usage: LLMResult | None = None

    async def write(
        self, *, job_title: str, gaps: list[GapDraft]
    ) -> dict[str, str]:
        if not gaps:
            return {}
        labels = "\n".join(f"- {g.label}" for g in gaps)
        messages: list[LLMMessage] = [
            {"role": "system", "content": RATIONALE_SYSTEM_PROMPT},
            {"role": "user", "content": f"Role: {job_title}\nSkills:\n{labels}"},
        ]
        try:
            llm_result = await self._llm.complete(
                messages, schema=RationalesOut, max_tokens=1024
            )
        except Exception:
            # Non-fatal: a provider/transport failure just means no rationales.
            log.warning("match_rationales_failed", exc_info=True)
            return {}
        self.last_usage = llm_result
        if llm_result.structured is None:
            return {}
        raw = llm_result.structured.get("rationales")
        if not isinstance(raw, dict):
            return {}
        wanted = {g.label for g in gaps}
        out: dict[str, str] = {}
        for label, text in raw.items():
            if label in wanted and isinstance(text, str) and text.strip():
                out[str(label)] = text
        return out


def _explain_user_message(
    job_title: str, company: str | None, result: ScoreResult
) -> str:
    where = f" at {company}" if company else ""
    strengths = ", ".join(str(s["dimension"]) for s in result.strengths) or "none"
    gaps = ", ".join(str(g["dimension"]) for g in result.gaps) or "none"
    scores = ", ".join(
        f"{dim}={val:.2f}" for dim, val in sorted(result.dimension_scores.items())
    )
    return (
        f"Role: {job_title}{where}\n"
        f"Match band: {result.band}\n"
        f"Strongest dimensions: {strengths}\n"
        f"Weakest dimensions: {gaps}\n"
        f"Dimension scores: {scores}"
    )
