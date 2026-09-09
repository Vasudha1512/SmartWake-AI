"""Focused automated tests verifying SQLite foreign-key enforcement.

Verifies that PRAGMA foreign_keys = ON is active across SQLite connections and that:
A. Valid foreign-key relationships persist cleanly.
B. Invalid foreign-key references are rejected with IntegrityError (no silent inserts).
C. ON DELETE CASCADE and ON DELETE SET NULL behaviors are strictly enforced by SQLite.

Uses an isolated in-memory SQLite database (sqlite:///:memory:) to protect smartwake.db.
"""
from datetime import datetime
import unittest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.datetime_utils import now_utc_naive
from backend.app.database.base import Base
# Importing backend.app.database.session ensures the SQLite event listener is registered
import backend.app.database.session
import backend.app.models
from backend.app.models.alarm import Alarm
from backend.app.models.user import User
from backend.app.models.wake_session import WakeSession


class TestSQLiteForeignKeyEnforcement(unittest.TestCase):
    """Test suite proving SQLite foreign-key enforcement and cascade constraints."""

    @classmethod
    def setUpClass(cls):
        """Create an isolated in-memory database with all models registered."""
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
        """Tear down in-memory database."""
        Base.metadata.drop_all(bind=cls.engine)
        cls.engine.dispose()

    def setUp(self):
        """Clean all tables before each test to ensure state isolation."""
        with self.TestingSessionLocal() as session:
            for table in reversed(Base.metadata.sorted_tables):
                session.execute(table.delete())
            session.commit()

    def test_pragma_foreign_keys_is_enabled(self):
        """Verify PRAGMA foreign_keys is enabled (returns 1) on SQLite connections."""
        with self.engine.connect() as conn:
            result = conn.exec_driver_sql("PRAGMA foreign_keys").scalar()
            self.assertEqual(result, 1, "PRAGMA foreign_keys should be 1 (ON).")

    # --- Minimum Requirement A: Valid foreign-key relationship still works ---

    def test_valid_foreign_key_insert_succeeds(self):
        """Verify creating an Alarm referencing a valid User succeeds."""
        with self.TestingSessionLocal() as session:
            user = User(username="fk_tester", timezone="UTC")
            session.add(user)
            session.commit()
            session.refresh(user)

            alarm = Alarm(
                user_id=user.id,
                time="07:00",
                selected_challenge_type="math",
                difficulty_preference="adaptive",
                label="Valid FK Alarm",
                days_of_week="[0,1,2,3,4]",
                is_active=True,
            )
            session.add(alarm)
            session.commit()
            session.refresh(alarm)

            self.assertIsNotNone(alarm.id)
            self.assertEqual(alarm.user_id, user.id)
            self.assertEqual(alarm.user.username, "fk_tester")

    # --- Minimum Requirement B: Invalid foreign-key reference cannot be silently inserted ---

    def test_invalid_foreign_key_user_id_rejected_on_alarm(self):
        """Verify inserting an Alarm with a non-existent user_id raises IntegrityError."""
        with self.TestingSessionLocal() as session:
            non_existent_user_id = 99999
            orphan_alarm = Alarm(
                user_id=non_existent_user_id,
                time="07:00",
                selected_challenge_type="dance",
                difficulty_preference="easy",
                label="Orphan Alarm",
                days_of_week="[0,1,2,3,4]",
                is_active=True,
            )
            session.add(orphan_alarm)

            with self.assertRaises(IntegrityError) as ctx:
                session.commit()

            # Confirm the underlying constraint failure mentions foreign key
            self.assertIn(
                "foreign key",
                str(ctx.exception).lower(),
                "IntegrityError should indicate a foreign key constraint failure.",
            )

    def test_invalid_foreign_key_user_id_rejected_on_wake_session(self):
        """Verify inserting a WakeSession with non-existent user_id raises IntegrityError."""
        with self.TestingSessionLocal() as session:
            now = now_utc_naive()
            bad_session = WakeSession(
                user_id=88888,
                scheduled_time=now,
                initial_ring_time=now,
                status="ringing",
            )
            session.add(bad_session)

            with self.assertRaises(IntegrityError):
                session.commit()

    # --- Minimum Requirement C: ON DELETE behavior is actually enforced by SQLite ---

    def test_on_delete_cascade_user_deletes_alarms(self):
        """Verify deleting a User cascades and deletes all associated Alarms."""
        with self.TestingSessionLocal() as session:
            user = User(username="cascade_user", timezone="UTC")
            session.add(user)
            session.commit()
            session.refresh(user)
            user_id = user.id

            alarm1 = Alarm(
                user_id=user_id,
                time="06:00",
                selected_challenge_type="push_ups",
                difficulty_preference="hard",
                days_of_week="[0,1,2]",
                is_active=True,
            )
            alarm2 = Alarm(
                user_id=user_id,
                time="08:00",
                selected_challenge_type="memory",
                difficulty_preference="medium",
                days_of_week="[3,4]",
                is_active=True,
            )
            session.add_all([alarm1, alarm2])
            session.commit()

            # Confirm 2 alarms exist
            alarms_before = session.execute(
                select(Alarm).where(Alarm.user_id == user_id)
            ).scalars().all()
            self.assertEqual(len(alarms_before), 2)

            # Delete the parent User directly via raw SQL execution to verify SQLite DB engine enforcement
            session.execute(User.__table__.delete().where(User.id == user_id))
            session.commit()

            # Verify that SQLite engine cascaded the deletion to alarms
            alarms_after = session.execute(
                select(Alarm).where(Alarm.user_id == user_id)
            ).scalars().all()
            self.assertEqual(
                len(alarms_after),
                0,
                "SQLite should have cascaded deletion of alarms when parent user was deleted.",
            )

    def test_on_delete_set_null_alarm_preserves_wake_session(self):
        """Verify deleting an Alarm sets wake_sessions.alarm_id to NULL (ON DELETE SET NULL)."""
        with self.TestingSessionLocal() as session:
            user = User(username="set_null_user", timezone="UTC")
            session.add(user)
            session.commit()
            session.refresh(user)

            alarm = Alarm(
                user_id=user.id,
                time="07:30",
                selected_challenge_type="tongue_twister",
                difficulty_preference="adaptive",
                days_of_week="[0,1,2,3,4]",
                is_active=True,
            )
            session.add(alarm)
            session.commit()
            session.refresh(alarm)
            alarm_id = alarm.id

            now = now_utc_naive()
            wake_session = WakeSession(
                user_id=user.id,
                alarm_id=alarm_id,
                scheduled_time=now,
                initial_ring_time=now,
                status="completed",
            )
            session.add(wake_session)
            session.commit()
            session.refresh(wake_session)
            session_id = wake_session.id

            # Confirm initial linkage
            self.assertEqual(wake_session.alarm_id, alarm_id)

            # Delete the Alarm directly at SQL level
            session.execute(Alarm.__table__.delete().where(Alarm.id == alarm_id))
            session.commit()

            # Fetch the WakeSession from a fresh query
            persisted_session = session.get(WakeSession, session_id)
            self.assertIsNotNone(persisted_session, "WakeSession should still exist.")
            self.assertIsNone(
                persisted_session.alarm_id,
                "alarm_id should have been set to NULL by SQLite ON DELETE SET NULL.",
            )


if __name__ == "__main__":
    unittest.main()
