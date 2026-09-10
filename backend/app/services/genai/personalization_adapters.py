"""Procedural Personalization Adapters for SmartWake AI (Phase 4.5 Step 4).

Translates a PersonalizedChallengeProfile (produced by Step 3) into strictly typed,
generator-compatible parameter outputs for each canonical challenge type.

ARCHITECTURE
============
Phase 3 -> authoritative challenge_type + difficulty_level
      |
Phase 4.5 Step 3 -> PersonalizedChallengeProfile
      |
Phase 4.5 Step 4 (THIS MODULE) -> typed AdapterOutput
      |
future Step 5 dispatcher -> existing generator

CRITICAL INVARIANTS
===================
1. Pure deterministic translation -- identical inputs produce identical outputs.
2. No LLM calls, no Gemini, no network, no DB, no ORM, no randomization.
3. challenge_type and difficulty_level are IMMUTABLE -- preserved exactly from input.
4. No actual challenge content is generated (no questions, sequences, sentences, routines).
5. Strict typed Pydantic outputs only -- no Dict[str, Any] anywhere.
6. Unsupported personalization fields are silently omitted, not injected.
7. Wrong parameter model vs. challenge type is rejected immediately.
8. Forbidden and unknown challenge types are rejected immediately.
9. desired_duration_seconds is treated as generation-style sizing hint only.

SCOPE
=====
This module is ONLY the adapter boundary.
Step 5 (dispatcher) and challenge generators are NOT implemented here.
"""
from typing import Literal, Optional, Union
from pydantic import BaseModel, ConfigDict, Field

from backend.app.schemas.personalization_content_schemas import (
    CanonicalChallengeType,
    CanonicalDifficultyLevel,
    DancePersonalizationParams,
    MathPersonalizationParams,
    MemoryPersonalizationParams,
    PersonalizedChallengeProfile,
    PushUpPersonalizationParams,
    TongueTwisterPersonalizationParams,
    VALID_CANONICAL_CHALLENGE_TYPES,
    VALID_CANONICAL_DIFFICULTIES,
)
from backend.app.core.constants import FORBIDDEN_CHALLENGE_TYPES


# =============================================================================
# ADAPTER-SPECIFIC EXCEPTIONS
# =============================================================================

class AdapterError(ValueError):
    """Base exception for personalization adapter errors (Step 4)."""
    pass


class AdapterTypeError(AdapterError):
    """Raised when the challenge type is forbidden or not recognised by adapters."""
    pass


class AdapterDifficultyError(AdapterError):
    """Raised when the difficulty level is invalid or unknown."""
    pass


class AdapterParameterMismatchError(AdapterError):
    """Raised when typed_parameters does not match the expected model for challenge_type."""
    pass


# =============================================================================
# TYPED ADAPTER OUTPUT MODELS
# =============================================================================

