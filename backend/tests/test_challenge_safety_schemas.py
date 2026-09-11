"""Unit tests for Phase 4.6.1 GenAI Safety & Validation Contracts.

Validates the foundational typed contracts for the Phase 4.6 GenAI safety boundary:
- SafetyViolationCode, SafetySeverity, FallbackReason, FallbackSource enums.
- SafetyViolation and bounded SafetyViolationDetails.
- SafetyValidationReport and absence of silent sanitization / arbitrary content.
- FallbackResolution and immutable preservation of canonical type and difficulty.
- ValidationRetryPolicy bounding (max_retries <= 2, positive budgets, fallback_on_exhaustion=True).
- Privacy guarantees (zero PII, zero DB IDs, rejection of extra fields).
- Serialization and JSON schema generation.
"""
import json
import unittest
from typing import Any, Dict

from pydantic import ValidationError

from backend.app.schemas.challenge_safety_schemas import (
    FallbackPayloadContract,
    FallbackReason,
    FallbackResolution,
    FallbackSource,
    SafetySeverity,
    SafetyValidationReport,
    SafetyViolation,
    SafetyViolationCode,
    SafetyViolationDetails,
    ValidationRetryPolicy,
)


class TestSafetyEnums(unittest.TestCase):
    """Test suite A: Verify all required enums, members, and serialization."""

    def test_safety_violation_codes_completeness(self) -> None:
        """Verify all 16 required SafetyViolationCode values are defined."""
        expected_codes = {
            # Framework & Structural
            "schema_malformed": SafetyViolationCode.SCHEMA_MALFORMED,
            "type_mutation": SafetyViolationCode.TYPE_MUTATION,
            "difficulty_mutation": SafetyViolationCode.DIFFICULTY_MUTATION,
            "prompt_injection": SafetyViolationCode.PROMPT_INJECTION,
            "harmful_content": SafetyViolationCode.HARMFUL_CONTENT,
            # Math Safety
            "math_unsolvable": SafetyViolationCode.MATH_UNSOLVABLE,
            "math_division_by_zero": SafetyViolationCode.MATH_DIVISION_BY_ZERO,
            "math_precision_overflow": SafetyViolationCode.MATH_PRECISION_OVERFLOW,
            # Memory Safety (Strict Non-Numeric)
            "memory_numeric_leak": SafetyViolationCode.MEMORY_NUMERIC_LEAK,
            "memory_empty_sequence": SafetyViolationCode.MEMORY_EMPTY_SEQUENCE,
            "memory_invalid_palette": SafetyViolationCode.MEMORY_INVALID_PALETTE,
            # Tongue Twister Safety
            "tongue_twister_length_bounds": SafetyViolationCode.TONGUE_TWISTER_LENGTH_BOUNDS,
            "tongue_twister_low_alliteration": SafetyViolationCode.TONGUE_TWISTER_LOW_ALLITERATION,
            # Physical Exertion Safety
            "physical_exertion_exceeded": SafetyViolationCode.PHYSICAL_EXERTION_EXCEEDED,
            # Operational & Boundary
            "latency_budget_exceeded": SafetyViolationCode.LATENCY_BUDGET_EXCEEDED,
            "provider_error": SafetyViolationCode.PROVIDER_ERROR,
        }
        self.assertEqual(len(SafetyViolationCode), 16)
        for raw_value, enum_member in expected_codes.items():
            self.assertEqual(enum_member.value, raw_value)
            self.assertEqual(SafetyViolationCode(raw_value), enum_member)

    def test_safety_severity_values(self) -> None:
        """Verify SafetySeverity enum contains exactly 'critical' and 'warning'."""
        self.assertEqual(len(SafetySeverity), 2)
        self.assertEqual(SafetySeverity.CRITICAL.value, "critical")
        self.assertEqual(SafetySeverity.WARNING.value, "warning")
        self.assertEqual(SafetySeverity("critical"), SafetySeverity.CRITICAL)
        self.assertEqual(SafetySeverity("warning"), SafetySeverity.WARNING)

    def test_fallback_reason_values(self) -> None:
        """Verify all 7 FallbackReason values are defined."""
        expected_reasons = {
            "validation_failed": FallbackReason.VALIDATION_FAILED,
            "provider_timeout": FallbackReason.PROVIDER_TIMEOUT,
            "provider_unavailable": FallbackReason.PROVIDER_UNAVAILABLE,
            "rate_limited": FallbackReason.RATE_LIMITED,
            "latency_exceeded": FallbackReason.LATENCY_EXCEEDED,
            "safety_violation": FallbackReason.SAFETY_VIOLATION,
            "malformed_output": FallbackReason.MALFORMED_OUTPUT,
        }
        self.assertEqual(len(FallbackReason), 7)
        for raw_value, enum_member in expected_reasons.items():
            self.assertEqual(enum_member.value, raw_value)
            self.assertEqual(FallbackReason(raw_value), enum_member)

    def test_fallback_source_values(self) -> None:
        """Verify FallbackSource enum contains exactly 'procedural_catalog' and 'algorithmic_fallback'."""
        self.assertEqual(len(FallbackSource), 2)
        self.assertEqual(FallbackSource.PROCEDURAL_CATALOG.value, "procedural_catalog")
        self.assertEqual(FallbackSource.ALGORITHMIC_FALLBACK.value, "algorithmic_fallback")


