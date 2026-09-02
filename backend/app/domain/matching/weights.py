"""Hand-tuned constants for the deterministic :mod:`app.domain.matching.scorer`.

Ten dimension weights (they sum to ``1.0``), score bands, and a seniority ladder
that maps every profile/job seniority label onto a single 0-5 line. Plain
constants plus one pure ``band_for`` function -- no I/O, no imports.
"""

SCORER_VERSION = "v1"

# Dimension order here is authoritative: components, ``dimension_scores`` and the
# aggregation loop all iterate this dict's insertion order.
WEIGHTS: dict[str, float] = {
    "skill": 0.22,
    "experience": 0.16,
    "technology": 0.13,
    "semantic": 0.12,
    "role": 0.10,
    "seniority": 0.08,
    "project": 0.07,
    "education": 0.05,
    "location": 0.04,
    "salary": 0.03,
}

BANDS: tuple[tuple[float, str], ...] = (
    (80.0, "strong"),
    (65.0, "good"),
    (45.0, "partial"),
    (0.0, "weak"),
)

# ``lead``/``manager`` sit alongside ``staff``. The spec's profile ladder has no
# ``intern``/``manager`` and the job ladder carries both -- this table maps every
# value that either side can produce onto the same 0-5 scale.
SENIORITY_LADDER: dict[str, int] = {
    "intern": 0,
    "junior": 1,
    "mid": 2,
    "senior": 3,
    "staff": 4,
    "principal": 5,
    "lead": 4,
    "manager": 4,
}


def band_for(score: float) -> str:
    """Return the first band name whose threshold is ``<= score``."""
    for threshold, name in BANDS:
        if threshold <= score:
            return name
    return BANDS[-1][1]
