"""Mock GenAI Provider for SmartWake AI (Phase 4.0).

Provides deterministic contract-level mock responses for offline testing,
CI/CD validation, and interface verification without implementing challenge-specific
domain logic (which belongs to Phase 4.1-4.5).
"""
import time
from typing import Any, Dict, Optional

from backend.app.core.exceptions import (
    GenAIError,
    GenAITimeoutError,
    GenAIValidationError,
)
from backend.app.schemas.genai_schemas import (
    GenAIContentRequest,
    GenAIGenerationResponse,
    GenAIProviderHealth,
)
from backend.app.services.genai.base_provider import BaseGenAIProvider


class MockGenAIProvider(BaseGenAIProvider):
    """Deterministic, contract-level mock provider for testing and offline development.

    Strictly limited to contract verification:
    - Verifies request parsing and attribute preservation.
    - Emits structured mock payloads without challenge-specific algorithms.
    - Supports simulated error triggers for testing error handling and fallbacks.
    """

    def __init__(
        self,
        model_name: str = "mock-model",
        timeout_seconds: float = 5.0,
        temperature: float = 0.7,
        max_retries: int = 1,
        simulate_error: Optional[Exception] = None,
        simulate_latency_ms: float = 5.0,
        canned_content: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize MockGenAIProvider.

        Args:
            model_name: Test model name.
            timeout_seconds: Timeout threshold.
            temperature: Sampling temperature.
            max_retries: Max retries before failure.
            simulate_error: Optional exception to trigger on generate().
            simulate_latency_ms: Artificial latency to record in response.
            canned_content: Optional custom payload to return instead of default contract payload.
        """
        super().__init__(
            model_name=model_name,
            timeout_seconds=timeout_seconds,
            temperature=temperature,
            max_retries=max_retries,
        )
        self._simulate_error = simulate_error
        self._simulate_latency_ms = simulate_latency_ms
        self._canned_content = canned_content
        self.call_count: int = 0
        self.last_request: Optional[GenAIContentRequest] = None

    @property
    def provider_name(self) -> str:
        """Canonical provider identifier."""
        return "mock"

    def generate(self, request: GenAIContentRequest) -> GenAIGenerationResponse:
        """Return a deterministic contract-level mock response.

        Does NOT implement domain-specific challenge logic (e.g. math solvers,
        memory grids, phonetic analysis).
        """
        self.call_count += 1
        self.last_request = request

        # Handle simulated error injection for test verification
        if self._simulate_error is not None:
            if isinstance(self._simulate_error, GenAIError):
                raise self._simulate_error
            elif isinstance(self._simulate_error, TimeoutError):
                raise GenAITimeoutError(f"Simulated mock timeout: {self._simulate_error}")
            else:
                raise GenAIError(f"Simulated mock error: {self._simulate_error}")

        # Construct minimal generic structured payload to validate the contract
        if self._canned_content is not None:
            content = dict(self._canned_content)
        else:
            content = {
                "contract_valid": True,
                "challenge_type": request.challenge_type,
                "difficulty_level": request.difficulty_level,
                "mock_identifier": f"mock-{request.challenge_type}-{request.difficulty_level}",
                "generated_text": (
                    f"Contract-level mock challenge content for '{request.challenge_type}' "
                    f"at difficulty '{request.difficulty_level}'."
                ),
                "parameters": dict(request.context_payload),
            }

        return GenAIGenerationResponse(
            content=content,
            raw_response=str(content),
            provider_name=self.provider_name,
            model_name=self.model_name,
            latency_ms=self._simulate_latency_ms,
            tokens_used=42,
            metadata={
                "is_mock": True,
                "call_count": self.call_count,
            },
        )

    def check_health(self) -> GenAIProviderHealth:
        """Inspect mock provider readiness."""
        return GenAIProviderHealth(
            is_healthy=True,
            provider_name=self.provider_name,
            model_name=self.model_name,
            latency_ms=1.0,
            message="Mock GenAI provider operational (contract verification mode).",
            details={
                "mode": "contract_only",
                "call_count": self.call_count,
            },
        )
