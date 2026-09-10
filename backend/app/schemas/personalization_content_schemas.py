"""Pydantic schemas and data contracts for AI-Powered Challenge Personalization (Phase 4.5).

Defines strictly typed, bounded domain models for challenge personalization:
- BehavioralPersonalizationSignals: Non-clinical pre-challenge behavioral metrics (T < T0).
- MathPersonalizationParams: Bounded math personalization parameters.
- MemoryPersonalizationParams: Bounded memory personalization parameters.
- TongueTwisterPersonalizationParams: Bounded tongue twister personalization parameters.
- DancePersonalizationParams: Bounded procedural dance personalization parameters.
- PushUpPersonalizationParams: Bounded procedural push-up personalization parameters.
- PersonalizedChallengeProfile: Central application-constructed container coordinating
  authoritative difficulty, canonical type, safe context, behavioral signals, and typed parameters.

CRITICAL INVARIANTS:
1. Extra fields are strictly forbidden across all models (extra="forbid", strict=True).
2. All unbounded dictionaries (Dict[str, Any]) are completely eliminated.
3. SafePersonalizationContext from Phase 4.1 is preserved without modification.
4. challenge_type and difficulty_level remain application-authoritative and immutable.
5. historical_success_rate defaults to None so no-history is never conflated with 100% success.
6. Zero database IDs, PII, credentials, or post-challenge outcomes are permitted.
"""
from typing import List, Literal, Mapping, Optional, Set, Type, Union
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.schemas.challenge_content_schemas import (
    FORBIDDEN_CONTEXT_KEYS,
    SAFE_TOPIC_REGEX,
    SafePersonalizationContext,
)

CanonicalChallengeType = Literal["dance", "math", "memory", "tongue_twister", "push_ups"]
CanonicalDifficultyLevel = Literal["easy", "medium", "hard"]

VALID_CANONICAL_CHALLENGE_TYPES: Set[str] = {
    "dance",
    "math",
    "memory",
    "tongue_twister",
    "push_ups",
}

VALID_CANONICAL_DIFFICULTIES: Set[str] = {"easy", "medium", "hard"}


class BehavioralPersonalizationSignals(BaseModel):
    """Sanitized, non-clinical behavioral signals derived strictly before T0.

    GUARANTEES:
    - recent_snooze_level reflects behavioral snooze events, NOT clinical sleep inertia.
    - historical_success_rate defaults to None (no-history != 100% success).
    - All fields strictly bounded and validated with strict=True, extra="forbid".
    """

    recent_snooze_level: Literal["none", "low", "moderate", "high"] = Field(
        default="none",
        description="Behavioral snooze intensity derived from snooze count strictly prior to T0.",
    )
    is_retry_attempt: bool = Field(
        default=False,
        description="Indicates whether this generation is for a retry following an earlier failed attempt prior to T0.",
    )
    historical_success_rate: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Historical completion success rate (0.0 to 1.0) for this challenge type prior to T0. None indicates no prior history.",
    )
    recent_failure_count: int = Field(
        default=0,
        ge=0,
        le=10,
        description="Count of consecutive recent failures prior to T0.",
    )

    model_config = ConfigDict(extra="forbid", strict=True)


