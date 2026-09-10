"""AI-Generated Math Challenge Generator for SmartWake AI (Phase 4.2).

Orchestrates prompt construction, provider dispatch, deterministic mathematical
validation, independent answer computation, and framework content validation.
"""
from typing import Any, Dict, Optional, Union

from backend.app.core.constants import FORBIDDEN_CHALLENGE_TYPES, VALID_CHALLENGE_TYPES
from backend.app.core.exceptions import (
    ChallengeContentValidationError,
    GenAIError,
    InvalidChallengeTypeError,
    InvalidDifficultyError,
    MathChallengeGenerationError,
    MathEvaluationError,
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
from backend.app.services.genai.math_answer_validator import MathAnswerValidator
from backend.app.services.genai.math_generation_constraints import (
    build_math_generation_constraints,
    get_math_difficulty_constraints,
)
from backend.app.services.genai.math_prompt_builder import MathPromptBuilder


class MathChallengeGenerator:
    """Domain generator coordinating AI-generated math wake challenges."""

    def __init__(self, genai_service: Optional[GenAIService] = None) -> None:
        """Initialize MathChallengeGenerator.

        Args:
            genai_service: Optional pre-configured GenAIService instance.
        """
        self._genai_service = genai_service or GenAIService()
        self._prompt_builder = MathPromptBuilder()

    @property
    def genai_service(self) -> GenAIService:
        """Active GenAIService instance."""
        return self._genai_service

    def generate_math_challenge(
        self,
        difficulty_level: str,
        challenge_type: str = "math",
        raw_context: Optional[Union[SafePersonalizationContext, Dict[str, Any]]] = None,
        strict_context: bool = True,
    ) -> ValidatedChallengeContent:
        """Generate, independently validate, and calculate an AI-generated math wake challenge.

        CRITICAL TRUST BOUNDARY:
        The expected answer is independently calculated by deterministic Python logic.
        The LLM's proposed answer is never trusted as authoritative.

        Args:
            difficulty_level: Authoritative concrete difficulty tier ('easy', 'medium', 'hard').
            challenge_type: Must be 'math'.
            raw_context: Optional personalization context dictionary or SafePersonalizationContext.
            strict_context: If True, raises error on forbidden identity keys.

        Returns:
            ValidatedChallengeContent: Validated structured challenge domain model with
                                       authoritative expected_answer.

        Raises:
            InvalidChallengeTypeError: If challenge_type is not 'math'.
            InvalidDifficultyError: If difficulty is not concrete ('easy', 'medium', 'hard').
            UnsafePersonalizationContextError: If context contains forbidden identity data.
            MathEvaluationError: If math expressions, bounds, operands, or division fail validation.
            ChallengeContentValidationError: If framework structure or forbidden terms fail validation.
            MathChallengeGenerationError: If domain pipeline encounters an unexpected coordination error.
        """
        # 1. Validate challenge type authority
        clean_type = challenge_type.strip().lower() if challenge_type else ""
        if clean_type in FORBIDDEN_CHALLENGE_TYPES or clean_type != "math":
            raise InvalidChallengeTypeError(
                f"MathChallengeGenerator only supports challenge type 'math', received '{challenge_type}'."
            )

        # 2. Validate concrete difficulty authority (Phase 3 is authoritative; 'adaptive' forbidden)
        clean_diff = difficulty_level.strip().lower() if difficulty_level else ""
        if clean_diff not in ("easy", "medium", "hard"):
            raise InvalidDifficultyError(
                f"Invalid difficulty '{difficulty_level}'. Must be a concrete tier: 'easy', 'medium', or 'hard'."
            )

        # 3. Sanitize personalization context (Zero database identity / PII)
        safe_ctx = sanitize_personalization_context(raw_context, strict=strict_context)

        # 4. Resolve math-specific constraints and framework constraints
        math_constraints = get_math_difficulty_constraints(clean_diff)
        framework_constraints = build_math_generation_constraints(clean_type, clean_diff)

        # 5. Build standardized provider request
        request = self._prompt_builder.build_request(
            difficulty_level=clean_diff,
            safe_context=safe_ctx,
            constraints=math_constraints,
        )

        # 6. Dispatch generation via GenAIService
        try:
            provider_response: GenAIGenerationResponse = self.genai_service.generate_challenge_content(request)
        except (MathEvaluationError, ChallengeContentValidationError, UnsafePersonalizationContextError):
            raise
        except GenAIError:
            raise
        except Exception as exc:
            raise MathChallengeGenerationError(
                f"Unexpected provider dispatch failure in MathChallengeGenerator: {exc}"
            ) from exc

        raw_content = provider_response.content
        if not isinstance(raw_content, dict):
            raise ChallengeContentValidationError(
                "Provider returned malformed non-dictionary content for math challenge."
            )

        # 7. Extract content payload for mathematical validation
        content_payload = raw_content.get("content_payload")
        if content_payload is None:
            content_payload = raw_content.get("content")

        if content_payload is None or not isinstance(content_payload, dict):
            raise ChallengeContentValidationError(
                "Generated math content missing required 'content_payload' dictionary."
            )

        # 8. Deterministic Math Validation & Independent Answer Calculation (TRUST BOUNDARY)
        # Note: MathEvaluationError is preserved and bubbles up directly
        validated_payload, authoritative_answer = MathAnswerValidator.validate_and_compute_payload(
            payload_data=content_payload,
            difficulty_level=clean_diff,
        )

        # 9. Prepare canonical structured content for framework validation
        # Inject the independently verified content and authoritative expected answer
        canonical_raw_content = dict(raw_content)
        canonical_raw_content["challenge_type"] = "math"
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
            "authoritative_math_calculated": True,
            "authoritative_answer": authoritative_answer,
        }

        validated_content = ChallengeContentValidator.validate_or_raise(
            raw_content=canonical_raw_content,
            requested_type="math",
            requested_difficulty=clean_diff,
            constraints=framework_constraints,
            generation_metadata=generation_metadata,
        )

        return validated_content
