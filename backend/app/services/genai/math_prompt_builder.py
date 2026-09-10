"""Specialized Prompt Builder for AI-Generated Math Challenges (Phase 4.2).

Constructs sanitized, highly-structured GenAI prompts incorporating safe personalization
preferences, mathematical constraints, and rigid JSON schema instructions.
"""
from typing import Any, Dict, List, Optional

from backend.app.schemas.challenge_content_schemas import SafePersonalizationContext
from backend.app.schemas.genai_schemas import GenAIContentRequest
from backend.app.services.genai.math_generation_constraints import (
    MathGenerationConstraints,
    get_math_difficulty_constraints,
)


class MathPromptBuilder:
    """Specialized prompt constructor for AI-generated math wake challenges."""

    @classmethod
    def calculate_question_count(
        cls,
        constraints: MathGenerationConstraints,
        safe_context: SafePersonalizationContext,
    ) -> int:
        """Calibrate target question count based on desired_duration_seconds while respecting tier bounds.

        CRITICAL INVARIANT:
        `desired_duration_seconds` can adjust the question count within the tier's
        configured min/max, but it MUST NEVER mutate the concrete difficulty tier.
        """
        base_count = constraints.default_question_count
        duration = safe_context.desired_duration_seconds

        if duration is None:
            return base_count

        if duration <= 15:
            # Scaled down to lower bound for short duration
            target = constraints.min_question_count
        elif duration >= 45:
            # Scaled up towards upper bound for long duration
            target = constraints.max_question_count
        else:
            target = base_count

        # Strictly clamp within difficulty boundaries
        return max(constraints.min_question_count, min(constraints.max_question_count, target))

    @classmethod
    def build_custom_instructions(
        cls,
        constraints: MathGenerationConstraints,
        target_question_count: int,
        safe_context: SafePersonalizationContext,
    ) -> str:
        """Formulate precise, authoritative system and formatting instructions for the GenAI provider."""
        allowed_ops_str = ", ".join(sorted(list(constraints.allowed_operations)))
        banned_ops_str = ", ".join(sorted(list(constraints.banned_operations))) if constraints.banned_operations else "none"

        theme_text = (
            f" Context/Theme: '{safe_context.preferred_theme}'."
            if safe_context.preferred_theme
            else ""
        )

        instructions = (
            f"Generate a waking math challenge. Challenge type is locked to 'math'. "
            f"Difficulty is strictly locked to '{constraints.difficulty_level}' (DO NOT MUTATE DIFFICULTY).{theme_text}\n"
            f"Generate exactly {target_question_count} question(s).\n"
            f"MATHEMATICAL RULES:\n"
            f"1. Allowed operations: {allowed_ops_str}.\n"
            f"2. Banned operations: {banned_ops_str}, exponents, modulo, bitwise, trigonometry, variables, decimals.\n"
            f"3. All calculations must be pure integer arithmetic. All divisions must be exact integer division (no remainders).\n"
            f"4. Division by zero is strictly prohibited.\n"
            f"5. Operands must be within [{constraints.operand_min}, {constraints.operand_max}] with maximum absolute value {constraints.max_operand_abs}.\n"
            f"6. Intermediate results must not exceed absolute value {constraints.max_intermediate_abs}.\n"
            f"7. Final results must be within [{constraints.min_final_result}, {constraints.max_final_result}].\n"
            f"8. The expression constants must EXACTLY match the structured operands list.\n"
            f"OUTPUT FORMAT:\n"
            f"Output strictly valid JSON with no markdown explanations or conversational text. Format:\n"
            f'{{\n'
            f'  "challenge_type": "math",\n'
            f'  "difficulty_level": "{constraints.difficulty_level}",\n'
            f'  "title": "Clear concise challenge title",\n'
            f'  "instructions": "Clear user instructions for solving the arithmetic problems",\n'
            f'  "content_payload": {{\n'
            f'    "question_count": {target_question_count},\n'
            f'    "questions": [\n'
            f'      {{\n'
            f'        "question_id": 1,\n'
            f'        "question": "What is 17 + 8?",\n'
            f'        "expression": "17 + 8",\n'
            f'        "operation": "addition",\n'
            f'        "operands": [17, 8],\n'
            f'        "proposed_answer": 25\n'
            f'      }}\n'
            f'    ],\n'
            f'    "time_limit_seconds": {constraints.default_time_limit_seconds}\n'
            f'  }},\n'
            f'  "verification_mode": "math_standard",\n'
            f'  "min_duration_seconds": 10\n'
            f'}}'
        )
        return instructions

    @classmethod
    def build_request(
        cls,
        difficulty_level: str,
        safe_context: SafePersonalizationContext,
        constraints: Optional[MathGenerationConstraints] = None,
    ) -> GenAIContentRequest:
        """Construct a standardized GenAIContentRequest for Math challenge generation.

        Args:
            difficulty_level: Authoritative concrete difficulty tier.
            safe_context: Sanitized, identity-free personalization context.
            constraints: Optional pre-resolved MathGenerationConstraints.

        Returns:
            GenAIContentRequest: Provider request contract.
        """
        math_constraints = constraints or get_math_difficulty_constraints(difficulty_level)
        target_count = cls.calculate_question_count(math_constraints, safe_context)

        context_payload: Dict[str, Any] = {
            "current_session_snooze_count": safe_context.current_session_snooze_count,
            "current_attempt_number": safe_context.current_attempt_number,
            "desired_duration_seconds": safe_context.desired_duration_seconds,
            "language": safe_context.language,
            "target_question_count": target_count,
        }
        if safe_context.preferred_theme:
            context_payload["preferred_theme"] = safe_context.preferred_theme
        if safe_context.disallowed_topics:
            context_payload["disallowed_topics"] = safe_context.disallowed_topics

        custom_instructions = cls.build_custom_instructions(
            constraints=math_constraints,
            target_question_count=target_count,
            safe_context=safe_context,
        )

        return GenAIContentRequest(
            challenge_type="math",
            difficulty_level=math_constraints.difficulty_level,
            user_id=None,  # Zero database identity sent to provider
            context_payload=context_payload,
            custom_instructions=custom_instructions,
        )