class MathPersonalizationAdapterOutput(BaseModel):
    """Typed adapter output for the Phase 4.2 MathChallengeGenerator.

    Contains only fields that the existing math generator and prompt builder
    can consume. No arbitrary fields are allowed (extra='forbid').
    desired_duration_seconds is carried as a generation-style sizing hint only.
    """

    challenge_type: Literal["math"] = Field(
        ...,
        description="Authoritative canonical challenge type -- always 'math'.",
    )
    difficulty_level: CanonicalDifficultyLevel = Field(
        ...,
        description="Authoritative concrete difficulty tier -- immutable.",
    )
    focus_topic: Optional[str] = Field(
        default=None,
        max_length=30,
        description=(
            "Optional thematic framing carried from MathPersonalizationParams.focus_topic. "
            "Intended to inform preferred_theme in SafePersonalizationContext."
        ),
    )
    preferred_operation: Optional[
        Literal["addition", "subtraction", "multiplication", "division", "mixed"]
    ] = Field(
        default=None,
        description=(
            "Preferred arithmetic operation style carried from MathPersonalizationParams. "
            "Passed through to the prompt builder as a generation hint within tier bounds."
        ),
    )
    operand_scale_preference: Optional[Literal["standard", "compact"]] = Field(
        default=None,
        description=(
            "Operand sizing preference carried from MathPersonalizationParams. "
            "Used as a generation-style hint within difficulty-tier bounds."
        ),
    )
    desired_duration_seconds: Optional[int] = Field(
        default=None,
        ge=5,
        le=300,
        description=(
            "Generation-style sizing hint from SafePersonalizationContext.desired_duration_seconds. "
            "NEVER used to change difficulty. NEVER used as an ML target or alarm time."
        ),
    )

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class MemoryPersonalizationAdapterOutput(BaseModel):
    """Typed adapter output for the Phase 4.3 MemoryChallengeGenerator.

    Carries only fields accepted by the existing generator's preferred_mode
    parameter and SafePersonalizationContext. No arbitrary fields allowed.
    """

    challenge_type: Literal["memory"] = Field(
        ...,
        description="Authoritative canonical challenge type -- always 'memory'.",
    )
    difficulty_level: CanonicalDifficultyLevel = Field(
        ...,
        description="Authoritative concrete difficulty tier -- immutable.",
    )
    preferred_mode: Optional[
        Literal[
            "visual_sequence",
            "spatial_pattern_recall",
            "dynamic_spatial_path",
            "symbol_chronological_order",
        ]
    ] = Field(
        default=None,
        description=(
            "Preferred recall mode carried from MemoryPersonalizationParams. "
            "Passed as preferred_mode to MemoryChallengeGenerator.generate_memory_challenge()."
        ),
    )
    palette_theme: Optional[
        Literal["colors", "geometric_shapes", "cardinal_directions", "emojis"]
    ] = Field(
        default=None,
        description=(
            "Non-numeric palette theme carried from MemoryPersonalizationParams. "
            "Intended to inform preferred_theme in SafePersonalizationContext."
        ),
    )
    desired_duration_seconds: Optional[int] = Field(
        default=None,
        ge=5,
        le=300,
        description=(
            "Generation-style sizing hint. "
            "NEVER used to change difficulty. NEVER used as an ML target or alarm time."
        ),
    )

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class TongueTwisterPersonalizationAdapterOutput(BaseModel):
    """Typed adapter output for the Phase 4.4 TongueTwisterChallengeGenerator.

    Carries only fields the existing generator or prompt builder can consume.
    """

    challenge_type: Literal["tongue_twister"] = Field(
        ...,
        description="Authoritative canonical challenge type -- always 'tongue_twister'.",
    )
    difficulty_level: CanonicalDifficultyLevel = Field(
        ...,
        description="Authoritative concrete difficulty tier -- immutable.",
    )
    target_sound_family: Optional[
        Literal["sibilants", "plosives", "liquids", "nasals", "any"]
    ] = Field(
        default=None,
        description=(
            "Orthographic sound family carried from TongueTwisterPersonalizationParams. "
            "Intended to inform prompt instructions within Phase 4.4 generator."
        ),
    )
    theme_style: Optional[
        Literal["nature", "animals", "workday", "whimsical", "rhyme"]
    ] = Field(
        default=None,
        description=(
            "Passage thematic style carried from TongueTwisterPersonalizationParams. "
            "Intended to inform preferred_theme in SafePersonalizationContext."
        ),
    )
    desired_duration_seconds: Optional[int] = Field(
        default=None,
        ge=5,
        le=300,
        description=(
            "Generation-style sizing hint. "
            "NEVER used to change difficulty. NEVER used as an ML target or alarm time."
        ),
    )

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class DancePersonalizationAdapterOutput(BaseModel):
    """Typed adapter output for the Dance challenge procedural generation layer.

    Dance does NOT have a GenAI generator (future scope). This output provides
    a strictly typed procedural parameter map for a future dance generation or
    execution layer. No AI generator is called or created here.
    """

    challenge_type: Literal["dance"] = Field(
        ...,
        description="Authoritative canonical challenge type -- always 'dance'.",
    )
    difficulty_level: CanonicalDifficultyLevel = Field(
        ...,
        description="Authoritative concrete difficulty tier -- immutable.",
    )
    movement_style: Optional[
        Literal["rhythm_groove", "arm_raises", "step_touch", "standard"]
    ] = Field(
        default=None,
        description=(
            "Procedural movement routine style from DancePersonalizationParams. "
            "Informs future procedural routine selection only. No AI generation."
        ),
    )
    pacing: Optional[Literal["slow", "moderate", "dynamic"]] = Field(
        default=None,
        description=(
            "Procedural tempo pacing from DancePersonalizationParams. "
            "Informs future procedural timing selection only. No AI generation."
        ),
    )
    desired_duration_seconds: Optional[int] = Field(
        default=None,
        ge=5,
        le=300,
        description=(
            "Generation-style sizing hint from SafePersonalizationContext. "
            "NEVER changes difficulty, alarm time, or dance routine content."
        ),
    )

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class PushUpPersonalizationAdapterOutput(BaseModel):
    """Typed adapter output for the Push-Up challenge procedural generation layer.

    Push-ups do NOT have a GenAI generator (future scope). This output provides
    a strictly typed procedural parameter map for a future push-up generation or
    execution layer. No AI generator is called or created here.
    """

    challenge_type: Literal["push_ups"] = Field(
        ...,
        description="Authoritative canonical challenge type -- always 'push_ups'.",
    )
    difficulty_level: CanonicalDifficultyLevel = Field(
        ...,
        description="Authoritative concrete difficulty tier -- immutable.",
    )
    cadence_tempo: Optional[Literal["steady", "tempo_pause", "standard"]] = Field(
        default=None,
        description=(
            "Cadence and pacing emphasis from PushUpPersonalizationParams. "
            "Informs future procedural rep timing only. No AI generation."
        ),
    )
    target_rep_styling: Optional[Literal["tier_min", "tier_median", "tier_max"]] = Field(
        default=None,
        description=(
            "Rep count styling within tier range from PushUpPersonalizationParams. "
            "Instructs future procedural layer which tier boundary to target. "
            "NEVER invents repetition counts outside existing policy."
        ),
    )
    desired_duration_seconds: Optional[int] = Field(
        default=None,
        ge=5,
        le=300,
        description=(
            "Generation-style sizing hint from SafePersonalizationContext. "
            "NEVER changes difficulty, alarm time, or rep counts."
        ),
    )

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


