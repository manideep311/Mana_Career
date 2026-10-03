from app.domain.career.families import family_for
from app.domain.career.paths import (
    Candidate,
    CandidateSkill,
    CareerPath,
    JobLite,
    JobSkill,
    build_paths,
)
from app.domain.career.skill_plan import Resource, build_skill_plan


def test_families_group_titles_sensibly():
    assert family_for("Senior Backend Engineer, Payments").slug == "backend-engineer"
    assert family_for("Senior Machine Learning Platform Engineer").slug == "mlops-engineer"
    assert family_for("Machine Learning Engineer").slug == "machine-learning-engineer"
    assert family_for("Software Engineering Intern, Full-Stack").slug == "full-stack-engineer"
    assert family_for("Engineering Lead, ML Platform").slug == "engineering-manager"
    assert family_for("Applied Scientist, Forecasting").slug == "research-scientist"
    # Unknown titles fall back to the title without seniority/specialisation.
    assert family_for("Senior Product Designer, Growth").title == "Product Designer"


def _job(i, title, required, preferred=(), seniority="mid"):
    skills = tuple(JobSkill(s, s.title(), True) for s in required) + tuple(
        JobSkill(s, s.title(), False) for s in preferred
    )
    return JobLite(str(i), title, "Co", seniority, skills)


JOBS = [
    _job(1, "Data Analyst", ["sql", "excel", "tableau"], ["python"]),
    _job(2, "Senior Data Analyst", ["sql", "tableau", "statistics"], ["python"], "senior"),
    _job(3, "Data Analyst", ["sql", "excel", "python"]),
    _job(4, "Backend Engineer", ["python", "postgresql", "docker"], ["kubernetes"]),
    _job(5, "Senior Backend Engineer", ["go", "postgresql", "kubernetes"], [], "senior"),
]


def _candidate(slugs, *, seniority="mid", roles=(), sources=frozenset({"resume"})):
    return Candidate(
        skills={
            s: CandidateSkill(s, s.title(), "data", sources, (f"Used {s} at work",))
            for s in slugs
        },
        titles=("Operations Analyst",),
        seniority=seniority,
        preferred_roles=tuple(roles),
    )


def test_best_covered_path_ranks_first_and_explains_its_evidence():
    paths = build_paths(JOBS, _candidate(["sql", "excel", "tableau", "python"]))
    analyst = paths[0]
    assert analyst.slug == "data-analyst" and analyst.job_count == 3
    assert analyst.fit == "close"
    assert "SQL" in analyst.why or "Sql" in analyst.why
    assert {s.slug for s in analyst.have} >= {"sql", "tableau"}
    assert all(0.0 <= s.demand <= 1.0 for s in analyst.have + analyst.missing)


def test_a_stated_target_comes_first_even_with_lower_coverage():
    paths = build_paths(JOBS, _candidate(["sql", "excel"], roles=["Backend Engineer"]))
    assert paths[0].slug == "backend-engineer" and paths[0].stated_target


def _path(skills: list[str], slug: str = "backend-engineer") -> CareerPath:
    return next(p for p in build_paths(JOBS, _candidate(skills)) if p.slug == slug)


def test_fit_is_descriptive_never_a_probability():
    for path in build_paths(JOBS, _candidate(["sql"])):
        assert path.fit in ("close", "stretch", "pivot")
        assert "%" not in path.fit_label + path.fit_explanation + path.why


def test_no_matching_skills_is_described_as_new_ground():
    backend = _path(["excel"])
    assert backend.fit == "pivot"
    assert "new ground" in backend.why


def test_roles_far_above_your_level_downgrade_the_fit():
    senior_only = [_job(i, "Staff Data Engineer", ["sql", "python"], [], "staff") for i in range(3)]
    path = build_paths(senior_only, _candidate(["sql", "python"], seniority="junior"))[0]
    assert path.fit == "stretch" and path.seniority_note


def test_actions_are_concrete():
    backend = _path(["python"])
    kinds = [a.kind for a in backend.next_actions]
    assert kinds[0] == "project"
    first = backend.next_actions[0].title
    assert "Postgresql" in first or "Kubernetes" in first
    assert len(backend.next_actions) <= 3


def test_profile_only_skills_prompt_resume_evidence():
    profile_only = _candidate(["sql", "excel", "tableau"], sources=frozenset({"profile"}))
    paths = build_paths(JOBS, profile_only)
    analyst = next(p for p in paths if p.slug == "data-analyst")
    assert any(a.kind == "resume" for a in analyst.next_actions)


def test_thin_evidence_is_flagged():
    assert build_paths(JOBS, _candidate(["sql"]))[0].evidence_is_thin


def test_related_paths_share_skills():
    analyst = _path(["sql"], "data-analyst")
    assert all(slug != "data-analyst" for slug, _ in analyst.related)


def test_skill_plan_prioritises_required_gaps_and_stays_short():
    path = _path(["python"])
    resources = [
        Resource("r1", "Kubernetes Basics", "Prov", "https://x", "course", "beginner", 8, "free",
                 ("kubernetes",)),
        Resource("r2", "Kubernetes Pro", "Prov", "https://y", "course", "advanced", 40, "paid",
                 ("kubernetes",)),
    ]
    steps = build_skill_plan(
        path, _candidate(["python"]),
        categories={"postgresql": "database", "kubernetes": "devops", "docker": "devops",
                    "go": "language"},
        resources=resources, roadmap_positions={"docker": 2},
    )
    assert 0 < len(steps) <= 5
    assert steps[0].requirement == "Usually a requirement."
    k8s = next(s for s in steps if s.slug == "kubernetes")
    assert k8s.resource is not None and k8s.resource.id == "r1"  # free + beginner first
    assert "Kubernetes" in k8s.practice_project
    assert next(s for s in steps if s.slug == "docker").roadmap_position == 2
    for step in steps:
        assert step.why_it_matters and step.current_evidence and step.practice_project


def test_family_count_groups_titles_and_ignores_blanks():
    from app.domain.career.service import family_count

    titles = ["Senior Backend Engineer", "Backend Engineer, Payments", "Data Analyst", None, "  "]
    assert family_count(titles) == 2
