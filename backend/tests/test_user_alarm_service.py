"""Focused test suite for User and Alarm service/repository logic.

Uses an isolated in-memory SQLite database (sqlite:///:memory:) to guarantee
that the local development database (smartwake.db) is never polluted.
"""
import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.exceptions import (
    InvalidAlarmTimeError,
    InvalidChallengeTypeError,
    InvalidDifficultyError,
    UserNotFoundError,
)
from backend.app.database.base import Base
# Ensure all models are imported so Base.metadata knows about them
import backend.app.models
from backend.app.services.alarm_service import (
    VALID_CHALLENGE_TYPES,
    VALID_DIFFICULTIES,
    create_alarm,
    get_alarm_by_id,
    get_alarms_by_user,
)
from backend.app.services.user_service import (
    create_user,
    get_user_by_id,
    get_user_by_username,
)


class TestUserAndAlarmService(unittest.TestCase):
    """Test suite covering User and Alarm persistence, validation, and retrieval."""

    @classmethod
    def setUpClass(cls):
        """Set up an isolated in-memory SQLite database for the test class."""
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.TestingSessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=cls.engine
        )
        # Create all tables in the isolated in-memory database
        Base.metadata.create_all(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        """Clean up in-memory database tables."""
        Base.metadata.drop_all(bind=cls.engine)
        cls.engine.dispose()

    def setUp(self):
        """Open a fresh session for each test."""
        self.db: Session = self.TestingSessionLocal()

    def tearDown(self):
        """Rollback and close session after each test."""
        self.db.rollback()
        self.db.close()

    # -------------------------------------------------------------------------
    # Test 1 & 2: User Creation and Retrieval
    # -------------------------------------------------------------------------

    def test_01_create_user_successfully(self):
        """1. Create a user successfully."""
        user = create_user(
            db=self.db,
            username="alice",
            email="alice@example.com",
            timezone="America/New_York",
        )
        self.assertIsNotNone(user.id)
        self.assertEqual(user.username, "alice")
        self.assertEqual(user.email, "alice@example.com")
        self.assertEqual(user.timezone, "America/New_York")
        self.assertIsNotNone(user.created_at)

    def test_02_retrieve_created_user(self):
        """2. Retrieve the created user by ID and username."""
        user = create_user(db=self.db, username="bob", email="bob@example.com")

        # Retrieve by ID
        fetched_by_id = get_user_by_id(self.db, user.id)
        self.assertIsNotNone(fetched_by_id)
        self.assertEqual(fetched_by_id.id, user.id)
        self.assertEqual(fetched_by_id.username, "bob")

        # Retrieve by username
        fetched_by_username = get_user_by_username(self.db, "bob")
        self.assertIsNotNone(fetched_by_username)
        self.assertEqual(fetched_by_username.id, user.id)

    # -------------------------------------------------------------------------
    # Test 3, 4, 5, 6: Alarm Creation and Field Preservation
    # -------------------------------------------------------------------------

    def test_03_create_alarm_successfully(self):
        """3. Create an alarm for an existing user."""
        user = create_user(db=self.db, username="charlie")
        alarm = create_alarm(
            db=self.db,
            user_id=user.id,
            time="07:00",
            selected_challenge_type="tongue_twister",
            difficulty_preference="adaptive",
            label="Morning Wake-up",
            days_of_week=[0, 1, 2, 3, 4],
        )
        self.assertIsNotNone(alarm.id)
        self.assertEqual(alarm.user_id, user.id)
        self.assertTrue(alarm.is_active)

    def test_04_alarm_preserves_selected_task_type(self):
        """4. Verify the alarm preserves the user's selected task type."""
        user = create_user(db=self.db, username="david")

        # Test each of the five mandatory task types
        for task_type in VALID_CHALLENGE_TYPES:
            alarm = create_alarm(
                db=self.db,
                user_id=user.id,
                time="06:30",
                selected_challenge_type=task_type,
                difficulty_preference="medium",
            )
            self.assertEqual(
                alarm.selected_challenge_type,
                task_type,
                f"Alarm failed to preserve task type '{task_type}'",
            )

    def test_05_alarm_preserves_requested_alarm_time(self):
        """5. Verify the alarm preserves the exact requested alarm time."""
        user = create_user(db=self.db, username="eve")
        test_times = ["05:45", "07:00", "08:15", "23:59"]

        for t in test_times:
            alarm = create_alarm(
                db=self.db,
                user_id=user.id,
                time=t,
                selected_challenge_type="math",
                difficulty_preference="easy",
            )
            self.assertEqual(alarm.time, t, f"Alarm failed to preserve requested time '{t}'")

    def test_06_alarm_preserves_baseline_difficulty(self):
        """6. Verify the baseline difficulty preference is preserved."""
        user = create_user(db=self.db, username="frank")

        for diff in VALID_DIFFICULTIES:
            alarm = create_alarm(
                db=self.db,
                user_id=user.id,
                time="07:30",
                selected_challenge_type="push_ups",
                difficulty_preference=diff,
            )
            self.assertEqual(
                alarm.difficulty_preference,
                diff,
                f"Alarm failed to preserve difficulty preference '{diff}'",
            )

    # -------------------------------------------------------------------------
    # Test 7 & 8: Rejection Validation Rules
    # -------------------------------------------------------------------------

    def test_07_reject_invalid_task_type(self):
        """7. Reject an invalid task type (e.g. number guessing, trivia)."""
        user = create_user(db=self.db, username="grace")
        invalid_types = ["number_guessing", "trivia", "sudoku", "", "invalid_type"]

        for bad_type in invalid_types:
            with self.assertRaises(InvalidChallengeTypeError):
                create_alarm(
                    db=self.db,
                    user_id=user.id,
                    time="07:00",
                    selected_challenge_type=bad_type,
                )

    def test_08_reject_invalid_user_id(self):
        """8. Reject an invalid, non-existent user ID."""
        non_existent_user_id = 999999
        with self.assertRaises(UserNotFoundError):
            create_alarm(
                db=self.db,
                user_id=non_existent_user_id,
                time="07:00",
                selected_challenge_type="dance",
            )

    # -------------------------------------------------------------------------
    # Test 9: Retrieval of Alarms Belonging to a User
    # -------------------------------------------------------------------------

    def test_09_retrieve_alarms_belonging_to_user(self):
        """9. Retrieve alarms belonging to a user (and verify user isolation)."""
        user1 = create_user(db=self.db, username="helen")
        user2 = create_user(db=self.db, username="ian")

        # Create 3 alarms for Helen
        alarm_h1 = create_alarm(
            db=self.db,
            user_id=user1.id,
            time="06:00",
            selected_challenge_type="push_ups",
            label="Workout",
        )
        alarm_h2 = create_alarm(
            db=self.db,
            user_id=user1.id,
            time="07:15",
            selected_challenge_type="tongue_twister",
            label="Workday",
        )
        alarm_h3 = create_alarm(
            db=self.db,
            user_id=user1.id,
            time="09:00",
            selected_challenge_type="dance",
            label="Weekend",
        )

        # Create 1 alarm for Ian
        alarm_i1 = create_alarm(
            db=self.db,
            user_id=user2.id,
            time="08:00",
            selected_challenge_type="memory",
            label="Ian Alarm",
        )

        # Retrieve Helen's alarms
        helens_alarms = get_alarms_by_user(self.db, user1.id)
        self.assertEqual(len(helens_alarms), 3)
        helen_alarm_ids = {a.id for a in helens_alarms}
        self.assertEqual(helen_alarm_ids, {alarm_h1.id, alarm_h2.id, alarm_h3.id})

        # Retrieve Ian's alarms
        ians_alarms = get_alarms_by_user(self.db, user2.id)
        self.assertEqual(len(ians_alarms), 1)
        self.assertEqual(ians_alarms[0].id, alarm_i1.id)

        # Retrieve specific alarm by ID
        fetched_alarm = get_alarm_by_id(self.db, alarm_h2.id)
        self.assertIsNotNone(fetched_alarm)
        self.assertEqual(fetched_alarm.label, "Workday")
        self.assertEqual(fetched_alarm.selected_challenge_type, "tongue_twister")

    # -------------------------------------------------------------------------
    # Additional Validation Tests
    # -------------------------------------------------------------------------

    def test_10_reject_invalid_time_format(self):
        """Reject invalid time formats (e.g. 25:00, 7:00, noon)."""
        user = create_user(db=self.db, username="jack")
        invalid_times = ["25:00", "7:00", "07:60", "noon", "12:00 PM", ""]

        for bad_time in invalid_times:
            with self.assertRaises(InvalidAlarmTimeError):
                create_alarm(
                    db=self.db,
                    user_id=user.id,
                    time=bad_time,
                    selected_challenge_type="math",
                )

    def test_11_reject_invalid_difficulty_preference(self):
        """Reject unrecognized difficulty preferences."""
        user = create_user(db=self.db, username="karen")
        invalid_diffs = ["expert", "insane", "super_easy", ""]

        for bad_diff in invalid_diffs:
            with self.assertRaises(InvalidDifficultyError):
                create_alarm(
                    db=self.db,
                    user_id=user.id,
                    time="07:00",
                    selected_challenge_type="math",
                    difficulty_preference=bad_diff,
                )


if __name__ == "__main__":
    unittest.main()
