"""Automated test suite for Datetime & UTC Modernization and Hardening.

Validates that:
A. now_utc() returns timezone-aware UTC.
B. now_utc_naive() returns naive UTC.
C. ensure_utc() treats a naive datetime as UTC without changing its clock values.
D. ensure_utc() correctly converts a non-UTC aware datetime to UTC.
E. ensure_naive_utc() correctly normalizes both naive and aware datetimes.
F. diff_seconds() works safely for:
   - naive vs naive
   - aware vs aware
   - naive vs aware
   - aware vs naive
G. Model timestamp defaults remain valid in SQLite.
H. WakeSession completion calculates wake delay correctly after the record has been loaded back from SQLite.
I. Scheduler occurrence calculations remain correct.
J. Existing database can still be opened and queried.
"""
from datetime import datetime, timedelta, timezone
import unittest
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.datetime_utils import (
    diff_seconds,
    ensure_naive_utc,
    ensure_utc,
    now_utc,
    now_utc_naive,
)
from backend.app.database.base import Base
import backend.app.database.session  # Ensures pragma listeners
from backend.app.database.session import SessionLocal, engine
from backend.app.models.alarm import Alarm
from backend.app.models.challenge import Challenge
from backend.app.models.challenge_attempt import ChallengeAttempt
from backend.app.models.ml_adaptive_log import MLAdaptiveLog
from backend.app.models.snooze_event import SnoozeEvent
from backend.app.models.user import User
from backend.app.models.wake_session import WakeSession
from backend.app.services.alarm_service import create_alarm
from backend.app.services.scheduler_service import (
    get_occurrence_scheduled_time,
    has_active_or_occurrence_session,
    process_due_alarms,
)
from backend.app.services.user_service import create_user
from backend.app.services.wake_session_service import (
    STATUS_ABANDONED,
    STATUS_COMPLETED,
    complete_wake_session,
    create_wake_session,
    fail_wake_session,
)


