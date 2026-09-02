from app.domain.matching.gaps import GapDraft, derive_gaps
from app.domain.matching.scorer import Component


def _skill_component(missing: list[str]) -> Component:
    return Component(
        dimension="skill", raw_score=0.5, weight=0.22, contribution=11.0,
        detail={"matched": [], "missing": missing}, evidence=[],
    )


def test_derive_gaps_severity_from_weight_and_list():
    req = [
        {"skill_id": "a", "slug": "rust", "label": "Rust", "weight": 0.9},
        {"skill_id": "b", "slug": "go", "label": "Go", "weight": 0.4},
    ]
    pref = [{"skill_id": "c", "slug": "helm", "label": "Helm", "weight": 0.3}]
    gaps = derive_gaps(req, pref, _skill_component(["a", "b", "c"]))
    assert [(g.slug, g.severity) for g in gaps] == [
        ("rust", "critical"), ("go", "important"), ("helm", "nice_to_have")
    ]


def test_derive_gaps_dedups_required_over_preferred_and_skips_covered():
    req = [{"skill_id": "a", "slug": "rust", "label": "Rust", "weight": 0.9}]
    pref = [{"skill_id": "a", "slug": "rust", "label": "Rust", "weight": 0.2}]
    assert [g.severity for g in derive_gaps(req, pref, _skill_component(["a"]))] == ["critical"]
    assert derive_gaps(req, pref, _skill_component([])) == []


def test_derive_gaps_orders_by_severity_then_label():
    req = [
        {"skill_id": "1", "slug": "zeta", "label": "Zeta", "weight": 0.9},
        {"skill_id": "2", "slug": "alpha", "label": "Alpha", "weight": 0.9},
        {"skill_id": "3", "slug": "yankee", "label": "Yankee", "weight": 0.5},
        {"skill_id": "4", "slug": "bravo", "label": "Bravo", "weight": 0.5},
    ]
    pref = [
        {"skill_id": "5", "slug": "xray", "label": "Xray", "weight": 0.1},
        {"skill_id": "6", "slug": "charlie", "label": "Charlie", "weight": 0.1},
    ]
    gaps = derive_gaps(req, pref, _skill_component(["1", "2", "3", "4", "5", "6"]))
    assert [g.label for g in gaps] == [
        "Alpha", "Zeta", "Bravo", "Yankee", "Charlie", "Xray"
    ]
    assert [g.severity for g in gaps] == [
        "critical", "critical", "important", "important", "nice_to_have", "nice_to_have"
    ]


def test_derive_gaps_ignores_present_skills_and_returns_gapdraft():
    req = [
        {"skill_id": "have", "slug": "python", "label": "Python", "weight": 0.9},
        {"skill_id": "gap", "slug": "rust", "label": "Rust", "weight": 0.8},
    ]
    gaps = derive_gaps(req, [], _skill_component(["gap"]))
    assert gaps == [GapDraft(skill_id="gap", slug="rust", label="Rust", severity="critical")]
