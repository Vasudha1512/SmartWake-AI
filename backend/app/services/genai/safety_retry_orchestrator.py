"""Bounded Retry & Deterministic Fallback Orchestration for GenAI Challenge Generation (Phase 4.6.7 - 4.6.8).

Orchestrates the safe execution of GenAI challenge generation:
1. Coordinates generation attempts bounded by ValidationRetryPolicy (max_retries <= 2).
2. Intercepts untrusted output and validates through Common + Domain Safety Boundaries.
3. On validation failure, initiates one bounded retry if permitted by policy.
4. On provider failure (timeouts, rate limits, 503s, unexpected errors), catches exceptions cleanly.
5. On exhaustion or unrecoverable error, deterministically drops back to the procedural challenge catalog.
6. The Alarm Never Fails: guarantees a verified, safe challenge of the exact requested canonical type
   and concrete difficulty is ALWAYS delivered.

CRITICAL INVARIANTS:
- Pure in-memory orchestration: zero DB writes, zero ORM sessions, zero real network calls.
- Preserves application-authoritative challenge_type and difficulty_level under all circumstances.
- Zero Dict[str, Any] escape hatches.
"""
from typing import Callable, Mapping, Optional, Union
from pydantic import BaseModel, ConfigDict, Field

from backend.app.core.exceptions import (
    GenAIConfigurationError,
    GenAIError,
    GenAIProviderUnavailableError,
    GenAIRateLimitError,
    GenAITimeoutError,
)
from backend.app.schemas.challenge_safety_schemas import (
    FallbackPayloadContract,
    FallbackReason,
    FallbackResolution,
    FallbackSource,
    SafetySeverity,
    SafetyValidationReport,
    SafetyViolationCode,
    ValidationRetryPolicy,
)
from backend.app.schemas.personalization_content_schemas import (
    CanonicalChallengeType,
    CanonicalDifficultyLevel,
)
from backend.app.services.genai.domain_safety_validator import DomainSafetyValidator


# =============================================================================
# CURATED PROCEDURAL FALLBACK CATALOG (100% Deterministic, Offline, Verified)
# =============================================================================

class FallbackCatalogEntry(BaseModel):
    """Immutable catalog entry providing deterministic fallback content reference."""

    identifier: str
    instructions_hint: str
    parameters_tag: str
    challenge_payload: Mapping[str, object]

    model_config = ConfigDict(extra="forbid", strict=True)


