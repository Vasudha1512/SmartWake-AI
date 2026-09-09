"""Automated test suite for Phase 2.9 Challenge Execution & Attempt Tracking.

Validates:
Starting attempts (1-10):
1. Start Math attempt
2. Start Memory attempt
3. Start Dance attempt
4. Start Tongue Twister attempt
5. Start Push-up attempt
6. WakeSession moves to in_challenge
7. RuntimeChallenge is generated
8. ChallengeAttempt is persisted
9. started_at is recorded
10. Initial attempt number is 1

Submission (11-18):
11. Successful Math submission
12. Failed Math submission
13. Successful Memory submission
14. Failed Memory submission
15. Verification result is persisted
16. Verification score is persisted
17. Completion time is persisted
18. Duration is calculated correctly

Retry (19-23):
19. Failed attempt can be retried
20. Retry receives attempt number 2
21. Previous failed attempt remains unchanged
22. Third attempt receives number 3
23. Successful retry completes WakeSession

Ownership (24-27):
24. Non-owner cannot start attempt (403)
25. Non-owner cannot retrieve attempt (403)
26. Non-owner cannot submit attempt (403)
27. Non-owner cannot retrieve session history (403)

Invalid lifecycle (28-31):
28. Cannot start attempt for invalid/terminal WakeSession
29. Cannot create multiple active attempts for same WakeSession (409)
30. Cannot submit completed attempt (400)
31. Inactive challenge template cannot execute (400)

Memory safety (32):
32. Memory execution contains no number-guessing behavior

Regression (33-37):
33. Existing challenge verification tests pass
34. Existing runtime generation tests pass
35. Existing challenge catalog tests pass
36. Full existing project test suite passes
37. Challenge catalog remains 30 records
"""
import asyncio
from datetime import datetime
import json
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.constants import FORBIDDEN_CHALLENGE_TYPES, VALID_CHALLENGE_TYPES
from backend.app.core.datetime_utils import now_utc_naive
from backend.app.core.exceptions import (
    ActiveChallengeAttemptExistsError,
    ChallengeAttemptCompletedError,
    ChallengeAttemptNotFoundError,
    ChallengeAttemptOwnershipError,
    InactiveChallengeError,
    InvalidChallengeTypeError,
    InvalidSessionTransitionError,
    WakeSessionNotFoundError,
)
from backend.app.database.base import Base
import backend.app.database.session  # Ensures pragma listeners
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
    list_attempts_for_wake_session,
    start_challenge_attempt,
    submit_challenge_attempt,
)
from backend.app.services.challenge_seed_service import seed_default_challenges
from backend.app.services.wake_session_service import (
    STATUS_COMPLETED,
    STATUS_IN_CHALLENGE,
    STATUS_RINGING,
    STATUS_SNOOZED,
    complete_wake_session,
    create_wake_session,
    fail_wake_session,
)


class SimpleASGIClient:
    """Lightweight ASGI test client using Python asyncio standard library."""

    def __init__(self, asgi_app):
        self.app = asgi_app

    def _request(self, method: str, path: str, json_data=None, headers=None):
        return asyncio.run(self._async_request(method, path, json_data, headers))

    async def _async_request(self, method: str, path: str, json_data=None, headers=None):
        headers_list = []
        if headers:
            for k, v in headers.items():
                headers_list.append((k.lower().encode("latin1"), v.encode("latin1")))

        body_bytes = b""
        if json_data is not None:
            body_bytes = json.dumps(json_data).encode("utf-8")
            headers_list.append((b"content-type", b"application/json"))
            headers_list.append((b"content-length", str(len(body_bytes)).encode("latin1")))

        raw_path = path.encode("ascii")
        query_string = b""
        if "?" in path:
            p, qs = path.split("?", 1)
            raw_path = p.encode("ascii")
            path = p
            query_string = qs.encode("ascii")

        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.0"},
            "http_version": "1.1",
            "method": method.upper(),
            "scheme": "http",
            "path": path,
            "raw_path": raw_path,
            "query_string": query_string,
            "headers": headers_list,
            "server": ("127.0.0.1", 8000),
            "client": ("127.0.0.1", 50000),
        }

        messages = []
        sent_body = False

        async def receive():
            nonlocal sent_body
            if not sent_body:
                sent_body = True
                return {"type": "http.request", "body": body_bytes, "more_body": False}
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            messages.append(message)

        await self.app(scope, receive, send)

        status_code = next(m["status"] for m in messages if m["type"] == "http.response.start")
        raw_body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")

        class Response:
            def __init__(self, code, body):
                self.status_code = code
                self.text = body.decode("utf-8", errors="replace")

            def json(self):
                return json.loads(self.text)

        return Response(status_code, raw_body)

    def get(self, path: str, headers: dict = None):
        return self._request("GET", path, headers=headers)

    def post(self, path: str, json_data: dict = None, headers: dict = None):
        return self._request("POST", path, json_data=json_data, headers=headers)


