"""Pydantic schemas and structural data contracts for AI-Generated Math Challenges (Phase 4.2).

Defines:
- MathQuestionItem: Individual structured math question item returned by GenAI.
- MathChallengePayload: Complete math challenge payload containing questions, count, and time limit.
"""
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class MathQuestionItem(BaseModel):
    """Structured question item for an AI-generated math problem.

    Contains the presentation question, the restricted mathematical expression,
    the declared operation, the structured operands, and an untrusted proposed answer.
    """

    question_id: int = Field(
        ...,
        ge=1,
        le=100,
        description="1-indexed unique identifier for the question within this challenge",
    )
    question: str = Field(
        ...,
        min_length=3,
        max_length=200,
        description="User-facing question prompt text (e.g., 'What is 17 × 6?')",
    )
    expression: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="Restricted mathematical expression string (e.g., '17 * 6')",
    )
    operation: str = Field(
        ...,
        min_length=3,
        max_length=30,
        description="Canonical arithmetic operation category (e.g., 'addition', 'multiplication', 'division', 'mixed')",
    )
    operands: List[int] = Field(
        ...,
        min_length=2,
        max_length=5,
        description="Structured list of integer operands used in the expression",
    )
    proposed_answer: Optional[int] = Field(
        default=None,
        description="Untrusted LLM-proposed answer; validated independently by MathAnswerValidator",
    )

    model_config = ConfigDict(from_attributes=True)

    @field_validator("question")
    @classmethod
    def validate_question_text(cls, v: str) -> str:
        clean = v.strip() if isinstance(v, str) else ""
        if not clean:
            raise ValueError("question text cannot be empty or whitespace only.")
        return clean

    @field_validator("expression")
    @classmethod
    def validate_expression_string(cls, v: str) -> str:
        clean = v.strip() if isinstance(v, str) else ""
        if not clean:
            raise ValueError("expression cannot be empty or whitespace only.")
        return clean

    @field_validator("operation")
    @classmethod
    def validate_operation_name(cls, v: str) -> str:
        clean = v.strip().lower() if isinstance(v, str) else ""
        if not clean:
            raise ValueError("operation name cannot be empty.")
        return clean

    @field_validator("operands")
    @classmethod
    def validate_operands_list(cls, v: List[int]) -> List[int]:
        if not isinstance(v, list) or len(v) < 2:
            raise ValueError("operands must contain at least 2 integer values.")
        for idx, item in enumerate(v):
            if not isinstance(item, int) or isinstance(item, bool):
                raise ValueError(f"operands[{idx}] must be a pure integer, got {type(item).__name__}.")
        return v


class MathChallengePayload(BaseModel):
    """Complete structured payload for an AI-generated math challenge.

    Enclosed inside ValidatedChallengeContent.content_payload.
    """

    question_count: int = Field(
        ...,
        ge=1,
        le=10,
        description="Total number of math questions in this challenge",
    )
    questions: List[MathQuestionItem] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="List of structured math questions",
    )
    time_limit_seconds: int = Field(
        default=30,
        ge=10,
        le=120,
        description="Allocated time limit in seconds for completing the challenge",
    )

    model_config = ConfigDict(from_attributes=True)

    @field_validator("questions")
    @classmethod
    def validate_questions_consistency(
        cls, v: List[MathQuestionItem]
    ) -> List[MathQuestionItem]:
        if not v:
            raise ValueError("questions list cannot be empty.")
        q_ids = [q.question_id for q in v]
        if len(q_ids) != len(set(q_ids)):
            raise ValueError(f"Duplicate question_id detected in questions: {q_ids}")
        return v