class TestSafetyViolationAndDetails(unittest.TestCase):
    """Test suite B: Verify SafetyViolation and SafetyViolationDetails behavior."""

    def test_valid_critical_violation(self) -> None:
        """Verify constructing a valid critical violation with minimal fields."""
        v = SafetyViolation(
            code=SafetyViolationCode.MEMORY_NUMERIC_LEAK,
            message="Numeric tokens detected in memory recall challenge.",
            field="content_payload.items",
            severity=SafetySeverity.CRITICAL,
        )
        self.assertEqual(v.code, SafetyViolationCode.MEMORY_NUMERIC_LEAK)
        self.assertEqual(v.severity, SafetySeverity.CRITICAL)
        self.assertEqual(v.field, "content_payload.items")
        self.assertIsNone(v.details)

    def test_valid_warning_violation_with_details(self) -> None:
        """Verify constructing a valid warning violation with typed diagnostic details."""
        details = SafetyViolationDetails(
            rule_id="RULE_TT_ALLITERATION_DENSITY",
            observed_value="0.32",
            expected_bound=">= 0.40",
            numeric_measurement=0.32,
            diagnostic_note="Sub-optimal alliterative density in tongue twister.",
        )
        v = SafetyViolation(
            code=SafetyViolationCode.TONGUE_TWISTER_LOW_ALLITERATION,
            message="Phonetic alliteration density below desired target.",
            field="content_payload.passage",
            severity=SafetySeverity.WARNING,
            details=details,
        )
        self.assertEqual(v.severity, SafetySeverity.WARNING)
        self.assertIsNotNone(v.details)
        assert v.details is not None
        self.assertEqual(v.details.rule_id, "RULE_TT_ALLITERATION_DENSITY")
        self.assertEqual(v.details.numeric_measurement, 0.32)

    def test_invalid_severity_rejected(self) -> None:
        """Verify invalid severity strings are rejected."""
        with self.assertRaises(ValidationError):
            SafetyViolation(
                code=SafetyViolationCode.SCHEMA_MALFORMED,
                message="Malformed schema payload.",
                severity="fatal",  # type: ignore
            )

    def test_invalid_violation_code_rejected(self) -> None:
        """Verify invalid violation codes are rejected."""
        with self.assertRaises(ValidationError):
            SafetyViolation(
                code="UNKNOWN_ERROR",  # type: ignore
                message="Unknown error.",
                severity=SafetySeverity.CRITICAL,
            )

    def test_message_length_bounds(self) -> None:
        """Verify message length constraints (< 3 chars or > 300 chars)."""
        with self.assertRaises(ValidationError):
            SafetyViolation(
                code=SafetyViolationCode.MATH_UNSOLVABLE,
                message="ab",  # too short
                severity=SafetySeverity.CRITICAL,
            )
        with self.assertRaises(ValidationError):
            SafetyViolation(
                code=SafetyViolationCode.MATH_UNSOLVABLE,
                message="a" * 301,  # too long
                severity=SafetySeverity.CRITICAL,
            )

    def test_message_control_characters_rejected(self) -> None:
        """Verify messages cannot contain control characters or newlines."""
        with self.assertRaises(ValidationError):
            SafetyViolation(
                code=SafetyViolationCode.PROMPT_INJECTION,
                message="Detected injection:\nIgnore previous instructions.",
                severity=SafetySeverity.CRITICAL,
            )

    def test_message_forbidden_pii_keys_rejected(self) -> None:
        """Verify violation message cannot leak PII keys."""
        with self.assertRaises(ValidationError):
            SafetyViolation(
                code=SafetyViolationCode.SCHEMA_MALFORMED,
                message="Found user_id inside payload.",
                severity=SafetySeverity.CRITICAL,
            )

    def test_details_rejects_extra_fields(self) -> None:
        """Verify SafetyViolationDetails forbids arbitrary or unexpected fields."""
        with self.assertRaises(ValidationError):
            SafetyViolationDetails(
                rule_id="RULE_01",
                extra_untrusted_data="injection",  # type: ignore
            )

    def test_details_rejects_pii_in_diagnostic_text(self) -> None:
        """Verify SafetyViolationDetails rejects forbidden sensitive keys."""
        with self.assertRaises(ValidationError):
            SafetyViolationDetails(
                rule_id="RULE_01",
                diagnostic_note="Attempted lookup for email address.",
            )


