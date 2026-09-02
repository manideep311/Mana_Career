from __future__ import annotations

from dataclasses import dataclass

from app.models.profile import CareerProfile

_WEIGHTS: list[tuple[str, int, str, str]] = [
    ("location", 8, "Location", "Add your location"),
    ("links", 6, "Profile links", "Add a GitHub, LinkedIn or portfolio link"),
    ("goals", 10, "Career goals", "Add your career goals"),
    ("preferred_roles", 8, "Target roles", "Add the roles you're targeting"),
    ("seniority", 6, "Seniority", "Set your seniority level"),
    ("years_experience", 6, "Years of experience", "Add your years of experience"),
    ("salary", 6, "Salary expectations", "Add your salary expectations"),
    ("experience", 16, "Work experience", "Add your work experience"),
    ("education", 12, "Education", "Add your education"),
    ("projects", 10, "Projects", "Add a project"),
    ("certifications", 4, "Certifications", "Add a certification"),
    (
        "skills_mapped",
        8,
        "Skills mapped",
        "Upload a résumé so Mana can map your skills",
    ),
]


@dataclass(frozen=True)
class ProfileCounts:
    experiences: int
    education: int
    projects: int
    certifications: int


@dataclass(frozen=True)
class StrengthDimension:
    key: str
    label: str
    earned: int
    max: int
    hint: str
    met: bool


@dataclass(frozen=True)
class StrengthResult:
    score: int
    completeness: dict[str, bool]
    missing: list[str]
    dimensions: list[StrengthDimension]


def _truthy(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (list, tuple)):
        return len(value) > 0
    return True


def compute_strength(
    profile: CareerProfile, counts: ProfileCounts, *, skill_count: int = 0
) -> StrengthResult:
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
        "skills_mapped": skill_count >= 5,
    }
    score = sum(w for key, w, _label, _hint in _WEIGHTS if checks[key])
    missing = [hint for key, _w, _label, hint in _WEIGHTS if not checks[key]]
    dimensions = [
        StrengthDimension(
            key=key,
            label=label,
            earned=(w if checks[key] else 0),
            max=w,
            hint=hint,
            met=checks[key],
        )
        for key, w, label, hint in _WEIGHTS
    ]
    return StrengthResult(
        score=score, completeness=checks, missing=missing, dimensions=dimensions
    )