class TestDatetimeHardening(unittest.TestCase):
    """Test suite verifying datetime and timezone modernization behaviors."""

    @classmethod
    def setUpClass(cls):
        """Set up isolated in-memory SQLite database."""
        cls.test_engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.TestingSessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=cls.test_engine
        )
        Base.metadata.create_all(bind=cls.test_engine)

    @classmethod
    def tearDownClass(cls):
        """Clean up in-memory database."""
        Base.metadata.drop_all(bind=cls.test_engine)
        cls.test_engine.dispose()

    def setUp(self):
        """Clear database tables before each test."""
        with self.TestingSessionLocal() as session:
            for table in reversed(Base.metadata.sorted_tables):
                session.execute(table.delete())
            session.commit()

    # ----------------------------------------------------------------------
    # Requirement A: now_utc() returns timezone-aware UTC
    # ----------------------------------------------------------------------
    def test_a_now_utc_returns_aware_utc(self):
        """now_utc() returns a timezone-aware datetime with tzinfo=timezone.utc."""
        dt = now_utc()
        self.assertIsInstance(dt, datetime)
        self.assertIsNotNone(dt.tzinfo)
        self.assertEqual(dt.tzinfo, timezone.utc)
        # Verify it represents current time (within 5 seconds)
        delta = abs((datetime.now(timezone.utc) - dt).total_seconds())
        self.assertLess(delta, 5.0)

    # ----------------------------------------------------------------------
    # Requirement B: now_utc_naive() returns naive UTC
    # ----------------------------------------------------------------------
    def test_b_now_utc_naive_returns_naive_utc(self):
        """now_utc_naive() returns an offset-naive datetime representing UTC."""
        dt = now_utc_naive()
        self.assertIsInstance(dt, datetime)
        self.assertIsNone(dt.tzinfo)
        # Compare clock values with timezone-aware UTC
        utc_now = datetime.now(timezone.utc)
        delta = abs((utc_now.replace(tzinfo=None) - dt).total_seconds())
        self.assertLess(delta, 5.0)

    # ----------------------------------------------------------------------
    # Requirement C: ensure_utc() treats naive datetime as UTC (no clock shift)
    # ----------------------------------------------------------------------
    def test_c_ensure_utc_preserves_naive_clock_values(self):
        """ensure_utc() attaches timezone.utc to a naive datetime without shifting clock numbers."""
        naive_dt = datetime(2026, 9, 9, 7, 30, 45, 123456)
        aware_dt = ensure_utc(naive_dt)

        self.assertIsNotNone(aware_dt.tzinfo)
        self.assertEqual(aware_dt.tzinfo, timezone.utc)
        self.assertEqual(aware_dt.year, 2026)
        self.assertEqual(aware_dt.month, 9)
        self.assertEqual(aware_dt.day, 9)
        self.assertEqual(aware_dt.hour, 7)
        self.assertEqual(aware_dt.minute, 30)
        self.assertEqual(aware_dt.second, 45)
        self.assertEqual(aware_dt.microsecond, 123456)

        # None handling
        self.assertIsNone(ensure_utc(None))

    # ----------------------------------------------------------------------
    # Requirement D: ensure_utc() converts non-UTC aware datetime to UTC
    # ----------------------------------------------------------------------
    def test_d_ensure_utc_converts_aware_non_utc_to_utc(self):
        """ensure_utc() correctly translates a non-UTC aware datetime into UTC."""
        kolkata_tz = ZoneInfo("Asia/Kolkata")  # UTC+05:30
        local_dt = datetime(2026, 9, 9, 7, 0, 0, tzinfo=kolkata_tz)

        utc_dt = ensure_utc(local_dt)
        self.assertIsNotNone(utc_dt.tzinfo)
        self.assertEqual(utc_dt.tzinfo, timezone.utc)
        # 07:00 Asia/Kolkata == 01:30 UTC
        self.assertEqual(utc_dt.year, 2026)
        self.assertEqual(utc_dt.month, 9)
        self.assertEqual(utc_dt.day, 9)
        self.assertEqual(utc_dt.hour, 1)
        self.assertEqual(utc_dt.minute, 30)
        self.assertEqual(utc_dt.second, 0)

    # ----------------------------------------------------------------------
    # Requirement E: ensure_naive_utc() normalizes both naive and aware datetimes
    # ----------------------------------------------------------------------
    def test_e_ensure_naive_utc_normalizes_naive_and_aware(self):
        """ensure_naive_utc() strips tzinfo after ensuring UTC representation."""
        # 1. Naive input: assumed UTC, returned naive with same values
        naive_in = datetime(2026, 9, 9, 1, 30, 0)
        naive_out = ensure_naive_utc(naive_in)
        self.assertIsNone(naive_out.tzinfo)
        self.assertEqual(naive_out, naive_in)

        # 2. Aware UTC input: tzinfo removed
        aware_utc_in = datetime(2026, 9, 9, 1, 30, 0, tzinfo=timezone.utc)
        aware_utc_out = ensure_naive_utc(aware_utc_in)
        self.assertIsNone(aware_utc_out.tzinfo)
        self.assertEqual(aware_utc_out, datetime(2026, 9, 9, 1, 30, 0))

        # 3. Aware non-UTC input: converted to UTC then tzinfo removed
        kolkata_tz = ZoneInfo("Asia/Kolkata")
        local_in = datetime(2026, 9, 9, 7, 0, 0, tzinfo=kolkata_tz)
        local_out = ensure_naive_utc(local_in)
        self.assertIsNone(local_out.tzinfo)
        self.assertEqual(local_out, datetime(2026, 9, 9, 1, 30, 0))

        # 4. None handling
        self.assertIsNone(ensure_naive_utc(None))

    # ----------------------------------------------------------------------
    # Requirement F: diff_seconds() safe across naive and aware combinations
    # ----------------------------------------------------------------------
    def test_f_diff_seconds_safe_across_naive_and_aware(self):
        """diff_seconds() calculates differences without TypeError across all combinations."""
        t1_naive = datetime(2026, 9, 9, 1, 35, 0)
        t2_naive = datetime(2026, 9, 9, 1, 30, 0)
        expected_diff = 300.0  # 5 minutes

        t1_aware = datetime(2026, 9, 9, 1, 35, 0, tzinfo=timezone.utc)
        t2_aware = datetime(2026, 9, 9, 1, 30, 0, tzinfo=timezone.utc)

        # 1. Naive vs Naive
        self.assertEqual(diff_seconds(t1_naive, t2_naive), expected_diff)

        # 2. Aware vs Aware
        self.assertEqual(diff_seconds(t1_aware, t2_aware), expected_diff)

        # 3. Naive vs Aware (The Python TypeError trap)
        self.assertEqual(diff_seconds(t1_naive, t2_aware), expected_diff)

        # 4. Aware vs Naive (The Python TypeError trap)
        self.assertEqual(diff_seconds(t1_aware, t2_naive), expected_diff)

        # 5. Aware non-UTC vs Naive
        kolkata_tz = ZoneInfo("Asia/Kolkata")
        t1_kolkata = datetime(2026, 9, 9, 7, 5, 0, tzinfo=kolkata_tz)  # 01:35 UTC
        self.assertEqual(diff_seconds(t1_kolkata, t2_naive), expected_diff)

    # ----------------------------------------------------------------------
    # Requirement G: Model timestamp defaults remain valid in SQLite
    # ----------------------------------------------------------------------
    def test_g_model_timestamp_defaults_valid_in_sqlite(self):
        """Model column defaults using now_utc_naive persist cleanly in SQLite."""
        with self.TestingSessionLocal() as db:
            user = User(username="dt_user", timezone="UTC")
            db.add(user)
            db.commit()
            db.refresh(user)

            self.assertIsInstance(user.created_at, datetime)
            self.assertIsNone(user.created_at.tzinfo)
            self.assertIsInstance(user.updated_at, datetime)
            self.assertIsNone(user.updated_at.tzinfo)

            alarm = Alarm(user_id=user.id, time="07:00")
            db.add(alarm)
            db.commit()
            db.refresh(alarm)
            self.assertIsInstance(alarm.created_at, datetime)
            self.assertIsNone(alarm.created_at.tzinfo)

            wake_sess = WakeSession(
                user_id=user.id,
                alarm_id=alarm.id,
                scheduled_time=now_utc_naive(),
                initial_ring_time=now_utc_naive(),
            )
            db.add(wake_sess)
            db.commit()
            db.refresh(wake_sess)
            self.assertIsInstance(wake_sess.created_at, datetime)
            self.assertIsNone(wake_sess.created_at.tzinfo)

            snooze = SnoozeEvent(
                wake_session_id=wake_sess.id,
                snooze_number=1,
            )
            db.add(snooze)
            db.commit()
            db.refresh(snooze)
            self.assertIsInstance(snooze.snoozed_at, datetime)
            self.assertIsNone(snooze.snoozed_at.tzinfo)
            self.assertIsInstance(snooze.created_at, datetime)
            self.assertIsNone(snooze.created_at.tzinfo)

            challenge = Challenge(
                challenge_type="math",
                difficulty_level="easy",
                title="Math Test",
                description="Solve 2+2",
                template_payload="{}",
            )
            db.add(challenge)
            db.commit()
            db.refresh(challenge)
            self.assertIsInstance(challenge.created_at, datetime)
            self.assertIsNone(challenge.created_at.tzinfo)

            attempt = ChallengeAttempt(
                wake_session_id=wake_sess.id,
                challenge_id=challenge.id,
                challenge_type="math",
                difficulty_level="easy",
                prompt_content="2 + 2 = ?",
            )
            db.add(attempt)
            db.commit()
            db.refresh(attempt)
            self.assertIsInstance(attempt.started_at, datetime)
            self.assertIsNone(attempt.started_at.tzinfo)
            self.assertIsInstance(attempt.created_at, datetime)
            self.assertIsNone(attempt.created_at.tzinfo)

            ml_log = MLAdaptiveLog(
                wake_session_id=wake_sess.id,
                historical_features_snapshot="{}",
                user_selected_type="math",
                adaptive_difficulty="easy",
                model_policy_version="v1.0",
            )
            db.add(ml_log)
            db.commit()
            db.refresh(ml_log)
            self.assertIsInstance(ml_log.decision_timestamp, datetime)
            self.assertIsNone(ml_log.decision_timestamp.tzinfo)
            self.assertIsInstance(ml_log.created_at, datetime)
            self.assertIsNone(ml_log.created_at.tzinfo)

    # ----------------------------------------------------------------------
    # Requirement H: WakeSession completion delay calculation after SQLite reload
    # ----------------------------------------------------------------------
    def test_h_wake_session_delay_calculation_after_sqlite_reload(self):
        """WakeSession loaded from SQLite completes without TypeError and computes delay."""
        with self.TestingSessionLocal() as db:
            user = create_user(db, username="delay_user", timezone="UTC")
            alarm = create_alarm(db, user_id=user.id, time="07:00", selected_challenge_type="math")
            user_id = user.id
            alarm_id = alarm.id
            # Create session 10 minutes ago
            t_scheduled = now_utc_naive() - timedelta(minutes=10)
            sess = create_wake_session(
                db, user_id=user_id, alarm_id=alarm_id, scheduled_time=t_scheduled
            )
            sess_id = sess.id

        # Reload in fresh database session to ensure it comes from SQLite
        with self.TestingSessionLocal() as db:
            loaded_sess = db.get(WakeSession, sess_id)
            self.assertIsNone(loaded_sess.scheduled_time.tzinfo)

            # Complete wake session
            completed = complete_wake_session(db, sess_id)
            self.assertEqual(completed.status, STATUS_COMPLETED)
            self.assertIsNotNone(completed.dismissed_time)
            self.assertIsNone(completed.dismissed_time.tzinfo)
            # Delay should be approximately 600 seconds (10 minutes)
            self.assertGreaterEqual(completed.total_wake_delay_seconds, 595.0)
            self.assertLessEqual(completed.total_wake_delay_seconds, 610.0)

        # Test failure/abandonment delay calculation as well
        with self.TestingSessionLocal() as db:
            sess2 = create_wake_session(
                db, user_id=user_id, alarm_id=alarm_id, scheduled_time=t_scheduled
            )
            sess2_id = sess2.id

        with self.TestingSessionLocal() as db:
            abandoned = fail_wake_session(db, sess2_id)
            self.assertEqual(abandoned.status, STATUS_ABANDONED)
            self.assertGreaterEqual(abandoned.total_wake_delay_seconds, 595.0)

    # ----------------------------------------------------------------------
    # Requirement I: Scheduler occurrence calculations remain correct
    # ----------------------------------------------------------------------
    def test_i_scheduler_occurrence_calculations_remain_correct(self):
        """Scheduler computes correct UTC occurrence and checks duplicate sessions cleanly."""
        with self.TestingSessionLocal() as db:
            user = create_user(db, username="kolkata_user", timezone="Asia/Kolkata")
            alarm = create_alarm(
                db,
                user_id=user.id,
                time="07:00",
                selected_challenge_type="math",
                days_of_week=[2],  # Wednesday
                is_active=True,
            )

            # Wednesday 2026-09-09 01:30:15 UTC == 07:00:15 Asia/Kolkata
            t_due = datetime(2026, 9, 9, 1, 30, 15, tzinfo=timezone.utc)
            occ_utc = get_occurrence_scheduled_time(alarm, t_due)

            # Occurrence must be timezone-aware UTC at 01:30:00
            self.assertEqual(occ_utc.tzinfo, timezone.utc)
            self.assertEqual(occ_utc.hour, 1)
            self.assertEqual(occ_utc.minute, 30)
            self.assertEqual(occ_utc.second, 0)

            # Execution tick creates session
            result = process_due_alarms(db, current_time=t_due)
            self.assertEqual(result.created, 1)
            created_sess = result.sessions[0]
            self.assertIsNone(created_sess.scheduled_time.tzinfo)

            # has_active_or_occurrence_session handles occurrence correctly
            self.assertTrue(has_active_or_occurrence_session(db, alarm.id, occ_utc))

    # ----------------------------------------------------------------------
    # Requirement J: Existing database can still be opened and queried
    # ----------------------------------------------------------------------
    def test_j_existing_database_connectivity_and_querying(self):
        """Production database engine and SessionLocal can be connected and queried."""
        with SessionLocal() as db:
            # Query users table
            users = list(db.scalars(select(User)).all())
            self.assertIsInstance(users, list)

            # Query alarms table
            alarms = list(db.scalars(select(Alarm)).all())
            self.assertIsInstance(alarms, list)

            # Query wake_sessions table
            sessions = list(db.scalars(select(WakeSession)).all())
            self.assertIsInstance(sessions, list)


if __name__ == "__main__":
    unittest.main()
