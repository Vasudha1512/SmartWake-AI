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


class ChallengeVerificationResult(BaseModel):
    """Domain result schema representing the outcome of verifying a challenge submission."""

    is_successful: bool = Field(..., description="Whether the challenge was successfully completed")
    verification_score: float = Field(
        ..., description="Normalized accuracy or completion score (0.0 to 1.0)"
    )
    verification_result: str = Field(
        ..., description="Descriptive status summary (e.g. 'exact_match', 'failed', 'manual_confirmed')"
    )
    failure_reason: Optional[str] = Field(
        None, description="Diagnostic failure reason if unsuccessful"
    )
    diagnostic_details: Dict[str, Any] = Field(
        default_factory=dict, description="Diagnostic telemetry and verification details"
    )

    model_config = ConfigDict(from_attributes=True)


class ChallengeVerificationRequest(BaseModel):
    """Request payload for validating a user's submission against a runtime challenge."""

    runtime_challenge: Dict[str, Any] = Field(
        ..., description="The RuntimeChallenge object or dictionary generated for this task"
    )
    submission_data: Dict[str, Any] = Field(
        ..., description="User-submitted response data (answers, sequence, confirmed, etc.)"
    )


class ChallengeAttemptStartRequest(BaseModel):
    """Request schema to start a challenge execution attempt for a wake session."""

    user_id: int = Field(..., description="ID of the user attempting the challenge")
    wake_session_id: int = Field(..., description="ID of the active WakeSession")
    challenge_id: Optional[int] = Field(
        default=None, description="Optional specific catalog template ID to attempt"
    )
    challenge_type: Optional[str] = Field(
        default=None, description="Optional challenge category override or verification against session"
    )
    difficulty_level: Optional[str] = Field(
        default=None, description="Optional difficulty tier override ('easy', 'medium', 'hard')"
    )


class ChallengeAttemptSubmitRequest(BaseModel):
    """Request schema for submitting a user's answer or verification payload."""

    user_id: int = Field(..., description="ID of the user submitting the attempt")
    submission_data: Dict[str, Any] = Field(
        ..., description="User-submitted response data (answers, sequence, confirmed, etc.)"
    )


class ChallengeAttemptResponse(BaseModel):
    """Response schema representing a persisted ChallengeAttempt record."""

    id: int = Field(..., description="Unique challenge attempt ID")
    wake_session_id: int = Field(..., description="Associated WakeSession ID")
    challenge_id: Optional[int] = Field(None, description="Associated catalog Challenge ID")
    challenge_type: str = Field(..., description="Challenge category ('math', 'memory', etc.)")
    difficulty_level: str = Field(..., description="Difficulty tier ('easy', 'medium', 'hard')")
    prompt_content: str = Field(
        ..., description="JSON string of runtime generated challenge specifications"
    )
    attempt_number: int = Field(
        ..., description="Attempt sequence number for this session (1, 2, 3...)"
    )
    started_at: datetime = Field(..., description="Timestamp when attempt began in UTC")
    completed_at: Optional[datetime] = Field(None, description="Timestamp when submitted in UTC")
    duration_seconds: Optional[float] = Field(None, description="Completion duration in seconds")
    is_successful: Optional[bool] = Field(
        None, description="Outcome: True=passed, False=failed, None=in-progress"
    )
    verification_result: Optional[str] = Field(
        None, description="Verification status summary / diagnostic JSON"
    )
    verification_score: Optional[float] = Field(
        None, description="Normalized accuracy score (0.0 to 1.0)"
    )
    failure_reason: Optional[str] = Field(
        None, description="Diagnostic failure reason if unsuccessful"
    )
    created_at: datetime = Field(..., description="Record creation timestamp in UTC")

    model_config = ConfigDict(from_attributes=True)
