"""Generative AI Service Package for SmartWake AI (Phases 4.0 & 4.1)."""
from backend.app.schemas.challenge_content_schemas import (
    ChallengeGenerationConstraints,
    ContentValidationResult,
    SafePersonalizationContext,
    ValidatedChallengeContent,
)
from backend.app.services.genai.base_provider import BaseGenAIProvider
from backend.app.services.genai.challenge_constraints import (
    get_challenge_constraints,
    register_challenge_constraints,
)
from backend.app.services.genai.challenge_content_framework import (
    ChallengeContentFramework,
    sanitize_personalization_context,
)
from backend.app.services.genai.challenge_content_validator import ChallengeContentValidator
from backend.app.services.genai.gemini_provider import GeminiProvider
from backend.app.services.genai.genai_service import GenAIService
from backend.app.services.genai.mock_provider import MockGenAIProvider
from backend.app.services.genai.provider_factory import (
    get_genai_provider,
    list_registered_providers,
    register_provider,
)

__all__ = [
    "BaseGenAIProvider",
    "MockGenAIProvider",
    "GeminiProvider",
    "GenAIService",
    "get_genai_provider",
    "list_registered_providers",
    "register_provider",
    # Phase 4.1 Framework Exports
    "ChallengeContentFramework",
    "ChallengeContentValidator",
    "SafePersonalizationContext",
    "ChallengeGenerationConstraints",
    "ValidatedChallengeContent",
    "ContentValidationResult",
    "get_challenge_constraints",
    "register_challenge_constraints",
    "sanitize_personalization_context",
]

