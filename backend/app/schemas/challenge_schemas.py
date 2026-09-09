"""Pydantic schemas for Challenge catalog entries."""
from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field


class ChallengeResponse(BaseModel):
    """Response schema representing a persisted Challenge catalog entry."""

    id: int = Field(..., description="Unique challenge ID")
    challenge_type: str = Field(
        ...,
        description="Challenge category ('dance', 'math', 'memory', 'tongue_twister', 'push_ups')",
    )
    difficulty_level: str = Field(
        ..., description="Baseline difficulty tier ('easy', 'medium', 'hard', 'adaptive')"
    )
    title: str = Field(..., description="Human-readable challenge title")
    description: str = Field(..., description="Detailed description of the challenge task")
    template_payload: Optional[str] = Field(
        None, description="Template configuration payload string"
    )
    min_duration_seconds: int = Field(
        ..., description="Minimum expected interaction duration in seconds"
    )
    is_active: bool = Field(..., description="Whether this challenge is active in the catalog")
    created_at: datetime = Field(..., description="Creation timestamp in UTC")

    model_config = ConfigDict(from_attributes=True)


class RuntimeChallengeGenerationRequest(BaseModel):
    """Request schema for generating an in-memory runtime challenge instance."""

    challenge_type: Optional[str] = Field(
        None,
        description="Canonical challenge type ('dance', 'math', 'memory', 'tongue_twister', 'push_ups')",
    )
    template_id: Optional[int] = Field(
        None,
        description="Optional ID of a specific template to generate from",
    )
    difficulty_level: Optional[str] = Field(
        None,
        description="Optional difficulty level ('easy', 'medium', 'hard')",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "challenge_type": "math",
                "difficulty_level": "medium",
            }
        }
    )


class RuntimeChallengeResponse(BaseModel):
    """Response schema representing a generated runtime challenge instance."""

    challenge_id: int = Field(..., description="ID of the underlying template")
    challenge_type: str = Field(..., description="Canonical challenge type")
    difficulty_level: str = Field(..., description="Difficulty level of the challenge")
    title: str = Field(..., description="Challenge title")
    generated_content: Dict[str, Any] = Field(
        ..., description="Concrete generated task content (questions, sequence, steps, text, reps)"
    )
    parameters: Dict[str, Any] = Field(
        ..., description="Configuration parameters applied during generation"
    )
    expected_answer: Optional[Any] = Field(
        None, description="Expected answer or reference structure for future verification when applicable"
    )
    verification_mode: str = Field(
        ..., description="Verification mode to be used in future verification phases"
    )
    min_duration_seconds: int = Field(
        ..., description="Minimum expected interaction duration in seconds"
    )
    generated_at: datetime = Field(..., description="Timestamp of generation in UTC")

    model_config = ConfigDict(from_attributes=True)
