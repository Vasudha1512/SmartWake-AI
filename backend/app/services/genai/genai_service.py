"""GenAI Service Boundary for SmartWake AI (Phase 4.0).

Encapsulates provider execution, retry handling, and configuration management
behind a stable application service interface.
"""
from typing import Optional

from backend.app.core.config import settings
from backend.app.core.exceptions import (
    GenAIConfigurationError,
    GenAIError,
    GenAITimeoutError,
)
from backend.app.schemas.genai_schemas import (
    GenAIConfigSummary,
    GenAIContentRequest,
    GenAIGenerationResponse,
    GenAIProviderHealth,
)
from backend.app.services.genai.base_provider import BaseGenAIProvider
from backend.app.services.genai.provider_factory import get_genai_provider


class GenAIService:
    """Application service interface for Generative AI operations."""

    def __init__(
        self,
        provider: Optional[BaseGenAIProvider] = None,
        enabled: Optional[bool] = None,
    ) -> None:
        """Initialize GenAIService.

        Args:
            provider: Optional pre-configured provider instance. If None,
                      resolved dynamically via provider factory.
            enabled: Optional master toggle override. If None, uses settings.GENAI_ENABLED.
        """
        self._provider = provider
        self._enabled = enabled if enabled is not None else settings.GENAI_ENABLED

    @property
    def is_enabled(self) -> bool:
        """Whether GenAI capabilities are globally enabled."""
        return self._enabled

    @property
    def provider(self) -> BaseGenAIProvider:
        """Active provider instance, lazily instantiated if needed."""
        if self._provider is None:
            self._provider = get_genai_provider()
        return self._provider

    def get_config_summary(self) -> GenAIConfigSummary:
        """Return a sanitized summary of current GenAI configuration."""
        active_provider = self.provider
        return GenAIConfigSummary(
            enabled=self.is_enabled,
            provider=active_provider.provider_name,
            model=active_provider.model_name,
            timeout_seconds=active_provider.timeout_seconds,
            max_retries=settings.GENAI_MAX_RETRIES,
            temperature=active_provider.temperature,
            api_key_configured=bool(settings.GENAI_API_KEY),
            masked_api_key=settings.masked_genai_api_key,
        )

    def check_health(self) -> GenAIProviderHealth:
        """Inspect health of the active GenAI provider."""
        if not self.is_enabled:
            return GenAIProviderHealth(
                is_healthy=True,
                provider_name=self.provider.provider_name,
                model_name=self.provider.model_name,
                message="GenAI features are currently disabled in configuration (safe dormant state).",
                details={"enabled": False},
            )
        return self.provider.check_health()

    def generate_challenge_content(
        self, request: GenAIContentRequest
    ) -> GenAIGenerationResponse:
        """Generate structured challenge content via the active provider.

        Applies retry policies and timeout guardrails.

        Args:
            request: Validated GenAIContentRequest specifications.

        Returns:
            GenAIGenerationResponse: Structured generation payload and metadata.

        Raises:
            GenAIConfigurationError: If GenAI is disabled or provider is misconfigured.
            GenAIError: If generation fails across all retry attempts.
        """
        if not self.is_enabled:
            raise GenAIConfigurationError(
                "GenAI challenge generation is currently disabled. Set GENAI_ENABLED=true to activate."
            )

        max_attempts = max(1, settings.GENAI_MAX_RETRIES + 1)
        last_exception: Optional[Exception] = None

        for attempt in range(1, max_attempts + 1):
            try:
                return self.provider.generate(request)
            except (GenAITimeoutError, GenAIError) as exc:
                last_exception = exc
                if attempt >= max_attempts:
                    raise exc

        if last_exception:
            raise last_exception
        raise GenAIError("Unknown error occurred during GenAI content generation.")
