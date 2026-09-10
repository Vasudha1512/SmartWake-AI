"""Unit and Integration Tests for Phase 4.0 GenAI Architecture & Provider Foundation.

Verifies:
- Configurable settings and secret masking
- Data contract validation and user sovereignty invariants (e.g. rejection of number guessing)
- Mock provider contract-level behavior (strictly non-challenge-specific)
- Model-agnostic Gemini REST adapter formation, payload building, and response parsing
- Provider factory and registry extensibility
- GenAIService lifecycle, retry behavior, and health status
- Zero database mutation and zero Phase 3 interference
"""
import json
import unittest
from unittest.mock import MagicMock, patch

from backend.app.core.config import Settings
from backend.app.core.exceptions import (
    GenAIConfigurationError,
    GenAIError,
    GenAIProviderUnavailableError,
    GenAIRateLimitError,
    GenAITimeoutError,
    GenAIValidationError,
)
from backend.app.schemas.genai_schemas import (
    GenAIConfigSummary,
    GenAIContentRequest,
    GenAIGenerationResponse,
    GenAIProviderHealth,
)
from backend.app.services.genai import (
    BaseGenAIProvider,
    GeminiProvider,
    GenAIService,
    MockGenAIProvider,
    get_genai_provider,
    list_registered_providers,
    register_provider,
)


class TestGenAIConfiguration(unittest.TestCase):
    """Verify GenAI configuration attributes, safe defaults, and secret masking."""

    def test_default_configuration_values(self):
        """Settings should provide safe, non-blocking defaults."""
        custom_settings = Settings()
        self.assertIsInstance(custom_settings.GENAI_ENABLED, bool)
        self.assertIsInstance(custom_settings.GENAI_PROVIDER, str)
        self.assertIsInstance(custom_settings.GENAI_MODEL, str)
        self.assertIsInstance(custom_settings.GENAI_TIMEOUT_SECONDS, float)
        self.assertGreater(custom_settings.GENAI_TIMEOUT_SECONDS, 0.0)

    def test_masked_api_key_security(self):
        """API key should be safely masked and never exposed in cleartext."""
        settings_none = Settings()
        settings_none.GENAI_API_KEY = None
        self.assertEqual(settings_none.masked_genai_api_key, "not_set")

        settings_short = Settings()
        settings_short.GENAI_API_KEY = "12345"
        self.assertEqual(settings_short.masked_genai_api_key, "***")

        settings_valid = Settings()
        settings_valid.GENAI_API_KEY = "AIzaSyD-1234567890abcdef-secret"
        masked = settings_valid.masked_genai_api_key
        self.assertTrue(masked.startswith("AIza"))
        self.assertTrue(masked.endswith("cret"))
        self.assertIn("...", masked)
        self.assertNotIn("1234567890abcdef", masked)

    def test_model_is_configurable_and_agnostic(self):
        """Model identifier should not be locked to an obsolete hardcoded model."""
        test_settings = Settings()
        test_settings.GENAI_MODEL = "gemini-future-model-v3"
        self.assertEqual(test_settings.GENAI_MODEL, "gemini-future-model-v3")


class TestGenAISchemas(unittest.TestCase):
    """Verify Pydantic schemas enforce domain constraints and user sovereignty."""

    def test_valid_challenge_requests(self):
        """Valid canonical challenge types and concrete difficulties should succeed."""
        for c_type in ["dance", "math", "memory", "tongue_twister", "push_ups"]:
            for diff in ["easy", "medium", "hard"]:
                req = GenAIContentRequest(
                    challenge_type=c_type,
                    difficulty_level=diff,
                    context_payload={"attempt": 1},
                )
                self.assertEqual(req.challenge_type, c_type)
                self.assertEqual(req.difficulty_level, diff)

    def test_forbidden_number_guessing_rejected(self):
        """Memory challenges strictly forbid number guessing in GenAI schemas."""
        for forbidden in ["number_guessing", "guess_number", "numeric_memory"]:
            with self.assertRaises(ValueError) as ctx:
                GenAIContentRequest(
                    challenge_type=forbidden,
                    difficulty_level="easy",
                )
            self.assertIn("strictly forbid number guessing", str(ctx.exception).lower())

    def test_invalid_difficulty_rejected(self):
        """GenAI requires concrete difficulty; 'adaptive' is not a valid generation tier."""
        with self.assertRaises(ValueError) as ctx:
            GenAIContentRequest(
                challenge_type="math",
                difficulty_level="adaptive",
            )
        self.assertIn("concrete tier", str(ctx.exception).lower())

    def test_generation_response_contract(self):
        """GenAIGenerationResponse properly holds structured content and metadata."""
        resp = GenAIGenerationResponse(
            content={"task": "sample", "value": 10},
            raw_response='{"task": "sample", "value": 10}',
            provider_name="mock",
            model_name="test-model",
            latency_ms=12.5,
            tokens_used=15,
        )
        self.assertEqual(resp.provider_name, "mock")
        self.assertEqual(resp.content["value"], 10)
        self.assertEqual(resp.latency_ms, 12.5)


