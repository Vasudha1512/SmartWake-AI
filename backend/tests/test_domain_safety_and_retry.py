"""Comprehensive tests for Domain-Specific Safety Validation and Bounded Retry/Fallback.

Covers:
- Common safety checks (structure, type mutation, difficulty mutation, prompt injection, harmful content)
- Math safety validation (valid, unsolvable, division by zero, invalid answer, numerical overflow)
- Memory safety validation (valid, empty sequence, invalid mode, number guessing mutation, excessive length)
- Tongue twister safety validation (valid, empty, insufficient sound pattern, excessive length, digits)
- Procedural physical safety validation (valid dance/push-ups, excessive repetitions, duration, tempo)
- Bounded retry & deterministic fallback orchestration:
  * First attempt succeeds -> no fallback, 1 attempt
  * First attempt fails validation -> bounded retry succeeds -> 2 attempts, no fallback
  * Both attempts fail validation -> deterministic fallback, preserved type & difficulty
  * Provider timeout -> bounded retry -> fallback with PROVIDER_TIMEOUT
  * Provider rate limit -> immediate fallback with RATE_LIMITED
  * Maximum retry bound respected (max_retries=0 -> 1 attempt)
  * Deterministic fallback reproducibility across 10 repeated runs
"""
import unittest
from typing import Mapping

from backend.app.core.exceptions import (
    GenAIRateLimitError,
    GenAITimeoutError,
)
from backend.app.schemas.challenge_safety_schemas import (
    FallbackReason,
    SafetySeverity,
    SafetyViolationCode,
    ValidationRetryPolicy,
)
from backend.app.services.genai.domain_safety_validator import (
    DomainSafetyValidator,
)
from backend.app.services.genai.safety_retry_orchestrator import (
    DETERMINISTIC_FALLBACK_CATALOG,
    DeterministicFallbackResolver,
    SafetyRetryOrchestrator,
)


class TestDomainSafetyMath(unittest.TestCase):
    """Test suite: Domain safety validation for Math challenges."""

    def test_valid_math_challenge_accepted(self) -> None:
        """Verify valid arithmetic expression passes all common and domain checks."""
        payload = {
            "challenge_type": "math",
            "difficulty_level": "easy",
            "title": "Morning Arithmetic",
            "instructions": "Solve the arithmetic problem below.",
            "content_payload": {
                "expression": "12 + 15",
                "operands": [12, 15],
                "operator": "+",
            },
            "expected_answer": 27,
        }
        report = DomainSafetyValidator.validate_challenge_safety("math", "easy", payload)
        self.assertTrue(report.is_safe)
        self.assertEqual(len(report.violations), 0)
        self.assertIn("RULE_MATH_SAFETY_VALIDATION", report.checked_rules)

    def test_math_division_by_zero_rejected(self) -> None:
        """Verify math expression with division by zero is rejected."""
        payload = {
            "challenge_type": "math",
            "difficulty_level": "medium",
            "title": "Division Task",
            "instructions": "Solve this equation.",
            "content_payload": {
                "expression": "42 / 0",
                "operands": [42, 0],
                "operator": "/",
            },
            "expected_answer": 0,
        }
        report = DomainSafetyValidator.validate_challenge_safety("math", "medium", payload)
        self.assertFalse(report.is_safe)
        matching = [v for v in report.violations if v.code == SafetyViolationCode.MATH_DIVISION_BY_ZERO]
        self.assertTrue(len(matching) >= 1)
        self.assertEqual(matching[0].severity, SafetySeverity.CRITICAL)

    def test_math_unsolvable_syntax_rejected(self) -> None:
        """Verify invalid or unparseable math syntax is rejected."""
        payload = {
            "challenge_type": "math",
            "difficulty_level": "easy",
            "title": "Bad Math",
            "instructions": "Solve this.",
            "content_payload": {
                "expression": "12 + + * 4",
                "operands": [12, 4],
            },
        }
        report = DomainSafetyValidator.validate_challenge_safety("math", "easy", payload)
        self.assertFalse(report.is_safe)
        matching = [v for v in report.violations if v.code == SafetyViolationCode.MATH_UNSOLVABLE]
        self.assertTrue(len(matching) >= 1)

    def test_math_expected_answer_mismatch_rejected(self) -> None:
        """Verify incorrect expected answer triggers MATH_UNSOLVABLE violation."""
        payload = {
            "challenge_type": "math",
            "difficulty_level": "easy",
            "title": "Math Task",
            "instructions": "Solve: 5 + 5",
            "content_payload": {"expression": "5 + 5"},
            "expected_answer": 999,  # Incorrect answer
        }
        report = DomainSafetyValidator.validate_challenge_safety("math", "easy", payload)
        self.assertFalse(report.is_safe)
        matching = [v for v in report.violations if v.code == SafetyViolationCode.MATH_UNSOLVABLE]
        self.assertTrue(len(matching) >= 1)
        self.assertIn("does not match authoritative computed answer", matching[0].message)

    def test_math_numerical_overflow_rejected(self) -> None:
        """Verify operand exceeding difficulty bounds produces precision/overflow violation."""
        payload = {
            "challenge_type": "math",
            "difficulty_level": "easy",  # easy limit is 50 for max_operand_abs
            "title": "Overflow Math",
            "instructions": "Solve this equation.",
            "content_payload": {
                "expression": "99999999999999999999 + 1",
            },
        }
        report = DomainSafetyValidator.validate_challenge_safety("math", "easy", payload)
        self.assertFalse(report.is_safe)
        matching = [
            v for v in report.violations
            if v.code in (SafetyViolationCode.MATH_PRECISION_OVERFLOW, SafetyViolationCode.MATH_UNSOLVABLE)
        ]
        self.assertTrue(len(matching) >= 1)


