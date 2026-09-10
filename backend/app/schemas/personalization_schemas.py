"""Pydantic schemas and enums for Phase 3.3 Personalization Engine.

Defines the data contracts for decision sources, difficulty levels,
runtime personalization context, and auditable personalization decisions.
"""
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.core.constants import FORBIDDEN_CHALLENGE_TYPES, VALID_CHALLENGE_TYPES


class DecisionSource(str, Enum):
    """Enumeration of all valid decision sources for the Personalization Engine."""

    USER_FIXED = "user_fixed"
    COLD_START_STAGE_0 = "cold_start_stage_0"
    COLD_START_STAGE_1 = "cold_start_stage_1"
    ML_ADAPTIVE = "ml_adaptive"
    GUARDRAIL_CLAMPED = "guardrail_clamped"
    FALLBACK_SAFE = "fallback_safe"


class DifficultyLevel(str, Enum):
    """Canonical difficulty levels for runtime wake-up challenge tasks."""

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class DifficultyPreference(str, Enum):
    """Supported baseline difficulty preferences, including adaptive mode."""

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    ADAPTIVE = "adaptive"


# Canonical sets for fast validation
VALID_DECISION_SOURCES = {e.value for e in DecisionSource}
VALID_DIFFICULTY_LEVELS = {e.value for e in DifficultyLevel}
VALID_DIFFICULTY_PREFERENCES = {e.value for e in DifficultyPreference}


class PersonalizationContext(BaseModel):
    """Input context required by the Personalization Engine to resolve difficulty.

    Encapsulates user state, session state, snooze telemetry, and preference
    configuration available at challenge start (T_0).
    """

    user_id: int = Field(..., gt=0, description="Unique ID of the user")
    wake_session_id: int = Field(..., gt=0, description="Active wake session ID")
    alarm_id: Optional[int] = Field(
        None, gt=0, description="Associated alarm ID if session was triggered by an alarm"
    )
    challenge_type: str = Field(
        ...,
        description="Canonical challenge type ('dance', 'math', 'memory', 'tongue_twister', 'push_ups')",
    )
    difficulty_preference: str = Field(
        default="adaptive",
        description="Baseline difficulty preference ('adaptive', 'easy', 'medium', 'hard')",
    )
    current_session_snooze_count: int = Field(
        default=0, ge=0, description="Total snoozes pressed in the current wake session"
    )
    historical_session_count: int = Field(
        default=0, ge=0, description="Count of historical completed/abandoned wake sessions"
    )
    previous_difficulty: Optional[str] = Field(
        None, description="Previous successful difficulty level if available ('easy', 'medium', 'hard')"
    )

    @field_validator("challenge_type")
    @classmethod
    def validate_challenge_type(cls, v: Any) -> str:
        """Validate that challenge_type is a valid non-forbidden canonical challenge type."""
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

    @field_validator("difficulty_preference")
    @classmethod
    def validate_difficulty_preference(cls, v: Any) -> str:
        """Validate that difficulty_preference is a valid baseline preference."""
        if not isinstance(v, str):
            raise ValueError("difficulty_preference must be a string.")
        clean = v.strip().lower()
        if clean not in VALID_DIFFICULTY_PREFERENCES:
            raise ValueError(
                f"Invalid difficulty preference '{v}'. Must be one of: {sorted(list(VALID_DIFFICULTY_PREFERENCES))}."
            )
        return clean

    @field_validator("previous_difficulty")
    @classmethod
    def validate_previous_difficulty(cls, v: Optional[Any]) -> Optional[str]:
        """Validate previous_difficulty tier if provided."""
        if v is None:
            return None
        if not isinstance(v, str):
            raise ValueError("previous_difficulty must be a string or None.")
        clean = v.strip().lower()
        if clean not in VALID_DIFFICULTY_LEVELS:
            raise ValueError(
                f"Invalid previous difficulty '{v}'. Must be one of: {sorted(list(VALID_DIFFICULTY_LEVELS))}."
            )
        return clean

    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,
        json_schema_extra={
            "example": {
                "user_id": 1,
                "wake_session_id": 42,
                "alarm_id": 10,
                "challenge_type": "math",
                "difficulty_preference": "adaptive",
                "current_session_snooze_count": 1,
                "historical_session_count": 12,
                "previous_difficulty": "medium",
            }
        },
    )


