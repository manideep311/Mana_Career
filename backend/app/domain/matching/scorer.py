"""Pure, deterministic 10-dimension match scorer.

``score(profile, job)`` returns a byte-identical :class:`ScoreResult` for
identical inputs: no DB, no LLM, no I/O, no wall-clock -- stdlib only, plus the
sibling constant table in :mod:`app.domain.matching.weights`.
"""

import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Any

from app.domain.matching.weights import SCORER_VERSION, SENIORITY_LADDER, WEIGHTS, band_for

# (raw_score in [0, 1], detail, evidence) -- what every dimension helper returns.
DimResult = tuple[float, dict[str, Any], list[dict[str, Any]]]


@dataclass(frozen=True)
class ProfileSnapshot:
    skill_ids: frozenset[str]
    skill_labels: tuple[str, ...]
    tech: frozenset[str]
    titles: tuple[str, ...]
    project_tech: frozenset[str]
    has_degree: bool
    fields: tuple[str, ...]
    seniority: str | None
    years_experience: float | None
    preferred_roles: tuple[str, ...]
    locations: tuple[str, ...]
    work_modes: frozenset[str]
    salary_min: int | None
    summary_text: str


@dataclass(frozen=True)
class JobSnapshot:
    required: tuple[tuple[str, float], ...]
    preferred: tuple[tuple[str, float], ...]
    skill_labels: tuple[str, ...]
    title: str
    seniority: str | None
    exp_min: int | None
    exp_max: int | None
    location: str | None
    work_mode: str | None
    salary_min: int | None
    salary_max: int | None
    chunk_embeddings: tuple[tuple[float, ...], ...]


@dataclass(frozen=True)
class Component:
    dimension: str
    raw_score: float
    weight: float
    contribution: float
    detail: dict[str, Any]
    evidence: list[dict[str, Any]]


@dataclass(frozen=True)
class ScoreResult:
    score: float
    band: str
    components: tuple[Component, ...]
    dimension_scores: dict[str, float]
    strengths: list[dict[str, Any]]
    gaps: list[dict[str, Any]]
    inputs_hash: str


