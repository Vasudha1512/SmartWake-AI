"""Unit tests for Phase 3.3 Personalization Schemas and Enums.

Validates DecisionSource, DifficultyLevel, DifficultyPreference,
PersonalizationContext, and PersonalizationDecision.
"""
import unittest
from pydantic import ValidationError

from backend.app.core.constants import FORBIDDEN_CHALLENGE_TYPES, VALID_CHALLENGE_TYPES
from backend.app.schemas.personalization_schemas import (
    VALID_DECISION_SOURCES,
    VALID_DIFFICULTY_LEVELS,
    VALID_DIFFICULTY_PREFERENCES,
    DecisionSource,
    DifficultyLevel,
    DifficultyPreference,
    PersonalizationContext,
    PersonalizationDecision,
)


class TestPersonalizationEnums(unittest.TestCase):
    """Test suite for Personalization enums and constant sets."""

    def test_decision_source_enum_values(self):
        """Verify DecisionSource contains all 6 required canonical decision paths."""
        expected = {
            "user_fixed",
            "cold_start_stage_0",
            "cold_start_stage_1",
            "ml_adaptive",
            "guardrail_clamped",
            "fallback_safe",
        }
        actual = {e.value for e in DecisionSource}
        self.assertEqual(actual, expected)
        self.assertEqual(VALID_DECISION_SOURCES, expected)

    def test_difficulty_level_enum_values(self):
        """Verify DifficultyLevel contains easy, medium, hard."""
        expected = {"easy", "medium", "hard"}
        actual = {e.value for e in DifficultyLevel}
        self.assertEqual(actual, expected)
        self.assertEqual(VALID_DIFFICULTY_LEVELS, expected)

    def test_difficulty_preference_enum_values(self):
        """Verify DifficultyPreference contains easy, medium, hard, and adaptive."""
        expected = {"easy", "medium", "hard", "adaptive"}
        actual = {e.value for e in DifficultyPreference}
        self.assertEqual(actual, expected)
        self.assertEqual(VALID_DIFFICULTY_PREFERENCES, expected)