# Convenience union type for the dispatcher (Step 5)
PersonalizationAdapterOutput = Union[
    MathPersonalizationAdapterOutput,
    MemoryPersonalizationAdapterOutput,
    TongueTwisterPersonalizationAdapterOutput,
    DancePersonalizationAdapterOutput,
    PushUpPersonalizationAdapterOutput,
]


# =============================================================================
# INTERNAL VALIDATION HELPERS
# =============================================================================

def _validate_type_and_difficulty(profile: PersonalizedChallengeProfile) -> None:
    """Enforce type-safety and immutability checks on the incoming profile.

    Does NOT re-run Step 3s full content-safety policy.
    Enforces only what the adapter boundary must own:
    - Forbidden challenge types are rejected.
    - Unknown challenge types are rejected.
    - Invalid difficulty levels are rejected.

    Args:
        profile: Validated PersonalizedChallengeProfile from Step 3.

    Raises:
        AdapterTypeError: If challenge_type is forbidden or unknown.
        AdapterDifficultyError: If difficulty_level is not a concrete canonical tier.
    """
    ctype: str = profile.challenge_type
    diff: str = profile.difficulty_level

    if ctype in FORBIDDEN_CHALLENGE_TYPES:
        raise AdapterTypeError(
            f"Adapter received a forbidden challenge type '{ctype}'. "
            "Forbidden types must never reach the adapter layer."
        )
    if ctype not in VALID_CANONICAL_CHALLENGE_TYPES:
        raise AdapterTypeError(
            f"Adapter received an unknown challenge type '{ctype}'. "
            f"Supported types: {sorted(VALID_CANONICAL_CHALLENGE_TYPES)}."
        )
    if diff not in VALID_CANONICAL_DIFFICULTIES:
        raise AdapterDifficultyError(
            f"Adapter received an invalid difficulty level '{diff}'. "
            "Must be one of: 'easy', 'medium', 'hard'."
        )


# =============================================================================
# PER-TYPE ADAPTER FUNCTIONS
# =============================================================================

def _adapt_math(profile: PersonalizedChallengeProfile) -> MathPersonalizationAdapterOutput:
    """Translate a math PersonalizedChallengeProfile into MathPersonalizationAdapterOutput.

    Maps only MathPersonalizationParams fields supported by the Phase 4.2 generator.
    Preserves authoritative challenge_type='math' and difficulty_level exactly.
    Extracts desired_duration_seconds from SafePersonalizationContext as a sizing hint.

    Rules enforced:
    - typed_parameters must be MathPersonalizationParams (or None).
    - Does not generate any question, expression, operand, or answer.
    - Does not bypass Phase 4.2 validation.
    - Unsupported personalization fields are not passed through.

    Args:
        profile: PersonalizedChallengeProfile with challenge_type='math'.

    Returns:
        MathPersonalizationAdapterOutput with immutable type/difficulty.

    Raises:
        AdapterParameterMismatchError: If typed_parameters is not MathPersonalizationParams.
    """
    params = profile.typed_parameters
    if params is not None and not isinstance(params, MathPersonalizationParams):
        raise AdapterParameterMismatchError(
            f"Math adapter received typed_parameters of type '{type(params).__name__}'. "
            "Expected MathPersonalizationParams or None."
        )

    math_params: Optional[MathPersonalizationParams] = (
        params if isinstance(params, MathPersonalizationParams) else None
    )

    return MathPersonalizationAdapterOutput(
        challenge_type="math",
        difficulty_level=profile.difficulty_level,
        focus_topic=math_params.focus_topic if math_params is not None else None,
        preferred_operation=math_params.preferred_operation if math_params is not None else None,
        operand_scale_preference=math_params.operand_scale_preference if math_params is not None else None,
        desired_duration_seconds=profile.safe_context.desired_duration_seconds,
    )


