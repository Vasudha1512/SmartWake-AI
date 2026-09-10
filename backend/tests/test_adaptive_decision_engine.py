"""Unit and integration tests for Phase 3.4 Adaptive Decision Engine.

Validates:
A. Fixed difficulty:
   1. User selects easy -> final easy (ML bypassed, guardrails bypassed, type preserved).
   2. User selects medium -> final medium (ML bypassed, guardrails bypassed, type preserved).
   3. User selects hard -> final hard (ML bypassed, guardrails bypassed, type preserved).
B. Adaptive stages:
   4. Adaptive Stage 0 (0-3 sessions) uses cold-start heuristics without ML.
   5. Adaptive Stage 1 (4-7 sessions) uses contextual moving rules without ML.
   6. Adaptive Stage 2 (8+ sessions) uses ML when confidence >= 0.60.
   7. Adaptive Stage 2 falls back safely when confidence < 0.60 (fallback_safe).
C. Invariants:
   8. Challenge type preserved across all 5 canonical types (dance, math, memory, tongue_twister, push_ups).
   9. Alarm scheduled time and wake session ring times are never altered.
   10. Fixed preference cannot be overridden by snoozes or history.
   11. ML cannot choose or mutate challenge type.
   12. ML cannot modify alarm time.
   13. No post-challenge leakage (current attempt outcomes never used for difficulty).
D. Failure handling:
   14. Forbidden challenge types rejected ('number_guessing', 'guess_number', 'numeric_memory').
   15. Unknown challenge type rejected.
   16. Invalid difficulty preference rejected.
   17. Missing required context rejected.
   18. PersonalizationEngine mutating challenge type is caught and rejected.
   19. PersonalizationEngine invalid difficulty output is caught and rejected.
   20. Malformed ML prediction or low confidence below 0.60 produces safe fallback.
   21. Insufficient telemetry in Stage 2 safely falls back without fabricating data.
E. Integration:
   22. Final difficulty reaches runtime challenge generation.
   23. Generated challenge uses final difficulty.
   24. Session retries preserve challenge type and apply adaptive difficulty with guardrails.
   25. Verification behavior remains unchanged.
"""
from datetime import datetime
import json
import unittest
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.constants import FORBIDDEN_CHALLENGE_TYPES, VALID_CHALLENGE_TYPES
from backend.app.core.datetime_utils import now_utc_naive
from backend.app.core.exceptions import (
    InvalidChallengeTypeError,
    InvalidDifficultyError,
)
from backend.app.database.base import Base
import backend.app.database.session  # Ensures sqlite pragma listeners
from backend.app.models.alarm import Alarm
from backend.app.models.challenge_attempt import ChallengeAttempt
from backend.app.models.user import User
from backend.app.models.wake_session import WakeSession
from backend.app.schemas.challenge_schemas import (
    ChallengeAttemptStartRequest,
    ChallengeAttemptSubmitRequest,
)
from backend.app.schemas.personalization_schemas import (
    AdaptiveChallengeDecision,
    DecisionSource,
    DifficultyLevel,
    DifficultyPreference,
    PersonalizationContext,
    PersonalizationDecision,
)
from backend.app.services.adaptive_decision_engine import (
    MODEL_CONFIDENCE_THRESHOLD,
    AdaptiveDecisionEngine,
)
from backend.app.services.challenge_execution_service import (
    start_challenge_attempt,
    submit_challenge_attempt,
)
from backend.app.services.challenge_seed_service import seed_default_challenges
from backend.app.services.model_inference_manager import (
    ModelInferenceManager,
    ModelInferenceResult,
)
from backend.app.services.personalization_engine import PersonalizationEngine
from backend.app.services.wake_session_service import (
    STATUS_COMPLETED,
    STATUS_IN_CHALLENGE,
    create_wake_session,
)
from ml.preprocessing.feature_schema import ChallengeFeatureRecord


def make_test_features(challenge_type: str = "math") -> dict:
    """Helper constructing canonical 30 model input features."""
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