# --------------------------------------------------------------------------- #
# token helpers
# --------------------------------------------------------------------------- #
def _tokens(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9+#.]+", s.lower()))


def _label_tokens(labels: tuple[str, ...]) -> set[str]:
    toks: set[str] = set()
    for label in labels:
        toks |= _tokens(label)
    return toks


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _best_jaccard(target: set[str], candidates: tuple[str, ...]) -> float:
    best = 0.0
    for cand in candidates:
        best = max(best, _jaccard(target, _tokens(cand)))
    return best


def _cosine(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    dot = sum((x * y for x, y in zip(a, b, strict=False)), 0.0)
    norm_a = math.sqrt(sum((x * x for x in a), 0.0))
    norm_b = math.sqrt(sum((y * y for y in b), 0.0))
    return dot / (norm_a * norm_b or 1.0)


# --------------------------------------------------------------------------- #
# dimensions -- each returns (raw_score, detail, evidence)
# --------------------------------------------------------------------------- #
def _dim_skill(profile: ProfileSnapshot, job: JobSnapshot) -> DimResult:
    matched = [sid for sid, _ in job.required if sid in profile.skill_ids]
    missing = [sid for sid, _ in job.required if sid not in profile.skill_ids]
    detail: dict[str, Any] = {"matched": matched, "missing": missing}
    evidence: list[dict[str, Any]] = [
        {"kind": "profile_skill", "ref_id": sid, "snippet": ""} for sid in matched
    ]
    pref_hits = sum(sid in profile.skill_ids for sid, _ in job.preferred)
    if job.required:
        covered = sum((w for sid, w in job.required if sid in profile.skill_ids), 0.0)
        total = sum((w for _, w in job.required), 0.0) or 1.0
        pref_bonus = 0.3 * pref_hits / (len(job.preferred) or 1)
        raw = min(1.0, covered / total + pref_bonus)
    elif not job.preferred:
        raw = 1.0
    else:
        raw = 0.3 * (pref_hits / len(job.preferred))
    return raw, detail, evidence


def _dim_experience(profile: ProfileSnapshot, job: JobSnapshot) -> DimResult:
    if job.exp_min is None:
        years_part = 1.0
    elif profile.years_experience is None:
        years_part = 0.5
    elif profile.years_experience >= job.exp_min:
        years_part = 1.0
    else:
        years_part = max(0.0, profile.years_experience / job.exp_min)
    title_part = _best_jaccard(_tokens(job.title), profile.titles)
    raw = 0.6 * years_part + 0.4 * title_part
    detail: dict[str, Any] = {
        "years_part": round(years_part, 3),
        "title_part": round(title_part, 3),
        "job_exp_min": job.exp_min,
        "profile_years": profile.years_experience,
    }
    return raw, detail, []


def _dim_technology(profile: ProfileSnapshot, job: JobSnapshot) -> DimResult:
    job_toks = _label_tokens(job.skill_labels)
    prof_toks = profile.tech
    overlap = job_toks & prof_toks
    raw = len(overlap) / (len(job_toks) or 1)
    detail: dict[str, Any] = {
        "overlap": sorted(overlap),
        "job_only": sorted(job_toks - prof_toks),
    }
    return raw, detail, []


def _dim_semantic(
    profile_embedding: tuple[float, ...] | None, job: JobSnapshot
) -> DimResult:
    if profile_embedding is None or not job.chunk_embeddings:
        return 0.5, {"reason": "no embeddings"}, []
    width = len(job.chunk_embeddings[0])
    count = len(job.chunk_embeddings)
    mean_vec = tuple(
        sum((vec[i] for vec in job.chunk_embeddings), 0.0) / count for i in range(width)
    )
    raw = max(0.0, min(1.0, _cosine(profile_embedding, mean_vec)))
    detail: dict[str, Any] = {"chunks": count}
    return raw, detail, []


def _dim_role(profile: ProfileSnapshot, job: JobSnapshot) -> DimResult:
    detail: dict[str, Any] = {
        "job_title": job.title,
        "preferred_roles": list(profile.preferred_roles),
    }
    if not profile.preferred_roles:
        return 0.5, detail, []
    raw = _best_jaccard(_tokens(job.title), profile.preferred_roles)
    return raw, detail, []


def _dim_seniority(profile: ProfileSnapshot, job: JobSnapshot) -> DimResult:
    detail: dict[str, Any] = {"job": job.seniority, "profile": profile.seniority}
    if job.seniority is None or profile.seniority is None:
        return 0.5, detail, []
    pj = SENIORITY_LADDER.get(job.seniority, 2)
    pp = SENIORITY_LADDER.get(profile.seniority, 2)
    raw = max(0.0, 1.0 - abs(pj - pp) / 5.0)
    return raw, detail, []


def _dim_project(profile: ProfileSnapshot, job: JobSnapshot) -> DimResult:
    if not job.skill_labels:
        return 0.5, {"project_tech_overlap": []}, []
    job_toks = _label_tokens(job.skill_labels)
    overlap = profile.project_tech & job_toks
    if overlap:
        raw = 1.0
    elif profile.project_tech:
        raw = 0.4
    else:
        raw = 0.0
    detail: dict[str, Any] = {"project_tech_overlap": sorted(overlap)}
    return raw, detail, []


def _dim_education(profile: ProfileSnapshot, job: JobSnapshot) -> DimResult:
    raw = 0.6 if profile.has_degree else 0.2
    if _label_tokens(profile.fields) & _tokens(job.title):
        raw = min(1.0, raw + 0.4)
    detail: dict[str, Any] = {"has_degree": profile.has_degree}
    return raw, detail, []


def _dim_location(profile: ProfileSnapshot, job: JobSnapshot) -> DimResult:
    mode, loc = job.work_mode, job.location
    detail: dict[str, Any] = {
        "job_work_mode": mode,
        "job_location": loc,
        "profile_work_modes": sorted(profile.work_modes),
    }
    if mode == "remote":
        raw = 1.0
    elif mode and mode in profile.work_modes:
        raw = 1.0
    elif loc and any(p and (p in loc or loc in p) for p in profile.locations):
        raw = 1.0
    elif not mode and not loc:
        raw = 0.5
    else:
        raw = 0.3
    return raw, detail, []


def _dim_salary(profile: ProfileSnapshot, job: JobSnapshot) -> DimResult:
    detail: dict[str, Any] = {
        "job_max": job.salary_max,
        "job_min": job.salary_min,
        "profile_min": profile.salary_min,
    }
    floor = profile.salary_min
    if floor is None or (job.salary_min is None and job.salary_max is None):
        return 0.5, detail, []
    job_top = job.salary_max if job.salary_max is not None else job.salary_min
    if job_top is None:
        return 0.5, detail, []
    raw = 1.0 if job_top >= floor else max(0.0, job_top / floor)
    return raw, detail, []


# --------------------------------------------------------------------------- #
# aggregation
# --------------------------------------------------------------------------- #
def score(
    profile: ProfileSnapshot,
    job: JobSnapshot,
    *,
    profile_embedding: tuple[float, ...] | None = None,
) -> ScoreResult:
    results: dict[str, DimResult] = {
        "skill": _dim_skill(profile, job),
        "experience": _dim_experience(profile, job),
        "technology": _dim_technology(profile, job),
        "semantic": _dim_semantic(profile_embedding, job),
        "role": _dim_role(profile, job),
        "seniority": _dim_seniority(profile, job),
        "project": _dim_project(profile, job),
        "education": _dim_education(profile, job),
        "location": _dim_location(profile, job),
        "salary": _dim_salary(profile, job),
    }
    components: list[Component] = []
    for dim in WEIGHTS:
        raw, detail, evidence = results[dim]
        components.append(
            Component(
                dimension=dim,
                raw_score=round(raw, 3),
                weight=WEIGHTS[dim],
                contribution=round(raw * WEIGHTS[dim] * 100, 2),
                detail=detail,
                evidence=evidence,
            )
        )
    total = round(sum((c.contribution for c in components), 0.0), 2)

    strength_rows: list[dict[str, Any]] = [
        {"dimension": c.dimension, "raw_score": c.raw_score, "contribution": c.contribution}
        for c in components
        if c.raw_score >= 0.7
    ]
    strengths = sorted(strength_rows, key=lambda d: d["contribution"], reverse=True)[:3]

    gap_rows: list[dict[str, Any]] = [
        {"dimension": c.dimension, "raw_score": c.raw_score, "weight": c.weight}
        for c in components
        if c.raw_score < 0.5
    ]
    gaps = sorted(gap_rows, key=lambda d: d["weight"], reverse=True)[:4]

    return ScoreResult(
        score=total,
        band=band_for(total),
        components=tuple(components),
        dimension_scores={c.dimension: c.raw_score for c in components},
        strengths=strengths,
        gaps=gaps,
        inputs_hash=inputs_hash(profile, job),
    )


# --------------------------------------------------------------------------- #
# inputs hash -- stable cache key over the snapshot fields + scorer version
# --------------------------------------------------------------------------- #
def _profile_canonical(p: ProfileSnapshot) -> dict[str, Any]:
    return {
        "skill_ids": sorted(p.skill_ids),
        "skill_labels": list(p.skill_labels),
        "tech": sorted(p.tech),
        "titles": list(p.titles),
        "project_tech": sorted(p.project_tech),
        "has_degree": p.has_degree,
        "fields": list(p.fields),
        "seniority": p.seniority,
        "years_experience": p.years_experience,
        "preferred_roles": list(p.preferred_roles),
        "locations": list(p.locations),
        "work_modes": sorted(p.work_modes),
        "salary_min": p.salary_min,
        "summary_text": p.summary_text,
    }


def _job_canonical(j: JobSnapshot) -> dict[str, Any]:
    return {
        "required": [[sid, w] for sid, w in j.required],
        "preferred": [[sid, w] for sid, w in j.preferred],
        "skill_labels": list(j.skill_labels),
        "title": j.title,
        "seniority": j.seniority,
        "exp_min": j.exp_min,
        "exp_max": j.exp_max,
        "location": j.location,
        "work_mode": j.work_mode,
        "salary_min": j.salary_min,
        "salary_max": j.salary_max,
        "chunk_embeddings": [list(v) for v in j.chunk_embeddings],
    }


def inputs_hash(profile: ProfileSnapshot, job: JobSnapshot) -> str:
    payload = {
        "profile": _profile_canonical(profile),
        "job": _job_canonical(job),
        "scorer_version": SCORER_VERSION,
    }
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()
