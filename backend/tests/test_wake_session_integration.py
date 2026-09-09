"""Automated test suite for Wake Session Integration (Phase 2.6.4).

Validates end-to-end integration of Alarm, Scheduler, WakeSession, and SnoozeEvent:
A. Due alarm creates exactly one WakeSession.
B. Repeated scheduler execution does not duplicate the session.
C. WakeSession contains the correct alarm_id.
D. WakeSession contains the correct user_id.
E. WakeSession scheduled_time represents the correct occurrence.
F. Initial state is ringing.
G. Snoozing the scheduler-created session creates SnoozeEvent #1.
H. Snoozing changes the SAME session to snoozed.
I. Second snooze uses the SAME session.
J. Snooze count remains consistent.
K. Completed occurrence cannot create another session for the same occurrence.
L. Abandoned occurrence cannot create another session for the same occurrence.
M. Snoozed occurrence cannot create another session.
N. Inactive alarm creates no session.
O. Recurring alarm creates one session per valid recurrence.
P. Wrong-user operations remain rejected.
Q. Resume ringing transition (snoozed -> ringing) updates status and sets ring_resumed_at.
R. API endpoint PATCH /api/v1/wake-sessions/{session_id}/resume functions correctly.
S. Database integrity verified (FK constraints, cascading, no orphaned rows).
"""
import asyncio
from datetime import datetime, timezone
import json
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.exceptions import (
    AlarmOwnershipError,
    InvalidSessionTransitionError,
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
from backend.app.services.alarm_service import create_alarm
from backend.app.services.scheduler_service import process_due_alarms
from backend.app.services.user_service import create_user
from backend.app.services.wake_session_service import (
    STATUS_ABANDONED,
    STATUS_COMPLETED,
    STATUS_IN_CHALLENGE,
    STATUS_RINGING,
    STATUS_SNOOZED,
    complete_wake_session,
    fail_wake_session,
    get_snooze_events_by_session,
    record_snooze,
    resume_ringing,
    transition_to_in_progress,
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

    def patch(self, path: str, json: dict = None, headers: dict = None):
        return self._request("PATCH", path, json_data=json, headers=headers)

    def post(self, path: str, json: dict = None, headers: dict = None):
        return self._request("POST", path, json_data=json, headers=headers)


class TestWakeSessionIntegration(unittest.TestCase):
    """Test suite for Phase 2.6.4 Wake Session Integration."""

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

        # Seed standard user and alarm
        with self.TestingSessionLocal() as db:
            self.user = create_user(db, username="integration_user", timezone="Asia/Kolkata")
            self.alarm = create_alarm(
                db,
                user_id=self.user.id,
                time="07:00",
                selected_challenge_type="tongue_twister",
                difficulty_preference="medium",
                days_of_week=[0, 1, 2, 3, 4],  # Mon-Fri
                is_active=True,
            )
            self.user_id = self.user.id
            self.alarm_id = self.alarm.id

    # ----------------------------------------------------------------------
    # Requirements A, C, D, E, F: Scheduler creates canonical WakeSession
    # ----------------------------------------------------------------------
    def test_a_c_d_e_f_due_alarm_creates_canonical_wake_session(self):
        """Due alarm creates exactly one canonical WakeSession with correct properties."""
        with self.TestingSessionLocal() as db:
            # Wednesday 2026-09-09 01:30:15 UTC == 07:00:15 Asia/Kolkata
            t_due = datetime(2026, 9, 9, 1, 30, 15, tzinfo=timezone.utc)
            res = process_due_alarms(db, current_time=t_due)

            # Requirement A: exactly 1 created
            self.assertEqual(res.created, 1)
            self.assertEqual(res.processed, 1)
            self.assertEqual(res.skipped, 0)
            self.assertEqual(len(res.sessions), 1)

            session = res.sessions[0]
            # Requirement C: correct alarm_id
            self.assertEqual(session.alarm_id, self.alarm_id)
            # Requirement D: correct user_id
            self.assertEqual(session.user_id, self.user_id)
            # Requirement F: initial state is ringing
            self.assertEqual(session.status, STATUS_RINGING)
            self.assertEqual(session.total_snooze_count, 0)

            # Requirement E: scheduled_time matches normalized occurrence in UTC (01:30:00)
            self.assertEqual(session.scheduled_time.hour, 1)
            self.assertEqual(session.scheduled_time.minute, 30)
            self.assertEqual(session.scheduled_time.second, 0)

    # ----------------------------------------------------------------------
    # Requirement B: Repeated scheduler execution does not duplicate
    # ----------------------------------------------------------------------
    def test_b_repeated_scheduler_execution_does_not_duplicate(self):
        """Scheduler called multiple times during the same minute does not duplicate session."""
        with self.TestingSessionLocal() as db:
            t1 = datetime(2026, 9, 9, 1, 30, 5, tzinfo=timezone.utc)
            t2 = datetime(2026, 9, 9, 1, 30, 25, tzinfo=timezone.utc)
            t3 = datetime(2026, 9, 9, 1, 30, 55, tzinfo=timezone.utc)

            res1 = process_due_alarms(db, current_time=t1)
            res2 = process_due_alarms(db, current_time=t2)
            res3 = process_due_alarms(db, current_time=t3)

            self.assertEqual(res1.created, 1)
            self.assertEqual(res2.created, 0)
            self.assertEqual(res3.created, 0)

            all_sessions = list(db.scalars(select(WakeSession)).all())
            self.assertEqual(len(all_sessions), 1)

    # ----------------------------------------------------------------------
    # Requirements G, H, I, J: Snooze integration on SAME WakeSession
    # ----------------------------------------------------------------------
    def test_g_h_i_j_snooze_integration_on_same_session(self):
        """Snoozing uses the SAME WakeSession, updates status to 'snoozed',
        creates child SnoozeEvents, and maintains total_snooze_count accurately.
        """
        with self.TestingSessionLocal() as db:
            t_due = datetime(2026, 9, 9, 1, 30, 10, tzinfo=timezone.utc)
            res = process_due_alarms(db, current_time=t_due)
            created_session = res.sessions[0]
            session_id = created_session.id

            # Requirement G & H: First snooze
            snooze_res1 = record_snooze(db, session_id=session_id, duration_minutes=5)
            self.assertEqual(snooze_res1.wake_session.id, session_id)
            self.assertEqual(snooze_res1.wake_session.status, STATUS_SNOOZED)
            self.assertEqual(snooze_res1.wake_session.total_snooze_count, 1)
            self.assertEqual(snooze_res1.snooze_event.snooze_number, 1)

            # Requirement I & J: Second snooze on SAME session
            snooze_res2 = record_snooze(db, session_id=session_id, duration_minutes=10)
            self.assertEqual(snooze_res2.wake_session.id, session_id)
            self.assertEqual(snooze_res2.wake_session.status, STATUS_SNOOZED)
            self.assertEqual(snooze_res2.wake_session.total_snooze_count, 2)
            self.assertEqual(snooze_res2.snooze_event.snooze_number, 2)

            # Verify total WakeSession count remains 1
            all_sessions = list(db.scalars(select(WakeSession)).all())
            self.assertEqual(len(all_sessions), 1)

            # Verify SnoozeEvents are child records
            events = get_snooze_events_by_session(db, session_id)
            self.assertEqual(len(events), 2)
            self.assertEqual([e.snooze_number for e in events], [1, 2])
            self.assertEqual(events[0].snooze_duration_minutes, 5)
            self.assertEqual(events[1].snooze_duration_minutes, 10)

    # ----------------------------------------------------------------------
    # Requirements K, L, M: Occurrence safety across terminal and snoozed states
    # ----------------------------------------------------------------------
    def test_k_l_m_occurrence_safety_terminal_and_snoozed(self):
        """Completed, abandoned, or snoozed occurrences prevent duplicate creation in same minute."""
        with self.TestingSessionLocal() as db:
            t1 = datetime(2026, 9, 9, 1, 30, 5, tzinfo=timezone.utc)
            res1 = process_due_alarms(db, current_time=t1)
            sess = res1.sessions[0]

            # Requirement M: While snoozed, scheduler does not create duplicate
            record_snooze(db, session_id=sess.id)
            t2 = datetime(2026, 9, 9, 1, 30, 20, tzinfo=timezone.utc)
            res2 = process_due_alarms(db, current_time=t2)
            self.assertEqual(res2.created, 0)
            self.assertEqual(res2.skipped, 1)

            # Requirement K: Once completed, scheduler in same minute does not create duplicate
            complete_wake_session(db, sess.id)
            self.assertEqual(sess.status, STATUS_COMPLETED)
            t3 = datetime(2026, 9, 9, 1, 30, 40, tzinfo=timezone.utc)
            res3 = process_due_alarms(db, current_time=t3)
            self.assertEqual(res3.created, 0)
            self.assertEqual(res3.skipped, 1)

    def test_l_abandoned_occurrence_prevents_duplicate(self):
        """Abandoned occurrence prevents duplicate creation in same minute."""
        with self.TestingSessionLocal() as db:
            t1 = datetime(2026, 9, 9, 1, 30, 5, tzinfo=timezone.utc)
            res1 = process_due_alarms(db, current_time=t1)
            sess = res1.sessions[0]

            fail_wake_session(db, sess.id)
            self.assertEqual(sess.status, STATUS_ABANDONED)

            t2 = datetime(2026, 9, 9, 1, 30, 30, tzinfo=timezone.utc)
            res2 = process_due_alarms(db, current_time=t2)
            self.assertEqual(res2.created, 0)
            self.assertEqual(res2.skipped, 1)

    # ----------------------------------------------------------------------
    # Requirement N: Inactive alarm creates no session
    # ----------------------------------------------------------------------
    def test_n_inactive_alarm_creates_no_session(self):
        """Deactivated alarm is ignored by the scheduler."""
        with self.TestingSessionLocal() as db:
            alarm = db.get(Alarm, self.alarm_id)
            alarm.is_active = False
            db.commit()

            t = datetime(2026, 9, 9, 1, 30, 0, tzinfo=timezone.utc)
            res = process_due_alarms(db, current_time=t)
            self.assertEqual(res.created, 0)
            self.assertEqual(res.processed, 0)


    # ----------------------------------------------------------------------
    # Requirement O: Recurring alarm creates one session per valid recurrence
    # ----------------------------------------------------------------------
    def test_o_recurring_alarm_creates_session_per_recurrence(self):
        """Wednesday 07:00 creates Session 1; Thursday 07:00 creates Session 2."""
        with self.TestingSessionLocal() as db:
            # Day 1: Wednesday 07:00 local (01:30 UTC)
            t_wed = datetime(2026, 9, 9, 1, 30, 0, tzinfo=timezone.utc)
            res_wed = process_due_alarms(db, current_time=t_wed)
            self.assertEqual(res_wed.created, 1)
            sess_wed = res_wed.sessions[0]
            # Complete Wednesday session
            complete_wake_session(db, sess_wed.id)

            # Day 2: Thursday 07:00 local (01:30 UTC)
            t_thu = datetime(2026, 9, 10, 1, 30, 0, tzinfo=timezone.utc)
            res_thu = process_due_alarms(db, current_time=t_thu)
            self.assertEqual(res_thu.created, 1)
            sess_thu = res_thu.sessions[0]

            self.assertNotEqual(sess_wed.id, sess_thu.id)
            all_sessions = list(db.scalars(select(WakeSession)).all())
            self.assertEqual(len(all_sessions), 2)

    # ----------------------------------------------------------------------
    # Requirement P: Wrong user operations rejected
    # ----------------------------------------------------------------------
    def test_p_wrong_user_operations_rejected(self):
        """Attempting to snooze or modify another user's session is rejected."""
        with self.TestingSessionLocal() as db:
            other_user = create_user(db, username="other_intruder", timezone="UTC")
            t = datetime(2026, 9, 9, 1, 30, 0, tzinfo=timezone.utc)
            res = process_due_alarms(db, current_time=t)
            sess = res.sessions[0]

            # Rejection with wrong user_id
            with self.assertRaises(AlarmOwnershipError):
                record_snooze(db, session_id=sess.id, user_id=other_user.id)

    # ----------------------------------------------------------------------
    # Requirement Q: Resume ringing lifecycle transition (snoozed -> ringing)
    # ----------------------------------------------------------------------
    def test_q_resume_ringing_lifecycle_transition(self):
        """Resuming a snoozed session updates status to 'ringing' and sets ring_resumed_at."""
        with self.TestingSessionLocal() as db:
            t = datetime(2026, 9, 9, 1, 30, 0, tzinfo=timezone.utc)
            res = process_due_alarms(db, current_time=t)
            sess = res.sessions[0]

            # Record snooze
            record_snooze(db, session_id=sess.id, duration_minutes=5)
            self.assertEqual(sess.status, STATUS_SNOOZED)

            snooze_event = sess.snooze_events[0]
            self.assertIsNone(snooze_event.ring_resumed_at)

            # Resume ringing
            t_resume = datetime(2026, 9, 9, 1, 35, 0)
            resumed_sess = resume_ringing(db, session_id=sess.id, resumed_at=t_resume)
            self.assertEqual(resumed_sess.status, STATUS_RINGING)

            # Verify ring_resumed_at populated on SnoozeEvent
            db.refresh(snooze_event)
            self.assertEqual(snooze_event.ring_resumed_at, t_resume)

            # Resuming an already ringing session is rejected
            with self.assertRaises(InvalidSessionTransitionError):
                resume_ringing(db, session_id=sess.id)

            # Resuming a completed session is rejected
            complete_wake_session(db, sess.id)
            with self.assertRaises(InvalidSessionTransitionError):
                resume_ringing(db, session_id=sess.id)

    # ----------------------------------------------------------------------
    # Requirement R: API Endpoint PATCH /api/v1/wake-sessions/{id}/resume
    # ----------------------------------------------------------------------
    def test_r_api_resume_endpoint(self):
        """Test REST API endpoint PATCH /api/v1/wake-sessions/{session_id}/resume."""
        with self.TestingSessionLocal() as db:
            t = datetime(2026, 9, 9, 1, 30, 0, tzinfo=timezone.utc)
            res = process_due_alarms(db, current_time=t)
            sess_id = res.sessions[0].id
            record_snooze(db, session_id=sess_id)

        # Successful resume via API
        resp = self.client.patch(f"/api/v1/wake-sessions/{sess_id}/resume")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["id"], sess_id)
        self.assertEqual(data["status"], "ringing")

        # Invalid transition: resuming already ringing session returns 400
        resp_invalid = self.client.patch(f"/api/v1/wake-sessions/{sess_id}/resume")
        self.assertEqual(resp_invalid.status_code, 400)

        # Nonexistent session returns 404
        resp_404 = self.client.patch("/api/v1/wake-sessions/99999/resume")
        self.assertEqual(resp_404.status_code, 404)

    # ----------------------------------------------------------------------
    # Requirement S: Database state and cascading relationships
    # ----------------------------------------------------------------------
    def test_s_database_state_and_cascade(self):
        """Deleting a WakeSession cascades to child SnoozeEvents."""
        with self.TestingSessionLocal() as db:
            t = datetime(2026, 9, 9, 1, 30, 0, tzinfo=timezone.utc)
            res = process_due_alarms(db, current_time=t)
            sess = res.sessions[0]
            record_snooze(db, session_id=sess.id)
            record_snooze(db, session_id=sess.id)

            sess_id = sess.id
            events = get_snooze_events_by_session(db, sess_id)
            self.assertEqual(len(events), 2)

            # Delete wake session
            db.delete(sess)
            db.commit()

            # Verify cascading deletion of child SnoozeEvents
            events_after = get_snooze_events_by_session(db, sess_id)
            self.assertEqual(len(events_after), 0)


if __name__ == "__main__":
    unittest.main()