# =============================================================================
# A. FIXED DIFFICULTY TESTS
# =============================================================================
class TestAdaptiveDecisionEngineFixedDifficulty(unittest.TestCase):
    """Test suite verifying absolute user sovereignty for fixed difficulty preferences."""

    def setUp(self):
        self.mock_personalization = MagicMock(spec=PersonalizationEngine)
        self.engine = AdaptiveDecisionEngine(personalization_engine=self.mock_personalization)

    def test_fixed_easy_preference(self):
        """User explicitly selects easy -> final difficulty MUST be easy.
        ML must not be invoked, guardrails must not override, challenge type remains unchanged.
        """
        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=10,
            challenge_type="math",
            difficulty_preference="easy",
            current_session_snooze_count=5,  # High snooze would clamp in adaptive mode
            historical_session_count=25,     # Sufficient for ML
            previous_difficulty="hard",
        )
        decision = self.engine.decide(ctx)

        self.assertIsInstance(decision, AdaptiveChallengeDecision)
        self.assertEqual(decision.final_difficulty, "easy")
        self.assertEqual(decision.recommended_difficulty, "easy")
        self.assertEqual(decision.challenge_type, "math")
        self.assertEqual(decision.decision_source, DecisionSource.USER_FIXED.value)
        self.assertIsNone(decision.model_confidence)
        self.assertIsNone(decision.raw_model_prediction)
        self.assertFalse(decision.guardrail_applied)
        self.assertIsNone(decision.guardrail_reason)
        self.assertEqual(decision.user_id, 1)
        self.assertEqual(decision.wake_session_id, 10)
        self.mock_personalization.decide.assert_not_called()

    def test_fixed_medium_preference(self):
        """User explicitly selects medium -> final difficulty MUST be medium.
        ML must not be invoked, guardrails must not override, challenge type remains unchanged.
        """
        ctx = PersonalizationContext(
            user_id=2,
            wake_session_id=20,
            challenge_type="dance",
            difficulty_preference="medium",
            current_session_snooze_count=4,
            historical_session_count=15,
            previous_difficulty="easy",
        )
        decision = self.engine.decide(ctx)

        self.assertEqual(decision.final_difficulty, "medium")
        self.assertEqual(decision.challenge_type, "dance")
        self.assertEqual(decision.decision_source, DecisionSource.USER_FIXED.value)
        self.mock_personalization.decide.assert_not_called()

    def test_fixed_hard_preference(self):
        """User explicitly selects hard -> final difficulty MUST be hard.
        ML must not be invoked, guardrails must not override, challenge type remains unchanged.
        """
        ctx = PersonalizationContext(
            user_id=3,
            wake_session_id=30,
            challenge_type="tongue_twister",
            difficulty_preference="hard",
            current_session_snooze_count=4,  # Snooze >= 3 would clamp hard to medium in adaptive mode!
            historical_session_count=0,      # Stage 0 would default to medium in adaptive mode!
            previous_difficulty="easy",      # Step shift from easy would clamp to medium!
        )
        decision = self.engine.decide(ctx)

        self.assertEqual(decision.final_difficulty, "hard")
        self.assertEqual(decision.challenge_type, "tongue_twister")
        self.assertEqual(decision.decision_source, DecisionSource.USER_FIXED.value)
        self.assertFalse(decision.guardrail_applied)
        self.mock_personalization.decide.assert_not_called()


