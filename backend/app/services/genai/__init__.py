"""Generative AI Service Package for SmartWake AI (Phase 4.0 Foundation)."""
from backend.app.services.genai.base_provider import BaseGenAIProvider
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
]
