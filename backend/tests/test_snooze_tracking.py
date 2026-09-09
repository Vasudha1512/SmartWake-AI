"""Automated test suite for Snooze Tracking (Phase 2.6.3).

Validates:
A. Snooze from 'ringing' creates one SnoozeEvent.
B. Snooze changes session status from 'ringing' to 'snoozed'.
C. Snooze increments total_snooze_count (0 -> 1).
D. Second snooze creates another SnoozeEvent (snooze_number=2).
E. Second snooze does NOT create another WakeSession.
F. Multiple snoozes increment total_snooze_count correctly (e.g. 1 -> 2 -> 3).
G. Snooze from 'completed' session is rejected (InvalidSessionTransitionError / 400).
H. Snooze from 'abandoned' session is rejected (InvalidSessionTransitionError / 400).
I. Invalid / nonexistent WakeSession is rejected (WakeSessionNotFoundError / 404).
J. Wrong user ownership is rejected (AlarmOwnershipError / 400).
K. Wrong alarm ownership is rejected (AlarmOwnershipError / 400).
L. Non-positive / negative duration (<= 0) is rejected (InvalidSnoozeDurationError / 400).
M. Database transaction rollback works cleanly on failure without partial records.
N. SnoozeEvent is correctly linked to user, alarm, and wake_session.
O. Database state remains consistent after multiple snoozes.
P. API endpoint POST /api/v1/wake-sessions/{session_id}/snooze functions correctly.
"""
import asyncio
from datetime import datetime, timezone
import json
from unittest.mock import patch
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.exceptions import (
    AlarmOwnershipError,
    InvalidSessionTransitionError,
    InvalidSnoozeDurationError,
    UserNotFoundError,
    WakeSessionNotFoundError,
)
from backend.app.database.base import Base
import backend.app.database.session  # Ensures pragma listeners
from backend.app.database.session import get_db
from backend.app.main import app
from backend.app.models.alarm import Alarm
from backend.app.models.snooze_event import SnoozeEvent
from backend.app.models.user import User
from backend.app.models.wake_session import WakeSession
from backend.app.services import alarm_service, user_service, wake_session_service
from backend.app.services.wake_session_service import (
    STATUS_ABANDONED,
    STATUS_COMPLETED,
    STATUS_RINGING,
    STATUS_SNOOZED,
    complete_wake_session,
    create_wake_session,
    fail_wake_session,
    get_snooze_events_by_session,
    record_snooze,
)


class SimpleASGIClient:
    """Lightweight ASGI test client using Python standard library asyncio."""

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

    def post(self, path: str, json: dict = None, headers: dict = None):
        return self._request("POST", path, json_data=json, headers=headers)