DETERMINISTIC_FALLBACK_CATALOG: Mapping[
    tuple[str, str],
    FallbackCatalogEntry,
] = {
    # Math Catalog
    ("math", "easy"): FallbackCatalogEntry(
        identifier="catalog_math_easy_001",
        instructions_hint="Solve the arithmetic equation displayed below.",
        parameters_tag="addition_basic",
        challenge_payload={
            "challenge_type": "math",
            "difficulty_level": "easy",
            "title": "Morning Addition",
            "instructions": "Calculate the sum to dismiss your alarm.",
            "content_payload": {"expression": "14 + 19", "operands": [14, 19], "operator": "+"},
            "expected_answer": 33,
        },
    ),
    ("math", "medium"): FallbackCatalogEntry(
        identifier="catalog_math_medium_001",
        instructions_hint="Solve the arithmetic equation displayed below.",
        parameters_tag="multiplication_intermediate",
        challenge_payload={
            "challenge_type": "math",
            "difficulty_level": "medium",
            "title": "Morning Multiplication",
            "instructions": "Calculate the product to dismiss your alarm.",
            "content_payload": {"expression": "23 * 4", "operands": [23, 4], "operator": "*"},
            "expected_answer": 92,
        },
    ),
    ("math", "hard"): FallbackCatalogEntry(
        identifier="catalog_math_hard_001",
        instructions_hint="Solve the arithmetic equation displayed below.",
        parameters_tag="compound_arithmetic",
        challenge_payload={
            "challenge_type": "math",
            "difficulty_level": "hard",
            "title": "Morning Math Challenge",
            "instructions": "Evaluate the arithmetic expression to dismiss your alarm.",
            "content_payload": {"expression": "145 - 58", "operands": [145, 58], "operator": "-"},
            "expected_answer": 87,
        },
    ),
    # Memory Catalog (Strict Non-Numeric Guarantees)
    ("memory", "easy"): FallbackCatalogEntry(
        identifier="catalog_memory_easy_001",
        instructions_hint="Memorize the sequence of colored symbols.",
        parameters_tag="colors_sequence",
        challenge_payload={
            "challenge_type": "memory",
            "difficulty_level": "easy",
            "title": "Color Sequence Recall",
            "instructions": "Memorize the sequence of colors and repeat them in order.",
            "content_payload": {
                "mode": "visual_sequence",
                "palette_theme": "colors",
                "sequence": ["Crimson", "Azure", "Emerald"],
            },
            "expected_answer": ["Crimson", "Azure", "Emerald"],
        },
    ),
    ("memory", "medium"): FallbackCatalogEntry(
        identifier="catalog_memory_medium_001",
        instructions_hint="Memorize the sequence of geometric shapes.",
        parameters_tag="shapes_sequence",
        challenge_payload={
            "challenge_type": "memory",
            "difficulty_level": "medium",
            "title": "Shape Sequence Recall",
            "instructions": "Memorize the sequence of geometric shapes in order.",
            "content_payload": {
                "mode": "visual_sequence",
                "palette_theme": "geometric_shapes",
                "sequence": ["Triangle", "Hexagon", "Circle", "Square", "Diamond"],
            },
            "expected_answer": ["Triangle", "Hexagon", "Circle", "Square", "Diamond"],
        },
    ),
    ("memory", "hard"): FallbackCatalogEntry(
        identifier="catalog_memory_hard_001",
        instructions_hint="Memorize the spatial pattern of directions.",
        parameters_tag="directions_sequence",
        challenge_payload={
            "challenge_type": "memory",
            "difficulty_level": "hard",
            "title": "Compass Sequence Recall",
            "instructions": "Memorize the sequence of cardinal directions in order.",
            "content_payload": {
                "mode": "visual_sequence",
                "palette_theme": "cardinal_directions",
                "sequence": ["North", "South", "East", "West", "North", "East"],
            },
            "expected_answer": ["North", "South", "East", "West", "North", "East"],
        },
    ),
    # Tongue Twister Catalog
    ("tongue_twister", "easy"): FallbackCatalogEntry(
        identifier="catalog_tt_easy_001",
        instructions_hint="Articulate the tongue twister passage aloud.",
        parameters_tag="sibilants_basic",
        challenge_payload={
            "challenge_type": "tongue_twister",
            "difficulty_level": "easy",
            "title": "Morning Sibilants",
            "instructions": "Clearly enunciate the passage aloud without slurring consonants.",
            "content_payload": {
                "passage": "She sells sea shells by the sea shore.",
                "phonetic_focus": "s_and_sh_alternation",
                "target_word_count": 8,
            },
        },
    ),
    ("tongue_twister", "medium"): FallbackCatalogEntry(
        identifier="catalog_tt_medium_001",
        instructions_hint="Articulate the tongue twister passage aloud.",
        parameters_tag="sibilant_clusters",
        challenge_payload={
            "challenge_type": "tongue_twister",
            "difficulty_level": "medium",
            "title": "Morning Alliteration",
            "instructions": "Clearly enunciate the passage aloud without slurring consonants.",
            "content_payload": {
                "passage": "Six slippery snails slid slowly southward down the steep stone slope.",
                "phonetic_focus": "sibilant_s_clusters",
                "target_word_count": 10,
            },
        },
    ),
    ("tongue_twister", "hard"): FallbackCatalogEntry(
        identifier="catalog_tt_hard_001",
        instructions_hint="Articulate the tongue twister passage aloud.",
        parameters_tag="complex_phonetics",
        challenge_payload={
            "challenge_type": "tongue_twister",
            "difficulty_level": "hard",
            "title": "Morning Phonetic Mastery",
            "instructions": "Clearly articulate the compound passage aloud without slurring.",
            "content_payload": {
                "passage": "How much ground would a groundhog grind if a groundhog could grind ground? A groundhog would grind all the ground he could grind.",
                "phonetic_focus": "compound_cluster_gr_nd",
                "target_word_count": 21,
            },
        },
    ),
    # Dance Catalog (Procedural Kinetic Routine)
    ("dance", "easy"): FallbackCatalogEntry(
        identifier="catalog_dance_easy_001",
        instructions_hint="Follow the rhythmic dance movement cues.",
        parameters_tag="rhythm_groove_easy",
        challenge_payload={
            "challenge_type": "dance",
            "difficulty_level": "easy",
            "title": "Gentle Morning Groove",
            "instructions": "Follow the rhythmic movement cues shown on screen.",
            "content_payload": {
                "routine_type": "rhythm_groove",
                "step_count": 4,
                "target_duration_seconds": 20,
                "tempo_bpm": 100,
                "steps": [
                    {"step_number": 1, "action": "Step Left & Bounce", "cue_second": 0.0},
                    {"step_number": 2, "action": "Step Right & Bounce", "cue_second": 5.0},
                    {"step_number": 3, "action": "Overhead Arm Wave", "cue_second": 10.0},
                    {"step_number": 4, "action": "Double Clap & Pivot", "cue_second": 15.0},
                ],
            },
        },
    ),
    ("dance", "medium"): FallbackCatalogEntry(
        identifier="catalog_dance_medium_001",
        instructions_hint="Follow the rhythmic dance movement cues.",
        parameters_tag="rhythm_groove_medium",
        challenge_payload={
            "challenge_type": "dance",
            "difficulty_level": "medium",
            "title": "Rhythmic Morning Groove",
            "instructions": "Follow the rhythmic movement cues shown on screen.",
            "content_payload": {
                "routine_type": "rhythm_groove",
                "step_count": 6,
                "target_duration_seconds": 30,
                "tempo_bpm": 115,
                "steps": [
                    {"step_number": 1, "action": "Step Left & Bounce", "cue_second": 0.0},
                    {"step_number": 2, "action": "Step Right & Bounce", "cue_second": 5.0},
                    {"step_number": 3, "action": "High Knee March Left", "cue_second": 10.0},
                    {"step_number": 4, "action": "High Knee March Right", "cue_second": 15.0},
                    {"step_number": 5, "action": "Cross-Body Tap Left", "cue_second": 20.0},
                    {"step_number": 6, "action": "Cross-Body Tap Right", "cue_second": 25.0},
                ],
            },
        },
    ),
    ("dance", "hard"): FallbackCatalogEntry(
        identifier="catalog_dance_hard_001",
        instructions_hint="Follow the dynamic kinetic routine.",
        parameters_tag="kinetic_cardio_hard",
        challenge_payload={
            "challenge_type": "dance",
            "difficulty_level": "hard",
            "title": "Kinetic Wake Cardio",
            "instructions": "Follow the dynamic movement cues shown on screen.",
            "content_payload": {
                "routine_type": "rhythm_groove",
                "step_count": 8,
                "target_duration_seconds": 45,
                "tempo_bpm": 130,
                "steps": [
                    {"step_number": 1, "action": "Step Left & Bounce", "cue_second": 0.0},
                    {"step_number": 2, "action": "Step Right & Bounce", "cue_second": 5.5},
                    {"step_number": 3, "action": "High Knee March Left", "cue_second": 11.0},
                    {"step_number": 4, "action": "High Knee March Right", "cue_second": 16.5},
                    {"step_number": 5, "action": "Salsa Forward Step", "cue_second": 22.0},
                    {"step_number": 6, "action": "Salsa Back Step", "cue_second": 27.5},
                    {"step_number": 7, "action": "Overhead Arm Wave", "cue_second": 33.0},
                    {"step_number": 8, "action": "Double Clap & Pivot", "cue_second": 38.5},
                ],
            },
        },
    ),
    # Push-ups Catalog (Procedural Calisthenics)
    ("push_ups", "easy"): FallbackCatalogEntry(
        identifier="catalog_pushups_easy_001",
        instructions_hint="Perform steady push-ups maintaining plank posture.",
        parameters_tag="calisthenics_easy",
        challenge_payload={
            "challenge_type": "push_ups",
            "difficulty_level": "easy",
            "title": "Morning Push-ups",
            "instructions": "Perform 5 push-ups with steady form to dismiss the alarm.",
            "content_payload": {
                "target_repetitions": 5,
                "completion_window_seconds": 30,
                "min_rom_percentage": 75,
                "cadence_guideline": "moderate",
            },
        },
    ),
    ("push_ups", "medium"): FallbackCatalogEntry(
        identifier="catalog_pushups_medium_001",
        instructions_hint="Perform push-ups maintaining plank posture.",
        parameters_tag="calisthenics_medium",
        challenge_payload={
            "challenge_type": "push_ups",
            "difficulty_level": "medium",
            "title": "Morning Push-ups",
            "instructions": "Perform 12 push-ups with steady form to dismiss the alarm.",
            "content_payload": {
                "target_repetitions": 12,
                "completion_window_seconds": 45,
                "min_rom_percentage": 75,
                "cadence_guideline": "moderate",
            },
        },
    ),
    ("push_ups", "hard"): FallbackCatalogEntry(
        identifier="catalog_pushups_hard_001",
        instructions_hint="Perform push-ups maintaining strict form.",
        parameters_tag="calisthenics_hard",
        challenge_payload={
            "challenge_type": "push_ups",
            "difficulty_level": "hard",
            "title": "Intense Morning Push-ups",
            "instructions": "Perform 25 push-ups with strict plank posture to dismiss the alarm.",
            "content_payload": {
                "target_repetitions": 25,
                "completion_window_seconds": 60,
                "min_rom_percentage": 85,
                "cadence_guideline": "steady",
            },
        },
    ),
}


