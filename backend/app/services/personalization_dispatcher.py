"""Personalization Dispatcher and Generator Mapping for SmartWake AI (Phase 4.5 Step 5).

Orchestrates the deterministic mapping boundary from an already-created
PersonalizedChallengeProfile (Phase 4.5 Step 3) through procedural personalization adapters
(Phase 4.5 Step 4) to the appropriate existing challenge generator input contract or
procedural execution path.

ARCHITECTURE
============
PersonalizedChallengeProfile (Step 3)
           ↓
    adapt_profile() / typed adapter output (Step 4)
           ↓
PersonalizationDispatcher (Step 5, THIS MODULE)
           ↓
     challenge_type
        ├── math → Phase 4.2 MathChallengeGenerator contract (MathGeneratorInputArgs)
        ├── memory → Phase 4.3 MemoryChallengeGenerator contract (MemoryGeneratorInputArgs)
        ├── tongue_twister → Phase 4.4 TongueTwisterChallengeGenerator contract (TongueTwisterGeneratorInputArgs)
        ├── dance → Phase 4.5 Procedural Dance Adapter (DancePersonalizationAdapterOutput)
        └── push_ups → Phase 4.5 Procedural PushUp Adapter (PushUpPersonalizationAdapterOutput)

CRITICAL INVARIANTS & STRICT BOUNDARIES
=======================================
1. PURE ORCHESTRATION / MAPPING ONLY:
   - Does NOT choose challenge type or difficulty.
   - Does NOT modify authoritative challenge_type or difficulty_level.
   - Does NOT alter alarm time.
   - Does NOT call an LLM, GenAI provider, or network endpoint.
   - Does NOT access database, ORM models, or storage.
   - Does NOT use user IDs or PII.
   - Does NOT generate challenge content (no math questions, memory sequences, tongue twisters, routines).
   - Does NOT perform verification or evaluation.
   - Does NOT use randomness, UUIDs, or runtime timestamps (100% deterministic).
   - Does NOT modify existing Phase 4.2/4.3/4.4 generators.
   - Does NOT modify Phase 3 ML/personalization code.
   - Does NOT integrate runtime execution (deferred to Phase 4.7).
2. AUTHORITATIVE VALUES:
   - challenge_type is strictly immutable from PersonalizedChallengeProfile.
   - difficulty / difficulty_level is strictly immutable from PersonalizedChallengeProfile.
   - typed_parameters are adapted via Step 4 adapter layer.
   - desired_duration_seconds is ONLY a generation-style sizing hint.
3. STRICT TYPING & ZERO UNTYPED DICTIONARIES:
   - Zero untyped dictionary mappings anywhere in production code.
   - No dynamic reflection, eval(), exec(), or string-based imports.
   - Explicit typed Pydantic models for all inputs, outputs, and dispatch results.
4. DEPENDENCY DIRECTION:
   schemas -> personalization adapters -> dispatcher -> existing generator contracts.
   Generators never import the dispatcher.
"""
from enum import Enum
from typing import Literal, Optional, Type, Union
from pydantic import BaseModel, ConfigDict, Field

from backend.app.core.constants import FORBIDDEN_CHALLENGE_TYPES
from backend.app.core.exceptions import (
    InvalidChallengeTypeError,
    InvalidDifficultyError,
    SmartWakeException,
)
from backend.app.schemas.challenge_content_schemas import SafePersonalizationContext
from backend.app.schemas.personalization_content_schemas import (
    CanonicalChallengeType,
    CanonicalDifficultyLevel,
    PersonalizedChallengeProfile,
    VALID_CANONICAL_CHALLENGE_TYPES,
    VALID_CANONICAL_DIFFICULTIES,
)
from backend.app.services.genai.math_challenge_generator import MathChallengeGenerator
from backend.app.services.genai.memory_challenge_generator import MemoryChallengeGenerator
from backend.app.services.genai.personalization_adapters import (
    AdapterDifficultyError,
    AdapterError,
    AdapterTypeError,
    DancePersonalizationAdapterOutput,
    MathPersonalizationAdapterOutput,
    MemoryPersonalizationAdapterOutput,
    PersonalizationAdapterOutput,
    PushUpPersonalizationAdapterOutput,
    TongueTwisterPersonalizationAdapterOutput,
    _adapt_dance,
    _adapt_math,
    _adapt_memory,
    _adapt_push_ups,
    _adapt_tongue_twister,
)
from backend.app.services.genai.tongue_twister_challenge_generator import (
    TongueTwisterChallengeGenerator,
)


