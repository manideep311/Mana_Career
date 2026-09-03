from fastapi import APIRouter

from app.api.v1 import auth, eval, health, jobs, matches, profile, resumes, skill_gaps

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(eval.router)
api_router.include_router(jobs.router)
api_router.include_router(matches.router)
api_router.include_router(profile.router)
api_router.include_router(resumes.router)
api_router.include_router(skill_gaps.router)