class TestSafetyValidationReport(unittest.TestCase):
    """Test suite C: Verify SafetyValidationReport behavior."""

    def test_valid_safe_report_no_violations(self) -> None:
        """Verify constructing a valid safe report with no violations."""
        report = SafetyValidationReport(
            is_safe=True,
            challenge_type="math",
            difficulty_level="medium",
            violations=[],
            checked_rules=["RULE_MATH_SYNTAX", "RULE_NO_DIV_ZERO", "RULE_INJECTION_CHECK"],
        )
        self.assertTrue(report.is_safe)
        self.assertEqual(report.challenge_type, "math")
        self.assertEqual(report.difficulty_level, "medium")
        self.assertEqual(len(report.violations), 0)
        self.assertEqual(len(report.checked_rules), 3)

    def test_valid_unsafe_report_with_violations(self) -> None:
        """Verify constructing an unsafe report containing critical violations."""
        v = SafetyViolation(
            code=SafetyViolationCode.MATH_DIVISION_BY_ZERO,
            message="Math expression contains division by zero.",
            field="content_payload.expression",
            severity=SafetySeverity.CRITICAL,
        )
        report = SafetyValidationReport(
            is_safe=False,
            challenge_type="math",
            difficulty_level="hard",
            violations=[v],
            checked_rules=["RULE_MATH_SYNTAX", "RULE_NO_DIV_ZERO"],
        )
        self.assertFalse(report.is_safe)
        self.assertEqual(len(report.violations), 1)
        self.assertEqual(report.violations[0].code, SafetyViolationCode.MATH_DIVISION_BY_ZERO)

    def test_invalid_canonical_type_rejected(self) -> None:
        """Verify non-canonical challenge types (e.g. number_guessing) are rejected."""
        with self.assertRaises(ValidationError):
            SafetyValidationReport(
                is_safe=False,
                challenge_type="number_guessing",  # type: ignore
                difficulty_level="easy",
            )

    def test_invalid_difficulty_level_rejected(self) -> None:
        """Verify non-concrete difficulties (e.g. adaptive, extreme) are rejected."""
        with self.assertRaises(ValidationError):
            SafetyValidationReport(
                is_safe=True,
                challenge_type="tongue_twister",
                difficulty_level="adaptive",  # type: ignore
            )
        with self.assertRaises(ValidationError):
            SafetyValidationReport(
                is_safe=True,
                challenge_type="tongue_twister",
                difficulty_level="extreme",  # type: ignore
            )

    def test_no_sanitized_content_field(self) -> None:
        """Verify SafetyValidationReport does NOT have a sanitized_content field (no silent sanitization)."""
        self.assertNotIn("sanitized_content", SafetyValidationReport.model_fields)

    def test_rejects_extra_fields_in_report(self) -> None:
        """Verify extra or untrusted content fields are rejected."""
        with self.assertRaises(ValidationError):
            SafetyValidationReport(
                is_safe=True,
                challenge_type="dance",
                difficulty_level="easy",
                sanitized_content={"moves": []},  # type: ignore
            )

    def test_checked_rules_validation_and_bounds(self) -> None:
        """Verify checked_rules constraints (max 50, no empty strings, no control chars)."""
        # Empty string rejected
        with self.assertRaises(ValidationError):
            SafetyValidationReport(
                is_safe=True,
                challenge_type="memory",
                difficulty_level="easy",
                checked_rules=["   "],
            )
        # Exceeds max 50 items
        with self.assertRaises(ValidationError):
            SafetyValidationReport(
                is_safe=True,
                challenge_type="memory",
                difficulty_level="easy",
                checked_rules=[f"RULE_{i}" for i in range(51)],
            )


