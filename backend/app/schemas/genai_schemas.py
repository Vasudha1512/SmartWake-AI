"""Pydantic schemas and data contracts for Generative AI (Phase 4.0).

Defines request/response contracts for provider abstraction, configuration,
and health inspection.
"""
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.core.constants import FORBIDDEN_CHALLENGE_TYPES, VALID_CHALLENGE_TYPES


class GenAIContentRequest(BaseModel):
    """Domain request contract passed to a GenAI provider."""

    challenge_type: str = Field(
        ...,
        description="Canonical challenge type ('dance', 'math', 'memory', 'tongue_twister', 'push_ups')",
    )
    difficulty_level: str = Field(
        ...,
        description="Concrete difficulty tier ('easy', 'medium', 'hard')",
    )
    user_id: Optional[int] = Field(
        None,
        description="Optional user ID for future personalization context (Phase 4.5)",
    )
    context_payload: Dict[str, Any] = Field(
        default_factory=dict,
        description="Optional pre-challenge telemetry or context metadata",
    )
    custom_instructions: Optional[str] = Field(
        None,
        description="Optional system or prompt guidelines for the provider",
    )

    @field_validator("challenge_type")
    @classmethod
    def validate_type(cls, v: Any) -> str:
        """Enforce canonical challenge types and reject forbidden types."""
        if not isinstance(v, str):
            raise ValueError("challenge_type must be a string.")
        clean = v.strip().lower()
        if clean in FORBIDDEN_CHALLENGE_TYPES:
            raise ValueError(
                f"Forbidden challenge type '{v}'. Memory challenges strictly forbid number guessing."
            )
        if clean not in VALID_CHALLENGE_TYPES:
            raise ValueError(
                f"Invalid challenge type '{v}'. Must be one of: {sorted(list(VALID_CHALLENGE_TYPES))}."
            )
        return clean

    @field_validator("difficulty_level")
    @classmethod
    def validate_difficulty(cls, v: Any) -> str:
        """Enforce concrete difficulty levels ('easy', 'medium', 'hard')."""
        if not isinstance(v, str):
            raise ValueError("difficulty_level must be a string.")
        clean = v.strip().lower()
        if clean not in ("easy", "medium", "hard"):
            raise ValueError(
                f"Invalid difficulty '{v}'. Must be a concrete tier: 'easy', 'medium', or 'hard'."
            )
        return clean

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "challenge_type": "math",
                "difficulty_level": "medium",
                "context_payload": {"snooze_count": 1},
            }
        }
    )


class GenAIGenerationResponse(BaseModel):
    """Domain response contract returned by a GenAI provider."""

    content: Dict[str, Any] = Field(
        ...,
        description="Structured challenge content payload returned by the provider",
    )
    raw_response: Optional[str] = Field(
        None,
        description="Raw string output or completion from the provider if available",
    )
    provider_name: str = Field(
        ...,
        description="Identifier of the provider that generated this response",
    )
    model_name: str = Field(
        ...,
        description="Name of the model utilized for generation",
    )
    latency_ms: float = Field(
        ...,
        ge=0.0,
        description="Elapsed generation duration in milliseconds",
    )
    tokens_used: Optional[int] = Field(
        None,
        description="Reported token consumption if provided by the model API",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional provider diagnostics or generation metadata",
    )

    model_config = ConfigDict(from_attributes=True)


class GenAIProviderHealth(BaseModel):
    """Health and connectivity status of a GenAI provider."""

    is_healthy: bool = Field(
        ...,
        description="Whether the provider is currently reachable and operational",
    )
    provider_name: str = Field(
        ...,
        description="Provider identifier ('mock', 'gemini')",
    )
    model_name: Optional[str] = Field(
        None,
        description="Configured model name for the provider",
    )
    latency_ms: Optional[float] = Field(
        None,
        description="Roundtrip ping latency in milliseconds if tested",
    )
    message: str = Field(
        ...,
        description="Descriptive health status or diagnostic message",
    )
    details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Diagnostic details (e.g. error specifics with keys masked)",
    )

    model_config = ConfigDict(from_attributes=True)


class GenAIConfigSummary(BaseModel):
    """Safe, non-leaking representation of GenAI system configuration."""

    enabled: bool = Field(..., description="Whether GenAI generation is globally enabled")
    provider: str = Field(..., description="Active provider identifier ('mock', 'gemini')")
    model: str = Field(..., description="Configured model identifier")
    timeout_seconds: float = Field(..., description="Configured provider timeout limit")
    max_retries: int = Field(..., description="Configured retry limit before fallback")
    temperature: float = Field(..., description="Configured sampling temperature")
    api_key_configured: bool = Field(..., description="Whether an API key is provided")
    masked_api_key: str = Field(..., description="Masked API key string for safe display")

    model_config = ConfigDict(from_attributes=True)
