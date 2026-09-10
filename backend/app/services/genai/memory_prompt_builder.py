"""Specialized Prompt Builder for AI-Generated Memory Challenges (Phase 4.3).

Constructs sanitized, highly-structured GenAI prompts incorporating safe personalization
preferences, memory constraints, and strict non-numeric rules without number guessing.
"""
from typing import Any, Dict, List, Optional

from backend.app.schemas.challenge_content_schemas import SafePersonalizationContext
from backend.app.schemas.genai_schemas import GenAIContentRequest
from backend.app.services.genai.memory_generation_constraints import (
    MemoryGenerationConstraints,
    get_memory_difficulty_constraints,
)


class MemoryPromptBuilder:
    """Specialized prompt constructor for AI-generated memory wake challenges."""

    @classmethod
    def calibrate_item_count(
        cls,
        constraints: MemoryGenerationConstraints,
        safe_context: SafePersonalizationContext,
    ) -> int:
        """Calibrate target sequence length or highlight count based on desired_duration_seconds.

        CRITICAL INVARIANT (Correction 5):
        `desired_duration_seconds` may influence content parameters ONLY inside the
        already-authoritative Phase 3 difficulty bounds. It must NEVER escalate or
        downgrade the concrete difficulty tier.
        """
        base_count = constraints.default_sequence_length
        duration = safe_context.desired_duration_seconds

        if duration is None:
            return base_count

        if duration <= 15:
            target = constraints.min_sequence_length
        elif duration >= 45:
            target = constraints.max_sequence_length
        else:
            target = base_count

        return max(constraints.min_sequence_length, min(constraints.max_sequence_length, target))

    @classmethod
    def build_custom_instructions(
        cls,
        constraints: MemoryGenerationConstraints,
        target_count: int,
        safe_context: SafePersonalizationContext,
        preferred_mode: Optional[str] = None,
    ) -> str:
        """Formulate precise instructions enforcing strict non-numeric memory rules."""
        allowed_modes = sorted(list(constraints.allowed_recall_modes))
        mode_instruction = (
            f"Allowed recall modes: {', '.join(allowed_modes)}."
        )
        if preferred_mode and preferred_mode in constraints.allowed_recall_modes:
            mode_instruction += f" Focus on mode: '{preferred_mode}'."

        theme_text = (
            f" Context/Theme: '{safe_context.preferred_theme}'."
            if safe_context.preferred_theme
            else ""
        )

        instructions = (
            f"Generate a waking memory challenge. Challenge type is locked to 'memory'. "
            f"Difficulty is strictly locked to '{constraints.difficulty_level}' (DO NOT MUTATE DIFFICULTY).{theme_text}\n"
            f"{mode_instruction}\n"
            f"Target sequence/highlight count: {target_count} items (bounded between {constraints.min_sequence_length} and {constraints.max_sequence_length}).\n"
            f"CRITICAL SAFETY & NON-NUMERIC RULES:\n"
            f"1. Memory challenges strictly forbid number guessing, digit sequence recall, PIN codes, OTPs, passcodes, and math equations.\n"
            f"2. Memory items (display_sequence, palette) MUST be non-numeric: use visual color names (e.g. emerald, amber, azure, coral), "
            f"geometric shapes (e.g. triangle, circle, diamond, star), or morning objects (e.g. coffee_cup, sunrise, alarm_clock).\n"
            f"3. Structural numeric fields (matrix_size, display_duration_seconds, time_limit_seconds, coordinates [row, col]) are permitted.\n"
            f"4. For spatial grid modes, matrix size must be between {constraints.min_matrix_size} and {constraints.max_matrix_size}. "
            f"All cell coordinates [row, col] must satisfy 0 <= row < matrix_size and 0 <= col < matrix_size.\n"
            f"5. For dynamic_spatial_path, consecutive steps must be adjacent (no jumps or teleporting).\n"
            f"OUTPUT FORMAT:\n"
            f"Output strictly valid JSON with no markdown explanations or extra fields. Match schema:\n"
            f'{{\n'
            f'  "challenge_type": "memory",\n'
            f'  "difficulty_level": "{constraints.difficulty_level}",\n'
            f'  "title": "Clear concise challenge title",\n'
            f'  "instructions": "Clear user instructions for memorizing and recalling the visual items",\n'
            f'  "content_payload": {{\n'
            f'    "recall_mode": "visual_sequence",\n'
            f'    "sequence_length": {target_count},\n'
            f'    "display_sequence": ["emerald", "amber", "azure"],\n'
            f'    "palette": ["emerald", "amber", "azure", "coral"],\n'
            f'    "display_duration_seconds": {constraints.default_display_duration_seconds},\n'
            f'    "time_limit_seconds": {constraints.default_time_limit_seconds},\n'
            f'    "proposed_answer": ["emerald", "amber", "azure"]\n'
            f'  }},\n'
            f'  "verification_mode": "memory_standard",\n'
            f'  "min_duration_seconds": 10\n'
            f'}}'
        )
        return instructions

    @classmethod
    def build_request(
        cls,
        difficulty_level: str,
        safe_context: SafePersonalizationContext,
        constraints: Optional[MemoryGenerationConstraints] = None,
        preferred_mode: Optional[str] = None,
    ) -> GenAIContentRequest:
        """Construct standardized GenAIContentRequest for Memory challenge generation.

        Args:
            difficulty_level: Authoritative concrete difficulty tier.
            safe_context: Sanitized, identity-free personalization context.
            constraints: Optional pre-resolved MemoryGenerationConstraints.
            preferred_mode: Optional specific recall mode to request.

        Returns:
            GenAIContentRequest: Provider request contract.
        """
        mem_constraints = constraints or get_memory_difficulty_constraints(difficulty_level)
        target_count = cls.calibrate_item_count(mem_constraints, safe_context)

        context_payload: Dict[str, Any] = {
            "current_session_snooze_count": safe_context.current_session_snooze_count,
            "current_attempt_number": safe_context.current_attempt_number,
            "desired_duration_seconds": safe_context.desired_duration_seconds,
            "language": safe_context.language,
            "target_item_count": target_count,
        }
        if safe_context.preferred_theme:
            context_payload["preferred_theme"] = safe_context.preferred_theme
        if safe_context.disallowed_topics:
            context_payload["disallowed_topics"] = safe_context.disallowed_topics
        if preferred_mode:
            context_payload["preferred_mode"] = preferred_mode

        custom_instructions = cls.build_custom_instructions(
            constraints=mem_constraints,
            target_count=target_count,
            safe_context=safe_context,
            preferred_mode=preferred_mode,
        )

        return GenAIContentRequest(
            challenge_type="memory",
            difficulty_level=mem_constraints.difficulty_level,
            user_id=None,  # Zero database identity sent to provider
            context_payload=context_payload,
            custom_instructions=custom_instructions,
        )
