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

    # Authentication & Security Configuration
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

    def validate_auth_config(self) -> None:
        """Validate that authentication configuration is securely set.

        Raises:
            ValueError: If JWT_SECRET_KEY is missing or less than 32 characters,
                        ACCESS_TOKEN_EXPIRE_MINUTES is not > 0,
                        or JWT_ALGORITHM is not HS256.
        """
        secret = self.JWT_SECRET_KEY.strip() if self.JWT_SECRET_KEY else ""
        if not secret or len(secret) < 32:
            raise ValueError(
                "JWT_SECRET_KEY environment variable is required and must be at least 32 characters. "
                "Please configure a secure JWT_SECRET_KEY in your environment or .env file."
            )
        if not isinstance(self.ACCESS_TOKEN_EXPIRE_MINUTES, int) or self.ACCESS_TOKEN_EXPIRE_MINUTES <= 0:
            raise ValueError(
                "ACCESS_TOKEN_EXPIRE_MINUTES must be an integer greater than 0."
            )
        if self.JWT_ALGORITHM != "HS256":
            raise ValueError(
                "Authentication strictly supports HS256 algorithm only."
            )


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