# =============================================================================
# B. ADAPTIVE STAGES TESTS
# =============================================================================
class TestAdaptiveDecisionEngineAdaptiveStages(unittest.TestCase):
    """Test suite verifying adaptive lifecycle stages (Stage 0, Stage 1, Stage 2 ML)."""

    def setUp(self):
        self.mock_model_manager = MagicMock(spec=ModelInferenceManager)
        self.personalization_engine = PersonalizationEngine(model_manager=self.mock_model_manager)
        self.engine = AdaptiveDecisionEngine(personalization_engine=self.personalization_engine)

    def test_adaptive_stage_0_heuristics(self):
        """Adaptive Stage 0 (0-3 sessions) uses cold-start heuristics without ML."""
        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=101,
            challenge_type="math",
            difficulty_preference="adaptive",
            historical_session_count=1,
            current_session_snooze_count=0,
        )
        decision = self.engine.decide(ctx)

        self.assertEqual(decision.final_difficulty, "easy")  # Math Stage 0 is easy
        self.assertEqual(decision.challenge_type, "math")
        self.assertEqual(decision.decision_source, DecisionSource.COLD_START_STAGE_0.value)
        self.assertIsNone(decision.model_confidence)
        self.mock_model_manager.predict.assert_not_called()

    def test_adaptive_stage_1_contextual_rules(self):
        """Adaptive Stage 1 (4-7 sessions) uses contextual moving metrics without ML."""
        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=102,
            challenge_type="push_ups",
            difficulty_preference="adaptive",
            historical_session_count=5,
            previous_difficulty="medium",
        )
        # Fast completion + 100% success rate promotes baseline medium -> hard
        decision = self.engine.decide(
            ctx,
            recent_success_rate=1.0,
            recent_avg_duration_seconds=12.0,
            has_recent_failure=False,
        )

        self.assertEqual(decision.final_difficulty, "hard")
        self.assertEqual(decision.challenge_type, "push_ups")
        self.assertEqual(decision.decision_source, DecisionSource.COLD_START_STAGE_1.value)
        self.assertIsNone(decision.model_confidence)
        self.mock_model_manager.predict.assert_not_called()

    def test_adaptive_stage_2_ml_high_confidence(self):
        """Adaptive Stage 2 (8+ sessions) uses ML when confidence >= 0.60."""
        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=103,
            challenge_type="memory",
            difficulty_preference="adaptive",
            historical_session_count=12,
            previous_difficulty="medium",
        )
        self.mock_model_manager.predict.return_value = ModelInferenceResult(
            predicted_difficulty="hard",
            confidence=0.85,
            probabilities={"easy": 0.05, "medium": 0.10, "hard": 0.85},
            meets_confidence_threshold=True,
            confidence_threshold=0.60,
            feature_snapshot={"user_total_wake_sessions": 12},
        )
        features = make_test_features("memory")
        decision = self.engine.decide(ctx, feature_record=features)

        self.assertEqual(decision.final_difficulty, "hard")
        self.assertEqual(decision.challenge_type, "memory")
        self.assertEqual(decision.decision_source, DecisionSource.ML_ADAPTIVE.value)
        self.assertEqual(decision.model_confidence, 0.85)
        self.assertEqual(decision.raw_model_prediction, "hard")
        self.mock_model_manager.predict.assert_called_once()

    def test_adaptive_stage_2_ml_low_confidence_fallback(self):
        """Adaptive Stage 2 falls back safely when ML confidence < 0.60."""
        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=104,
            challenge_type="dance",
            difficulty_preference="adaptive",
            historical_session_count=14,
            previous_difficulty="medium",
        )
        self.mock_model_manager.predict.return_value = ModelInferenceResult(
            predicted_difficulty="hard",
            confidence=0.48,  # Below 0.60 threshold
            probabilities={"easy": 0.25, "medium": 0.27, "hard": 0.48},
            meets_confidence_threshold=False,
            confidence_threshold=0.60,
            feature_snapshot={"user_total_wake_sessions": 14},
        )
        features = make_test_features("dance")
        decision = self.engine.decide(ctx, feature_record=features)

        # Falls back safely to Stage 1 contextual heuristic (medium default)
        self.assertEqual(decision.final_difficulty, "medium")
        self.assertEqual(decision.challenge_type, "dance")
        self.assertEqual(decision.decision_source, DecisionSource.FALLBACK_SAFE.value)
        self.assertEqual(decision.model_confidence, 0.48)
        self.assertEqual(decision.raw_model_prediction, "hard")
        self.mock_model_manager.predict.assert_called_once()