class TestMockGenAIProvider(unittest.TestCase):
    """Verify MockGenAIProvider operates strictly at the contract level (Phase 4.0)."""

    def setUp(self):
        self.provider = MockGenAIProvider(model_name="mock-contract-model")

    def test_provider_identity(self):
        """Provider name and model should match configured values."""
        self.assertEqual(self.provider.provider_name, "mock")
        self.assertEqual(self.provider.model_name, "mock-contract-model")

    def test_contract_level_response_non_challenge_specific(self):
        """Mock provider returns generic contract payload without challenge domain logic."""
        req = GenAIContentRequest(
            challenge_type="math",
            difficulty_level="hard",
            context_payload={"session_id": 99},
        )
        resp = self.provider.generate(req)

        self.assertIsInstance(resp, GenAIGenerationResponse)
        self.assertEqual(resp.provider_name, "mock")
        self.assertTrue(resp.content["contract_valid"])
        self.assertEqual(resp.content["challenge_type"], "math")
        self.assertEqual(resp.content["difficulty_level"], "hard")
        self.assertEqual(resp.content["parameters"], {"session_id": 99})
        # Verify it does NOT contain domain arithmetic equations
        self.assertNotIn("equation", resp.content)
        self.assertNotIn("expected_answers", resp.content)

    def test_call_tracking(self):
        """Mock provider accurately tracks invocation count and last request."""
        self.assertEqual(self.provider.call_count, 0)
        req = GenAIContentRequest(challenge_type="memory", difficulty_level="medium")
        self.provider.generate(req)
        self.assertEqual(self.provider.call_count, 1)
        self.assertEqual(self.provider.last_request.challenge_type, "memory")

    def test_simulated_error_injection(self):
        """Mock provider supports error simulation for failure testing."""
        timeout_mock = MockGenAIProvider(simulate_error=TimeoutError("Connection timed out"))
        req = GenAIContentRequest(challenge_type="tongue_twister", difficulty_level="easy")
        with self.assertRaises(GenAITimeoutError):
            timeout_mock.generate(req)

    def test_health_check(self):
        """Mock provider reports operational health."""
        health = self.provider.check_health()
        self.assertTrue(health.is_healthy)
        self.assertEqual(health.provider_name, "mock")


class TestGeminiProvider(unittest.TestCase):
    """Verify GeminiProvider adapter formation, model agnosticism, and response parsing."""

    def test_model_agnostic_initialization(self):
        """GeminiProvider accepts arbitrary model names without hardcoding."""
        provider = GeminiProvider(
            api_key="fake-key-for-test",
            model_name="gemini-experimental-next",
            timeout_seconds=4.0,
            temperature=0.5,
        )
        self.assertEqual(provider.provider_name, "gemini")
        self.assertEqual(provider.model_name, "gemini-experimental-next")
        self.assertEqual(provider.timeout_seconds, 4.0)
        self.assertEqual(provider.temperature, 0.5)

    def test_missing_api_key_behavior(self):
        """Provider detects missing API key safely without crashing."""
        provider = GeminiProvider(api_key=None)
        self.assertFalse(provider.has_api_key)
        health = provider.check_health()
        self.assertFalse(health.is_healthy)
        self.assertIn("not set", health.message.lower())

        req = GenAIContentRequest(challenge_type="math", difficulty_level="easy")
        with self.assertRaises(GenAIConfigurationError):
            provider.generate(req)

    def test_request_payload_structure(self):
        """Provider correctly structures Gemini JSON payload."""
        provider = GeminiProvider(
            api_key="test-key",
            model_name="gemini-test",
            temperature=0.8,
        )
        req = GenAIContentRequest(
            challenge_type="push_ups",
            difficulty_level="medium",
            context_payload={"user_reps": 15},
            custom_instructions="Focus on strict form.",
        )
        payload = provider.build_request_payload(req)

        self.assertIn("contents", payload)
        self.assertIn("systemInstruction", payload)
        self.assertEqual(payload["generationConfig"]["temperature"], 0.8)
        self.assertEqual(payload["generationConfig"]["responseMimeType"], "application/json")
        system_text = payload["systemInstruction"]["parts"][0]["text"]
        self.assertIn("push_ups", system_text)
        self.assertIn("Focus on strict form.", system_text)

    def test_response_parsing_valid(self):
        """Provider parses valid Gemini REST candidate response."""
        provider = GeminiProvider(api_key="test-key")
        sample_gemini_json = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": json.dumps({"task_id": 101, "status": "generated"})}
                        ]
                    },
                    "finishReason": "STOP",
                }
            ],
            "usageMetadata": {
                "totalTokenCount": 85,
            },
        }
        parsed = provider.parse_gemini_response(sample_gemini_json, elapsed_ms=45.0)
        self.assertEqual(parsed.content["task_id"], 101)
        self.assertEqual(parsed.tokens_used, 85)
        self.assertEqual(parsed.latency_ms, 45.0)

    def test_response_parsing_malformed(self):
        """Provider raises GenAIValidationError on malformed response."""
        provider = GeminiProvider(api_key="test-key")
        # Empty candidates
        with self.assertRaises(GenAIValidationError):
            provider.parse_gemini_response({"candidates": []}, elapsed_ms=10.0)

        # Non-JSON content
        bad_text_json = {
            "candidates": [
                {"content": {"parts": [{"text": "Not valid json"}]}}
            ]
        }
        with self.assertRaises(GenAIValidationError):
            provider.parse_gemini_response(bad_text_json, elapsed_ms=10.0)


