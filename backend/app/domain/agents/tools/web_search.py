from __future__ import annotations

from typing import Any

from app.domain.agents.search.provider import SearchProvider
from app.domain.rag.context import _neutralize

_FENCE = '<untrusted_data source="web" ref="{ref}">\n{body}\n</untrusted_data>'


async def web_search(
    *, provider: SearchProvider, query: str, k: int = 5
) -> list[dict[str, Any]]:
    """Run ``query`` through the :class:`SearchProvider` seam and fence each hit.

    Every result's scraped text is neutralized (fence markers defanged) and
    clamped to 1200 chars, then wrapped in an ``<untrusted_data source="web">``
    block so downstream LLM prompts cannot be hijacked by scraped content.
    No persistence in Phase 7a -- ``company_research`` storage lands with
    ``enrich_job`` later.
    """
    hits = await provider.search(query, k=k)
    out: list[dict[str, Any]] = []
    for i, h in enumerate(hits):
        body = _neutralize(h["content"])[:1200]
        source = _neutralize(
            "\n".join(
                (
                    f"Title: {h['title']}",
                    f"URL: {h['url']}",
                    f"Published: {h.get('published_date') or 'unknown'}",
                    f"Retrieved: {h.get('retrieved_at') or 'unknown'}",
                )
            )
        )[:600]
        fenced = _FENCE.format(ref=f"web:{i}", body=f"{source}\n\n{body}")
        out.append(
            {
                "ref": f"web:{i}",
                "url": h["url"],
                "title": h["title"],
                "published_date": h.get("published_date"),
                "retrieved_at": h.get("retrieved_at"),
                "fenced": fenced,
            }
        )
    return out
