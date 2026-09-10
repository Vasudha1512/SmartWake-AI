"""Unit tests for Step 3.3.4 — Core Personalization Engine Assembly.

Verifies:
1. Fixed easy preference returns easy with user_fixed.
2. Fixed medium preference returns medium with user_fixed.
3. Fixed hard preference returns hard with user_fixed.
4. Fixed preference never invokes ModelInferenceManager.
5. Fixed preference bypasses adaptive safety guardrails (absolute user precedence).
6. Adaptive Stage 0 (0-3 historical sessions) uses heuristics without ML.
7. Adaptive Stage 1 (4-7 historical sessions) uses contextual rules without ML.
8. Adaptive Stage 2 (8+ historical sessions) invokes ML inference.
9. ML prediction with confidence >= 0.60 produces ml_adaptive decision.
10. ML prediction with confidence < 0.60 does not become final decision.
11. Low-confidence fallback produces fallback_safe.
12. Fallback uses available telemetry without fabricating synthetic data.
13. Fallback without telemetry safely resolves without inventing runtime metrics.
14. Safety guardrails applied after adaptive ML candidate selection.
15. Previous difficulty +-1 step-shift restriction enforced on ML candidates.
16. Snooze count >= 3 hard-to-medium sleep inertia clamp enforced on ML candidates.
17. Selected challenge type remains strictly unchanged across all 5 canonical challenge types.
18. user_selected_difficulty is not passed as an ML feature.
19. is_adaptive_preference is not passed as an ML feature.
20. Post-challenge target/outcome fields (target_*) are not passed to ML.
21. No database writes occur during personalization decisions.
22. Complete PersonalizationDecision output is produced and validates against Pydantic schema.
23. Decision source is correct for every path.
24. PersonalizationEngine.decide supports both instance and classmethod invocation.
25. PersonalizationContext validation handles dict and schema objects, rejecting invalid inputs.
"""
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from pydantic import ValidationError

from backend.app.schemas.personalization_schemas import (
    DecisionSource,
    DifficultyLevel,
    PersonalizationContext,
    PersonalizationDecision,
)
from backend.app.services.model_inference_manager import (
    ModelInferenceManager,
    ModelInferenceResult,
)
from backend.app.services.personalization_engine import (
    ColdStartRouter,
    PersonalizationEngine,
    SafetyGuardrails,
)
from ml.preprocessing.feature_schema import ChallengeFeatureRecord


def make_valid_feature_dict(challenge_type: str = "math") -> dict:
    """Helper to construct a valid 30-feature dictionary for testing."""
    return {
        "user_total_wake_sessions": 12,
        "user_successful_wake_sessions": 10,
        "user_failed_wake_sessions": 2,
        "user_historical_success_rate": 0.833,
        "user_avg_completion_time_seconds": 16.5,
        "user_avg_attempts_per_session": 1.1,
        "user_avg_snooze_count": 0.5,
        "user_total_snooze_count": 6,
        "user_recent_snooze_count": 1,
        "user_recent_challenge_success_rate": 0.8,
        "challenge_type_total_attempts": 6,
        "challenge_type_successful_attempts": 5,
        "challenge_type_success_rate": 0.833,
        "challenge_type_avg_completion_time": 15.2,
        "challenge_type_avg_attempts_per_session": 1.0,
        "challenge_type_easy_attempts": 2,
        "challenge_type_easy_success_rate": 1.0,
        "challenge_type_medium_attempts": 3,
        "challenge_type_medium_success_rate": 0.67,
        "challenge_type_hard_attempts": 1,
        "challenge_type_hard_success_rate": 1.0,
        "current_session_snooze_count": 0,
        "current_session_snooze_duration_minutes": 0,
        "current_session_wake_delay_seconds": 25.0,
        "alarm_scheduled_hour": 7,
        "alarm_scheduled_minute": 30,
        "alarm_day_of_week": 2,
        "alarm_is_weekend": 0,
        "historical_snooze_avg_around_alarm_time": 0.6,
        "selected_challenge_type": challenge_type,
    }


