from app.domain.resume.extractor import ExtractedExperience, ResumeExtraction
from app.domain.resume.version_service import diff


def _cv(**kw) -> ResumeExtraction:
    base = dict(
        full_name="A", summary="s", skills=["python", "sql"],
        experiences=[ExtractedExperience(company="Acme", title="Eng", highlights=["one"])],
    )
    base.update(kw)
    return ResumeExtraction(**base)


def test_identical_extractions_have_no_deltas():
    assert diff(_cv(), _cv()).deltas == []


def test_changed_summary_is_one_changed_delta():
    d = diff(_cv(), _cv(summary="different"))
    assert [x.path for x in d.deltas] == ["summary"]
    assert d.deltas[0].op == "changed"


def test_added_highlight_on_existing_experience():
    other = _cv()
    other.experiences[0].highlights.append("two")
    d = diff(_cv(), other)
    assert any(x.path == "experiences[0].highlights" and x.op == "added" for x in d.deltas)


def test_new_experience_is_added_delta():
    other = _cv()
    other.experiences.append(ExtractedExperience(company="Globex", title="Staff"))
    d = diff(_cv(), other)
    assert any(x.path.startswith("experiences[") and x.op == "added" for x in d.deltas)


def test_skills_reordered_only():
    d = diff(_cv(), _cv(skills=["sql", "python"]))
    assert [x.op for x in d.deltas] == ["reordered"]
