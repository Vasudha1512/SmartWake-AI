"""Math Generation Constraints and Difficulty Presets for SmartWake AI (Phase 4.2).

Defines deterministic mathematical boundaries, numeric safety limits, AST limits,
and operations allowed across Easy, Medium, and Hard tiers.
"""
from typing import Dict, List, Optional, Set
from pydantic import BaseModel, ConfigDict, Field

from backend.app.core.exceptions import InvalidDifficultyError
from backend.app.schemas.challenge_content_schemas import ChallengeGenerationConstraints

MATH_GLOBAL_FORBIDDEN_TERMS: Set[str] = {
    "number_guessing",
    "guess_number",
    "numeric_memory",
}


class MathGenerationConstraints(BaseModel):
    """Deterministic mathematical boundaries and resource safety limits for a difficulty tier."""

    difficulty_level: str = Field(..., description="Concrete difficulty tier ('easy', 'medium', 'hard')")
    allowed_operations: Set[str] = Field(..., description="Canonical allowed arithmetic operations")
    banned_operations: Set[str] = Field(default_factory=set, description="Explicitly forbidden operations")
    operand_min: int = Field(..., description="Standard minimum operand value")
    operand_max: int = Field(..., description="Standard maximum operand value")
    max_operand_abs: int = Field(..., description="Maximum permitted absolute value for any single operand")
    max_intermediate_abs: int = Field(..., description="Maximum permitted absolute value for any intermediate result")
    min_final_result: int = Field(..., description="Minimum permitted final evaluated result")
    max_final_result: int = Field(..., description="Maximum permitted final evaluated result")
    max_final_abs: int = Field(..., description="Maximum permitted final evaluated result absolute value")
    max_expression_length: int = Field(..., description="Maximum permitted expression string length in characters")
    max_ast_depth: int = Field(..., description="Maximum permitted depth of the parsed AST")
    max_ast_node_count: int = Field(..., description="Maximum permitted total AST node count")
    min_question_count: int = Field(default=1, ge=1, description="Minimum questions per challenge")
    max_question_count: int = Field(default=6, le=10, description="Maximum questions per challenge")
    default_question_count: int = Field(default=3, description="Baseline question count for difficulty tier")
    default_time_limit_seconds: int = Field(default=30, description="Baseline allocated time limit in seconds")
    allow_parentheses: bool = Field(default=False, description="Whether parentheses are permitted in expressions")
    exact_division_required: bool = Field(default=True, description="Whether all division operations must be exact")

    model_config = ConfigDict(from_attributes=True, frozen=True)


# =============================================================================
# DIFFICULTY PRESETS (Consistent with Phase 2.7.3 & Catalog Seeds)
# =============================================================================

EASY_MATH_CONSTRAINTS = MathGenerationConstraints(
    difficulty_level="easy",
    allowed_operations={"addition", "subtraction"},
    banned_operations={
        "division",
        "multiplication",
        "exponent",
        "modulo",
        "bitwise",
        "power",
    },
    operand_min=1,
    operand_max=15,
    max_operand_abs=15,
    max_intermediate_abs=30,
    min_final_result=0,
    max_final_result=30,
    max_final_abs=30,
    max_expression_length=20,
    max_ast_depth=2,
    max_ast_node_count=3,
    min_question_count=1,
    max_question_count=3,
    default_question_count=3,
    default_time_limit_seconds=20,
    allow_parentheses=False,
    exact_division_required=True,
)

MEDIUM_MATH_CONSTRAINTS = MathGenerationConstraints(
    difficulty_level="medium",
    allowed_operations={"addition", "subtraction", "multiplication", "division"},
    banned_operations={"exponent", "modulo", "bitwise", "power"},
    operand_min=2,
    operand_max=25,
    max_operand_abs=144,  # Dividend may reach 12 * 12 = 144
    max_intermediate_abs=200,
    min_final_result=0,
    max_final_result=150,
    max_final_abs=150,
    max_expression_length=35,
    max_ast_depth=3,
    max_ast_node_count=7,
    min_question_count=2,
    max_question_count=4,
    default_question_count=4,
    default_time_limit_seconds=35,
    allow_parentheses=False,
    exact_division_required=True,
)

HARD_MATH_CONSTRAINTS = MathGenerationConstraints(
    difficulty_level="hard",
    allowed_operations={"addition", "subtraction", "multiplication", "division", "parentheses", "mixed"},
    banned_operations={"exponent", "modulo", "bitwise", "power"},
    operand_min=2,
    operand_max=50,
    max_operand_abs=225,  # Dividend may reach 15 * 15 = 225
    max_intermediate_abs=1000,
    min_final_result=-50,
    max_final_result=500,
    max_final_abs=500,
    max_expression_length=50,
    max_ast_depth=4,
    max_ast_node_count=15,
    min_question_count=2,
    max_question_count=6,
    default_question_count=5,
    default_time_limit_seconds=50,
    allow_parentheses=True,
    exact_division_required=True,
)

_MATH_DIFFICULTY_MAP: Dict[str, MathGenerationConstraints] = {
    "easy": EASY_MATH_CONSTRAINTS,
    "medium": MEDIUM_MATH_CONSTRAINTS,
    "hard": HARD_MATH_CONSTRAINTS,
}


def get_math_difficulty_constraints(difficulty_level: str) -> MathGenerationConstraints:
    """Retrieve the MathGenerationConstraints for a concrete difficulty level.

    Args:
        difficulty_level: Concrete difficulty ('easy', 'medium', 'hard').

    Returns:
        MathGenerationConstraints: Strict mathematical and resource limits.

    Raises:
        InvalidDifficultyError: If difficulty is not concrete or unknown.
    """
    if not difficulty_level:
        raise InvalidDifficultyError("difficulty_level must be specified.")

    clean_diff = difficulty_level.strip().lower()
    if clean_diff not in _MATH_DIFFICULTY_MAP:
        raise InvalidDifficultyError(
            f"Invalid difficulty '{difficulty_level}'. Math challenges require concrete tier: 'easy', 'medium', or 'hard'."
        )

    return _MATH_DIFFICULTY_MAP[clean_diff]


def build_math_generation_constraints(
    challenge_type: str, difficulty_level: str
) -> ChallengeGenerationConstraints:
    """Construct framework ChallengeGenerationConstraints for Math challenges.

    Plugs into the Phase 4.1 framework registry (`_CONSTRAINT_REGISTRY['math']`).

    Args:
        challenge_type: Must be 'math'.
        difficulty_level: Concrete tier ('easy', 'medium', 'hard').

    Returns:
        ChallengeGenerationConstraints: Framework boundary configuration.
    """
    math_diff = get_math_difficulty_constraints(difficulty_level)

    min_duration = 10
    if math_diff.difficulty_level == "medium":
        min_duration = 15
    elif math_diff.difficulty_level == "hard":
        min_duration = 20

    return ChallengeGenerationConstraints(
        challenge_type="math",
        difficulty_level=math_diff.difficulty_level,
        max_title_length=100,
        max_instructions_length=500,
        max_payload_bytes=16384,
        forbidden_terms=MATH_GLOBAL_FORBIDDEN_TERMS | {"guess", "random_guess"},
        required_payload_keys=["questions"],
        min_duration_seconds=min_duration,
        verification_mode="math_standard",
    )
