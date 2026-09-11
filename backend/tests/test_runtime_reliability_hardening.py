"""SmartWake AI Phase 4.8-A — Runtime Reliability Hardening Test Suite.

Validates:
1. Terminal WakeSession non-resurrection: Submissions against abandoned or completed
   sessions are rejected with InvalidSessionTransitionError without mutating session state.
2. HTTP 400 Error Translation: Verifies that terminal session submissions, forbidden
   challenge patterns (e.g., number guessing), and invalid challenge types return HTTP 400
   instead of unhandled 500 server errors.
3. Atomic transaction safety across challenge generation and attempt persistence.
4. Concurrency & duplicate prevention at the service and API boundaries.
"""
import asyncio
import json
import unittest
from typing import Any, Dict, Optional

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.exceptions import (
    ActiveChallengeAttemptExistsError,
    ChallengeAttemptCompletedError,
    ChallengeAttemptNotFoundError,
    ChallengeAttemptOwnershipError,
    InvalidChallengeTypeError,
    InvalidSessionTransitionError,
    WakeSessionNotFoundError,
)
from backend.app.database.base import Base
from backend.app.database.session import get_db
from backend.app.main import app
from backend.app.models.alarm import Alarm
from backend.app.models.challenge import Challenge
from backend.app.models.challenge_attempt import ChallengeAttempt
from backend.app.models.user import User
from backend.app.models.wake_session import WakeSession
from backend.app.schemas.challenge_schemas import (
    ChallengeAttemptStartRequest,
    ChallengeAttemptSubmitRequest,
)
from backend.app.services.challenge_execution_service import (
    get_challenge_attempt,
    start_challenge_attempt,
    submit_challenge_attempt,
)
from backend.app.services.challenge_seed_service import seed_default_challenges
from backend.app.services.wake_session_service import (
    STATUS_ABANDONED,
    STATUS_COMPLETED,
    STATUS_IN_CHALLENGE,
    STATUS_RINGING,
    STATUS_SNOOZED,
    complete_wake_session,
    create_wake_session,
    fail_wake_session,
)
from backend.tests.test_challenge_execution import SimpleASGIClient