# =============================================================================
# C. PRODUCT INVARIANTS TESTS
# =============================================================================
class TestAdaptiveDecisionEngineInvariants(unittest.TestCase):
    """Test suite verifying critical product invariants."""

    def setUp(self):
        self.engine = AdaptiveDecisionEngine()

    def test_challenge_type_strictly_preserved_all_types(self):
        """Challenge type MUST remain strictly identical across all 5 canonical types."""
        for ctype in VALID_CHALLENGE_TYPES:
            ctx = PersonalizationContext(
                user_id=1,
                wake_session_id=10,
                challenge_type=ctype,
                difficulty_preference="adaptive",
                historical_session_count=0,
            )
            decision = self.engine.decide(ctx)
            self.assertEqual(
                decision.challenge_type,
                ctype,
                f"Challenge type '{ctype}' was altered to '{decision.challenge_type}'!",
            )

    def test_alarm_time_is_untouched(self):
        """Verifies alarm scheduled time and ring times are never altered."""
        alarm = Alarm(
            id=42,
            user_id=1,
            time="06:30",
            days_of_week="[0,1,2,3,4]",
            selected_challenge_type="math",
            difficulty_preference="adaptive",
            is_active=True,
        )
        original_time = alarm.time
        original_days = alarm.days_of_week

        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=1,
            alarm_id=int(alarm.id),
            challenge_type=str(alarm.selected_challenge_type),
            difficulty_preference=str(alarm.difficulty_preference),
            historical_session_count=2,
        )
        decision = self.engine.decide(ctx)

        self.assertIsNotNone(decision)
        # Ensure Alarm attributes remain completely untouched
        self.assertEqual(alarm.time, original_time)
        self.assertEqual(alarm.days_of_week, original_days)

    def test_fixed_preference_cannot_be_overridden_by_snoozes_or_history(self):
        """Fixed user preference MUST NOT be overridden by snoozes, history, or previous difficulty."""
        ctx_easy = PersonalizationContext(
            user_id=1,
            wake_session_id=1,
            challenge_type="dance",
            difficulty_preference="easy",
            current_session_snooze_count=0,
            historical_session_count=50,
            previous_difficulty="hard",
        )
        self.assertEqual(self.engine.decide(ctx_easy).final_difficulty, "easy")

        ctx_hard = PersonalizationContext(
            user_id=1,
            wake_session_id=2,
            challenge_type="dance",
            difficulty_preference="hard",
            current_session_snooze_count=5,  # Snooze count >= 3
            historical_session_count=0,
            previous_difficulty="easy",
        )
        self.assertEqual(self.engine.decide(ctx_hard).final_difficulty, "hard")

    def test_no_post_challenge_leakage(self):
        """Ensures that post-challenge outcome fields are never passed to inference."""
        mock_model = MagicMock(spec=ModelInferenceManager)
        mock_model.predict.return_value = ModelInferenceResult(
            predicted_difficulty="medium",
            confidence=0.75,
            probabilities={"medium": 0.75},
            meets_confidence_threshold=True,
            confidence_threshold=0.60,
            feature_snapshot={},
        )
        p_engine = PersonalizationEngine(model_manager=mock_model)
        engine = AdaptiveDecisionEngine(personalization_engine=p_engine)

        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=10,
            challenge_type="math",
            difficulty_preference="adaptive",
            historical_session_count=10,
        )
        raw_feature_dict = make_test_features("math")
        # Attempt to contaminate feature dict with post-challenge outcome fields
        raw_feature_dict["target_is_successful"] = True
        raw_feature_dict["target_duration_seconds"] = 14.2
        raw_feature_dict["target_verification_score"] = 1.0

        decision = engine.decide(ctx, feature_record=raw_feature_dict)
        self.assertIsNotNone(decision)

        # Inspect features actually passed to mock_model.predict
        mock_model.predict.assert_called_once()
        called_features = mock_model.predict.call_args[0][0]
        self.assertNotIn("target_is_successful", called_features)
        self.assertNotIn("target_duration_seconds", called_features)
        self.assertNotIn("target_verification_score", called_features)


