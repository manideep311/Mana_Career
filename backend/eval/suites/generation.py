"""Generation eval suite: score write_cover_letter + draft_email against a
hand-authored golden set.

Under ``LLM_PROVIDER=fake`` every generated field is empty (see
``FakeLLMProvider``), so the deterministic metrics trivially clear their
default-tier floors (see ``thresholds.py``'s calibration note) -- this suite
proves the pipeline runs end to end and persists an EvalRun/EvalResult, not
that the writing is any good. The LLM-judge leg runs every time (proving that
plumbing works too) but is never gated in CI (see thresholds.py).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.generation.cover_letter import write_cover_letter
from app.domain.generation.email_draft import draft_email
from app.domain.generation.service import GenerationService
from app.domain.llm.factory import get_llm_provider
from app.domain.resume.extractor import ResumeExtraction
from app.models.eval import EvalResult, EvalRun
from app.models.user import User
from eval.thresholds import (
    GROUNDEDNESS_FLOOR,
    KEYWORD_COVERAGE_FLOOR,
    QUALITY_GROUNDEDNESS,
    QUALITY_KEYWORD_COVERAGE,
)

GOLDEN_PATH = Path(__file__).parent.parent / "datasets" / "generation" / "golden_v1.jsonl"
EVAL_USER_EMAIL = "eval-runner@mana.internal"


class _JudgeVerdict(BaseModel):
    score: float
    rationale: str


@dataclass
class CaseScore:
    case_id: str
    groundedness: float
    keyword_coverage: float
    judge_score: float
    passed: bool


@dataclass
class GenerationEvalReport:
    aggregate: dict[str, float]
    cases: list[CaseScore]
    passed: bool


def load_golden() -> list[dict[str, Any]]:
    lines = GOLDEN_PATH.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


async def ensure_eval_user(session: AsyncSession) -> User:
    user = (
        await session.execute(select(User).where(User.email == EVAL_USER_EMAIL))
    ).scalar_one_or_none()
    if user is None:
        user = User(
            email=EVAL_USER_EMAIL,
            password_hash="x",  # noqa: S106  eval user never authenticates
            full_name="Eval Runner",
        )
        session.add(user)
        await session.flush()
    return user


async def run_generation_suite(
    session: AsyncSession, *, llm_provider: str, write_db: bool, git_sha: str
) -> GenerationEvalReport:
    await ensure_eval_user(session)
    llm = get_llm_provider(get_settings())
    gen = GenerationService(llm)

    golden = load_golden()
    cases: list[CaseScore] = []
    for case in golden:
        resume = ResumeExtraction.model_validate(case["resume"])
        job = case["job"]
        job_brief = f"{job['title']} at {job['company']}\n{job['description']}"

        letter, letter_meta = await write_cover_letter(
            gen=gen, base=resume, profile_summary="", job_brief=job_brief
        )
        email, _email_meta = await draft_email(
            gen=gen, job_title=job["title"], company=job["company"],
            applicant_name=resume.full_name or "", cover_letter_content=letter.content,
        )

        groundedness = letter_meta.claim_validation.get("supported_ratio", 1.0)

        combined = f"{letter.content}\n{email.subject}\n{email.body}".lower()
        expected = case.get("expected_keywords", [])
        matched = [kw for kw in expected if kw.lower() in combined]
        keyword_coverage = len(matched) / len(expected) if expected else 1.0

        judge_res = await gen.generate(
            system="Rate how well this application material fits the job, 0-1.",
            user=f"Job: {job_brief}\n\nCover letter:\n{letter.content}\n\nEmail:\n{email.body}",
            schema=_JudgeVerdict,
            prompt_version="judge-1",
            max_tokens=200,
        )
        verdict = _JudgeVerdict.model_validate(judge_res.structured)

        passed = groundedness >= GROUNDEDNESS_FLOOR and keyword_coverage >= KEYWORD_COVERAGE_FLOOR
        cases.append(
            CaseScore(
                case_id=case["id"],
                groundedness=groundedness,
                keyword_coverage=keyword_coverage,
                judge_score=verdict.score,
                passed=passed,
            )
        )

    n = len(cases) or 1
    aggregate = {
        "groundedness": sum(c.groundedness for c in cases) / n,
        "keyword_coverage": sum(c.keyword_coverage for c in cases) / n,
        "judge_score": sum(c.judge_score for c in cases) / n,
    }
    is_quality = llm_provider not in {"fake", ""}
    groundedness_floor = QUALITY_GROUNDEDNESS if is_quality else GROUNDEDNESS_FLOOR
    coverage_floor = QUALITY_KEYWORD_COVERAGE if is_quality else KEYWORD_COVERAGE_FLOOR
    report_passed = (
        aggregate["groundedness"] >= groundedness_floor
        and aggregate["keyword_coverage"] >= coverage_floor
    )

    if write_db:
        now = datetime.now(tz=UTC)
        run = EvalRun(
            suite="generation",
            dataset_ref="datasets/generation/golden_v1.jsonl",
            dataset_version="v1",
            git_sha=git_sha,
            provider=llm_provider,
            model_ids={},
            config={},
            metrics=aggregate,
            status="passed" if report_passed else "failed",
            started_at=now,
            ended_at=now,
        )
        session.add(run)
        await session.flush()
        for case, score in zip(golden, cases, strict=True):
            session.add(
                EvalResult(
                    eval_run_id=run.id,
                    case_id=score.case_id,
                    input={"job": case["job"]},
                    expected={"expected_keywords": case.get("expected_keywords", [])},
                    actual={
                        "groundedness": score.groundedness,
                        "keyword_coverage": score.keyword_coverage,
                    },
                    scores={
                        "groundedness": score.groundedness,
                        "keyword_coverage": score.keyword_coverage,
                        "judge_score": score.judge_score,
                    },
                    passed=score.passed,
                    judge_meta={"rationale_len": 0},
                )
            )
        await session.flush()

    return GenerationEvalReport(aggregate=aggregate, cases=cases, passed=report_passed)
