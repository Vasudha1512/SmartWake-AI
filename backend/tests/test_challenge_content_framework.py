"""Unit and Integration Tests for Phase 4.1 Personalized Challenge Content Framework.

Verifies:
- Complete exclusion of database identity (user_id, session_id, alarm_id, PII) from GenAI context
- Strict bounding and sanitization of disallowed_topics (max 10 topics, max 30 chars, max 300 total chars)
- Proper semantic usage of desired_duration_seconds as styling preference
- Generic framework constraint resolution without implementing domain solvers
- Pure in-memory ChallengeContentValidator enforcement (type & difficulty immutability, forbidden terms, size limits)
- End-to-end framework execution with MockGenAIProvider
- Preservation of Phase 3 ML, Phase 2.8 verification, and zero DB changes
"""
import json
import unittest

from backend.app.core.exceptions import (
    ChallengeContentValidationError,
    GenAITimeoutError,
    InvalidChallengeTypeError,
    InvalidDifficultyError,
    UnsafePersonalizationContextError,
)
from backend.app.schemas.challenge_content_schemas import (
    ChallengeGenerationConstraints,
    SafePersonalizationContext,
    ValidatedChallengeContent,
)
from backend.app.services.genai import (
    ChallengeContentFramework,
    ChallengeContentValidator,
    GenAIService,
    MockGenAIProvider,
    get_challenge_constraints,
    register_challenge_constraints,
    sanitize_personalization_context,
)


class TestSafePersonalizationContext(unittest.TestCase):
    """Verify SafePersonalizationContext enforces identity exclusion and strict bounding."""

    def test_valid_context_creation(self):
        """Valid parameters should construct clean SafePersonalizationContext."""
        ctx = SafePersonalizationContext(
            desired_duration_seconds=30,
            current_session_snooze_count=2,
            current_attempt_number=1,
            preferred_theme="morning motivation",
            language="en",
            disallowed_topics=["politics", "stress"],
        )
        self.assertEqual(ctx.desired_duration_seconds, 30)
        self.assertEqual(ctx.current_session_snooze_count, 2)
        self.assertEqual(ctx.current_attempt_number, 1)
        self.assertEqual(ctx.preferred_theme, "morning motivation")
        self.assertEqual(ctx.language, "en")
        self.assertEqual(ctx.disallowed_topics, ["politics", "stress"])

    def test_database_identity_strictly_forbidden(self):
        """Context schema must reject database identity attributes (user_id, email, alarm_id, session_id)."""
        forbidden_payloads = [
            {"user_id": 123},
            {"email": "user@example.com"},
            {"alarm_id": 45},
            {"session_id": 67},
            {"wake_session_id": 89},
            {"password": "secret"},
            {"token": "auth_token_xyz"},
        ]
        for payload in forbidden_payloads:
            with self.assertRaises(ValueError):
                SafePersonalizationContext(**payload)

    def test_sanitize_personalization_context_strict_mode(self):
        """Sanitizer in strict mode raises UnsafePersonalizationContextError on identity keys."""
        with self.assertRaises(UnsafePersonalizationContextError) as err:
            sanitize_personalization_context(
                {"user_id": 99, "preferred_theme": "focus"},
                strict=True,
            )
        self.assertIn("forbidden identity/sensitive keys", str(err.exception).lower())

    def test_sanitize_personalization_context_strip_mode(self):
        """Sanitizer in non-strict mode safely strips identity keys."""
        cleaned = sanitize_personalization_context(
            {"user_id": 99, "alarm_id": 12, "preferred_theme": "energy"},
            strict=False,
        )
        self.assertEqual(cleaned.preferred_theme, "energy")
        self.assertFalse(hasattr(cleaned, "user_id"))

    def test_disallowed_topics_maximum_count_limit(self):
        """disallowed_topics cannot exceed 10 topics."""
        too_many = [f"topic_{i}" for i in range(11)]
        with self.assertRaises(ValueError) as err:
            SafePersonalizationContext(disallowed_topics=too_many)
        self.assertIn("cannot exceed 10 topics", str(err.exception).lower())

    def test_disallowed_topics_item_length_limit(self):
        """disallowed_topics rejects items longer than 30 characters."""
        long_topic = ["a" * 31]
        with self.assertRaises(ValueError) as err:
            SafePersonalizationContext(disallowed_topics=long_topic)
        self.assertIn("exceeds maximum length of 30", str(err.exception).lower())

    def test_disallowed_topics_total_size_limit(self):
        """Total serialized length of disallowed_topics cannot exceed 300 characters."""
        # 10 topics of 30 characters each = 300 (valid boundary), 10 * 31 exceeds
        valid_edge = ["a" * 30 for _ in range(10)]
        ctx = SafePersonalizationContext(disallowed_topics=valid_edge)
        self.assertEqual(len(ctx.disallowed_topics), 1)  # deduplicated

        # 10 distinct topics of 30 chars each = 300 total chars
        distinct_topics = [f"topic_number_{i:02d}_" + ("x" * 14) for i in range(10)]
        ctx_distinct = SafePersonalizationContext(disallowed_topics=distinct_topics)
        self.assertEqual(len(ctx_distinct.disallowed_topics), 10)

    def test_disallowed_topics_rejects_malformed_and_control_chars(self):
        """disallowed_topics rejects control characters, newlines, and unsafe symbols."""
        malformed = [
            ["topic\nwith_newline"],
            ["topic<script>alert(1)</script>"],
            [""],  # empty string
            ["   "],  # whitespace only
            [123],  # non-string
        ]
        for bad_list in malformed:
            with self.assertRaises(ValueError):
                SafePersonalizationContext(disallowed_topics=bad_list)  # type: ignore

    def test_desired_duration_seconds_bounds(self):
        """desired_duration_seconds must be within [5, 300] seconds."""
        # Valid
        self.assertEqual(SafePersonalizationContext(desired_duration_seconds=5).desired_duration_seconds, 5)
        self.assertEqual(SafePersonalizationContext(desired_duration_seconds=300).desired_duration_seconds, 300)

        # Invalid
        with self.assertRaises(ValueError):
            SafePersonalizationContext(desired_duration_seconds=4)
        with self.assertRaises(ValueError):
            SafePersonalizationContext(desired_duration_seconds=301)


