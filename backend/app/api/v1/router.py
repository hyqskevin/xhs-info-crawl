from fastapi import APIRouter

from app.api.v1.health import router as health_router
from app.api.v1.auth import router as auth_router
from app.api.v1.activities import router as activities_router
from app.api.v1.settings import router as settings_router
from app.api.v1.reports import router as reports_router


api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(activities_router)
api_router.include_router(settings_router)
api_router.include_router(reports_router)