class TestFallbackResolution(unittest.TestCase):
    """Test suite D: Verify FallbackResolution and FallbackPayloadContract behavior."""

    def test_valid_fallback_resolution(self) -> None:
        """Verify constructing a valid FallbackResolution record."""
        payload = FallbackPayloadContract(
            fallback_identifier="catalog_math_easy_001",
            instructions_hint="Solve the arithmetic expression.",
            parameters_tag="arithmetic_basic",
        )
        res = FallbackResolution(
            challenge_type="math",
            difficulty_level="easy",
            fallback_reason=FallbackReason.VALIDATION_FAILED,
            fallback_source=FallbackSource.PROCEDURAL_CATALOG,
            trigger_error="Expression failed validation check: division by zero.",
            fallback_payload=payload,
        )
        self.assertEqual(res.challenge_type, "math")
        self.assertEqual(res.difficulty_level, "easy")
        self.assertEqual(res.fallback_reason, FallbackReason.VALIDATION_FAILED)
        self.assertEqual(res.fallback_source, FallbackSource.PROCEDURAL_CATALOG)
        self.assertTrue(res.preserved_type)
        self.assertTrue(res.preserved_difficulty)
        self.assertEqual(res.fallback_payload.fallback_identifier, "catalog_math_easy_001")

    def test_preserved_type_cannot_be_false(self) -> None:
        """Verify preserved_type cannot be set to False."""
        payload = FallbackPayloadContract(fallback_identifier="catalog_001")
        with self.assertRaises(ValidationError):
            FallbackResolution(
                challenge_type="push_ups",
                difficulty_level="medium",
                fallback_reason=FallbackReason.PROVIDER_TIMEOUT,
                fallback_source=FallbackSource.PROCEDURAL_CATALOG,
                trigger_error="Provider timed out.",
                preserved_type=False,  # type: ignore
                fallback_payload=payload,
            )

    def test_preserved_difficulty_cannot_be_false(self) -> None:
        """Verify preserved_difficulty cannot be set to False."""
        payload = FallbackPayloadContract(fallback_identifier="catalog_001")
        with self.assertRaises(ValidationError):
            FallbackResolution(
                challenge_type="push_ups",
                difficulty_level="medium",
                fallback_reason=FallbackReason.PROVIDER_TIMEOUT,
                fallback_source=FallbackSource.PROCEDURAL_CATALOG,
                trigger_error="Provider timed out.",
                preserved_difficulty=False,  # type: ignore
                fallback_payload=payload,
            )

    def test_invalid_challenge_type_in_fallback_rejected(self) -> None:
        """Verify invalid challenge types are rejected in fallback resolution."""
        payload = FallbackPayloadContract(fallback_identifier="catalog_001")
        with self.assertRaises(ValidationError):
            FallbackResolution(
                challenge_type="sudoku",  # type: ignore
                difficulty_level="easy",
                fallback_reason=FallbackReason.MALFORMED_OUTPUT,
                fallback_source=FallbackSource.PROCEDURAL_CATALOG,
                trigger_error="Malformed JSON response.",
                fallback_payload=payload,
            )

    def test_invalid_difficulty_in_fallback_rejected(self) -> None:
        """Verify invalid difficulty tiers are rejected in fallback resolution."""
        payload = FallbackPayloadContract(fallback_identifier="catalog_001")
        with self.assertRaises(ValidationError):
            FallbackResolution(
                challenge_type="memory",
                difficulty_level="adaptive",  # type: ignore
                fallback_reason=FallbackReason.RATE_LIMITED,
                fallback_source=FallbackSource.PROCEDURAL_CATALOG,
                trigger_error="HTTP 429 Rate limited.",
                fallback_payload=payload,
            )

    def test_invalid_fallback_reason_rejected(self) -> None:
        """Verify invalid fallback reason values are rejected."""
        payload = FallbackPayloadContract(fallback_identifier="catalog_001")
        with self.assertRaises(ValidationError):
            FallbackResolution(
                challenge_type="tongue_twister",
                difficulty_level="hard",
                fallback_reason="RANDOM_ERROR",  # type: ignore
                fallback_source=FallbackSource.PROCEDURAL_CATALOG,
                trigger_error="Random error.",
                fallback_payload=payload,
            )

    def test_invalid_fallback_source_rejected(self) -> None:
        """Verify invalid fallback source values are rejected."""
        payload = FallbackPayloadContract(fallback_identifier="catalog_001")
        with self.assertRaises(ValidationError):
            FallbackResolution(
                challenge_type="tongue_twister",
                difficulty_level="hard",
                fallback_reason=FallbackReason.PROVIDER_UNAVAILABLE,
                fallback_source="external_service",  # type: ignore
                trigger_error="Provider 503.",
                fallback_payload=payload,
            )

    def test_trigger_error_bounds_and_pii(self) -> None:
        """Verify trigger_error bounds and rejection of sensitive PII keys."""
        payload = FallbackPayloadContract(fallback_identifier="catalog_001")
        # Empty trigger error rejected
        with self.assertRaises(ValidationError):
            FallbackResolution(
                challenge_type="math",
                difficulty_level="easy",
                fallback_reason=FallbackReason.PROVIDER_TIMEOUT,
                fallback_source=FallbackSource.PROCEDURAL_CATALOG,
                trigger_error="   ",
                fallback_payload=payload,
            )
        # PII key in trigger error rejected
        with self.assertRaises(ValidationError):
            FallbackResolution(
                challenge_type="math",
                difficulty_level="easy",
                fallback_reason=FallbackReason.PROVIDER_TIMEOUT,
                fallback_source=FallbackSource.PROCEDURAL_CATALOG,
                trigger_error="Failed for user_id=123",
                fallback_payload=payload,
            )

    def test_fallback_payload_contract_rejects_extra_fields(self) -> None:
        """Verify FallbackPayloadContract forbids generic dictionaries or extra fields."""
        with self.assertRaises(ValidationError):
            FallbackPayloadContract(
                fallback_identifier="catalog_001",
                raw_payload={"arbitrary": "data"},  # type: ignore
            )


