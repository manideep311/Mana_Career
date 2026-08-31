import pytest
from pydantic import ValidationError

from app.api.v1.schemas.profile import (
    CareerProfileUpdate,
    ExperienceIn,
    ReorderIn,
)


def test_update_rejects_unknown_field():
    with pytest.raises(ValidationError):
        CareerProfileUpdate(nickname="Neo")


def test_update_rejects_bad_work_mode():
    with pytest.raises(ValidationError):
        CareerProfileUpdate(work_modes=["telepathy"])


def test_update_rejects_non_http_url():
    with pytest.raises(ValidationError):
        CareerProfileUpdate(github_url="ftp://nope")


def test_update_accepts_partial_valid_payload():
    m = CareerProfileUpdate(location="Hyderabad", work_modes=["remote", "hybrid"],
                            years_experience=5.5, seniority="senior")
    dumped = m.model_dump(exclude_unset=True)
    assert set(dumped) == {"location", "work_modes", "years_experience", "seniority"}


def test_experience_in_requires_company_and_title():
    with pytest.raises(ValidationError):
        ExperienceIn(company="Acme")


def test_reorder_in_requires_nonempty():
    with pytest.raises(ValidationError):
        ReorderIn(ids=[])