# =============================================================================
# DISPATCHER-SPECIFIC EXCEPTIONS
# =============================================================================

class DispatcherError(SmartWakeException, ValueError):
    """Base domain exception for personalization dispatcher errors (Step 5)."""
    pass


class DispatcherTypeError(DispatcherError, AdapterTypeError, InvalidChallengeTypeError):
    """Raised when the challenge type is forbidden, invalid, or unsupported."""
    pass


class DispatcherDifficultyError(DispatcherError, AdapterDifficultyError, InvalidDifficultyError):
    """Raised when the difficulty level is invalid or unsupported."""
    pass


# =============================================================================
# DISPATCH TARGET IDENTIFIERS
# =============================================================================

class DispatchTarget(str, Enum):
    """Authoritative enumeration of selected generator and adapter dispatch paths."""

    MATH_GENERATOR = "math_challenge_generator"
    MEMORY_GENERATOR = "memory_challenge_generator"
    TONGUE_TWISTER_GENERATOR = "tongue_twister_challenge_generator"
    DANCE_ADAPTER = "dance_procedural_adapter"
    PUSH_UPS_ADAPTER = "push_ups_procedural_adapter"


DispatchTargetPath = Literal[
    "math_challenge_generator",
    "memory_challenge_generator",
    "tongue_twister_challenge_generator",
    "dance_procedural_adapter",
    "push_ups_procedural_adapter",
]


# =============================================================================
# TYPED GENERATOR INPUT MODELS
# =============================================================================

class MathGeneratorInputArgs(BaseModel):
    """Generator-compatible call arguments for Phase 4.2 MathChallengeGenerator.

    Matches exact signature of MathChallengeGenerator.generate_math_challenge:
    (difficulty_level, challenge_type='math', raw_context=..., strict_context=True).
    """

    difficulty_level: CanonicalDifficultyLevel = Field(
        ...,
        description="Authoritative concrete difficulty tier ('easy', 'medium', 'hard').",
    )
    challenge_type: Literal["math"] = Field(
        default="math",
        description="Canonical challenge type -- strictly locked to 'math'.",
    )
    raw_context: SafePersonalizationContext = Field(
        ...,
        description="Sanitized personalization context including sizing and theme hints.",
    )
    strict_context: bool = Field(
        default=True,
        description="Enforces strict context validation in Phase 4.2 generator.",
    )

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class MemoryGeneratorInputArgs(BaseModel):
    """Generator-compatible call arguments for Phase 4.3 MemoryChallengeGenerator.

    Matches exact signature of MemoryChallengeGenerator.generate_memory_challenge:
    (difficulty_level, challenge_type='memory', raw_context=..., strict_context=True, preferred_mode=...).
    """

    difficulty_level: CanonicalDifficultyLevel = Field(
        ...,
        description="Authoritative concrete difficulty tier ('easy', 'medium', 'hard').",
    )
    challenge_type: Literal["memory"] = Field(
        default="memory",
        description="Canonical challenge type -- strictly locked to 'memory'.",
    )
    raw_context: SafePersonalizationContext = Field(
        ...,
        description="Sanitized personalization context including sizing and palette theme hints.",
    )
    strict_context: bool = Field(
        default=True,
        description="Enforces strict context validation in Phase 4.3 generator.",
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
        description="Preferred non-numeric memory recall mode passed directly to generator.",
    )

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class TongueTwisterGeneratorInputArgs(BaseModel):
    """Generator-compatible call arguments for Phase 4.4 TongueTwisterChallengeGenerator.

    Matches exact signature of TongueTwisterChallengeGenerator.generate_tongue_twister_challenge:
    (difficulty_level, challenge_type='tongue_twister', raw_context=..., strict_context=True).
    """

    difficulty_level: CanonicalDifficultyLevel = Field(
        ...,
        description="Authoritative concrete difficulty tier ('easy', 'medium', 'hard').",
    )
    challenge_type: Literal["tongue_twister"] = Field(
        default="tongue_twister",
        description="Canonical challenge type -- strictly locked to 'tongue_twister'.",
    )
    raw_context: SafePersonalizationContext = Field(
        ...,
        description="Sanitized personalization context including sizing and style theme hints.",
    )
    strict_context: bool = Field(
        default=True,
        description="Enforces strict context validation in Phase 4.4 generator.",
    )

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