class TestValidationRetryPolicy(unittest.TestCase):
    """Test suite E: Verify ValidationRetryPolicy bounding and invariants."""

    def test_default_policy(self) -> None:
        """Verify default retry policy configuration."""
        policy = ValidationRetryPolicy()
        self.assertEqual(policy.max_retries, 1)
        self.assertEqual(policy.timeout_per_attempt_seconds, 3.0)
        self.assertEqual(policy.total_latency_budget_seconds, 6.0)
        self.assertTrue(policy.fallback_on_exhaustion)

    def test_custom_valid_policy_boundary_values(self) -> None:
        """Verify boundary values: max_retries = 0 and max_retries = 2."""
        policy_zero = ValidationRetryPolicy(
            max_retries=0,
            timeout_per_attempt_seconds=4.0,
            total_latency_budget_seconds=4.0,
        )
        self.assertEqual(policy_zero.max_retries, 0)

        policy_two = ValidationRetryPolicy(
            max_retries=2,
            timeout_per_attempt_seconds=2.5,
            total_latency_budget_seconds=8.0,
        )
        self.assertEqual(policy_two.max_retries, 2)

    def test_max_retries_exceeding_two_rejected(self) -> None:
        """Verify max_retries > 2 is strictly rejected (alarm latency guarantee)."""
        with self.assertRaises(ValidationError):
            ValidationRetryPolicy(max_retries=3)

    def test_negative_max_retries_rejected(self) -> None:
        """Verify negative max_retries is rejected."""
        with self.assertRaises(ValidationError):
            ValidationRetryPolicy(max_retries=-1)

    def test_timeout_zero_or_negative_rejected(self) -> None:
        """Verify zero or negative attempt timeouts are rejected."""
        with self.assertRaises(ValidationError):
            ValidationRetryPolicy(timeout_per_attempt_seconds=0.0)
        with self.assertRaises(ValidationError):
            ValidationRetryPolicy(timeout_per_attempt_seconds=-1.0)

    def test_total_budget_zero_or_negative_rejected(self) -> None:
        """Verify zero or negative total latency budgets are rejected."""
        with self.assertRaises(ValidationError):
            ValidationRetryPolicy(total_latency_budget_seconds=0.0)
        with self.assertRaises(ValidationError):
            ValidationRetryPolicy(total_latency_budget_seconds=-5.0)

    def test_budget_smaller_than_attempt_timeout_rejected(self) -> None:
        """Verify total latency budget cannot be smaller than one attempt timeout."""
        with self.assertRaises(ValidationError):
            ValidationRetryPolicy(
                timeout_per_attempt_seconds=5.0,
                total_latency_budget_seconds=4.0,
            )

    def test_fallback_on_exhaustion_cannot_be_false(self) -> None:
        """Verify fallback_on_exhaustion cannot be set to False."""
        with self.assertRaises(ValidationError):
            ValidationRetryPolicy(fallback_on_exhaustion=False)  # type: ignore