class DeterministicFallbackResolver:
    """Pure in-memory resolver providing deterministic procedural challenge fallbacks."""

    @classmethod
    def resolve_fallback(
        cls,
        expected_type: CanonicalChallengeType,
        expected_difficulty: CanonicalDifficultyLevel,
        reason: FallbackReason,
        trigger_error: str,
    ) -> tuple[FallbackResolution, Mapping[str, object]]:
        """Resolve a deterministic procedural challenge preserving canonical type and concrete difficulty."""
        catalog_key = (expected_type, expected_difficulty)
        entry = DETERMINISTIC_FALLBACK_CATALOG.get(catalog_key)

        if entry is None:
            # Fallback catalog entry must exist for all 15 canonical pairs
            raise ValueError(
                f"Missing catalog fallback entry for ({expected_type}, {expected_difficulty})."
            )

        payload_contract = FallbackPayloadContract(
            fallback_identifier=entry.identifier,
            instructions_hint=entry.instructions_hint,
            parameters_tag=entry.parameters_tag,
        )

        resolution = FallbackResolution(
            challenge_type=expected_type,
            difficulty_level=expected_difficulty,
            fallback_reason=reason,
            fallback_source=FallbackSource.PROCEDURAL_CATALOG,
            trigger_error=trigger_error[:250],
            preserved_type=True,
            preserved_difficulty=True,
            fallback_payload=payload_contract,
        )
        return resolution, entry.challenge_payload