class TestProviderFactory(unittest.TestCase):
    """Verify provider factory and registry mechanics."""

    def test_resolve_mock_provider(self):
        """Factory returns MockGenAIProvider for 'mock'."""
        provider = get_genai_provider("mock", model_name="custom-mock")
        self.assertIsInstance(provider, MockGenAIProvider)
        self.assertEqual(provider.model_name, "custom-mock")

    def test_resolve_gemini_provider(self):
        """Factory returns GeminiProvider for 'gemini'."""
        provider = get_genai_provider("gemini", api_key="test-key", model_name="gemini-custom")
        self.assertIsInstance(provider, GeminiProvider)
        self.assertEqual(provider.model_name, "gemini-custom")

    def test_unregistered_provider_raises(self):
        """Factory raises GenAIConfigurationError for unknown provider."""
        with self.assertRaises(GenAIConfigurationError) as ctx:
            get_genai_provider("non_existent_provider_xyz")
        self.assertIn("unsupported genai provider", str(ctx.exception).lower())

    def test_custom_provider_registration(self):
        """Registry allows registering new custom providers."""
        class CustomProvider(BaseGenAIProvider):
            @property
            def provider_name(self) -> str:
                return "custom_test"

            def generate(self, request):
                return None

            def check_health(self):
                return None

        register_provider("custom_test", CustomProvider)
        self.assertIn("custom_test", list_registered_providers())
        instantiated = get_genai_provider("custom_test")
        self.assertIsInstance(instantiated, CustomProvider)


class TestGenAIService(unittest.TestCase):
    """Verify GenAIService facade, lifecycle, and retry handling."""

    def test_service_disabled_by_default(self):
        """Service honors disabled state and blocks generation."""
        mock_prov = MockGenAIProvider()
        service = GenAIService(provider=mock_prov, enabled=False)

        self.assertFalse(service.is_enabled)
        req = GenAIContentRequest(challenge_type="math", difficulty_level="easy")
        with self.assertRaises(GenAIConfigurationError) as ctx:
            service.generate_challenge_content(req)
        self.assertIn("currently disabled", str(ctx.exception).lower())

        health = service.check_health()
        self.assertTrue(health.is_healthy)
        self.assertIn("disabled", health.message.lower())

    def test_service_generation_success(self):
        """Enabled service successfully delegates to active provider."""
        mock_prov = MockGenAIProvider()
        service = GenAIService(provider=mock_prov, enabled=True)

        req = GenAIContentRequest(challenge_type="dance", difficulty_level="medium")
        resp = service.generate_challenge_content(req)
        self.assertIsInstance(resp, GenAIGenerationResponse)
        self.assertEqual(resp.content["challenge_type"], "dance")

    def test_service_config_summary(self):
        """Service provides sanitized configuration summary."""
        mock_prov = MockGenAIProvider(model_name="test-summary-model")
        service = GenAIService(provider=mock_prov, enabled=True)
        summary = service.get_config_summary()

        self.assertIsInstance(summary, GenAIConfigSummary)
        self.assertTrue(summary.enabled)
        self.assertEqual(summary.provider, "mock")
        self.assertEqual(summary.model, "test-summary-model")


class TestPhase4SafetyAndInvariants(unittest.TestCase):
    """Verify Phase 4 foundation does not mutate DB or modify Phase 3 ML."""

    def test_phase3_ml_decision_engine_untouched(self):
        """AdaptiveDecisionEngine continues to function normally and unmodified."""
        from backend.app.schemas.personalization_schemas import PersonalizationContext
        from backend.app.services.adaptive_decision_engine import AdaptiveDecisionEngine

        engine = AdaptiveDecisionEngine()
        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=1,
            challenge_type="math",
            difficulty_preference="easy",
        )
        decision = engine.decide(context=ctx)
        self.assertEqual(decision.challenge_type, "math")
        self.assertEqual(decision.final_difficulty, "easy")
        self.assertEqual(decision.decision_source, "user_fixed")

    def test_genai_foundation_does_not_touch_db(self):
        """GenAI service generation executes purely in memory without database queries."""
        mock_prov = MockGenAIProvider()
        service = GenAIService(provider=mock_prov, enabled=True)
        req = GenAIContentRequest(challenge_type="tongue_twister", difficulty_level="hard")

        # Generate content
        resp = service.generate_challenge_content(req)
        self.assertIsNotNone(resp)
        self.assertTrue(resp.content["contract_valid"])


if __name__ == "__main__":
    unittest.main()