class TestPersonalizationContext(unittest.TestCase):
    """Test suite for PersonalizationContext input schema."""

    def test_valid_context_with_defaults(self):
        """Verify PersonalizationContext creates successfully with default values."""
        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=10,
            challenge_type="math",
        )
        self.assertEqual(ctx.user_id, 1)
        self.assertEqual(ctx.wake_session_id, 10)
        self.assertIsNone(ctx.alarm_id)
        self.assertEqual(ctx.challenge_type, "math")
        self.assertEqual(ctx.difficulty_preference, "adaptive")
        self.assertEqual(ctx.current_session_snooze_count, 0)
        self.assertEqual(ctx.historical_session_count, 0)
        self.assertIsNone(ctx.previous_difficulty)

    def test_valid_context_full_fields(self):
        """Verify PersonalizationContext creates with all fields specified."""
        ctx = PersonalizationContext(
            user_id=2,
            wake_session_id=20,
            alarm_id=5,
            challenge_type="dance",
            difficulty_preference="hard",
            current_session_snooze_count=3,
            historical_session_count=15,
            previous_difficulty="medium",
        )
        self.assertEqual(ctx.user_id, 2)
        self.assertEqual(ctx.wake_session_id, 20)
        self.assertEqual(ctx.alarm_id, 5)
        self.assertEqual(ctx.challenge_type, "dance")
        self.assertEqual(ctx.difficulty_preference, "hard")
        self.assertEqual(ctx.current_session_snooze_count, 3)
        self.assertEqual(ctx.historical_session_count, 15)
        self.assertEqual(ctx.previous_difficulty, "medium")

    def test_all_valid_challenge_types_accepted(self):
        """Verify all valid challenge types from constants are accepted."""
        for ctype in VALID_CHALLENGE_TYPES:
            ctx = PersonalizationContext(
                user_id=1,
                wake_session_id=1,
                challenge_type=ctype,
            )
            self.assertEqual(ctx.challenge_type, ctype)

    def test_forbidden_challenge_type_rejected(self):
        """Verify forbidden challenge types (e.g. number guessing) are rejected."""
        for forbidden in FORBIDDEN_CHALLENGE_TYPES:
            with self.assertRaises(ValidationError) as cm:
                PersonalizationContext(
                    user_id=1,
                    wake_session_id=1,
                    challenge_type=forbidden,
                )
            self.assertIn("Forbidden challenge type", str(cm.exception))

    def test_invalid_challenge_type_rejected(self):
        """Verify unrecognized challenge types raise ValidationError."""
        with self.assertRaises(ValidationError) as cm:
            PersonalizationContext(
                user_id=1,
                wake_session_id=1,
                challenge_type="sudoku_puzzle",
            )
        self.assertIn("Invalid challenge type", str(cm.exception))

    def test_invalid_difficulty_preference_rejected(self):
        """Verify invalid difficulty preference raises ValidationError."""
        with self.assertRaises(ValidationError) as cm:
            PersonalizationContext(
                user_id=1,
                wake_session_id=1,
                challenge_type="math",
                difficulty_preference="super_extreme",
            )
        self.assertIn("Invalid difficulty preference", str(cm.exception))

    def test_invalid_previous_difficulty_rejected(self):
        """Verify previous_difficulty only accepts easy, medium, hard (not adaptive)."""
        # adaptive is not a concrete difficulty tier
        with self.assertRaises(ValidationError) as cm:
            PersonalizationContext(
                user_id=1,
                wake_session_id=1,
                challenge_type="math",
                previous_difficulty="adaptive",
            )
        self.assertIn("Invalid previous difficulty", str(cm.exception))

    def test_negative_counts_rejected(self):
        """Verify negative snooze or session counts raise ValidationError."""
        with self.assertRaises(ValidationError):
            PersonalizationContext(
                user_id=1,
                wake_session_id=1,
                challenge_type="math",
                current_session_snooze_count=-1,
            )
        with self.assertRaises(ValidationError):
            PersonalizationContext(
                user_id=1,
                wake_session_id=1,
                challenge_type="math",
                historical_session_count=-5,
            )

    def test_non_positive_ids_rejected(self):
        """Verify user_id, wake_session_id, and alarm_id must be positive."""
        with self.assertRaises(ValidationError):
            PersonalizationContext(
                user_id=0,
                wake_session_id=1,
                challenge_type="math",
            )
        with self.assertRaises(ValidationError):
            PersonalizationContext(
                user_id=1,
                wake_session_id=-1,
                challenge_type="math",
            )
        with self.assertRaises(ValidationError):
            PersonalizationContext(
                user_id=1,
                wake_session_id=1,
                alarm_id=0,
                challenge_type="math",
            )


