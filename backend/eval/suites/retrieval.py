"""Retrieval eval suite: score ``RagService`` against a hand-authored golden set.

The golden set (``datasets/retrieval/golden_v1.jsonl``) is labelled conservatively
so the lexical (``tsv``) arm alone clears the CI thresholds under the ``fake``
embeddings provider -- every ``relevant`` ref is a chunk whose text literally
contains all of its query's terms. See ``thresholds.py`` for the floors.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.embeddings.factory import get_embeddings_provider
from app.domain.rag.service import RagService
from app.domain.rag.types import RetrievalSource
from app.models.eval import EvalResult, EvalRun
from app.models.job import Job, JobChunk
from app.models.user import User
from app.seed import seed_jobs, seed_skills
from eval.metrics import mrr, ndcg_at_k, precision_at_k, recall_at_k
from eval.thresholds import (
    MRR,
    NDCG_AT_10,
    QUALITY_MRR,
    QUALITY_NDCG_AT_10,
    QUALITY_RECALL_AT_10,
    RECALL_AT_10,
)

GOLDEN_PATH = Path(__file__).parent.parent / "datasets" / "retrieval" / "golden_v1.jsonl"
EVAL_USER_EMAIL = "eval-runner@mana.internal"


@dataclass
class CaseScore:
    case_id: str
    recall_at_5: float
    recall_at_10: float
    precision_at_5: float
    mrr: float
    ndcg_at_10: float
    passed: bool
    retrieved: list[str]
    relevant: list[str]


@dataclass
class EvalReport:
    aggregate: dict[str, float]
    cases: list[CaseScore]
    passed: bool


def load_golden() -> list[dict[str, Any]]:
    """Parse ``GOLDEN_PATH`` -- one JSON object per non-blank line."""
    lines = GOLDEN_PATH.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


async def ensure_corpus(session: AsyncSession, provider_name: str) -> uuid.UUID:
    """Seed skills + jobs, get-or-create the eval user, backfill any NULL chunk
    embeddings, and return the eval user's id.

    With ``fake`` this is deterministic and a re-run is a no-op: ``seed_jobs``
    already embeds every chunk, so the backfill loop finds nothing.
    """
    del provider_name  # embeddings come from get_settings(); kept for call-site symmetry

    await seed_skills(session)
    await seed_jobs(session)

    provider = get_embeddings_provider(get_settings())

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

    pending = list(
        (
            await session.execute(select(JobChunk).where(JobChunk.embedding.is_(None)))
        ).scalars()
    )
    if pending:
        vectors = await provider.embed_documents([c.content for c in pending])
        for chunk, vec in zip(pending, vectors, strict=True):
            chunk.embedding = vec

    await session.flush()
    return user.id


async def run_retrieval_suite(
    session: AsyncSession, *, provider: str, write_db: bool, git_sha: str
) -> EvalReport:
    user_id = await ensure_corpus(session, provider)
    settings = get_settings()

    key_to_id: dict[str, uuid.UUID] = {
        source_ref: job_id
        for source_ref, job_id in (
            await session.execute(
                select(Job.source_ref, Job.id).where(Job.is_seed.is_(True))
            )
        ).all()
    }

    is_quality = provider == "voyage"
    case_recall_floor = QUALITY_RECALL_AT_10 if is_quality else RECALL_AT_10
    rag = RagService(session, get_embeddings_provider(settings))

    golden = load_golden()
    cases: list[CaseScore] = []
    for case in golden:
        relevant = {
            f"{key_to_id[k.split(':')[0]]}:{k.split(':')[1]}" for k in case["relevant"]
        }
        ctx = await rag.retrieve(
            case["query"],
            source=RetrievalSource.JOB_CHUNKS,
            user_id=user_id,
            k=10,
            token_budget=100_000,
        )
        retrieved = [b.ref_id for b in ctx.blocks]
        recall5 = recall_at_k(retrieved, relevant, 5)
        recall10 = recall_at_k(retrieved, relevant, 10)
        precision5 = precision_at_k(retrieved, relevant, 5)
        rr = mrr(retrieved, relevant)
        ndcg10 = ndcg_at_k(retrieved, relevant, 10)
        cases.append(
            CaseScore(
                case_id=case["id"],
                recall_at_5=recall5,
                recall_at_10=recall10,
                precision_at_5=precision5,
                mrr=rr,
                ndcg_at_10=ndcg10,
                passed=recall10 >= case_recall_floor,
                retrieved=retrieved,
                relevant=sorted(relevant),
            )
        )

    n = len(cases) or 1
    aggregate = {
        "recall_at_5": sum(c.recall_at_5 for c in cases) / n,
        "recall_at_10": sum(c.recall_at_10 for c in cases) / n,
        "precision_at_5": sum(c.precision_at_5 for c in cases) / n,
        "mrr": sum(c.mrr for c in cases) / n,
        "ndcg_at_10": sum(c.ndcg_at_10 for c in cases) / n,
    }

    recall_floor = QUALITY_RECALL_AT_10 if is_quality else RECALL_AT_10
    mrr_floor = QUALITY_MRR if is_quality else MRR
    ndcg_floor = QUALITY_NDCG_AT_10 if is_quality else NDCG_AT_10
    report_passed = (
        aggregate["recall_at_10"] >= recall_floor
        and aggregate["mrr"] >= mrr_floor
        and aggregate["ndcg_at_10"] >= ndcg_floor
    )

    if write_db:
        now = datetime.now(tz=UTC)
        run = EvalRun(
            suite="retrieval",
            dataset_ref="datasets/retrieval/golden_v1.jsonl",
            dataset_version="v1",
            git_sha=git_sha,
            provider=provider,
            model_ids={"embed": settings.embed_model},
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
                    input={"query": case["query"]},
                    expected={"relevant": score.relevant},
                    actual={"retrieved": score.retrieved},
                    scores={
                        "recall_at_5": score.recall_at_5,
                        "recall_at_10": score.recall_at_10,
                        "precision_at_5": score.precision_at_5,
                        "mrr": score.mrr,
                        "ndcg_at_10": score.ndcg_at_10,
                    },
                    passed=score.passed,
                    judge_meta={},
                )
            )
        await session.flush()

    return EvalReport(aggregate=aggregate, cases=cases, passed=report_passed)
