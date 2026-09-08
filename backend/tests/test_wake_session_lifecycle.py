"""Automated test suite for WakeSession lifecycle operations in SmartWake AI.

Validates requirements from Phase 2.6.1:
A. Create WakeSession for valid user + active alarm
B. WakeSession receives correct initial status ('ringing')
C. WakeSession receives start timestamp (initial_ring_time and scheduled_time)
D. Nonexistent user rejected (404)
E. Nonexistent alarm rejected (404)
F. Alarm belonging to another user rejected (400)
G. Inactive alarm cannot start a new session (400)
H. Existing alarm configuration remains unchanged after session creation
I. Retrieve WakeSession by ID (200, 404)
J. User can retrieve their own wake-session history (newest first)
K. Another user's sessions are not exposed
L. Valid lifecycle transition to IN_PROGRESS ('in_challenge')
M. Valid lifecycle transition to COMPLETED
N. Valid failure transition ('abandoned')
O. Invalid transition is rejected (e.g. completed -> in_challenge, abandoned -> completed)
P. Completed session receives end/completion timestamp and delay seconds
Q. Duplicate active session protection works according to the active status rule
"""
import asyncio
import json
from datetime import datetime, timedelta
import unittest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.exceptions import (
    ActiveSessionExistsError,
    AlarmNotFoundError,
    AlarmOwnershipError,
    InactiveAlarmError,
    InvalidSessionTransitionError,
    UserNotFoundError,
    WakeSessionNotFoundError,
)
from backend.app.database.base import Base
import backend.app.database.session  # Ensures SQLite pragma listeners
from backend.app.database.session import get_db
from backend.app.main import app
from backend.app.models.alarm import Alarm
from backend.app.models.user import User
from backend.app.models.wake_session import WakeSession
from backend.app.services import alarm_service, user_service, wake_session_service


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

    def post(self, path: str, json: dict = None, headers: dict = None):
        return self._request("POST", path, json_data=json, headers=headers)

    def put(self, path: str, json: dict = None, headers: dict = None):
        return self._request("PUT", path, json_data=json, headers=headers)

    def patch(self, path: str, json: dict = None, headers: dict = None):
        return self._request("PATCH", path, json_data=json, headers=headers)

    def delete(self, path: str, headers: dict = None):
        return self._request("DELETE", path, headers=headers)


