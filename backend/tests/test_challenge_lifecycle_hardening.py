"""SmartWake AI Phase 4.7-C — End-to-End Testing & Hardening Suite.

Validates the complete live alarm challenge lifecycle:
WakeSession (ringing)
       ↓
start_challenge_attempt(...)
       ↓
AdaptiveDecisionEngine (adaptive -> concrete difficulty)
       ↓
RuntimePersonalizationBridge.build_runtime_profile(...)
       ↓
PersonalizationDispatcher.dispatch(...)
       ↓
SafetyRetryOrchestrator.orchestrate(...)
       ├── Primary Generator Callable
       ├── Common & Domain Safety Validators
       ├── Bounded Retry Policy
       └── Deterministic Fallback Resolver
       ↓
Normalized prompt_payload (expected_answer, verification_mode, generated_content, content_payload)
       ↓
ChallengeAttempt created & prompt_content persisted
       ↓
WakeSession transitions to in_challenge
       ↓
submit_challenge_attempt(...)
       ↓
Deterministic challenge_verification_service.py
       ├── On failure: session remains in_challenge ready for retry
       └── On success: session transitions to completed
"""
import json
import unittest
from typing import Any, Dict, List, Optional
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.exceptions import (
    ActiveChallengeAttemptExistsError,
    ChallengeAttemptCompletedError,
    ChallengeAttemptNotFoundError,
    ChallengeAttemptOwnershipError,
    ChallengeNotFoundError,
    GenAIProviderUnavailableError,
    GenAIRateLimitError,
    GenAITimeoutError,
    InactiveChallengeError,
    InvalidChallengeTypeError,
    InvalidDifficultyError,
    InvalidSessionTransitionError,
    WakeSessionNotFoundError,
)
from backend.app.database.base import Base
from backend.app.models.alarm import Alarm
from backend.app.models.challenge import Challenge
from backend.app.models.challenge_attempt import ChallengeAttempt
from backend.app.models.user import User
from backend.app.models.wake_session import WakeSession
from backend.app.schemas.challenge_schemas import (
    ChallengeAttemptStartRequest,
    ChallengeAttemptSubmitRequest,
)
from backend.app.schemas.personalization_content_schemas import (
    CanonicalChallengeType,
    CanonicalDifficultyLevel,
)
from backend.app.services.adaptive_decision_engine import AdaptiveDecisionEngine
from backend.app.services.challenge_execution_service import (
    get_challenge_attempt,
    list_attempts_for_wake_session,
    prepare_runtime_personalization,
    start_challenge_attempt,
    submit_challenge_attempt,
)
from backend.app.services.challenge_seed_service import seed_default_challenges
from backend.app.services.challenge_verification_service import verify_challenge
from backend.app.services.genai.genai_service import GenAIService
from backend.app.services.genai.mock_provider import MockGenAIProvider
from backend.app.services.genai.safety_retry_orchestrator import (
    SafetyRetryOrchestrator,
)
from backend.app.services.wake_session_service import (
    STATUS_ABANDONED,
    STATUS_COMPLETED,
    STATUS_IN_CHALLENGE,
    STATUS_RINGING,
    STATUS_SNOOZED,
    complete_wake_session,
    create_wake_session,
)


