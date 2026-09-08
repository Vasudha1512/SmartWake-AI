"""Application configuration and environment settings."""
from typing import List


class Settings:
    PROJECT_NAME: str = "SmartWake AI Backend"
    VERSION: str = "0.1.0"
    DESCRIPTION: str = (
        "FastAPI backend for SmartWake AI - an adaptive, task-gated smart alarm system."
    )
    API_V1_STR: str = "/api/v1"
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ]


settings = Settings()
