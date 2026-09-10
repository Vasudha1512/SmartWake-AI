"""Provider Factory and Registry for Generative AI in SmartWake AI (Phase 4.0).

Instantiates the active provider based on application configuration and supports
pluggable provider extensions.
"""
from typing import Dict, Optional, Type

from backend.app.core.config import settings
from backend.app.core.exceptions import GenAIConfigurationError
from backend.app.services.genai.base_provider import BaseGenAIProvider
from backend.app.services.genai.gemini_provider import GeminiProvider
from backend.app.services.genai.mock_provider import MockGenAIProvider

# Built-in provider registry mapping canonical names to implementation classes
_PROVIDER_REGISTRY: Dict[str, Type[BaseGenAIProvider]] = {
    "mock": MockGenAIProvider,
    "gemini": GeminiProvider,
}


def register_provider(name: str, provider_class: Type[BaseGenAIProvider]) -> None:
    """Register a custom provider class under a canonical name.

    Args:
        name: Provider identifier (e.g. 'mock', 'gemini', 'custom').
        provider_class: Class implementing BaseGenAIProvider.
    """
    clean_name = name.strip().lower()
    _PROVIDER_REGISTRY[clean_name] = provider_class


def list_registered_providers() -> list[str]:
    """Return sorted list of registered provider identifiers."""
    return sorted(list(_PROVIDER_REGISTRY.keys()))


def get_genai_provider(
    provider_name: Optional[str] = None,
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
    timeout_seconds: Optional[float] = None,
    temperature: Optional[float] = None,
    max_retries: Optional[int] = None,
) -> BaseGenAIProvider:
    """Instantiate and configure a GenAI provider.

    Pulls defaults from global settings if arguments are omitted.

    Args:
        provider_name: Canonical provider name ('mock', 'gemini').
        api_key: Provider API credentials (for Gemini).
        model_name: Model identifier string.
        timeout_seconds: Timeout threshold.
        temperature: Sampling temperature.
        max_retries: Retry attempts.

    Returns:
        BaseGenAIProvider: Configured provider instance.

    Raises:
        GenAIConfigurationError: If provider_name is not registered.
    """
    name = (provider_name or settings.GENAI_PROVIDER).strip().lower()

    if name not in _PROVIDER_REGISTRY:
        valid_options = list_registered_providers()
        raise GenAIConfigurationError(
            f"Unsupported GenAI provider '{name}'. Must be one of: {valid_options}."
        )

    provider_cls = _PROVIDER_REGISTRY[name]
    model = model_name or settings.GENAI_MODEL
    timeout = timeout_seconds if timeout_seconds is not None else settings.GENAI_TIMEOUT_SECONDS
    temp = temperature if temperature is not None else settings.GENAI_TEMPERATURE
    retries = max_retries if max_retries is not None else settings.GENAI_MAX_RETRIES

    if name == "gemini":
        key = api_key if api_key is not None else settings.GENAI_API_KEY
        return GeminiProvider(
            api_key=key,
            model_name=model,
            timeout_seconds=timeout,
            temperature=temp,
            max_retries=retries,
        )
    elif name == "mock":
        return MockGenAIProvider(
            model_name=model,
            timeout_seconds=timeout,
            temperature=temp,
            max_retries=retries,
        )
    else:
        # Generic instantiation for custom providers
        return provider_cls(
            model_name=model,
            timeout_seconds=timeout,
            temperature=temp,
            max_retries=retries,
        )
