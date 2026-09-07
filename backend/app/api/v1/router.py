from fastapi import APIRouter

from app.api.v1 import (
    ai,
    applications,
    approvals,
    auth,
    eval,
    health,
    jobs,
    matches,
    profile,
    resumes,
    roadmaps,
    skill_gaps,
)

api_router = APIRouter()
api_router.include_router(ai.router)
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(eval.router)
api_router.include_router(jobs.router)
api_router.include_router(matches.router)
api_router.include_router(profile.router)
api_router.include_router(resumes.router)
api_router.include_router(roadmaps.router)
api_router.include_router(roadmaps.lr_router)
api_router.include_router(skill_gaps.router)
api_router.include_router(applications.router)
api_router.include_router(approvals.router)