class TestPrivacyAndSerialization(unittest.TestCase):
    """Test suite F & G: Verify privacy enforcement and serialization."""

    def test_models_reject_database_ids_and_pii(self) -> None:
        """Verify that identity fields (user_id, email, alarm_id) are rejected across all models."""
        # SafetyViolation
        with self.assertRaises(ValidationError):
            SafetyViolation(
                code=SafetyViolationCode.HARMFUL_CONTENT,
                message="Harmful content detected.",
                severity=SafetySeverity.CRITICAL,
                user_id=123,  # type: ignore
            )
        # SafetyValidationReport
        with self.assertRaises(ValidationError):
            SafetyValidationReport(
                is_safe=False,
                challenge_type="math",
                difficulty_level="easy",
                alarm_id=456,  # type: ignore
            )
        # FallbackResolution
        with self.assertRaises(ValidationError):
            FallbackResolution(
                challenge_type="math",
                difficulty_level="easy",
                fallback_reason=FallbackReason.VALIDATION_FAILED,
                fallback_source=FallbackSource.PROCEDURAL_CATALOG,
                trigger_error="Validation failure.",
                fallback_payload=FallbackPayloadContract(fallback_identifier="cat_01"),
                email="user@example.com",  # type: ignore
            )

    def test_model_dump_and_json_serialization(self) -> None:
        """Verify serialization to dict and JSON format preserves enum strings."""
        payload = FallbackPayloadContract(
            fallback_identifier="proc_dance_easy_01",
            instructions_hint="Follow the morning rhythm.",
            parameters_tag="gentle_groove",
        )
        res = FallbackResolution(
            challenge_type="dance",
            difficulty_level="easy",
            fallback_reason=FallbackReason.LATENCY_EXCEEDED,
            fallback_source=FallbackSource.PROCEDURAL_CATALOG,
            trigger_error="Latency budget of 6.0s reached.",
            fallback_payload=payload,
        )
        dumped = res.model_dump()
        self.assertEqual(dumped["challenge_type"], "dance")
        self.assertEqual(dumped["difficulty_level"], "easy")
        self.assertEqual(dumped["fallback_reason"], "latency_exceeded")
        self.assertEqual(dumped["fallback_source"], "procedural_catalog")
        self.assertTrue(dumped["preserved_type"])
        self.assertTrue(dumped["preserved_difficulty"])

        # Test valid JSON dump
        json_str = res.model_dump_json()
        data = json.loads(json_str)
        self.assertEqual(data["fallback_reason"], "latency_exceeded")

    def test_json_schema_generation(self) -> None:
        """Verify OpenAPI/JSON Schema generation succeeds across all models."""
        schemas = [
            SafetyViolationDetails.model_json_schema(),
            SafetyViolation.model_json_schema(),
            SafetyValidationReport.model_json_schema(),
            FallbackPayloadContract.model_json_schema(),
            FallbackResolution.model_json_schema(),
            ValidationRetryPolicy.model_json_schema(),
        ]
        for s in schemas:
            self.assertIn("properties", s)
            self.assertIn("type", s)


if __name__ == "__main__":
    unittest.main()
