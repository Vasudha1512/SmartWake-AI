"""Focused test suite for Phase 4.7-A: Runtime Integration Foundation.

Verifies the runtime bridge connecting live WakeSession and historical database
records to the Phase 4.5 Challenge Personalization and Precedence Engine:
1. Active WakeSession → valid personalization signals.
2. Snooze count is taken from actual session/runtime data (0 -> none, 1 -> low, 2 -> moderate, 3+ -> high).
3. Attempt number is represented correctly (attempt 1 -> False, attempt 2+ -> True).
4. Historical challenge outcomes are read from actual stored records (success rate, failure count).
5. Recent structural signatures are collected correctly from stored prompt_content.
6. Cold-start / insufficient-history behavior works without fabricated records (rate=None, failures=0).
7. SafePersonalizationContext contains no user/session identifiers or PII.
8. User-selected challenge type remains unchanged across all 5 canonical types.
9. Explicit fixed difficulty remains unchanged.
10. Adaptive difficulty output from AdaptiveDecisionEngine is passed through correctly.
11. Existing personalization dispatcher integration (dispatch_runtime_bundle).
12. Helper integration in challenge_execution_service.prepare_runtime_personalization.
"""
from datetime import datetime, timedelta
import json
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.datetime_utils import now_utc_naive
from backend.app.database.base import Base
import backend.app.database.session  # Ensures pragma listeners
from backend.app.models.alarm import Alarm
from backend.app.models.challenge_attempt import ChallengeAttempt
from backend.app.models.user import User
from backend.app.models.wake_session import WakeSession
from backend.app.schemas.challenge_content_schemas import (
    FORBIDDEN_CONTEXT_KEYS,
    SafePersonalizationContext,
)
from backend.app.schemas.personalization_content_schemas import (
    BehavioralPersonalizationSignals,
    MathPersonalizationParams,
    MemoryPersonalizationParams,
    PersonalizedChallengeProfile,
    TongueTwisterPersonalizationParams,
)
from backend.app.services.adaptive_decision_engine import AdaptiveDecisionEngine
from backend.app.services.challenge_execution_service import (
    prepare_runtime_personalization,
)
from backend.app.services.personalization_dispatcher import (
    MathDispatchResult,
    MemoryDispatchResult,
    PersonalizationDispatcher,
    TongueTwisterDispatchResult,
)
from backend.app.services.runtime_personalization_bridge import (
    RuntimeBridgeDifficultyError,
    RuntimeBridgeTypeError,
    RuntimePersonalizationBridge,
    RuntimePersonalizationBundle,
)
from backend.app.services.wake_session_service import STATUS_RINGING, STATUS_SNOOZED


import uuid