class TestRuntimeReliabilityHardening(unittest.TestCase):
    """Rigorous reliability and edge-case validation for the SmartWake AI challenge lifecycle."""

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=cls.engine)
        cls.TestingSessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=cls.engine
        )

        def override_get_db():
            db = cls.TestingSessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = SimpleASGIClient(app)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=cls.engine)
        cls.engine.dispose()
        app.dependency_overrides.clear()

    def setUp(self):
        """Seed clean baseline data before each test."""
        with self.TestingSessionLocal() as session:
            for table in reversed(Base.metadata.sorted_tables):
                session.execute(table.delete())
            session.commit()
            seed_default_challenges(session)

            user = User(username="reliability_user", email="reliability@smartwake.ai")
            session.add(user)
            other_user = User(username="other_user", email="other@smartwake.ai")
            session.add(other_user)
            session.commit()
            session.refresh(user)
            session.refresh(other_user)
            self.user_id = user.id
            self.other_user_id = other_user.id

            alarm = Alarm(
                user_id=self.user_id,
                time="07:15",
                days_of_week="[0,1,2,3,4]",
                selected_challenge_type="math",
                difficulty_preference="medium",
                is_active=True,
            )
            session.add(alarm)
            session.commit()
            session.refresh(alarm)
            self.alarm_id = alarm.id

    def _create_ringing_session(self, db: Session, challenge_type: str = "math") -> WakeSession:
        alarm = db.get(Alarm, self.alarm_id)
        assert alarm is not None
        alarm.selected_challenge_type = challenge_type
        db.commit()
        return create_wake_session(db=db, user_id=self.user_id, alarm_id=self.alarm_id)

    # =========================================================================
    # 1. TERMINAL SESSION STATE INVARIANTS (NO RESURRECTION)
    # =========================================================================

    def test_submit_attempt_on_abandoned_session_rejected_without_resurrection(self):
        """Failed submission on an abandoned session must NOT resurrect session to in_challenge."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db, "math")
            req = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_type="math",
                difficulty_level="easy",
                challenge_id=None,
            )
            att = start_challenge_attempt(db, req)

            # Session is abandoned while attempt was in progress
            fail_wake_session(db, sess.id)
            db.refresh(sess)
            self.assertEqual(sess.status, STATUS_ABANDONED)

            # Incorrect submission must be rejected with InvalidSessionTransitionError
            with self.assertRaises(InvalidSessionTransitionError) as ctx:
                submit_challenge_attempt(
                    db=db,
                    attempt_id=att.id,
                    user_id=self.user_id,
                    submission_data={"answers": [999999]},
                )
            self.assertIn("already in terminal status 'abandoned'", str(ctx.exception))

            # INVARIANT: Session MUST remain abandoned, never resurrected to in_challenge
            db.refresh(sess)
            self.assertEqual(sess.status, STATUS_ABANDONED)

    def test_submit_attempt_on_abandoned_session_with_correct_answer_rejected(self):
        """Correct submission on an abandoned session must be rejected with InvalidSessionTransitionError."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db, "math")
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

            # Abandon session
            fail_wake_session(db, sess.id)
            db.refresh(sess)
            self.assertEqual(sess.status, STATUS_ABANDONED)

            # Submitting correct answer must be rejected
            with self.assertRaises(InvalidSessionTransitionError) as ctx:
                submit_challenge_attempt(
                    db=db,
                    attempt_id=att.id,
                    user_id=self.user_id,
                    submission_data={"answers": [correct_ans] if isinstance(correct_ans, int) else correct_ans},
                )
            self.assertIn("already in terminal status 'abandoned'", str(ctx.exception))

            # INVARIANT: Session MUST remain abandoned, never converted to completed
            db.refresh(sess)
            self.assertEqual(sess.status, STATUS_ABANDONED)

    def test_submit_attempt_on_completed_session_rejected(self):
        """Submitting an attempt when session was already completed must be rejected."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db, "math")
            req = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_type="math",
                difficulty_level="easy",
                challenge_id=None,
            )
            att = start_challenge_attempt(db, req)

            # Complete session directly
            complete_wake_session(db, sess.id)
            db.refresh(sess)
            self.assertEqual(sess.status, STATUS_COMPLETED)

            # Attempting to submit must raise InvalidSessionTransitionError
            with self.assertRaises(InvalidSessionTransitionError) as ctx:
                submit_challenge_attempt(
                    db=db,
                    attempt_id=att.id,
                    user_id=self.user_id,
                    submission_data={"answers": [10]},
                )
            self.assertIn("already in terminal status 'completed'", str(ctx.exception))

            db.refresh(sess)
            self.assertEqual(sess.status, STATUS_COMPLETED)

    # =========================================================================
    # 2. HTTP API 400 TRANSLATION (NO UNHANDLED 500 ERRORS)
    # =========================================================================

    def test_submit_attempt_api_returns_400_for_terminal_session(self):
        """POST /attempts/{id}/submit on terminal session returns HTTP 400 Bad Request."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db, "math")
            att = start_challenge_attempt(
                db,
                ChallengeAttemptStartRequest(
                    user_id=self.user_id,
                    wake_session_id=sess.id,
                    challenge_type="math",
                    challenge_id=None,
                    difficulty_level=None,
                ),
            )
            fail_wake_session(db, sess.id)
            att_id = att.id

        resp = self.client.post(
            f"/api/v1/challenges/attempts/{att_id}/submit",
            json_data={
                "user_id": self.user_id,
                "submission_data": {"answers": [42]},
            },
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertIn("detail", data)
        self.assertIn("terminal status 'abandoned'", data["detail"])

    def test_submit_attempt_api_returns_400_for_forbidden_number_guessing(self):
        """POST /attempts/{id}/submit with forbidden number guessing returns HTTP 400."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db, "memory")
            att = start_challenge_attempt(
                db,
                ChallengeAttemptStartRequest(
                    user_id=self.user_id,
                    wake_session_id=sess.id,
                    challenge_type="memory",
                    challenge_id=None,
                    difficulty_level=None,
                ),
            )
            att_id = att.id

        # Submitting number guessing pattern to memory challenge
        resp = self.client.post(
            f"/api/v1/challenges/attempts/{att_id}/submit",
            json_data={
                "user_id": self.user_id,
                "submission_data": {"number_guessing": 7},
            },
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertIn("detail", data)
        self.assertIn("Number guessing is strictly forbidden", data["detail"])

    def test_start_attempt_api_returns_400_for_invalid_challenge_type(self):
        """POST /attempts/start with non-canonical type returns HTTP 400 Bad Request."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db, "math")
            sess_id = sess.id

        resp = self.client.post(
            "/api/v1/challenges/attempts/start",
            json_data={
                "user_id": self.user_id,
                "wake_session_id": sess_id,
                "challenge_type": "flying_saucer",
            },
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertIn("detail", data)
        self.assertIn("Invalid challenge type 'flying_saucer'", data["detail"])

    def test_start_attempt_api_returns_400_for_forbidden_challenge_type(self):
        """POST /attempts/start with forbidden challenge type returns HTTP 400 Bad Request."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db, "math")
            sess_id = sess.id

        resp = self.client.post(
            "/api/v1/challenges/attempts/start",
            json_data={
                "user_id": self.user_id,
                "wake_session_id": sess_id,
                "challenge_type": "number_guessing",
            },
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertIn("detail", data)
        self.assertIn("strictly forbidden", data["detail"])

    # =========================================================================
    # 3. ATOMICITY & DUPLICATE PREVENTION
    # =========================================================================

    def test_failed_challenge_start_does_not_mutate_session_status(self):
        """If challenge start raises an error, session remains in initial status."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db, "math")
            self.assertEqual(sess.status, STATUS_RINGING)

            req = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_type="invalid_type",
                challenge_id=None,
                difficulty_level=None,
            )
            with self.assertRaises(InvalidChallengeTypeError):
                start_challenge_attempt(db, req)

            # Session status must still be ringing
            db.refresh(sess)
            self.assertEqual(sess.status, STATUS_RINGING)

            # No attempts should exist
            attempts = list(db.scalars(
                select(ChallengeAttempt).where(ChallengeAttempt.wake_session_id == sess.id)
            ).all())
            self.assertEqual(len(attempts), 0)

    def test_duplicate_active_attempt_api_returns_409(self):
        """POST /attempts/start when active attempt exists returns HTTP 409 Conflict."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db, "math")
            sess_id = sess.id

        # First start succeeds (201)
        resp1 = self.client.post(
            "/api/v1/challenges/attempts/start",
            json_data={
                "user_id": self.user_id,
                "wake_session_id": sess_id,
                "challenge_type": "math",
            },
        )
        self.assertEqual(resp1.status_code, 201)

        # Second concurrent start fails (409)
        resp2 = self.client.post(
            "/api/v1/challenges/attempts/start",
            json_data={
                "user_id": self.user_id,
                "wake_session_id": sess_id,
                "challenge_type": "math",
            },
        )
        self.assertEqual(resp2.status_code, 409)
        self.assertIn("already in progress", resp2.json()["detail"])

    def test_duplicate_submission_api_returns_400(self):
        """POST /attempts/{id}/submit on already submitted attempt returns HTTP 400."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db, "math")
            att = start_challenge_attempt(
                db,
                ChallengeAttemptStartRequest(
                    user_id=self.user_id,
                    wake_session_id=sess.id,
                    challenge_type="math",
                    challenge_id=None,
                    difficulty_level=None,
                ),
            )
            payload = json.loads(att.prompt_content)
            correct_ans = payload["expected_answer"]
            att_id = att.id

        # First submission succeeds (200)
        resp1 = self.client.post(
            f"/api/v1/challenges/attempts/{att_id}/submit",
            json_data={
                "user_id": self.user_id,
                "submission_data": {"answers": [correct_ans] if isinstance(correct_ans, int) else correct_ans},
            },
        )
        self.assertEqual(resp1.status_code, 200)

        # Second submission fails (400)
        resp2 = self.client.post(
            f"/api/v1/challenges/attempts/{att_id}/submit",
            json_data={
                "user_id": self.user_id,
                "submission_data": {"answers": [correct_ans] if isinstance(correct_ans, int) else correct_ans},
            },
        )
        self.assertEqual(resp2.status_code, 400)
        self.assertIn("already been completed and submitted", resp2.json()["detail"])