class PersonalizationDecision(BaseModel):
    """Output domain decision produced by the Personalization Engine.

    Captures the final recommended difficulty, the decision source (rule vs ML),
    model confidence, guardrail interventions, and the point-in-time feature snapshot
    for auditability and offline training.
    """

    recommended_difficulty: str = Field(
        ..., description="Resolved challenge difficulty level ('easy', 'medium', 'hard')"
    )
    challenge_type: str = Field(
        ..., description="Immutable user-selected challenge category"
    )
    decision_source: str = Field(
        ...,
        description=(
            "Source policy of the decision ('user_fixed', 'cold_start_stage_0', "
            "'cold_start_stage_1', 'ml_adaptive', 'guardrail_clamped', 'fallback_safe')"
        ),
    )
    model_confidence: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Top class probability if ML inference was executed",
    )
    raw_model_prediction: Optional[str] = Field(
        None, description="Pre-guardrail model prediction if ML inference was executed"
    )
    guardrail_applied: bool = Field(
        default=False, description="True if safety guardrails clamped or adjusted the difficulty"
    )
    guardrail_reason: Optional[str] = Field(
        None, description="Diagnostic explanation if guardrails were applied"
    )
    feature_snapshot: Dict[str, Any] = Field(
        default_factory=dict,
        description="Snapshot of 30 pre-challenge input features at decision time",
    )

    @field_validator("recommended_difficulty")
    @classmethod
    def validate_recommended_difficulty(cls, v: Any) -> str:
        """Validate that recommended difficulty is a concrete easy, medium, or hard level."""
        val = v.value if isinstance(v, DifficultyLevel) else str(v).strip().lower()
        if val not in VALID_DIFFICULTY_LEVELS:
            raise ValueError(
                f"Invalid recommended difficulty '{v}'. Must be one of: {sorted(list(VALID_DIFFICULTY_LEVELS))}."
            )
        return val

    @field_validator("challenge_type")
    @classmethod
    def validate_challenge_type(cls, v: Any) -> str:
        """Validate canonical challenge type."""
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

    @field_validator("decision_source")
    @classmethod
    def validate_decision_source(cls, v: Any) -> str:
        """Validate that decision_source is one of the recognized decision paths."""
        val = v.value if isinstance(v, DecisionSource) else str(v).strip().lower()
        if val not in VALID_DECISION_SOURCES:
            raise ValueError(
                f"Invalid decision source '{v}'. Must be one of: {sorted(list(VALID_DECISION_SOURCES))}."
            )
        return val

    @field_validator("raw_model_prediction")
    @classmethod
    def validate_raw_model_prediction(cls, v: Optional[Any]) -> Optional[str]:
        """Validate raw model prediction if present."""
        if v is None:
            return None
        val = v.value if isinstance(v, DifficultyLevel) else str(v).strip().lower()
        if val not in VALID_DIFFICULTY_LEVELS:
            raise ValueError(
                f"Invalid raw model prediction '{v}'. Must be one of: {sorted(list(VALID_DIFFICULTY_LEVELS))}."
            )
        return val

    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,
        json_schema_extra={
            "example": {
                "recommended_difficulty": "medium",
                "challenge_type": "math",
                "decision_source": "ml_adaptive",
                "model_confidence": 0.82,
                "raw_model_prediction": "medium",
                "guardrail_applied": False,
                "guardrail_reason": None,
                "feature_snapshot": {
                    "user_total_wake_sessions": 12,
                    "current_session_snooze_count": 1,
                },
            }
        },
    )


