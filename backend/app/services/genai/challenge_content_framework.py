"""Personalized Challenge Content Framework for SmartWake AI (Phase 4.1).

Coordinates safe context sanitization, generic constraint resolution, structured request
construction, provider execution, and pure in-memory content validation.
"""
from typing import Any, Dict, Optional, Union

from backend.app.core.constants import FORBIDDEN_CHALLENGE_TYPES, VALID_CHALLENGE_TYPES
from backend.app.core.exceptions import (
    ChallengeContentValidationError,
    InvalidChallengeTypeError,
    InvalidDifficultyError,
    UnsafePersonalizationContextError,
)
from backend.app.schemas.challenge_content_schemas import (
    FORBIDDEN_CONTEXT_KEYS,
    ChallengeGenerationConstraints,
    SafePersonalizationContext,
    ValidatedChallengeContent,
)
from backend.app.schemas.genai_schemas import (
    GenAIContentRequest,
    GenAIGenerationResponse,
)
from backend.app.services.genai.challenge_constraints import get_challenge_constraints
from backend.app.services.genai.challenge_content_validator import ChallengeContentValidator
from backend.app.services.genai.genai_service import GenAIService


def sanitize_personalization_context(
    raw_context: Optional[Union[SafePersonalizationContext, Dict[str, Any]]],
    strict: bool = True,
) -> SafePersonalizationContext:
    """Sanitize and filter personalization context for GenAI challenge generation.

    SECURITY & PRIVACY GUARANTEES:
    - Strips/rejects database identity (user_id, email, alarm_id, session_id).
    - Excludes authentication tokens, passwords, and raw database records.
    - Strictly bounds disallowed_topics (max 10 items, max 30 chars/item, max 300 total chars).
    - Clamps operational metrics (snooze count, attempt number, desired duration).

    NOTE ON PROMPT SAFETY:
    Context sanitization and strict topic bounds substantially reduce unbounded-input
    and prompt-injection risk, but do not claim to completely eliminate all adversarial
    prompt injection attacks.

    Args:
        raw_context: Raw input context dictionary or SafePersonalizationContext instance.
        strict: If True, raises UnsafePersonalizationContextError when forbidden identity
                keys are detected. If False, silently strips forbidden keys.

    Returns:
        SafePersonalizationContext: Validated, identity-free personalization context.

    Raises:
        UnsafePersonalizationContextError: If strict is True and forbidden identity keys are present,
                                           or if field bounds are violated.
    """
    if raw_context is None:
        return SafePersonalizationContext()

    if isinstance(raw_context, SafePersonalizationContext):
        return raw_context

    if not isinstance(raw_context, dict):
        raise UnsafePersonalizationContextError(
            f"Personalization context must be a dictionary, got {type(raw_context).__name__}."
        )

    # Detect forbidden identity/sensitive keys
    forbidden_present = [k for k in raw_context.keys() if k.lower() in FORBIDDEN_CONTEXT_KEYS]
    if forbidden_present:
        if strict:
            raise UnsafePersonalizationContextError(
                f"Personalization context contains forbidden identity/sensitive keys: {forbidden_present}. "
                "GenAI context must not contain database identity or user PII."
            )
        else:
            # Strip forbidden keys
            raw_context = {k: v for k, v in raw_context.items() if k.lower() not in FORBIDDEN_CONTEXT_KEYS}

    # Only pass permitted fields into SafePersonalizationContext
    allowed_fields = SafePersonalizationContext.model_fields.keys()
    filtered_data = {k: v for k, v in raw_context.items() if k in allowed_fields}

    try:
        return SafePersonalizationContext(**filtered_data)
    except (ValueError, TypeError) as exc:
        raise UnsafePersonalizationContextError(
            f"Failed to construct safe personalization context: {exc}"
        ) from exc


