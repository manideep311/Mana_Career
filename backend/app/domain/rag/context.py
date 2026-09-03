from __future__ import annotations

from app.domain.rag.types import Citation, RetrievalSource, RetrievedContext, ScoredChunk

DEFAULT_TOKEN_BUDGET = 2000

_OPEN = '<untrusted_data source="{source}" ref="{ref}">'
_CLOSE = "</untrusted_data>"


def _neutralize(text: str) -> str:
    return text.replace("<untrusted_data", "‹untrusted_data").replace(  # noqa: RUF001
        "untrusted_data>", "untrusted_data›"  # noqa: RUF001
    )


def _render_block(chunk: ScoredChunk) -> str:
    head = _OPEN.format(source=chunk.source.value, ref=chunk.ref_id)
    return f"{head}\n{_neutralize(chunk.content)}\n{_CLOSE}"


def assemble_context(
    chunks: list[ScoredChunk],
    *,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    query: str,
) -> RetrievedContext:
    selected: list[ScoredChunk] = []
    running = 0
    for chunk in chunks:
        if not selected:
            selected.append(chunk)
            running += chunk.token_count
            continue
        if running + chunk.token_count > token_budget:
            break
        selected.append(chunk)
        running += chunk.token_count

    text = "\n\n".join(_render_block(c) for c in selected)
    citations = tuple(
        Citation(ref_id=c.ref_id, source=c.source.value, section=c.section, score=c.rrf_score)
        for c in selected
    )
    return RetrievedContext(
        blocks=tuple(selected),
        text=text,
        citations=citations,
        total_tokens=running,
        query=query,
    )


__all__ = ["DEFAULT_TOKEN_BUDGET", "RetrievalSource", "assemble_context"]
