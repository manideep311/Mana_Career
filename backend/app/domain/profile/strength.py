from __future__ import annotations

from dataclasses import dataclass

from app.models.profile import CareerProfile

_WEIGHTS: list[tuple[str, int, str]] = [
    ("location", 8, "Add your location"),
    ("links", 10, "Add a GitHub, LinkedIn or portfolio link"),
    ("goals", 10, "Add your career goals"),
    ("preferred_roles", 8, "Add the roles you're targeting"),
    ("seniority", 6, "Set your seniority level"),
    ("years_experience", 6, "Add your years of experience"),
    ("salary", 6, "Add your salary expectations"),
    ("experience", 20, "Add your work experience"),
    ("education", 12, "Add your education"),
    ("projects", 10, "Add a project"),
    ("certifications", 4, "Add a certification"),
]


@dataclass(frozen=True)
class ProfileCounts:
    experiences: int
    education: int
    projects: int
    certifications: int


@dataclass(frozen=True)
class StrengthResult:
    score: int
    completeness: dict[str, bool]
    missing: list[str]


def _truthy(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (list, tuple)):
        return len(value) > 0
    return True


def compute_strength(profile: CareerProfile, counts: ProfileCounts) -> StrengthResult:
    checks: dict[str, bool] = {
        "location": _truthy(profile.location),
        "links": any(
            _truthy(u)
            for u in (profile.github_url, profile.linkedin_url, profile.portfolio_url)
        ),
        "goals": _truthy(profile.career_goals),
        "preferred_roles": _truthy(profile.preferred_roles),
        "seniority": _truthy(profile.seniority),
        "years_experience": profile.years_experience is not None,
        "salary": profile.expected_salary_min is not None
        or profile.expected_salary_max is not None,
        "experience": counts.experiences >= 1,
        "education": counts.education >= 1,
        "projects": counts.projects >= 1,
        "certifications": counts.certifications >= 1,
    }
    score = sum(w for key, w, _ in _WEIGHTS if checks[key])
    missing = [label for key, _, label in _WEIGHTS if not checks[key]]
    return StrengthResult(score=score, completeness=checks, missing=missing)