def _adapt_memory(profile: PersonalizedChallengeProfile) -> MemoryPersonalizationAdapterOutput:
    """Translate a memory PersonalizedChallengeProfile into MemoryPersonalizationAdapterOutput.

    Maps only MemoryPersonalizationParams fields supported by the Phase 4.3 generator.
    Preserves authoritative challenge_type='memory' and difficulty_level exactly.

    Rules enforced:
    - typed_parameters must be MemoryPersonalizationParams (or None).
    - Does not generate any sequence, pattern, or numeric recall data.
    - Does not introduce number-guessing behavior.
    - Does not bypass Phase 4.3 validation.

    Args:
        profile: PersonalizedChallengeProfile with challenge_type='memory'.

    Returns:
        MemoryPersonalizationAdapterOutput with immutable type/difficulty.

    Raises:
        AdapterParameterMismatchError: If typed_parameters is not MemoryPersonalizationParams.
    """
    params = profile.typed_parameters
    if params is not None and not isinstance(params, MemoryPersonalizationParams):
        raise AdapterParameterMismatchError(
            f"Memory adapter received typed_parameters of type '{type(params).__name__}'. "
            "Expected MemoryPersonalizationParams or None."
        )

    mem_params: Optional[MemoryPersonalizationParams] = (
        params if isinstance(params, MemoryPersonalizationParams) else None
    )

    return MemoryPersonalizationAdapterOutput(
        challenge_type="memory",
        difficulty_level=profile.difficulty_level,
        preferred_mode=mem_params.preferred_mode if mem_params is not None else None,
        palette_theme=mem_params.palette_theme if mem_params is not None else None,
        desired_duration_seconds=profile.safe_context.desired_duration_seconds,
    )


def _adapt_tongue_twister(
    profile: PersonalizedChallengeProfile,
) -> TongueTwisterPersonalizationAdapterOutput:
    """Translate a tongue_twister PersonalizedChallengeProfile.

    Maps only TongueTwisterPersonalizationParams fields supported by Phase 4.4 generator.
    Preserves authoritative challenge_type='tongue_twister' and difficulty_level exactly.

    Rules enforced:
    - typed_parameters must be TongueTwisterPersonalizationParams (or None).
    - Does not generate any tongue twister sentence.
    - Does not determine repetitions outside Phase 4.4 policy.
    - Does not bypass Phase 4.4 validation.

    Args:
        profile: PersonalizedChallengeProfile with challenge_type='tongue_twister'.

    Returns:
        TongueTwisterPersonalizationAdapterOutput with immutable type/difficulty.

    Raises:
        AdapterParameterMismatchError: If typed_parameters is not TongueTwisterPersonalizationParams.
    """
    params = profile.typed_parameters
    if params is not None and not isinstance(params, TongueTwisterPersonalizationParams):
        raise AdapterParameterMismatchError(
            f"Tongue twister adapter received typed_parameters of type '{type(params).__name__}'. "
            "Expected TongueTwisterPersonalizationParams or None."
        )

    tt_params: Optional[TongueTwisterPersonalizationParams] = (
        params if isinstance(params, TongueTwisterPersonalizationParams) else None
    )

    return TongueTwisterPersonalizationAdapterOutput(
        challenge_type="tongue_twister",
        difficulty_level=profile.difficulty_level,
        target_sound_family=tt_params.target_sound_family if tt_params is not None else None,
        theme_style=tt_params.theme_style if tt_params is not None else None,
        desired_duration_seconds=profile.safe_context.desired_duration_seconds,
    )