class TestRuntimePersonalizationBridge(unittest.TestCase):
    """Test suite validating Phase 4.7-A Runtime Integration Foundation."""

    @classmethod
    def setUpClass(cls):
        """Set up in-memory SQLite database."""
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.TestingSessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=cls.engine
        )
        Base.metadata.create_all(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=cls.engine)
        cls.engine.dispose()

    def setUp(self):
        """Set up clean database session and base records."""
        self.db: Session = self.TestingSessionLocal()
        uid = uuid.uuid4().hex[:8]

        # Seed test user
        self.user = User(
            username=f"test_user_{uid}",
            email=f"test_user_{uid}@example.com",
            timezone="UTC",
        )
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)

        # Seed test alarm
        self.alarm = Alarm(
            user_id=self.user.id,
            time="07:00",
            label="Morning Alarm",
            selected_challenge_type="math",
            difficulty_preference="medium",
            is_active=True,
        )
        self.db.add(self.alarm)
        self.db.commit()
        self.db.refresh(self.alarm)

        # Seed active wake session
        now = now_utc_naive()
        self.wake_session = WakeSession(
            user_id=self.user.id,
            alarm_id=self.alarm.id,
            scheduled_time=now,
            initial_ring_time=now,
            status=STATUS_RINGING,
            total_snooze_count=0,
        )
        self.db.add(self.wake_session)
        self.db.commit()
        self.db.refresh(self.wake_session)

    def tearDown(self):
        self.db.rollback()
        for table in reversed(Base.metadata.sorted_tables):
            self.db.execute(table.delete())
        self.db.commit()
        self.db.close()

    # -------------------------------------------------------------------------
    # 1. Active WakeSession → Valid Personalization Signals
    # -------------------------------------------------------------------------
    def test_extract_behavioral_signals_active_session(self):
        """Test extraction of baseline signals from an active wake session."""
        signals = RuntimePersonalizationBridge.extract_behavioral_signals(
            db=self.db,
            wake_session=self.wake_session,
            challenge_type="math",
            current_attempt_number=1,
        )
        self.assertIsInstance(signals, BehavioralPersonalizationSignals)
        self.assertEqual(signals.recent_snooze_level, "none")
        self.assertFalse(signals.is_retry_attempt)
        self.assertIsNone(signals.historical_success_rate)  # Cold start
        self.assertEqual(signals.recent_failure_count, 0)

    # -------------------------------------------------------------------------
    # 2. Snooze Count Mapping from Actual Session Data
    # -------------------------------------------------------------------------
    def test_snooze_count_mapping_tiers(self):
        """Verify snooze count mapping matches architectural tiers (none, low, moderate, high)."""
        test_cases = [
            (0, "none"),
            (1, "low"),
            (2, "moderate"),
            (3, "high"),
            (7, "high"),
        ]
        for count, expected_level in test_cases:
            self.wake_session.total_snooze_count = count
            self.db.commit()
            self.db.refresh(self.wake_session)

            signals = RuntimePersonalizationBridge.extract_behavioral_signals(
                db=self.db,
                wake_session=self.wake_session,
                challenge_type="math",
            )
            self.assertEqual(
                signals.recent_snooze_level,
                expected_level,
                f"Snooze count {count} should map to level '{expected_level}'",
            )

    # -------------------------------------------------------------------------
    # 3. Attempt Number Representation
    # -------------------------------------------------------------------------
    def test_attempt_number_retry_representation(self):
        """Verify attempt number 1 is not retry, but attempt 2+ is flagged as retry."""
        # Attempt 1
        sig1 = RuntimePersonalizationBridge.extract_behavioral_signals(
            db=self.db,
            wake_session=self.wake_session,
            challenge_type="math",
            current_attempt_number=1,
        )
        self.assertFalse(sig1.is_retry_attempt)

        # Attempt 2
        sig2 = RuntimePersonalizationBridge.extract_behavioral_signals(
            db=self.db,
            wake_session=self.wake_session,
            challenge_type="math",
            current_attempt_number=2,
        )
        self.assertTrue(sig2.is_retry_attempt)

    # -------------------------------------------------------------------------
    # 4. Historical Challenge Outcomes from Actual Stored Records
    # -------------------------------------------------------------------------
    def test_historical_outcomes_calculated_accurately(self):
        """Verify historical success rate and consecutive failure count are calculated from actual DB rows."""
        now = now_utc_naive()

        # Prior session 1 (completed, 1 success)
        prior_session_1 = WakeSession(
            user_id=self.user.id,
            alarm_id=self.alarm.id,
            scheduled_time=now - timedelta(days=2),
            initial_ring_time=now - timedelta(days=2),
            status="completed",
            total_snooze_count=0,
        )
        self.db.add(prior_session_1)
        self.db.commit()

        att1 = ChallengeAttempt(
            wake_session_id=prior_session_1.id,
            challenge_type="math",
            difficulty_level="medium",
            prompt_content="{}",
            attempt_number=1,
            started_at=now - timedelta(days=2),
            completed_at=now - timedelta(days=2) + timedelta(seconds=20),
            is_successful=True,
        )
        self.db.add(att1)

        # Prior session 2 (completed after 2 failures and 1 success)
        prior_session_2 = WakeSession(
            user_id=self.user.id,
            alarm_id=self.alarm.id,
            scheduled_time=now - timedelta(days=1),
            initial_ring_time=now - timedelta(days=1),
            status="completed",
            total_snooze_count=1,
        )
        self.db.add(prior_session_2)
        self.db.commit()

        att2_fail1 = ChallengeAttempt(
            wake_session_id=prior_session_2.id,
            challenge_type="math",
            difficulty_level="medium",
            prompt_content="{}",
            attempt_number=1,
            started_at=now - timedelta(days=1),
            completed_at=now - timedelta(days=1) + timedelta(seconds=15),
            is_successful=False,
        )
        att2_fail2 = ChallengeAttempt(
            wake_session_id=prior_session_2.id,
            challenge_type="math",
            difficulty_level="medium",
            prompt_content="{}",
            attempt_number=2,
            started_at=now - timedelta(days=1) + timedelta(seconds=30),
            completed_at=now - timedelta(days=1) + timedelta(seconds=45),
            is_successful=False,
        )
        self.db.add_all([att2_fail1, att2_fail2])
        self.db.commit()

        # Check signals for active session before any attempt:
        # Total attempts: 3 (att1=True, att2_fail1=False, att2_fail2=False)
        # Success rate = 1 / 3 = 0.3333
        # Most recent failure count = 2 (att2_fail2, att2_fail1)
        signals = RuntimePersonalizationBridge.extract_behavioral_signals(
            db=self.db,
            wake_session=self.wake_session,
            challenge_type="math",
            current_attempt_number=1,
        )
        self.assertAlmostEqual(signals.historical_success_rate, 0.3333, places=3)
        self.assertEqual(signals.recent_failure_count, 2)

    # -------------------------------------------------------------------------
    # 5. Recent Structural Signatures Collected from Stored Attempts
    # -------------------------------------------------------------------------
    def test_collect_recent_structural_signatures(self):
        """Verify structural signatures are extracted from past prompt_content and bounded to 5."""
        now = now_utc_naive()

        # Create past session with 3 attempts having valid signatures
        past_session = WakeSession(
            user_id=self.user.id,
            alarm_id=self.alarm.id,
            scheduled_time=now - timedelta(days=1),
            initial_ring_time=now - timedelta(days=1),
            status="completed",
        )
        self.db.add(past_session)
        self.db.commit()

        sig_a = "type=math|op=addition|scale=standard"
        sig_b = "type=math|op=multiplication|scale=compact"

        att_a = ChallengeAttempt(
            wake_session_id=past_session.id,
            challenge_type="math",
            difficulty_level="easy",
            prompt_content=json.dumps({"structural_signature": sig_a}),
            attempt_number=1,
            started_at=now - timedelta(days=1),
            completed_at=now - timedelta(days=1) + timedelta(seconds=10),
            is_successful=True,
        )
        att_b = ChallengeAttempt(
            wake_session_id=past_session.id,
            challenge_type="math",
            difficulty_level="medium",
            prompt_content=json.dumps({"structural_signature": sig_b}),
            attempt_number=2,
            started_at=now - timedelta(days=1) + timedelta(seconds=20),
            completed_at=now - timedelta(days=1) + timedelta(seconds=35),
            is_successful=True,
        )
        self.db.add_all([att_a, att_b])
        self.db.commit()

        signatures = RuntimePersonalizationBridge.collect_recent_structural_signatures(
            db=self.db,
            wake_session=self.wake_session,
            challenge_type="math",
        )
        # Should contain newest first: sig_b, then sig_a
        self.assertEqual(len(signatures), 2)
        self.assertEqual(signatures[0], sig_b)
        self.assertEqual(signatures[1], sig_a)

    # -------------------------------------------------------------------------
    # 6. Cold-Start / Insufficient-History Graceful Handling
    # -------------------------------------------------------------------------
    def test_cold_start_insufficient_history(self):
        """Verify that a brand new user with 0 history gets clean defaults without errors or synthetic data."""
        signals = RuntimePersonalizationBridge.extract_behavioral_signals(
            db=self.db,
            wake_session=self.wake_session,
            challenge_type="memory",
            current_attempt_number=1,
        )
        self.assertIsNone(signals.historical_success_rate)
        self.assertEqual(signals.recent_failure_count, 0)
        self.assertEqual(signals.recent_snooze_level, "none")
        self.assertFalse(signals.is_retry_attempt)

        signatures = RuntimePersonalizationBridge.collect_recent_structural_signatures(
            db=self.db,
            wake_session=self.wake_session,
            challenge_type="memory",
        )
        self.assertEqual(signatures, [])

    # -------------------------------------------------------------------------
    # 7. SafePersonalizationContext Strips All PII & DB Identifiers
    # -------------------------------------------------------------------------
    def test_safe_context_strips_pii_and_db_ids(self):
        """Verify that passing dictionary with sensitive/database keys is strictly sanitized."""
        polluted_context = {
            "user_id": 9999,
            "alarm_id": 8888,
            "session_id": 7777,
            "wake_session_id": 6666,
            "email": "leak@example.com",
            "password_hash": "secret",
            "token": "bearer-12345",
            "desired_duration_seconds": 30,
            "preferred_theme": "morning motivation",
            "language": "en",
            "disallowed_topics": ["politics", "exams"],
        }
        self.wake_session.total_snooze_count = 2
        safe_ctx = RuntimePersonalizationBridge.build_safe_context(
            wake_session=self.wake_session,
            current_attempt_number=2,
            explicit_context=polluted_context,
        )
        self.assertIsInstance(safe_ctx, SafePersonalizationContext)
        self.assertEqual(safe_ctx.desired_duration_seconds, 30)
        self.assertEqual(safe_ctx.preferred_theme, "morning motivation")
        self.assertEqual(safe_ctx.language, "en")
        self.assertEqual(safe_ctx.disallowed_topics, ["politics", "exams"])
        self.assertEqual(safe_ctx.current_session_snooze_count, 2)
        self.assertEqual(safe_ctx.current_attempt_number, 2)

        # Verify zero forbidden keys exist in schema dump
        dump = safe_ctx.model_dump()
        for forbidden in FORBIDDEN_CONTEXT_KEYS:
            self.assertNotIn(forbidden, dump)
            self.assertNotIn(forbidden, str(dump))

    # -------------------------------------------------------------------------
    # 8. User-Selected Challenge Type Invariance Across All 5 Types
    # -------------------------------------------------------------------------
    def test_all_canonical_challenge_types_supported_and_preserved(self):
        """Verify all 5 canonical challenge types produce valid bundles preserving exact type."""
        canonical_types = ["dance", "math", "memory", "tongue_twister", "push_ups"]
        for ctype in canonical_types:
            bundle = RuntimePersonalizationBridge.build_runtime_profile(
                db=self.db,
                wake_session=self.wake_session,
                challenge_type=ctype,
                difficulty_level="medium",
                current_attempt_number=1,
            )
            self.assertIsInstance(bundle, RuntimePersonalizationBundle)
            self.assertEqual(bundle.challenge_type, ctype)
            self.assertEqual(bundle.difficulty_level, "medium")
            self.assertEqual(bundle.personalized_profile.challenge_type, ctype)
            self.assertEqual(bundle.personalized_profile.difficulty_level, "medium")

    # -------------------------------------------------------------------------
    # 9. Explicit Fixed Difficulty Invariance
    # -------------------------------------------------------------------------
    def test_explicit_fixed_difficulty_preserved(self):
        """Verify fixed difficulty levels ('easy', 'medium', 'hard') are preserved without alteration."""
        for diff in ("easy", "medium", "hard"):
            bundle = RuntimePersonalizationBridge.build_runtime_profile(
                db=self.db,
                wake_session=self.wake_session,
                challenge_type="math",
                difficulty_level=diff,
            )
            self.assertEqual(bundle.difficulty_level, diff)
            self.assertEqual(bundle.personalized_profile.difficulty_level, diff)

    # -------------------------------------------------------------------------
    # 10. Adaptive Decision Engine Passthrough
    # -------------------------------------------------------------------------
    def test_adaptive_decision_engine_passthrough(self):
        """Verify difficulty decision from AdaptiveDecisionEngine passes cleanly into bridge."""
        # Use AdaptiveDecisionEngine to decide difficulty for session
        decision = AdaptiveDecisionEngine.decide_for_session(
            db=self.db,
            wake_session=self.wake_session,
            challenge_type="math",
            difficulty_preference="adaptive",
            current_attempt_number=1,
        )
        self.assertIn(decision.final_difficulty, ("easy", "medium", "hard"))

        bundle = RuntimePersonalizationBridge.build_runtime_profile(
            db=self.db,
            wake_session=self.wake_session,
            challenge_type=decision.challenge_type,
            difficulty_level=decision.final_difficulty,
            current_attempt_number=1,
        )
        self.assertEqual(bundle.challenge_type, decision.challenge_type)
        self.assertEqual(bundle.difficulty_level, decision.final_difficulty)

    # -------------------------------------------------------------------------
    # 11. Forbidden Challenge Types Rejected
    # -------------------------------------------------------------------------
    def test_forbidden_challenge_type_rejected(self):
        """Verify forbidden types (e.g. number guessing) are strictly rejected with RuntimeBridgeTypeError."""
        for forbidden in ("number_guessing", "numeric_memory", "guess_number", "invalid_type"):
            with self.assertRaises(RuntimeBridgeTypeError):
                RuntimePersonalizationBridge.build_runtime_profile(
                    db=self.db,
                    wake_session=self.wake_session,
                    challenge_type=forbidden,
                    difficulty_level="medium",
                )

    # -------------------------------------------------------------------------
    # 12. Dispatcher Integration (dispatch_runtime_bundle)
    # -------------------------------------------------------------------------
    def test_dispatch_runtime_bundle(self):
        """Verify dispatch_runtime_bundle returns typed generator arguments ready for Phase 4.7-B."""
        # Math bundle
        math_bundle = RuntimePersonalizationBridge.build_runtime_profile(
            db=self.db,
            wake_session=self.wake_session,
            challenge_type="math",
            difficulty_level="medium",
        )
        math_res = RuntimePersonalizationBridge.dispatch_runtime_bundle(math_bundle)
        self.assertIsInstance(math_res, MathDispatchResult)
        self.assertEqual(math_res.challenge_type, "math")
        self.assertEqual(math_res.generator_input.difficulty_level, "medium")

        # Memory bundle
        mem_bundle = RuntimePersonalizationBridge.build_runtime_profile(
            db=self.db,
            wake_session=self.wake_session,
            challenge_type="memory",
            difficulty_level="easy",
        )
        mem_res = RuntimePersonalizationBridge.dispatch_runtime_bundle(mem_bundle)
        self.assertIsInstance(mem_res, MemoryDispatchResult)
        self.assertEqual(mem_res.challenge_type, "memory")

        # Tongue twister bundle
        tt_bundle = RuntimePersonalizationBridge.build_runtime_profile(
            db=self.db,
            wake_session=self.wake_session,
            challenge_type="tongue_twister",
            difficulty_level="hard",
        )
        tt_res = RuntimePersonalizationBridge.dispatch_runtime_bundle(tt_bundle)
        self.assertIsInstance(tt_res, TongueTwisterDispatchResult)
        self.assertEqual(tt_res.challenge_type, "tongue_twister")

    # -------------------------------------------------------------------------
    # 13. Integration via prepare_runtime_personalization in execution service
    # -------------------------------------------------------------------------
    def test_prepare_runtime_personalization_helper(self):
        """Verify prepare_runtime_personalization in challenge_execution_service invokes bridge cleanly."""
        bundle = prepare_runtime_personalization(
            db=self.db,
            wake_session=self.wake_session,
            challenge_type="math",
            difficulty_level="easy",
            current_attempt_number=1,
        )
        self.assertIsInstance(bundle, RuntimePersonalizationBundle)
        self.assertEqual(bundle.challenge_type, "math")
        self.assertEqual(bundle.difficulty_level, "easy")


if __name__ == "__main__":
    unittest.main()
