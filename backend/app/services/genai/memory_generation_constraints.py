"""Memory Generation Constraints and Difficulty Presets for SmartWake AI (Phase 4.3).

Defines deterministic mathematical boundaries, sequence bounds, matrix limits,
path rules, and curated palettes across Easy, Medium, and Hard tiers.
"""
from typing import Dict, List, Optional, Set
from pydantic import BaseModel, ConfigDict, Field

from backend.app.core.exceptions import InvalidDifficultyError
from backend.app.schemas.challenge_content_schemas import ChallengeGenerationConstraints

# Targeted context-aware forbidden phrases for numeric memory (Correction 4)
FORBIDDEN_NUMERIC_MEMORY_PHRASES: Set[str] = {
    "guess the number",
    "guess_the_number",
    "guess_number",
    "guess number",
    "number guessing",
    "number_guessing",
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
}

# Curated non-numeric item palettes for memory generation
CURATED_COLOR_PALETTE = [
    "emerald", "amber", "azure", "coral", "teal", "violet", "cyan", "magenta"
]
CURATED_SYMBOL_PALETTE = [
    "triangle", "circle", "diamond", "hexagon", "star", "crescent", "square", "cross"
]
CURATED_MORNING_PALETTE = [
    "coffee_cup", "alarm_clock", "sunrise", "pillow", "kettle", "apple", "sun", "book"
]


class MemoryGenerationConstraints(BaseModel):
    """Deterministic memory boundaries and resource limits for a difficulty tier."""

    difficulty_level: str = Field(..., description="Concrete difficulty tier ('easy', 'medium', 'hard')")
    allowed_recall_modes: Set[str] = Field(..., description="Allowed canonical memory recall modes")
    min_sequence_length: int = Field(..., description="Minimum allowed sequence length")
    max_sequence_length: int = Field(..., description="Maximum allowed sequence length")
    default_sequence_length: int = Field(..., description="Baseline sequence length")
    min_matrix_size: int = Field(..., description="Minimum N of N x N spatial grid")
    max_matrix_size: int = Field(..., description="Maximum N of N x N spatial grid")
    min_highlight_count: int = Field(..., description="Minimum highlighted cells for spatial recall")
    max_highlight_count: int = Field(..., description="Maximum highlighted cells for spatial recall")
    default_highlight_count: int = Field(..., description="Baseline highlighted cells count")
    min_path_length: int = Field(default=0, description="Minimum path steps for dynamic spatial path (0 if not allowed)")
    max_path_length: int = Field(default=0, description="Maximum path steps for dynamic spatial path (0 if not allowed)")
    default_path_length: int = Field(default=0, description="Baseline path steps")
    default_display_duration_seconds: int = Field(default=5, description="Baseline display duration in seconds")
    default_time_limit_seconds: int = Field(default=30, description="Baseline recall time limit in seconds")
    banned_concepts: Set[str] = Field(default_factory=set, description="Forbidden concepts/phrases")

    model_config = ConfigDict(from_attributes=True, frozen=True)


# =============================================================================
# DIFFICULTY PRESETS (Strictly Bounded per Approved Plan)
# =============================================================================

EASY_MEMORY_CONSTRAINTS = MemoryGenerationConstraints(
    difficulty_level="easy",
    allowed_recall_modes={"visual_sequence", "spatial_pattern_recall"},
    min_sequence_length=3,
    max_sequence_length=4,
    default_sequence_length=3,
    min_matrix_size=3,
    max_matrix_size=3,
    min_highlight_count=3,
    max_highlight_count=4,
    default_highlight_count=3,
    min_path_length=0,
    max_path_length=0,  # Dynamic path not permitted in Easy
    default_path_length=0,
    default_display_duration_seconds=4,
    default_time_limit_seconds=20,
    banned_concepts=FORBIDDEN_NUMERIC_MEMORY_PHRASES,
)

