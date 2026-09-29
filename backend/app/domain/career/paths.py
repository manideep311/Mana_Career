"""Career paths: which role families your experience points toward, and why.

Pure functions over plain data (the loader in ``service.py`` builds the
inputs). For each role family found in the job catalogue:

- *demand*: the share of the family's roles that ask for a skill (required
  counts 1, preferred 0.5);
- *coverage*: the demand-weighted share of the family's core skills you have;
- *fit*: a description, never a probability ("close fit", "reachable stretch",
  "significant pivot"), adjusted when the roles are well above your level;
- the evidence behind it, what's missing, related paths and concrete actions.

Paths are suggestions to weigh, not verdicts: the copy always says what the
evidence is and lets the person decide.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from statistics import median
from typing import Literal

from app.domain.career.families import Family, family_for

Fit = Literal["close", "stretch", "pivot"]

SENIORITY_RANK = {
    "intern": 0, "junior": 1, "mid": 2, "senior": 3, "staff": 4, "principal": 5,
    "lead": 4, "manager": 4,
}
CORE_SKILLS = 10
_FIT_LABEL = {
    "close": "Close fit",
    "stretch": "Reachable stretch",
    "pivot": "Significant pivot",
}
_FIT_TEXT = {
    "close": "You already cover most of what these roles ask for.",
    "stretch": "A few focused skills stand between you and these roles.",
    "pivot": "This would mean building several new skills and fresh evidence first.",
}


@dataclass(frozen=True)
class JobSkill:
    slug: str
    label: str
    required: bool


@dataclass(frozen=True)
class JobLite:
    id: str
    title: str
    company: str | None
    seniority: str | None
    skills: tuple[JobSkill, ...]


@dataclass(frozen=True)
class CandidateSkill:
    slug: str
    label: str
    category: str
    sources: frozenset[str]  # "profile", "experience", "project", "resume"
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class Candidate:
    skills: dict[str, CandidateSkill]
    titles: tuple[str, ...] = ()
    seniority: str | None = None
    preferred_roles: tuple[str, ...] = ()

    @property
    def target_families(self) -> frozenset[str]:
        return frozenset(family_for(r).slug for r in self.preferred_roles if r.strip())


@dataclass(frozen=True)
class PathSkill:
    slug: str
    label: str
    demand: float  # 0..1 share of the family's roles asking for it
    required: bool  # required (not just preferred) in at least half of those roles
    have: bool
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class PathAction:
    kind: Literal["project", "resume", "apply", "roadmap", "explore"]
    title: str
    detail: str


@dataclass(frozen=True)
class CareerPath:
    slug: str
    title: str
    summary: str
    job_count: int
    stated_target: bool
    coverage: float
    fit: Fit
    fit_label: str
    fit_explanation: str
    why: str
    have: tuple[PathSkill, ...]
    missing: tuple[PathSkill, ...]
    relevant_experience: tuple[str, ...]
    seniority_note: str | None
    next_actions: tuple[PathAction, ...]
    related: tuple[tuple[str, str], ...] = ()
    example_jobs: tuple[tuple[str, str, str | None], ...] = ()
    evidence_is_thin: bool = False


@dataclass
class _Group:
    family: Family
    jobs: list[JobLite] = field(default_factory=list)


def _demand(jobs: Sequence[JobLite]) -> list[tuple[str, str, float, bool]]:
    score: dict[str, float] = defaultdict(float)
    required_in: dict[str, int] = defaultdict(int)
    label: dict[str, str] = {}
    for job in jobs:
        for s in job.skills:
            score[s.slug] += 1.0 if s.required else 0.5
            required_in[s.slug] += int(s.required)
            label.setdefault(s.slug, s.label)
    n = max(1, len(jobs))
    ranked = sorted(score.items(), key=lambda kv: (-kv[1], kv[0]))
    return [
        (slug, label[slug], min(1.0, value / n), required_in[slug] * 2 >= n)
        for slug, value in ranked
    ]


def _seniority_note(jobs: Sequence[JobLite], mine: str | None) -> tuple[str | None, bool]:
    ranks = [SENIORITY_RANK[j.seniority] for j in jobs if j.seniority in SENIORITY_RANK]
    if not ranks or mine not in SENIORITY_RANK:
        return None, False
    typical = median(ranks)
    gap = typical - SENIORITY_RANK[mine]
    has_nearby = any(abs(r - SENIORITY_RANK[mine]) <= 1 for r in ranks)
    if gap >= 2 and not has_nearby:
        return ("Most of these roles are well above your current level; expect a longer "
                "route, or look for mid-level openings first."), True
    if gap >= 2:
        return ("Most of these roles are senior, but some are close to your level; "
                "start with those."), False
    return None, False


def _fit(coverage: float, downgrade: bool) -> Fit:
    fit: Fit = "close" if coverage >= 0.65 else "stretch" if coverage >= 0.35 else "pivot"
    if downgrade:
        fit = "stretch" if fit == "close" else "pivot"
    return fit


def _join(labels: Sequence[str]) -> str:
    items = list(labels)
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} and {items[-1]}"


def _why(title: str, have: Sequence[PathSkill], core: int, n_jobs: int) -> str:
    if not have:
        return (f"This would be new ground: none of the {core} skills {title} roles ask for "
                "most are on your profile yet.")
    top = _join([s.label for s in have[:3]])
    return (f"You already have {len(have)} of the {core} skills {title} roles ask for most, "
            f"including {top} (across {n_jobs} role{'s' if n_jobs != 1 else ''} here).")


def _actions(
    title: str, fit: Fit, have: Sequence[PathSkill], missing: Sequence[PathSkill],
    candidate: Candidate, n_jobs: int,
) -> tuple[PathAction, ...]:
    actions: list[PathAction] = []
    if missing:
        top = missing[:2]
        names = _join([m.label for m in top])
        share = round(top[0].demand * n_jobs)
        actions.append(PathAction(
            "project",
            f"Build a small project that uses {names}",
            f"{top[0].label} appears in {share} of the {n_jobs} {title} roles here. A focused "
            "project gives you something concrete to show and talk about.",
        ))
    hidden = [
        s for s in have
        if s.slug in candidate.skills and candidate.skills[s.slug].sources <= {"profile"}
    ]
    if hidden:
        actions.append(PathAction(
            "resume",
            f"Show where you've used {_join([s.label for s in hidden[:2]])} on your résumé",
            "They're on your profile but not in any role or project line, so reviewers "
            "won't see the evidence.",
        ))
    if fit == "close":
        actions.append(PathAction(
            "apply",
            f"Apply to the {title} roles that match you best",
            "You cover most of what they ask for; tailoring your résumé to each one is the "
            "next useful step.",
        ))
    elif missing:
        actions.append(PathAction(
            "roadmap",
            f"Turn the {title} gaps into a roadmap",
            "A short, ordered plan makes the gap concrete: what to learn first and how "
            "you'll prove it.",
        ))
    return tuple(actions[:3])


def build_paths(
    jobs: Iterable[JobLite], candidate: Candidate, *, limit: int = 6
) -> list[CareerPath]:
    groups: dict[str, _Group] = {}
    for job in jobs:
        fam = family_for(job.title)
        groups.setdefault(fam.slug, _Group(fam)).jobs.append(job)

    built: list[CareerPath] = []
    core_sets: dict[str, set[str]] = {}
    for slug, group in groups.items():
        demand = _demand(group.jobs)[:CORE_SKILLS]
        if not demand:
            continue
        core_sets[slug] = {d[0] for d in demand}
        skills = [
            PathSkill(
                slug=s, label=label, demand=round(d, 2), required=req,
                have=s in candidate.skills,
                evidence=candidate.skills[s].evidence[:2] if s in candidate.skills else (),
            )
            for s, label, d, req in demand
        ]
        total = sum(p.demand for p in skills) or 1.0
        coverage = sum(p.demand for p in skills if p.have) / total
        note, downgrade = _seniority_note(group.jobs, candidate.seniority)
        fit = _fit(coverage, downgrade)
        have = tuple(p for p in skills if p.have)
        missing = tuple(p for p in skills if not p.have)
        relevant = tuple(t for t in candidate.titles if family_for(t).slug == slug)
        n_jobs = len(group.jobs)
        built.append(CareerPath(
            slug=slug, title=group.family.title, summary=group.family.summary,
            job_count=n_jobs, stated_target=slug in candidate.target_families,
            coverage=round(coverage, 2), fit=fit, fit_label=_FIT_LABEL[fit],
            fit_explanation=_FIT_TEXT[fit],
            why=_why(group.family.title, have, len(skills), n_jobs),
            have=have, missing=missing, relevant_experience=relevant,
            seniority_note=note,
            next_actions=_actions(group.family.title, fit, have, missing, candidate, n_jobs),
            example_jobs=tuple((j.id, j.title, j.company) for j in group.jobs[:5]),
            evidence_is_thin=len(candidate.skills) < 3,
        ))

    ranked = sorted(built, key=lambda p: (not p.stated_target, -p.coverage, p.title))
    titles = {p.slug: p.title for p in ranked}
    out: list[CareerPath] = []
    for path in ranked[:limit]:
        mine = core_sets[path.slug]
        related = sorted(
            (
                (len(mine & other) / len(mine | other), s)
                for s, other in core_sets.items()
                if s != path.slug and mine | other
            ),
            reverse=True,
        )
        out.append(_with_related(path, tuple(
            (s, titles.get(s) or family_for(s).title) for score, s in related[:2] if score >= 0.2
        )))
    return out


def _with_related(path: CareerPath, related: tuple[tuple[str, str], ...]) -> CareerPath:
    return replace(path, related=related)
