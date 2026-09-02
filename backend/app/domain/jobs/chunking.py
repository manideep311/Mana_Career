from __future__ import annotations

from dataclasses import dataclass

from app.domain.jobs.extractor import JobExtraction

_SECTIONS = ("description", "responsibilities", "requirements")


@dataclass(frozen=True)
class JobChunkDraft:
    section: str
    chunk_index: int
    content: str
    token_count: int


def estimate_tokens(text: str) -> int:
    return len(text.split())


def _section_text(extraction: JobExtraction, section: str) -> str:
    if section == "description":
        return (extraction.description or "").strip()
    if section == "responsibilities":
        return "\n".join(f"- {r}" for r in extraction.responsibilities if r.strip()).strip()
    lines = [f"Required: {s.raw} ({s.weight:.2f})" for s in extraction.required_skills]
    lines += [f"Preferred: {s.raw} ({s.weight:.2f})" for s in extraction.preferred_skills]
    return "\n".join(lines).strip()


def _windows(text: str, *, max_tokens: int, overlap: int) -> list[str]:
    words = text.split()
    if len(words) <= max_tokens:
        return [text] if text else []
    step = max(1, max_tokens - overlap)
    return [" ".join(words[i : i + max_tokens]) for i in range(0, len(words), step)]


def chunk_job(
    extraction: JobExtraction, *, max_tokens: int = 350, overlap: int = 40
) -> list[JobChunkDraft]:
    drafts: list[JobChunkDraft] = []
    idx = 0
    for section in _SECTIONS:
        text = _section_text(extraction, section)
        if not text:
            continue
        for window in _windows(text, max_tokens=max_tokens, overlap=overlap):
            drafts.append(
                JobChunkDraft(
                    section=section,
                    chunk_index=idx,
                    content=window,
                    token_count=estimate_tokens(window),
                )
            )
            idx += 1
    return drafts