class TestPersonalizationDecision(unittest.TestCase):
    """Test suite for PersonalizationDecision output schema."""

    def test_valid_decision_defaults(self):
        """Verify PersonalizationDecision creates with valid defaults."""
        decision = PersonalizationDecision(
            recommended_difficulty="medium",
            challenge_type="math",
            decision_source="ml_adaptive",
        )
        self.assertEqual(decision.recommended_difficulty, "medium")
        self.assertEqual(decision.challenge_type, "math")
        self.assertEqual(decision.decision_source, "ml_adaptive")
        self.assertIsNone(decision.model_confidence)
        self.assertIsNone(decision.raw_model_prediction)
        self.assertFalse(decision.guardrail_applied)
        self.assertIsNone(decision.guardrail_reason)
        self.assertEqual(decision.feature_snapshot, {})

    def test_valid_decision_with_enums(self):
        """Verify PersonalizationDecision accepts enum instances directly."""
        decision = PersonalizationDecision(
            recommended_difficulty=DifficultyLevel.HARD,
            challenge_type="dance",
            decision_source=DecisionSource.GUARDRAIL_CLAMPED,
            model_confidence=0.88,
            raw_model_prediction=DifficultyLevel.HARD,
            guardrail_applied=True,
            guardrail_reason="sleep_inertia_floor_applied",
            feature_snapshot={"snooze_count": 3},
        )
        self.assertEqual(decision.recommended_difficulty, "hard")
        self.assertEqual(decision.challenge_type, "dance")
        self.assertEqual(decision.decision_source, "guardrail_clamped")
        self.assertEqual(decision.model_confidence, 0.88)
        self.assertEqual(decision.raw_model_prediction, "hard")
        self.assertTrue(decision.guardrail_applied)
        self.assertEqual(decision.guardrail_reason, "sleep_inertia_floor_applied")
        self.assertEqual(decision.feature_snapshot, {"snooze_count": 3})

    def test_all_decision_sources_accepted(self):
        """Verify every DecisionSource value is accepted by PersonalizationDecision."""
        for src in VALID_DECISION_SOURCES:
            decision = PersonalizationDecision(
                recommended_difficulty="easy",
                challenge_type="memory",
                decision_source=src,
            )
            self.assertEqual(decision.decision_source, src)

    def test_invalid_recommended_difficulty_rejected(self):
        """Verify recommended_difficulty must be a concrete difficulty level."""
        with self.assertRaises(ValidationError) as cm:
            PersonalizationDecision(
                recommended_difficulty="adaptive",
                challenge_type="math",
                decision_source="user_fixed",
            )
        self.assertIn("Invalid recommended difficulty", str(cm.exception))

    def test_invalid_decision_source_rejected(self):
        """Verify invalid decision source raises ValidationError."""
        with self.assertRaises(ValidationError) as cm:
            PersonalizationDecision(
                recommended_difficulty="medium",
                challenge_type="math",
                decision_source="random_guess",
            )
        self.assertIn("Invalid decision source", str(cm.exception))

    def test_model_confidence_bounds(self):
        """Verify model_confidence must be between 0.0 and 1.0."""
        # Valid edge cases
        d0 = PersonalizationDecision(
            recommended_difficulty="easy",
            challenge_type="math",
            decision_source="ml_adaptive",
            model_confidence=0.0,
        )
        self.assertEqual(d0.model_confidence, 0.0)

        d1 = PersonalizationDecision(
            recommended_difficulty="easy",
            challenge_type="math",
            decision_source="ml_adaptive",
            model_confidence=1.0,
        )
        self.assertEqual(d1.model_confidence, 1.0)

        # Invalid bounds
        with self.assertRaises(ValidationError):
            PersonalizationDecision(
                recommended_difficulty="easy",
                challenge_type="math",
                decision_source="ml_adaptive",
                model_confidence=-0.05,
            )
        with self.assertRaises(ValidationError):
            PersonalizationDecision(
                recommended_difficulty="easy",
                challenge_type="math",
                decision_source="ml_adaptive",
                model_confidence=1.05,
            )

    def test_serialization_roundtrip(self):
        """Verify model_dump and model_dump_json serialize cleanly."""
        decision = PersonalizationDecision(
            recommended_difficulty="hard",
            challenge_type="tongue_twister",
            decision_source="user_fixed",
            feature_snapshot={"sessions": 10},
        )
        dumped = decision.model_dump()
        self.assertEqual(dumped["recommended_difficulty"], "hard")
        self.assertEqual(dumped["challenge_type"], "tongue_twister")
        self.assertEqual(dumped["decision_source"], "user_fixed")

        json_str = decision.model_dump_json()
        self.assertIn('"recommended_difficulty":"hard"', json_str)
        self.assertIn('"decision_source":"user_fixed"', json_str)


if __name__ == "__main__":
    unittest.main()
