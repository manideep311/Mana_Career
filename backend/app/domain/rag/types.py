from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RetrievalSource(StrEnum):
    JOB_CHUNKS = "job_chunks"
    # RESUME_CHUNKS = "resume_chunks"          # later
    # COMPANY_RESEARCH = "company_research"    # Phase 7
    # LEARNING_RESOURCES = "learning_resources"  # Phase 12


@dataclass(frozen=True)
class ScoredChunk:
    ref_id: str  # "<job_id>:<chunk_index>"
    source: RetrievalSource
    section: str
    content: str
    token_count: int
    embedding: tuple[float, ...] | None
    vector_rank: int | None
    text_rank: int | None
    rrf_score: float
    mmr_score: float | None


@dataclass(frozen=True)
class Citation:
    ref_id: str
    source: str
    section: str
    score: float


@dataclass(frozen=True)
class RetrievedContext:
    blocks: tuple[ScoredChunk, ...]
    text: str
    citations: tuple[Citation, ...]
    total_tokens: int
    query: str
