from app.domain.matching.weights import BANDS, SENIORITY_LADDER, WEIGHTS, band_for


def test_weights_sum_to_one_and_cover_ten_dimensions():
    assert set(WEIGHTS) == {
        "skill", "experience", "education", "project", "technology",
        "location", "role", "seniority", "salary", "semantic",
    }
    assert round(sum(WEIGHTS.values()), 10) == 1.0


def test_bands_thresholds():
    assert band_for(92.0) == "strong"
    assert band_for(80.0) == "strong"
    assert band_for(70.0) == "good"
    assert band_for(50.0) == "partial"
    assert band_for(10.0) == "weak"
    assert BANDS[0] == (80.0, "strong")


def test_seniority_ladder_maps_every_job_and_profile_value():
    for v in ("intern", "junior", "mid", "senior", "staff", "principal", "lead", "manager"):
        assert v in SENIORITY_LADDER
    assert 0 <= min(SENIORITY_LADDER.values()) and max(SENIORITY_LADDER.values()) <= 5
