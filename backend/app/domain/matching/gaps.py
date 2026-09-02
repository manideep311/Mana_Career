"""Deterministic skill-gap derivation from the scorer's ``skill`` component.

Pure function, stdlib only: given a job's required/preferred skill rows and the
``skill`` :class:`~app.domain.matching.scorer.Component` (whose ``detail`` carries
``matched`` / ``missing`` skill-id lists), emit an ordered list of
:class:`GapDraft` rows -- no DB, no LLM, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.domain.matching.scorer import Component

_SEVERITY_ORDER: dict[str, int] = {"critical": 0, "important": 1, "nice_to_have": 2}


@dataclass(frozen=True)
class GapDraft:
    skill_id: str
    slug: str
    label: str
    severity: str  # "critical" | "important" | "nice_to_have"


def derive_gaps(
    job_required: list[dict[str, Any]],
    job_preferred: list[dict[str, Any]],
    skill_component: Component,
) -> list[GapDraft]:
    """Turn the ``skill`` component's ``missing`` set into ordered gap drafts.

    A required skill the profile lacks is ``critical`` when its ``weight`` is
    ``>= 0.7`` and ``important`` otherwise; a preferred skill the profile lacks
    is ``nice_to_have``. Required wins on de-dupe. The result lists every
    ``critical`` first, then ``important``, then ``nice_to_have``; within a
    severity it is sorted by ``label``.
    """
    missing = {str(x) for x in skill_component.detail.get("missing", [])}
    drafts: list[GapDraft] = []
    seen: set[str] = set()

    for entry in job_required:
        skill_id = str(entry["skill_id"])
        if skill_id not in missing or skill_id in seen:
            continue
        seen.add(skill_id)
        severity = "critical" if entry["weight"] >= 0.7 else "important"
        drafts.append(
            GapDraft(
                skill_id=skill_id,
                slug=str(entry["slug"]),
                label=str(entry["label"]),
                severity=severity,
            )
        )

    for entry in job_preferred:
        skill_id = str(entry["skill_id"])
        if skill_id not in missing or skill_id in seen:
            continue
        seen.add(skill_id)
        drafts.append(
            GapDraft(
                skill_id=skill_id,
                slug=str(entry["slug"]),
                label=str(entry["label"]),
                severity="nice_to_have",
            )
        )

    drafts.sort(key=lambda g: (_SEVERITY_ORDER[g.severity], g.label))
    return drafts
