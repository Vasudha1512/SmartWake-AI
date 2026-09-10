"""Phase 3.5 Focused Test Suite — Cold-Start & Fallback Strategy.

Verifies:
Category A: Fixed user preference precedence (easy, medium, hard bypass ML/fallback/guardrails).
Category B: Stage 0 cold start (0-3 sessions, cognitive vs physical baseline, snooze downgrade).
Category C: Stage 1 cold start (4-7 sessions, recent failure, boundary durations 40.1s/40.0s, 14.9s/15.0s).
Category D: Stage 2 ML & confidence boundaries (0.60 threshold, 0.599 fallback, high/low confidence).
Category E: Model failure modes (ModelNotFoundError, ModelCorruptError, ModelMetadataError, IncompatibleFeatureSchemaError, generic inference error).
Category F: Telemetry distinction (complete vs partial vs unavailable) & zero telemetry fabrication.
Category G: Infrastructure / Database failure diagnostic preservation.
Category H: SafetyGuardrails interaction with fallback candidates (GUARDRAIL_CLAMPED vs FALLBACK_SAFE).
Category I: Product invariants (5 challenge types preserved, alarm time intact, never 'adaptive', forbidden types rejected, zero leakage, runtime integration).
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch
from typing import cast

from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.constants import FORBIDDEN_CHALLENGE_TYPES, VALID_CHALLENGE_TYPES
from backend.app.core.exceptions import InvalidChallengeTypeError, InvalidDifficultyError
from backend.app.database.base import Base
from backend.app.models.alarm import Alarm
from backend.app.models.challenge_attempt import ChallengeAttempt
from backend.app.models.user import User
from backend.app.models.wake_session import WakeSession
from backend.app.schemas.challenge_schemas import (
    ChallengeAttemptStartRequest,
    RuntimeChallengeGenerationRequest,
)
from backend.app.schemas.personalization_schemas import (
    VALID_DIFFICULTY_LEVELS,
    AdaptiveChallengeDecision,
    DecisionSource,
    DifficultyLevel,
    PersonalizationContext,
    PersonalizationDecision,
)
from backend.app.services.adaptive_decision_engine import (
    MODEL_CONFIDENCE_THRESHOLD,
    AdaptiveDecisionEngine,
)
from backend.app.services.challenge_execution_service import (
    generate_challenge,
    start_challenge_attempt,
)
from backend.app.services.model_inference_manager import (
    IncompatibleFeatureSchemaError,
    ModelCorruptError,
    ModelInferenceManager,
    ModelInferenceResult,
    ModelMetadataError,
    ModelNotFoundError,
)
from backend.app.services.personalization_engine import (
    ColdStartRouter,
    PersonalizationEngine,
    SafetyGuardrails,
)
from backend.app.services.wake_session_service import create_wake_session
from backend.app.services.challenge_seed_service import seed_default_challenges
from ml.preprocessing.feature_schema import ChallengeFeatureRecord


def make_valid_feature_dict(challenge_type: str = "math") -> dict:
    """Construct a clean 30-feature dictionary matching baseline model inputs."""
    return {
        "user_total_wake_sessions": 12,
        "user_successful_wake_sessions": 10,
        "user_failed_wake_sessions": 2,
        "user_historical_success_rate": 0.833,
        "user_avg_completion_time_seconds": 18.0,
        "user_avg_attempts_per_session": 1.1,
        "user_avg_snooze_count": 0.5,
        "user_total_snooze_count": 6,
        "user_recent_snooze_count": 1,
        "user_recent_challenge_success_rate": 0.80,
        "challenge_type_total_attempts": 10,
        "challenge_type_successful_attempts": 9,
        "challenge_type_success_rate": 0.90,
        "challenge_type_avg_completion_time": 17.5,
        "challenge_type_recent_success_rate": 0.85,
        "snooze_count_relative_to_user_avg": 0.5,
        "snooze_time_total_minutes": 5.0,
        "current_session_snooze_count": 1,
        "scheduled_alarm_hour": 7,
        "scheduled_alarm_minute": 30,
        "day_of_week": 2,
        "is_weekend": 0,
        "target_delay_minutes": 0.0,
        "actual_wake_hour": 7,
        "actual_wake_minute": 35,
        "alarm_sound_id": 1,
        "alarm_vibration_enabled": 1,
        "alarm_volume_numeric": 80,
        "alarm_snooze_interval_minutes": 5,
        "selected_challenge_type": challenge_type,
    }


# =============================================================================
# CATEGORY A: FIXED USER PREFERENCES
# =============================================================================
class TestCategoryAFixedPreferences(unittest.TestCase):
    """Verify fixed preferences bypass ML, fallback, and guardrails."""

    def setUp(self):
        self.mock_model_manager = MagicMock(spec=ModelInferenceManager)
        self.personalization_engine = PersonalizationEngine(
            model_manager=self.mock_model_manager
        )
        self.decision_engine = AdaptiveDecisionEngine(
            personalization_engine=self.personalization_engine
        )

    def test_fixed_easy_returns_easy_user_fixed(self):
        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=10,
            challenge_type="math",
            difficulty_preference="easy",
            historical_session_count=12,
            previous_difficulty="hard",
        )
        decision = self.decision_engine.decide(ctx)
        self.assertEqual(decision.final_difficulty, "easy")
        self.assertEqual(decision.decision_source, DecisionSource.USER_FIXED.value)
        self.assertFalse(decision.guardrail_applied)
        self.mock_model_manager.predict.assert_not_called()

    def test_fixed_medium_returns_medium_user_fixed(self):
        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=11,
            challenge_type="dance",
            difficulty_preference="medium",
            historical_session_count=20,
            previous_difficulty="hard",
        )
        decision = self.decision_engine.decide(ctx)
        self.assertEqual(decision.final_difficulty, "medium")
        self.assertEqual(decision.decision_source, DecisionSource.USER_FIXED.value)
        self.assertFalse(decision.guardrail_applied)
        self.mock_model_manager.predict.assert_not_called()

    def test_fixed_hard_returns_hard_user_fixed(self):
        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=12,
            challenge_type="memory",
            difficulty_preference="hard",
            historical_session_count=0,
            previous_difficulty=None,
        )
        decision = self.decision_engine.decide(ctx)
        self.assertEqual(decision.final_difficulty, "hard")
        self.assertEqual(decision.decision_source, DecisionSource.USER_FIXED.value)
        self.assertFalse(decision.guardrail_applied)
        self.mock_model_manager.predict.assert_not_called()


# =============================================================================
# CATEGORY B: STAGE 0 COLD START
# =============================================================================
class TestCategoryBStage0ColdStart(unittest.TestCase):
    """Verify Stage 0 routing, heuristics, and boundaries."""

    def test_lifecycle_stage_routing_boundaries(self):
        self.assertEqual(ColdStartRouter.get_stage(0), 0)
        self.assertEqual(ColdStartRouter.get_stage(1), 0)
        self.assertEqual(ColdStartRouter.get_stage(2), 0)
        self.assertEqual(ColdStartRouter.get_stage(3), 0)
        self.assertEqual(ColdStartRouter.get_stage(4), 1)

    def test_cognitive_challenge_defaults_to_easy(self):
        for ctype in ["math", "memory"]:
            diff, reason = ColdStartRouter.evaluate_stage_0(ctype, current_session_snooze_count=0)
            self.assertEqual(diff, "easy")
            self.assertIn("high-cognitive", reason)

    def test_physical_speech_challenge_defaults_to_medium(self):
        for ctype in ["dance", "tongue_twister", "push_ups"]:
            diff, reason = ColdStartRouter.evaluate_stage_0(ctype, current_session_snooze_count=0)
            self.assertEqual(diff, "medium")
            self.assertIn("physical/speech", reason)

    def test_snooze_downgrade_boundary(self):
        # snooze = 1 keeps medium for dance
        diff1, _ = ColdStartRouter.evaluate_stage_0("dance", current_session_snooze_count=1)
        self.assertEqual(diff1, "medium")

        # snooze = 2 downgrades dance to easy
        diff2, reason2 = ColdStartRouter.evaluate_stage_0("dance", current_session_snooze_count=2)
        self.assertEqual(diff2, "easy")
        self.assertIn("snooze count (2 >= 2)", reason2)

        # snooze = 4 downgrades push_ups to easy
        diff4, reason4 = ColdStartRouter.evaluate_stage_0("push_ups", current_session_snooze_count=4)
        self.assertEqual(diff4, "easy")


# =============================================================================
# CATEGORY C: STAGE 1 COLD START
# =============================================================================
class TestCategoryCStage1ColdStart(unittest.TestCase):
    """Verify Stage 1 contextual moving average rules and duration boundaries."""

    def test_stage_1_lifecycle_boundaries(self):
        self.assertEqual(ColdStartRouter.get_stage(4), 1)
        self.assertEqual(ColdStartRouter.get_stage(7), 1)
        self.assertEqual(ColdStartRouter.get_stage(8), 2)

    def test_recent_failure_demotes_to_easy(self):
        diff, reason = ColdStartRouter.evaluate_stage_1(
            baseline_difficulty="hard",
            recent_success_rate=0.9,
            recent_avg_duration_seconds=20.0,
            has_recent_failure=True,
        )
        self.assertEqual(diff, "easy")
        self.assertIn("recent failure", reason)

    def test_duration_boundary_40_demotion(self):
        # 40.0s does NOT demote automatically
        diff_40, _ = ColdStartRouter.evaluate_stage_1(
            baseline_difficulty="medium",
            recent_success_rate=0.8,
            recent_avg_duration_seconds=40.0,
            has_recent_failure=False,
        )
        self.assertEqual(diff_40, "medium")

        # 40.1s DEMOTES to easy
        diff_40_1, reason_40_1 = ColdStartRouter.evaluate_stage_1(
            baseline_difficulty="medium",
            recent_success_rate=0.8,
            recent_avg_duration_seconds=40.1,
            has_recent_failure=False,
        )
        self.assertEqual(diff_40_1, "easy")
        self.assertIn("slow completion time", reason_40_1)

    def test_duration_boundary_15_mastery_promotion(self):
        # 100% success and 15.0s does NOT promote
        diff_15, _ = ColdStartRouter.evaluate_stage_1(
            baseline_difficulty="medium",
            recent_success_rate=1.0,
            recent_avg_duration_seconds=15.0,
            has_recent_failure=False,
        )
        self.assertEqual(diff_15, "medium")

        # 100% success and 14.9s PROMOTES medium -> hard
        diff_14_9, reason_14_9 = ColdStartRouter.evaluate_stage_1(
            baseline_difficulty="medium",
            recent_success_rate=1.0,
            recent_avg_duration_seconds=14.9,
            has_recent_failure=False,
        )
        self.assertEqual(diff_14_9, "hard")
        self.assertIn("promotes baseline 'medium' to 'hard'", reason_14_9)

    def test_mastery_promotion_from_easy_promotes_to_medium(self):
        diff, _ = ColdStartRouter.evaluate_stage_1(
            baseline_difficulty="easy",
            recent_success_rate=1.0,
            recent_avg_duration_seconds=10.0,
            has_recent_failure=False,
        )
        self.assertEqual(diff, "medium")


# =============================================================================
# CATEGORY D: STAGE 2 ML & CONFIDENCE BOUNDARIES
# =============================================================================
class TestCategoryDStage2MLConfidence(unittest.TestCase):
    """Verify confidence threshold (0.60) acceptance and low-confidence fallback."""

    def setUp(self):
        self.mock_model = MagicMock(spec=ModelInferenceManager)
        self.mock_model.confidence_threshold = 0.60
        self.engine = PersonalizationEngine(model_manager=self.mock_model)
        self.decision_engine = AdaptiveDecisionEngine(personalization_engine=self.engine)

    def test_confidence_exactly_point_60_accepted(self):
        feats = make_valid_feature_dict("math")
        self.mock_model.predict.return_value = ModelInferenceResult(
            predicted_difficulty="hard",
            confidence=0.60,
            probabilities={"easy": 0.10, "medium": 0.30, "hard": 0.60},
            meets_confidence_threshold=True,
            confidence_threshold=0.60,
            feature_snapshot=feats,
            model_name="baseline_difficulty_classifier",
        )
        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=20,
            challenge_type="math",
            difficulty_preference="adaptive",
            historical_session_count=10,
            previous_difficulty="medium",
        )
        decision = self.decision_engine.decide(ctx, feature_record=feats)
        self.assertEqual(decision.decision_source, DecisionSource.ML_ADAPTIVE.value)
        self.assertEqual(decision.final_difficulty, "hard")
        self.assertEqual(decision.model_confidence, 0.60)

    def test_confidence_below_point_60_triggers_fallback(self):
        feats = make_valid_feature_dict("math")
        self.mock_model.predict.return_value = ModelInferenceResult(
            predicted_difficulty="hard",
            confidence=0.599,
            probabilities={"easy": 0.20, "medium": 0.201, "hard": 0.599},
            meets_confidence_threshold=False,
            confidence_threshold=0.60,
            feature_snapshot=feats,
            model_name="baseline_difficulty_classifier",
        )
        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=21,
            challenge_type="math",
            difficulty_preference="adaptive",
            historical_session_count=10,
            previous_difficulty="medium",
        )
        decision = self.decision_engine.decide(ctx, feature_record=feats)
        self.assertEqual(decision.decision_source, DecisionSource.FALLBACK_SAFE.value)
        self.assertEqual(decision.final_difficulty, "medium")
        self.assertEqual(decision.model_confidence, 0.599)
        self.assertEqual(decision.raw_model_prediction, "hard")
        self.assertIn("low model confidence", decision.decision_rationale)

    def test_high_confidence_ml_decision(self):
        feats = make_valid_feature_dict("push_ups")
        self.mock_model.predict.return_value = ModelInferenceResult(
            predicted_difficulty="medium",
            confidence=0.88,
            probabilities={"easy": 0.05, "medium": 0.88, "hard": 0.07},
            meets_confidence_threshold=True,
            confidence_threshold=0.60,
            feature_snapshot=feats,
            model_name="baseline_difficulty_classifier",
        )
        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=22,
            challenge_type="push_ups",
            difficulty_preference="adaptive",
            historical_session_count=15,
            previous_difficulty="easy",
        )
        decision = self.decision_engine.decide(ctx, feature_record=feats)
        self.assertEqual(decision.decision_source, DecisionSource.ML_ADAPTIVE.value)
        self.assertEqual(decision.final_difficulty, "medium")
        self.assertEqual(decision.model_confidence, 0.88)


# =============================================================================
# CATEGORY E: MODEL FAILURE MODES
# =============================================================================
class TestCategoryEModelFailureModes(unittest.TestCase):
    """Verify robust defensive fallback across all ML failure modes."""

    def setUp(self):
        self.mock_model = MagicMock(spec=ModelInferenceManager)
        self.mock_model.confidence_threshold = 0.60
        self.engine = PersonalizationEngine(model_manager=self.mock_model)
        self.decision_engine = AdaptiveDecisionEngine(personalization_engine=self.engine)
        self.ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=30,
            challenge_type="dance",
            difficulty_preference="adaptive",
            historical_session_count=10,
            previous_difficulty="medium",
        )
        self.feats = make_valid_feature_dict("dance")

    def _assert_safe_fallback(self, decision, expected_error_type: str):
        self.assertEqual(decision.decision_source, DecisionSource.FALLBACK_SAFE.value)
        self.assertIn(decision.final_difficulty, VALID_DIFFICULTY_LEVELS)
        self.assertIn(expected_error_type, decision.decision_rationale)
        self.assertEqual(
            decision.feature_snapshot.get("ml_error_type"), expected_error_type
        )

    def test_model_not_found_error_safe_fallback(self):
        self.mock_model.predict.side_effect = ModelNotFoundError("Artifact missing: /models/clf.joblib")
        decision = self.decision_engine.decide(self.ctx, feature_record=self.feats)
        self._assert_safe_fallback(decision, "ModelNotFoundError")

    def test_model_corrupt_error_safe_fallback(self):
        self.mock_model.predict.side_effect = ModelCorruptError("Invalid pickle byte sequence")
        decision = self.decision_engine.decide(self.ctx, feature_record=self.feats)
        self._assert_safe_fallback(decision, "ModelCorruptError")

    def test_model_metadata_error_safe_fallback(self):
        self.mock_model.predict.side_effect = ModelMetadataError("Malformed metadata JSON schema")
        decision = self.decision_engine.decide(self.ctx, feature_record=self.feats)
        self._assert_safe_fallback(decision, "ModelMetadataError")

    def test_incompatible_feature_schema_error_safe_fallback(self):
        self.mock_model.predict.side_effect = IncompatibleFeatureSchemaError("Missing feature: snooze_time")
        decision = self.decision_engine.decide(self.ctx, feature_record=self.feats)
        self._assert_safe_fallback(decision, "IncompatibleFeatureSchemaError")

    def test_generic_inference_exception_safe_fallback(self):
        self.mock_model.predict.side_effect = RuntimeError("GPU memory allocation failure")
        decision = self.decision_engine.decide(self.ctx, feature_record=self.feats)
        self._assert_safe_fallback(decision, "RuntimeError")

    def test_malformed_model_output_tier_safe_fallback(self):
        # Model returns an invalid tier string like 'ultra_hard'
        self.mock_model.predict.return_value = ModelInferenceResult(
            predicted_difficulty="ultra_hard",
            confidence=0.95,
            probabilities={"easy": 0.05, "medium": 0.0, "hard": 0.0},
            meets_confidence_threshold=True,
            confidence_threshold=0.60,
            feature_snapshot=self.feats,
            model_name="baseline_difficulty_classifier",
        )
        decision = self.decision_engine.decide(self.ctx, feature_record=self.feats)
        self._assert_safe_fallback(decision, "ValueError")


# =============================================================================
# CATEGORY F: TELEMETRY DISTINCTION & ZERO FABRICATION
# =============================================================================
class TestCategoryFTelemetryDistinction(unittest.TestCase):
    """Verify distinct handling of complete, partial, and unavailable telemetry with zero fabrication."""

    def test_partial_telemetry_failure_demotes_to_easy(self):
        # Only has_recent_failure=True, no duration or success rate
        diff, reason = ColdStartRouter.evaluate_safe_fallback(
            challenge_type="math",
            baseline_difficulty="hard",
            recent_success_rate=None,
            recent_avg_duration_seconds=None,
            has_recent_failure=True,
            current_session_snooze_count=0,
        )
        self.assertEqual(diff, "easy")
        self.assertIn("recent failure", reason)

    def test_partial_telemetry_slow_duration_demotes_to_easy(self):
        # Only slow duration, no success rate
        diff, reason = ColdStartRouter.evaluate_safe_fallback(
            challenge_type="math",
            baseline_difficulty="medium",
            recent_success_rate=None,
            recent_avg_duration_seconds=45.0,
            has_recent_failure=False,
            current_session_snooze_count=0,
        )
        self.assertEqual(diff, "easy")
        self.assertIn("slow completion time", reason)

    def test_partial_telemetry_missing_duration_never_promotes(self):
        # Success rate 100%, but duration is None (never fabricate duration < 15s)
        diff, reason = ColdStartRouter.evaluate_safe_fallback(
            challenge_type="dance",
            baseline_difficulty="medium",
            recent_success_rate=1.0,
            recent_avg_duration_seconds=None,
            has_recent_failure=False,
            current_session_snooze_count=0,
        )
        self.assertEqual(diff, "medium")
        self.assertNotIn("promotes", reason)

    def test_partial_telemetry_missing_success_rate_never_promotes(self):
        # Fast duration 12.0s, but success rate is None (never fabricate success rate == 1.0)
        diff, reason = ColdStartRouter.evaluate_safe_fallback(
            challenge_type="dance",
            baseline_difficulty="medium",
            recent_success_rate=None,
            recent_avg_duration_seconds=12.0,
            has_recent_failure=False,
            current_session_snooze_count=0,
        )
        self.assertEqual(diff, "medium")
        self.assertNotIn("promotes", reason)

    def test_complete_telemetry_mastery_promotes(self):
        # Both success rate and duration present
        diff, reason = ColdStartRouter.evaluate_safe_fallback(
            challenge_type="math",
            baseline_difficulty="medium",
            recent_success_rate=1.0,
            recent_avg_duration_seconds=12.0,
            has_recent_failure=False,
            current_session_snooze_count=0,
        )
        self.assertEqual(diff, "hard")
        self.assertIn("promotes", reason)

    def test_unavailable_telemetry_with_medium_baseline_defaults_to_medium(self):
        diff, reason = ColdStartRouter.evaluate_safe_fallback(
            challenge_type="math",
            baseline_difficulty="medium",
            recent_success_rate=None,
            recent_avg_duration_seconds=None,
            has_recent_failure=False,
            current_session_snooze_count=0,
        )
        self.assertEqual(diff, "medium")
        self.assertIn("telemetry unavailable", reason)

    def test_unavailable_telemetry_with_easy_baseline_defaults_to_easy(self):
        diff, reason = ColdStartRouter.evaluate_safe_fallback(
            challenge_type="math",
            baseline_difficulty="easy",
            recent_success_rate=None,
            recent_avg_duration_seconds=None,
            has_recent_failure=False,
            current_session_snooze_count=0,
        )
        self.assertEqual(diff, "easy")
        self.assertIn("telemetry unavailable", reason)

    def test_unavailable_telemetry_without_baseline_uses_stage_0_cognitive_baseline(self):
        # Baseline is None -> math defaults to easy
        diff, reason = ColdStartRouter.evaluate_safe_fallback(
            challenge_type="math",
            baseline_difficulty=None,
            recent_success_rate=None,
            recent_avg_duration_seconds=None,
            has_recent_failure=False,
            current_session_snooze_count=0,
        )
        self.assertEqual(diff, "easy")
        self.assertIn("high-cognitive challenge 'math' defaults to 'easy'", reason)

    def test_unavailable_telemetry_without_baseline_uses_stage_0_physical_baseline(self):
        # Baseline is None -> dance defaults to medium
        diff, reason = ColdStartRouter.evaluate_safe_fallback(
            challenge_type="dance",
            baseline_difficulty=None,
            recent_success_rate=None,
            recent_avg_duration_seconds=None,
            has_recent_failure=False,
            current_session_snooze_count=0,
        )
        self.assertEqual(diff, "medium")
        self.assertIn("physical/speech challenge 'dance' defaults to 'medium'", reason)

    def test_unavailable_telemetry_snooze_downgrade(self):
        # Snooze >= 2 with unavailable telemetry defaults to easy
        diff, reason = ColdStartRouter.evaluate_safe_fallback(
            challenge_type="dance",
            baseline_difficulty="medium",
            recent_success_rate=None,
            recent_avg_duration_seconds=None,
            has_recent_failure=False,
            current_session_snooze_count=2,
        )
        self.assertEqual(diff, "easy")
        self.assertIn("snooze count (2 >= 2)", reason)


# =============================================================================
# CATEGORY G: INFRASTRUCTURE / DATABASE FAILURES & DIAGNOSTIC PRESERVATION
# =============================================================================
class TestCategoryGInfrastructureFailures(unittest.TestCase):
    """Verify database/feature extraction errors preserve diagnostics without fabricating data."""

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cls.engine)
        Base.metadata.create_all(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=cls.engine)
        cls.engine.dispose()

    def setUp(self):
        with self.SessionLocal() as session:
            for table in reversed(Base.metadata.sorted_tables):
                session.execute(table.delete())
            session.commit()
            seed_default_challenges(session)

            user = User(username="alice", email="alice@example.com")
            session.add(user)
            session.commit()
            session.refresh(user)
            self.user_id = cast(int, user.id)

            alarm = Alarm(
                user_id=self.user_id,
                time="07:00",
                days_of_week="[0,1,2,3,4]",
                selected_challenge_type="math",
                difficulty_preference="adaptive",
                is_active=True,
            )
            session.add(alarm)
            session.commit()
            session.refresh(alarm)
            self.alarm_id = cast(int, alarm.id)

    def test_database_query_error_preserves_diagnostics_as_fallback_safe(self):
        with self.SessionLocal() as db:
            wake_session = create_wake_session(
                db=db,
                user_id=self.user_id,
                alarm_id=self.alarm_id,
            )

            # Mock db.scalars to simulate database crash
            mock_db = MagicMock(spec=db)
            mock_db.scalars.side_effect = RuntimeError("Database connection timeout")

            decision = AdaptiveDecisionEngine.decide_for_session(
                db=mock_db,
                wake_session=wake_session,
                challenge_type="math",
                difficulty_preference="adaptive",
            )

            self.assertEqual(decision.decision_source, DecisionSource.FALLBACK_SAFE.value)
            self.assertIn(decision.final_difficulty, VALID_DIFFICULTY_LEVELS)
            self.assertEqual(
                decision.feature_snapshot.get("infrastructure_error_type"), "RuntimeError"
            )
            self.assertIsNotNone(decision.decision_rationale)
            self.assertIn("Database connection timeout", decision.decision_rationale or "")
            # Must NOT be treated as user failure (it's infrastructure)
            self.assertNotIn("recent failure", decision.decision_rationale or "")

    def test_feature_extraction_failure_preserves_diagnostics(self):
        with self.SessionLocal() as db:
            wake_session = create_wake_session(
                db=db,
                user_id=self.user_id,
                alarm_id=self.alarm_id,
            )

            # Create 8 prior sessions so Stage 2 is entered
            for i in range(8):
                prior_s = WakeSession(
                    user_id=self.user_id,
                    alarm_id=self.alarm_id,
                    scheduled_time=datetime(2026, 1, i + 1, 7, 0, tzinfo=timezone.utc),
                    initial_ring_time=datetime(2026, 1, i + 1, 7, 0, tzinfo=timezone.utc),
                    status="completed",
                )
                db.add(prior_s)
            db.commit()

            with patch(
                "backend.app.services.adaptive_decision_engine.extract_features_for_session_context",
                side_effect=ValueError("Feature calculation division by zero"),
            ):
                decision = AdaptiveDecisionEngine.decide_for_session(
                    db=db,
                    wake_session=wake_session,
                    challenge_type="dance",
                    difficulty_preference="adaptive",
                )

                self.assertEqual(decision.decision_source, DecisionSource.FALLBACK_SAFE.value)
                self.assertIn(decision.final_difficulty, VALID_DIFFICULTY_LEVELS)
                self.assertEqual(
                    decision.feature_snapshot.get("infrastructure_error_type"), "ValueError"
                )
                self.assertIsNotNone(decision.decision_rationale)
                self.assertIn("Feature calculation division by zero", decision.decision_rationale or "")

    def test_runtime_boundary_unexpected_exception_preserves_diagnostics(self):
        mock_pe = MagicMock(spec=PersonalizationEngine)
        mock_pe.decide.side_effect = MemoryError("Out of memory in matrix dot product")

        ade = AdaptiveDecisionEngine(personalization_engine=mock_pe)
        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=55,
            challenge_type="math",
            difficulty_preference="adaptive",
            historical_session_count=10,
            previous_difficulty="medium",
        )
        decision = ade.decide(ctx)
        self.assertEqual(decision.decision_source, DecisionSource.FALLBACK_SAFE.value)
        self.assertEqual(decision.final_difficulty, "medium")
        self.assertEqual(decision.feature_snapshot.get("runtime_error_type"), "MemoryError")
        self.assertIsNotNone(decision.decision_rationale)
        self.assertIn("Out of memory", decision.decision_rationale or "")


# =============================================================================
# CATEGORY H: SAFETY GUARDRAIL CLAMPING ON FALLBACKS
# =============================================================================
class TestCategoryHSafetyGuardrailClamping(unittest.TestCase):
    """Verify decision source accurately reflects GUARDRAIL_CLAMPED vs FALLBACK_SAFE."""

    def setUp(self):
        self.mock_model = MagicMock(spec=ModelInferenceManager)
        self.mock_model.confidence_threshold = 0.60
        self.engine = PersonalizationEngine(model_manager=self.mock_model)
        self.decision_engine = AdaptiveDecisionEngine(personalization_engine=self.engine)

    def test_fallback_unclamped_remains_fallback_safe(self):
        # Fallback resolves to 'medium', previous was 'medium' -> no clamp
        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=40,
            challenge_type="dance",
            difficulty_preference="adaptive",
            historical_session_count=10,
            previous_difficulty="medium",
            current_session_snooze_count=0,
        )
        self.mock_model.predict.side_effect = ModelNotFoundError("Model missing")
        decision = self.decision_engine.decide(ctx, feature_record=make_valid_feature_dict("dance"))
        self.assertEqual(decision.decision_source, DecisionSource.FALLBACK_SAFE.value)
        self.assertEqual(decision.final_difficulty, "medium")
        self.assertFalse(decision.guardrail_applied)

    def test_fallback_clamped_by_snooze_sleep_inertia_becomes_guardrail_clamped(self):
        # Stage 1 mastery rule promotes medium -> hard, but snooze count >= 3 caps hard to medium
        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=41,
            challenge_type="dance",
            difficulty_preference="adaptive",
            historical_session_count=10,
            previous_difficulty="medium",
            current_session_snooze_count=3,
        )
        self.mock_model.predict.side_effect = ModelNotFoundError("Model missing")
        # Provide telemetry that would produce 'hard'
        decision = self.decision_engine.decide(
            ctx,
            feature_record=make_valid_feature_dict("dance"),
            recent_success_rate=1.0,
            recent_avg_duration_seconds=12.0,
        )
        self.assertEqual(decision.decision_source, DecisionSource.GUARDRAIL_CLAMPED.value)
        self.assertEqual(decision.final_difficulty, "medium")
        self.assertTrue(decision.guardrail_applied)
        self.assertIn("Sleep inertia floor applied", decision.guardrail_reason)

    def test_fallback_clamped_by_step_shift_becomes_guardrail_clamped(self):
        # Fallback resolves to 'easy' due to failure, but previous difficulty is 'hard' (-2 steps)
        decision = self.decision_engine.decide(
            context=PersonalizationContext(
                user_id=1,
                wake_session_id=43,
                challenge_type="dance",
                difficulty_preference="adaptive",
                historical_session_count=10,
                previous_difficulty="hard",
                current_session_snooze_count=0,
            ),
            feature_record=make_valid_feature_dict("dance"),
            has_recent_failure=True,  # demotes to 'easy', but previous was 'hard' (-2 steps -> clamped to medium)
        )
        self.assertEqual(decision.decision_source, DecisionSource.GUARDRAIL_CLAMPED.value)
        self.assertEqual(decision.final_difficulty, "medium")
        self.assertTrue(decision.guardrail_applied)
        self.assertIn("Maximum step shift clamped", decision.guardrail_reason)


# =============================================================================
# CATEGORY I: PRODUCT INVARIANTS & RUNTIME INTEGRATION
# =============================================================================
class TestCategoryIProductInvariantsAndIntegration(unittest.TestCase):
    """Verify all product invariants and end-to-end challenge execution integration."""

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cls.engine)
        Base.metadata.create_all(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=cls.engine)
        cls.engine.dispose()

    def setUp(self):
        with self.SessionLocal() as session:
            for table in reversed(Base.metadata.sorted_tables):
                session.execute(table.delete())
            session.commit()
            seed_default_challenges(session)

            user = User(username="bob", email="bob@example.com")
            session.add(user)
            session.commit()
            session.refresh(user)
            self.user_id = cast(int, user.id)

            alarm = Alarm(
                user_id=self.user_id,
                time="06:45",
                days_of_week="[0,1,2,3,4]",
                selected_challenge_type="tongue_twister",
                difficulty_preference="adaptive",
                is_active=True,
            )
            session.add(alarm)
            session.commit()
            session.refresh(alarm)
            self.alarm_id = cast(int, alarm.id)

    def test_five_canonical_challenge_types_preserved_across_fallbacks(self):
        for ctype in VALID_CHALLENGE_TYPES:
            ctx = PersonalizationContext(
                user_id=self.user_id,
                wake_session_id=50,
                challenge_type=ctype,
                difficulty_preference="adaptive",
                historical_session_count=0,
            )
            decision = AdaptiveDecisionEngine.decide(context=ctx)
            self.assertEqual(decision.challenge_type, ctype)
            self.assertIn(decision.final_difficulty, VALID_DIFFICULTY_LEVELS)
            self.assertNotEqual(decision.final_difficulty, "adaptive")

    def test_alarm_scheduled_time_never_modified_by_decision(self):
        with self.SessionLocal() as db:
            wake_session = create_wake_session(
                db=db,
                user_id=self.user_id,
                alarm_id=self.alarm_id,
            )
            orig_scheduled = wake_session.scheduled_time

            decision = AdaptiveDecisionEngine.decide_for_session(
                db=db,
                wake_session=wake_session,
                challenge_type="tongue_twister",
                difficulty_preference="adaptive",
            )

            # Scheduled time on session must remain completely intact
            self.assertEqual(wake_session.scheduled_time, orig_scheduled)
            self.assertEqual(decision.challenge_type, "tongue_twister")

    def test_forbidden_challenge_types_rejected(self):
        for ftype in FORBIDDEN_CHALLENGE_TYPES:
            with self.assertRaises((InvalidChallengeTypeError, ValidationError, ValueError)):
                PersonalizationContext(
                    user_id=self.user_id,
                    wake_session_id=51,
                    challenge_type=ftype,
                    difficulty_preference="adaptive",
                )

    def test_end_to_end_fallback_difficulty_reaches_runtime_generator(self):
        with self.SessionLocal() as db:
            wake_session = create_wake_session(
                db=db,
                user_id=self.user_id,
                alarm_id=self.alarm_id,
            )

            # Start challenge attempt with adaptive mode under cold start
            req = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=cast(int, wake_session.id),
            )
            attempt = start_challenge_attempt(
                db=db,
                request=req,
            )

            # Verification of runtime execution artifacts
            self.assertEqual(attempt.challenge_type, "tongue_twister")
            # For tongue_twister in Stage 0, default is 'medium'
            self.assertEqual(attempt.difficulty_level, "medium")
            self.assertEqual(attempt.attempt_number, 1)

            # Verify persisted attempt in database
            fetched = db.get(ChallengeAttempt, attempt.id)
            self.assertIsNotNone(fetched)
            self.assertEqual(fetched.challenge_type, "tongue_twister")
            self.assertEqual(fetched.difficulty_level, "medium")

            # Verify prompt content has concrete difficulty and never 'adaptive'
            payload = json.loads(fetched.prompt_content)
            self.assertEqual(payload["difficulty_level"], "medium")
            self.assertNotEqual(payload["difficulty_level"], "adaptive")


if __name__ == "__main__":
    unittest.main()