class MathPersonalizationParams(BaseModel):
    """Bounded, typed personalization parameters for AI-generated math challenges."""

    focus_topic: Optional[str] = Field(
        default=None,
        max_length=30,
        description="Optional thematic framing within tier (e.g., 'astronomy', 'budgeting', 'morning_routine').",
    )
    preferred_operation: Optional[
        Literal["addition", "subtraction", "multiplication", "division", "mixed"]
    ] = Field(
        default=None,
        description="Preferred operation style within tier bounds.",
    )
    operand_scale_preference: Optional[Literal["standard", "compact"]] = Field(
        default=None,
        description="Styling preference for operand sizing within difficulty tier bounds.",
    )

    model_config = ConfigDict(extra="forbid", strict=True)

    @field_validator("focus_topic")
    @classmethod
    def validate_focus_topic(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        clean = v.strip()
        if not clean:
            return None
        if any(ord(c) < 32 for c in clean):
            raise ValueError("focus_topic cannot contain control characters or newlines.")
        if not SAFE_TOPIC_REGEX.match(clean):
            raise ValueError(
                f"focus_topic '{clean}' contains invalid characters. "
                "Only alphanumeric characters, spaces, hyphens, and underscores are allowed."
            )
        if len(clean) > 30:
            raise ValueError("focus_topic cannot exceed 30 characters.")
        return clean


class MemoryPersonalizationParams(BaseModel):
    """Bounded, typed personalization parameters for AI-generated memory challenges.

    CRITICAL: Non-numeric recall only. Number guessing or numeric memory parameters are strictly prohibited.
    """

    preferred_mode: Optional[
        Literal[
            "visual_sequence",
            "spatial_pattern_recall",
            "dynamic_spatial_path",
            "symbol_chronological_order",
        ]
    ] = Field(
        default=None,
        description="Recall mode preference within tier.",
    )
    palette_theme: Optional[
        Literal["colors", "geometric_shapes", "cardinal_directions", "emojis"]
    ] = Field(
        default=None,
        description="Non-numeric symbol theme for memory items.",
    )

    model_config = ConfigDict(extra="forbid", strict=True)


class TongueTwisterPersonalizationParams(BaseModel):
    """Bounded, typed personalization parameters for AI-generated tongue twister challenges."""

    target_sound_family: Optional[
        Literal["sibilants", "plosives", "liquids", "nasals", "any"]
    ] = Field(
        default=None,
        description="Orthographic sound pattern focus family.",
    )
    theme_style: Optional[
        Literal["nature", "animals", "workday", "whimsical", "rhyme"]
    ] = Field(
        default=None,
        description="Passage thematic style.",
    )

    model_config = ConfigDict(extra="forbid", strict=True)


class DancePersonalizationParams(BaseModel):
    """Bounded procedural personalization parameters for dance wake challenges.

    NOTE: Procedural generation remains authoritative. AI generation is explicitly FUTURE SCOPE.
    """

    movement_style: Optional[
        Literal["rhythm_groove", "arm_raises", "step_touch", "standard"]
    ] = Field(
        default=None,
        description="Procedural movement routine style.",
    )
    pacing: Optional[Literal["slow", "moderate", "dynamic"]] = Field(
        default=None,
        description="Procedural tempo pacing.",
    )

    model_config = ConfigDict(extra="forbid", strict=True)


class PushUpPersonalizationParams(BaseModel):
    """Bounded procedural personalization parameters for push-up wake challenges.

    NOTE: Procedural generation remains authoritative. AI generation is explicitly FUTURE SCOPE.
    """

    cadence_tempo: Optional[Literal["steady", "tempo_pause", "standard"]] = Field(
        default=None,
        description="Cadence and pacing emphasis.",
    )
    target_rep_styling: Optional[Literal["tier_min", "tier_median", "tier_max"]] = Field(
        default=None,
        description="Rep count styling within tier range.",
    )

    model_config = ConfigDict(extra="forbid", strict=True)


# Union of all supported typed parameter models
PersonalizationParamsType = Union[
    MathPersonalizationParams,
    MemoryPersonalizationParams,
    TongueTwisterPersonalizationParams,
    DancePersonalizationParams,
    PushUpPersonalizationParams,
]

CHALLENGE_TYPE_TO_PARAMS_MAP: Mapping[
    CanonicalChallengeType,
    Type[PersonalizationParamsType],
] = {
    "math": MathPersonalizationParams,
    "memory": MemoryPersonalizationParams,
    "tongue_twister": TongueTwisterPersonalizationParams,
    "dance": DancePersonalizationParams,
    "push_ups": PushUpPersonalizationParams,
}


class PersonalizedChallengeProfile(BaseModel):
    """Application-constructed container coordinating all challenge personalization inputs.

    GUARANTEES:
    - Zero database IDs (user_id, alarm_id, session_id).
    - Zero PII (name, email, phone, credentials).
    - Zero raw ORM objects or database records.
    - Zero post-challenge outcomes or current verification results.
    - Zero unbounded Dict[str, Any] structures.
    - Strict difficulty and type immutability.
    """

    challenge_type: CanonicalChallengeType = Field(
        ...,
        description="Authoritative canonical challenge type.",
    )
    difficulty_level: CanonicalDifficultyLevel = Field(
        ...,
        description="Authoritative concrete difficulty tier ('easy', 'medium', 'hard').",
    )
    safe_context: SafePersonalizationContext = Field(
        default_factory=SafePersonalizationContext,
        description="Sanitized explicit user preferences from Phase 4.1.",
    )
    behavioral_signals: BehavioralPersonalizationSignals = Field(
        default_factory=BehavioralPersonalizationSignals,
        description="Bounded behavioral signals strictly before T0.",
    )
    recent_structural_signatures: List[str] = Field(
        default_factory=list,
        max_length=5,
        description="Deterministic historical content signatures (T < T0) to avoid structural repetition.",
    )
    typed_parameters: Optional[PersonalizationParamsType] = Field(
        default=None,
        description="Strictly typed, bounded personalization parameters for the canonical challenge type.",
    )

    model_config = ConfigDict(extra="forbid", strict=True)

    @field_validator("recent_structural_signatures")
    @classmethod
    def validate_signatures(cls, signatures: List[str]) -> List[str]:
        """Validate historical structural signatures list."""
        if len(signatures) > 5:
            raise ValueError("recent_structural_signatures cannot exceed 5 items.")
        validated: List[str] = []
        for sig in signatures:
            if not isinstance(sig, str):
                raise ValueError("Each signature must be a string.")
            clean = sig.strip()
            if not clean:
                raise ValueError("Structural signature cannot be empty or whitespace.")
            if any(ord(c) < 32 for c in clean):
                raise ValueError("Structural signature cannot contain control characters or newlines.")
            if len(clean) > 60:
                raise ValueError("Structural signature cannot exceed 60 characters.")
            # Verify no forbidden identity keys are leaked into signatures
            lower = clean.lower()
            for forbidden in FORBIDDEN_CONTEXT_KEYS:
                if forbidden in lower:
                    raise ValueError(
                        f"Structural signature contains forbidden identity key '{forbidden}'."
                    )
            validated.append(clean)
        return validated

    @model_validator(mode="before")
    @classmethod
    def resolve_typed_parameters(cls, data: object) -> object:
        """Resolve dict-based typed_parameters to the appropriate parameter model before type validation."""
        if isinstance(data, dict):
            ctype = data.get("challenge_type")
            tparams = data.get("typed_parameters")
            if ctype in CHALLENGE_TYPE_TO_PARAMS_MAP and isinstance(tparams, dict):
                data = dict(data)
                data["typed_parameters"] = CHALLENGE_TYPE_TO_PARAMS_MAP[ctype](**tparams)
        return data

    @model_validator(mode="after")
    def validate_typed_parameters_compatibility(self) -> "PersonalizedChallengeProfile":
        """Enforce that typed_parameters matches the authoritative challenge_type."""
        if self.typed_parameters is None:
            return self

        expected_cls = CHALLENGE_TYPE_TO_PARAMS_MAP.get(self.challenge_type)
        if expected_cls and not isinstance(self.typed_parameters, expected_cls):
            raise ValueError(
                f"typed_parameters for challenge_type '{self.challenge_type}' must be of type "
                f"{expected_cls.__name__}, got {type(self.typed_parameters).__name__}."
            )
        return self
