"""Automated test suite for Scheduler Execution (Phase 2.6.2.2).

Validates:
A. Due active alarm creates one WakeSession.
B. Non-due alarm creates no WakeSession.
C. Inactive alarm creates no WakeSession.
D. Recurrence rules are respected (e.g. weekend vs weekday).
E. Timezone conversion is respected (Asia/Kolkata vs America/New_York).
F. Repeated execution during the same minute does not create duplicate active sessions (07:00:05, 07:00:20, 07:00:50).
G. Existing active WakeSession causes scheduler to skip creation.
H. Multiple due alarms create separate WakeSessions.
I. User ownership remains correct (session.user_id == alarm.user_id).
J. Created session starts in 'ringing' state with zero snooze count.
K. Existing terminal sessions do not corrupt scheduler behavior (terminal in same minute skips; next day triggers new session).
L. Database state is correct after execution and alarm configuration remains completely unmodified.
M. Failure handling does not leave an invalid partial transaction.
"""
from datetime import datetime, timezone
from unittest.mock import patch
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.database.base import Base
import backend.app.database.session  # Ensures pragma listeners
from backend.app.models.alarm import Alarm
from backend.app.models.user import User
from backend.app.models.wake_session import WakeSession
from backend.app.services.alarm_service import create_alarm
from backend.app.services.scheduler_service import (
    SchedulerExecutionResult,
    get_occurrence_scheduled_time,
    has_active_or_occurrence_session,
    process_due_alarms,
)
from backend.app.services.user_service import create_user
from backend.app.services.wake_session_service import (
    STATUS_RINGING,
    complete_wake_session,
    create_wake_session,
    transition_to_in_progress,
)