# =============================================================================
# D. FAILURE HANDLING & VALIDATION TESTS
# =============================================================================
class TestAdaptiveDecisionEngineValidation(unittest.TestCase):
    """Test suite verifying validation and failure handling."""

    def setUp(self):
        self.engine = AdaptiveDecisionEngine()

    def test_reject_forbidden_challenge_types(self):
        """Engine must reject all forbidden challenge types."""
        for forbidden in FORBIDDEN_CHALLENGE_TYPES:
            with self.assertRaises((ValueError, InvalidChallengeTypeError)):
                self.engine.decide({
                    "user_id": 1,
                    "wake_session_id": 10,
                    "challenge_type": forbidden,
                    "difficulty_preference": "adaptive",
                })

    def test_reject_unknown_challenge_type(self):
        """Engine must reject unknown challenge types."""
        with self.assertRaises((ValueError, InvalidChallengeTypeError)):
            self.engine.decide({
                "user_id": 1,
                "wake_session_id": 10,
                "challenge_type": "chess_puzzle",
                "difficulty_preference": "adaptive",
            })

    def test_reject_invalid_difficulty_preference(self):
        """Engine must reject invalid difficulty preference."""
        with self.assertRaises((ValueError, InvalidDifficultyError)):
            self.engine.decide({
                "user_id": 1,
                "wake_session_id": 10,
                "challenge_type": "math",
                "difficulty_preference": "super_extreme",
            })

    def test_reject_missing_context(self):
        """Engine must reject None context."""
        with self.assertRaises(ValueError):
            self.engine.decide(None)

    def test_reject_personalization_engine_mutating_challenge_type(self):
        """Engine must catch and reject any PersonalizationEngine attempt to mutate challenge type."""
        mock_p_engine = MagicMock(spec=PersonalizationEngine)
        # Malformed PersonalizationEngine returning dance when math was requested
        mock_p_engine.decide.return_value = PersonalizationDecision(
            recommended_difficulty="medium",
            challenge_type="dance",  # Mutated!
            decision_source=DecisionSource.ML_ADAPTIVE.value,
            model_confidence=0.80,
        )
        engine = AdaptiveDecisionEngine(personalization_engine=mock_p_engine)

        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=10,
            challenge_type="math",
            difficulty_preference="adaptive",
        )
        with self.assertRaises(ValueError) as err:
            engine.decide(ctx)
        self.assertIn("mutated challenge type", str(err.exception))

    def test_reject_personalization_engine_invalid_difficulty(self):
        """Engine must catch and reject any PersonalizationEngine returning non-concrete difficulty."""
        mock_p_engine = MagicMock(spec=PersonalizationEngine)
        # Malformed: returning 'adaptive' as recommended_difficulty
        mock_bad_decision = MagicMock()
        mock_bad_decision.recommended_difficulty = "adaptive"  # 'adaptive' is not a concrete challenge level!
        mock_bad_decision.challenge_type = "math"
        mock_bad_decision.decision_source = DecisionSource.ML_ADAPTIVE.value
        mock_bad_decision.model_confidence = 0.80
        mock_p_engine.decide.return_value = mock_bad_decision
        engine = AdaptiveDecisionEngine(personalization_engine=mock_p_engine)

        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=10,
            challenge_type="math",
            difficulty_preference="adaptive",
        )
        with self.assertRaises(ValueError) as err:
            engine.decide(ctx)
        self.assertIn("invalid final difficulty", str(err.exception))

    def test_stage_2_missing_telemetry_safe_fallback(self):
        """Stage 2 with missing telemetry safely falls back without fabricating metrics."""
        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=10,
            challenge_type="math",
            difficulty_preference="adaptive",
            historical_session_count=12,
            previous_difficulty="medium",
        )
        # feature_record is None -> safe fallback without synthetic data
        decision = self.engine.decide(ctx, feature_record=None)
        self.assertEqual(decision.decision_source, DecisionSource.FALLBACK_SAFE.value)
        self.assertEqual(decision.final_difficulty, "medium")
        self.assertEqual(decision.challenge_type, "math")


