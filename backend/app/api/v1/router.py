from fastapi import APIRouter

from app.api.v1 import auth, health, jobs, profile, resumes

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(jobs.router)
api_router.include_router(profile.router)
api_router.include_router(resumes.router)