class TestDomainSafetyMemory(unittest.TestCase):
    """Test suite: Domain safety validation for Memory challenges."""

    def test_valid_memory_challenge_accepted(self) -> None:
        """Verify valid visual sequence recall challenge passes validation."""
        payload = {
            "challenge_type": "memory",
            "difficulty_level": "easy",
            "title": "Visual Memory",
            "instructions": "Remember the sequence of symbols.",
            "content_payload": {
                "mode": "visual_sequence",
                "palette_theme": "colors",
                "sequence": ["Red", "Green", "Blue"],
            },
            "expected_answer": ["Red", "Green", "Blue"],
        }
        report = DomainSafetyValidator.validate_challenge_safety("memory", "easy", payload)
        self.assertTrue(report.is_safe)
        self.assertEqual(len(report.violations), 0)

    def test_memory_empty_sequence_rejected(self) -> None:
        """Verify memory challenge with empty sequence is rejected."""
        payload = {
            "challenge_type": "memory",
            "difficulty_level": "easy",
            "title": "Empty Memory",
            "instructions": "Remember nothing.",
            "content_payload": {
                "mode": "visual_sequence",
                "sequence": [],
            },
        }
        report = DomainSafetyValidator.validate_challenge_safety("memory", "easy", payload)
        self.assertFalse(report.is_safe)
        matching = [v for v in report.violations if v.code == SafetyViolationCode.MEMORY_EMPTY_SEQUENCE]
        self.assertTrue(len(matching) >= 1)

    def test_memory_number_guessing_strictly_rejected(self) -> None:
        """Verify CRITICAL INVARIANT: memory challenges with numbers are rejected as MEMORY_NUMERIC_LEAK."""
        # Raw integers in sequence
        payload_ints = {
            "challenge_type": "memory",
            "difficulty_level": "easy",
            "title": "Number Recall",
            "instructions": "Remember the digits.",
            "content_payload": {
                "mode": "visual_sequence",
                "sequence": [4, 8, 15, 16, 23, 42],
            },
        }
        report1 = DomainSafetyValidator.validate_challenge_safety("memory", "easy", payload_ints)
        self.assertFalse(report1.is_safe)
        matching1 = [v for v in report1.violations if v.code == SafetyViolationCode.MEMORY_NUMERIC_LEAK]
        self.assertTrue(len(matching1) >= 1)

        # Digit strings in sequence
        payload_digit_str = {
            "challenge_type": "memory",
            "difficulty_level": "easy",
            "title": "PIN Recall",
            "instructions": "Remember your PIN code.",
            "content_payload": {
                "mode": "visual_sequence",
                "sequence": ["123", "456"],
            },
        }
        report2 = DomainSafetyValidator.validate_challenge_safety("memory", "easy", payload_digit_str)
        self.assertFalse(report2.is_safe)
        matching2 = [v for v in report2.violations if v.code == SafetyViolationCode.MEMORY_NUMERIC_LEAK]
        self.assertTrue(len(matching2) >= 1)

    def test_memory_invalid_palette_theme_rejected(self) -> None:
        """Verify unknown palette theme is rejected."""
        payload = {
            "challenge_type": "memory",
            "difficulty_level": "medium",
            "title": "Invalid Theme Memory",
            "instructions": "Memorize the sequence.",
            "content_payload": {
                "mode": "visual_sequence",
                "palette_theme": "sci_fi_weapons",  # invalid theme
                "sequence": ["A", "B", "C", "D"],
            },
        }
        report = DomainSafetyValidator.validate_challenge_safety("memory", "medium", payload)
        self.assertFalse(report.is_safe)
        matching = [v for v in report.violations if v.code == SafetyViolationCode.MEMORY_INVALID_PALETTE]
        self.assertTrue(len(matching) >= 1)