class TestSnoozeTracking(unittest.TestCase):
    """Test suite for Phase 2.6.3 Snooze Tracking."""

    @classmethod
    def setUpClass(cls):
        """Set up isolated in-memory SQLite database and FastAPI client override."""
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
        """Clean up database and clear dependency overrides."""
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=cls.engine)
        cls.engine.dispose()

    def setUp(self):
        """Clear database tables before each test for clean isolation."""
        with self.TestingSessionLocal() as session:
            for table in reversed(Base.metadata.sorted_tables):
                session.execute(table.delete())
            session.commit()

        # Seed standard user and alarm for tests
        with self.TestingSessionLocal() as db:
            self.user = user_service.create_user(db, username="snooze_user", timezone="Asia/Kolkata")
            self.alarm = alarm_service.create_alarm(
                db,
                user_id=self.user.id,
                time="07:00",
                selected_challenge_type="math",
                days_of_week=[0, 1, 2, 3, 4],
                is_active=True,
            )
            self.user_id = self.user.id
            self.alarm_id = self.alarm.id

    # ----------------------------------------------------------------------
    # Requirement A, B, C: Single snooze from ringing
    # ----------------------------------------------------------------------
    def test_a_b_c_snooze_from_ringing(self):
        """Snoozing a ringing session creates 1 SnoozeEvent, changes status to 'snoozed',
        and increments total_snooze_count from 0 to 1.
        """
        with self.TestingSessionLocal() as db:
            sess = create_wake_session(db, user_id=self.user_id, alarm_id=self.alarm_id)
            self.assertEqual(sess.status, STATUS_RINGING)
            self.assertEqual(sess.total_snooze_count, 0)

            # Record snooze
            res = record_snooze(db, session_id=sess.id)
            updated_session, snooze_event = res

            # Requirement B: status is snoozed
            self.assertEqual(updated_session.status, STATUS_SNOOZED)
            # Requirement C: total_snooze_count incremented to 1
            self.assertEqual(updated_session.total_snooze_count, 1)

            # Requirement A: 1 SnoozeEvent created with snooze_number=1
            self.assertIsNotNone(snooze_event.id)
            self.assertEqual(snooze_event.snooze_number, 1)
            self.assertEqual(snooze_event.wake_session_id, sess.id)
            self.assertEqual(snooze_event.snooze_duration_minutes, 5)
            self.assertIsNone(snooze_event.ring_resumed_at)

            # Verify in DB
            events = get_snooze_events_by_session(db, sess.id)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].id, snooze_event.id)

    # ----------------------------------------------------------------------
    # Requirement D, E, F: Repeated snoozes within same session
    # ----------------------------------------------------------------------
    def test_d_e_f_repeated_snoozes_same_session(self):
        """Multiple snoozes create subsequent SnoozeEvents, keep the SAME WakeSession,
        and increment total_snooze_count accurately (1 -> 2 -> 3).
        """
        with self.TestingSessionLocal() as db:
            sess = create_wake_session(db, user_id=self.user_id, alarm_id=self.alarm_id)

            # Snooze 1
            res1 = record_snooze(db, session_id=sess.id, duration_minutes=5)
            self.assertEqual(res1.wake_session.total_snooze_count, 1)
            self.assertEqual(res1.snooze_event.snooze_number, 1)

            # Snooze 2 (Requirement D)
            res2 = record_snooze(db, session_id=sess.id, duration_minutes=10)
            self.assertEqual(res2.wake_session.total_snooze_count, 2)
            self.assertEqual(res2.snooze_event.snooze_number, 2)
            self.assertEqual(res2.snooze_event.snooze_duration_minutes, 10)
            self.assertEqual(res2.wake_session.status, STATUS_SNOOZED)

            # Snooze 3 (Requirement F)
            res3 = record_snooze(db, session_id=sess.id, duration_minutes=5)
            self.assertEqual(res3.wake_session.total_snooze_count, 3)
            self.assertEqual(res3.snooze_event.snooze_number, 3)

            # Requirement E: Exactly ONE WakeSession exists in the database
            all_sessions = list(db.scalars(select(WakeSession)).all())
            self.assertEqual(len(all_sessions), 1)
            self.assertEqual(all_sessions[0].id, sess.id)

            # Exactly THREE SnoozeEvents exist in the database
            all_events = get_snooze_events_by_session(db, sess.id)
            self.assertEqual(len(all_events), 3)
            self.assertEqual([e.snooze_number for e in all_events], [1, 2, 3])

    # ----------------------------------------------------------------------
    # Requirement G: Snooze from completed session is rejected
    # ----------------------------------------------------------------------
    def test_g_snooze_completed_session_rejected(self):
        """Snoozing a completed session raises InvalidSessionTransitionError."""
        with self.TestingSessionLocal() as db:
            sess = create_wake_session(db, user_id=self.user_id, alarm_id=self.alarm_id)
            complete_wake_session(db, sess.id)
            self.assertEqual(sess.status, STATUS_COMPLETED)

            with self.assertRaises(InvalidSessionTransitionError) as ctx:
                record_snooze(db, session_id=sess.id)
            self.assertIn("terminal status 'completed'", str(ctx.exception))

            # No snooze events recorded
            events = get_snooze_events_by_session(db, sess.id)
            self.assertEqual(len(events), 0)

    # ----------------------------------------------------------------------
    # Requirement H: Snooze from abandoned session is rejected
    # ----------------------------------------------------------------------
    def test_h_snooze_abandoned_session_rejected(self):
        """Snoozing an abandoned session raises InvalidSessionTransitionError."""
        with self.TestingSessionLocal() as db:
            sess = create_wake_session(db, user_id=self.user_id, alarm_id=self.alarm_id)
            fail_wake_session(db, sess.id)
            self.assertEqual(sess.status, STATUS_ABANDONED)

            with self.assertRaises(InvalidSessionTransitionError) as ctx:
                record_snooze(db, session_id=sess.id)
            self.assertIn("terminal status 'abandoned'", str(ctx.exception))

            events = get_snooze_events_by_session(db, sess.id)
            self.assertEqual(len(events), 0)

    # ----------------------------------------------------------------------
    # Requirement I: Invalid / nonexistent WakeSession rejected
    # ----------------------------------------------------------------------
    def test_i_nonexistent_wake_session_rejected(self):
        """Snoozing a nonexistent session ID raises WakeSessionNotFoundError."""
        with self.TestingSessionLocal() as db:
            with self.assertRaises(WakeSessionNotFoundError):
                record_snooze(db, session_id=99999)

    # ----------------------------------------------------------------------
    # Requirement J: Wrong user ownership rejected
    # ----------------------------------------------------------------------
    def test_j_wrong_user_ownership_rejected(self):
        """Passing mismatched user_id raises AlarmOwnershipError or UserNotFoundError."""
        with self.TestingSessionLocal() as db:
            other_user = user_service.create_user(db, username="other_user", timezone="UTC")
            sess = create_wake_session(db, user_id=self.user_id, alarm_id=self.alarm_id)

            # Mismatched valid user
            with self.assertRaises(AlarmOwnershipError) as ctx:
                record_snooze(db, session_id=sess.id, user_id=other_user.id)
            self.assertIn(f"belongs to user {self.user_id}", str(ctx.exception))

            # Nonexistent user
            with self.assertRaises(UserNotFoundError):
                record_snooze(db, session_id=sess.id, user_id=88888)

    # ----------------------------------------------------------------------
    # Requirement K: Wrong alarm ownership rejected
    # ----------------------------------------------------------------------
    def test_k_wrong_alarm_ownership_rejected(self):
        """Passing mismatched alarm_id raises AlarmOwnershipError."""
        with self.TestingSessionLocal() as db:
            other_alarm = alarm_service.create_alarm(
                db,
                user_id=self.user_id,
                time="08:30",
                selected_challenge_type="dance",
            )
            sess = create_wake_session(db, user_id=self.user_id, alarm_id=self.alarm_id)

            with self.assertRaises(AlarmOwnershipError) as ctx:
                record_snooze(db, session_id=sess.id, alarm_id=other_alarm.id)
            self.assertIn(f"belongs to alarm {self.alarm_id}", str(ctx.exception))

    # ----------------------------------------------------------------------
    # Requirement L: Negative / zero duration rejected
    # ----------------------------------------------------------------------
    def test_l_negative_or_zero_duration_rejected(self):
        """Duration <= 0 is rejected with InvalidSnoozeDurationError."""
        with self.TestingSessionLocal() as db:
            sess = create_wake_session(db, user_id=self.user_id, alarm_id=self.alarm_id)

            with self.assertRaises(InvalidSnoozeDurationError):
                record_snooze(db, session_id=sess.id, duration_minutes=-5)

            with self.assertRaises(InvalidSnoozeDurationError):
                record_snooze(db, session_id=sess.id, duration_minutes=0)

    # ----------------------------------------------------------------------
    # Requirement M: Database transaction rollback on failure
    # ----------------------------------------------------------------------
    def test_m_database_transaction_rollback(self):
        """Unexpected database error rolls back both SnoozeEvent and WakeSession changes."""
        with self.TestingSessionLocal() as db:
            sess = create_wake_session(db, user_id=self.user_id, alarm_id=self.alarm_id)
            initial_count = sess.total_snooze_count
            initial_status = sess.status

            with patch.object(db, "commit", side_effect=RuntimeError("Simulated commit error")):
                with self.assertRaises(RuntimeError):
                    record_snooze(db, session_id=sess.id)

            # Re-read session from DB
            db.rollback()
            fresh_session = db.get(WakeSession, sess.id)
            self.assertEqual(fresh_session.total_snooze_count, initial_count)
            self.assertEqual(fresh_session.status, initial_status)

            # Zero SnoozeEvents persisted
            events = get_snooze_events_by_session(db, sess.id)
            self.assertEqual(len(events), 0)

    # ----------------------------------------------------------------------
    # Requirement N: SnoozeEvent correctly linked to user, alarm, session
    # ----------------------------------------------------------------------
    def test_n_snooze_event_relationships_linked(self):
        """SnoozeEvent links to wake_session, which links to user and alarm."""
        with self.TestingSessionLocal() as db:
            sess = create_wake_session(db, user_id=self.user_id, alarm_id=self.alarm_id)
            _, snooze_event = record_snooze(
                db,
                session_id=sess.id,
                user_id=self.user_id,
                alarm_id=self.alarm_id,
                duration_minutes=7,
            )

            # Direct relationship
            self.assertEqual(snooze_event.wake_session.id, sess.id)
            # Associated user
            self.assertEqual(snooze_event.wake_session.user.id, self.user_id)
            # Associated alarm
            self.assertEqual(snooze_event.wake_session.alarm.id, self.alarm_id)

    # ----------------------------------------------------------------------
    # Requirement O: Database state remains consistent
    # ----------------------------------------------------------------------
    def test_o_database_state_consistency(self):
        """Database state and foreign key cascade remain consistent."""
        with self.TestingSessionLocal() as db:
            sess = create_wake_session(db, user_id=self.user_id, alarm_id=self.alarm_id)
            record_snooze(db, session_id=sess.id)
            record_snooze(db, session_id=sess.id)

            sess_reloaded = db.get(WakeSession, sess.id)
            self.assertEqual(sess_reloaded.total_snooze_count, 2)
            self.assertEqual(len(sess_reloaded.snooze_events), 2)

    # ----------------------------------------------------------------------
    # Requirement P: API Endpoint POST /api/v1/wake-sessions/{session_id}/snooze
    # ----------------------------------------------------------------------
    def test_p_api_snooze_endpoint_success_and_errors(self):
        """Test the RESTful API endpoint for snoozing wake sessions."""
        with self.TestingSessionLocal() as db:
            sess = create_wake_session(db, user_id=self.user_id, alarm_id=self.alarm_id)
            sess_id = sess.id

        # 1. Successful snooze via API with empty payload (defaults to 5 mins)
        resp = self.client.post(f"/api/v1/wake-sessions/{sess_id}/snooze", json={})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["id"], sess_id)
        self.assertEqual(data["status"], "snoozed")
        self.assertEqual(data["total_snooze_count"], 1)

        # 2. Second snooze via API with explicit duration and ownership
        resp2 = self.client.post(
            f"/api/v1/wake-sessions/{sess_id}/snooze",
            json={
                "user_id": self.user_id,
                "alarm_id": self.alarm_id,
                "duration_minutes": 10,
            },
        )
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json()
        self.assertEqual(data2["total_snooze_count"], 2)
        self.assertEqual(data2["status"], "snoozed")

        # 3. Mismatched user ownership -> 400 Bad Request
        with self.TestingSessionLocal() as db:
            other_u = user_service.create_user(db, username="api_other_user", timezone="UTC")
            other_uid = other_u.id

        resp_bad_user = self.client.post(
            f"/api/v1/wake-sessions/{sess_id}/snooze",
            json={"user_id": other_uid},
        )
        self.assertEqual(resp_bad_user.status_code, 400)

        # 4. Nonexistent session ID -> 404 Not Found
        resp_404 = self.client.post("/api/v1/wake-sessions/99999/snooze", json={})
        self.assertEqual(resp_404.status_code, 404)

        # 5. Negative duration -> 400 Bad Request
        resp_neg = self.client.post(
            f"/api/v1/wake-sessions/{sess_id}/snooze",
            json={"duration_minutes": -3},
        )
        self.assertEqual(resp_neg.status_code, 400)


if __name__ == "__main__":
    unittest.main()
