"""Place roadmap milestones on a simple timeline: now, the next 30 days,
the 60-90 days after that, and later.

Timing comes from each milestone's estimated hours at a stated weekly pace
(5 hours a week unless the roadmap was created with ``hours_per_week``).
It is a planning aid, not a promise, and the API says which pace it assumed.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

Phase = Literal["done", "current", "next_30", "next_60_90", "later"]

DEFAULT_HOURS_PER_WEEK = 5
DEFAULT_MILESTONE_HOURS = 8
_WEEKS_30 = 30 / 7
_WEEKS_90 = 90 / 7


@dataclass(frozen=True)
class MilestoneTiming:
    id: uuid.UUID
    est_hours: int | None
    status: str


def hours_per_week(constraints: Mapping[str, Any] | None) -> int:
    raw = (constraints or {}).get("hours_per_week")
    try:
        value = int(raw) if raw is not None else DEFAULT_HOURS_PER_WEEK
    except (TypeError, ValueError):
        value = DEFAULT_HOURS_PER_WEEK
    return max(1, min(value, 40))


def assign_phases(
    milestones: Sequence[MilestoneTiming], *, weekly_hours: int
) -> dict[uuid.UUID, Phase]:
    """Done stays done; the first open milestone (or the one in progress) is
    current; the rest fall into windows by cumulative hours from today."""
    phases: dict[uuid.UUID, Phase] = {}
    open_ = [m for m in milestones if m.status != "done"]
    current = next((m for m in open_ if m.status == "in_progress"), open_[0] if open_ else None)
    budget_30 = weekly_hours * _WEEKS_30
    budget_90 = weekly_hours * _WEEKS_90
    elapsed = 0.0
    for m in milestones:
        if m.status == "done":
            phases[m.id] = "done"
            continue
        start = elapsed
        elapsed += m.est_hours or DEFAULT_MILESTONE_HOURS
        if m is current:
            phases[m.id] = "current"
        elif start < budget_30:
            phases[m.id] = "next_30"
        elif start < budget_90:
            phases[m.id] = "next_60_90"
        else:
            phases[m.id] = "later"
    return phases
