import pytest

from app.core.errors import ValidationAppError
from app.domain.jobs.ingestor import JobIngestor


def test_clean_collapses_blank_lines_and_trims():
    raw = "  Senior ML Engineer  \n\n\n\n  Build models.  \n\n\n"
    out = JobIngestor().clean(raw)
    assert out == "Senior ML Engineer\n\nBuild models."


def test_clean_truncates_to_cap():
    out = JobIngestor().clean("x " * 30_000)
    assert len(out) <= 40_000


def test_clean_rejects_near_empty():
    with pytest.raises(ValidationAppError):
        JobIngestor().clean("   hi   ")
