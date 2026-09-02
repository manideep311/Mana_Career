import decimal

import pytest

from app.domain.profile.strength import ProfileCounts, compute_strength
from app.models.profile import CareerProfile

_ZERO = ProfileCounts(0, 0, 0, 0)
_FULL = ProfileCounts(2, 1, 3, 1)


@pytest.fixture
def _a_blank_profile() -> CareerProfile:
    return CareerProfile()


def _full_profile() -> CareerProfile:
    return CareerProfile(
        location="Hyderabad",
        github_url="https://github.com/x", linkedin_url=None, portfolio_url=None,
        preferred_roles=["AI/ML Engineer"], work_modes=["remote"],
        expected_salary_min=100, expected_salary_max=None, salary_currency="USD",
        years_experience=decimal.Decimal("5.0"), seniority="senior",
        career_goals="Lead an applied-AI team.",
    )


def test_empty_profile_scores_zero():
    r = compute_strength(CareerProfile(), _ZERO)
    assert r.score == 0
    assert r.completeness["experience"] is False
    assert "Add your work experience" in r.missing


def test_full_profile_scores_100():
    r = compute_strength(_full_profile(), _FULL, skill_count=5)
    assert r.score == 100
    assert r.missing == []
    assert all(r.completeness.values())


def test_partial_profile_sums_weights():
    p = CareerProfile(location="Berlin", career_goals="Ship models.")
    r = compute_strength(p, ProfileCounts(experiences=1, education=0, projects=0,
                                          certifications=0))
    # location 8 + goals 10 + experience 16
    assert r.score == 34
    assert r.completeness["education"] is False


def test_links_true_if_any_url_present():
    p = CareerProfile(portfolio_url="https://me.dev")
    r = compute_strength(p, _ZERO)
    assert r.completeness["links"] is True
    assert r.score == 6


def test_dimensions_sum_to_score_and_100(_a_blank_profile):
    from app.domain.profile.strength import ProfileCounts, compute_strength
    r = compute_strength(_a_blank_profile, ProfileCounts(0, 0, 0, 0), skill_count=0)
    assert sum(d.max for d in r.dimensions) == 100
    assert sum(d.earned for d in r.dimensions) == r.score
    assert {d.key for d in r.dimensions} >= {"skills_mapped", "experience", "links"}
    sm = next(d for d in r.dimensions if d.key == "skills_mapped")
    assert sm.met is False and sm.earned == 0 and sm.max == 8


def test_skills_mapped_dimension_flips_at_five(_a_blank_profile):
    from app.domain.profile.strength import ProfileCounts, compute_strength
    assert not compute_strength(_a_blank_profile, ProfileCounts(0,0,0,0), skill_count=4)\
        .dimensions[-1].met
    lit = compute_strength(_a_blank_profile, ProfileCounts(0,0,0,0), skill_count=5)
    assert next(d for d in lit.dimensions if d.key == "skills_mapped").met
