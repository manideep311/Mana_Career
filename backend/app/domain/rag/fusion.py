from __future__ import annotations

import math

from app.domain.rag.types import ScoredChunk

RRF_K = 60
MMR_LAMBDA = 0.7


def rrf(*ranked: list[str], k: int = RRF_K) -> dict[str, float]:
    scores: dict[str, float] = {}
    for lst in ranked:
        for rank, ref_id in enumerate(lst, start=1):
            scores[ref_id] = scores.get(ref_id, 0.0) + 1.0 / (k + rank)
    return scores


def _cosine(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def mmr(
    candidates: list[ScoredChunk], *, lambda_: float = MMR_LAMBDA, k: int
) -> list[ScoredChunk]:
    if not candidates:
        return []
    rels = [c.rrf_score for c in candidates]
    lo, hi = min(rels), max(rels)
    span = hi - lo
    norm = {
        c.ref_id: (1.0 if span == 0.0 else (c.rrf_score - lo) / span) for c in candidates
    }

    remaining = list(candidates)
    selected: list[ScoredChunk] = []
    while remaining and len(selected) < k:
        best: ScoredChunk | None = None
        best_val = -math.inf
        for cand in remaining:
            if cand.embedding is None or not selected:
                redundancy = 0.0
            else:
                redundancy = max(
                    (
                        _cosine(cand.embedding, s.embedding)
                        if s.embedding is not None
                        else 0.0
                    )
                    for s in selected
                )
            val = lambda_ * norm[cand.ref_id] - (1.0 - lambda_) * redundancy
            better = val > best_val or (
                val == best_val
                and best is not None
                and (
                    cand.rrf_score > best.rrf_score
                    or (cand.rrf_score == best.rrf_score and cand.ref_id < best.ref_id)
                )
            )
            if best is None or better:
                best, best_val = cand, val
        assert best is not None
        remaining.remove(best)
        selected.append(
            ScoredChunk(
                ref_id=best.ref_id, source=best.source, section=best.section,
                content=best.content, token_count=best.token_count,
                embedding=best.embedding, vector_rank=best.vector_rank,
                text_rank=best.text_rank, rrf_score=best.rrf_score, mmr_score=best_val,
            )
        )
    return selected
