"""Base Provider Interface for Generative AI in SmartWake AI (Phase 4.0).

Defines the abstract contract all GenAI model providers must fulfill.
"""
from abc import ABC, abstractmethod
from typing import Optional

from backend.app.schemas.genai_schemas import (
    GenAIContentRequest,
    GenAIGenerationResponse,
    GenAIProviderHealth,
)


class BaseGenAIProvider(ABC):
    """Abstract interface defining required provider behaviors."""

    def __init__(
        self,
        model_name: str = "default",
        timeout_seconds: float = 5.0,
        temperature: float = 0.7,
        max_retries: int = 1,
    ) -> None:
        """Initialize base provider parameters.

        Args:
            model_name: Identifier for the model.
            timeout_seconds: Request timeout in seconds.
            temperature: Sampling temperature for variety.
            max_retries: Retries before raising or falling back.
        """
        self._model_name = model_name
        self._timeout_seconds = timeout_seconds
        self._temperature = temperature
        self._max_retries = max_retries

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Unique canonical identifier for the provider (e.g., 'mock', 'gemini')."""
        pass

    @property
    def model_name(self) -> str:
        """Configured model identifier."""
        return self._model_name

    @property
    def timeout_seconds(self) -> float:
        """Configured request timeout in seconds."""
        return self._timeout_seconds

    @property
    def temperature(self) -> float:
        """Configured sampling temperature."""
        return self._temperature

    @abstractmethod
    def generate(self, request: GenAIContentRequest) -> GenAIGenerationResponse:
        """Generate structured challenge content matching request specifications.

        Args:
            request: Validated GenAIContentRequest specifying challenge_type,
                     difficulty_level, and contextual parameters.

        Returns:
            GenAIGenerationResponse: Standardized response with structured content payload.

        Raises:
            GenAIError: Base or specialized exception if generation fails.
        """
        pass

    @abstractmethod
    def check_health(self) -> GenAIProviderHealth:
        """Inspect provider readiness, connectivity, and credentials.

        Returns:
            GenAIProviderHealth: Health diagnostic status.
        """
        pass
