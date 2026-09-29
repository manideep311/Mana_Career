"""Career guidance: directions, paths, the skills worth building next.

Read-only and deterministic: everything is computed from the person's own
profile, résumé and the job catalogue, so it works with or without an LLM.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbDep
from app.api.v1.schemas.career import (
    AnalysisIssueOut,
    CareerOverviewOut,
    CareerPathOut,
    CareerPathsOut,
    JourneyStageOut,
    NextActionOut,
    OpportunityOut,
    PathActionOut,
    PathJobOut,
    PathSkillOut,
    RelatedPathOut,
    ResumeAnalysisOut,
    RoadmapBriefOut,
    RoleAlignmentOut,
    SkillEvidenceOut,
    SkillPlanOut,
    SkillStepOut,
)
from app.core.errors import NotFoundError
from app.domain.career.paths import CareerPath
from app.domain.career.service import CareerService
from app.domain.resume.analysis import ResumeAnalysis

router = APIRouter(prefix="/career", tags=["career"])


def path_out(p: CareerPath) -> CareerPathOut:
    return CareerPathOut(
        slug=p.slug, title=p.title, summary=p.summary, job_count=p.job_count,
        stated_target=p.stated_target, fit=p.fit, fit_label=p.fit_label,
        fit_explanation=p.fit_explanation, why=p.why,
        have=[PathSkillOut.model_validate(s) for s in p.have],
        missing=[PathSkillOut.model_validate(s) for s in p.missing],
        relevant_experience=list(p.relevant_experience),
        seniority_note=p.seniority_note,
        next_actions=[PathActionOut.model_validate(a) for a in p.next_actions],
        related=[RelatedPathOut(slug=s, title=t) for s, t in p.related],
        roles=[PathJobOut(id=uuid.UUID(i), title=t, company=c) for i, t, c in p.example_jobs],
        evidence_is_thin=p.evidence_is_thin,
    )


def analysis_out(
    resume_id: uuid.UUID, a: ResumeAnalysis, direction: CareerPath | None
) -> ResumeAnalysisOut:
    return ResumeAnalysisOut(
        resume_id=resume_id, enough_text=a.enough_text, sections=dict(a.sections),
        word_count=a.word_count, page_count=a.page_count, bullet_count=a.bullet_count,
        bullets_with_results=a.bullets_with_results, strengths=list(a.strengths),
        issues=[AnalysisIssueOut.model_validate(i) for i in a.issues],
        skills=[SkillEvidenceOut.model_validate(s) for s in a.skills],
        alignment=RoleAlignmentOut.model_validate(a.alignment) if a.alignment else None,
        target_path=(
            RelatedPathOut(slug=direction.slug, title=direction.title) if direction else None
        ),
    )


@router.get("/overview")
async def career_overview(db: DbDep, user: CurrentUser) -> CareerOverviewOut:
    o = await CareerService(db).overview(user.id)
    return CareerOverviewOut(
        direction=path_out(o.direction) if o.direction else None,
        direction_summary=o.direction_summary,
        next_actions=[NextActionOut.model_validate(a) for a in o.next_actions],
        journey=[JourneyStageOut.model_validate(s) for s in o.journey],
        roadmap=RoadmapBriefOut.model_validate(o.roadmap) if o.roadmap else None,
        opportunities=[OpportunityOut.model_validate(x) for x in o.opportunities],
        skills=[SkillStepOut.model_validate(s) for s in o.skills],
        notes=list(o.notes),
        has_resume=o.has_resume,
    )


@router.get("/paths")
async def career_paths(db: DbDep, user: CurrentUser) -> CareerPathsOut:
    paths, notes = await CareerService(db).paths(user.id)
    return CareerPathsOut(paths=[path_out(p) for p in paths], notes=list(notes))


@router.get("/paths/{slug}")
async def career_path(slug: str, db: DbDep, user: CurrentUser) -> CareerPathOut:
    path = await CareerService(db).path(user.id, slug)
    if path is None:
        raise NotFoundError(
            detail="We couldn't find that career path.", code="career.path_not_found"
        )
    return path_out(path)


@router.get("/skills")
async def career_skills(
    db: DbDep, user: CurrentUser, path: str | None = None
) -> SkillPlanOut:
    chosen, steps = await CareerService(db).skill_plan(user.id, path)
    return SkillPlanOut(
        path_slug=chosen.slug if chosen else None,
        path_title=chosen.title if chosen else None,
        steps=[SkillStepOut.model_validate(s) for s in steps],
    )