# =============================================================================
# TYPED DISPATCH RESULTS
# =============================================================================

class MathDispatchResult(BaseModel):
    """Typed dispatch result for math wake challenges routing to Phase 4.2 generator."""

    challenge_type: Literal["math"] = Field(
        default="math",
        description="Canonical challenge type -- immutable 'math'.",
    )
    difficulty: CanonicalDifficultyLevel = Field(
        ...,
        description="Authoritative concrete difficulty tier.",
    )
    difficulty_level: CanonicalDifficultyLevel = Field(
        ...,
        description="Authoritative concrete difficulty tier (alias for difficulty).",
    )
    selected_path: Literal["math_challenge_generator"] = Field(
        default="math_challenge_generator",
        description="Identifier of selected generator path.",
    )
    adapter_output: MathPersonalizationAdapterOutput = Field(
        ...,
        description="Typed parameter output from Phase 4.5 Step 4 math adapter.",
    )
    generator_input: MathGeneratorInputArgs = Field(
        ...,
        description="Generator-compatible typed input arguments for Phase 4.2 MathChallengeGenerator.",
    )

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    @property
    def is_procedural(self) -> bool:
        """Indicates whether this dispatch target is procedural-only."""
        return False

    @property
    def generator_class(self) -> Type[MathChallengeGenerator]:
        """Reference to the destination generator class."""
        return MathChallengeGenerator

    @property
    def payload(self) -> MathPersonalizationAdapterOutput:
        """Convenience property accessing the adapter output payload."""
        return self.adapter_output

    @property
    def parameters(self) -> MathGeneratorInputArgs:
        """Convenience property accessing the generator-compatible parameters."""
        return self.generator_input


class MemoryDispatchResult(BaseModel):
    """Typed dispatch result for memory wake challenges routing to Phase 4.3 generator."""

    challenge_type: Literal["memory"] = Field(
        default="memory",
        description="Canonical challenge type -- immutable 'memory'.",
    )
    difficulty: CanonicalDifficultyLevel = Field(
        ...,
        description="Authoritative concrete difficulty tier.",
    )
    difficulty_level: CanonicalDifficultyLevel = Field(
        ...,
        description="Authoritative concrete difficulty tier (alias for difficulty).",
    )
    selected_path: Literal["memory_challenge_generator"] = Field(
        default="memory_challenge_generator",
        description="Identifier of selected generator path.",
    )
    adapter_output: MemoryPersonalizationAdapterOutput = Field(
        ...,
        description="Typed parameter output from Phase 4.5 Step 4 memory adapter.",
    )
    generator_input: MemoryGeneratorInputArgs = Field(
        ...,
        description="Generator-compatible typed input arguments for Phase 4.3 MemoryChallengeGenerator.",
    )

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    @property
    def is_procedural(self) -> bool:
        """Indicates whether this dispatch target is procedural-only."""
        return False

    @property
    def generator_class(self) -> Type[MemoryChallengeGenerator]:
        """Reference to the destination generator class."""
        return MemoryChallengeGenerator

    @property
    def payload(self) -> MemoryPersonalizationAdapterOutput:
        """Convenience property accessing the adapter output payload."""
        return self.adapter_output

    @property
    def parameters(self) -> MemoryGeneratorInputArgs:
        """Convenience property accessing the generator-compatible parameters."""
        return self.generator_input