def _adapt_dance(profile: PersonalizedChallengeProfile) -> DancePersonalizationAdapterOutput:
    """Translate a dance PersonalizedChallengeProfile into DancePersonalizationAdapterOutput.

    Dance has no GenAI generator. This produces a procedural parameter map ONLY.
    Preserves authoritative challenge_type='dance' and difficulty_level exactly.

    Rules enforced:
    - typed_parameters must be DancePersonalizationParams (or None).
    - Does not create a routine, call AI, call computer vision, or call an LLM.
    - desired_duration_seconds is a generation-style hint only.
    - Does not change difficulty or alarm time.

    Args:
        profile: PersonalizedChallengeProfile with challenge_type='dance'.

    Returns:
        DancePersonalizationAdapterOutput with immutable type/difficulty.

    Raises:
        AdapterParameterMismatchError: If typed_parameters is not DancePersonalizationParams.
    """
    params = profile.typed_parameters
    if params is not None and not isinstance(params, DancePersonalizationParams):
        raise AdapterParameterMismatchError(
            f"Dance adapter received typed_parameters of type '{type(params).__name__}'. "
            "Expected DancePersonalizationParams or None."
        )

    dance_params: Optional[DancePersonalizationParams] = (
        params if isinstance(params, DancePersonalizationParams) else None
    )

    return DancePersonalizationAdapterOutput(
        challenge_type="dance",
        difficulty_level=profile.difficulty_level,
        movement_style=dance_params.movement_style if dance_params is not None else None,
        pacing=dance_params.pacing if dance_params is not None else None,
        desired_duration_seconds=profile.safe_context.desired_duration_seconds,
    )


def _adapt_push_ups(profile: PersonalizedChallengeProfile) -> PushUpPersonalizationAdapterOutput:
    """Translate a push_ups PersonalizedChallengeProfile into PushUpPersonalizationAdapterOutput.

    Push-ups have no GenAI generator. This produces a procedural parameter map ONLY.
    Preserves authoritative challenge_type='push_ups' and difficulty_level exactly.

    Rules enforced:
    - typed_parameters must be PushUpPersonalizationParams (or None).
    - Does not create challenge execution, call AI, computer vision, or an LLM.
    - Does not invent rep counts outside existing policy.
    - desired_duration_seconds is a generation-style hint only.
    - Does not change difficulty or alarm time.

    Args:
        profile: PersonalizedChallengeProfile with challenge_type='push_ups'.

    Returns:
        PushUpPersonalizationAdapterOutput with immutable type/difficulty.

    Raises:
        AdapterParameterMismatchError: If typed_parameters is not PushUpPersonalizationParams.
    """
    params = profile.typed_parameters
    if params is not None and not isinstance(params, PushUpPersonalizationParams):
        raise AdapterParameterMismatchError(
            f"Push-up adapter received typed_parameters of type '{type(params).__name__}'. "
            "Expected PushUpPersonalizationParams or None."
        )

    pushup_params: Optional[PushUpPersonalizationParams] = (
        params if isinstance(params, PushUpPersonalizationParams) else None
    )

    return PushUpPersonalizationAdapterOutput(
        challenge_type="push_ups",
        difficulty_level=profile.difficulty_level,
        cadence_tempo=pushup_params.cadence_tempo if pushup_params is not None else None,
        target_rep_styling=pushup_params.target_rep_styling if pushup_params is not None else None,
        desired_duration_seconds=profile.safe_context.desired_duration_seconds,
    )


# =============================================================================
# PUBLIC DISPATCH ENTRY-POINT
# =============================================================================

def adapt_profile(profile: PersonalizedChallengeProfile) -> PersonalizationAdapterOutput:
    """Dispatch a PersonalizedChallengeProfile to its per-type adapter.

    This is the sole public entry-point for Step 4. It:
    1. Validates type and difficulty immutability at the adapter boundary.
    2. Dispatches to the correct per-type adapter function.
    3. Returns a strictly typed, frozen adapter output.

    The challenge_type and difficulty_level in the returned output are GUARANTEED
    to be identical to those in the input profile.

    No LLM calls, no DB access, no network calls, no randomization, no challenge content
    is generated by this function or any adapter it dispatches to.

    Args:
        profile: PersonalizedChallengeProfile produced by Phase 4.5 Step 3.

    Returns:
        One of: MathPersonalizationAdapterOutput, MemoryPersonalizationAdapterOutput,
        TongueTwisterPersonalizationAdapterOutput, DancePersonalizationAdapterOutput,
        PushUpPersonalizationAdapterOutput.

    Raises:
        AdapterTypeError: If challenge_type is forbidden or unknown.
        AdapterDifficultyError: If difficulty_level is invalid.
        AdapterParameterMismatchError: If typed_parameters model does not match challenge_type.
    """
    _validate_type_and_difficulty(profile)

    ctype: CanonicalChallengeType = profile.challenge_type

    if ctype == "math":
        return _adapt_math(profile)
    elif ctype == "memory":
        return _adapt_memory(profile)
    elif ctype == "tongue_twister":
        return _adapt_tongue_twister(profile)
    elif ctype == "dance":
        return _adapt_dance(profile)
    else:
        # ctype == "push_ups" -- all canonical types are covered above
        return _adapt_push_ups(profile)
