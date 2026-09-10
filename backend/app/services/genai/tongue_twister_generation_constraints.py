"""Tongue Twister Generation Constraints and Difficulty Presets for SmartWake AI (Phase 4.4).

Defines deterministic textual boundaries, repetition limits, speaking duration limits,
degeneracy safeguards, and orthographic sound-pattern thresholds across Easy, Medium, and Hard tiers.
"""
from typing import Dict, Optional, Set
from pydantic import BaseModel, ConfigDict, Field

from backend.app.core.exceptions import InvalidDifficultyError
from backend.app.schemas.challenge_content_schemas import ChallengeGenerationConstraints

# Targeted forbidden numeric-memory and prompt-injection concepts
FORBIDDEN_TONGUE_TWISTER_PHRASES: Set[str] = {
    "guess the number",
    "guess_number",
    "number_guessing",
    "number guessing",
    "numeric sequence",
    "numeric_sequence",
    "pin code",
    "pin",
    "otp",
    "passcode",
    "digit sequence",
    "number recall",
    "numeric code",
    "numeric_memory",
    "numeric memory",
    # Anti-prompt injection / jailbreak guardrails
    "ignore previous instructions",
    "ignore all instructions",
    "disregard previous instructions",
    "system prompt",
    "you are now",
    "change challenge to",
    "switch to math",
    "switch to memory",
    "switch to dance",
    "switch to push_ups",
}


class TongueTwisterGenerationConstraints(BaseModel):
    """Deterministic tongue-twister boundaries and resource limits for a difficulty tier."""

    difficulty_level: str = Field(..., description="Concrete difficulty tier ('easy', 'medium', 'hard')")
    min_word_count: int = Field(..., description="Minimum allowed words in passage")
    max_word_count: int = Field(..., description="Maximum allowed words in passage")
    default_word_count: int = Field(..., description="Baseline word count")
    min_repetitions: int = Field(..., description="Minimum allowed repetition count")
    max_repetitions: int = Field(..., description="Maximum allowed repetition count")
    default_repetitions: int = Field(..., description="Authoritative default repetition count")
    min_speaking_duration_seconds: int = Field(..., description="Minimum speaking duration limit in seconds")
    max_speaking_duration_seconds: int = Field(..., description="Maximum speaking duration limit in seconds")
    default_speaking_duration_seconds: int = Field(..., description="Authoritative default speaking duration in seconds")
    min_unique_word_ratio: float = Field(..., description="Degeneracy safeguard: min ratio of unique words to total words")
    min_onset_repetition_count: int = Field(..., description="Orthographic sound-pattern: minimum repetitions for dominant onset cluster")
    banned_concepts: Set[str] = Field(default_factory=set, description="Forbidden concepts/phrases")

    model_config = ConfigDict(from_attributes=True, frozen=True)


# =============================================================================
# DIFFICULTY PRESETS (Strictly Bounded per Approved Plan)
# =============================================================================

EASY_TONGUE_TWISTER_CONSTRAINTS = TongueTwisterGenerationConstraints(
    difficulty_level="easy",
    min_word_count=6,
    max_word_count=12,
    default_word_count=8,
    min_repetitions=1,
    max_repetitions=2,
    default_repetitions=2,
    min_speaking_duration_seconds=15,
    max_speaking_duration_seconds=20,
    default_speaking_duration_seconds=15,
    min_unique_word_ratio=0.35,
    min_onset_repetition_count=3,
    banned_concepts=FORBIDDEN_TONGUE_TWISTER_PHRASES,
)

MEDIUM_TONGUE_TWISTER_CONSTRAINTS = TongueTwisterGenerationConstraints(
    difficulty_level="medium",
    min_word_count=10,
    max_word_count=20,
    default_word_count=15,
    min_repetitions=2,
    max_repetitions=3,
    default_repetitions=2,
    min_speaking_duration_seconds=20,
    max_speaking_duration_seconds=35,
    default_speaking_duration_seconds=25,
    min_unique_word_ratio=0.40,
    min_onset_repetition_count=4,
    banned_concepts=FORBIDDEN_TONGUE_TWISTER_PHRASES,
)

HARD_TONGUE_TWISTER_CONSTRAINTS = TongueTwisterGenerationConstraints(
    difficulty_level="hard",
    min_word_count=20,
    max_word_count=35,
    default_word_count=25,
    min_repetitions=3,
    max_repetitions=4,
    default_repetitions=3,
    min_speaking_duration_seconds=35,
    max_speaking_duration_seconds=60,
    default_speaking_duration_seconds=45,
    min_unique_word_ratio=0.45,
    min_onset_repetition_count=5,
    banned_concepts=FORBIDDEN_TONGUE_TWISTER_PHRASES,
)

_TONGUE_TWISTER_DIFFICULTY_MAP: Dict[str, TongueTwisterGenerationConstraints] = {
    "easy": EASY_TONGUE_TWISTER_CONSTRAINTS,
    "medium": MEDIUM_TONGUE_TWISTER_CONSTRAINTS,
    "hard": HARD_TONGUE_TWISTER_CONSTRAINTS,
}


def get_tongue_twister_difficulty_constraints(difficulty_level: str) -> TongueTwisterGenerationConstraints:
    """Retrieve TongueTwisterGenerationConstraints for a concrete difficulty level.

    Args:
        difficulty_level: Concrete difficulty ('easy', 'medium', 'hard').

    Returns:
        TongueTwisterGenerationConstraints: Strict tongue twister boundaries.

    Raises:
        InvalidDifficultyError: If difficulty is not concrete or unknown.
    """
    if not difficulty_level:
        raise InvalidDifficultyError("difficulty_level must be specified.")

    clean_diff = difficulty_level.strip().lower()
    if clean_diff not in _TONGUE_TWISTER_DIFFICULTY_MAP:
        raise InvalidDifficultyError(
            f"Invalid difficulty '{difficulty_level}'. Tongue twister challenges require concrete tier: 'easy', 'medium', or 'hard'."
        )

    return _TONGUE_TWISTER_DIFFICULTY_MAP[clean_diff]


def build_tongue_twister_generation_constraints(
    challenge_type: str, difficulty_level: str
) -> ChallengeGenerationConstraints:
    """Construct framework ChallengeGenerationConstraints for Tongue Twister challenges.

    Plugs into the Phase 4.1 framework registry (_CONSTRAINT_REGISTRY['tongue_twister']).

    Args:
        challenge_type: Must be 'tongue_twister'.
        difficulty_level: Concrete tier ('easy', 'medium', 'hard').

    Returns:
        ChallengeGenerationConstraints: Framework boundary configuration.
    """
    tt_diff = get_tongue_twister_difficulty_constraints(difficulty_level)

    return ChallengeGenerationConstraints(
        challenge_type="tongue_twister",
        difficulty_level=tt_diff.difficulty_level,
        max_title_length=100,
        max_instructions_length=500,
        max_payload_bytes=16384,
        forbidden_terms=FORBIDDEN_TONGUE_TWISTER_PHRASES,
        required_payload_keys=["passage"],
        min_duration_seconds=tt_diff.min_speaking_duration_seconds,
        verification_mode="tongue_twister_standard",
    )
