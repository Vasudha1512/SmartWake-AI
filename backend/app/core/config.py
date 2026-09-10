import os
from typing import List, Optional


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
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./smartwake.db")

    # Generative AI Configuration (Phase 4.0 Foundation)
    GENAI_ENABLED: bool = os.getenv("GENAI_ENABLED", "false").lower() in ("true", "1", "yes")
    GENAI_PROVIDER: str = os.getenv("GENAI_PROVIDER", "mock")
    GENAI_API_KEY: Optional[str] = os.getenv("GENAI_API_KEY", None)
    GENAI_MODEL: str = os.getenv("GENAI_MODEL", "gemini-2.0-flash")
    GENAI_TIMEOUT_SECONDS: float = float(os.getenv("GENAI_TIMEOUT_SECONDS", "5.0"))
    GENAI_MAX_RETRIES: int = int(os.getenv("GENAI_MAX_RETRIES", "1"))
    GENAI_TEMPERATURE: float = float(os.getenv("GENAI_TEMPERATURE", "0.7"))

    @property
    def masked_genai_api_key(self) -> str:
        """Return masked API key for safe telemetry, logging, and health responses."""
        if not self.GENAI_API_KEY:
            return "not_set"
        key = self.GENAI_API_KEY.strip()
        if len(key) <= 8:
            return "***"
        return f"{key[:4]}...{key[-4:]}"


settings = Settings()


