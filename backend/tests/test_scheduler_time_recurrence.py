"""Automated test suite for Scheduler Time & Recurrence Engine (Phase 2.6.2.1).

Validates:
A. Active alarm on matching weekday + matching time -> due
B. Active alarm on wrong weekday -> not due
C. Active alarm at wrong hour -> not due
D. Active alarm at wrong minute -> not due
E. Inactive alarm -> not due
F. Matching time at second 0 -> due
G. Matching time at second 15 -> due
H. Matching time at second 59 -> due
I. One-minute-after alarm -> not due
J. Timezone conversion works correctly (UTC -> Asia/Kolkata, America/New_York)
K. Same UTC timestamp produces different local times for different timezones
L. Saturday/Sunday recurrence behavior
M. Monday-Friday recurrence behavior
N. Boundary around midnight (00:00 alarm, timezone date/day shift)
O. Scheduler does not modify alarm configuration

Also tests:
- Naive datetime handling (rejected with ValueError)
- Invalid timezone handling (rejected with InvalidTimezoneError)
- Invalid alarm time format (rejected with InvalidAlarmTimeError)
- Invalid days_of_week format (rejected with InvalidDaysOfWeekError)
- Missing timezone handling (rejected with ValueError)
- Database query integration test (get_due_alarms) using isolated in-memory SQLite
"""
from datetime import datetime, timezone
import json
import unittest
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.exceptions import (
    InvalidAlarmTimeError,
    InvalidDaysOfWeekError,
    InvalidTimezoneError,
)
from backend.app.database.base import Base
import backend.app.database.session  # Ensures pragma listeners
from backend.app.models.alarm import Alarm
from backend.app.models.user import User
from backend.app.services.alarm_service import create_alarm
from backend.app.services.scheduler_service import (
    get_alarm_days,
    get_due_alarms,
    is_alarm_active,
    is_alarm_day,
    is_alarm_due,
    is_alarm_time_due,
    parse_alarm_time,
    resolve_timezone,
    to_user_local_time,
)
from backend.app.services.user_service import create_user