MEDIUM_MEMORY_CONSTRAINTS = MemoryGenerationConstraints(
    difficulty_level="medium",
    allowed_recall_modes={
        "visual_sequence",
        "spatial_pattern_recall",
        "dynamic_spatial_path",
        "symbol_chronological_order",
    },
    min_sequence_length=4,
    max_sequence_length=6,
    default_sequence_length=5,
    min_matrix_size=3,
    max_matrix_size=4,
    min_highlight_count=4,
    max_highlight_count=6,
    default_highlight_count=5,
    min_path_length=4,
    max_path_length=5,
    default_path_length=5,
    default_display_duration_seconds=5,
    default_time_limit_seconds=35,
    banned_concepts=FORBIDDEN_NUMERIC_MEMORY_PHRASES,
)

HARD_MEMORY_CONSTRAINTS = MemoryGenerationConstraints(
    difficulty_level="hard",
    allowed_recall_modes={
        "visual_sequence",
        "spatial_pattern_recall",
        "dynamic_spatial_path",
        "symbol_chronological_order",
    },
    min_sequence_length=6,
    max_sequence_length=8,
    default_sequence_length=7,
    min_matrix_size=4,
    max_matrix_size=5,
    min_highlight_count=6,
    max_highlight_count=10,
    default_highlight_count=7,
    min_path_length=6,
    max_path_length=8,
    default_path_length=7,
    default_display_duration_seconds=7,
    default_time_limit_seconds=50,
    banned_concepts=FORBIDDEN_NUMERIC_MEMORY_PHRASES,
)

_MEMORY_DIFFICULTY_MAP: Dict[str, MemoryGenerationConstraints] = {
    "easy": EASY_MEMORY_CONSTRAINTS,
    "medium": MEDIUM_MEMORY_CONSTRAINTS,
    "hard": HARD_MEMORY_CONSTRAINTS,
}


def get_memory_difficulty_constraints(difficulty_level: str) -> MemoryGenerationConstraints:
    """Retrieve MemoryGenerationConstraints for a concrete difficulty level.

    Args:
        difficulty_level: Concrete difficulty ('easy', 'medium', 'hard').

    Returns:
        MemoryGenerationConstraints: Strict memory boundaries.

    Raises:
        InvalidDifficultyError: If difficulty is not concrete or unknown.
    """
    if not difficulty_level:
        raise InvalidDifficultyError("difficulty_level must be specified.")

    clean_diff = difficulty_level.strip().lower()
    if clean_diff not in _MEMORY_DIFFICULTY_MAP:
        raise InvalidDifficultyError(
            f"Invalid difficulty '{difficulty_level}'. Memory challenges require concrete tier: 'easy', 'medium', or 'hard'."
        )

    return _MEMORY_DIFFICULTY_MAP[clean_diff]


def build_memory_generation_constraints(
    challenge_type: str, difficulty_level: str
) -> ChallengeGenerationConstraints:
    """Construct framework ChallengeGenerationConstraints for Memory challenges.

    Plugs into the Phase 4.1 framework registry (_CONSTRAINT_REGISTRY['memory']).

    Args:
        challenge_type: Must be 'memory'.
        difficulty_level: Concrete tier ('easy', 'medium', 'hard').

    Returns:
        ChallengeGenerationConstraints: Framework boundary configuration.
    """
    mem_diff = get_memory_difficulty_constraints(difficulty_level)

    min_duration = 10
    if mem_diff.difficulty_level == "medium":
        min_duration = 15
    elif mem_diff.difficulty_level == "hard":
        min_duration = 20

    return ChallengeGenerationConstraints(
        challenge_type="memory",
        difficulty_level=mem_diff.difficulty_level,
        max_title_length=100,
        max_instructions_length=500,
        max_payload_bytes=16384,
        forbidden_terms=FORBIDDEN_NUMERIC_MEMORY_PHRASES | {"guess_the_number", "number_guessing"},
        required_payload_keys=["recall_mode"],
        min_duration_seconds=min_duration,
        verification_mode="memory_standard",
    )
