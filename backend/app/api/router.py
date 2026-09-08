"""Central API Router.

Includes and organizes all modular endpoint routers under the API prefix.
"""
from fastapi import APIRouter
from backend.app.api.health import router as health_router

api_router = APIRouter()

# Register modular sub-routers
api_router.include_router(health_router, prefix="/health", tags=["Health"])
