"""AI-Generated Tongue Twister Challenge Generator for SmartWake AI (Phase 4.4).

Orchestrates prompt construction, provider dispatch, deterministic tongue-twister
validation, independent answer derivation, and framework content validation.
"""
from typing import Any, Dict, Optional, Union

from backend.app.core.constants import FORBIDDEN_CHALLENGE_TYPES, VALID_CHALLENGE_TYPES
from backend.app.core.exceptions import (
    ChallengeContentValidationError,
    GenAIError,
    InvalidChallengeTypeError,
    InvalidDifficultyError,
    TongueTwisterChallengeGenerationError,
    TongueTwisterEvaluationError,
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
from backend.app.services.genai.tongue_twister_answer_validator import (
    TongueTwisterAnswerValidator,
)
from backend.app.services.genai.tongue_twister_generation_constraints import (
    build_tongue_twister_generation_constraints,
    get_tongue_twister_difficulty_constraints,
)
from backend.app.services.genai.tongue_twister_prompt_builder import (
    TongueTwisterPromptBuilder,
)


class TongueTwisterChallengeGenerator:
    """Domain generator coordinating AI-generated tongue twister wake challenges."""

    def __init__(self, genai_service: Optional[GenAIService] = None) -> None:
        """Initialize TongueTwisterChallengeGenerator.

        Args:
            genai_service: Optional pre-configured GenAIService instance.
        """
        self._genai_service = genai_service or GenAIService()
        self._prompt_builder = TongueTwisterPromptBuilder()

    @property
    def genai_service(self) -> GenAIService:
        """Active GenAIService instance."""
        return self._genai_service

    def generate_tongue_twister_challenge(
        self,
        difficulty_level: str,
        challenge_type: str = "tongue_twister",
        raw_context: Optional[Union[SafePersonalizationContext, Dict[str, Any]]] = None,
        strict_context: bool = True,
    ) -> ValidatedChallengeContent:
        """Generate, independently validate, and derive answer for an AI tongue twister challenge.

        CRITICAL TRUST BOUNDARY:
        The expected answer is independently derived by deterministic Python logic.
        The LLM's proposed answer is never trusted as authoritative.
        Authoritative repetition and speaking duration policies are strictly application-owned.

        Args:
            difficulty_level: Authoritative concrete difficulty tier ('easy', 'medium', 'hard').
            challenge_type: Must be 'tongue_twister'.
            raw_context: Optional personalization context dictionary or SafePersonalizationContext.
            strict_context: If True, raises error on forbidden identity keys.

        Returns:
            ValidatedChallengeContent: Validated structured challenge domain model with
                                       authoritative expected_answer.

        Raises:
            InvalidChallengeTypeError: If challenge_type is not 'tongue_twister'.
            InvalidDifficultyError: If difficulty is not concrete ('easy', 'medium', 'hard').
            UnsafePersonalizationContextError: If context contains forbidden identity data.
            TongueTwisterEvaluationError: If tongue twister structure, bounds, sound pattern, or answers fail.
            ChallengeContentValidationError: If framework structure or forbidden terms fail validation.
            TongueTwisterChallengeGenerationError: If domain pipeline encounters an unexpected coordination error.
        """
        # 1. Validate challenge type authority
        clean_type = challenge_type.strip().lower() if challenge_type else ""
        if clean_type in FORBIDDEN_CHALLENGE_TYPES or clean_type != "tongue_twister":
            raise InvalidChallengeTypeError(
                f"TongueTwisterChallengeGenerator only supports challenge type 'tongue_twister', received '{challenge_type}'."
            )

        # 2. Validate concrete difficulty authority (Phase 3 is authoritative; 'adaptive' forbidden)
        clean_diff = difficulty_level.strip().lower() if difficulty_level else ""
        if clean_diff not in ("easy", "medium", "hard"):
            raise InvalidDifficultyError(
                f"Invalid difficulty '{difficulty_level}'. Must be a concrete tier: 'easy', 'medium', or 'hard'."
            )

        # 3. Sanitize personalization context (Zero database identity / PII)
        safe_ctx = sanitize_personalization_context(raw_context, strict=strict_context)

        # 4. Resolve tongue-twister constraints and framework constraints
        tt_constraints = get_tongue_twister_difficulty_constraints(clean_diff)
        framework_constraints = build_tongue_twister_generation_constraints(clean_type, clean_diff)

        # 5. Build standardized provider request
        request = self._prompt_builder.build_request(
            difficulty_level=clean_diff,
            safe_context=safe_ctx,
            constraints=tt_constraints,
        )

        # 6. Dispatch generation via GenAIService
        try:
            provider_response: GenAIGenerationResponse = self.genai_service.generate_challenge_content(request)
        except (TongueTwisterEvaluationError, ChallengeContentValidationError, UnsafePersonalizationContextError):
            raise
        except GenAIError:
            raise
        except Exception as exc:
            raise TongueTwisterChallengeGenerationError(
                f"Unexpected provider dispatch failure in TongueTwisterChallengeGenerator: {exc}"
            ) from exc

        raw_content = provider_response.content
        if not isinstance(raw_content, dict):
            raise ChallengeContentValidationError(
                "Provider returned malformed non-dictionary content for tongue twister challenge."
            )

        # 7. Extract content payload for domain validation
        content_payload = raw_content.get("content_payload")
        if content_payload is None:
            content_payload = raw_content.get("content")

        if content_payload is None or not isinstance(content_payload, dict):
            raise ChallengeContentValidationError(
                "Generated tongue twister content missing required 'content_payload' dictionary."
            )

        # 8. Deterministic Tongue Twister Validation & Authoritative Answer Derivation (TRUST BOUNDARY)
        validated_payload, authoritative_answer, authoritative_reps, authoritative_duration = (
            TongueTwisterAnswerValidator.validate_and_compute_payload(
                raw_payload=content_payload,
                difficulty_level=clean_diff,
            )
        )

        # 9. Prepare canonical structured content for framework validation
        payload_dict = validated_payload.model_dump()
        payload_dict["target_repetitions"] = authoritative_reps
        payload_dict["speaking_duration_seconds"] = authoritative_duration
        actual_words = authoritative_answer.split()
        payload_dict["target_word_count"] = len(actual_words)

        canonical_raw_content = dict(raw_content)
        canonical_raw_content["challenge_type"] = "tongue_twister"
        canonical_raw_content["difficulty_level"] = clean_diff
        canonical_raw_content["content_payload"] = payload_dict
        canonical_raw_content["expected_answer"] = authoritative_answer
        canonical_raw_content["verification_mode"] = framework_constraints.verification_mode
        canonical_raw_content["min_duration_seconds"] = authoritative_duration

        # 10. Pass through framework-level ChallengeContentValidator
        generation_metadata = {
            "provider_name": provider_response.provider_name,
            "model_name": provider_response.model_name,
            "latency_ms": provider_response.latency_ms,
            "tokens_used": provider_response.tokens_used,
            "authoritative_answer_derived": True,
            "authoritative_answer": authoritative_answer,
            "authoritative_repetitions": authoritative_reps,
            "authoritative_speaking_duration": authoritative_duration,
            "phonetic_focus": validated_payload.phonetic_focus,
        }

        validated_content = ChallengeContentValidator.validate_or_raise(
            raw_content=canonical_raw_content,
            requested_type="tongue_twister",
            requested_difficulty=clean_diff,
            constraints=framework_constraints,
            generation_metadata=generation_metadata,
        )

        return validated_content
