"""Challenge Generation Constraints Mechanism for SmartWake AI (Phase 4.1).

Defines generic framework constraint slots and provides an extensible registry
for challenge generation boundaries without implementing future sub-phase generators
(Math 4.2, Memory 4.3, Tongue Twister 4.4, Personalization 4.5).
"""
from typing import Callable, Dict, Optional, Set
from backend.app.core.constants import FORBIDDEN_CHALLENGE_TYPES, VALID_CHALLENGE_TYPES
from backend.app.core.exceptions import InvalidChallengeTypeError, InvalidDifficultyError
from backend.app.schemas.challenge_content_schemas import ChallengeGenerationConstraints

# Global forbidden terms enforced across all challenge types
GLOBAL_FORBIDDEN_TERMS: Set[str] = {
    "number_guessing",
    "guess_number",
    "numeric_memory",
}

# Constraint builder function type signature
ConstraintBuilder = Callable[[str, str], ChallengeGenerationConstraints]

# Registry mapping canonical challenge types to generic framework constraint builders
_CONSTRAINT_REGISTRY: Dict[str, ConstraintBuilder] = {}


def _build_default_math_constraints(challenge_type: str, difficulty: str) -> ChallengeGenerationConstraints:
    """Generic constraint slot for Math challenges (Phase 4.2 plugs in detailed rules)."""
    return ChallengeGenerationConstraints(
        challenge_type=challenge_type,
        difficulty_level=difficulty,
        max_title_length=100,
        max_instructions_length=500,
        max_payload_bytes=16384,
        forbidden_terms=GLOBAL_FORBIDDEN_TERMS | {"guess", "random_guess"},
        required_payload_keys=["questions"],
        min_duration_seconds=10,
        verification_mode="math_standard",
    )


def _build_default_memory_constraints(challenge_type: str, difficulty: str) -> ChallengeGenerationConstraints:
    """Generic constraint slot for Memory challenges (Phase 4.3 plugs in detailed rules)."""
    return ChallengeGenerationConstraints(
        challenge_type=challenge_type,
        difficulty_level=difficulty,
        max_title_length=100,
        max_instructions_length=500,
        max_payload_bytes=16384,
        forbidden_terms=GLOBAL_FORBIDDEN_TERMS | {"guess", "guess_the_number", "number_guessing"},
        required_payload_keys=["recall_mode"],
        min_duration_seconds=10,
        verification_mode="memory_standard",
    )


def _build_default_tongue_twister_constraints(challenge_type: str, difficulty: str) -> ChallengeGenerationConstraints:
    """Generic constraint slot for Tongue Twisters (Phase 4.4 plugs in detailed rules)."""
    return ChallengeGenerationConstraints(
        challenge_type=challenge_type,
        difficulty_level=difficulty,
        max_title_length=100,
        max_instructions_length=500,
        max_payload_bytes=16384,
        forbidden_terms=GLOBAL_FORBIDDEN_TERMS,
        required_payload_keys=["passage"],
        min_duration_seconds=10,
        verification_mode="tongue_twister_standard",
    )


def _build_default_dance_constraints(challenge_type: str, difficulty: str) -> ChallengeGenerationConstraints:
    """Generic constraint slot for Dance routines."""
    return ChallengeGenerationConstraints(
        challenge_type=challenge_type,
        difficulty_level=difficulty,
        max_title_length=100,
        max_instructions_length=500,
        max_payload_bytes=16384,
        forbidden_terms=GLOBAL_FORBIDDEN_TERMS,
        required_payload_keys=["steps"],
        min_duration_seconds=15,
        verification_mode="dance_standard",
    )


def _build_default_push_ups_constraints(challenge_type: str, difficulty: str) -> ChallengeGenerationConstraints:
    """Generic constraint slot for Push-ups repetition tracking."""
    return ChallengeGenerationConstraints(
        challenge_type=challenge_type,
        difficulty_level=difficulty,
        max_title_length=100,
        max_instructions_length=500,
        max_payload_bytes=16384,
        forbidden_terms=GLOBAL_FORBIDDEN_TERMS,
        required_payload_keys=["target_repetitions"],
        min_duration_seconds=15,
        verification_mode="push_ups_standard",
    )


from backend.app.services.genai.math_generation_constraints import (
    build_math_generation_constraints,
)
from backend.app.services.genai.memory_generation_constraints import (
    build_memory_generation_constraints,
)
from backend.app.services.genai.tongue_twister_generation_constraints import (
    build_tongue_twister_generation_constraints,
)

# Seed initial baseline constraint slots for canonical types
_CONSTRAINT_REGISTRY = {
    "math": build_math_generation_constraints,
    "memory": build_memory_generation_constraints,
    "tongue_twister": build_tongue_twister_generation_constraints,
    "dance": _build_default_dance_constraints,
    "push_ups": _build_default_push_ups_constraints,
}


def register_challenge_constraints(challenge_type: str, builder: ConstraintBuilder) -> None:
    """Register or override constraint builder for a challenge type.

    Used by future sub-phases (4.2-4.5) to plug in detailed domain rules.

    Args:
        challenge_type: Canonical challenge type.
        builder: Callable returning ChallengeGenerationConstraints.
    """
    clean_type = challenge_type.strip().lower()
    _CONSTRAINT_REGISTRY[clean_type] = builder


def get_challenge_constraints(challenge_type: str, difficulty_level: str) -> ChallengeGenerationConstraints:
    """Resolve generation constraints for a specific challenge type and difficulty.

    Args:
        challenge_type: Canonical challenge type.
        difficulty_level: Concrete difficulty ('easy', 'medium', 'hard').

    Returns:
        ChallengeGenerationConstraints: Structural constraints and boundary slots.

    Raises:
        InvalidChallengeTypeError: If challenge_type is unknown or forbidden.
        InvalidDifficultyError: If difficulty_level is not concrete.
    """
    if not challenge_type:
        raise InvalidChallengeTypeError("challenge_type must be specified.")

    clean_type = challenge_type.strip().lower()
    if clean_type in FORBIDDEN_CHALLENGE_TYPES:
        raise InvalidChallengeTypeError(
            f"Challenge type '{challenge_type}' is strictly forbidden. "
            "Memory challenges strictly forbid number guessing."
        )
    if clean_type not in VALID_CHALLENGE_TYPES:
        raise InvalidChallengeTypeError(
            f"Invalid challenge type '{challenge_type}'. Must be one of: {sorted(list(VALID_CHALLENGE_TYPES))}."
        )

    if not difficulty_level:
        raise InvalidDifficultyError("difficulty_level must be specified.")

    clean_diff = difficulty_level.strip().lower()
    if clean_diff not in ("easy", "medium", "hard"):
        raise InvalidDifficultyError(
            f"Invalid difficulty '{difficulty_level}'. Must be a concrete tier: 'easy', 'medium', or 'hard'."
        )

    builder = _CONSTRAINT_REGISTRY.get(clean_type)
    if not builder:
        raise InvalidChallengeTypeError(f"No constraint builder registered for challenge type '{clean_type}'.")

    return builder(clean_type, clean_diff)
