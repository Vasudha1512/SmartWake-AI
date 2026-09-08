"""SmartWake AI - FastAPI Backend Entrypoint."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.core.config import settings
from backend.app.api.router import api_router


def get_application() -> FastAPI:
    """Initialize and configure the FastAPI application instance."""
    application = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description=settings.DESCRIPTION,
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS Middleware configuration
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Root index endpoint
    @application.get("/", tags=["Root"], summary="Root Index")
    def root():
        """Root endpoint returning service info and documentation links."""
        return {
            "status": "healthy",
            "service": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "docs": "/docs",
        }

    # Health check endpoints
    @application.get("/health", tags=["Health"], summary="Health Check")
    @application.get("/health/", include_in_schema=False)
    def root_health():
        """Simple health check endpoint returning service status."""
        return {
            "status": "healthy",
            "service": settings.PROJECT_NAME,
            "version": settings.VERSION,
        }

    # Register modular API router
    application.include_router(api_router, prefix=settings.API_V1_STR)

    return application


app = get_application()
