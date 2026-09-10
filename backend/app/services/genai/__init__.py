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
    # Phase 4.2 Math Challenge Exports
    "MathQuestionItem",
    "MathChallengePayload",
    "MathGenerationConstraints",
    "get_math_difficulty_constraints",
    "build_math_generation_constraints",
    "SafeArithmeticEvaluator",
    "MathAnswerValidator",
    "MathPromptBuilder",
    "MathChallengeGenerator",
]

# Phase 4.2 Schema and Service Imports
from backend.app.schemas.math_challenge_schemas import (
    MathChallengePayload,
    MathQuestionItem,
)
from backend.app.services.genai.math_answer_validator import (
    MathAnswerValidator,
    SafeArithmeticEvaluator,
)
from backend.app.services.genai.math_challenge_generator import MathChallengeGenerator
from backend.app.services.genai.math_generation_constraints import (
    MathGenerationConstraints,
    build_math_generation_constraints,
    get_math_difficulty_constraints,
)
from backend.app.services.genai.math_prompt_builder import MathPromptBuilder