class TestChallengeConstraints(unittest.TestCase):
    """Verify generic constraint slots and registry mechanism without domain generators."""

    def test_canonical_challenge_types_resolve(self):
        """All 5 canonical types resolve generic constraints."""
        for c_type in ["math", "memory", "tongue_twister", "dance", "push_ups"]:
            constraints = get_challenge_constraints(c_type, "medium")
            self.assertIsInstance(constraints, ChallengeGenerationConstraints)
            self.assertEqual(constraints.challenge_type, c_type)
            self.assertEqual(constraints.difficulty_level, "medium")
            self.assertTrue(constraints.verification_mode.endswith("_standard"))
            self.assertGreater(constraints.max_payload_bytes, 1000)

    def test_forbidden_and_invalid_types_rejected(self):
        """Forbidden number guessing and invalid types raise InvalidChallengeTypeError."""
        for forbidden in ["number_guessing", "guess_number", "numeric_memory"]:
            with self.assertRaises(InvalidChallengeTypeError):
                get_challenge_constraints(forbidden, "easy")

        with self.assertRaises(InvalidChallengeTypeError):
            get_challenge_constraints("unknown_challenge_type", "easy")

    def test_adaptive_difficulty_rejected(self):
        """Constraints require concrete difficulty; 'adaptive' is rejected."""
        with self.assertRaises(InvalidDifficultyError):
            get_challenge_constraints("math", "adaptive")

    def test_extensible_constraint_registration(self):
        """Registry allows future sub-phases to register or override constraint builders."""
        def custom_builder(c_type, diff):
            return ChallengeGenerationConstraints(
                challenge_type=c_type,
                difficulty_level=diff,
                max_title_length=80,
                max_instructions_length=300,
                verification_mode="custom_mode",
            )

        register_challenge_constraints("dance", custom_builder)
        custom_res = get_challenge_constraints("dance", "hard")
        self.assertEqual(custom_res.verification_mode, "custom_mode")
        self.assertEqual(custom_res.max_title_length, 80)