class AdaptiveChallengeDecision(BaseModel):
    """Authoritative challenge decision produced by AdaptiveDecisionEngine (Phase 3.4).

    Acts as the final runtime contract consumed by runtime challenge generation.
    Captures the concrete final difficulty, preserved challenge type, decision
    source audit trail, session context for traceability, and rationale.
    """

    challenge_type: str = Field(
        ..., description="Immutable user-selected challenge category"
    )
    final_difficulty: str = Field(
        ..., description="Authoritative challenge difficulty level ('easy', 'medium', 'hard')"
    )
    decision_source: str = Field(
        ...,
        description=(
            "Source policy of the decision ('user_fixed', 'cold_start_stage_0', "
            "'cold_start_stage_1', 'ml_adaptive', 'guardrail_clamped', 'fallback_safe')"
        ),
    )
    model_confidence: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Top class probability if ML inference was executed",
    )
    raw_model_prediction: Optional[str] = Field(
        None, description="Pre-guardrail model prediction if ML inference was executed"
    )
    guardrail_applied: bool = Field(
        default=False, description="True if safety guardrails adjusted the candidate difficulty"
    )
    guardrail_reason: Optional[str] = Field(
        None, description="Diagnostic explanation if guardrails were applied"
    )
    user_id: Optional[int] = Field(
        None, description="User ID for auditability and session traceability"
    )
    wake_session_id: Optional[int] = Field(
        None, description="WakeSession ID for auditability and session traceability"
    )
    alarm_id: Optional[int] = Field(
        None, description="Associated Alarm ID if session was triggered by an alarm"
    )
    decision_rationale: Optional[str] = Field(
        None, description="Concise explainable rationale for the final decision"
    )
    feature_snapshot: Dict[str, Any] = Field(
        default_factory=dict,
        description="Snapshot of pre-challenge input features at decision time",
    )

    @property
    def recommended_difficulty(self) -> str:
        """Alias for interoperability with PersonalizationDecision consumers."""
        return self.final_difficulty

    @field_validator("challenge_type")
    @classmethod
    def validate_challenge_type(cls, v: Any) -> str:
        """Validate canonical challenge type."""
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

    @field_validator("final_difficulty")
    @classmethod
    def validate_final_difficulty(cls, v: Any) -> str:
        """Validate that final difficulty is a concrete easy, medium, or hard level."""
        val = v.value if isinstance(v, DifficultyLevel) else str(v).strip().lower()
        if val not in VALID_DIFFICULTY_LEVELS:
            raise ValueError(
                f"Invalid final difficulty '{v}'. Must be one of: {sorted(list(VALID_DIFFICULTY_LEVELS))}."
            )
        return val

    @field_validator("decision_source")
    @classmethod
    def validate_decision_source(cls, v: Any) -> str:
        """Validate that decision_source is one of the recognized decision paths."""
        val = v.value if isinstance(v, DecisionSource) else str(v).strip().lower()
        if val not in VALID_DECISION_SOURCES:
            raise ValueError(
                f"Invalid decision source '{v}'. Must be one of: {sorted(list(VALID_DECISION_SOURCES))}."
            )
        return val

    @field_validator("raw_model_prediction")
    @classmethod
    def validate_raw_model_prediction(cls, v: Optional[Any]) -> Optional[str]:
        """Validate raw model prediction if present."""
        if v is None:
            return None
        val = v.value if isinstance(v, DifficultyLevel) else str(v).strip().lower()
        if val not in VALID_DIFFICULTY_LEVELS:
            raise ValueError(
                f"Invalid raw model prediction '{v}'. Must be one of: {sorted(list(VALID_DIFFICULTY_LEVELS))}."
            )
        return val

    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,
        json_schema_extra={
            "example": {
                "challenge_type": "math",
                "final_difficulty": "medium",
                "decision_source": "ml_adaptive",
                "model_confidence": 0.82,
                "raw_model_prediction": "medium",
                "guardrail_applied": False,
                "guardrail_reason": None,
                "user_id": 1,
                "wake_session_id": 42,
                "alarm_id": 10,
                "decision_rationale": "Stage 2 ML adaptive: model predicted 'medium' with confidence 0.82.",
                "feature_snapshot": {
                    "user_total_wake_sessions": 12,
                    "current_session_snooze_count": 1,
                },
            }
        },
    )