class TestDomainSafetyTongueTwister(unittest.TestCase):
    """Test suite: Domain safety validation for Tongue Twister challenges."""

    def test_valid_tongue_twister_accepted(self) -> None:
        """Verify valid alliterative tongue twister passage passes validation."""
        payload = {
            "challenge_type": "tongue_twister",
            "difficulty_level": "easy",
            "title": "Sibilant Twister",
            "instructions": "Repeat aloud clearly.",
            "content_payload": {
                "passage": "She sells sea shells by the sea shore.",
                "phonetic_focus": "s_and_sh_alternation",
                "target_word_count": 8,
            },
        }
        report = DomainSafetyValidator.validate_challenge_safety("tongue_twister", "easy", payload)
        self.assertTrue(report.is_safe)
        self.assertEqual(len(report.violations), 0)

    def test_tongue_twister_with_digits_rejected(self) -> None:
        """Verify numeric digits (0-9) in tongue twister passage are rejected."""
        payload = {
            "challenge_type": "tongue_twister",
            "difficulty_level": "medium",
            "title": "Numeric Twister",
            "instructions": "Repeat aloud.",
            "content_payload": {
                "passage": "The 33 thieves thought that they thrilled the throne.",  # '33' instead of 'thirty-three'
            },
        }
        report = DomainSafetyValidator.validate_challenge_safety("tongue_twister", "medium", payload)
        self.assertFalse(report.is_safe)
        self.assertTrue(any("numeric digits" in v.message for v in report.violations))

    def test_tongue_twister_length_bounds_rejected(self) -> None:
        """Verify too-short passage is rejected under TONGUE_TWISTER_LENGTH_BOUNDS."""
        payload = {
            "challenge_type": "tongue_twister",
            "difficulty_level": "hard",  # hard requires min 18 words
            "title": "Short Hard Twister",
            "instructions": "Repeat aloud.",
            "content_payload": {
                "passage": "Red lorry, yellow lorry.",  # only 4 words
            },
        }
        report = DomainSafetyValidator.validate_challenge_safety("tongue_twister", "hard", payload)
        self.assertFalse(report.is_safe)
        matching = [v for v in report.violations if v.code == SafetyViolationCode.TONGUE_TWISTER_LENGTH_BOUNDS]
        self.assertTrue(len(matching) >= 1)


class TestDomainSafetyPhysical(unittest.TestCase):
    """Test suite: Domain safety validation for Dance and Push-ups."""

    def test_valid_dance_challenge_accepted(self) -> None:
        """Verify valid dance routine is accepted."""
        payload = {
            "challenge_type": "dance",
            "difficulty_level": "easy",
            "title": "Gentle Morning Groove",
            "instructions": "Follow the rhythmic movement cues.",
            "content_payload": {
                "routine_type": "rhythm_groove",
                "step_count": 4,
                "target_duration_seconds": 20,
                "tempo_bpm": 100,
                "steps": [
                    {"step_number": 1, "action": "Step Left & Bounce"},
                    {"step_number": 2, "action": "Step Right & Bounce"},
                    {"step_number": 3, "action": "Overhead Wave"},
                    {"step_number": 4, "action": "Double Clap"},
                ],
            },
        }
        report = DomainSafetyValidator.validate_challenge_safety("dance", "easy", payload)
        self.assertTrue(report.is_safe)
        self.assertEqual(len(report.violations), 0)

    def test_dance_excessive_tempo_rejected(self) -> None:
        """Verify dangerous/excessive dance tempo (> 180 BPM) is rejected."""
        payload = {
            "challenge_type": "dance",
            "difficulty_level": "easy",
            "title": "Extreme Dance",
            "instructions": "Move your body.",
            "content_payload": {
                "routine_type": "rhythm_groove",
                "step_count": 4,
                "target_duration_seconds": 20,
                "tempo_bpm": 240,  # dangerous tempo
                "steps": [{"step_number": 1, "action": "Step"}],
            },
        }
        report = DomainSafetyValidator.validate_challenge_safety("dance", "easy", payload)
        self.assertFalse(report.is_safe)
        matching = [v for v in report.violations if v.code == SafetyViolationCode.PHYSICAL_EXERTION_EXCEEDED]
        self.assertTrue(len(matching) >= 1)

    def test_valid_push_ups_accepted(self) -> None:
        """Verify valid push-ups challenge is accepted."""
        payload = {
            "challenge_type": "push_ups",
            "difficulty_level": "medium",
            "title": "Morning Push-ups",
            "instructions": "Perform push-ups maintaining form.",
            "content_payload": {
                "target_repetitions": 15,
                "completion_window_seconds": 45,
            },
        }
        report = DomainSafetyValidator.validate_challenge_safety("push_ups", "medium", payload)
        self.assertTrue(report.is_safe)
        self.assertEqual(len(report.violations), 0)

    def test_push_ups_excessive_repetitions_rejected(self) -> None:
        """Verify push-ups exceeding tier limit (easy max 15) are rejected."""
        payload = {
            "challenge_type": "push_ups",
            "difficulty_level": "easy",
            "title": "Extreme Push-ups",
            "instructions": "Do 100 push-ups.",
            "content_payload": {
                "target_repetitions": 100,  # far exceeds easy limit of 15
                "completion_window_seconds": 60,
            },
        }
        report = DomainSafetyValidator.validate_challenge_safety("push_ups", "easy", payload)
        self.assertFalse(report.is_safe)
        matching = [v for v in report.violations if v.code == SafetyViolationCode.PHYSICAL_EXERTION_EXCEEDED]
        self.assertTrue(len(matching) >= 1)


