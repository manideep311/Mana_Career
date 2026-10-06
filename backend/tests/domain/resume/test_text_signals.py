"""Filling extraction gaps from the résumé's own words (no AI model)."""
from __future__ import annotations

import json
from pathlib import Path

from app.domain.resume.extractor import ResumeExtraction
from app.domain.resume.text_signals import complete_from_text, skills_named_in

RESUME = """Asha Rao  |  asha.rao@example.com  |  github.com/asharao  |  linkedin.com/in/asha-rao
Backend engineer. Built services in Python/Django and FastAPI on AWS Lambda; React-based dashboards.
Skills: Python, Go, SQL, PostgreSQL, Docker, Kubernetes, Express.js, scikit-learn, C++, C#, Node.js
"""


def test_finds_catalogue_skills_the_text_names_in_reading_order():
    found = skills_named_in(RESUME)
    for skill in (
        "Python", "Django", "FastAPI", "AWS Lambda", "React", "Go", "SQL", "PostgreSQL",
        "Docker", "Kubernetes", "Express", "scikit-learn", "C++", "C#", "Node.js",
    ):
        assert skill in found, skill
    assert found.index("Python") < found.index("Django") < found.index("Kubernetes")
    assert len(found) == len(set(found))


def test_every_skill_found_is_a_catalogue_label():
    taxonomy = Path(__file__).resolve().parents[3] / "app" / "domain" / "skills" / "taxonomy.json"
    labels = {e["label"] for e in json.loads(taxonomy.read_text(encoding="utf-8"))}
    assert set(skills_named_in(RESUME)) <= labels


def test_words_inside_other_words_do_not_count():
    assert skills_named_in("JavaScript, MySQL, NoSQL, SQLAlchemy") == [
        "JavaScript", "MySQL", "SQLAlchemy",
    ]  # no Java, no SQL


def test_ordinary_words_are_not_mistaken_for_skills():
    prose = (
        "Owned the go-to-market plan and R&D budget; covered the rest of the team. "
        "Spring 2023 semester. Make data-driven decisions. Attached: CV. Swift turnaround."
    )
    assert skills_named_in(prose) == []
    # The same names count when written as the tools themselves.
    assert skills_named_in("Languages: Go, R, Swift") == ["Go", "R", "Swift"]


def test_fills_only_what_the_extractor_left_empty():
    filled = complete_from_text(ResumeExtraction(), RESUME)
    assert "Python" in filled.skills
    assert filled.email == "asha.rao@example.com"
    assert filled.github_url == "https://github.com/asharao"
    assert filled.linkedin_url == "https://www.linkedin.com/in/asha-rao"

    already = ResumeExtraction(skills=["Rust"], email="me@x.test")
    kept = complete_from_text(already, RESUME)
    assert kept.skills == ["Rust"] and kept.email == "me@x.test"
    assert kept.github_url == "https://github.com/asharao"


def test_text_without_signals_changes_nothing():
    empty = ResumeExtraction()
    assert complete_from_text(empty, "Hello there.") is empty
