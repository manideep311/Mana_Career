"""Loads what we know about a person and composes their career guidance.

Everything is read from stored data and combined by the pure functions in
``paths.py`` and ``skill_plan.py``. Nothing here calls a model.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.career.paths import (
    Candidate,
    CandidateSkill,
    CareerPath,
    JobLite,
    JobSkill,
    build_paths,
)
from app.domain.career.skill_plan import Resource, SkillStep, build_skill_plan
from app.domain.resume.analysis import ResumeAnalysis, TargetSpec, analyze_resume
from app.domain.skills.scanner import load_taxonomy, scan_lines
from app.models.application import Application
from app.models.job import Job
from app.models.learning import LearningRecommendation, LearningResource, RoadmapMilestone
from app.models.match import JobMatch, SkillGap
from app.models.profile import CareerProfile, ProfileExperience, ProfileProject
from app.models.resume import Resume
from app.models.skill import ProfileSkill, Skill

_ACTIVE_APPLICATION = ("applied", "interview", "offer")
_DIMENSION_REASON = {
    "skill": "Strong skill overlap",
    "experience": "Relevant experience",
    "technology": "Tech stack overlap",
    "semantic": "Similar work to yours",
    "role": "Fits your role history",
    "seniority": "Right level for you",
    "project": "Relevant projects",
    "education": "Education fits",
    "location": "Location fits",
    "salary": "Salary in your range",
}


@dataclass(frozen=True)
class CandidateContext:
    candidate: Candidate
    has_resume: bool
    resume_id: uuid.UUID | None
    resume_confirmed: bool
    projects: int


@dataclass(frozen=True)
class NextAction:
    kind: str
    title: str
    detail: str
    href: str | None


@dataclass(frozen=True)
class JourneyStage:
    key: str
    label: str
    status: Literal["done", "current", "upcoming"]
    detail: str


@dataclass(frozen=True)
class MilestoneBrief:
    id: uuid.UUID
    title: str
    skill_label: str
    status: str


@dataclass(frozen=True)
class RoadmapBrief:
    id: uuid.UUID
    title: str
    done: int
    total: int
    current: MilestoneBrief | None
    upcoming: MilestoneBrief | None


@dataclass(frozen=True)
class Opportunity:
    job_id: uuid.UUID
    title: str
    company: str | None
    band: str | None
    reason: str | None
    gap: str | None


@dataclass(frozen=True)
class Overview:
    direction: CareerPath | None
    direction_summary: str
    next_actions: tuple[NextAction, ...]
    journey: tuple[JourneyStage, ...]
    roadmap: RoadmapBrief | None
    opportunities: tuple[Opportunity, ...]
    skills: tuple[SkillStep, ...]
    notes: tuple[str, ...]
    has_resume: bool


class CareerService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # ------------------------------------------------------------------ inputs

    async def candidate(self, user_id: uuid.UUID) -> CandidateContext:
        profile = (
            await self._s.execute(select(CareerProfile).where(CareerProfile.user_id == user_id))
        ).scalar_one_or_none()
        skills: dict[str, CandidateSkill] = {}

        def add(slug: str, label: str, category: str, source: str, evidence: str | None) -> None:
            prev = skills.get(slug)
            sources = (prev.sources if prev else frozenset()) | {source}
            ev = list(prev.evidence if prev else ())
            if evidence and evidence not in ev and source != "profile":
                ev.append(evidence)
            skills[slug] = CandidateSkill(slug, label, category, frozenset(sources), tuple(ev[:3]))

        rows = (
            await self._s.execute(
                select(Skill.slug, Skill.label, Skill.category)
                .join(ProfileSkill, ProfileSkill.skill_id == Skill.id)
                .where(ProfileSkill.user_id == user_id)
            )
        ).all()
        for row in rows:
            add(row.slug, row.label, row.category, "profile", None)

        experiences = (
            await self._s.execute(
                select(ProfileExperience).where(ProfileExperience.user_id == user_id)
            )
        ).scalars().all()
        for exp in experiences:
            lines = [*exp.highlights, *(exp.tech or []), exp.description or ""]
            for hit in scan_lines(lines).values():
                line = next((ln for ln in hit.lines if len(ln.split()) > 3), None)
                add(hit.slug, hit.label, hit.category, "experience",
                    line or f"{exp.title} at {exp.company}")

        projects = (
            await self._s.execute(select(ProfileProject).where(ProfileProject.user_id == user_id))
        ).scalars().all()
        for proj in projects:
            lines = [*proj.highlights, *(proj.tech or []), proj.description or ""]
            for hit in scan_lines(lines).values():
                line = next((ln for ln in hit.lines if len(ln.split()) > 3), None)
                add(hit.slug, hit.label, hit.category, "project", line or f"Project: {proj.name}")

        resume = await self._latest_resume(user_id)
        if resume is not None and resume.extracted_text:
            for hit in scan_lines(resume.extracted_text.splitlines()).values():
                line = next((ln for ln in hit.lines if len(ln.split()) > 3), None)
                add(hit.slug, hit.label, hit.category, "resume", line)

        return CandidateContext(
            candidate=Candidate(
                skills=skills,
                titles=tuple(e.title for e in experiences),
                seniority=profile.seniority if profile else None,
                preferred_roles=tuple(profile.preferred_roles or ()) if profile else (),
            ),
            has_resume=resume is not None,
            resume_id=resume.id if resume else None,
            resume_confirmed=bool(resume and resume.confirmed_at),
            projects=len(projects),
        )

    async def _latest_resume(self, user_id: uuid.UUID) -> Resume | None:
        return (
            await self._s.execute(
                select(Resume)
                .where(Resume.user_id == user_id, Resume.deleted_at.is_(None))
                .order_by(Resume.is_primary.desc(), Resume.created_at.desc())
                .limit(1)
            )
        ).scalars().first()

    async def jobs(self, user_id: uuid.UUID) -> list[JobLite]:
        rows = (
            await self._s.execute(
                select(Job).where(
                    Job.status == "ready",
                    Job.deleted_at.is_(None),
                    or_(Job.user_id == user_id, Job.user_id.is_(None)),
                )
            )
        ).scalars().all()
        return [
            JobLite(
                id=str(j.id),
                title=j.title or "Untitled role",
                company=j.company,
                seniority=j.seniority,
                skills=tuple(_job_skills(j.required_skills, True))
                + tuple(_job_skills(j.preferred_skills, False)),
            )
            for j in rows
        ]

    # ------------------------------------------------------------------ guidance

    async def paths(
        self, user_id: uuid.UUID, *, limit: int = 6
    ) -> tuple[list[CareerPath], tuple[str, ...]]:
        """Suggested paths plus notes on how much evidence they rest on."""
        ctx = await self.candidate(user_id)
        return build_paths(await self.jobs(user_id), ctx.candidate, limit=limit), _notes(ctx)

    async def path(self, user_id: uuid.UUID, slug: str) -> CareerPath | None:
        paths, _ = await self.paths(user_id, limit=50)
        return next((p for p in paths if p.slug == slug), None)

    async def skill_plan(
        self, user_id: uuid.UUID, slug: str | None = None
    ) -> tuple[CareerPath | None, list[SkillStep]]:
        ctx = await self.candidate(user_id)
        paths = build_paths(await self.jobs(user_id), ctx.candidate, limit=50)
        path = next((p for p in paths if p.slug == slug), None) if slug else _direction(paths)
        if path is None:
            return None, []
        return path, build_skill_plan(
            path, ctx.candidate,
            categories={t.slug: t.category for t in load_taxonomy()},
            resources=await self._resources(),
            roadmap_positions=await self._roadmap_positions(user_id),
        )

    async def resume_analysis(
        self, user_id: uuid.UUID, resume: Resume
    ) -> tuple[ResumeAnalysis, CareerPath | None]:
        ctx = await self.candidate(user_id)
        direction = _direction(build_paths(await self.jobs(user_id), ctx.candidate, limit=50))
        return _analyse(resume, direction), direction

    async def overview(self, user_id: uuid.UUID) -> Overview:
        ctx = await self.candidate(user_id)
        paths = build_paths(await self.jobs(user_id), ctx.candidate, limit=50)
        direction = _direction(paths)
        roadmap = await self._roadmap(user_id)
        steps: list[SkillStep] = []
        if direction is not None:
            steps = build_skill_plan(
                direction, ctx.candidate,
                categories={t.slug: t.category for t in load_taxonomy()},
                resources=await self._resources(),
                roadmap_positions=await self._roadmap_positions(user_id),
            )
        applications = await self._application_counts(user_id)
        resume = await self._latest_resume(user_id)
        analysis = (
            _analyse(resume, direction) if resume is not None and resume.extracted_text else None
        )

        return Overview(
            direction=direction,
            direction_summary=_direction_summary(direction, ctx),
            next_actions=await self._next_actions(user_id, ctx, direction, roadmap, analysis),
            journey=_journey(ctx, direction, roadmap, applications),
            roadmap=roadmap,
            opportunities=await self._opportunities(user_id),
            skills=tuple(steps[:3]),
            notes=_notes(ctx),
            has_resume=ctx.has_resume,
        )

    # ------------------------------------------------------------------ helpers

    async def _resources(self) -> list[Resource]:
        rows = (
            await self._s.execute(select(LearningResource).where(LearningResource.is_active))
        ).scalars().all()
        return [
            Resource(
                id=str(r.id), title=r.title, provider=r.provider, url=r.url, type=r.type,
                level=r.level, est_hours=r.est_hours, cost=r.cost, skills=tuple(r.skills),
            )
            for r in rows
        ]

    async def _active_recommendation(self, user_id: uuid.UUID) -> LearningRecommendation | None:
        return (
            await self._s.execute(
                select(LearningRecommendation)
                .where(
                    LearningRecommendation.user_id == user_id,
                    LearningRecommendation.status == "active",
                )
                .order_by(LearningRecommendation.created_at.desc())
                .limit(1)
            )
        ).scalars().first()

    async def _milestones(self, rec_id: uuid.UUID) -> list[RoadmapMilestone]:
        return list(
            (
                await self._s.execute(
                    select(RoadmapMilestone)
                    .where(RoadmapMilestone.recommendation_id == rec_id)
                    .order_by(RoadmapMilestone.order_index)
                )
            ).scalars().all()
        )

    async def _roadmap_positions(self, user_id: uuid.UUID) -> dict[str, int]:
        rec = await self._active_recommendation(user_id)
        if rec is None:
            return {}
        return {m.skill_slug: i + 1 for i, m in enumerate(await self._milestones(rec.id))}

    async def _roadmap(self, user_id: uuid.UUID) -> RoadmapBrief | None:
        rec = await self._active_recommendation(user_id)
        if rec is None:
            return None
        milestones = await self._milestones(rec.id)
        open_ = [m for m in milestones if m.status != "done"]
        current = next((m for m in open_ if m.status == "in_progress"), open_[0] if open_ else None)
        upcoming = next((m for m in open_ if m is not current), None)
        return RoadmapBrief(
            id=rec.id, title=rec.title,
            done=sum(1 for m in milestones if m.status == "done"), total=len(milestones),
            current=_brief(current), upcoming=_brief(upcoming),
        )

    async def _application_counts(self, user_id: uuid.UUID) -> dict[str, int]:
        rows = (
            await self._s.execute(
                select(Application.status, func.count())
                .where(Application.user_id == user_id, Application.deleted_at.is_(None))
                .group_by(Application.status)
            )
        ).all()
        return {status: int(n) for status, n in rows}

    async def _opportunities(self, user_id: uuid.UUID) -> tuple[Opportunity, ...]:
        rows = (
            await self._s.execute(
                select(JobMatch, Job)
                .join(Job, Job.id == JobMatch.job_id)
                .where(
                    JobMatch.user_id == user_id,
                    JobMatch.status == "ready",
                    Job.deleted_at.is_(None),
                    JobMatch.band.in_(("strong", "good")),
                )
                .order_by(JobMatch.score.desc().nulls_last())
                .limit(3)
            )
        ).all()
        out: list[Opportunity] = []
        for match, job in rows:
            top = max(
                (s for s in match.strengths or [] if s.get("dimension")),
                key=lambda s: float(s.get("contribution") or 0),
                default=None,
            )
            gap = (
                await self._s.execute(
                    select(SkillGap.skill_label)
                    .where(SkillGap.job_match_id == match.id)
                    .order_by(SkillGap.frequency.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            out.append(Opportunity(
                job_id=job.id, title=job.title or "Untitled role", company=job.company,
                band=match.band,
                reason=_DIMENSION_REASON.get(str(top["dimension"])) if top else None,
                gap=f"Missing: {gap}" if gap else None,
            ))
        return tuple(out)

    async def _next_actions(
        self,
        user_id: uuid.UUID,
        ctx: CandidateContext,
        direction: CareerPath | None,
        roadmap: RoadmapBrief | None,
        analysis: ResumeAnalysis | None,
    ) -> tuple[NextAction, ...]:
        actions: list[NextAction] = []
        waiting = (
            await self._s.execute(
                select(Application.id).where(
                    Application.user_id == user_id,
                    Application.status == "awaiting_approval",
                    Application.deleted_at.is_(None),
                ).limit(1)
            )
        ).scalar_one_or_none()
        if waiting is not None:
            actions.append(NextAction(
                "review_approval", "Review the application waiting for you",
                "Nothing is sent until you approve it.", f"/applications/{waiting}",
            ))
        if not ctx.has_resume:
            actions.append(NextAction(
                "upload_resume", "Upload your résumé",
                "It's the quickest way to map your experience and see where it can take you.",
                "/resume",
            ))
        elif not ctx.resume_confirmed and len(ctx.candidate.skills) < 3:
            actions.append(NextAction(
                "confirm_resume", "Check what we read from your résumé",
                "Confirming it fills in your profile, which sharpens every suggestion.",
                "/resume",
            ))
        if analysis is not None:
            high = next((i for i in analysis.issues if i.severity == "high"), None)
            if high is not None:
                actions.append(NextAction(
                    "improve_resume", "Strengthen your résumé", high.problem, "/resume#review",
                ))
        if roadmap is not None and roadmap.current is not None:
            verb = "Continue" if roadmap.current.status == "in_progress" else "Start"
            actions.append(NextAction(
                "roadmap", f"{verb}: {roadmap.current.title}",
                f"Step {roadmap.done + 1} of {roadmap.total} on your roadmap.", "/insights#roadmap",
            ))
        if direction is not None:
            for a in direction.next_actions:
                if a.kind == "roadmap" and roadmap is not None:
                    continue
                href = {
                    "apply": f"/career/{direction.slug}#roles",
                    "resume": "/resume#review",
                    "roadmap": "/insights#roadmap",
                    "project": f"/career/{direction.slug}",
                }.get(a.kind)
                actions.append(NextAction(a.kind, a.title, a.detail, href))
        if direction is None and ctx.has_resume:
            actions.append(NextAction(
                "explore", "Explore where your experience could take you",
                "See the role families your skills point to, and why.", "/career",
            ))
        unique: list[NextAction] = []
        for action in actions:
            if all(action.title != kept.title for kept in unique):
                unique.append(action)
        return tuple(unique[:3])


def _job_skills(items: Iterable[dict[str, object]] | None, required: bool) -> Iterable[JobSkill]:
    for item in items or []:
        slug = str(item.get("slug") or "").strip()
        if slug:
            yield JobSkill(slug=slug, label=str(item.get("label") or slug), required=required)


def _direction(paths: list[CareerPath]) -> CareerPath | None:
    if not paths:
        return None
    first = paths[0]
    if first.stated_target or first.have:
        return first
    return None


def _analyse(resume: Resume, direction: CareerPath | None) -> ResumeAnalysis:
    target = None
    if direction is not None:
        core = sorted(direction.have + direction.missing, key=lambda s: -s.demand)[:8]
        target = TargetSpec(direction.title, tuple((s.slug, s.label) for s in core))
    return analyze_resume(resume.extracted_text or "", page_count=resume.page_count, target=target)


def _brief(m: RoadmapMilestone | None) -> MilestoneBrief | None:
    if m is None:
        return None
    return MilestoneBrief(id=m.id, title=m.title, skill_label=m.skill_label, status=m.status)


def _direction_summary(direction: CareerPath | None, ctx: CandidateContext) -> str:
    if direction is None:
        if not ctx.has_resume:
            return ("Upload your résumé and we'll map the roles your experience points to, "
                    "with the evidence behind each.")
        return ("We don't have enough about your skills yet to suggest a direction. Add the "
                "tools you use to your profile, or check what we read from your résumé.")
    if direction.stated_target:
        return f"You're aiming for {direction.title} roles. {direction.fit_explanation}"
    return (f"Based on your experience, {direction.title} roles look like a relevant path. "
            f"{direction.why}")


def _journey(
    ctx: CandidateContext,
    direction: CareerPath | None,
    roadmap: RoadmapBrief | None,
    applications: dict[str, int],
) -> tuple[JourneyStage, ...]:
    sent = sum(applications.get(s, 0) for s in _ACTIVE_APPLICATION)
    interviewing = applications.get("interview", 0) + applications.get("offer", 0)
    core = len(direction.have) + len(direction.missing) if direction else 0
    stages = [
        ("profile", "Your profile", ctx.has_resume and len(ctx.candidate.skills) >= 3,
         "Résumé read and skills mapped" if ctx.has_resume else "Add your résumé"),
        ("skills", "Skills", bool(direction and direction.coverage >= 0.65),
         f"{len(direction.have)} of {core} core skills for {direction.title}"
         if direction else "Pick a direction to measure against"),
        ("proof", "Proof of work",
         ctx.projects >= 2 or bool(roadmap and roadmap.done >= 1),
         f"{ctx.projects} project{'s' if ctx.projects != 1 else ''} on your profile"),
        ("applications", "Applications", sent >= 1,
         f"{sent} sent" if sent else "None sent yet"),
        ("target", "Target role", interviewing >= 1,
         "Interviewing" if interviewing else
         (f"A {direction.title} role" if direction else "Your next role")),
    ]
    out: list[JourneyStage] = []
    current_set = False
    for key, label, done, detail in stages:
        if done and not current_set:
            status: Literal["done", "current", "upcoming"] = "done"
        elif not current_set:
            status, current_set = "current", True
        else:
            status = "upcoming"
        out.append(JourneyStage(key, label, status, detail))
    return tuple(out)


def _notes(ctx: CandidateContext) -> tuple[str, ...]:
    notes: list[str] = []
    if not ctx.candidate.preferred_roles:
        notes.append("You haven't set a target role, so directions are inferred from your skills. "
                     "Add one in your profile to focus the guidance.")
    if 0 < len(ctx.candidate.skills) < 3:
        notes.append("We know only a few of your skills, so these suggestions are rough.")
    return tuple(notes)

