import uuid

from app.domain.roadmap.phases import MilestoneTiming, assign_phases, hours_per_week
from app.domain.roadmap.planner import _template_draft
from app.models.learning import LearningResource
from app.models.match import SkillGap


def _m(hours: int | None, status: str = "not_started") -> MilestoneTiming:
    return MilestoneTiming(uuid.uuid4(), hours, status)


def test_first_open_milestone_is_current_and_the_rest_fill_the_windows():
    # At 5h a week: ~21h fits in 30 days, ~64h in 90. Open work starts at 0, 10,
    # 20, 30, 60 and 80 hours.
    ms = [_m(10, "done"), _m(10), _m(10), _m(10), _m(30), _m(20), _m(10)]
    phases = assign_phases(ms, weekly_hours=5)
    assert [phases[m.id] for m in ms] == [
        "done", "current", "next_30", "next_30", "next_60_90", "next_60_90", "later",
    ]


def test_in_progress_milestone_is_current_even_when_not_first():
    ms = [_m(8), _m(8, "in_progress"), _m(8)]
    phases = assign_phases(ms, weekly_hours=5)
    assert phases[ms[1].id] == "current"
    assert phases[ms[0].id] == "next_30"


def test_missing_estimates_use_a_default_rather_than_zero():
    ms = [_m(None) for _ in range(10)]  # 8h each: the last starts at 72h
    phases = [assign_phases(ms, weekly_hours=5)[m.id] for m in ms]
    assert phases.count("later") >= 1


def test_a_faster_pace_pulls_work_forward():
    ms = [_m(20) for _ in range(4)]
    slow = assign_phases(ms, weekly_hours=2)
    fast = assign_phases(ms, weekly_hours=20)
    assert list(slow.values()).count("later") > list(fast.values()).count("later")


def test_weekly_pace_is_clamped_and_defaulted():
    assert hours_per_week(None) == 5
    assert hours_per_week({"hours_per_week": "12"}) == 12
    assert hours_per_week({"hours_per_week": 500}) == 40
    assert hours_per_week({"hours_per_week": "lots"}) == 5


def _gap(freq: int, severity: str) -> SkillGap:
    return SkillGap(
        user_id=uuid.uuid4(), scope="aggregate", skill_slug="kubernetes",
        skill_label="Kubernetes", severity=severity, frequency=freq, status="open",
    )


def test_template_milestone_uses_only_stored_facts():
    resource = LearningResource(
        title="K8s", provider="P", url="https://x", type="course", skills=["kubernetes"],
        level="beginner", cost="free", summary="s", est_hours=14,
    )
    draft = _template_draft(_gap(3, "critical"), [resource], "devops")
    assert "3 of your job matches, usually as a requirement" in draft.why_it_matters
    assert draft.est_hours == 14
    assert draft.practice_project.startswith("Deploy one of your existing projects using")
    assert "Kubernetes" in draft.checkpoint


def test_template_milestone_without_resources_still_gives_a_next_step():
    draft = _template_draft(_gap(1, "nice_to_have"), [], "")
    assert "1 of your job matches." in draft.why_it_matters
    assert "requirement" not in draft.why_it_matters
    assert draft.est_hours == 8
    assert "Kubernetes" in draft.practice_project
