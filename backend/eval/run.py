from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

from app.core.db import AsyncSessionLocal
from eval.suites.generation import GenerationEvalReport, run_generation_suite
from eval.suites.retrieval import EvalReport, run_retrieval_suite
from eval.thresholds import (
    GROUNDEDNESS_FLOOR,
    KEYWORD_COVERAGE_FLOOR,
    MRR,
    NDCG_AT_10,
    QUALITY_GROUNDEDNESS,
    QUALITY_KEYWORD_COVERAGE,
    QUALITY_MRR,
    QUALITY_NDCG_AT_10,
    QUALITY_RECALL_AT_10,
    RECALL_AT_10,
)


async def _amain(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="eval.run")
    parser.add_argument("suite", choices=["retrieval", "generation"])
    parser.add_argument("--provider", default=os.environ.get("EMBEDDINGS_PROVIDER", "fake"))
    parser.add_argument("--write-db", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    git_sha = os.environ.get("GITHUB_SHA", "dev")[:40]
    report: EvalReport | GenerationEvalReport
    async with AsyncSessionLocal() as session:
        if args.suite == "retrieval":
            report = await run_retrieval_suite(
                session, provider=args.provider, write_db=args.write_db, git_sha=git_sha
            )
        else:
            report = await run_generation_suite(
                session, llm_provider=args.provider, write_db=args.write_db, git_sha=git_sha
            )
        if args.write_db:
            await session.commit()

    if args.suite == "retrieval":
        quality = args.provider == "voyage"
        floors = {
            "recall_at_10": QUALITY_RECALL_AT_10 if quality else RECALL_AT_10,
            "mrr": QUALITY_MRR if quality else MRR,
            "ndcg_at_10": QUALITY_NDCG_AT_10 if quality else NDCG_AT_10,
        }
    else:
        quality = args.provider not in {"fake", ""}
        floors = {
            "groundedness": QUALITY_GROUNDEDNESS if quality else GROUNDEDNESS_FLOOR,
            "keyword_coverage": QUALITY_KEYWORD_COVERAGE if quality else KEYWORD_COVERAGE_FLOOR,
        }
    print(f"{'metric':<16} {'value':>8} {'threshold':>10} {'pass':>6}")
    for name, floor in floors.items():
        v = report.aggregate[name]
        print(f"{name:<16} {v:>8.3f} {floor:>10.3f} {('yes' if v >= floor else 'NO'):>6}")
    for name, v in report.aggregate.items():
        if name not in floors:
            print(f"{name:<16} {v:>8.3f} {'-':>10} {'-':>6}")
    if args.as_json:
        print(json.dumps({"aggregate": report.aggregate, "passed": report.passed}))
    return 0 if report.passed else 1


def main() -> None:
    sys.exit(asyncio.run(_amain(sys.argv[1:])))


if __name__ == "__main__":
    main()