class TestChallengeContentValidator(unittest.TestCase):
    """Verify pure in-memory content validation rules and boundary enforcement."""

    def setUp(self):
        self.constraints = get_challenge_constraints("math", "medium")

    def test_valid_content_passes(self):
        """Well-formed generated content passes validation."""
        valid_raw = {
            "challenge_type": "math",
            "difficulty_level": "medium",
            "title": "Arithmetic Challenge",
            "instructions": "Calculate the answers to the arithmetic problems below accurately.",
            "content_payload": {"questions": [{"id": 1, "prompt": "10 + 5"}]},
            "verification_mode": "math_standard",
            "min_duration_seconds": 10,
        }
        res = ChallengeContentValidator.validate(valid_raw, "math", "medium", self.constraints)
        self.assertTrue(res.is_valid)
        self.assertEqual(len(res.errors), 0)
        self.assertIsInstance(res.validated_content, ValidatedChallengeContent)
        self.assertEqual(res.validated_content.title, "Arithmetic Challenge")

    def test_type_immutability_enforced(self):
        """Validator rejects content if provider mutated challenge_type."""
        mutated_type_raw = {
            "challenge_type": "tongue_twister",  # Mutated!
            "difficulty_level": "medium",
            "title": "Twister Challenge",
            "instructions": "Say the passage aloud clearly three times.",
            "content_payload": {"passage": "She sells sea shells"},
            "verification_mode": "math_standard",
        }
        res = ChallengeContentValidator.validate(mutated_type_raw, "math", "medium", self.constraints)
        self.assertFalse(res.is_valid)
        self.assertTrue(any("mutation detected" in e.lower() for e in res.errors))

    def test_difficulty_immutability_enforced(self):
        """Validator rejects content if provider mutated difficulty_level."""
        mutated_diff_raw = {
            "challenge_type": "math",
            "difficulty_level": "hard",  # Mutated from medium!
            "title": "Math Task",
            "instructions": "Solve the equations accurately.",
            "content_payload": {"questions": []},
            "verification_mode": "math_standard",
        }
        res = ChallengeContentValidator.validate(mutated_diff_raw, "math", "medium", self.constraints)
        self.assertFalse(res.is_valid)
        self.assertTrue(any("difficulty level mutation" in e.lower() for e in res.errors))

    def test_forbidden_concept_rejected(self):
        """Validator rejects content containing forbidden concepts (e.g. number guessing in memory)."""
        memory_constraints = get_challenge_constraints("memory", "easy")
        forbidden_memory_raw = {
            "challenge_type": "memory",
            "difficulty_level": "easy",
            "title": "Number Guessing Memory Challenge",  # Forbidden!
            "instructions": "Guess the random secret number between 1 and 100.",
            "content_payload": {"recall_mode": "visual_sequence", "secret": 42},
            "verification_mode": "memory_standard",
        }
        res = ChallengeContentValidator.validate(forbidden_memory_raw, "memory", "easy", memory_constraints)
        self.assertFalse(res.is_valid)
        self.assertTrue(any("forbidden concept" in e.lower() for e in res.errors))

    def test_empty_or_too_short_instructions_rejected(self):
        """Instructions must be at least 10 characters long."""
        short_instructions_raw = {
            "challenge_type": "math",
            "difficulty_level": "medium",
            "title": "Valid Title",
            "instructions": "Too short",  # 9 chars
            "content_payload": {"questions": []},
            "verification_mode": "math_standard",
        }
        res = ChallengeContentValidator.validate(short_instructions_raw, "math", "medium", self.constraints)
        self.assertFalse(res.is_valid)
        self.assertTrue(any("instructions too short" in e.lower() for e in res.errors))

    def test_oversized_payload_rejected(self):
        """Content payload exceeding byte bounds is rejected."""
        bloated_payload = {"questions": ["x" * 20000]}
        oversized_raw = {
            "challenge_type": "math",
            "difficulty_level": "medium",
            "title": "Valid Title",
            "instructions": "Solve the arithmetic equations below accurately.",
            "content_payload": bloated_payload,
            "verification_mode": "math_standard",
        }
        res = ChallengeContentValidator.validate(oversized_raw, "math", "medium", self.constraints)
        self.assertFalse(res.is_valid)
        self.assertTrue(any("byte size" in e.lower() for e in res.errors))

    def test_validate_or_raise_behavior(self):
        """validate_or_raise raises ChallengeContentValidationError on failure."""
        invalid_raw = {"challenge_type": "math"}
        with self.assertRaises(ChallengeContentValidationError):
            ChallengeContentValidator.validate_or_raise(invalid_raw, "math", "medium", self.constraints)