# =============================================================================
# ORCHESTRATION RESULT
# =============================================================================

class OrchestratedGenerationResult(BaseModel):
    """Result of safety-orchestrated GenAI challenge generation."""

    is_fallback: bool = Field(
        ...,
        description="Whether the output was produced via deterministic procedural fallback",
    )
    challenge_type: CanonicalChallengeType = Field(
        ...,
        description="Preserved authoritative canonical challenge type",
    )
    difficulty_level: CanonicalDifficultyLevel = Field(
        ...,
        description="Preserved authoritative concrete difficulty tier",
    )
    content: object = Field(
        ...,
        description="Validated generated content or verified fallback payload",
    )
    report: SafetyValidationReport = Field(
        ...,
        description="Inspection safety report from Common & Domain validators",
    )
    attempts_used: int = Field(
        ...,
        ge=1,
        description="Total generation attempts consumed",
    )
    fallback_resolution: Optional[FallbackResolution] = Field(
        default=None,
        description="Structured fallback resolution record if fallback occurred",
    )

    model_config = ConfigDict(extra="forbid", strict=True, arbitrary_types_allowed=True)


# =============================================================================
# SAFETY RETRY ORCHESTRATOR
# =============================================================================

class SafetyRetryOrchestrator:
    """Orchestrates generation attempts, safety validation, bounded retries, and deterministic fallback."""

    @classmethod
    def orchestrate(
        cls,
        expected_type: CanonicalChallengeType,
        expected_difficulty: CanonicalDifficultyLevel,
        generator_func: Callable[[], object],
        policy: Optional[ValidationRetryPolicy] = None,
    ) -> OrchestratedGenerationResult:
        """Execute generation with bounded retries and guaranteed deterministic fallback.

        Args:
            expected_type: Authoritative canonical challenge type requested.
            expected_difficulty: Authoritative concrete difficulty tier requested.
            generator_func: Callable executing generation (untrusted provider or generator).
            policy: Bounded retry policy (default max_retries=1, timeout=3.0s, total_budget=6.0s).

        Returns:
            OrchestratedGenerationResult: Validated challenge result with full telemetry.
        """
        active_policy = policy or ValidationRetryPolicy()
        max_attempts = active_policy.max_retries + 1  # 1 retry means 2 total attempts max

        last_report: Optional[SafetyValidationReport] = None
        last_error_message: str = "Unknown error occurred."
        last_fallback_reason: FallbackReason = FallbackReason.VALIDATION_FAILED
        attempt: int = 0

        for attempt in range(1, max_attempts + 1):
            raw_output: Optional[object] = None
            try:
                raw_output = generator_func()
            except GenAITimeoutError as exc:
                last_error_message = f"GenAI provider timed out: {exc}"
                last_fallback_reason = FallbackReason.PROVIDER_TIMEOUT
                if attempt < max_attempts:
                    continue
                break
            except GenAIRateLimitError as exc:
                # Rate limits are not immediately retried to avoid compounding provider backoff
                last_error_message = f"GenAI rate limit encountered: {exc}"
                last_fallback_reason = FallbackReason.RATE_LIMITED
                break
            except GenAIProviderUnavailableError as exc:
                last_error_message = f"GenAI provider unavailable: {exc}"
                last_fallback_reason = FallbackReason.PROVIDER_UNAVAILABLE
                break
            except (GenAIError, Exception) as exc:
                last_error_message = f"Provider generation failed: {exc}"
                last_fallback_reason = FallbackReason.PROVIDER_UNAVAILABLE
                if attempt < max_attempts:
                    continue
                break

            # If raw output obtained, validate through Common + Domain boundary
            report = DomainSafetyValidator.validate_challenge_safety(
                expected_type, expected_difficulty, raw_output
            )
            last_report = report

            if report.is_safe:
                # Generation and validation succeeded
                return OrchestratedGenerationResult(
                    is_fallback=False,
                    challenge_type=expected_type,
                    difficulty_level=expected_difficulty,
                    content=raw_output,
                    report=report,
                    attempts_used=attempt,
                    fallback_resolution=None,
                )

            # Map validation violations to fallback reason
            codes = {v.code for v in report.violations}
            if SafetyViolationCode.PROMPT_INJECTION in codes or SafetyViolationCode.HARMFUL_CONTENT in codes:
                last_fallback_reason = FallbackReason.SAFETY_VIOLATION
                last_error_message = "Safety violation: prompt injection or harmful content detected."
            elif SafetyViolationCode.SCHEMA_MALFORMED in codes:
                last_fallback_reason = FallbackReason.MALFORMED_OUTPUT
                last_error_message = "Malformed generated schema structure."
            else:
                last_fallback_reason = FallbackReason.VALIDATION_FAILED
                last_error_message = (
                    report.violations[0].message if report.violations else "Validation failed."
                )

            # If retries remain, attempt again
            if attempt < max_attempts:
                continue

        # Exhaustion or unrecoverable error -> Deterministic Procedural Fallback
        resolution, fallback_payload = DeterministicFallbackResolver.resolve_fallback(
            expected_type=expected_type,
            expected_difficulty=expected_difficulty,
            reason=last_fallback_reason,
            trigger_error=last_error_message,
        )

        # Build synthetic safe report for fallback payload
        fallback_report = last_report or SafetyValidationReport(
            is_safe=False,
            challenge_type=expected_type,
            difficulty_level=expected_difficulty,
            violations=[],
            checked_rules=["DETERMINISTIC_FALLBACK_RESOLVED"],
        )

        return OrchestratedGenerationResult(
            is_fallback=True,
            challenge_type=expected_type,
            difficulty_level=expected_difficulty,
            content=fallback_payload,
            report=fallback_report,
            attempts_used=min(attempt, max_attempts),
            fallback_resolution=resolution,
        )