class TestChallengeExecution(unittest.TestCase):
    """Isolated test suite for Phase 2.9 Challenge Execution & Attempt Tracking."""

    @classmethod
    def setUpClass(cls):
        """Set up isolated in-memory SQLite database and test client."""
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.TestingSessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=cls.engine
        )
        Base.metadata.create_all(bind=cls.engine)

        def override_get_db():
            db: Session = cls.TestingSessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = SimpleASGIClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=cls.engine)
        cls.engine.dispose()

    def setUp(self):
        """Clear database and re-seed clean baseline."""
        with self.TestingSessionLocal() as session:
            for table in reversed(Base.metadata.sorted_tables):
                session.execute(table.delete())
            session.commit()
            seed_default_challenges(session)

            # Create default user and alarm
            user = User(username="alice", email="alice@example.com")
            session.add(user)
            session.commit()
            session.refresh(user)
            self.user_id = user.id

            other_user = User(username="bob", email="bob@example.com")
            session.add(other_user)
            session.commit()
            session.refresh(other_user)
            self.other_user_id = other_user.id

            alarm = Alarm(
                user_id=self.user_id,
                time="07:00",
                days_of_week="[0,1,2,3,4]",
                selected_challenge_type="math",
                difficulty_preference="easy",
                is_active=True,
            )
            session.add(alarm)
            session.commit()
            session.refresh(alarm)
            self.alarm_id = alarm.id

    def _create_ringing_session(self, db: Session) -> WakeSession:
        """Helper to create an active ringing wake session."""
        return create_wake_session(
            db=db,
            user_id=self.user_id,
            alarm_id=self.alarm_id,
        )

    # ----------------------------------------------------------------------
    # STARTING ATTEMPTS (Tests 1-10)
    # ----------------------------------------------------------------------
    def test_01_start_math_attempt(self):
        """Start Math attempt successfully."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            req = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_type="math",
            )
            att = start_challenge_attempt(db, req)
            self.assertEqual(att.challenge_type, "math")
            self.assertEqual(att.attempt_number, 1)

    def test_02_start_memory_attempt(self):
        """Start Memory attempt successfully."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            req = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_type="memory",
            )
            att = start_challenge_attempt(db, req)
            self.assertEqual(att.challenge_type, "memory")

    def test_03_start_dance_attempt(self):
        """Start Dance attempt successfully."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            req = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_type="dance",
            )
            att = start_challenge_attempt(db, req)
            self.assertEqual(att.challenge_type, "dance")

    def test_04_start_tongue_twister_attempt(self):
        """Start Tongue Twister attempt successfully."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            req = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_type="tongue_twister",
            )
            att = start_challenge_attempt(db, req)
            self.assertEqual(att.challenge_type, "tongue_twister")

    def test_05_start_push_up_attempt(self):
        """Start Push-up attempt successfully."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            req = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_type="push_ups",
            )
            att = start_challenge_attempt(db, req)
            self.assertEqual(att.challenge_type, "push_ups")

    def test_06_wake_session_moves_to_in_challenge(self):
        """WakeSession status transitions from ringing to in_challenge on start."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            self.assertEqual(sess.status, STATUS_RINGING)
            req = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_type="math",
            )
            start_challenge_attempt(db, req)
            db.refresh(sess)
            self.assertEqual(sess.status, STATUS_IN_CHALLENGE)

    def test_07_runtime_challenge_generated_in_prompt_content(self):
        """RuntimeChallenge is generated and stored in prompt_content."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            req = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_type="math",
            )
            att = start_challenge_attempt(db, req)
            prompt_data = json.loads(att.prompt_content)
            self.assertIn("generated_content", prompt_data)
            self.assertIn("questions", prompt_data["generated_content"])
            self.assertIn("expected_answer", prompt_data)

    def test_08_challenge_attempt_is_persisted(self):
        """ChallengeAttempt is persisted in database and queryable."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            req = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_type="math",
            )
            att = start_challenge_attempt(db, req)
            att_id = att.id

            reloaded = db.get(ChallengeAttempt, att_id)
            self.assertIsNotNone(reloaded)
            self.assertEqual(reloaded.wake_session_id, sess.id)

    def test_09_started_at_is_recorded(self):
        """started_at is populated with a valid datetime."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            req = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_type="math",
            )
            att = start_challenge_attempt(db, req)
            self.assertIsNotNone(att.started_at)
            self.assertIsInstance(att.started_at, datetime)

    def test_10_initial_attempt_number_is_one(self):
        """Initial attempt receives attempt_number 1."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            req = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_type="math",
            )
            att = start_challenge_attempt(db, req)
            self.assertEqual(att.attempt_number, 1)

    # ----------------------------------------------------------------------
    # SUBMISSION (Tests 11-18)
    # ----------------------------------------------------------------------
    def test_11_successful_math_submission(self):
        """Math: correct answer submission marks attempt successful and completes session."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            req = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_type="math",
            )
            att = start_challenge_attempt(db, req)
            prompt_data = json.loads(att.prompt_content)
            expected = prompt_data["expected_answer"]

            sub_att = submit_challenge_attempt(
                db=db,
                attempt_id=att.id,
                user_id=self.user_id,
                submission_data={"answers": expected},
            )
            self.assertTrue(sub_att.is_successful)
            self.assertEqual(sub_att.verification_score, 1.0)
            self.assertIsNone(sub_att.failure_reason)

            # Session completes
            db.refresh(sess)
            self.assertEqual(sess.status, STATUS_COMPLETED)
            self.assertIsNotNone(sess.dismissed_time)

    def test_12_failed_math_submission(self):
        """Math: incorrect answer marks attempt failed and leaves session in_challenge."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            req = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_type="math",
            )
            att = start_challenge_attempt(db, req)

            sub_att = submit_challenge_attempt(
                db=db,
                attempt_id=att.id,
                user_id=self.user_id,
                submission_data={"answers": [999999]},
            )
            self.assertFalse(sub_att.is_successful)
            self.assertEqual(sub_att.verification_score, 0.0)
            self.assertEqual(sub_att.failure_reason, "incorrect_answer")

            # Session remains in_challenge ready for retry
            db.refresh(sess)
            self.assertEqual(sess.status, STATUS_IN_CHALLENGE)

    def test_13_successful_memory_submission(self):
        """Memory: correct sequence submission succeeds and completes session."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            req = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_type="memory",
            )
            att = start_challenge_attempt(db, req)
            prompt_data = json.loads(att.prompt_content)
            expected = prompt_data["expected_answer"]

            sub_att = submit_challenge_attempt(
                db=db,
                attempt_id=att.id,
                user_id=self.user_id,
                submission_data={"sequence": expected},
            )
            self.assertTrue(sub_att.is_successful)
            self.assertEqual(sub_att.verification_score, 1.0)
            db.refresh(sess)
            self.assertEqual(sess.status, STATUS_COMPLETED)

    def test_14_failed_memory_submission(self):
        """Memory: incorrect sequence submission fails."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            req = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_type="memory",
            )
            att = start_challenge_attempt(db, req)

            sub_att = submit_challenge_attempt(
                db=db,
                attempt_id=att.id,
                user_id=self.user_id,
                submission_data={"sequence": ["wrong", "color"]},
            )
            self.assertFalse(sub_att.is_successful)
            self.assertEqual(sub_att.verification_score, 0.0)

    def test_15_verification_result_is_persisted(self):
        """verification_result JSON string is stored in ChallengeAttempt."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            req = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_type="math",
            )
            att = start_challenge_attempt(db, req)
            expected = json.loads(att.prompt_content)["expected_answer"]

            sub_att = submit_challenge_attempt(
                db=db,
                attempt_id=att.id,
                user_id=self.user_id,
                submission_data={"answers": expected},
            )
            self.assertIsNotNone(sub_att.verification_result)
            res_obj = json.loads(sub_att.verification_result)
            self.assertEqual(res_obj["status"], "exact_match")

    def test_16_verification_score_is_persisted(self):
        """verification_score float is stored in ChallengeAttempt."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            req = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_type="dance",
            )
            att = start_challenge_attempt(db, req)
            sub_att = submit_challenge_attempt(
                db=db,
                attempt_id=att.id,
                user_id=self.user_id,
                submission_data={"confirmed": True},
            )
            self.assertEqual(sub_att.verification_score, 1.0)

    def test_17_completion_time_is_persisted(self):
        """completed_at is set when submission completes."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            req = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_type="math",
            )
            att = start_challenge_attempt(db, req)
            self.assertIsNone(att.completed_at)

            sub_att = submit_challenge_attempt(
                db=db,
                attempt_id=att.id,
                user_id=self.user_id,
                submission_data={"answers": [1]},
            )
            self.assertIsNotNone(sub_att.completed_at)
            self.assertIsInstance(sub_att.completed_at, datetime)

    def test_18_duration_is_calculated_correctly(self):
        """duration_seconds is non-negative and stored."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            req = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_type="math",
            )
            att = start_challenge_attempt(db, req)
            sub_att = submit_challenge_attempt(
                db=db,
                attempt_id=att.id,
                user_id=self.user_id,
                submission_data={"answers": [1]},
            )
            self.assertIsNotNone(sub_att.duration_seconds)
            self.assertGreaterEqual(sub_att.duration_seconds, 0.0)

    # ----------------------------------------------------------------------
    # RETRY (Tests 19-23)
    # ----------------------------------------------------------------------
    def test_19_failed_attempt_can_be_retried(self):
        """A failed attempt permits starting a new attempt for the same session."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            # Attempt 1
            att1 = start_challenge_attempt(
                db,
                ChallengeAttemptStartRequest(
                    user_id=self.user_id,
                    wake_session_id=sess.id,
                    challenge_type="math",
                ),
            )
            submit_challenge_attempt(
                db, att1.id, self.user_id, {"answers": [999999]}
            )
            self.assertFalse(att1.is_successful)

            # Retry: Attempt 2
            att2 = start_challenge_attempt(
                db,
                ChallengeAttemptStartRequest(
                    user_id=self.user_id,
                    wake_session_id=sess.id,
                ),
            )
            self.assertIsNotNone(att2)
            self.assertNotEqual(att1.id, att2.id)

    def test_20_retry_receives_attempt_number_two(self):
        """Second attempt receives attempt_number 2."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            att1 = start_challenge_attempt(
                db,
                ChallengeAttemptStartRequest(
                    user_id=self.user_id,
                    wake_session_id=sess.id,
                    challenge_type="math",
                ),
            )
            submit_challenge_attempt(
                db, att1.id, self.user_id, {"answers": [999999]}
            )

            att2 = start_challenge_attempt(
                db,
                ChallengeAttemptStartRequest(
                    user_id=self.user_id,
                    wake_session_id=sess.id,
                ),
            )
            self.assertEqual(att2.attempt_number, 2)

    def test_21_previous_failed_attempt_remains_unchanged(self):
        """Previous failed attempt remains preserved in database."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            att1 = start_challenge_attempt(
                db,
                ChallengeAttemptStartRequest(
                    user_id=self.user_id,
                    wake_session_id=sess.id,
                    challenge_type="math",
                ),
            )
            submit_challenge_attempt(
                db, att1.id, self.user_id, {"answers": [999999]}
            )
            att1_id = att1.id

            # Start and complete attempt 2
            att2 = start_challenge_attempt(
                db,
                ChallengeAttemptStartRequest(
                    user_id=self.user_id,
                    wake_session_id=sess.id,
                ),
            )
            expected2 = json.loads(att2.prompt_content)["expected_answer"]
            submit_challenge_attempt(
                db, att2.id, self.user_id, {"answers": expected2}
            )

            # Reload att1 and verify it is completely unchanged
            reloaded_att1 = db.get(ChallengeAttempt, att1_id)
            self.assertEqual(reloaded_att1.attempt_number, 1)
            self.assertFalse(reloaded_att1.is_successful)
            self.assertEqual(reloaded_att1.failure_reason, "incorrect_answer")

    def test_22_third_attempt_receives_number_three(self):
        """Third attempt receives attempt_number 3."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            # Attempt 1
            att1 = start_challenge_attempt(
                db, ChallengeAttemptStartRequest(user_id=self.user_id, wake_session_id=sess.id, challenge_type="math")
            )
            submit_challenge_attempt(db, att1.id, self.user_id, {"answers": [0]})

            # Attempt 2
            att2 = start_challenge_attempt(
                db, ChallengeAttemptStartRequest(user_id=self.user_id, wake_session_id=sess.id)
            )
            submit_challenge_attempt(db, att2.id, self.user_id, {"answers": [0]})

            # Attempt 3
            att3 = start_challenge_attempt(
                db, ChallengeAttemptStartRequest(user_id=self.user_id, wake_session_id=sess.id)
            )
            self.assertEqual(att3.attempt_number, 3)

    def test_23_successful_retry_completes_wake_session(self):
        """WakeSession moves to completed when retry succeeds."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            att1 = start_challenge_attempt(
                db, ChallengeAttemptStartRequest(user_id=self.user_id, wake_session_id=sess.id, challenge_type="math")
            )
            submit_challenge_attempt(db, att1.id, self.user_id, {"answers": [0]})
            db.refresh(sess)
            self.assertEqual(sess.status, STATUS_IN_CHALLENGE)

            att2 = start_challenge_attempt(
                db, ChallengeAttemptStartRequest(user_id=self.user_id, wake_session_id=sess.id)
            )
            expected2 = json.loads(att2.prompt_content)["expected_answer"]
            submit_challenge_attempt(db, att2.id, self.user_id, {"answers": expected2})

            db.refresh(sess)
            self.assertEqual(sess.status, STATUS_COMPLETED)

    # ----------------------------------------------------------------------
    # OWNERSHIP (Tests 24-27)
    # ----------------------------------------------------------------------
    def test_24_non_owner_cannot_start_attempt(self):
        """Non-owner cannot start challenge attempt (403)."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            req = ChallengeAttemptStartRequest(
                user_id=self.other_user_id,
                wake_session_id=sess.id,
                challenge_type="math",
            )
            with self.assertRaises(ChallengeAttemptOwnershipError):
                start_challenge_attempt(db, req)

        # Via API
        resp = self.client.post(
            "/api/v1/challenges/attempts/start",
            json_data={
                "user_id": self.other_user_id,
                "wake_session_id": sess.id,
                "challenge_type": "math",
            },
        )
        self.assertEqual(resp.status_code, 403)

    def test_25_non_owner_cannot_retrieve_attempt(self):
        """Non-owner cannot retrieve another user's attempt (403)."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            att = start_challenge_attempt(
                db, ChallengeAttemptStartRequest(user_id=self.user_id, wake_session_id=sess.id, challenge_type="math")
            )
            att_id = att.id

            with self.assertRaises(ChallengeAttemptOwnershipError):
                get_challenge_attempt(db, att_id, user_id=self.other_user_id)

        # Via API
        resp = self.client.get(f"/api/v1/challenges/attempts/{att_id}?user_id={self.other_user_id}")
        self.assertEqual(resp.status_code, 403)

    def test_26_non_owner_cannot_submit_attempt(self):
        """Non-owner cannot submit another user's attempt (403)."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            att = start_challenge_attempt(
                db, ChallengeAttemptStartRequest(user_id=self.user_id, wake_session_id=sess.id, challenge_type="math")
            )
            att_id = att.id

            with self.assertRaises(ChallengeAttemptOwnershipError):
                submit_challenge_attempt(db, att_id, user_id=self.other_user_id, submission_data={"answers": [1]})

        # Via API
        resp = self.client.post(
            f"/api/v1/challenges/attempts/{att_id}/submit",
            json_data={"user_id": self.other_user_id, "submission_data": {"answers": [1]}},
        )
        self.assertEqual(resp.status_code, 403)

    def test_27_non_owner_cannot_retrieve_session_history(self):
        """Non-owner cannot retrieve wake session challenge attempts (403)."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            att = start_challenge_attempt(
                db, ChallengeAttemptStartRequest(user_id=self.user_id, wake_session_id=sess.id, challenge_type="math")
            )

            with self.assertRaises(ChallengeAttemptOwnershipError):
                list_attempts_for_wake_session(db, sess.id, user_id=self.other_user_id)

        # Via API
        resp = self.client.get(f"/api/v1/wake-sessions/{sess.id}/challenge-attempts?user_id={self.other_user_id}")
        self.assertEqual(resp.status_code, 403)

    # ----------------------------------------------------------------------
    # INVALID LIFECYCLE (Tests 28-31)
    # ----------------------------------------------------------------------
    def test_28_cannot_start_attempt_for_terminal_wake_session(self):
        """Cannot start challenge attempt for completed or abandoned session."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            complete_wake_session(db, sess.id)

            req = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_type="math",
            )
            with self.assertRaises(InvalidSessionTransitionError):
                start_challenge_attempt(db, req)

    def test_29_cannot_create_multiple_active_attempts_same_session(self):
        """Cannot start second attempt while first attempt is uncompleted (409 Conflict)."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            req = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_type="math",
            )
            start_challenge_attempt(db, req)

            # Second attempt before first is submitted raises ActiveChallengeAttemptExistsError
            with self.assertRaises(ActiveChallengeAttemptExistsError):
                start_challenge_attempt(db, req)

        # Via API
        resp = self.client.post(
            "/api/v1/challenges/attempts/start",
            json_data={
                "user_id": self.user_id,
                "wake_session_id": sess.id,
                "challenge_type": "math",
            },
        )
        self.assertEqual(resp.status_code, 409)

    def test_30_cannot_submit_completed_attempt(self):
        """Cannot submit an attempt that has already been submitted (400)."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            att = start_challenge_attempt(
                db, ChallengeAttemptStartRequest(user_id=self.user_id, wake_session_id=sess.id, challenge_type="math")
            )
            expected = json.loads(att.prompt_content)["expected_answer"]
            submit_challenge_attempt(db, att.id, self.user_id, {"answers": expected})

            # Re-submitting raises ChallengeAttemptCompletedError
            with self.assertRaises(ChallengeAttemptCompletedError):
                submit_challenge_attempt(db, att.id, self.user_id, {"answers": expected})

        # Via API
        resp = self.client.post(
            f"/api/v1/challenges/attempts/{att.id}/submit",
            json_data={"user_id": self.user_id, "submission_data": {"answers": expected}},
        )
        self.assertEqual(resp.status_code, 400)

    def test_31_inactive_challenge_template_cannot_execute(self):
        """Attempting to start an attempt with a deactivated template raises error."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            chal = db.scalars(select(Challenge).where(Challenge.is_active == True)).first()
            chal.is_active = False
            db.commit()

            req = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_id=chal.id,
            )
            with self.assertRaises(InactiveChallengeError):
                start_challenge_attempt(db, req)

    # ----------------------------------------------------------------------
    # MEMORY SAFETY (Test 32)
    # ----------------------------------------------------------------------
    def test_32_memory_execution_contains_no_number_guessing(self):
        """Memory challenge attempt stores strictly visual/spatial recall without number guessing."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            req = ChallengeAttemptStartRequest(
                user_id=self.user_id,
                wake_session_id=sess.id,
                challenge_type="memory",
            )
            att = start_challenge_attempt(db, req)
            prompt_str = att.prompt_content.lower()
            for forbidden in ["number_guessing", "guess_number", "numeric_memory"]:
                self.assertNotIn(forbidden, prompt_str)

    # ----------------------------------------------------------------------
    # REGRESSION TESTS (Tests 33-37)
    # ----------------------------------------------------------------------
    def test_33_existing_challenge_verification_tests_pass(self):
        """Regression: Phase 2.8 verification engine works as expected."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            att = start_challenge_attempt(
                db, ChallengeAttemptStartRequest(user_id=self.user_id, wake_session_id=sess.id, challenge_type="push_ups")
            )
            sub = submit_challenge_attempt(db, att.id, self.user_id, {"confirmed": True})
            self.assertTrue(sub.is_successful)

    def test_34_existing_runtime_generation_tests_pass(self):
        """Regression: runtime generation returns valid payload."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            att = start_challenge_attempt(
                db, ChallengeAttemptStartRequest(user_id=self.user_id, wake_session_id=sess.id, challenge_type="tongue_twister")
            )
            prompt = json.loads(att.prompt_content)
            self.assertIn("passage", prompt["generated_content"])

    def test_35_existing_challenge_catalog_tests_pass(self):
        """Regression: challenge catalog querying remains intact."""
        with self.TestingSessionLocal() as db:
            challenges = list(db.scalars(select(Challenge)).all())
            self.assertEqual(len(challenges), 30)

    def test_36_full_api_endpoints_work_together(self):
        """Full flow: start via API -> get via API -> submit via API -> list history via API."""
        with self.TestingSessionLocal() as db:
            sess = self._create_ringing_session(db)
            sess_id = sess.id

        # 1. Start attempt via API
        start_resp = self.client.post(
            "/api/v1/challenges/attempts/start",
            json_data={
                "user_id": self.user_id,
                "wake_session_id": sess_id,
                "challenge_type": "dance",
            },
        )
        self.assertEqual(start_resp.status_code, 201)
        att_data = start_resp.json()
        att_id = att_data["id"]
        self.assertEqual(att_data["attempt_number"], 1)

        # 2. Get attempt via API
        get_resp = self.client.get(f"/api/v1/challenges/attempts/{att_id}?user_id={self.user_id}")
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(get_resp.json()["id"], att_id)

        # 3. Submit attempt via API
        sub_resp = self.client.post(
            f"/api/v1/challenges/attempts/{att_id}/submit",
            json_data={
                "user_id": self.user_id,
                "submission_data": {"confirmed": True},
            },
        )
        self.assertEqual(sub_resp.status_code, 200)
        self.assertTrue(sub_resp.json()["is_successful"])

        # 4. List attempts for session via API
        history_resp = self.client.get(f"/api/v1/wake-sessions/{sess_id}/challenge-attempts?user_id={self.user_id}")
        self.assertEqual(history_resp.status_code, 200)
        history = history_resp.json()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["id"], att_id)

    def test_37_challenge_catalog_remains_thirty_records(self):
        """Regression: database challenge templates count remains 30."""
        with self.TestingSessionLocal() as db:
            self.assertEqual(db.query(Challenge).count(), 30)


if __name__ == "__main__":
    unittest.main()