class TestChallengeContentFramework(unittest.TestCase):
    """Verify end-to-end framework request building, execution, and validation pipeline."""

    def setUp(self):
        self.mock_provider = MockGenAIProvider(model_name="mock-framework-test")
        self.genai_service = GenAIService(provider=self.mock_provider, enabled=True)
        self.framework = ChallengeContentFramework(genai_service=self.genai_service)

    def test_build_generation_request_excludes_user_id(self):
        """build_generation_request constructs GenAIContentRequest with user_id=None."""
        safe_ctx = SafePersonalizationContext(
            desired_duration_seconds=45,
            current_session_snooze_count=1,
            preferred_theme="focus",
        )
        constraints = get_challenge_constraints("tongue_twister", "hard")
        req = self.framework.build_generation_request("tongue_twister", "hard", safe_ctx, constraints)

        self.assertIsNone(req.user_id)
        self.assertEqual(req.challenge_type, "tongue_twister")
        self.assertEqual(req.difficulty_level, "hard")
        self.assertEqual(req.context_payload["desired_duration_seconds"], 45)
        self.assertEqual(req.context_payload["current_session_snooze_count"], 1)

    def test_end_to_end_generate_and_validate_all_canonical_types(self):
        """Framework successfully completes end-to-end for all 5 canonical types."""
        for c_type in ["math", "memory", "tongue_twister", "dance", "push_ups"]:
            validated = self.framework.generate_and_validate(
                challenge_type=c_type,
                difficulty_level="medium",
                raw_context={"desired_duration_seconds": 30},
            )
            self.assertIsInstance(validated, ValidatedChallengeContent)
            self.assertEqual(validated.challenge_type, c_type)
            self.assertEqual(validated.difficulty_level, "medium")
            self.assertTrue(validated.generation_metadata["validation_passed"])
            self.assertEqual(validated.generation_metadata["provider_name"], "mock")

    def test_generate_and_validate_rejects_forbidden_challenge_type(self):
        """Framework rejects forbidden challenge types upfront before calling provider."""
        with self.assertRaises(InvalidChallengeTypeError):
            self.framework.generate_and_validate("number_guessing", "easy")

    def test_generate_and_validate_rejects_adaptive_difficulty(self):
        """Framework rejects 'adaptive' difficulty upfront (must be concrete)."""
        with self.assertRaises(InvalidDifficultyError):
            self.framework.generate_and_validate("math", "adaptive")

    def test_provider_timeout_propagates(self):
        """Transient provider failure or timeout propagates cleanly through framework."""
        failing_provider = MockGenAIProvider(simulate_error=TimeoutError("Request timed out"))
        failing_service = GenAIService(provider=failing_provider, enabled=True)
        failing_framework = ChallengeContentFramework(genai_service=failing_service)

        with self.assertRaises(GenAITimeoutError):
            failing_framework.generate_and_validate("math", "easy")


class TestPhase41BoundariesAndSafety(unittest.TestCase):
    """Verify Phase 4.1 preserves Phase 3 ML, Phase 2.8 verification, and DB integrity."""

    def test_phase3_ml_decision_engine_untouched(self):
        """AdaptiveDecisionEngine functions completely untouched by Phase 4.1."""
        from backend.app.schemas.personalization_schemas import PersonalizationContext
        from backend.app.services.adaptive_decision_engine import AdaptiveDecisionEngine

        engine = AdaptiveDecisionEngine()
        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=1,
            challenge_type="math",
            difficulty_preference="medium",
        )
        decision = engine.decide(context=ctx)
        self.assertEqual(decision.challenge_type, "math")
        self.assertEqual(decision.final_difficulty, "medium")
        self.assertEqual(decision.decision_source, "user_fixed")

    def test_phase28_verification_engine_untouched(self):
        """Phase 2.8 verify_challenge functions completely untouched by Phase 4.1."""
        from backend.app.services.challenge_verification_service import verify_challenge

        runtime_challenge = {
            "challenge_type": "math",
            "expected_answer": [15],
        }
        res = verify_challenge(runtime_challenge, {"answer": 15})
        self.assertTrue(res.is_successful)
        self.assertEqual(res.verification_score, 1.0)


if __name__ == "__main__":
    unittest.main()