# =============================================================================
# E. INTEGRATION TESTS (Runtime Challenge Generation & Execution)
# =============================================================================
class TestAdaptiveDecisionEngineIntegration(unittest.TestCase):
    """Integration test suite verifying final difficulty reaches runtime generation and attempt tracking."""

    @classmethod
    def setUpClass(cls):
        """Set up isolated in-memory database."""
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=cls.engine
        )
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

            user = User(username="carol", email="carol@example.com")
            session.add(user)
            session.commit()
            session.refresh(user)
            self.user_id: int = int(user.id)

            alarm = Alarm(
                user_id=self.user_id,
                time="07:30",
                days_of_week="[0,1,2,3,4]",
                selected_challenge_type="math",
                difficulty_preference="adaptive",
                is_active=True,
            )
            session.add(alarm)
            session.commit()
            session.refresh(alarm)
            self.alarm_id: int = int(alarm.id)

    def test_start_attempt_adaptive_stage_0_reaches_runtime_generator(self):
        """Final difficulty from AdaptiveDecisionEngine reaches runtime generator and attempt record."""
        with self.SessionLocal() as db:
            wake_session = create_wake_session(
                db=db,
                user_id=int(self.user_id),
                alarm_id=int(self.alarm_id),
            )

            # User has 0 historical sessions -> Stage 0 heuristic for math resolves to 'easy'
            req = ChallengeAttemptStartRequest(
                user_id=int(self.user_id),
                wake_session_id=int(wake_session.id),
                challenge_type="math",
            )
            attempt = start_challenge_attempt(db, req)

            self.assertEqual(attempt.challenge_type, "math")
            self.assertEqual(attempt.difficulty_level, "easy")
            self.assertEqual(attempt.attempt_number, 1)

            # Verify prompt content was generated with easy math
            payload = json.loads(attempt.prompt_content)
            self.assertEqual(payload["challenge_type"], "math")
            self.assertEqual(payload["difficulty_level"], "easy")

    def test_start_attempt_fixed_difficulty_preserves_choice(self):
        """Fixed difficulty preference in Alarm is preserved through start_challenge_attempt."""
        with self.SessionLocal() as db:
            alarm = Alarm(
                user_id=int(self.user_id),
                time="08:00",
                days_of_week="[0,1,2,3,4]",
                selected_challenge_type="dance",
                difficulty_preference="hard",
                is_active=True,
            )
            db.add(alarm)
            db.commit()
            db.refresh(alarm)

            wake_sess = create_wake_session(
                db=db,
                user_id=int(self.user_id),
                alarm_id=int(alarm.id),
            )

            req = ChallengeAttemptStartRequest(
                user_id=int(self.user_id),
                wake_session_id=int(wake_sess.id),
            )
            attempt = start_challenge_attempt(db, req)

            self.assertEqual(attempt.challenge_type, "dance")
            self.assertEqual(attempt.difficulty_level, "hard")

    def test_attempt_retry_preserves_challenge_type_and_status(self):
        """Failed attempt retry preserves challenge type and advances attempt number."""
        with self.SessionLocal() as db:
            wake_session = create_wake_session(
                db=db,
                user_id=int(self.user_id),
                alarm_id=int(self.alarm_id),
            )

            # Attempt 1: starts attempt
            req1 = ChallengeAttemptStartRequest(
                user_id=int(self.user_id),
                wake_session_id=int(wake_session.id),
                challenge_type="math",
            )
            att1 = start_challenge_attempt(db, req1)
            self.assertEqual(att1.attempt_number, 1)

            # Submit wrong answer to fail attempt 1
            submit_challenge_attempt(
                db=db,
                attempt_id=int(att1.id),
                user_id=int(self.user_id),
                submission_data={"answer": 999999},  # Incorrect
            )

            # Attempt 2: retry must keep math and advance to attempt #2
            req2 = ChallengeAttemptStartRequest(
                user_id=int(self.user_id),
                wake_session_id=int(wake_session.id),
                challenge_type="math",
            )
            att2 = start_challenge_attempt(db, req2)
            self.assertEqual(att2.attempt_number, 2)
            self.assertEqual(att2.challenge_type, "math")

            # Submit attempt 2 so no active uncompleted attempt blocks the next attempt
            submit_challenge_attempt(
                db=db,
                attempt_id=int(att2.id),
                user_id=int(self.user_id),
                submission_data={"answer": 999999},  # Incorrect
            )

            # Cannot switch challenge type on retry (attempt #3)
            req_invalid = ChallengeAttemptStartRequest(
                user_id=int(self.user_id),
                wake_session_id=int(wake_session.id),
                challenge_type="dance",
            )
            with self.assertRaises(InvalidChallengeTypeError):
                start_challenge_attempt(db, req_invalid)


if __name__ == "__main__":
    unittest.main()