class ChallengeContentFramework:
    """Orchestrator for the Personalized Challenge Content Framework (Phase 4.1).

    Transforms authoritative challenge inputs into validated structured challenge content.
    """

    def __init__(self, genai_service: Optional[GenAIService] = None) -> None:
        """Initialize ChallengeContentFramework.

        Args:
            genai_service: Optional pre-configured GenAIService instance.
                           If omitted, instantiates default GenAIService.
        """
        self._genai_service = genai_service or GenAIService()

    @property
    def genai_service(self) -> GenAIService:
        """Active GenAIService instance."""
        return self._genai_service

    def build_generation_request(
        self,
        challenge_type: str,
        difficulty_level: str,
        safe_context: SafePersonalizationContext,
        constraints: ChallengeGenerationConstraints,
    ) -> GenAIContentRequest:
        """Construct a standardized GenAIContentRequest for the provider layer.

        Args:
            challenge_type: Validated canonical challenge category.
            difficulty_level: Validated concrete difficulty tier.
            safe_context: Sanitized, identity-free personalization context.
            constraints: Structural constraints and boundary slots.

        Returns:
            GenAIContentRequest: Standardized provider request contract.
        """
        # Build contextual guidelines without leaking identity
        context_payload: Dict[str, Any] = {
            "current_session_snooze_count": safe_context.current_session_snooze_count,
            "current_attempt_number": safe_context.current_attempt_number,
            "desired_duration_seconds": safe_context.desired_duration_seconds,
            "language": safe_context.language,
        }
        if safe_context.preferred_theme:
            context_payload["preferred_theme"] = safe_context.preferred_theme
        if safe_context.disallowed_topics:
            context_payload["disallowed_topics"] = safe_context.disallowed_topics

        # Instructions specifying the required structured JSON output format
        custom_instructions = (
            f"Generate a {difficulty_level} difficulty {challenge_type} wake-up challenge. "
            f"Output strictly valid JSON matching verification_mode '{constraints.verification_mode}'. "
            f"Required keys: {constraints.required_payload_keys}. "
            f"Forbidden concepts: {sorted(list(constraints.forbidden_terms))}."
        )

        return GenAIContentRequest(
            challenge_type=challenge_type,
            difficulty_level=difficulty_level,
            user_id=None,  # Explicitly None: no database identity sent to provider
            context_payload=context_payload,
            custom_instructions=custom_instructions,
        )

    def generate_and_validate(
        self,
        challenge_type: str,
        difficulty_level: str,
        raw_context: Optional[Union[SafePersonalizationContext, Dict[str, Any]]] = None,
        strict_context: bool = True,
    ) -> ValidatedChallengeContent:
        """Execute full framework lifecycle: sanitize context -> build request -> generate -> validate.

        Args:
            challenge_type: Authoritative user-selected challenge category.
            difficulty_level: Authoritative concrete difficulty ('easy', 'medium', 'hard').
            raw_context: Optional context dictionary or SafePersonalizationContext.
            strict_context: If True, raises error if forbidden identity keys are detected.

        Returns:
            ValidatedChallengeContent: Validated structured challenge domain model.

        Raises:
            InvalidChallengeTypeError: If challenge_type is invalid or forbidden.
            InvalidDifficultyError: If difficulty_level is invalid or not concrete.
            UnsafePersonalizationContextError: If context contains forbidden identity data.
            ChallengeContentValidationError: If provider output fails structured validation.
            GenAIError: If provider generation fails.
        """
        # 1. Validate inputs
        clean_type = challenge_type.strip().lower() if challenge_type else ""
        if clean_type in FORBIDDEN_CHALLENGE_TYPES:
            raise InvalidChallengeTypeError(
                f"Forbidden challenge type '{challenge_type}'. Memory challenges strictly forbid number guessing."
            )
        if clean_type not in VALID_CHALLENGE_TYPES:
            raise InvalidChallengeTypeError(
                f"Invalid challenge type '{challenge_type}'. Must be one of: {sorted(list(VALID_CHALLENGE_TYPES))}."
            )

        clean_diff = difficulty_level.strip().lower() if difficulty_level else ""
        if clean_diff not in ("easy", "medium", "hard"):
            raise InvalidDifficultyError(
                f"Invalid difficulty '{difficulty_level}'. Must be a concrete tier: 'easy', 'medium', or 'hard'."
            )

        # 2. Sanitize personalization context
        safe_ctx = sanitize_personalization_context(raw_context, strict=strict_context)

        # 3. Resolve generic constraints
        constraints = get_challenge_constraints(clean_type, clean_diff)

        # 4. Build standardized request
        request = self.build_generation_request(
            challenge_type=clean_type,
            difficulty_level=clean_diff,
            safe_context=safe_ctx,
            constraints=constraints,
        )

        # 5. Dispatch generation via GenAIService
        provider_response: GenAIGenerationResponse = self.genai_service.generate_challenge_content(request)

        # 6. Validate content via ChallengeContentValidator
        generation_meta = {
            "provider_name": provider_response.provider_name,
            "model_name": provider_response.model_name,
            "latency_ms": provider_response.latency_ms,
            "tokens_used": provider_response.tokens_used,
            "validation_passed": True,
        }

        validated_content = ChallengeContentValidator.validate_or_raise(
            raw_content=provider_response.content,
            requested_type=clean_type,
            requested_difficulty=clean_diff,
            constraints=constraints,
            generation_metadata=generation_meta,
        )

        return validated_content
