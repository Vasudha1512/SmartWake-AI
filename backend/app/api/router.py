"""Central API Router.

Includes and organizes all modular endpoint routers under the API prefix.
"""
from fastapi import APIRouter
from backend.app.api.alarms import router as alarms_router
from backend.app.api.challenges import router as challenges_router
from backend.app.api.health import router as health_router
from backend.app.api.users import router as users_router
from backend.app.api.wake_sessions import router as wake_sessions_router

api_router = APIRouter()

# Register modular sub-routers
api_router.include_router(health_router, prefix="/health", tags=["Health"])
api_router.include_router(users_router, prefix="/users", tags=["Users"])
api_router.include_router(alarms_router, prefix="/alarms", tags=["Alarms"])
api_router.include_router(wake_sessions_router, prefix="/wake-sessions", tags=["Wake Sessions"])
api_router.include_router(challenges_router, prefix="/challenges", tags=["Challenges"])