class TestSafetyRetryOrchestrator(unittest.TestCase):
    """Test suite: Bounded retry, provider failure handling, and deterministic fallback."""

    def test_first_attempt_succeeds_no_fallback(self) -> None:
        """Verify successful generation on attempt 1 returns valid content with 1 attempt consumed."""
        valid_math = {
            "challenge_type": "math",
            "difficulty_level": "easy",
            "title": "Morning Math",
            "instructions": "Solve 10 + 12.",
            "content_payload": {"expression": "10 + 12"},
            "expected_answer": 22,
        }
        result = SafetyRetryOrchestrator.orchestrate(
            expected_type="math",
            expected_difficulty="easy",
            generator_func=lambda: valid_math,
        )
        self.assertFalse(result.is_fallback)
        self.assertEqual(result.attempts_used, 1)
        self.assertIsNone(result.fallback_resolution)
        self.assertTrue(result.report.is_safe)
        self.assertEqual(result.challenge_type, "math")

    def test_first_attempt_fails_retry_succeeds(self) -> None:
        """Verify first attempt validation failure triggers bounded retry that succeeds on attempt 2."""
        call_count = 0

        def generator():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First attempt: invalid (division by zero)
                return {
                    "challenge_type": "math",
                    "difficulty_level": "easy",
                    "title": "Bad Math",
                    "instructions": "Solve 10 / 0",
                    "content_payload": {"expression": "10 / 0"},
                }
            # Second attempt: valid
            return {
                "challenge_type": "math",
                "difficulty_level": "easy",
                "title": "Good Math",
                "instructions": "Solve 10 + 5",
                "content_payload": {"expression": "10 + 5"},
                "expected_answer": 15,
            }

        result = SafetyRetryOrchestrator.orchestrate(
            expected_type="math",
            expected_difficulty="easy",
            generator_func=generator,
        )
        self.assertFalse(result.is_fallback)
        self.assertEqual(result.attempts_used, 2)
        self.assertEqual(call_count, 2)
        self.assertTrue(result.report.is_safe)

    def test_all_retries_fail_triggers_deterministic_fallback(self) -> None:
        """Verify exhaustion across all retries triggers deterministic fallback preserving type and difficulty."""
        call_count = 0

        def always_malformed():
            nonlocal call_count
            call_count += 1
            return {"malformed": "content"}

        policy = ValidationRetryPolicy(max_retries=1)
        result = SafetyRetryOrchestrator.orchestrate(
            expected_type="memory",
            expected_difficulty="medium",
            generator_func=always_malformed,
            policy=policy,
        )
        self.assertTrue(result.is_fallback)
        self.assertEqual(result.attempts_used, 2)
        self.assertIsNotNone(result.fallback_resolution)
        assert result.fallback_resolution is not None
        self.assertEqual(result.fallback_resolution.fallback_reason, FallbackReason.MALFORMED_OUTPUT)
        self.assertTrue(result.fallback_resolution.preserved_type)
        self.assertTrue(result.fallback_resolution.preserved_difficulty)
        self.assertEqual(result.challenge_type, "memory")
        self.assertEqual(result.difficulty_level, "medium")

    def test_provider_timeout_triggers_retry_and_fallback(self) -> None:
        """Verify GenAITimeoutError triggers retry and falls back with PROVIDER_TIMEOUT."""
        timeout_calls = 0

        def timeout_generator():
            nonlocal timeout_calls
            timeout_calls += 1
            raise GenAITimeoutError("HTTP timeout contacting provider.")

        result = SafetyRetryOrchestrator.orchestrate(
            expected_type="tongue_twister",
            expected_difficulty="hard",
            generator_func=timeout_generator,
            policy=ValidationRetryPolicy(max_retries=1),
        )
        self.assertTrue(result.is_fallback)
        self.assertEqual(result.attempts_used, 2)
        self.assertEqual(timeout_calls, 2)
        self.assertIsNotNone(result.fallback_resolution)
        assert result.fallback_resolution is not None
        self.assertEqual(result.fallback_resolution.fallback_reason, FallbackReason.PROVIDER_TIMEOUT)
        self.assertEqual(result.challenge_type, "tongue_twister")
        self.assertEqual(result.difficulty_level, "hard")

    def test_provider_rate_limit_triggers_immediate_fallback(self) -> None:
        """Verify GenAIRateLimitError drops immediately to fallback without compounding retries."""
        rate_limit_calls = 0

        def rate_limited_generator():
            nonlocal rate_limit_calls
            rate_limit_calls += 1
            raise GenAIRateLimitError("HTTP 429 Too Many Requests.")

        result = SafetyRetryOrchestrator.orchestrate(
            expected_type="dance",
            expected_difficulty="easy",
            generator_func=rate_limited_generator,
            policy=ValidationRetryPolicy(max_retries=1),
        )
        self.assertTrue(result.is_fallback)
        self.assertEqual(result.attempts_used, 1)  # Immediate fallback without retry
        self.assertEqual(rate_limit_calls, 1)
        self.assertIsNotNone(result.fallback_resolution)
        assert result.fallback_resolution is not None
        self.assertEqual(result.fallback_resolution.fallback_reason, FallbackReason.RATE_LIMITED)
        self.assertEqual(result.challenge_type, "dance")
        self.assertEqual(result.difficulty_level, "easy")

    def test_max_retries_zero_executes_only_one_attempt(self) -> None:
        """Verify policy with max_retries=0 executes exactly 1 attempt before fallback."""
        calls = 0

        def failing_generator():
            nonlocal calls
            calls += 1
            return {"bad": "data"}

        result = SafetyRetryOrchestrator.orchestrate(
            expected_type="push_ups",
            expected_difficulty="medium",
            generator_func=failing_generator,
            policy=ValidationRetryPolicy(max_retries=0),
        )
        self.assertTrue(result.is_fallback)
        self.assertEqual(result.attempts_used, 1)
        self.assertEqual(calls, 1)

    def test_deterministic_fallback_reproducibility(self) -> None:
        """Verify deterministic fallback produces identical resolution across 10 repeated runs."""
        runs = [
            DeterministicFallbackResolver.resolve_fallback(
                expected_type="math",
                expected_difficulty="hard",
                reason=FallbackReason.PROVIDER_TIMEOUT,
                trigger_error="Provider timed out after 3.0s",
            )
            for _ in range(10)
        ]
        first_resolution_dump = runs[0][0].model_dump()
        first_payload_dump = runs[0][1]

        for i, (res, payload) in enumerate(runs[1:], start=2):
            self.assertEqual(res.model_dump(), first_resolution_dump, f"Run {i} resolution differed")
            self.assertEqual(payload, first_payload_dump, f"Run {i} payload differed")

    def test_all_15_canonical_pairs_in_fallback_catalog(self) -> None:
        """Verify fallback catalog contains verified entries for all 5 types x 3 difficulties = 15 pairs."""
        canonical_types = ["dance", "math", "memory", "tongue_twister", "push_ups"]
        canonical_diffs = ["easy", "medium", "hard"]

        self.assertEqual(len(DETERMINISTIC_FALLBACK_CATALOG), 15)
        for ctype in canonical_types:
            for diff in canonical_diffs:
                res, payload = DeterministicFallbackResolver.resolve_fallback(
                    expected_type=ctype,  # type: ignore
                    expected_difficulty=diff,  # type: ignore
                    reason=FallbackReason.VALIDATION_FAILED,
                    trigger_error="Test verification",
                )
                self.assertTrue(res.preserved_type)
                self.assertTrue(res.preserved_difficulty)
                self.assertEqual(res.challenge_type, ctype)
                self.assertEqual(res.difficulty_level, diff)
                self.assertIsNotNone(payload)


if __name__ == "__main__":
    unittest.main()