class TongueTwisterDispatchResult(BaseModel):
    """Typed dispatch result for tongue-twister challenges routing to Phase 4.4 generator."""

    challenge_type: Literal["tongue_twister"] = Field(
        default="tongue_twister",
        description="Canonical challenge type -- immutable 'tongue_twister'.",
    )
    difficulty: CanonicalDifficultyLevel = Field(
        ...,
        description="Authoritative concrete difficulty tier.",
    )
    difficulty_level: CanonicalDifficultyLevel = Field(
        ...,
        description="Authoritative concrete difficulty tier (alias for difficulty).",
    )
    selected_path: Literal["tongue_twister_challenge_generator"] = Field(
        default="tongue_twister_challenge_generator",
        description="Identifier of selected generator path.",
    )
    adapter_output: TongueTwisterPersonalizationAdapterOutput = Field(
        ...,
        description="Typed parameter output from Phase 4.5 Step 4 tongue-twister adapter.",
    )
    generator_input: TongueTwisterGeneratorInputArgs = Field(
        ...,
        description="Generator-compatible typed input arguments for Phase 4.4 TongueTwisterChallengeGenerator.",
    )

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    @property
    def is_procedural(self) -> bool:
        """Indicates whether this dispatch target is procedural-only."""
        return False

    @property
    def generator_class(self) -> Type[TongueTwisterChallengeGenerator]:
        """Reference to the destination generator class."""
        return TongueTwisterChallengeGenerator

    @property
    def payload(self) -> TongueTwisterPersonalizationAdapterOutput:
        """Convenience property accessing the adapter output payload."""
        return self.adapter_output

    @property
    def parameters(self) -> TongueTwisterGeneratorInputArgs:
        """Convenience property accessing the generator-compatible parameters."""
        return self.generator_input


class DanceDispatchResult(BaseModel):
    """Typed dispatch result for dance challenges routing to procedural dance adapter."""

    challenge_type: Literal["dance"] = Field(
        default="dance",
        description="Canonical challenge type -- immutable 'dance'.",
    )
    difficulty: CanonicalDifficultyLevel = Field(
        ...,
        description="Authoritative concrete difficulty tier.",
    )
    difficulty_level: CanonicalDifficultyLevel = Field(
        ...,
        description="Authoritative concrete difficulty tier (alias for difficulty).",
    )
    selected_path: Literal["dance_procedural_adapter"] = Field(
        default="dance_procedural_adapter",
        description="Identifier of selected procedural adapter path.",
    )
    adapter_output: DancePersonalizationAdapterOutput = Field(
        ...,
        description="Typed parameter output from Phase 4.5 Step 4 dance adapter.",
    )

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    @property
    def is_procedural(self) -> bool:
        """Indicates whether this dispatch target is procedural-only."""
        return True

    @property
    def payload(self) -> DancePersonalizationAdapterOutput:
        """Convenience property accessing the adapter output payload."""
        return self.adapter_output

    @property
    def parameters(self) -> DancePersonalizationAdapterOutput:
        """Convenience property accessing the procedural parameters."""
        return self.adapter_output


class PushUpDispatchResult(BaseModel):
    """Typed dispatch result for push-up challenges routing to procedural push-up adapter."""

    challenge_type: Literal["push_ups"] = Field(
        default="push_ups",
        description="Canonical challenge type -- immutable 'push_ups'.",
    )
    difficulty: CanonicalDifficultyLevel = Field(
        ...,
        description="Authoritative concrete difficulty tier.",
    )
    difficulty_level: CanonicalDifficultyLevel = Field(
        ...,
        description="Authoritative concrete difficulty tier (alias for difficulty).",
    )
    selected_path: Literal["push_ups_procedural_adapter"] = Field(
        default="push_ups_procedural_adapter",
        description="Identifier of selected procedural adapter path.",
    )
    adapter_output: PushUpPersonalizationAdapterOutput = Field(
        ...,
        description="Typed parameter output from Phase 4.5 Step 4 push-up adapter.",
    )

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    @property
    def is_procedural(self) -> bool:
        """Indicates whether this dispatch target is procedural-only."""
        return True

    @property
    def payload(self) -> PushUpPersonalizationAdapterOutput:
        """Convenience property accessing the adapter output payload."""
        return self.adapter_output

    @property
    def parameters(self) -> PushUpPersonalizationAdapterOutput:
        """Convenience property accessing the procedural parameters."""
        return self.adapter_output


PersonalizationDispatchResult = Union[
    MathDispatchResult,
    MemoryDispatchResult,
    TongueTwisterDispatchResult,
    DanceDispatchResult,
    PushUpDispatchResult,
]


# =============================================================================
# VALIDATION HELPERS
# =============================================================================

