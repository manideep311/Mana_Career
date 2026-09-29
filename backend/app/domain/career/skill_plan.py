"""The few skills worth working on next, with a concrete way to build each.

Takes the gaps from one career path, keeps the handful that matter most
(required before preferred, then by how many roles ask), and for each says
why it matters, what related evidence you already have, which catalogue
resource fits, what to build to prove it, and where it sits on your roadmap.
Never a long list: the point is the next useful step.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.career.paths import Candidate, CareerPath

MAX_STEPS = 5

_PROJECTS = {
    "language": ("Rewrite a small tool you already rely on in {skill}: a script that reads "
                 "real data, does one useful thing, and has a few tests."),
    "backend": ("Build a small {skill} API for something you know well (a reading list, an "
                "expense tracker) with 3-4 endpoints, input validation and tests."),
    "frontend": ("Build a one-page {skill} app that loads data from a public API, handles "
                 "loading and error states, and passes a basic accessibility check."),
    "database": ("Model a small dataset from your own field in {skill}, then write five "
                 "queries that answer real questions and explain them in a README."),
    "data": ("Take a public dataset in an area you care about, clean and analyse it with "
             "{skill}, and publish three findings with the charts that support them."),
    "ml_technique": ("Apply {skill} to a public dataset: report a simple baseline, one "
                     "improvement, and what you would try next."),
    "ml_framework": ("Train and evaluate a small model with {skill} on a public dataset; "
                     "write up the baseline, one improvement, and its limits."),
    "devops": ("Deploy one of your existing projects using {skill}, with a README that lets "
               "someone else reproduce the setup from scratch."),
    "cloud": ("Deploy one of your existing projects on {skill}, keep it within the free tier, "
              "and document the architecture in one diagram."),
    "tooling": ("Adopt {skill} in one of your existing projects and write a short note on "
                "what it changed in how you work."),
    "practice": ("Prepare two STAR-format stories from your past work that show {skill}, and "
                 "apply it deliberately in your next project."),
}
_DEFAULT_PROJECT = ("Use {skill} in a small, self-contained project you can finish in a "
                    "weekend and explain in an interview.")
_COST_RANK = {"free": 0, "freemium": 1, "paid": 2}
_LEVEL_RANK = {"beginner": 0, "intermediate": 1, "advanced": 2}


@dataclass(frozen=True)
class Resource:
    id: str
    title: str
    provider: str
    url: str
    type: str
    level: str
    est_hours: int | None
    cost: str
    skills: tuple[str, ...]


@dataclass(frozen=True)
class SkillStep:
    slug: str
    label: str
    category: str
    why_it_matters: str
    requirement: str
    current_evidence: str
    resource: Resource | None
    practice_project: str
    roadmap_position: int | None


def _pick_resource(slug: str, resources: Sequence[Resource]) -> Resource | None:
    matches = [r for r in resources if slug in r.skills]
    if not matches:
        return None
    return min(
        matches,
        key=lambda r: (
            _COST_RANK.get(r.cost, 3),
            _LEVEL_RANK.get(r.level, 3),
            r.est_hours if r.est_hours is not None else 999,
            r.title,
        ),
    )


def practice_project(label: str, category: str) -> str:
    """A small, finishable project that proves ``label``; shaped by its category."""
    return _PROJECTS.get(category, _DEFAULT_PROJECT).format(skill=label)


def _evidence(category: str, candidate: Candidate) -> str:
    related = [s.label for s in candidate.skills.values() if s.category == category]
    if related:
        shown = ", ".join(sorted(related)[:2])
        return f"You already use {shown}, a related skill, so this builds on what you know."
    return "Nothing on your profile shows this area yet, so plan for a first project from scratch."


def build_skill_plan(
    path: CareerPath,
    candidate: Candidate,
    *,
    categories: dict[str, str],
    resources: Sequence[Resource],
    roadmap_positions: dict[str, int] | None = None,
) -> list[SkillStep]:
    ranked = sorted(path.missing, key=lambda g: (not g.required, -g.demand, g.label))
    positions = roadmap_positions or {}
    steps: list[SkillStep] = []
    for gap in ranked[:MAX_STEPS]:
        category = categories.get(gap.slug, "")
        share = round(gap.demand * path.job_count)
        steps.append(SkillStep(
            slug=gap.slug,
            label=gap.label,
            category=category,
            why_it_matters=(
                f"{gap.label} appears in {share} of the {path.job_count} {path.title} "
                f"role{'s' if path.job_count != 1 else ''} we looked at."
            ),
            requirement=(
                "Usually a requirement." if gap.required else "Usually listed as a plus."
            ),
            current_evidence=_evidence(category, candidate),
            resource=_pick_resource(gap.slug, resources),
            practice_project=practice_project(gap.label, category),
            roadmap_position=positions.get(gap.slug),
        ))
    return steps
