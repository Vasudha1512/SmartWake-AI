"""Specialized Prompt Builder for AI-Generated Tongue Twister Challenges (Phase 4.4).

Constructs sanitized, highly-structured GenAI prompts incorporating safe personalization
preferences, tongue twister constraints, sound-pattern rules, and strict identity exclusion.
"""
from typing import Any, Dict, Optional, Tuple

from backend.app.schemas.challenge_content_schemas import SafePersonalizationContext
from backend.app.schemas.genai_schemas import GenAIContentRequest
from backend.app.services.genai.tongue_twister_generation_constraints import (
    TongueTwisterGenerationConstraints,
    get_tongue_twister_difficulty_constraints,
)


class TongueTwisterPromptBuilder:
    """Specialized prompt constructor for AI-generated tongue twister wake challenges."""

    @classmethod
    def calibrate_parameters(
        cls,
        constraints: TongueTwisterGenerationConstraints,
        safe_context: SafePersonalizationContext,
    ) -> Tuple[int, int, int]:
        """Calibrate target word count, repetitions, and duration based on desired_duration_seconds.

        CRITICAL INVARIANT:
        `desired_duration_seconds` may influence content parameters ONLY inside the
        already-authoritative Phase 3 difficulty bounds. It must NEVER escalate or
        downgrade the concrete difficulty tier.
        """
        base_words = constraints.default_word_count
        base_reps = constraints.default_repetitions
        base_duration = constraints.default_speaking_duration_seconds
        duration = safe_context.desired_duration_seconds

        if duration is None:
            return base_words, base_reps, base_duration

        if duration <= 15:
            target_words = constraints.min_word_count
            target_reps = constraints.min_repetitions
            target_duration = constraints.min_speaking_duration_seconds
        elif duration >= 45:
            target_words = constraints.max_word_count
            target_reps = constraints.max_repetitions
            target_duration = constraints.max_speaking_duration_seconds
        else:
            target_words = base_words
            target_reps = base_reps
            target_duration = base_duration

        target_words = max(constraints.min_word_count, min(constraints.max_word_count, target_words))
        target_reps = max(constraints.min_repetitions, min(constraints.max_repetitions, target_reps))
        target_duration = max(
            constraints.min_speaking_duration_seconds,
            min(constraints.max_speaking_duration_seconds, target_duration),
        )

        return target_words, target_reps, target_duration

    @classmethod
    def build_custom_instructions(
        cls,
        constraints: TongueTwisterGenerationConstraints,
        target_words: int,
        target_reps: int,
        target_duration: int,
        safe_context: SafePersonalizationContext,
    ) -> str:
        """Formulate precise instructions enforcing sound patterns, bounds, and non-numeric rules."""
        theme_text = (
            f" Context/Theme: '{safe_context.preferred_theme}'."
            if safe_context.preferred_theme
            else ""
        )

        instructions = (
            f"Generate a waking tongue twister challenge. Challenge type is locked to 'tongue_twister'. "
            f"Difficulty is strictly locked to '{constraints.difficulty_level}' (DO NOT MUTATE DIFFICULTY).{theme_text}\n"
            f"Language is locked to English ('en').\n"
            f"Target word count: ~{target_words} words (bounded between {constraints.min_word_count} and {constraints.max_word_count} words).\n"
            f"Target repetitions: {target_reps} times (bounded between {constraints.min_repetitions} and {constraints.max_repetitions}).\n"
            f"Speaking time limit: {target_duration} seconds.\n"
            f"CRITICAL SAFETY & TEXT RULES:\n"
            f"1. Passage must be a genuine English tongue twister with dense alliteration or alternating consonant sounds "
            f"(e.g. s/sh, p/b, t/th, f/v, cl/cr, sl/sn).\n"
            f"2. DO NOT use digit characters (0-9). Numbers must be spelled out as words (e.g. 'thirty-three' instead of '33').\n"
            f"3. No number guessing, PIN codes, OTPs, arithmetic, or meta-instructions.\n"
            f"4. The passage string must be a SINGLE coherent sentence or verse. Do not duplicate the sentence multiple times in the passage.\n"
            f"5. Natural punctuation is allowed. Do not use abusive repeated punctuation (e.g. '???', '!!!').\n"
            f"OUTPUT FORMAT:\n"
            f"Output strictly valid JSON with no markdown explanations or extra fields. Match schema:\n"
            f'{{\n'
            f'  "challenge_type": "tongue_twister",\n'
            f'  "difficulty_level": "{constraints.difficulty_level}",\n'
            f'  "title": "Clear concise challenge title",\n'
            f'  "instructions": "Articulate the passage clearly aloud {target_reps} times",\n'
            f'  "content_payload": {{\n'
            f'    "passage": "Example tongue twister passage with prominent alliterative consonant patterns.",\n'
            f'    "target_repetitions": {target_reps},\n'
            f'    "phonetic_focus": "prominent_consonant_pattern",\n'
            f'    "target_word_count": {target_words},\n'
            f'    "speaking_duration_seconds": {target_duration},\n'
            f'    "language": "en",\n'
            f'    "proposed_answer": "Example tongue twister passage with prominent alliterative consonant patterns."\n'
            f'  }},\n'
            f'  "verification_mode": "tongue_twister_standard",\n'
            f'  "min_duration_seconds": {constraints.min_speaking_duration_seconds}\n'
            f'}}'
        )
        return instructions

    @classmethod
    def build_request(
        cls,
        difficulty_level: str,
        safe_context: SafePersonalizationContext,
        constraints: Optional[TongueTwisterGenerationConstraints] = None,
    ) -> GenAIContentRequest:
        """Construct standardized GenAIContentRequest for Tongue Twister generation.

        Args:
            difficulty_level: Authoritative concrete difficulty tier.
            safe_context: Sanitized, identity-free personalization context.
            constraints: Optional pre-resolved TongueTwisterGenerationConstraints.

        Returns:
            GenAIContentRequest: Provider request contract.
        """
        tt_constraints = constraints or get_tongue_twister_difficulty_constraints(difficulty_level)
        target_words, target_reps, target_duration = cls.calibrate_parameters(
            tt_constraints, safe_context
        )

        context_payload: Dict[str, Any] = {
            "current_session_snooze_count": safe_context.current_session_snooze_count,
            "current_attempt_number": safe_context.current_attempt_number,
            "desired_duration_seconds": safe_context.desired_duration_seconds,
            "language": "en",
            "target_word_count": target_words,
            "target_repetitions": target_reps,
            "speaking_duration_seconds": target_duration,
        }
        if safe_context.preferred_theme:
            context_payload["preferred_theme"] = safe_context.preferred_theme
        if safe_context.disallowed_topics:
            context_payload["disallowed_topics"] = safe_context.disallowed_topics

        custom_instructions = cls.build_custom_instructions(
            constraints=tt_constraints,
            target_words=target_words,
            target_reps=target_reps,
            target_duration=target_duration,
            safe_context=safe_context,
        )

        return GenAIContentRequest(
            challenge_type="tongue_twister",
            difficulty_level=tt_constraints.difficulty_level,
            user_id=None,  # Zero database identity sent to provider
            context_payload=context_payload,
            custom_instructions=custom_instructions,
        )