def _validate_profile_type_and_difficulty(profile: PersonalizedChallengeProfile) -> None:
    """Validate incoming profile against type and difficulty invariants.

    Enforces that:
    - profile is an instance of PersonalizedChallengeProfile.
    - challenge_type is not empty, forbidden, or unknown.
    - difficulty_level is a valid canonical concrete tier ('easy', 'medium', 'hard').

    Args:
        profile: Candidate PersonalizedChallengeProfile.

    Raises:
        DispatcherTypeError: If challenge_type is forbidden or unknown.
        DispatcherDifficultyError: If difficulty_level is invalid.
    """
    if not isinstance(profile, PersonalizedChallengeProfile):
        raise DispatcherError(
            f"Dispatcher received invalid profile of type '{type(profile).__name__}'. "
            "Expected PersonalizedChallengeProfile."
        )

    ctype = getattr(profile, "challenge_type", None)
    if not isinstance(ctype, str) or not ctype.strip():
        raise DispatcherTypeError("Challenge type must be a non-empty string.")

    if ctype in FORBIDDEN_CHALLENGE_TYPES:
        raise DispatcherTypeError(
            f"Dispatcher received forbidden challenge type '{ctype}'. "
            "Forbidden challenge types must never reach the dispatcher layer."
        )
    if ctype not in VALID_CANONICAL_CHALLENGE_TYPES:
        raise DispatcherTypeError(
            f"Dispatcher received unknown challenge type '{ctype}'. "
            f"Supported canonical types: {sorted(list(VALID_CANONICAL_CHALLENGE_TYPES))}."
        )

    diff = getattr(profile, "difficulty_level", None)
    if not isinstance(diff, str) or not diff.strip():
        raise DispatcherDifficultyError("Difficulty level must be a non-empty string.")

    if diff not in VALID_CANONICAL_DIFFICULTIES:
        raise DispatcherDifficultyError(
            f"Dispatcher received invalid difficulty '{diff}'. "
            f"Must be one of: {sorted(list(VALID_CANONICAL_DIFFICULTIES))}."
        )


# =============================================================================
# PERSONALIZATION DISPATCHER SERVICE
# =============================================================================

