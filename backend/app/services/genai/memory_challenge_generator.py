"""AI-Generated Memory Challenge Generator for SmartWake AI (Phase 4.3).

Orchestrates prompt construction, provider dispatch, deterministic non-numeric memory
validation, independent answer derivation, and framework content validation.
"""
from typing import Any, Dict, Optional, Union

from backend.app.core.constants import FORBIDDEN_CHALLENGE_TYPES, VALID_CHALLENGE_TYPES
from backend.app.core.exceptions import (
    ChallengeContentValidationError,
    GenAIError,
    InvalidChallengeTypeError,
    InvalidDifficultyError,
    MemoryChallengeGenerationError,
    MemoryEvaluationError,
    UnsafePersonalizationContextError,
)
from backend.app.schemas.challenge_content_schemas import (
    SafePersonalizationContext,
    ValidatedChallengeContent,
)
from backend.app.schemas.genai_schemas import (
    GenAIContentRequest,
    GenAIGenerationResponse,
)
from backend.app.services.genai.challenge_content_framework import (
    sanitize_personalization_context,
)
from backend.app.services.genai.challenge_content_validator import ChallengeContentValidator
from backend.app.services.genai.genai_service import GenAIService
from backend.app.services.genai.memory_answer_validator import MemoryAnswerValidator
from backend.app.services.genai.memory_generation_constraints import (
    build_memory_generation_constraints,
    get_memory_difficulty_constraints,
)
from backend.app.services.genai.memory_prompt_builder import MemoryPromptBuilder


class MemoryChallengeGenerator:
    """Domain generator coordinating AI-generated memory wake challenges."""

    def __init__(self, genai_service: Optional[GenAIService] = None) -> None:
        """Initialize MemoryChallengeGenerator.

        Args:
            genai_service: Optional pre-configured GenAIService instance.
        """
        self._genai_service = genai_service or GenAIService()
        self._prompt_builder = MemoryPromptBuilder()

    @property
    def genai_service(self) -> GenAIService:
        """Active GenAIService instance."""
        return self._genai_service

    def generate_memory_challenge(
        self,
        difficulty_level: str,
        challenge_type: str = "memory",
        raw_context: Optional[Union[SafePersonalizationContext, Dict[str, Any]]] = None,
        strict_context: bool = True,
        preferred_mode: Optional[str] = None,
    ) -> ValidatedChallengeContent:
        """Generate, independently validate, and derive answer for an AI memory challenge.

        CRITICAL TRUST BOUNDARY:
        The expected answer is independently derived by deterministic Python logic.
        The LLM's proposed answer is never trusted as authoritative.
        Zero number guessing is strictly enforced on memory content.

        Args:
            difficulty_level: Authoritative concrete difficulty tier ('easy', 'medium', 'hard').
            challenge_type: Must be 'memory'.
            raw_context: Optional personalization context dictionary or SafePersonalizationContext.
            strict_context: If True, raises error on forbidden identity keys.
            preferred_mode: Optional specific recall mode requested.

        Returns:
            ValidatedChallengeContent: Validated structured challenge domain model with
                                       authoritative expected_answer.

        Raises:
            InvalidChallengeTypeError: If challenge_type is not 'memory'.
            InvalidDifficultyError: If difficulty is not concrete ('easy', 'medium', 'hard').
            UnsafePersonalizationContextError: If context contains forbidden identity data.
            MemoryEvaluationError: If memory structure, bounds, items, or continuity fail validation.
            ChallengeContentValidationError: If framework structure or forbidden terms fail validation.
            MemoryChallengeGenerationError: If domain pipeline encounters an unexpected coordination error.
        """
        # 1. Validate challenge type authority
        clean_type = challenge_type.strip().lower() if challenge_type else ""
        if clean_type in FORBIDDEN_CHALLENGE_TYPES or clean_type != "memory":
            raise InvalidChallengeTypeError(
                f"MemoryChallengeGenerator only supports challenge type 'memory', received '{challenge_type}'."
            )

        # 2. Validate concrete difficulty authority (Phase 3 is authoritative; 'adaptive' forbidden)
        clean_diff = difficulty_level.strip().lower() if difficulty_level else ""
        if clean_diff not in ("easy", "medium", "hard"):
            raise InvalidDifficultyError(
                f"Invalid difficulty '{difficulty_level}'. Must be a concrete tier: 'easy', 'medium', or 'hard'."
            )

        # 3. Sanitize personalization context (Zero database identity / PII)
        safe_ctx = sanitize_personalization_context(raw_context, strict=strict_context)

        # 4. Resolve memory-specific constraints and framework constraints
        mem_constraints = get_memory_difficulty_constraints(clean_diff)
        framework_constraints = build_memory_generation_constraints(clean_type, clean_diff)

        # 5. Build standardized provider request
        request = self._prompt_builder.build_request(
            difficulty_level=clean_diff,
            safe_context=safe_ctx,
            constraints=mem_constraints,
            preferred_mode=preferred_mode,
        )

        # 6. Dispatch generation via GenAIService
        try:
            provider_response: GenAIGenerationResponse = self.genai_service.generate_challenge_content(request)
        except (MemoryEvaluationError, ChallengeContentValidationError, UnsafePersonalizationContextError):
            raise
        except GenAIError:
            raise
        except Exception as exc:
            raise MemoryChallengeGenerationError(
                f"Unexpected provider dispatch failure in MemoryChallengeGenerator: {exc}"
            ) from exc

        raw_content = provider_response.content
        if not isinstance(raw_content, dict):
            raise ChallengeContentValidationError(
                "Provider returned malformed non-dictionary content for memory challenge."
            )

        # 7. Extract content payload for domain validation
        content_payload = raw_content.get("content_payload")
        if content_payload is None:
            content_payload = raw_content.get("content")

        if content_payload is None or not isinstance(content_payload, dict):
            raise ChallengeContentValidationError(
                "Generated memory content missing required 'content_payload' dictionary."
            )

        # 8. Deterministic Memory Validation & Authoritative Answer Derivation (TRUST BOUNDARY)
        validated_payload, authoritative_answer = MemoryAnswerValidator.validate_and_compute_payload(
            raw_payload=content_payload,
            difficulty_level=clean_diff,
        )

        # 9. Prepare canonical structured content for framework validation
        canonical_raw_content = dict(raw_content)
        canonical_raw_content["challenge_type"] = "memory"
        canonical_raw_content["difficulty_level"] = clean_diff
        canonical_raw_content["content_payload"] = validated_payload.model_dump()
        canonical_raw_content["expected_answer"] = authoritative_answer
        canonical_raw_content["verification_mode"] = framework_constraints.verification_mode
        canonical_raw_content["min_duration_seconds"] = int(
            raw_content.get("min_duration_seconds", framework_constraints.min_duration_seconds)
        )

        # 10. Pass through framework-level ChallengeContentValidator
        generation_metadata = {
            "provider_name": provider_response.provider_name,
            "model_name": provider_response.model_name,
            "latency_ms": provider_response.latency_ms,
            "tokens_used": provider_response.tokens_used,
            "authoritative_answer_derived": True,
            "authoritative_answer": authoritative_answer,
            "recall_mode": validated_payload.recall_mode,
        }

        validated_content = ChallengeContentValidator.validate_or_raise(
            raw_content=canonical_raw_content,
            requested_type="memory",
            requested_difficulty=clean_diff,
            constraints=framework_constraints,
            generation_metadata=generation_metadata,
        )

        return validated_content
