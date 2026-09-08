"""Health and system status routes."""
from fastapi import APIRouter
from backend.app.core.config import settings

router = APIRouter()


@router.get("", summary="Service Health Check")
@router.get("/", include_in_schema=False)
def health_status():
    """Return health status, service name, and version."""
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
    }