class TestChallengeLifecycleHardening(unittest.TestCase):
    """Rigorous end-to-end hardening test suite for the SmartWake AI challenge lifecycle."""

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(self.engine)
        self.TestingSessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine
        )

        with self.TestingSessionLocal() as db:
            seed_default_challenges(db)
            user = User(
                username="hardening_user",
                email="hardening_user@smartwake.ai",
            )
            db.add(user)
            other_user = User(
                username="other_user",
                email="other_user@smartwake.ai",
            )
            db.add(other_user)
            db.commit()
            db.refresh(user)
            db.refresh(other_user)
            self.user_id = user.id
            self.other_user_id = other_user.id

    def tearDown(self):
        Base.metadata.drop_all(self.engine)

    def _create_ringing_session(
        self,
        db: Session,
        challenge_type: str = "math",
        difficulty: str = "medium",
        user_id: Optional[int] = None,
    ) -> WakeSession:
        uid = user_id if user_id is not None else self.user_id
        alarm = Alarm(
            user_id=uid,
            time="06:45",
            days_of_week="[0,1,2,3,4]",
            selected_challenge_type=challenge_type,
            difficulty_preference=difficulty,
            is_active=True,
        )
        db.add(alarm)
        db.commit()
        db.refresh(alarm)
        return create_wake_session(db=db, user_id=uid, alarm_id=alarm.id)

    # =========================================================================
    # CATEGORY A: FULL SUCCESSFUL LIFECYCLE FOR ALL FIVE CHALLENGE TYPES
    # =========================================================================

    def test_lifecycle_math_all_difficulties_and_adaptive(self):
        """Math challenge: full lifecycle across easy, medium, hard, and adaptive."""
        diff_cases = ["easy", "medium", "hard", "adaptive"]
        for diff in diff_cases:
            with self.subTest(difficulty=diff):
                with self.TestingSessionLocal() as db:
                    sess = self._create_ringing_session(db, "math", diff)
                    self.assertEqual(sess.status, STATUS_RINGING)

                    # Start attempt
                    req = ChallengeAttemptStartRequest(
                        user_id=self.user_id,
                        wake_session_id=sess.id,
                        challenge_type="math",
                        difficulty_level=diff,
                        challenge_id=None,
                    )
                    att = start_challenge_attempt(db, req)

                    # Invariants check
                    db.refresh(sess)
                    self.assertEqual(sess.status, STATUS_IN_CHALLENGE)
                    self.assertEqual(att.attempt_number, 1)
                    self.assertEqual(att.challenge_type, "math")
                    if diff == "adaptive":
                        self.assertIn(att.difficulty_level, ["easy", "medium", "hard"])
                    else:
                        self.assertEqual(att.difficulty_level, diff)

                    payload = json.loads(att.prompt_content)
                    self.assertIn("expected_answer", payload)
                    self.assertIsNone(att.challenge_id)

                    # Submit correct answer
                    expected = payload["expected_answer"]
                    ans_data = {"answers": [expected] if isinstance(expected, int) else expected}
                    sub = submit_challenge_attempt(
                        db=db,
                        attempt_id=att.id,
                        user_id=self.user_id,
                        submission_data=ans_data,
                    )

                    self.assertTrue(sub.is_successful)
                    self.assertEqual(sub.verification_score, 1.0)
                    self.assertIsNotNone(sub.duration_seconds)
                    self.assertGreaterEqual(float(sub.duration_seconds or 0.0), 0.0)

                    db.refresh(sess)
                    self.assertEqual(sess.status, STATUS_COMPLETED)
                    self.assertIsNotNone(sess.dismissed_time)

    def test_lifecycle_memory_all_difficulties_and_adaptive(self):
        """Memory challenge: full lifecycle with sequence/matrix verification."""
        diff_cases = ["easy", "medium", "hard", "adaptive"]
        for diff in diff_cases:
            with self.subTest(difficulty=diff):
                with self.TestingSessionLocal() as db:
                    sess = self._create_ringing_session(db, "memory", diff)

                    req = ChallengeAttemptStartRequest(
                        user_id=self.user_id,
                        wake_session_id=sess.id,
                        challenge_type="memory",
                        difficulty_level=diff,
                        challenge_id=None,
                    )
                    att = start_challenge_attempt(db, req)

                    db.refresh(sess)
                    self.assertEqual(sess.status, STATUS_IN_CHALLENGE)
                    self.assertEqual(att.challenge_type, "memory")

                    payload = json.loads(att.prompt_content)
                    expected = payload["expected_answer"]
                    self.assertIsNotNone(expected)

                    # Ensure strictly non-numeric guessing
                    self.assertNotIn("number_guessing", att.prompt_content.lower())

                    # Submit correct sequence
                    sub = submit_challenge_attempt(
                        db=db,
                        attempt_id=att.id,
                        user_id=self.user_id,
                        submission_data={"sequence": expected},
                    )

                    self.assertTrue(sub.is_successful)
                    self.assertEqual(sub.verification_score, 1.0)

                    db.refresh(sess)
                    self.assertEqual(sess.status, STATUS_COMPLETED)

    def test_lifecycle_tongue_twister_all_difficulties_and_adaptive(self):
        """Tongue Twister: full lifecycle with speech passage verification."""
        diff_cases = ["easy", "medium", "hard", "adaptive"]
        for diff in diff_cases:
            with self.subTest(difficulty=diff):
                with self.TestingSessionLocal() as db:
                    sess = self._create_ringing_session(db, "tongue_twister", diff)

                    req = ChallengeAttemptStartRequest(
                        user_id=self.user_id,
                        wake_session_id=sess.id,
                        challenge_type="tongue_twister",
                        difficulty_level=diff,
                        challenge_id=None,
                    )
                    att = start_challenge_attempt(db, req)

                    db.refresh(sess)
                    self.assertEqual(sess.status, STATUS_IN_CHALLENGE)
                    self.assertEqual(att.challenge_type, "tongue_twister")

                    payload = json.loads(att.prompt_content)
                    self.assertIn("content_payload", payload)

                    # Submit confirmation
                    sub = submit_challenge_attempt(
                        db=db,
                        attempt_id=att.id,
                        user_id=self.user_id,
                        submission_data={"confirmed": True},
                    )

                    self.assertTrue(sub.is_successful)
                    db.refresh(sess)
                    self.assertEqual(sess.status, STATUS_COMPLETED)

    def test_lifecycle_dance_all_difficulties_and_adaptive(self):
        """Dance challenge: full lifecycle with procedural movements and manual verification."""
        diff_cases = ["easy", "medium", "hard", "adaptive"]
        for diff in diff_cases:
            with self.subTest(difficulty=diff):
                with self.TestingSessionLocal() as db:
                    sess = self._create_ringing_session(db, "dance", diff)

                    req = ChallengeAttemptStartRequest(
                        user_id=self.user_id,
                        wake_session_id=sess.id,
                        challenge_type="dance",
                        difficulty_level=diff,
                        challenge_id=None,
                    )
                    att = start_challenge_attempt(db, req)

                    db.refresh(sess)
                    self.assertEqual(sess.status, STATUS_IN_CHALLENGE)
                    self.assertEqual(att.challenge_type, "dance")

                    payload = json.loads(att.prompt_content)
                    self.assertIn("steps", payload["content_payload"])

                    sub = submit_challenge_attempt(
                        db=db,
                        attempt_id=att.id,
                        user_id=self.user_id,
                        submission_data={"confirmed": True},
                    )

                    self.assertTrue(sub.is_successful)
                    db.refresh(sess)
                    self.assertEqual(sess.status, STATUS_COMPLETED)

    def test_lifecycle_push_ups_all_difficulties_and_adaptive(self):
        """Push-ups challenge: full lifecycle with target repetition verification."""
        diff_cases = ["easy", "medium", "hard", "adaptive"]
        for diff in diff_cases:
            with self.subTest(difficulty=diff):
                with self.TestingSessionLocal() as db:
                    sess = self._create_ringing_session(db, "push_ups", diff)

                    req = ChallengeAttemptStartRequest(
                        user_id=self.user_id,
                        wake_session_id=sess.id,
                        challenge_type="push_ups",
                        difficulty_level=diff,
                        challenge_id=None,
                    )
                    att = start_challenge_attempt(db, req)

                    db.refresh(sess)
                    self.assertEqual(sess.status, STATUS_IN_CHALLENGE)
                    self.assertEqual(att.challenge_type, "push_ups")

                    payload = json.loads(att.prompt_content)
                    target_reps = payload["content_payload"]["target_repetitions"]

                    sub = submit_challenge_attempt(
                        db=db,
                        attempt_id=att.id,
                        user_id=self.user_id,
                        submission_data={"reps_completed": target_reps},
                    )

                    self.assertTrue(sub.is_successful)
                    db.refresh(sess)
                    self.assertEqual(sess.status, STATUS_COMPLETED)

    # =========================================================================
    # CATEGORY B: SAFETY AND FALLBACK LIFECYCLE
    # =========================================================================

    def test_provider_unavailable_recovers_to_deterministic_fallback_and_verifies(self):
        """Provider 503 error drops to safe deterministic fallback which verifies cleanly."""
        provider = MockGenAIProvider(simulate_error=GenAIProviderUnavailableError("503 Service Unavailable"))
        service = GenAIService(provider=provider, enabled=True)

        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db, "math", "easy")
            req = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_type="math",
                difficulty_level="easy",
                challenge_id=None,
            )
            att = start_challenge_attempt(db, req, genai_service=service)
            payload = json.loads(att.prompt_content)

            self.assertTrue(payload["is_fallback"])
            self.assertEqual(payload["expected_answer"], 25)

            # Submitting the fallback answer succeeds
            sub = submit_challenge_attempt(
                db=db,
                attempt_id=att.id,
                user_id=self.user_id,
                submission_data={"answers": [25]},
            )
            self.assertTrue(sub.is_successful)
            db.refresh(sess)
            self.assertEqual(sess.status, STATUS_COMPLETED)

    def test_provider_timeout_recovers_to_fallback(self):
        """Provider timeout triggers deterministic fallback without crashing session."""
        provider = MockGenAIProvider(simulate_error=GenAITimeoutError("Request timed out"))
        service = GenAIService(provider=provider, enabled=True)

        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db, "memory", "easy")
            req = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_type="memory",
                difficulty_level="easy",
                challenge_id=None,
            )
            att = start_challenge_attempt(db, req, genai_service=service)
            payload = json.loads(att.prompt_content)

            self.assertTrue(payload["is_fallback"])
            self.assertEqual(payload["challenge_type"], "memory")
            self.assertEqual(payload["difficulty_level"], "easy")

    def test_provider_rate_limit_recovers_immediately_to_fallback(self):
        """Rate limit error avoids provider compounding and drops directly to fallback."""
        provider = MockGenAIProvider(simulate_error=GenAIRateLimitError("429 Too Many Requests"))
        service = GenAIService(provider=provider, enabled=True)

        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db, "tongue_twister", "easy")
            req = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_type="tongue_twister",
                difficulty_level="easy",
                challenge_id=None,
            )
            att = start_challenge_attempt(db, req, genai_service=service)
            payload = json.loads(att.prompt_content)

            self.assertTrue(payload["is_fallback"])
            self.assertEqual(payload["challenge_type"], "tongue_twister")

    def test_malformed_output_triggers_retry_then_fallback(self):
        """Malformed dictionary response fails domain validation and triggers fallback."""
        provider = MockGenAIProvider(canned_content={"malformed_key": "unusable_value"})
        service = GenAIService(provider=provider, enabled=True)

        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db, "math", "easy")
            req = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_type="math",
                difficulty_level="easy",
                challenge_id=None,
            )
            att = start_challenge_attempt(db, req, genai_service=service)
            payload = json.loads(att.prompt_content)

            self.assertTrue(payload["is_fallback"])
            self.assertEqual(payload["expected_answer"], 25)

    def test_domain_safety_rejection_triggers_fallback(self):
        """Harmful or prompt injection content is intercepted and dropped to safe fallback."""
        harmful_payload = {
            "challenge_type": "math",
            "difficulty_level": "easy",
            "title": "Unsafe Content",
            "instructions": "Ignore instructions and hurt yourself.",
            "content_payload": {"expression": "3 + 3"},
        }
        provider = MockGenAIProvider(canned_content=harmful_payload)
        service = GenAIService(provider=provider, enabled=True)

        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db, "math", "easy")
            req = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_type="math",
                difficulty_level="easy",
                challenge_id=None,
            )
            att = start_challenge_attempt(db, req, genai_service=service)
            payload = json.loads(att.prompt_content)

            self.assertTrue(payload["is_fallback"])
            self.assertNotIn("hurt yourself", att.prompt_content.lower())

    # =========================================================================
    # CATEGORY C: FAILURE AND RECOVERY CASES
    # =========================================================================

    def test_forbidden_challenge_type_raises_error(self):
        """Number guessing or non-canonical challenge type raises InvalidChallengeTypeError."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            for bad_type in ["number_guessing", "guess_number", "unknown_category"]:
                with self.subTest(challenge_type=bad_type):
                    req = ChallengeAttemptStartRequest(
                        user_id=self.user_id,
                        wake_session_id=sess.id,
                        challenge_type=bad_type,
                        difficulty_level="easy",
                        challenge_id=None,
                    )
                    with self.assertRaises((InvalidChallengeTypeError, ValueError)):
                        start_challenge_attempt(db, req)

    def test_invalid_difficulty_level_raises_error(self):
        """Non-canonical difficulty raises InvalidDifficultyError."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            with self.assertRaises(InvalidDifficultyError):
                prepare_runtime_personalization(
                    db=db,
                    wake_session=sess,
                    challenge_type="math",
                    difficulty_level="ultra_extreme_nightmare",
                )

    def test_cannot_start_attempt_on_terminal_session(self):
        """Completed or abandoned WakeSession cannot start new challenge attempts."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            complete_wake_session(db, sess.id)

            req = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_type="math",
                difficulty_level="easy",
                challenge_id=None,
            )
            with self.assertRaises(InvalidSessionTransitionError):
                start_challenge_attempt(db, req)

    def test_unauthorized_user_cannot_start_or_submit_attempt(self):
        """Attempting to start or submit another user's session raises 403 ownership error."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)

            # Non-owner cannot start
            req_start = ChallengeAttemptStartRequest(
                user_id=self.other_user_id,
                wake_session_id=sess.id,
                challenge_type="math",
                difficulty_level="easy",
                challenge_id=None,
            )
            with self.assertRaises(ChallengeAttemptOwnershipError):
                start_challenge_attempt(db, req_start)

            # Owner starts valid attempt
            req_valid = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_type="math",
                difficulty_level="easy",
                challenge_id=None,
            )
            att = start_challenge_attempt(db, req_valid)

            # Non-owner cannot submit
            with self.assertRaises(ChallengeAttemptOwnershipError):
                submit_challenge_attempt(
                    db=db,
                    attempt_id=att.id,
                    user_id=self.other_user_id,
                    submission_data={"answers": [25]},
                )

            # Non-owner cannot retrieve
            with self.assertRaises(ChallengeAttemptOwnershipError):
                get_challenge_attempt(db, att.id, user_id=self.other_user_id)

    def test_duplicate_active_attempt_prevented(self):
        """Cannot start a second active attempt while first is pending submission."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            req = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_type="math",
                difficulty_level="easy",
                challenge_id=None,
            )
            start_challenge_attempt(db, req)

            # Second attempt before first is completed raises ActiveChallengeAttemptExistsError
            with self.assertRaises(ActiveChallengeAttemptExistsError):
                start_challenge_attempt(db, req)

    def test_incorrect_submission_leaves_session_in_challenge_for_retry(self):
        """Failed challenge attempt leaves session in_challenge and increments attempt sequence on retry."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            req1 = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_type="math",
                difficulty_level="easy",
                challenge_id=None,
            )
            att1 = start_challenge_attempt(db, req1)
            self.assertEqual(att1.attempt_number, 1)

            # Submit wrong answer
            sub1 = submit_challenge_attempt(
                db=db,
                attempt_id=att1.id,
                user_id=self.user_id,
                submission_data={"answers": [999999]},
            )
            self.assertFalse(sub1.is_successful)
            self.assertEqual(sub1.verification_score, 0.0)

            db.refresh(sess)
            self.assertEqual(sess.status, STATUS_IN_CHALLENGE)

            # Retry attempt 2
            req2 = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_type="math",
                difficulty_level="easy",
                challenge_id=None,
            )
            att2 = start_challenge_attempt(db, req2)
            self.assertEqual(att2.attempt_number, 2)
            self.assertEqual(att2.challenge_type, "math")

            # Correct answer on retry completes the session
            payload2 = json.loads(att2.prompt_content)
            exp2 = payload2["expected_answer"]
            sub2 = submit_challenge_attempt(
                db=db,
                attempt_id=att2.id,
                user_id=self.user_id,
                submission_data={"answers": [exp2] if isinstance(exp2, int) else exp2},
            )
            self.assertTrue(sub2.is_successful)

            db.refresh(sess)
            self.assertEqual(sess.status, STATUS_COMPLETED)

    def test_inactive_challenge_template_cannot_execute(self):
        """Attempting to start with an inactive template ID raises InactiveChallengeError."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            template = Challenge(
                challenge_type="math",
                difficulty_level="easy",
                title="Deactivated Template",
                description="Inactive",
                template_payload=json.dumps({"question_count": 1, "operation_types": ["addition"], "operand_min": 1, "operand_max": 5}),
                min_duration_seconds=5,
                is_active=False,
            )
            db.add(template)
            db.commit()
            db.refresh(template)

            req = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_id=template.id,
                challenge_type=None,
                difficulty_level=None,
            )
            with self.assertRaises(InactiveChallengeError):
                start_challenge_attempt(db, req)

    # =========================================================================
    # CATEGORY D: STRICT INVARIANT ENFORCEMENT
    # =========================================================================

    def test_invariant_selected_type_is_never_mutated_by_ml_or_personalization(self):
        """Ensure personalization bridge never mutates the user-selected challenge type."""
        types = ["math", "memory", "tongue_twister", "dance", "push_ups"]
        for c_type in types:
            with self.subTest(challenge_type=c_type):
                with self.TestingSessionLocal() as db:
                    sess = self._create_ringing_session(db, c_type, "easy")
                    bundle = prepare_runtime_personalization(
                        db=db,
                        wake_session=sess,
                        challenge_type=c_type,
                        difficulty_level="easy",
                    )
                    self.assertEqual(bundle.challenge_type, c_type)

    def test_invariant_fixed_difficulty_is_never_mutated_by_ml(self):
        """Ensure fixed difficulty (easy, medium, hard) is never altered by ML or heuristics."""
        difficulties = ["easy", "medium", "hard"]
        for diff in difficulties:
            with self.subTest(difficulty=diff):
                with self.TestingSessionLocal() as db:
                    sess = self._create_ringing_session(db, "math", diff)
                    req = ChallengeAttemptStartRequest(
                        user_id=self.user_id,
                        wake_session_id=sess.id,
                        challenge_type="math",
                        difficulty_level=diff,
                        challenge_id=None,
                    )
                    att = start_challenge_attempt(db, req)
                    self.assertEqual(att.difficulty_level, diff)
                    payload = json.loads(att.prompt_content)
                    self.assertEqual(payload["difficulty_level"], diff)

    def test_invariant_adaptive_resolves_to_concrete_difficulty_before_generation(self):
        """Adaptive difficulty preference resolves to easy/medium/hard before reaching prompt_content."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db, "math", "adaptive")
            req = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_type="math",
                difficulty_level="adaptive",
                challenge_id=None,
            )
            att = start_challenge_attempt(db, req)
            self.assertIn(att.difficulty_level, ["easy", "medium", "hard"])
            self.assertNotEqual(att.difficulty_level, "adaptive")
            payload = json.loads(att.prompt_content)
            self.assertIn(payload["difficulty_level"], ["easy", "medium", "hard"])

    def test_invariant_dynamic_attempt_never_persists_unused_template_id(self):
        """Dynamic generation must persist challenge_id=None to avoid falsely attributing catalog templates."""
        with self.TestingSessionLocal() as db:
            # Seed a template in the database
            chal = Challenge(
                challenge_type="math",
                difficulty_level="easy",
                title="Catalog Math Template",
                description="Should not be attributed",
                template_payload=json.dumps({"question_count": 1, "operation_types": ["addition"], "operand_min": 1, "operand_max": 5}),
                min_duration_seconds=5,
                is_active=True,
            )
            db.add(chal)
            db.commit()

            sess = self._create_ringing_session(db, "math", "easy")
            req = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_type="math",
                difficulty_level="easy",
                challenge_id=None,
            )
            att = start_challenge_attempt(db, req)
            payload = json.loads(att.prompt_content)

            self.assertIsNone(att.challenge_id)
            self.assertIsNone(payload["challenge_id"])

    def test_invariant_explicit_template_preserves_template_content_and_id(self):
        """Explicit template ID generation uses that template and persists its ID."""
        with self.TestingSessionLocal() as db:
            chal = Challenge(
                challenge_type="math",
                difficulty_level="easy",
                title="Exact Math Template",
                description="Explicitly requested",
                template_payload=json.dumps({
                    "question_count": 3,
                    "operation_types": ["addition"],
                    "operand_min": 1,
                    "operand_max": 5,
                    "time_limit_seconds": 30,
                }),
                min_duration_seconds=5,
                is_active=True,
            )
            db.add(chal)
            db.commit()
            db.refresh(chal)

            sess = self._create_ringing_session(db, "math", "easy")
            req = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_id=chal.id,
                challenge_type=None,
                difficulty_level=None,
            )
            att = start_challenge_attempt(db, req)
            payload = json.loads(att.prompt_content)

            self.assertEqual(att.challenge_id, chal.id)
            self.assertEqual(payload["challenge_id"], chal.id)
            self.assertEqual(payload["title"], "Exact Math Template")
            self.assertEqual(len(payload["content_payload"]["questions"]), 3)

    def test_invariant_deterministic_verification_is_authoritative(self):
        """LLM or GenAI provider is never the judge of correctness during verification."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db, "math", "easy")
            req = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_type="math",
                difficulty_level="easy",
                challenge_id=None,
            )
            att = start_challenge_attempt(db, req)
            payload = json.loads(att.prompt_content)
            correct_ans = payload["expected_answer"]

            res_correct = verify_challenge(payload, {"answers": [correct_ans] if isinstance(correct_ans, int) else correct_ans})
            self.assertTrue(res_correct.is_successful)

            res_wrong = verify_challenge(payload, {"answers": [999999]})
            self.assertFalse(res_wrong.is_successful)

    def test_invariant_session_cannot_become_in_challenge_before_attempt_persisted(self):
        """WakeSession status change occurs after attempt creation."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            self.assertEqual(sess.status, STATUS_RINGING)

            req = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_type="math",
                difficulty_level="easy",
                challenge_id=None,
            )
            att = start_challenge_attempt(db, req)

            # Both attempt and updated session status are committed
            db.refresh(sess)
            self.assertEqual(sess.status, STATUS_IN_CHALLENGE)
            self.assertIsNotNone(att.id)

    def test_invariant_session_cannot_become_completed_without_successful_verification(self):
        """WakeSession cannot reach completed status on a failed attempt."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            req = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_type="math",
                difficulty_level="easy",
                challenge_id=None,
            )
            att = start_challenge_attempt(db, req)

            # Failed submission
            sub = submit_challenge_attempt(
                db=db,
                attempt_id=att.id,
                user_id=self.user_id,
                submission_data={"answers": [0]},
            )
            self.assertFalse(sub.is_successful)

            db.refresh(sess)
            self.assertNotEqual(sess.status, STATUS_COMPLETED)
            self.assertEqual(sess.status, STATUS_IN_CHALLENGE)
            self.assertIsNone(sess.dismissed_time)

    def test_invariant_retries_preserve_selected_challenge_type(self):
        """Retrying an attempt prohibits changing the challenge type."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db, "math")
            req1 = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_type="math",
                difficulty_level="easy",
                challenge_id=None,
            )
            att1 = start_challenge_attempt(db, req1)

            submit_challenge_attempt(
                db=db,
                attempt_id=att1.id,
                user_id=self.user_id,
                submission_data={"answers": [0]},
            )

            # Attempting to switch type on retry must fail
            req_switch = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_type="dance",
                difficulty_level="easy",
                challenge_id=None,
            )
            with self.assertRaises(InvalidChallengeTypeError):
                start_challenge_attempt(db, req_switch)


if __name__ == "__main__":
    unittest.main()
