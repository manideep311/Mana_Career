from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from app.domain.agents.budget import check_budget

if TYPE_CHECKING:
    from app.domain.agents.state import ManaState


@dataclass(frozen=True)
class ToolSpec:
    name: str
    side_effecting: bool
    cap_key: str | None


TOOL_SPECS: dict[str, ToolSpec] = {
    "vector_search": ToolSpec("vector_search", False, "vector_search"),
    "web_search": ToolSpec("web_search", False, "web_search"),
    "parse_pdf": ToolSpec("parse_pdf", False, None),
}


def tool_key(name: str, args: dict[str, Any]) -> str:
    """Stable content hash for a tool invocation, used as the dedup-cache key."""
    return hashlib.sha256(
        f"{name}:{json.dumps(args, sort_keys=True, default=str)}".encode()
    ).hexdigest()


async def call_tool(
    state: ManaState,
    spec: ToolSpec,
    args: dict[str, Any],
    fn: Callable[..., Awaitable[Any]],
    *,
    now: float | None = None,
) -> tuple[Any, Literal["ok", "deduped"]]:
    """Run ``fn(**args)`` once per identical call, enforcing the per-tool cap.

    Dedup is checked before the cap and before the ``tool_calls_made`` bump, so a
    repeat call returns the cached result without consuming budget. The cap check
    (:func:`check_budget`) may raise :class:`BudgetExceeded`, which propagates to
    the caller / ``guard`` wrapper.
    """
    key = tool_key(spec.name, args)
    cache = state.setdefault("tool_cache", {})
    if key in cache:
        return cache[key], "deduped"

    if spec.cap_key:
        check_budget(state["budget"], now=now or time.time(), tool=spec.cap_key)

    result = await fn(**args)

    cache[key] = result
    if spec.cap_key:
        made = state["budget"]["tool_calls_made"]
        made[spec.cap_key] = made.get(spec.cap_key, 0) + 1
    return result, "ok"