class TestWakeSessionLifecycle(unittest.TestCase):
    """Test suite for WakeSession lifecycle operations, validation, and transitions."""

    @classmethod
    def setUpClass(cls):
        """Configure an isolated in-memory SQLite database and override get_db."""
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
        """Clean up in-memory database tables and remove dependency overrides."""
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=cls.engine)
        cls.engine.dispose()

    def setUp(self):
        """Clear database tables before each test for clean isolation."""
        with self.TestingSessionLocal() as session:
            for table in reversed(Base.metadata.sorted_tables):
                session.execute(table.delete())
            session.commit()

        # Seed primary test user and active alarm
        with self.TestingSessionLocal() as session:
            user = user_service.create_user(session, username="session_user", timezone="UTC")
            self.user_id = user.id

            alarm = alarm_service.create_alarm(
                db=session,
                user_id=self.user_id,
                time="07:00",
                selected_challenge_type="tongue_twister",
                difficulty_preference="adaptive",
                label="Morning Wakeup",
                days_of_week=[0, 1, 2, 3, 4],
                is_active=True,
            )
            self.alarm_id = alarm.id

    def test_create_wake_session_valid_user_and_active_alarm(self):
        """Requirement A, B, C: Create session for valid user & active alarm with initial status and timestamps."""
        resp = self.client.post(
            "/api/v1/wake-sessions",
            json={"user_id": self.user_id, "alarm_id": self.alarm_id},
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertIn("id", data)
        self.assertEqual(data["user_id"], self.user_id)
        self.assertEqual(data["alarm_id"], self.alarm_id)
        self.assertEqual(data["status"], "ringing")  # Requirement B
        self.assertIsNotNone(data["initial_ring_time"])  # Requirement C
        self.assertIsNotNone(data["scheduled_time"])  # Requirement C
        self.assertIsNone(data["dismissed_time"])
        self.assertEqual(data["total_snooze_count"], 0)
        self.assertIsNone(data["total_wake_delay_seconds"])

    def test_create_wake_session_nonexistent_user_rejected(self):
        """Requirement D: Nonexistent user_id is rejected with HTTP 404."""
        resp = self.client.post(
            "/api/v1/wake-sessions",
            json={"user_id": 99999, "alarm_id": self.alarm_id},
        )
        self.assertEqual(resp.status_code, 404)
        self.assertIn("User with id 99999 not found", resp.json()["detail"])

    def test_create_wake_session_nonexistent_alarm_rejected(self):
        """Requirement E: Nonexistent alarm_id is rejected with HTTP 404."""
        resp = self.client.post(
            "/api/v1/wake-sessions",
            json={"user_id": self.user_id, "alarm_id": 99999},
        )
        self.assertEqual(resp.status_code, 404)
        self.assertIn("Alarm with id 99999 not found", resp.json()["detail"])

    def test_create_wake_session_alarm_belonging_to_another_user_rejected(self):
        """Requirement F: Starting a session for another user's alarm is rejected with HTTP 400."""
        with self.TestingSessionLocal() as session:
            user2 = user_service.create_user(session, username="other_user", timezone="UTC")
            user2_id = user2.id

        # user2 attempts to trigger user1's alarm
        resp = self.client.post(
            "/api/v1/wake-sessions",
            json={"user_id": user2_id, "alarm_id": self.alarm_id},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("does not belong to user", resp.json()["detail"])

    def test_create_wake_session_inactive_alarm_rejected(self):
        """Requirement G: Inactive alarm cannot start a new wake session (HTTP 400)."""
        # Deactivate alarm
        self.client.delete(f"/api/v1/alarms/{self.alarm_id}")

        resp = self.client.post(
            "/api/v1/wake-sessions",
            json={"user_id": self.user_id, "alarm_id": self.alarm_id},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("inactive alarm", resp.json()["detail"].lower())

    def test_alarm_configuration_unchanged_after_session_creation(self):
        """Requirement H: Alarm configuration fields remain completely unchanged after session creation."""
        with self.TestingSessionLocal() as session:
            alarm_before = session.get(Alarm, self.alarm_id)
            time_before = alarm_before.time
            days_before = alarm_before.days_of_week
            type_before = alarm_before.selected_challenge_type
            diff_before = alarm_before.difficulty_preference
            active_before = alarm_before.is_active

        # Create session
        resp = self.client.post(
            "/api/v1/wake-sessions",
            json={"user_id": self.user_id, "alarm_id": self.alarm_id},
        )
        self.assertEqual(resp.status_code, 201)

        with self.TestingSessionLocal() as session:
            alarm_after = session.get(Alarm, self.alarm_id)
            self.assertEqual(alarm_after.time, time_before)
            self.assertEqual(alarm_after.days_of_week, days_before)
            self.assertEqual(alarm_after.selected_challenge_type, type_before)
            self.assertEqual(alarm_after.difficulty_preference, diff_before)
            self.assertEqual(alarm_after.is_active, active_before)

    def test_get_wake_session_by_id(self):
        """Requirement I: Retrieve WakeSession by ID returns 200, invalid ID returns 404."""
        resp = self.client.post(
            "/api/v1/wake-sessions",
            json={"user_id": self.user_id, "alarm_id": self.alarm_id},
        )
        session_id = resp.json()["id"]

        get_resp = self.client.get(f"/api/v1/wake-sessions/{session_id}")
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(get_resp.json()["id"], session_id)
        self.assertEqual(get_resp.json()["status"], "ringing")

        # Nonexistent ID
        not_found_resp = self.client.get("/api/v1/wake-sessions/99999")
        self.assertEqual(not_found_resp.status_code, 404)

    def test_user_wake_session_history_and_isolation(self):
        """Requirement J & K: User can retrieve history (newest first); another user's sessions are isolated."""
        # Create user 2 with an alarm
        with self.TestingSessionLocal() as session:
            user2 = user_service.create_user(session, username="user2", timezone="UTC")
            user2_id = user2.id
            alarm2 = alarm_service.create_alarm(
                session, user_id=user2_id, time="08:00",
                selected_challenge_type="math", difficulty_preference="easy"
            )
            alarm2_id = alarm2.id

        # Create session 1 for user 1 and complete it
        resp1 = self.client.post(
            "/api/v1/wake-sessions",
            json={"user_id": self.user_id, "alarm_id": self.alarm_id},
        )
        s1_id = resp1.json()["id"]
        self.client.patch(f"/api/v1/wake-sessions/{s1_id}/complete")

        # Create session 2 for user 1
        resp2 = self.client.post(
            "/api/v1/wake-sessions",
            json={"user_id": self.user_id, "alarm_id": self.alarm_id},
        )
        s2_id = resp2.json()["id"]

        # Create session for user 2
        resp_u2 = self.client.post(
            "/api/v1/wake-sessions",
            json={"user_id": user2_id, "alarm_id": alarm2_id},
        )
        s_u2_id = resp_u2.json()["id"]

        # User 1 history
        u1_history = self.client.get(f"/api/v1/users/{self.user_id}/wake-sessions")
        self.assertEqual(u1_history.status_code, 200)
        u1_sessions = u1_history.json()
        self.assertEqual(len(u1_sessions), 2)
        # Newest first
        self.assertEqual(u1_sessions[0]["id"], s2_id)
        self.assertEqual(u1_sessions[1]["id"], s1_id)
        # Ensure user2 session is NOT present
        self.assertNotIn(s_u2_id, [s["id"] for s in u1_sessions])

        # User 2 history
        u2_history = self.client.get(f"/api/v1/users/{user2_id}/wake-sessions")
        self.assertEqual(u2_history.status_code, 200)
        u2_sessions = u2_history.json()
        self.assertEqual(len(u2_sessions), 1)
        self.assertEqual(u2_sessions[0]["id"], s_u2_id)

    def test_lifecycle_transition_to_in_progress(self):
        """Requirement L: Valid lifecycle transition to IN_PROGRESS ('in_challenge')."""
        create_resp = self.client.post(
            "/api/v1/wake-sessions",
            json={"user_id": self.user_id, "alarm_id": self.alarm_id},
        )
        session_id = create_resp.json()["id"]

        patch_resp = self.client.patch(f"/api/v1/wake-sessions/{session_id}/in-progress")
        self.assertEqual(patch_resp.status_code, 200)
        self.assertEqual(patch_resp.json()["status"], "in_challenge")

    def test_lifecycle_transition_to_completed(self):
        """Requirement M & P: Valid transition to COMPLETED sets dismissed_time and wake delay."""
        create_resp = self.client.post(
            "/api/v1/wake-sessions",
            json={"user_id": self.user_id, "alarm_id": self.alarm_id},
        )
        session_id = create_resp.json()["id"]

        # First transition to in-progress
        self.client.patch(f"/api/v1/wake-sessions/{session_id}/in-progress")

        # Then complete
        comp_resp = self.client.patch(f"/api/v1/wake-sessions/{session_id}/complete")
        self.assertEqual(comp_resp.status_code, 200)
        data = comp_resp.json()
        self.assertEqual(data["status"], "completed")
        self.assertIsNotNone(data["dismissed_time"])  # Requirement P
        self.assertIsNotNone(data["total_wake_delay_seconds"])  # Requirement P
        self.assertGreaterEqual(data["total_wake_delay_seconds"], 0.0)

    def test_lifecycle_failure_transition(self):
        """Requirement N: Valid failure transition sets status to 'abandoned' and records dismissed_time."""
        create_resp = self.client.post(
            "/api/v1/wake-sessions",
            json={"user_id": self.user_id, "alarm_id": self.alarm_id},
        )
        session_id = create_resp.json()["id"]

        fail_resp = self.client.patch(f"/api/v1/wake-sessions/{session_id}/fail")
        self.assertEqual(fail_resp.status_code, 200)
        data = fail_resp.json()
        self.assertEqual(data["status"], "abandoned")
        self.assertIsNotNone(data["dismissed_time"])
        self.assertIsNotNone(data["total_wake_delay_seconds"])

    def test_invalid_lifecycle_transitions_rejected(self):
        """Requirement O: Invalid transitions are rejected with HTTP 400."""
        # 1. Complete a session
        create_resp = self.client.post(
            "/api/v1/wake-sessions",
            json={"user_id": self.user_id, "alarm_id": self.alarm_id},
        )
        s1_id = create_resp.json()["id"]
        self.client.patch(f"/api/v1/wake-sessions/{s1_id}/complete")

        # Attempting COMPLETED -> IN_PROGRESS must fail
        resp_comp_to_prog = self.client.patch(f"/api/v1/wake-sessions/{s1_id}/in-progress")
        self.assertEqual(resp_comp_to_prog.status_code, 400)
        self.assertIn("terminal status", resp_comp_to_prog.json()["detail"].lower())

        # Attempting COMPLETED -> FAIL must fail
        resp_comp_to_fail = self.client.patch(f"/api/v1/wake-sessions/{s1_id}/fail")
        self.assertEqual(resp_comp_to_fail.status_code, 400)
        self.assertIn("terminal status", resp_comp_to_fail.json()["detail"].lower())

        # 2. Abandon a session
        create_resp2 = self.client.post(
            "/api/v1/wake-sessions",
            json={"user_id": self.user_id, "alarm_id": self.alarm_id},
        )
        s2_id = create_resp2.json()["id"]
        self.client.patch(f"/api/v1/wake-sessions/{s2_id}/fail")

        # Attempting ABANDONED -> IN_PROGRESS must fail
        resp_aban_to_prog = self.client.patch(f"/api/v1/wake-sessions/{s2_id}/in-progress")
        self.assertEqual(resp_aban_to_prog.status_code, 400)
        self.assertIn("terminal status", resp_aban_to_prog.json()["detail"].lower())

        # Attempting ABANDONED -> COMPLETE must fail
        resp_aban_to_comp = self.client.patch(f"/api/v1/wake-sessions/{s2_id}/complete")
        self.assertEqual(resp_aban_to_comp.status_code, 400)
        self.assertIn("terminal status", resp_aban_to_comp.json()["detail"].lower())

        # 3. Redundant IN_PROGRESS transition
        create_resp3 = self.client.post(
            "/api/v1/wake-sessions",
            json={"user_id": self.user_id, "alarm_id": self.alarm_id},
        )
        s3_id = create_resp3.json()["id"]
        self.client.patch(f"/api/v1/wake-sessions/{s3_id}/in-progress")
        dup_prog = self.client.patch(f"/api/v1/wake-sessions/{s3_id}/in-progress")
        self.assertEqual(dup_prog.status_code, 400)
        self.assertIn("already in progress", dup_prog.json()["detail"].lower())

    def test_duplicate_active_session_protection(self):
        """Requirement Q: Duplicate active session protection prevents overlapping active sessions."""
        # Create first active session
        resp1 = self.client.post(
            "/api/v1/wake-sessions",
            json={"user_id": self.user_id, "alarm_id": self.alarm_id},
        )
        self.assertEqual(resp1.status_code, 201)
        s1_id = resp1.json()["id"]

        # Attempting to start another session for the same alarm while s1 is active ('ringing')
        resp_dup = self.client.post(
            "/api/v1/wake-sessions",
            json={"user_id": self.user_id, "alarm_id": self.alarm_id},
        )
        self.assertEqual(resp_dup.status_code, 409)
        self.assertIn("already exists", resp_dup.json()["detail"].lower())

        # Transition s1 to in_challenge
        self.client.patch(f"/api/v1/wake-sessions/{s1_id}/in-progress")

        # Still rejected while in_challenge
        resp_dup2 = self.client.post(
            "/api/v1/wake-sessions",
            json={"user_id": self.user_id, "alarm_id": self.alarm_id},
        )
        self.assertEqual(resp_dup2.status_code, 409)

        # Complete s1
        self.client.patch(f"/api/v1/wake-sessions/{s1_id}/complete")

        # Now creating a new session succeeds
        resp_next = self.client.post(
            "/api/v1/wake-sessions",
            json={"user_id": self.user_id, "alarm_id": self.alarm_id},
        )
        self.assertEqual(resp_next.status_code, 201)
        self.assertNotEqual(resp_next.json()["id"], s1_id)

    def test_service_layer_direct_exceptions(self):
        """Directly verify service layer raises custom domain exceptions."""
        with self.TestingSessionLocal() as session:
            # UserNotFoundError
            with self.assertRaises(UserNotFoundError):
                wake_session_service.create_wake_session(session, user_id=9999, alarm_id=self.alarm_id)

            # AlarmNotFoundError
            with self.assertRaises(AlarmNotFoundError):
                wake_session_service.create_wake_session(session, user_id=self.user_id, alarm_id=9999)

            # WakeSessionNotFoundError
            with self.assertRaises(WakeSessionNotFoundError):
                wake_session_service.transition_to_in_progress(session, session_id=9999)

            with self.assertRaises(WakeSessionNotFoundError):
                wake_session_service.complete_wake_session(session, session_id=9999)

            with self.assertRaises(WakeSessionNotFoundError):
                wake_session_service.fail_wake_session(session, session_id=9999)


if __name__ == "__main__":
    unittest.main()