class TestSchedulerTimeRecurrence(unittest.TestCase):
    """Test suite for Phase 2.6.2.1 Scheduler Time & Recurrence Engine."""

    def _make_dummy_alarm(
        self,
        time_str: str = "07:00",
        days_of_week: str = "[0, 1, 2, 3, 4]",
        is_active: bool = True,
        user_tz: str = "Asia/Kolkata",
    ) -> Alarm:
        """Create an in-memory unpersisted Alarm model instance for pure function tests."""
        user = User(
            id=1,
            username="test_user",
            timezone=user_tz,
        )
        alarm = Alarm(
            id=1,
            user_id=1,
            time=time_str,
            label="Morning Alarm",
            days_of_week=days_of_week,
            selected_challenge_type="tongue_twister",
            difficulty_preference="adaptive",
            is_active=is_active,
        )
        alarm.user = user
        return alarm

    # ----------------------------------------------------------------------
    # Requirement A: Active alarm on matching weekday + matching time -> due
    # ----------------------------------------------------------------------
    def test_a_active_alarm_matching_weekday_and_time_is_due(self):
        """Active alarm on matching weekday and matching hour:minute is due."""
        alarm = self._make_dummy_alarm(
            time_str="07:00",
            days_of_week="[0, 1, 2, 3, 4]",
            is_active=True,
            user_tz="Asia/Kolkata",
        )
        # 2026-09-09 is Wednesday (day 2). In Asia/Kolkata (+05:30), 07:00 is 01:30 UTC.
        dt_utc = datetime(2026, 9, 9, 1, 30, 0, tzinfo=timezone.utc)
        self.assertTrue(is_alarm_due(alarm, current_time=dt_utc))

    # ----------------------------------------------------------------------
    # Requirement B: Active alarm on wrong weekday -> not due
    # ----------------------------------------------------------------------
    def test_b_active_alarm_on_wrong_weekday_not_due(self):
        """Active alarm on wrong weekday is not due even if time matches."""
        # Alarm only enabled on weekends: Saturday (5), Sunday (6)
        alarm = self._make_dummy_alarm(
            time_str="07:00",
            days_of_week="[5, 6]",
            is_active=True,
            user_tz="Asia/Kolkata",
        )
        # 2026-09-09 is Wednesday (day 2). Local time matches 07:00, but day does not.
        dt_utc = datetime(2026, 9, 9, 1, 30, 0, tzinfo=timezone.utc)
        self.assertFalse(is_alarm_due(alarm, current_time=dt_utc))

    # ----------------------------------------------------------------------
    # Requirement C: Active alarm at wrong hour -> not due
    # ----------------------------------------------------------------------
    def test_c_active_alarm_at_wrong_hour_not_due(self):
        """Active alarm at wrong hour is not due."""
        alarm = self._make_dummy_alarm(
            time_str="07:00",
            days_of_week="[0, 1, 2, 3, 4]",
            is_active=True,
            user_tz="Asia/Kolkata",
        )
        # 08:00 in Asia/Kolkata is 02:30 UTC
        dt_utc = datetime(2026, 9, 9, 2, 30, 0, tzinfo=timezone.utc)
        self.assertFalse(is_alarm_due(alarm, current_time=dt_utc))

    # ----------------------------------------------------------------------
    # Requirement D: Active alarm at wrong minute -> not due
    # ----------------------------------------------------------------------
    def test_d_active_alarm_at_wrong_minute_not_due(self):
        """Active alarm at wrong minute is not due."""
        alarm = self._make_dummy_alarm(
            time_str="07:00",
            days_of_week="[0, 1, 2, 3, 4]",
            is_active=True,
            user_tz="Asia/Kolkata",
        )
        # 07:05 in Asia/Kolkata is 01:35 UTC
        dt_utc = datetime(2026, 9, 9, 1, 35, 0, tzinfo=timezone.utc)
        self.assertFalse(is_alarm_due(alarm, current_time=dt_utc))

    # ----------------------------------------------------------------------
    # Requirement E: Inactive alarm -> not due
    # ----------------------------------------------------------------------
    def test_e_inactive_alarm_not_due(self):
        """Inactive alarm is never due, even when weekday and time match perfectly."""
        alarm = self._make_dummy_alarm(
            time_str="07:00",
            days_of_week="[0, 1, 2, 3, 4]",
            is_active=False,
            user_tz="Asia/Kolkata",
        )
        dt_utc = datetime(2026, 9, 9, 1, 30, 0, tzinfo=timezone.utc)
        self.assertFalse(is_alarm_active(alarm))
        self.assertFalse(is_alarm_due(alarm, current_time=dt_utc))

    # ----------------------------------------------------------------------
    # Requirements F, G, H, I: Second-level precision & one-minute-after
    # ----------------------------------------------------------------------
    def test_f_matching_time_at_second_0_is_due(self):
        """Matching time at second 0 (07:00:00) is due."""
        alarm = self._make_dummy_alarm(time_str="07:00", user_tz="Asia/Kolkata")
        dt_utc = datetime(2026, 9, 9, 1, 30, 0, tzinfo=timezone.utc)
        self.assertTrue(is_alarm_due(alarm, current_time=dt_utc))

    def test_g_matching_time_at_second_15_is_due(self):
        """Matching time at second 15 (07:00:15) is due."""
        alarm = self._make_dummy_alarm(time_str="07:00", user_tz="Asia/Kolkata")
        dt_utc = datetime(2026, 9, 9, 1, 30, 15, tzinfo=timezone.utc)
        self.assertTrue(is_alarm_due(alarm, current_time=dt_utc))

    def test_h_matching_time_at_second_59_is_due(self):
        """Matching time at second 59 (07:00:59) is due."""
        alarm = self._make_dummy_alarm(time_str="07:00", user_tz="Asia/Kolkata")
        dt_utc = datetime(2026, 9, 9, 1, 30, 59, tzinfo=timezone.utc)
        self.assertTrue(is_alarm_due(alarm, current_time=dt_utc))

    def test_i_one_minute_after_alarm_not_due(self):
        """One minute after alarm (07:01:00) is not due."""
        alarm = self._make_dummy_alarm(time_str="07:00", user_tz="Asia/Kolkata")
        dt_utc = datetime(2026, 9, 9, 1, 31, 0, tzinfo=timezone.utc)
        self.assertFalse(is_alarm_due(alarm, current_time=dt_utc))

    # ----------------------------------------------------------------------
    # Requirement J: Timezone conversion works correctly
    # ----------------------------------------------------------------------
    def test_j_timezone_conversion_works_correctly(self):
        """Verify to_user_local_time converts UTC correctly to specified timezone."""
        dt_utc = datetime(2026, 9, 9, 10, 0, 0, tzinfo=timezone.utc)

        # Asia/Kolkata (+05:30)
        local_kolkata = to_user_local_time(dt_utc, "Asia/Kolkata")
        self.assertEqual(local_kolkata.hour, 15)
        self.assertEqual(local_kolkata.minute, 30)
        self.assertEqual(local_kolkata.second, 0)
        self.assertEqual(local_kolkata.day, 9)

        # UTC
        local_utc = to_user_local_time(dt_utc, "UTC")
        self.assertEqual(local_utc.hour, 10)
        self.assertEqual(local_utc.minute, 0)

        # America/New_York (EDT, UTC-4 in September)
        local_ny = to_user_local_time(dt_utc, "America/New_York")
        self.assertEqual(local_ny.hour, 6)
        self.assertEqual(local_ny.minute, 0)

    # ----------------------------------------------------------------------
    # Requirement K: Same UTC timestamp produces different local times
    # ----------------------------------------------------------------------
    def test_k_same_utc_timestamp_different_timezones(self):
        """The exact same UTC timestamp produces different local times and due results."""
        dt_utc = datetime(2026, 9, 9, 12, 0, 0, tzinfo=timezone.utc)

        # Alarm configured for 17:30
        alarm_1730 = self._make_dummy_alarm(time_str="17:30", days_of_week="[2]")

        # For Asia/Kolkata (+05:30): 12:00 UTC == 17:30 Local -> DUE
        self.assertTrue(is_alarm_due(alarm_1730, current_time=dt_utc, user_tz="Asia/Kolkata"))

        # For UTC: 12:00 UTC == 12:00 Local -> NOT DUE
        self.assertFalse(is_alarm_due(alarm_1730, current_time=dt_utc, user_tz="UTC"))

        # For America/New_York (EDT -04:00): 12:00 UTC == 08:00 Local -> NOT DUE
        self.assertFalse(is_alarm_due(alarm_1730, current_time=dt_utc, user_tz="America/New_York"))

        # Alarm configured for 08:00
        alarm_0800 = self._make_dummy_alarm(time_str="08:00", days_of_week="[2]")
        # For America/New_York: 12:00 UTC == 08:00 Local -> DUE
        self.assertTrue(is_alarm_due(alarm_0800, current_time=dt_utc, user_tz="America/New_York"))
        # For Asia/Kolkata: 12:00 UTC == 17:30 Local -> NOT DUE
        self.assertFalse(is_alarm_due(alarm_0800, current_time=dt_utc, user_tz="Asia/Kolkata"))

    # ----------------------------------------------------------------------
    # Requirement L: Saturday/Sunday recurrence behavior
    # ----------------------------------------------------------------------
    def test_l_weekend_recurrence_behavior(self):
        """Alarms configured with days_of_week=[5, 6] trigger only on Saturday and Sunday."""
        weekend_alarm = self._make_dummy_alarm(
            time_str="09:00",
            days_of_week="[5, 6]",
            user_tz="UTC",
        )

        # Friday 2026-09-11 09:00 UTC (day 4) -> NOT DUE
        dt_fri = datetime(2026, 9, 11, 9, 0, 0, tzinfo=timezone.utc)
        self.assertFalse(is_alarm_due(weekend_alarm, current_time=dt_fri))

        # Saturday 2026-09-12 09:00 UTC (day 5) -> DUE
        dt_sat = datetime(2026, 9, 12, 9, 0, 0, tzinfo=timezone.utc)
        self.assertTrue(is_alarm_due(weekend_alarm, current_time=dt_sat))

        # Sunday 2026-09-13 09:00 UTC (day 6) -> DUE
        dt_sun = datetime(2026, 9, 13, 9, 0, 0, tzinfo=timezone.utc)
        self.assertTrue(is_alarm_due(weekend_alarm, current_time=dt_sun))

        # Monday 2026-09-14 09:00 UTC (day 0) -> NOT DUE
        dt_mon = datetime(2026, 9, 14, 9, 0, 0, tzinfo=timezone.utc)
        self.assertFalse(is_alarm_due(weekend_alarm, current_time=dt_mon))

    # ----------------------------------------------------------------------
    # Requirement M: Monday-Friday recurrence behavior
    # ----------------------------------------------------------------------
    def test_m_weekday_recurrence_behavior(self):
        """Alarms configured with days_of_week=[0, 1, 2, 3, 4] trigger Mon-Fri and not on weekends."""
        weekday_alarm = self._make_dummy_alarm(
            time_str="06:30",
            days_of_week="[0, 1, 2, 3, 4]",
            user_tz="UTC",
        )

        # Mon 2026-09-07 to Fri 2026-09-11
        for day in range(7, 12):
            dt = datetime(2026, 9, day, 6, 30, 0, tzinfo=timezone.utc)
            self.assertTrue(is_alarm_due(weekday_alarm, current_time=dt), f"Failed on day {day}")

        # Saturday 2026-09-12 06:30 UTC -> NOT DUE
        dt_sat = datetime(2026, 9, 12, 6, 30, 0, tzinfo=timezone.utc)
        self.assertFalse(is_alarm_due(weekday_alarm, current_time=dt_sat))

        # Sunday 2026-09-13 06:30 UTC -> NOT DUE
        dt_sun = datetime(2026, 9, 13, 6, 30, 0, tzinfo=timezone.utc)
        self.assertFalse(is_alarm_due(weekday_alarm, current_time=dt_sun))

    # ----------------------------------------------------------------------
    # Requirement N: Boundary around midnight
    # ----------------------------------------------------------------------
    def test_n_midnight_boundary_and_weekday_shift(self):
        """Midnight boundary and date/weekday changes caused by timezone conversion."""
        # Midnight alarm (00:00) on Thursdays (3) in Asia/Kolkata (+05:30)
        alarm_thu_midnight = self._make_dummy_alarm(
            time_str="00:00",
            days_of_week="[3]",  # Thursday
            user_tz="Asia/Kolkata",
        )

        # In Asia/Kolkata, Thursday 00:00:00 is Wednesday 18:30:00 UTC
        dt_exact_midnight = datetime(2026, 9, 9, 18, 30, 0, tzinfo=timezone.utc)
        self.assertTrue(is_alarm_due(alarm_thu_midnight, current_time=dt_exact_midnight))

        # 15 seconds into midnight -> DUE
        dt_15s_midnight = datetime(2026, 9, 9, 18, 30, 15, tzinfo=timezone.utc)
        self.assertTrue(is_alarm_due(alarm_thu_midnight, current_time=dt_15s_midnight))

        # 1 second before midnight: Wednesday 23:59:59 Kolkata (18:29:59 UTC) -> NOT DUE
        dt_before_midnight = datetime(2026, 9, 9, 18, 29, 59, tzinfo=timezone.utc)
        self.assertFalse(is_alarm_due(alarm_thu_midnight, current_time=dt_before_midnight))

        # 1 minute after midnight: Thursday 00:01:00 Kolkata (18:31:00 UTC) -> NOT DUE
        dt_after_midnight = datetime(2026, 9, 9, 18, 31, 0, tzinfo=timezone.utc)
        self.assertFalse(is_alarm_due(alarm_thu_midnight, current_time=dt_after_midnight))

        # An alarm on Wednesday (2) at 00:00 must NOT be due on Thursday midnight
        alarm_wed_midnight = self._make_dummy_alarm(
            time_str="00:00",
            days_of_week="[2]",  # Wednesday
            user_tz="Asia/Kolkata",
        )
        self.assertFalse(is_alarm_due(alarm_wed_midnight, current_time=dt_exact_midnight))

    # ----------------------------------------------------------------------
    # Requirement O: Scheduler does not modify alarm configuration
    # ----------------------------------------------------------------------
    def test_o_scheduler_does_not_modify_alarm_configuration(self):
        """Verify scheduler evaluation leaves alarm instance properties completely unchanged."""
        alarm = self._make_dummy_alarm(
            time_str="07:00",
            days_of_week="[0, 1, 2, 3, 4]",
            is_active=True,
            user_tz="Asia/Kolkata",
        )
        # Snapshot alarm attributes before evaluation
        snapshot_before = {
            "id": alarm.id,
            "user_id": alarm.user_id,
            "time": alarm.time,
            "label": alarm.label,
            "days_of_week": alarm.days_of_week,
            "selected_challenge_type": alarm.selected_challenge_type,
            "difficulty_preference": alarm.difficulty_preference,
            "is_active": alarm.is_active,
        }

        dt_utc = datetime(2026, 9, 9, 1, 30, 0, tzinfo=timezone.utc)
        result = is_alarm_due(alarm, current_time=dt_utc)
        self.assertTrue(result)

        snapshot_after = {
            "id": alarm.id,
            "user_id": alarm.user_id,
            "time": alarm.time,
            "label": alarm.label,
            "days_of_week": alarm.days_of_week,
            "selected_challenge_type": alarm.selected_challenge_type,
            "difficulty_preference": alarm.difficulty_preference,
            "is_active": alarm.is_active,
        }

        self.assertEqual(snapshot_before, snapshot_after)

    # ----------------------------------------------------------------------
    # Input Validation & Edge Cases
    # ----------------------------------------------------------------------
    def test_naive_datetime_raises_value_error(self):
        """Naive datetime without tzinfo is rejected with ValueError."""
        alarm = self._make_dummy_alarm(time_str="07:00", user_tz="UTC")
        naive_dt = datetime(2026, 9, 9, 7, 0, 0)  # No tzinfo
        with self.assertRaises(ValueError) as ctx:
            is_alarm_due(alarm, current_time=naive_dt)
        self.assertIn("timezone-aware", str(ctx.exception))

    def test_invalid_timezone_raises_exception(self):
        """Invalid IANA timezone string raises InvalidTimezoneError."""
        alarm = self._make_dummy_alarm(time_str="07:00", user_tz="Invalid/TZ_Region")
        dt_utc = datetime(2026, 9, 9, 7, 0, 0, tzinfo=timezone.utc)
        with self.assertRaises(InvalidTimezoneError):
            is_alarm_due(alarm, current_time=dt_utc)

    def test_invalid_alarm_time_raises_exception(self):
        """Malformed alarm time string raises InvalidAlarmTimeError."""
        alarm = self._make_dummy_alarm(time_str="25:99", user_tz="UTC")
        dt_utc = datetime(2026, 9, 9, 7, 0, 0, tzinfo=timezone.utc)
        with self.assertRaises(InvalidAlarmTimeError):
            is_alarm_due(alarm, current_time=dt_utc)

    def test_invalid_days_of_week_raises_exception(self):
        """Malformed days_of_week JSON raises InvalidDaysOfWeekError."""
        alarm = self._make_dummy_alarm(
            time_str="07:00",
            days_of_week="[0, 8]",  # 8 is invalid day
            user_tz="UTC",
        )
        dt_utc = datetime(2026, 9, 9, 7, 0, 0, tzinfo=timezone.utc)
        with self.assertRaises(InvalidDaysOfWeekError):
            is_alarm_due(alarm, current_time=dt_utc)

    def test_missing_timezone_raises_value_error(self):
        """If alarm has no attached user and user_tz is None, raises ValueError."""
        alarm = Alarm(
            id=1,
            user_id=1,
            time="07:00",
            days_of_week="[0, 1, 2, 3, 4]",
            is_active=True,
        )
        alarm.user = None
        dt_utc = datetime(2026, 9, 9, 7, 0, 0, tzinfo=timezone.utc)
        with self.assertRaises(ValueError) as ctx:
            is_alarm_due(alarm, current_time=dt_utc)
        self.assertIn("User timezone must be provided", str(ctx.exception))

    def test_pure_helpers_isolated(self):
        """Verify individual helper functions operate correctly in isolation."""
        # parse_alarm_time
        h, m = parse_alarm_time("23:59")
        self.assertEqual((h, m), (23, 59))
        h, m = parse_alarm_time("00:00")
        self.assertEqual((h, m), (0, 0))

        # is_alarm_time_due
        dt = datetime(2026, 9, 9, 14, 45, 30, tzinfo=timezone.utc)
        self.assertTrue(is_alarm_time_due("14:45", dt))
        self.assertFalse(is_alarm_time_due("14:46", dt))

        # resolve_timezone with ZoneInfo instance
        zi = ZoneInfo("Asia/Kolkata")
        self.assertEqual(resolve_timezone(zi), zi)

        # resolve_timezone with valid string
        self.assertEqual(resolve_timezone("UTC"), ZoneInfo("UTC"))