class TestPersonalizationEngineAssembly(unittest.TestCase):
    """Test suite for Step 3.3.4 Core Personalization Engine Assembly."""

    def setUp(self):
        self.mock_model_manager = MagicMock(spec=ModelInferenceManager)
        self.engine_with_mock = PersonalizationEngine(model_manager=self.mock_model_manager)
        self.real_engine = PersonalizationEngine()

    # 1. Fixed easy preference
    def test_fixed_easy_preference(self):
        """User-fixed easy preference must return easy with DecisionSource.USER_FIXED."""
        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=10,
            challenge_type="math",
            difficulty_preference="easy",
            historical_session_count=15,
            previous_difficulty="hard",
        )
        decision = self.engine_with_mock.decide(ctx)

        self.assertIsInstance(decision, PersonalizationDecision)
        self.assertEqual(decision.recommended_difficulty, "easy")
        self.assertEqual(decision.challenge_type, "math")
        self.assertEqual(decision.decision_source, DecisionSource.USER_FIXED.value)
        self.assertIsNone(decision.model_confidence)
        self.assertIsNone(decision.raw_model_prediction)
        self.assertFalse(decision.guardrail_applied)
        self.assertIsNone(decision.guardrail_reason)
        self.assertEqual(decision.feature_snapshot, {})
        self.mock_model_manager.predict.assert_not_called()

    # 2. Fixed medium preference
    def test_fixed_medium_preference(self):
        """User-fixed medium preference must return medium with DecisionSource.USER_FIXED."""
        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=11,
            challenge_type="dance",
            difficulty_preference="medium",
            historical_session_count=20,
        )
        decision = self.engine_with_mock.decide(ctx)

        self.assertEqual(decision.recommended_difficulty, "medium")
        self.assertEqual(decision.challenge_type, "dance")
        self.assertEqual(decision.decision_source, DecisionSource.USER_FIXED.value)
        self.mock_model_manager.predict.assert_not_called()

    # 3. Fixed hard preference
    def test_fixed_hard_preference(self):
        """User-fixed hard preference must return hard with DecisionSource.USER_FIXED."""
        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=12,
            challenge_type="tongue_twister",
            difficulty_preference="hard",
            historical_session_count=50,
        )
        decision = self.engine_with_mock.decide(ctx)

        self.assertEqual(decision.recommended_difficulty, "hard")
        self.assertEqual(decision.challenge_type, "tongue_twister")
        self.assertEqual(decision.decision_source, DecisionSource.USER_FIXED.value)
        self.mock_model_manager.predict.assert_not_called()

    # 4. Fixed preference does not invoke ML
    def test_fixed_preference_never_invokes_ml(self):
        """Verify across all fixed preferences that ML inference is never called."""
        for diff in ["easy", "medium", "hard"]:
            ctx = PersonalizationContext(
                user_id=2,
                wake_session_id=15,
                challenge_type="push_ups",
                difficulty_preference=diff,
                historical_session_count=100,  # Even with 100 sessions
            )
            self.mock_model_manager.reset_mock()
            decision = self.engine_with_mock.decide(ctx)
            self.assertEqual(decision.recommended_difficulty, diff)
            self.assertEqual(decision.decision_source, DecisionSource.USER_FIXED.value)
            self.mock_model_manager.predict.assert_not_called()

    # 5. Fixed preference bypasses adaptive guardrails
    def test_fixed_preference_bypasses_adaptive_guardrails(self):
        """Explicit fixed preferences must NEVER be overridden by adaptive guardrails.

        Example: User selects HARD with previous EASY (+2 shift) and snooze=4 (sleep inertia).
        Adaptive rules would clamp this to medium, but fixed user choice MUST be respected.
        """
        ctx = PersonalizationContext(
            user_id=3,
            wake_session_id=16,
            challenge_type="math",
            difficulty_preference="hard",
            current_session_snooze_count=4,  # snooze >= 3 would clamp adaptive to medium
            historical_session_count=10,
            previous_difficulty="easy",      # easy -> hard would clamp adaptive to medium
        )
        decision = self.engine_with_mock.decide(ctx)

        self.assertEqual(decision.recommended_difficulty, "hard")
        self.assertEqual(decision.decision_source, DecisionSource.USER_FIXED.value)
        self.assertFalse(decision.guardrail_applied)
        self.assertIsNone(decision.guardrail_reason)

    # 6. Adaptive Stage 0 (0-3 sessions)
    def test_adaptive_stage_0_heuristics(self):
        """Stage 0 (0-3 sessions) uses ColdStartRouter heuristics and never invokes ML."""
        for count in [0, 1, 2, 3]:
            # Math defaults to easy in Stage 0
            ctx = PersonalizationContext(
                user_id=1,
                wake_session_id=20,
                challenge_type="math",
                difficulty_preference="adaptive",
                historical_session_count=count,
                current_session_snooze_count=0,
            )
            self.mock_model_manager.reset_mock()
            decision = self.engine_with_mock.decide(ctx)

            self.assertEqual(decision.recommended_difficulty, "easy")
            self.assertEqual(decision.decision_source, DecisionSource.COLD_START_STAGE_0.value)
            self.assertIsNone(decision.model_confidence)
            self.assertIsNone(decision.raw_model_prediction)
            self.assertFalse(decision.guardrail_applied)
            self.mock_model_manager.predict.assert_not_called()

        # Dance defaults to medium in Stage 0
        ctx_dance = PersonalizationContext(
            user_id=1,
            wake_session_id=21,
            challenge_type="dance",
            difficulty_preference="adaptive",
            historical_session_count=2,
            current_session_snooze_count=0,
        )
        decision_dance = self.engine_with_mock.decide(ctx_dance)
        self.assertEqual(decision_dance.recommended_difficulty, "medium")
        self.assertEqual(decision_dance.decision_source, DecisionSource.COLD_START_STAGE_0.value)

    # 7. Adaptive Stage 1 (4-7 sessions)
    def test_adaptive_stage_1_contextual_rules(self):
        """Stage 1 (4-7 sessions) uses contextual rules and never invokes ML."""
        for count in [4, 5, 6, 7]:
            # Mastery promotion: 100% success rate, duration < 15s promotes medium to hard
            ctx = PersonalizationContext(
                user_id=1,
                wake_session_id=25,
                challenge_type="memory",
                difficulty_preference="adaptive",
                historical_session_count=count,
                previous_difficulty="medium",
            )
            self.mock_model_manager.reset_mock()
            decision = self.engine_with_mock.decide(
                ctx,
                recent_success_rate=1.0,
                recent_avg_duration_seconds=12.0,
                has_recent_failure=False,
            )

            self.assertEqual(decision.recommended_difficulty, "hard")
            self.assertEqual(decision.decision_source, DecisionSource.COLD_START_STAGE_1.value)
            self.assertIsNone(decision.model_confidence)
            self.assertIsNone(decision.raw_model_prediction)
            self.assertFalse(decision.guardrail_applied)
            self.mock_model_manager.predict.assert_not_called()

        # Demotion on recent failure: resolves to easy
        ctx_fail = PersonalizationContext(
            user_id=1,
            wake_session_id=26,
            challenge_type="memory",
            difficulty_preference="adaptive",
            historical_session_count=5,
            previous_difficulty="medium",
        )
        decision_fail = self.engine_with_mock.decide(ctx_fail, has_recent_failure=True)
        self.assertEqual(decision_fail.recommended_difficulty, "easy")
        self.assertEqual(decision_fail.decision_source, DecisionSource.COLD_START_STAGE_1.value)

    # 8. Adaptive Stage 2 with successful ML inference
    def test_adaptive_stage_2_successful_ml_inference(self):
        """Stage 2 (8+ sessions) invokes ML inference and uses ML recommendation."""
        feats = make_valid_feature_dict(challenge_type="math")
        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=30,
            challenge_type="math",
            difficulty_preference="adaptive",
            historical_session_count=12,
            previous_difficulty="medium",
        )

        decision = self.real_engine.decide(ctx, feature_record=feats)

        self.assertIsInstance(decision, PersonalizationDecision)
        self.assertIn(decision.recommended_difficulty, ["easy", "medium", "hard"])
        self.assertEqual(decision.challenge_type, "math")
        self.assertEqual(decision.decision_source, DecisionSource.ML_ADAPTIVE.value)
        self.assertIsNotNone(decision.model_confidence)
        self.assertGreaterEqual(decision.model_confidence, 0.60)
        self.assertEqual(decision.raw_model_prediction, decision.recommended_difficulty)
        self.assertFalse(decision.guardrail_applied)
        self.assertEqual(len(decision.feature_snapshot), 30)

    # 9. ML prediction with confidence >= 0.60
    def test_ml_prediction_confidence_gte_threshold(self):
        """Mock test: ML inference with confidence >= 0.60 accepted as ml_adaptive."""
        feats = make_valid_feature_dict()
        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=31,
            challenge_type="dance",
            difficulty_preference="adaptive",
            historical_session_count=10,
            previous_difficulty="medium",
        )

        self.mock_model_manager.predict.return_value = ModelInferenceResult(
            predicted_difficulty="hard",
            confidence=0.78,
            probabilities={"easy": 0.05, "medium": 0.17, "hard": 0.78},
            meets_confidence_threshold=True,
            confidence_threshold=0.60,
            feature_snapshot=feats,
            model_name="baseline_difficulty_classifier",
        )

        decision = self.engine_with_mock.decide(ctx, feature_record=feats)
        self.assertEqual(decision.recommended_difficulty, "hard")
        self.assertEqual(decision.decision_source, DecisionSource.ML_ADAPTIVE.value)
        self.assertEqual(decision.model_confidence, 0.78)
        self.assertEqual(decision.raw_model_prediction, "hard")
        self.assertFalse(decision.guardrail_applied)

    # 10. ML prediction with confidence < 0.60
    def test_ml_prediction_confidence_lt_threshold_not_accepted(self):
        """ML inference with confidence < 0.60 must NOT be accepted as final candidate."""
        feats = make_valid_feature_dict()
        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=32,
            challenge_type="dance",
            difficulty_preference="adaptive",
            historical_session_count=10,
            previous_difficulty="medium",
        )

        # Mock ML returns 'hard' but with low confidence 0.42 (< 0.60)
        self.mock_model_manager.predict.return_value = ModelInferenceResult(
            predicted_difficulty="hard",
            confidence=0.42,
            probabilities={"easy": 0.28, "medium": 0.30, "hard": 0.42},
            meets_confidence_threshold=False,
            confidence_threshold=0.60,
            feature_snapshot=feats,
            model_name="baseline_difficulty_classifier",
        )

        # Telemetry indicates neutral performance -> Stage 1 fallback evaluates to 'medium'
        decision = self.engine_with_mock.decide(
            ctx,
            feature_record=feats,
            recent_success_rate=0.75,
            recent_avg_duration_seconds=20.0,
            has_recent_failure=False,
        )

        # Must NOT be 'hard' (the low-confidence ML prediction)
        self.assertEqual(decision.recommended_difficulty, "medium")
        self.assertEqual(decision.decision_source, DecisionSource.FALLBACK_SAFE.value)
        # Raw prediction and confidence preserved for auditability
        self.assertEqual(decision.raw_model_prediction, "hard")
        self.assertEqual(decision.model_confidence, 0.42)

    # 11. Low-confidence fallback
    def test_low_confidence_fallback_records_fallback_safe(self):
        """Low confidence ML must set decision_source to DecisionSource.FALLBACK_SAFE."""
        feats = make_valid_feature_dict()
        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=33,
            challenge_type="math",
            difficulty_preference="adaptive",
            historical_session_count=8,
            previous_difficulty="medium",
        )

        self.mock_model_manager.predict.return_value = ModelInferenceResult(
            predicted_difficulty="easy",
            confidence=0.48,
            probabilities={"easy": 0.48, "medium": 0.30, "hard": 0.22},
            meets_confidence_threshold=False,
            confidence_threshold=0.60,
            feature_snapshot=feats,
            model_name="baseline_difficulty_classifier",
        )

        decision = self.engine_with_mock.decide(ctx, feature_record=feats)
        self.assertEqual(decision.decision_source, DecisionSource.FALLBACK_SAFE.value)
        self.assertEqual(decision.model_confidence, 0.48)
        self.assertEqual(decision.raw_model_prediction, "easy")

    # 12. Fallback with available telemetry
    def test_fallback_uses_available_telemetry_without_fabrication(self):
        """Fallback extracts real telemetry from feature_record without fabricating data."""
        feats = make_valid_feature_dict()
        # Telemetry in feature dict shows mastery: 100% success rate, 12s completion time
        feats["user_recent_challenge_success_rate"] = 1.0
        feats["challenge_type_avg_completion_time"] = 12.0
        feats["user_failed_wake_sessions"] = 0

        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=34,
            challenge_type="math",
            difficulty_preference="adaptive",
            historical_session_count=9,
            previous_difficulty="medium",
        )

        self.mock_model_manager.predict.return_value = ModelInferenceResult(
            predicted_difficulty="easy",
            confidence=0.40,
            probabilities={"easy": 0.40, "medium": 0.35, "hard": 0.25},
            meets_confidence_threshold=False,
            confidence_threshold=0.60,
            feature_snapshot=feats,
            model_name="baseline_difficulty_classifier",
        )

        # Stage 1 fallback evaluates real mastery telemetry -> promotes 'medium' to 'hard'
        decision = self.engine_with_mock.decide(ctx, feature_record=feats)
        self.assertEqual(decision.recommended_difficulty, "hard")
        self.assertEqual(decision.decision_source, DecisionSource.FALLBACK_SAFE.value)

    # 13. Fallback without telemetry safely resolves without fabricating data
    def test_fallback_without_telemetry_safely_defaults(self):
        """When telemetry is genuinely unavailable, fallback uses default neutral rule without fabrication."""
        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=35,
            challenge_type="math",
            difficulty_preference="adaptive",
            historical_session_count=10,
            previous_difficulty="medium",
        )
        # Stage 2 called with feature_record=None: safe fallback without inventing telemetry
        decision = self.engine_with_mock.decide(ctx, feature_record=None)
        # Default neutral Stage 1 rule resolves to 'medium'
        self.assertEqual(decision.recommended_difficulty, "medium")
        self.assertEqual(decision.decision_source, DecisionSource.FALLBACK_SAFE.value)
        self.assertFalse(decision.guardrail_applied)

    # 14. Safety guardrails after ML candidate selection
    def test_safety_guardrail_after_ml_candidate(self):
        """Guardrails must apply after ML prediction, setting DecisionSource.GUARDRAIL_CLAMPED."""
        feats = make_valid_feature_dict()
        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=36,
            challenge_type="dance",
            difficulty_preference="adaptive",
            historical_session_count=14,
            previous_difficulty="medium",
            current_session_snooze_count=3,  # Snooze >= 3 must clamp hard -> medium
        )

        self.mock_model_manager.predict.return_value = ModelInferenceResult(
            predicted_difficulty="hard",
            confidence=0.85,
            probabilities={"easy": 0.05, "medium": 0.10, "hard": 0.85},
            meets_confidence_threshold=True,
            confidence_threshold=0.60,
            feature_snapshot=feats,
            model_name="baseline_difficulty_classifier",
        )

        decision = self.engine_with_mock.decide(ctx, feature_record=feats)

        self.assertEqual(decision.recommended_difficulty, "medium")  # Clamped from hard
        self.assertEqual(decision.raw_model_prediction, "hard")
        self.assertEqual(decision.decision_source, DecisionSource.GUARDRAIL_CLAMPED.value)
        self.assertTrue(decision.guardrail_applied)
        self.assertIn("Sleep inertia floor applied", str(decision.guardrail_reason))

    # 15. Previous difficulty +-1 restriction
    def test_previous_difficulty_step_shift_restriction_on_ml(self):
        """ML candidate 'hard' with previous 'easy' (+2 shift) clamped to 'medium'."""
        feats = make_valid_feature_dict()
        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=37,
            challenge_type="math",
            difficulty_preference="adaptive",
            historical_session_count=15,
            previous_difficulty="easy",
            current_session_snooze_count=0,
        )

        self.mock_model_manager.predict.return_value = ModelInferenceResult(
            predicted_difficulty="hard",
            confidence=0.82,
            probabilities={"easy": 0.08, "medium": 0.10, "hard": 0.82},
            meets_confidence_threshold=True,
            confidence_threshold=0.60,
            feature_snapshot=feats,
            model_name="baseline_difficulty_classifier",
        )

        decision = self.engine_with_mock.decide(ctx, feature_record=feats)
        self.assertEqual(decision.recommended_difficulty, "medium")  # Clamped from hard
        self.assertEqual(decision.decision_source, DecisionSource.GUARDRAIL_CLAMPED.value)
        self.assertTrue(decision.guardrail_applied)
        self.assertIn("Maximum step shift clamped", str(decision.guardrail_reason))

    # 16. Snooze >= 3 hard-to-medium clamp
    def test_snooze_gte_3_hard_to_medium_clamp_on_ml(self):
        """Candidate 'hard' with snooze_count >= 3 is strictly clamped to 'medium'."""
        feats = make_valid_feature_dict()
        for snoozes in [3, 4, 7]:
            ctx = PersonalizationContext(
                user_id=1,
                wake_session_id=38,
                challenge_type="push_ups",
                difficulty_preference="adaptive",
                historical_session_count=10,
                previous_difficulty="hard",
                current_session_snooze_count=snoozes,
            )

            self.mock_model_manager.predict.return_value = ModelInferenceResult(
                predicted_difficulty="hard",
                confidence=0.90,
                probabilities={"easy": 0.02, "medium": 0.08, "hard": 0.90},
                meets_confidence_threshold=True,
                confidence_threshold=0.60,
                feature_snapshot=feats,
                model_name="baseline_difficulty_classifier",
            )

            decision = self.engine_with_mock.decide(ctx, feature_record=feats)
            self.assertEqual(decision.recommended_difficulty, "medium")
            self.assertTrue(decision.guardrail_applied)
            self.assertEqual(decision.decision_source, DecisionSource.GUARDRAIL_CLAMPED.value)

    # 17. Challenge type remains unchanged for all 5 canonical types
    def test_challenge_type_preserved_across_all_five_types(self):
        """Ensure challenge_type is never modified across dance, math, memory, tongue_twister, push_ups."""
        canonical_types = ["dance", "math", "memory", "tongue_twister", "push_ups"]

        for ctype in canonical_types:
            feats = make_valid_feature_dict(challenge_type=ctype)
            ctx = PersonalizationContext(
                user_id=1,
                wake_session_id=40,
                challenge_type=ctype,
                difficulty_preference="adaptive",
                historical_session_count=12,
                previous_difficulty="medium",
            )
            decision = self.real_engine.decide(ctx, feature_record=feats)
            self.assertEqual(decision.challenge_type, ctype)

    # 18. user_selected_difficulty leakage prevention
    def test_user_selected_difficulty_not_passed_to_ml(self):
        """Verify user_selected_difficulty is stripped and never passed to ML."""
        feats = make_valid_feature_dict()
        feats["user_selected_difficulty"] = "hard"

        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=41,
            challenge_type="math",
            difficulty_preference="adaptive",
            historical_session_count=10,
        )

        self.mock_model_manager.predict.return_value = ModelInferenceResult(
            predicted_difficulty="medium",
            confidence=0.75,
            probabilities={"easy": 0.15, "medium": 0.75, "hard": 0.10},
            meets_confidence_threshold=True,
            confidence_threshold=0.60,
            feature_snapshot=make_valid_feature_dict(),
            model_name="baseline_difficulty_classifier",
        )

        self.engine_with_mock.decide(ctx, feature_record=feats)
        passed_features = self.mock_model_manager.predict.call_args[0][0]
        self.assertNotIn("user_selected_difficulty", passed_features)

    # 19. is_adaptive_preference leakage prevention
    def test_is_adaptive_preference_not_passed_to_ml(self):
        """Verify is_adaptive_preference is stripped and never passed to ML."""
        feats = make_valid_feature_dict()
        feats["is_adaptive_preference"] = 1

        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=42,
            challenge_type="math",
            difficulty_preference="adaptive",
            historical_session_count=10,
        )

        self.mock_model_manager.predict.return_value = ModelInferenceResult(
            predicted_difficulty="medium",
            confidence=0.75,
            probabilities={"easy": 0.15, "medium": 0.75, "hard": 0.10},
            meets_confidence_threshold=True,
            confidence_threshold=0.60,
            feature_snapshot=make_valid_feature_dict(),
            model_name="baseline_difficulty_classifier",
        )

        self.engine_with_mock.decide(ctx, feature_record=feats)
        passed_features = self.mock_model_manager.predict.call_args[0][0]
        self.assertNotIn("is_adaptive_preference", passed_features)

    # 20. Post-challenge target outcomes not passed to ML
    def test_post_challenge_outcomes_not_passed_to_ml(self):
        """Verify post-challenge outcome fields (target_*) are stripped before ML prediction."""
        record = ChallengeFeatureRecord(
            user_id=1,
            wake_session_id=43,
            challenge_attempt_id=10,
            alarm_id=2,
            timestamp="2026-09-10T12:00:00Z",
            user_total_wake_sessions=15,
            target_is_successful=1,
            target_duration_seconds=14.5,
            target_verification_score=0.95,
            target_attempt_number=1,
        )

        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=43,
            challenge_type="tongue_twister",
            difficulty_preference="adaptive",
            historical_session_count=10,
        )

        self.mock_model_manager.predict.return_value = ModelInferenceResult(
            predicted_difficulty="medium",
            confidence=0.80,
            probabilities={"easy": 0.10, "medium": 0.80, "hard": 0.10},
            meets_confidence_threshold=True,
            confidence_threshold=0.60,
            feature_snapshot=make_valid_feature_dict(),
            model_name="baseline_difficulty_classifier",
        )

        self.engine_with_mock.decide(ctx, feature_record=record)
        passed_features = self.mock_model_manager.predict.call_args[0][0]
        self.assertNotIn("target_is_successful", passed_features)
        self.assertNotIn("target_duration_seconds", passed_features)
        self.assertNotIn("target_verification_score", passed_features)
        self.assertNotIn("target_attempt_number", passed_features)

    # 21. No database writes
    def test_no_database_writes(self):
        """Verify that running personalization decisions performs zero database writes."""
        db_path = Path("smartwake.db")
        initial_mtime = db_path.stat().st_mtime if db_path.exists() else None
        initial_size = db_path.stat().st_size if db_path.exists() else None

        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=50,
            challenge_type="math",
            difficulty_preference="adaptive",
            historical_session_count=12,
            previous_difficulty="medium",
        )
        feats = make_valid_feature_dict()
        _ = self.real_engine.decide(ctx, feature_record=feats)

        if db_path.exists():
            self.assertEqual(db_path.stat().st_mtime, initial_mtime)
            self.assertEqual(db_path.stat().st_size, initial_size)

    # 22. Complete PersonalizationDecision validation
    def test_complete_personalization_decision_validation(self):
        """Verify PersonalizationDecision contains all required fields and serializes cleanly."""
        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=55,
            challenge_type="dance",
            difficulty_preference="adaptive",
            historical_session_count=15,
            previous_difficulty="medium",
        )
        feats = make_valid_feature_dict(challenge_type="dance")
        decision = self.real_engine.decide(ctx, feature_record=feats)

        # All required schema fields present
        self.assertIn(decision.recommended_difficulty, ["easy", "medium", "hard"])
        self.assertEqual(decision.challenge_type, "dance")
        self.assertIn(decision.decision_source, [e.value for e in DecisionSource])
        self.assertIsNotNone(decision.model_confidence)
        self.assertIsNotNone(decision.raw_model_prediction)
        self.assertIsInstance(decision.guardrail_applied, bool)
        self.assertIsInstance(decision.feature_snapshot, dict)

        # Pydantic dump round-trip
        dumped = decision.model_dump()
        self.assertEqual(dumped["challenge_type"], "dance")
        json_str = decision.model_dump_json()
        self.assertIn('"challenge_type":"dance"', json_str)

    # 23. Decision source is correct for every path
    def test_decision_source_all_paths(self):
        """Verify every DecisionSource enum value is correctly produced across all paths."""
        # 1. user_fixed
        c_fixed = PersonalizationContext(
            user_id=1, wake_session_id=1, challenge_type="math", difficulty_preference="hard"
        )
        d_fixed = self.engine_with_mock.decide(c_fixed)
        self.assertEqual(d_fixed.decision_source, DecisionSource.USER_FIXED.value)

        # 2. cold_start_stage_0
        c_s0 = PersonalizationContext(
            user_id=1, wake_session_id=2, challenge_type="math", difficulty_preference="adaptive", historical_session_count=1
        )
        d_s0 = self.engine_with_mock.decide(c_s0)
        self.assertEqual(d_s0.decision_source, DecisionSource.COLD_START_STAGE_0.value)

        # 3. cold_start_stage_1
        c_s1 = PersonalizationContext(
            user_id=1, wake_session_id=3, challenge_type="math", difficulty_preference="adaptive", historical_session_count=5
        )
        d_s1 = self.engine_with_mock.decide(c_s1)
        self.assertEqual(d_s1.decision_source, DecisionSource.COLD_START_STAGE_1.value)

        # 4. ml_adaptive
        feats = make_valid_feature_dict()
        c_s2_ml = PersonalizationContext(
            user_id=1, wake_session_id=4, challenge_type="math", difficulty_preference="adaptive", historical_session_count=10, previous_difficulty="medium"
        )
        self.mock_model_manager.predict.return_value = ModelInferenceResult(
            predicted_difficulty="medium",
            confidence=0.85,
            probabilities={"easy": 0.05, "medium": 0.85, "hard": 0.10},
            meets_confidence_threshold=True,
            confidence_threshold=0.60,
            feature_snapshot=feats,
            model_name="baseline_difficulty_classifier",
        )
        d_s2_ml = self.engine_with_mock.decide(c_s2_ml, feature_record=feats)
        self.assertEqual(d_s2_ml.decision_source, DecisionSource.ML_ADAPTIVE.value)

        # 5. fallback_safe
        self.mock_model_manager.predict.return_value = ModelInferenceResult(
            predicted_difficulty="easy",
            confidence=0.45,
            probabilities={"easy": 0.45, "medium": 0.35, "hard": 0.20},
            meets_confidence_threshold=False,
            confidence_threshold=0.60,
            feature_snapshot=feats,
            model_name="baseline_difficulty_classifier",
        )
        d_fallback = self.engine_with_mock.decide(c_s2_ml, feature_record=feats)
        self.assertEqual(d_fallback.decision_source, DecisionSource.FALLBACK_SAFE.value)

        # 6. guardrail_clamped
        c_clamp = PersonalizationContext(
            user_id=1, wake_session_id=5, challenge_type="math", difficulty_preference="adaptive", historical_session_count=10, previous_difficulty="easy"
        )
        self.mock_model_manager.predict.return_value = ModelInferenceResult(
            predicted_difficulty="hard",
            confidence=0.90,
            probabilities={"easy": 0.02, "medium": 0.08, "hard": 0.90},
            meets_confidence_threshold=True,
            confidence_threshold=0.60,
            feature_snapshot=feats,
            model_name="baseline_difficulty_classifier",
        )
        d_clamp = self.engine_with_mock.decide(c_clamp, feature_record=feats)
        self.assertEqual(d_clamp.decision_source, DecisionSource.GUARDRAIL_CLAMPED.value)

    # 24. PersonalizationEngine.decide supports both instance and classmethod invocation
    def test_instance_and_classmethod_invocations(self):
        """Verify PersonalizationEngine.decide works both as instance method and classmethod."""
        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=60,
            challenge_type="math",
            difficulty_preference="easy",
        )

        # Instance invocation
        engine = PersonalizationEngine()
        d1 = engine.decide(ctx)
        self.assertEqual(d1.recommended_difficulty, "easy")
        self.assertEqual(d1.decision_source, DecisionSource.USER_FIXED.value)

        # Classmethod invocation
        d2 = PersonalizationEngine.decide(ctx)
        self.assertEqual(d2.recommended_difficulty, "easy")
        self.assertEqual(d2.decision_source, DecisionSource.USER_FIXED.value)

    # 25. Input validation and dictionary handling
    def test_context_validation_and_dict_support(self):
        """Verify PersonalizationEngine accepts raw dictionary context and validates fields."""
        valid_dict = {
            "user_id": 1,
            "wake_session_id": 70,
            "challenge_type": "dance",
            "difficulty_preference": "adaptive",
            "historical_session_count": 0,
        }
        decision = PersonalizationEngine.decide(valid_dict)
        self.assertEqual(decision.challenge_type, "dance")
        self.assertEqual(decision.recommended_difficulty, "medium")

        # Invalid challenge type raises ValidationError
        invalid_dict = {
            "user_id": 1,
            "wake_session_id": 71,
            "challenge_type": "invalid_challenge_category",
        }
        with self.assertRaises(ValidationError):
            PersonalizationEngine.decide(invalid_dict)

        # Invalid context type raises ValueError
        with self.assertRaises(ValueError):
            PersonalizationEngine.decide("not_a_context_or_dict")


if __name__ == "__main__":
    unittest.main()