class TestSchedulerExecution(unittest.TestCase):
    """Test suite for Phase 2.6.2.2 Scheduler Execution."""

    @classmethod
    def setUpClass(cls):
        """Set up isolated in-memory SQLite database."""
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
        """Clean up in-memory database."""
        Base.metadata.drop_all(bind=cls.engine)
        cls.engine.dispose()

    def setUp(self):
        """Clear database tables before each test for clean isolation."""
        with self.TestingSessionLocal() as session:
            for table in reversed(Base.metadata.sorted_tables):
                session.execute(table.delete())
            session.commit()

    # ----------------------------------------------------------------------
    # Requirement A: Due active alarm creates one WakeSession
    # ----------------------------------------------------------------------
    def test_a_due_active_alarm_creates_one_wake_session(self):
        """Active due alarm creates exactly one WakeSession in the database."""
        with self.TestingSessionLocal() as db:
            user = create_user(db, username="user_a", timezone="Asia/Kolkata")
            alarm = create_alarm(
                db,
                user_id=user.id,
                time="07:00",
                selected_challenge_type="math",
                days_of_week=[0, 1, 2, 3, 4],  # Mon-Fri
                is_active=True,
            )

            # Wednesday 2026-09-09 01:30:00 UTC == 07:00:00 Asia/Kolkata
            dt_utc = datetime(2026, 9, 9, 1, 30, 0, tzinfo=timezone.utc)
            result = process_due_alarms(db, current_time=dt_utc)

            self.assertEqual(result.processed, 1)
            self.assertEqual(result.created, 1)
            self.assertEqual(result.skipped, 0)
            self.assertEqual(len(result.sessions), 1)

            created_session = result.sessions[0]
            self.assertEqual(created_session.alarm_id, alarm.id)
            self.assertEqual(created_session.user_id, user.id)
            self.assertEqual(created_session.status, STATUS_RINGING)

            # Check DB persistence
            db_sessions = list(db.scalars(select(WakeSession)).all())
            self.assertEqual(len(db_sessions), 1)
            self.assertEqual(db_sessions[0].id, created_session.id)

    # ----------------------------------------------------------------------
    # Requirement B: Non-due alarm creates no WakeSession
    # ----------------------------------------------------------------------
    def test_b_non_due_alarm_creates_no_wake_session(self):
        """Alarm configured for a different time creates no session."""
        with self.TestingSessionLocal() as db:
            user = create_user(db, username="user_b", timezone="Asia/Kolkata")
            create_alarm(
                db,
                user_id=user.id,
                time="08:00",  # Different time
                selected_challenge_type="dance",
                days_of_week=[0, 1, 2, 3, 4],
                is_active=True,
            )

            # Current time is 07:00 local (01:30 UTC)
            dt_utc = datetime(2026, 9, 9, 1, 30, 0, tzinfo=timezone.utc)
            result = process_due_alarms(db, current_time=dt_utc)

            self.assertEqual(result.processed, 0)
            self.assertEqual(result.created, 0)
            self.assertEqual(result.skipped, 0)
            self.assertEqual(len(result.sessions), 0)

            db_sessions = list(db.scalars(select(WakeSession)).all())
            self.assertEqual(len(db_sessions), 0)

    # ----------------------------------------------------------------------
    # Requirement C: Inactive alarm creates no WakeSession
    # ----------------------------------------------------------------------
    def test_c_inactive_alarm_creates_no_wake_session(self):
        """Inactive alarm matching time and day creates no WakeSession."""
        with self.TestingSessionLocal() as db:
            user = create_user(db, username="user_c", timezone="Asia/Kolkata")
            create_alarm(
                db,
                user_id=user.id,
                time="07:00",
                selected_challenge_type="tongue_twister",
                days_of_week=[0, 1, 2, 3, 4],
                is_active=False,  # Inactive
            )

            dt_utc = datetime(2026, 9, 9, 1, 30, 0, tzinfo=timezone.utc)
            result = process_due_alarms(db, current_time=dt_utc)

            self.assertEqual(result.processed, 0)
            self.assertEqual(result.created, 0)
            self.assertEqual(len(result.sessions), 0)

            db_sessions = list(db.scalars(select(WakeSession)).all())
            self.assertEqual(len(db_sessions), 0)

    # ----------------------------------------------------------------------
    # Requirement D: Recurrence rules are respected
    # ----------------------------------------------------------------------
    def test_d_recurrence_rules_respected(self):
        """Alarms only create sessions on their configured recurrence days."""
        with self.TestingSessionLocal() as db:
            user = create_user(db, username="user_d", timezone="UTC")
            create_alarm(
                db,
                user_id=user.id,
                time="09:00",
                selected_challenge_type="memory",
                days_of_week=[5, 6],  # Weekend only
                is_active=True,
            )

            # Wednesday (day 2) 09:00 UTC -> no session
            dt_wed = datetime(2026, 9, 9, 9, 0, 0, tzinfo=timezone.utc)
            res_wed = process_due_alarms(db, current_time=dt_wed)
            self.assertEqual(res_wed.created, 0)

            # Saturday (day 5) 09:00 UTC -> creates session
            dt_sat = datetime(2026, 9, 12, 9, 0, 0, tzinfo=timezone.utc)
            res_sat = process_due_alarms(db, current_time=dt_sat)
            self.assertEqual(res_sat.created, 1)

    # ----------------------------------------------------------------------
    # Requirement E: Timezone conversion is respected
    # ----------------------------------------------------------------------
    def test_e_timezone_conversion_respected(self):
        """User timezones determine when alarms are due and executed."""
        with self.TestingSessionLocal() as db:
            u_kolkata = create_user(db, username="u_kolkata", timezone="Asia/Kolkata")
            u_ny = create_user(db, username="u_ny", timezone="America/New_York")

            a_kolkata = create_alarm(
                db,
                user_id=u_kolkata.id,
                time="07:00",
                selected_challenge_type="math",
                days_of_week=[0, 1, 2, 3, 4],
                is_active=True,
            )
            a_ny = create_alarm(
                db,
                user_id=u_ny.id,
                time="07:00",
                selected_challenge_type="push_ups",
                days_of_week=[0, 1, 2, 3, 4],
                is_active=True,
            )

            # At 01:30:00 UTC:
            # - Kolkata is 07:00:00 Wednesday -> due
            # - New York is 21:30:00 Tuesday -> not due
            dt_utc1 = datetime(2026, 9, 9, 1, 30, 0, tzinfo=timezone.utc)
            res1 = process_due_alarms(db, current_time=dt_utc1)
            self.assertEqual(res1.created, 1)
            self.assertEqual(res1.sessions[0].alarm_id, a_kolkata.id)

            # At 11:00:00 UTC:
            # - New York is 07:00:00 Wednesday -> due
            # - Kolkata is 16:30:00 Wednesday -> not due
            dt_utc2 = datetime(2026, 9, 9, 11, 0, 0, tzinfo=timezone.utc)
            res2 = process_due_alarms(db, current_time=dt_utc2)
            self.assertEqual(res2.created, 1)
            self.assertEqual(res2.sessions[0].alarm_id, a_ny.id)

    # ----------------------------------------------------------------------
    # Requirement F: Repeated execution during same minute -> 1 active session
    # ----------------------------------------------------------------------
    def test_f_repeated_execution_same_minute_creates_one_session(self):
        """Running scheduler at 07:00:05, 07:00:20, 07:00:50 creates only ONE active WakeSession."""
        with self.TestingSessionLocal() as db:
            user = create_user(db, username="user_f", timezone="Asia/Kolkata")
            alarm = create_alarm(
                db,
                user_id=user.id,
                time="07:00",
                selected_challenge_type="tongue_twister",
                days_of_week=[0, 1, 2, 3, 4],
                is_active=True,
            )

            # Tick 1: 07:00:05 local (01:30:05 UTC)
            t1 = datetime(2026, 9, 9, 1, 30, 5, tzinfo=timezone.utc)
            res1 = process_due_alarms(db, current_time=t1)
            self.assertEqual(res1.created, 1)
            self.assertEqual(res1.skipped, 0)
            self.assertEqual(res1.processed, 1)

            # Tick 2: 07:00:20 local (01:30:20 UTC)
            t2 = datetime(2026, 9, 9, 1, 30, 20, tzinfo=timezone.utc)
            res2 = process_due_alarms(db, current_time=t2)
            self.assertEqual(res2.created, 0)
            self.assertEqual(res2.skipped, 1)
            self.assertEqual(res2.processed, 1)

            # Tick 3: 07:00:50 local (01:30:50 UTC)
            t3 = datetime(2026, 9, 9, 1, 30, 50, tzinfo=timezone.utc)
            res3 = process_due_alarms(db, current_time=t3)
            self.assertEqual(res3.created, 0)
            self.assertEqual(res3.skipped, 1)
            self.assertEqual(res3.processed, 1)

            # Total sessions in database must be exactly 1
            all_sessions = list(db.scalars(select(WakeSession).where(WakeSession.alarm_id == alarm.id)).all())
            self.assertEqual(len(all_sessions), 1)

    # ----------------------------------------------------------------------
    # Requirement G: Existing active WakeSession causes scheduler to skip
    # ----------------------------------------------------------------------
    def test_g_existing_active_session_causes_skip(self):
        """If an active session ('in_challenge' or 'snoozed') already exists, scheduler skips."""
        with self.TestingSessionLocal() as db:
            user = create_user(db, username="user_g", timezone="UTC")
            alarm = create_alarm(
                db,
                user_id=user.id,
                time="08:00",
                selected_challenge_type="math",
                days_of_week=[0, 1, 2, 3, 4],
                is_active=True,
            )

            # Create session manually and transition to IN_PROGRESS ('in_challenge')
            sess = create_wake_session(db, user_id=user.id, alarm_id=alarm.id)
            transition_to_in_progress(db, sess.id)

            # Scheduler runs at 08:00:00
            t = datetime(2026, 9, 9, 8, 0, 0, tzinfo=timezone.utc)
            res = process_due_alarms(db, current_time=t)

            self.assertEqual(res.processed, 1)
            self.assertEqual(res.created, 0)
            self.assertEqual(res.skipped, 1)

    # ----------------------------------------------------------------------
    # Requirement H: Multiple due alarms create separate WakeSessions
    # ----------------------------------------------------------------------
    def test_h_multiple_due_alarms_create_separate_sessions(self):
        """Multiple alarms configured for the same time create distinct WakeSessions."""
        with self.TestingSessionLocal() as db:
            u1 = create_user(db, username="u_h1", timezone="UTC")
            u2 = create_user(db, username="u_h2", timezone="UTC")

            a1 = create_alarm(
                db,
                user_id=u1.id,
                time="06:00",
                selected_challenge_type="dance",
                days_of_week=[0, 1, 2, 3, 4],
            )
            a2 = create_alarm(
                db,
                user_id=u2.id,
                time="06:00",
                selected_challenge_type="math",
                days_of_week=[0, 1, 2, 3, 4],
            )

            t = datetime(2026, 9, 9, 6, 0, 0, tzinfo=timezone.utc)
            res = process_due_alarms(db, current_time=t)

            self.assertEqual(res.processed, 2)
            self.assertEqual(res.created, 2)
            self.assertEqual(res.skipped, 0)

            alarm_ids = {s.alarm_id for s in res.sessions}
            self.assertEqual(alarm_ids, {a1.id, a2.id})

    # ----------------------------------------------------------------------
    # Requirement I: User ownership remains correct
    # ----------------------------------------------------------------------
    def test_i_user_ownership_correct(self):
        """Created WakeSessions have matching user_id of the alarm owner."""
        with self.TestingSessionLocal() as db:
            user = create_user(db, username="user_i", timezone="UTC")
            alarm = create_alarm(
                db,
                user_id=user.id,
                time="10:00",
                selected_challenge_type="memory",
                days_of_week=[2],
            )

            t = datetime(2026, 9, 9, 10, 0, 0, tzinfo=timezone.utc)
            res = process_due_alarms(db, current_time=t)

            self.assertEqual(res.created, 1)
            session = res.sessions[0]
            self.assertEqual(session.user_id, user.id)
            self.assertEqual(session.alarm_id, alarm.id)

    # ----------------------------------------------------------------------
    # Requirement J: Created session starts in 'ringing' state
    # ----------------------------------------------------------------------
    def test_j_created_session_starts_in_ringing_state(self):
        """Created WakeSession has status='ringing', 0 snoozes, null dismissed time."""
        with self.TestingSessionLocal() as db:
            user = create_user(db, username="user_j", timezone="UTC")
            alarm = create_alarm(
                db,
                user_id=user.id,
                time="07:30",
                selected_challenge_type="tongue_twister",
                days_of_week=[2],
            )

            t = datetime(2026, 9, 9, 7, 30, 0, tzinfo=timezone.utc)
            res = process_due_alarms(db, current_time=t)

            sess = res.sessions[0]
            self.assertEqual(sess.status, STATUS_RINGING)
            self.assertEqual(sess.total_snooze_count, 0)
            self.assertIsNone(sess.dismissed_time)
            self.assertIsNotNone(sess.scheduled_time)
            self.assertIsNotNone(sess.initial_ring_time)

    # ----------------------------------------------------------------------
    # Requirement K: Existing terminal sessions do not corrupt scheduler behavior
    # ----------------------------------------------------------------------
    def test_k_terminal_sessions_occurrence_safety(self):
        """Dismissing/completing alarm in the same minute does not create a duplicate session;
        the next scheduled occurrence correctly creates a new session.
        """
        with self.TestingSessionLocal() as db:
            user = create_user(db, username="user_k", timezone="Asia/Kolkata")
            alarm = create_alarm(
                db,
                user_id=user.id,
                time="07:00",
                selected_challenge_type="math",
                days_of_week=[0, 1, 2, 3, 4],  # Mon-Fri
            )

            # 1. 07:00:05 local (01:30:05 UTC) -> Session created
            t1 = datetime(2026, 9, 9, 1, 30, 5, tzinfo=timezone.utc)
            res1 = process_due_alarms(db, current_time=t1)
            self.assertEqual(res1.created, 1)
            sess1 = res1.sessions[0]

            # 2. User quickly completes the challenge at 07:00:15
            complete_wake_session(db, sess1.id)
            self.assertEqual(sess1.status, "completed")

            # 3. Scheduler checks again at 07:00:25 (same minute)
            t2 = datetime(2026, 9, 9, 1, 30, 25, tzinfo=timezone.utc)
            res2 = process_due_alarms(db, current_time=t2)
            self.assertEqual(res2.created, 0)
            self.assertEqual(res2.skipped, 1)

            # 4. Next day (Thursday 2026-09-10 01:30:05 UTC) -> Creates new session for next day!
            t3 = datetime(2026, 9, 10, 1, 30, 5, tzinfo=timezone.utc)
            res3 = process_due_alarms(db, current_time=t3)
            self.assertEqual(res3.created, 1)
            sess2 = res3.sessions[0]
            self.assertNotEqual(sess1.id, sess2.id)

    # ----------------------------------------------------------------------
    # Requirement L: Database state and alarm configuration immutability
    # ----------------------------------------------------------------------
    def test_l_database_state_and_alarm_configuration_unmodified(self):
        """Scheduler execution leaves alarm properties completely unmodified."""
        with self.TestingSessionLocal() as db:
            user = create_user(db, username="user_l", timezone="UTC")
            alarm = create_alarm(
                db,
                user_id=user.id,
                time="12:00",
                selected_challenge_type="dance",
                difficulty_preference="hard",
                label="Workout Alarm",
                days_of_week=[0, 1, 2, 3, 4],
                is_active=True,
            )

            # Snapshot alarm state
            initial_time = alarm.time
            initial_days = alarm.days_of_week
            initial_challenge = alarm.selected_challenge_type
            initial_diff = alarm.difficulty_preference
            initial_label = alarm.label
            initial_active = alarm.is_active

            t = datetime(2026, 9, 9, 12, 0, 0, tzinfo=timezone.utc)
            res = process_due_alarms(db, current_time=t)
            self.assertEqual(res.created, 1)

            # Refresh and verify alarm properties remain identical
            db.refresh(alarm)
            self.assertEqual(alarm.time, initial_time)
            self.assertEqual(alarm.days_of_week, initial_days)
            self.assertEqual(alarm.selected_challenge_type, initial_challenge)
            self.assertEqual(alarm.difficulty_preference, initial_diff)
            self.assertEqual(alarm.label, initial_label)
            self.assertEqual(alarm.is_active, initial_active)

    # ----------------------------------------------------------------------
    # Requirement M: Failure handling rolls back cleanly
    # ----------------------------------------------------------------------
    def test_m_failure_handling_rolls_back_cleanly(self):
        """Unexpected database failure triggers rollback without corrupting session."""
        with self.TestingSessionLocal() as db:
            user = create_user(db, username="user_m", timezone="UTC")
            create_alarm(
                db,
                user_id=user.id,
                time="15:00",
                selected_challenge_type="math",
                days_of_week=[2],
            )

            t = datetime(2026, 9, 9, 15, 0, 0, tzinfo=timezone.utc)

            # Patch create_wake_session to raise an unexpected RuntimeError
            with patch(
                "backend.app.services.wake_session_service.create_wake_session",
                side_effect=RuntimeError("Simulated database failure"),
            ):
                with self.assertRaises(RuntimeError):
                    process_due_alarms(db, current_time=t)

            # Verify that session remains functional and no partial records exist
            db_sessions = list(db.scalars(select(WakeSession)).all())
            self.assertEqual(len(db_sessions), 0)

            # Subsequent normal database operation succeeds
            u = db.get(User, user.id)
            self.assertIsNotNone(u)

    # ----------------------------------------------------------------------
    # Additional edge cases & input validations
    # ----------------------------------------------------------------------
    def test_naive_current_time_raises_value_error(self):
        """Passing naive datetime to process_due_alarms raises ValueError."""
        with self.TestingSessionLocal() as db:
            naive_dt = datetime(2026, 9, 9, 7, 0, 0)
            with self.assertRaises(ValueError) as ctx:
                process_due_alarms(db, current_time=naive_dt)
            self.assertIn("timezone-aware", str(ctx.exception))

    def test_scheduler_result_dataclass_methods(self):
        """Test SchedulerExecutionResult dictionary subscripting and to_dict method."""
        res = SchedulerExecutionResult(processed=3, created=2, skipped=1)
        self.assertEqual(res["processed"], 3)
        self.assertEqual(res["created"], 2)
        self.assertEqual(res["skipped"], 1)
        d = res.to_dict()
        self.assertEqual(d["processed"], 3)
        self.assertEqual(d["created"], 2)
        self.assertEqual(d["skipped"], 1)


if __name__ == "__main__":
    unittest.main()