class TestSchedulerDatabaseIntegration(unittest.TestCase):
    """Database integration tests for get_due_alarms using isolated in-memory SQLite."""

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
        """Clear database tables before each test."""
        with self.TestingSessionLocal() as session:
            for table in reversed(Base.metadata.sorted_tables):
                session.execute(table.delete())
            session.commit()

    def test_get_due_alarms_multi_user_and_timezones(self):
        """Verify get_due_alarms retrieves only active due alarms across multiple users and timezones."""
        with self.TestingSessionLocal() as db:
            # User 1 in Kolkata (+05:30)
            u1 = create_user(db, username="kolkata_user", timezone="Asia/Kolkata")
            # User 2 in New York (-04:00 EDT)
            u2 = create_user(db, username="ny_user", timezone="America/New_York")

            # Alarm 1: User 1, 07:00, Mon-Fri, Active
            a1 = create_alarm(
                db,
                user_id=u1.id,
                time="07:00",
                selected_challenge_type="math",
                days_of_week=[0, 1, 2, 3, 4],
                is_active=True,
            )
            # Alarm 2: User 1, 07:00, Mon-Fri, INACTIVE
            a2 = create_alarm(
                db,
                user_id=u1.id,
                time="07:00",
                selected_challenge_type="dance",
                days_of_week=[0, 1, 2, 3, 4],
                is_active=False,
            )
            # Alarm 3: User 2, 21:30, Mon-Fri, Active
            a3 = create_alarm(
                db,
                user_id=u2.id,
                time="21:30",
                selected_challenge_type="memory",
                days_of_week=[0, 1, 2, 3, 4],
                is_active=True,
            )

            # At Wednesday 01:30:00 UTC:
            # - User 1 local time is 07:00:00 Wednesday -> a1 is DUE, a2 is inactive
            # - User 2 local time is 21:30:00 Tuesday (previous day!) -> a3 is DUE!
            dt_utc = datetime(2026, 9, 9, 1, 30, 0, tzinfo=timezone.utc)
            due = get_due_alarms(db, current_time=dt_utc)
            due_ids = [a.id for a in due]

            self.assertIn(a1.id, due_ids)
            self.assertNotIn(a2.id, due_ids)  # Inactive
            self.assertIn(a3.id, due_ids)

            # At Wednesday 01:31:00 UTC (1 minute later) -> neither is due
            dt_next = datetime(2026, 9, 9, 1, 31, 0, tzinfo=timezone.utc)
            due_next = get_due_alarms(db, current_time=dt_next)
            self.assertEqual(len(due_next), 0)


if __name__ == "__main__":
    unittest.main()