class PersonalizationDispatcher:
    """Deterministic orchestration boundary dispatching profiles to generator/adapter contracts.

    Coordinates the boundary between Phase 4.5 Step 3/4 profiles and:
    - Phase 4.2 MathChallengeGenerator
    - Phase 4.3 MemoryChallengeGenerator
    - Phase 4.4 TongueTwisterChallengeGenerator
    - Phase 4.5 Procedural Dance Adapter
    - Phase 4.5 Procedural Push-Up Adapter

    Zero LLM calls, zero DB access, zero network calls, zero randomization, zero content generation.
    """

    def dispatch(
        self, profile: PersonalizedChallengeProfile
    ) -> PersonalizationDispatchResult:
        """Route a PersonalizedChallengeProfile to its canonical generator or adapter path.

        Authoritative challenge_type and difficulty_level are guaranteed to be preserved.
        The input profile is treated as strictly read-only and is never mutated.

        Args:
            profile: Validated PersonalizedChallengeProfile from Step 3.

        Returns:
            One of MathDispatchResult, MemoryDispatchResult, TongueTwisterDispatchResult,
            DanceDispatchResult, or PushUpDispatchResult.

        Raises:
            DispatcherTypeError: If challenge_type is forbidden or unknown.
            DispatcherDifficultyError: If difficulty_level is invalid.
        """
        _validate_profile_type_and_difficulty(profile)

        ctype: CanonicalChallengeType = profile.challenge_type

        if ctype == "math":
            return self.dispatch_math(profile)
        elif ctype == "memory":
            return self.dispatch_memory(profile)
        elif ctype == "tongue_twister":
            return self.dispatch_tongue_twister(profile)
        elif ctype == "dance":
            return self.dispatch_dance(profile)
        else:
            # ctype == "push_ups"
            return self.dispatch_push_ups(profile)

    def dispatch_math(self, profile: PersonalizedChallengeProfile) -> MathDispatchResult:
        """Route a math PersonalizedChallengeProfile to Phase 4.2 generator contract.

        Args:
            profile: PersonalizedChallengeProfile with challenge_type='math'.

        Returns:
            MathDispatchResult containing typed adapter output and MathGeneratorInputArgs.

        Raises:
            DispatcherTypeError: If profile challenge_type is not 'math'.
            DispatcherDifficultyError: If difficulty is invalid.
        """
        _validate_profile_type_and_difficulty(profile)
        if profile.challenge_type != "math":
            raise DispatcherTypeError(
                f"dispatch_math expected challenge_type='math', got '{profile.challenge_type}'."
            )

        adapter_output: MathPersonalizationAdapterOutput = _adapt_math(profile)

        # Inform preferred_theme using focus_topic if provided, preserving existing theme otherwise
        theme: Optional[str] = adapter_output.focus_topic or profile.safe_context.preferred_theme

        generator_context = SafePersonalizationContext(
            desired_duration_seconds=adapter_output.desired_duration_seconds,
            current_session_snooze_count=profile.safe_context.current_session_snooze_count,
            current_attempt_number=profile.safe_context.current_attempt_number,
            preferred_theme=theme,
            language=profile.safe_context.language,
            disallowed_topics=list(profile.safe_context.disallowed_topics),
        )

        generator_input = MathGeneratorInputArgs(
            difficulty_level=profile.difficulty_level,
            challenge_type="math",
            raw_context=generator_context,
            strict_context=True,
        )

        return MathDispatchResult(
            challenge_type="math",
            difficulty=profile.difficulty_level,
            difficulty_level=profile.difficulty_level,
            selected_path="math_challenge_generator",
            adapter_output=adapter_output,
            generator_input=generator_input,
        )

    def dispatch_memory(self, profile: PersonalizedChallengeProfile) -> MemoryDispatchResult:
        """Route a memory PersonalizedChallengeProfile to Phase 4.3 generator contract.

        Args:
            profile: PersonalizedChallengeProfile with challenge_type='memory'.

        Returns:
            MemoryDispatchResult containing typed adapter output and MemoryGeneratorInputArgs.

        Raises:
            DispatcherTypeError: If profile challenge_type is not 'memory'.
            DispatcherDifficultyError: If difficulty is invalid.
        """
        _validate_profile_type_and_difficulty(profile)
        if profile.challenge_type != "memory":
            raise DispatcherTypeError(
                f"dispatch_memory expected challenge_type='memory', got '{profile.challenge_type}'."
            )

        adapter_output: MemoryPersonalizationAdapterOutput = _adapt_memory(profile)

        # Inform preferred_theme using palette_theme if provided, preserving existing theme otherwise
        theme: Optional[str] = adapter_output.palette_theme or profile.safe_context.preferred_theme

        generator_context = SafePersonalizationContext(
            desired_duration_seconds=adapter_output.desired_duration_seconds,
            current_session_snooze_count=profile.safe_context.current_session_snooze_count,
            current_attempt_number=profile.safe_context.current_attempt_number,
            preferred_theme=theme,
            language=profile.safe_context.language,
            disallowed_topics=list(profile.safe_context.disallowed_topics),
        )

        generator_input = MemoryGeneratorInputArgs(
            difficulty_level=profile.difficulty_level,
            challenge_type="memory",
            raw_context=generator_context,
            strict_context=True,
            preferred_mode=adapter_output.preferred_mode,
        )

        return MemoryDispatchResult(
            challenge_type="memory",
            difficulty=profile.difficulty_level,
            difficulty_level=profile.difficulty_level,
            selected_path="memory_challenge_generator",
            adapter_output=adapter_output,
            generator_input=generator_input,
        )

    def dispatch_tongue_twister(
        self, profile: PersonalizedChallengeProfile
    ) -> TongueTwisterDispatchResult:
        """Route a tongue_twister PersonalizedChallengeProfile to Phase 4.4 generator contract.

        Args:
            profile: PersonalizedChallengeProfile with challenge_type='tongue_twister'.

        Returns:
            TongueTwisterDispatchResult containing typed adapter output and TongueTwisterGeneratorInputArgs.

        Raises:
            DispatcherTypeError: If profile challenge_type is not 'tongue_twister'.
            DispatcherDifficultyError: If difficulty is invalid.
        """
        _validate_profile_type_and_difficulty(profile)
        if profile.challenge_type != "tongue_twister":
            raise DispatcherTypeError(
                f"dispatch_tongue_twister expected challenge_type='tongue_twister', got '{profile.challenge_type}'."
            )

        adapter_output: TongueTwisterPersonalizationAdapterOutput = _adapt_tongue_twister(profile)

        # Inform preferred_theme using theme_style if provided, preserving existing theme otherwise
        theme: Optional[str] = adapter_output.theme_style or profile.safe_context.preferred_theme

        generator_context = SafePersonalizationContext(
            desired_duration_seconds=adapter_output.desired_duration_seconds,
            current_session_snooze_count=profile.safe_context.current_session_snooze_count,
            current_attempt_number=profile.safe_context.current_attempt_number,
            preferred_theme=theme,
            language=profile.safe_context.language,
            disallowed_topics=list(profile.safe_context.disallowed_topics),
        )

        generator_input = TongueTwisterGeneratorInputArgs(
            difficulty_level=profile.difficulty_level,
            challenge_type="tongue_twister",
            raw_context=generator_context,
            strict_context=True,
        )

        return TongueTwisterDispatchResult(
            challenge_type="tongue_twister",
            difficulty=profile.difficulty_level,
            difficulty_level=profile.difficulty_level,
            selected_path="tongue_twister_challenge_generator",
            adapter_output=adapter_output,
            generator_input=generator_input,
        )

    def dispatch_dance(self, profile: PersonalizedChallengeProfile) -> DanceDispatchResult:
        """Route a dance PersonalizedChallengeProfile to procedural dance adapter path.

        Dance has no GenAI generator. Produces a procedural parameter map only.

        Args:
            profile: PersonalizedChallengeProfile with challenge_type='dance'.

        Returns:
            DanceDispatchResult containing DancePersonalizationAdapterOutput.

        Raises:
            DispatcherTypeError: If profile challenge_type is not 'dance'.
            DispatcherDifficultyError: If difficulty is invalid.
        """
        _validate_profile_type_and_difficulty(profile)
        if profile.challenge_type != "dance":
            raise DispatcherTypeError(
                f"dispatch_dance expected challenge_type='dance', got '{profile.challenge_type}'."
            )

        adapter_output: DancePersonalizationAdapterOutput = _adapt_dance(profile)

        return DanceDispatchResult(
            challenge_type="dance",
            difficulty=profile.difficulty_level,
            difficulty_level=profile.difficulty_level,
            selected_path="dance_procedural_adapter",
            adapter_output=adapter_output,
        )

    def dispatch_push_ups(self, profile: PersonalizedChallengeProfile) -> PushUpDispatchResult:
        """Route a push_ups PersonalizedChallengeProfile to procedural push-up adapter path.

        Push-ups have no GenAI generator. Produces a procedural parameter map only.

        Args:
            profile: PersonalizedChallengeProfile with challenge_type='push_ups'.

        Returns:
            PushUpDispatchResult containing PushUpPersonalizationAdapterOutput.

        Raises:
            DispatcherTypeError: If profile challenge_type is not 'push_ups'.
            DispatcherDifficultyError: If difficulty is invalid.
        """
        _validate_profile_type_and_difficulty(profile)
        if profile.challenge_type != "push_ups":
            raise DispatcherTypeError(
                f"dispatch_push_ups expected challenge_type='push_ups', got '{profile.challenge_type}'."
            )

        adapter_output: PushUpPersonalizationAdapterOutput = _adapt_push_ups(profile)

        return PushUpDispatchResult(
            challenge_type="push_ups",
            difficulty=profile.difficulty_level,
            difficulty_level=profile.difficulty_level,
            selected_path="push_ups_procedural_adapter",
            adapter_output=adapter_output,
        )


# =============================================================================
# MODULE-LEVEL ENTRY-POINT
# =============================================================================

def dispatch_profile(
    profile: PersonalizedChallengeProfile,
) -> PersonalizationDispatchResult:
    """Convenience functional entry-point for dispatching a PersonalizedChallengeProfile.

    Args:
        profile: Validated PersonalizedChallengeProfile from Step 3.

    Returns:
        Typed PersonalizationDispatchResult matching the profile's canonical challenge type.
    """
    return PersonalizationDispatcher().dispatch(profile)
