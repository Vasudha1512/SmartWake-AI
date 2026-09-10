"""Google Gemini REST API Provider Adapter for SmartWake AI (Phase 4.0).

Encapsulates REST payload formation, authentication, timeouts, and error mapping
for Google Gemini without locking the architecture to a single fixed model.
"""
import json
import time
from typing import Any, Dict, Optional
import urllib.error
import urllib.request

from backend.app.core.exceptions import (
    GenAIConfigurationError,
    GenAIError,
    GenAIProviderUnavailableError,
    GenAIRateLimitError,
    GenAITimeoutError,
    GenAIValidationError,
)
from backend.app.schemas.genai_schemas import (
    GenAIContentRequest,
    GenAIGenerationResponse,
    GenAIProviderHealth,
)
from backend.app.services.genai.base_provider import BaseGenAIProvider

GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiProvider(BaseGenAIProvider):
    """Google Gemini HTTP REST adapter.

    Model-agnostic: accepts any valid model identifier (e.g. gemini-2.0-flash,
    gemini-2.5-flash) via configuration.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gemini-2.0-flash",
        timeout_seconds: float = 5.0,
        temperature: float = 0.7,
        max_retries: int = 1,
        api_base_url: str = GEMINI_API_BASE_URL,
    ) -> None:
        """Initialize GeminiProvider.

        Args:
            api_key: Google Gemini API key. If unset, provider cannot generate content.
            model_name: Configurable model identifier.
            timeout_seconds: Request timeout in seconds.
            temperature: Sampling temperature.
            max_retries: Retry attempts.
            api_base_url: API endpoint root.
        """
        super().__init__(
            model_name=model_name,
            timeout_seconds=timeout_seconds,
            temperature=temperature,
            max_retries=max_retries,
        )
        self._api_key = api_key
        self._api_base_url = api_base_url.rstrip("/")

    @property
    def provider_name(self) -> str:
        """Canonical provider identifier."""
        return "gemini"

    @property
    def has_api_key(self) -> bool:
        """Whether an API key has been supplied."""
        return bool(self._api_key and self._api_key.strip())

    def _build_endpoint_url(self) -> str:
        """Build the complete API endpoint URL including model and key parameter."""
        if not self.has_api_key:
            raise GenAIConfigurationError(
                "Gemini API key is not configured. Set GENAI_API_KEY environment variable."
            )
        return f"{self._api_base_url}/{self.model_name}:generateContent?key={self._api_key}"

    def build_request_payload(self, request: GenAIContentRequest) -> Dict[str, Any]:
        """Construct the Gemini REST JSON payload for a given request."""
        # System instructions or task framing
        task_instruction = (
            f"Generate wake-up challenge content for task type '{request.challenge_type}' "
            f"at difficulty '{request.difficulty_level}'."
        )
        if request.custom_instructions:
            task_instruction += f" {request.custom_instructions}"

        prompt_body = {
            "challenge_type": request.challenge_type,
            "difficulty_level": request.difficulty_level,
            "context": request.context_payload,
        }

        payload: Dict[str, Any] = {
            "contents": [
                {
                    "parts": [
                        {"text": json.dumps(prompt_body)}
                    ]
                }
            ],
            "systemInstruction": {
                "parts": [
                    {"text": task_instruction}
                ]
            },
            "generationConfig": {
                "temperature": self.temperature,
                "responseMimeType": "application/json",
            },
        }
        return payload

    def parse_gemini_response(
        self, response_dict: Dict[str, Any], elapsed_ms: float
    ) -> GenAIGenerationResponse:
        """Parse raw Gemini JSON response into standardized GenAIGenerationResponse."""
        try:
            candidates = response_dict.get("candidates", [])
            if not candidates:
                raise GenAIValidationError("Gemini response returned no candidates.")

            content_parts = (
                candidates[0].get("content", {}).get("parts", [])
            )
            if not content_parts:
                raise GenAIValidationError("Gemini candidate contains no content parts.")

            raw_text = content_parts[0].get("text", "")
            if not raw_text:
                raise GenAIValidationError("Gemini content part text is empty.")

            # Parse JSON content payload
            try:
                parsed_json = json.loads(raw_text)
            except json.JSONDecodeError as exc:
                raise GenAIValidationError(
                    f"Gemini response could not be parsed as JSON: {exc}"
                ) from exc

            if not isinstance(parsed_json, dict):
                parsed_json = {"result": parsed_json}

            # Extract token usage if available
            usage_metadata = response_dict.get("usageMetadata", {})
            total_tokens = usage_metadata.get("totalTokenCount")

            return GenAIGenerationResponse(
                content=parsed_json,
                raw_response=raw_text,
                provider_name=self.provider_name,
                model_name=self.model_name,
                latency_ms=elapsed_ms,
                tokens_used=total_tokens,
                metadata={
                    "finish_reason": candidates[0].get("finishReason"),
                    "safety_ratings": candidates[0].get("safetyRatings", []),
                },
            )
        except (KeyError, TypeError) as exc:
            raise GenAIValidationError(
                f"Unexpected Gemini response structure: {exc}"
            ) from exc

    def generate(self, request: GenAIContentRequest) -> GenAIGenerationResponse:
        """Execute HTTP request to Gemini API and return structured response."""
        url = self._build_endpoint_url()
        payload = self.build_request_payload(request)
        encoded_data = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            url=url,
            data=encoded_data,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": "SmartWake-AI-Backend/1.0",
            },
            method="POST",
        )

        start_time = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                raw_body = response.read().decode("utf-8")
                response_dict = json.loads(raw_body)
                return self.parse_gemini_response(response_dict, elapsed_ms)

        except urllib.error.HTTPError as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            status_code = exc.code
            error_body = ""
            try:
                error_body = exc.read().decode("utf-8")
            except Exception:
                pass

            if status_code in (401, 403):
                raise GenAIConfigurationError(
                    f"Gemini authentication failed (HTTP {status_code}). Check GENAI_API_KEY. {error_body}"
                ) from exc
            elif status_code == 429:
                raise GenAIRateLimitError(
                    f"Gemini API rate limit or quota exceeded (HTTP 429). {error_body}"
                ) from exc
            elif status_code >= 500:
                raise GenAIProviderUnavailableError(
                    f"Gemini service unavailable (HTTP {status_code}). {error_body}"
                ) from exc
            else:
                raise GenAIError(
                    f"Gemini API error (HTTP {status_code}): {error_body}"
                ) from exc

        except (urllib.error.URLError, TimeoutError) as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            if "timed out" in str(exc).lower() or isinstance(exc, TimeoutError):
                raise GenAITimeoutError(
                    f"Gemini request timed out after {self.timeout_seconds}s: {exc}"
                ) from exc
            raise GenAIProviderUnavailableError(
                f"Gemini network connection failed: {exc}"
            ) from exc

    def check_health(self) -> GenAIProviderHealth:
        """Inspect Gemini provider credentials and configuration."""
        if not self.has_api_key:
            return GenAIProviderHealth(
                is_healthy=False,
                provider_name=self.provider_name,
                model_name=self.model_name,
                message="Gemini provider unconfigured: GENAI_API_KEY is not set.",
                details={"api_key_configured": False},
            )

        # In Phase 4.0, we verify credentials and configuration without making billable calls
        return GenAIProviderHealth(
            is_healthy=True,
            provider_name=self.provider_name,
            model_name=self.model_name,
            message="Gemini provider configured and ready.",
            details={
                "api_key_configured": True,
                "model_name": self.model_name,
                "timeout_seconds": self.timeout_seconds,
            },
        )
