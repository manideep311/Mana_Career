"""The /career response models accept what the pure guidance layer produces
(no DB): catches schema drift locally, before the DB-gated API tests run."""

import uuid

from app.api.v1.career import analysis_out, path_out
from app.api.v1.schemas.career import SkillStepOut
from app.domain.career.paths import Candidate, CandidateSkill, JobLite, JobSkill, build_paths
from app.domain.career.skill_plan import Resource, build_skill_plan
from app.domain.resume.analysis import TargetSpec, analyze_resume

JOBS = [
    JobLite(str(uuid.uuid4()), f"Backend Engineer {i}", "Co", "mid", (
        JobSkill("python", "Python", True), JobSkill("kubernetes", "Kubernetes", True),
    ))
    for i in range(2)
]
CANDIDATE = Candidate(skills={
    "python": CandidateSkill("python", "Python", "language", frozenset({"resume"}),
                             ("Built Python services",)),
})


def test_path_out_serialises_a_built_path():
    path = build_paths(JOBS, CANDIDATE)[0]
    out = path_out(path).model_dump(mode="json")
    assert out["slug"] == "backend-engineer"
    assert out["have"][0]["evidence"] == ["Built Python services"]
    assert len(out["roles"]) == 2 and out["roles"][0]["company"] == "Co"


def test_skill_step_out_serialises_with_a_resource():
    path = build_paths(JOBS, CANDIDATE)[0]
    res = Resource(str(uuid.uuid4()), "K8s", "P", "https://x", "course", "beginner", 6,
                   "free", ("kubernetes",))
    steps = build_skill_plan(path, CANDIDATE, categories={"kubernetes": "devops"},
                             resources=[res])
    out = SkillStepOut.model_validate(steps[0]).model_dump(mode="json")
    assert out["resource"]["title"] == "K8s"
    assert out["practice_project"].startswith("Deploy")


def test_analysis_out_serialises_issues_and_alignment():
    text = "EXPERIENCE\nEngineer, Co 2020 - 2023\n• Responsible for Python scripts\n" * 4
    a = analyze_resume(text, target=TargetSpec("Backend Engineer", (("kubernetes", "Kubernetes"),)))
    out = analysis_out(uuid.uuid4(), a, None).model_dump(mode="json")
    assert out["issues"] and {"problem", "why_it_matters", "suggestion"} <= out["issues"][0].keys()
    assert out["alignment"]["missing"] == ["Kubernetes"]
    assert out["target_path"] is None
