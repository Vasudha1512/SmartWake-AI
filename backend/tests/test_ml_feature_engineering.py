"""Comprehensive automated tests for Phase 3.0 ML Feature Engineering and Data Preparation.

Verifies:
- Empty database does not crash and returns valid empty dataset
- Correct canonical feature columns and counts exist
- Historical attempts correctly aggregated into feature vectors
- Challenge-type filtering isolates metrics to selected challenge type
- Snooze features are calculated correctly and respect temporal cutoffs
- Success-rate calculations and divisions by zero are guarded
- Alarm-time and calendar context features are correct
- No data leakage from current challenge outcome into input features
- Deterministic synthetic dataset generation across runs
- Synthetic generation NEVER writes to production smartwake.db
"""
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database.base import Base
from backend.app.models.alarm import Alarm
from backend.app.models.challenge import Challenge
from backend.app.models.challenge_attempt import ChallengeAttempt
from backend.app.models.snooze_event import SnoozeEvent
from backend.app.models.user import User
from backend.app.models.wake_session import WakeSession
from ml.preprocessing.feature_engineering import (
    extract_features_for_attempt,
    extract_features_for_session_context,
)
from ml.preprocessing.feature_schema import (
    ALARM_CONTEXT_FEATURES,
    ALL_DATASET_COLUMNS,
    CHALLENGE_HISTORY_FEATURES,
    CURRENT_CONTEXT_FEATURES,
    FEATURE_COLUMNS,
    METADATA_COLUMNS,
    SNOOZE_HISTORY_FEATURES,
    TARGET_COLUMNS,
    USER_HISTORY_FEATURES,
    ChallengeFeatureRecord,
)
from ml.synthetic_generator import SyntheticMLDataGenerator, generate_synthetic_dataset
from ml.training.dataset_builder import (
    build_challenge_feature_dataframe,
    build_challenge_feature_dataset,
    build_challenge_feature_records,
)


class TestMLFeatureEngineering(unittest.TestCase):
    """Test suite for ML feature extraction and dataset construction."""

    def setUp(self):
        """Create isolated in-memory SQLite database for each test."""
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.db = self.SessionLocal()

    def tearDown(self):
        """Clean up in-memory database session and tables."""
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)

    def test_feature_column_schema_counts(self):
        """Verify canonical feature column lists, categories, and dataset schema."""
        self.assertEqual(len(USER_HISTORY_FEATURES), 10)
        self.assertEqual(len(CHALLENGE_HISTORY_FEATURES), 11)
        self.assertEqual(len(SNOOZE_HISTORY_FEATURES), 3)
        self.assertEqual(len(ALARM_CONTEXT_FEATURES), 5)
        self.assertEqual(len(CURRENT_CONTEXT_FEATURES), 3)
        self.assertEqual(len(FEATURE_COLUMNS), 32)
        self.assertEqual(len(TARGET_COLUMNS), 4)
        self.assertEqual(len(METADATA_COLUMNS), 5)
        self.assertEqual(len(ALL_DATASET_COLUMNS), 5 + 32 + 4)

    def test_empty_database_does_not_crash(self):
        """Ensure empty database safely returns empty lists and DataFrames without crashing."""
        records = build_challenge_feature_records(self.db)
        self.assertEqual(records, [])

        dataset = build_challenge_feature_dataset(self.db)
        self.assertEqual(dataset, [])

        df = build_challenge_feature_dataframe(self.db)
        self.assertEqual(len(df), 0)
        self.assertEqual(list(df.columns), ALL_DATASET_COLUMNS)

    def test_cold_start_new_user_default_features(self):
        """Verify that a brand new user with 0 prior history produces neutral default values."""
        user = User(username="newuser", email="newuser@example.com")
        self.db.add(user)
        self.db.commit()

        alarm = Alarm(
            user_id=user.id,
            time="07:00",
            selected_challenge_type="math",
            difficulty_preference="adaptive",
        )
        self.db.add(alarm)
        self.db.commit()

        session = WakeSession(
            user_id=user.id,
            alarm_id=alarm.id,
            scheduled_time=datetime(2026, 3, 10, 7, 0, 0, tzinfo=timezone.utc),
            initial_ring_time=datetime(2026, 3, 10, 7, 0, 0, tzinfo=timezone.utc),
            status="ringing",
        )
        self.db.add(session)
        self.db.commit()

        record = extract_features_for_session_context(
            db=self.db,
            wake_session=session,
            challenge_type="math",
            difficulty_preference="adaptive",
        )

        self.assertIsInstance(record, ChallengeFeatureRecord)
        self.assertEqual(record.user_total_wake_sessions, 0)
        self.assertEqual(record.user_successful_wake_sessions, 0)
        self.assertEqual(record.user_historical_success_rate, 0.0)
        self.assertEqual(record.user_avg_completion_time_seconds, 0.0)
        self.assertEqual(record.user_avg_snooze_count, 0.0)
        self.assertEqual(record.challenge_type_total_attempts, 0)
        self.assertEqual(record.challenge_type_success_rate, 0.0)
        self.assertEqual(record.current_session_snooze_count, 0)
        self.assertEqual(record.alarm_scheduled_hour, 7)
        self.assertEqual(record.selected_challenge_type, "math")
        self.assertEqual(record.is_adaptive_preference, 1)

    def test_historical_aggregations_and_success_rates(self):
        """Verify multi-session historical calculations across days."""
        user = User(username="testuser", email="testuser@example.com")
        self.db.add(user)
        self.db.commit()

        alarm = Alarm(
            user_id=user.id,
            time="07:00",
            selected_challenge_type="tongue_twister",
            difficulty_preference="medium",
        )
        self.db.add(alarm)
        self.db.commit()

        # Day 1: completed, 1 snooze, 1 successful attempt (15.0s)
        s1 = WakeSession(
            user_id=user.id,
            alarm_id=alarm.id,
            scheduled_time=datetime(2026, 3, 1, 7, 0, 0, tzinfo=timezone.utc),
            initial_ring_time=datetime(2026, 3, 1, 7, 0, 0, tzinfo=timezone.utc),
            status="completed",
            total_snooze_count=1,
        )
        self.db.add(s1)
        self.db.commit()

        att1 = ChallengeAttempt(
            wake_session_id=s1.id,
            challenge_type="tongue_twister",
            difficulty_level="medium",
            prompt_content="Sample prompt 1",
            attempt_number=1,
            started_at=datetime(2026, 3, 1, 7, 5, 0, tzinfo=timezone.utc),
            completed_at=datetime(2026, 3, 1, 7, 5, 15, tzinfo=timezone.utc),
            duration_seconds=15.0,
            is_successful=True,
            verification_score=0.95,
        )
        self.db.add(att1)
        self.db.commit()

        # Day 2: abandoned, 2 snoozes, 1 failed attempt (35.0s)
        s2 = WakeSession(
            user_id=user.id,
            alarm_id=alarm.id,
            scheduled_time=datetime(2026, 3, 2, 7, 0, 0, tzinfo=timezone.utc),
            initial_ring_time=datetime(2026, 3, 2, 7, 0, 0, tzinfo=timezone.utc),
            status="abandoned",
            total_snooze_count=2,
        )
        self.db.add(s2)
        self.db.commit()

        att2 = ChallengeAttempt(
            wake_session_id=s2.id,
            challenge_type="tongue_twister",
            difficulty_level="medium",
            prompt_content="Sample prompt 2",
            attempt_number=1,
            started_at=datetime(2026, 3, 2, 7, 10, 0, tzinfo=timezone.utc),
            completed_at=datetime(2026, 3, 2, 7, 10, 35, tzinfo=timezone.utc),
            duration_seconds=35.0,
            is_successful=False,
            verification_score=0.40,
        )
        self.db.add(att2)
        self.db.commit()

        # Day 3: current session
        s3 = WakeSession(
            user_id=user.id,
            alarm_id=alarm.id,
            scheduled_time=datetime(2026, 3, 3, 7, 0, 0, tzinfo=timezone.utc),
            initial_ring_time=datetime(2026, 3, 3, 7, 0, 0, tzinfo=timezone.utc),
            status="ringing",
            total_snooze_count=0,
        )
        self.db.add(s3)
        self.db.commit()

        record = extract_features_for_session_context(
            db=self.db,
            wake_session=s3,
            challenge_type="tongue_twister",
            difficulty_preference="medium",
            ref_time=datetime(2026, 3, 3, 7, 1, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(record.user_total_wake_sessions, 2)
        self.assertEqual(record.user_successful_wake_sessions, 1)
        self.assertEqual(record.user_failed_wake_sessions, 1)
        self.assertEqual(record.user_historical_success_rate, 0.5)
        self.assertEqual(record.user_total_snooze_count, 3)
        self.assertEqual(record.user_avg_snooze_count, 1.5)
        self.assertEqual(record.user_recent_snooze_count, 2)  # Most recent Day 2 had 2 snoozes
        self.assertEqual(record.user_avg_completion_time_seconds, 15.0)  # Only successful duration
        self.assertEqual(record.challenge_type_total_attempts, 2)
        self.assertEqual(record.challenge_type_successful_attempts, 1)
        self.assertEqual(record.challenge_type_success_rate, 0.5)
        self.assertEqual(record.challenge_type_medium_attempts, 2)
        self.assertEqual(record.challenge_type_medium_success_rate, 0.5)

    def test_challenge_type_filtering_isolation(self):
        """Verify that challenge-specific metrics only aggregate attempts of the selected type."""
        user = User(username="math_user", email="math_user@example.com")
        self.db.add(user)
        self.db.commit()

        alarm = Alarm(user_id=user.id, time="08:00", selected_challenge_type="math")
        self.db.add(alarm)
        self.db.commit()

        s1 = WakeSession(
            user_id=user.id,
            alarm_id=alarm.id,
            scheduled_time=datetime(2026, 3, 1, 8, 0, 0, tzinfo=timezone.utc),
            initial_ring_time=datetime(2026, 3, 1, 8, 0, 0, tzinfo=timezone.utc),
            status="completed",
        )
        self.db.add(s1)
        self.db.commit()

        # Math attempt (successful, 10s)
        att_math = ChallengeAttempt(
            wake_session_id=s1.id,
            challenge_type="math",
            difficulty_level="easy",
            prompt_content="5 + 3 = ?",
            attempt_number=1,
            started_at=datetime(2026, 3, 1, 8, 1, 0, tzinfo=timezone.utc),
            completed_at=datetime(2026, 3, 1, 8, 1, 10, tzinfo=timezone.utc),
            duration_seconds=10.0,
            is_successful=True,
        )
        # Dance attempt in same history (failed, 40s)
        att_dance = ChallengeAttempt(
            wake_session_id=s1.id,
            challenge_type="dance",
            difficulty_level="medium",
            prompt_content="Dance steps",
            attempt_number=2,
            started_at=datetime(2026, 3, 1, 8, 2, 0, tzinfo=timezone.utc),
            completed_at=datetime(2026, 3, 1, 8, 2, 40, tzinfo=timezone.utc),
            duration_seconds=40.0,
            is_successful=False,
        )
        self.db.add_all([att_math, att_dance])
        self.db.commit()

        # Current session evaluating "math"
        s2 = WakeSession(
            user_id=user.id,
            alarm_id=alarm.id,
            scheduled_time=datetime(2026, 3, 2, 8, 0, 0, tzinfo=timezone.utc),
            initial_ring_time=datetime(2026, 3, 2, 8, 0, 0, tzinfo=timezone.utc),
            status="ringing",
        )
        self.db.add(s2)
        self.db.commit()

        rec = extract_features_for_session_context(
            db=self.db,
            wake_session=s2,
            challenge_type="math",
            ref_time=datetime(2026, 3, 2, 8, 1, 0, tzinfo=timezone.utc),
        )

        # Global metrics include both
        self.assertEqual(rec.user_avg_attempts_per_session, 2.0)
        # Math-specific metrics must only count math attempt
        self.assertEqual(rec.challenge_type_total_attempts, 1)
        self.assertEqual(rec.challenge_type_successful_attempts, 1)
        self.assertEqual(rec.challenge_type_success_rate, 1.0)
        self.assertEqual(rec.challenge_type_avg_completion_time, 10.0)
        self.assertEqual(rec.challenge_type_easy_attempts, 1)
        self.assertEqual(rec.challenge_type_easy_success_rate, 1.0)
        self.assertEqual(rec.challenge_type_medium_attempts, 0)

    def test_snooze_features_and_temporal_cutoff(self):
        """Verify snooze features respect the pre-attempt temporal horizon."""
        user = User(username="snoozer", email="snoozer@example.com")
        self.db.add(user)
        self.db.commit()

        alarm = Alarm(user_id=user.id, time="06:30", selected_challenge_type="memory")
        self.db.add(alarm)
        self.db.commit()

        s = WakeSession(
            user_id=user.id,
            alarm_id=alarm.id,
            scheduled_time=datetime(2026, 3, 5, 6, 30, 0, tzinfo=timezone.utc),
            initial_ring_time=datetime(2026, 3, 5, 6, 30, 0, tzinfo=timezone.utc),
            status="in_challenge",
        )
        self.db.add(s)
        self.db.commit()

        # Snooze 1 at 06:30 (5 min)
        snz1 = SnoozeEvent(
            wake_session_id=s.id,
            snooze_number=1,
            snoozed_at=datetime(2026, 3, 5, 6, 30, 0, tzinfo=timezone.utc),
            snooze_duration_minutes=5,
        )
        # Snooze 2 at 06:35 (5 min)
        snz2 = SnoozeEvent(
            wake_session_id=s.id,
            snooze_number=2,
            snoozed_at=datetime(2026, 3, 5, 6, 35, 0, tzinfo=timezone.utc),
            snooze_duration_minutes=5,
        )
        # Snooze 3 occurs at 06:50 (AFTER our reference attempt start at 06:42)
        snz3 = SnoozeEvent(
            wake_session_id=s.id,
            snooze_number=3,
            snoozed_at=datetime(2026, 3, 5, 6, 50, 0, tzinfo=timezone.utc),
            snooze_duration_minutes=5,
        )
        self.db.add_all([snz1, snz2, snz3])
        self.db.commit()

        ref_time = datetime(2026, 3, 5, 6, 42, 0, tzinfo=timezone.utc)
        rec = extract_features_for_session_context(
            db=self.db,
            wake_session=s,
            challenge_type="memory",
            ref_time=ref_time,
        )

        # Only snoozes 1 and 2 should be included
        self.assertEqual(rec.current_session_snooze_count, 2)
        self.assertEqual(rec.current_session_snooze_duration_minutes, 10)
        self.assertAlmostEqual(rec.current_session_wake_delay_seconds, 720.0, delta=1.0)

    def test_alarm_context_and_calendar_features(self):
        """Verify scheduled hour, minute, day of week, and weekend detection."""
        user = User(username="weekend_user", email="weekend_user@example.com")
        self.db.add(user)
        self.db.commit()

        # 2026-03-07 is Saturday
        s_sat = WakeSession(
            user_id=user.id,
            scheduled_time=datetime(2026, 3, 7, 9, 45, 0, tzinfo=timezone.utc),
            initial_ring_time=datetime(2026, 3, 7, 9, 45, 0, tzinfo=timezone.utc),
            status="ringing",
        )
        self.db.add(s_sat)
        self.db.commit()

        rec = extract_features_for_session_context(
            db=self.db,
            wake_session=s_sat,
            challenge_type="push_ups",
            ref_time=datetime(2026, 3, 7, 9, 45, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(rec.alarm_scheduled_hour, 9)
        self.assertEqual(rec.alarm_scheduled_minute, 45)
        self.assertEqual(rec.alarm_day_of_week, 5)  # Saturday
        self.assertEqual(rec.alarm_is_weekend, 1)

    def test_no_data_leakage_from_current_outcome(self):
        """CRITICAL: Assert that mutating current attempt outcome produces bitwise identical features."""
        user = User(username="leak_test", email="leak_test@example.com")
        self.db.add(user)
        self.db.commit()

        s = WakeSession(
            user_id=user.id,
            scheduled_time=datetime(2026, 3, 10, 7, 0, 0, tzinfo=timezone.utc),
            initial_ring_time=datetime(2026, 3, 10, 7, 0, 0, tzinfo=timezone.utc),
            status="in_challenge",
        )
        self.db.add(s)
        self.db.commit()

        # Attempt in state A: Failed, 50s duration, score 0.20, failure reason "timeout"
        att = ChallengeAttempt(
            wake_session_id=s.id,
            challenge_type="dance",
            difficulty_level="hard",
            prompt_content="Dance routine A",
            attempt_number=1,
            started_at=datetime(2026, 3, 10, 7, 2, 0, tzinfo=timezone.utc),
            completed_at=datetime(2026, 3, 10, 7, 2, 50, tzinfo=timezone.utc),
            duration_seconds=50.0,
            is_successful=False,
            verification_score=0.20,
            failure_reason="timeout",
        )
        self.db.add(att)
        self.db.commit()

        rec_failed = extract_features_for_attempt(self.db, att)
        features_failed = rec_failed.to_feature_vector()

        # Mutate attempt to state B: Succeeded, 4.2s duration, score 0.99, no failure reason
        att.is_successful = True
        att.duration_seconds = 4.2
        att.verification_score = 0.99
        att.failure_reason = None
        self.db.commit()

        rec_success = extract_features_for_attempt(self.db, att)
        features_success = rec_success.to_feature_vector()

        # Input feature vectors must be 100% identical!
        self.assertEqual(
            features_failed,
            features_success,
            "DATA LEAKAGE DETECTED: Features varied when changing current attempt outcome!",
        )

        # Only the explicit target fields should differ
        self.assertEqual(rec_failed.target_is_successful, 0)
        self.assertEqual(rec_success.target_is_successful, 1)
        self.assertEqual(rec_failed.target_duration_seconds, 50.0)
        self.assertEqual(rec_success.target_duration_seconds, 4.2)
        self.assertEqual(rec_failed.target_verification_score, 0.20)
        self.assertEqual(rec_success.target_verification_score, 0.99)

    def test_synthetic_dataset_determinism(self):
        """Verify that SyntheticMLDataGenerator produces identical results with the same seed."""
        with tempfile.TemporaryDirectory() as tmpdir1, tempfile.TemporaryDirectory() as tmpdir2:
            gen1 = SyntheticMLDataGenerator(seed=123)
            data1 = gen1.generate(num_users=3, days_per_user=5, output_dir=tmpdir1)

            gen2 = SyntheticMLDataGenerator(seed=123)
            data2 = gen2.generate(num_users=3, days_per_user=5, output_dir=tmpdir2)

            self.assertEqual(len(data1), len(data2))
            self.assertEqual(len(data1), 15)  # 3 users * 5 days

            for r1, r2 in zip(data1, data2):
                self.assertEqual(r1.to_dict(), r2.to_dict())

            # Verify files were created
            json1 = os.path.join(tmpdir1, "synthetic_challenge_attempts.json")
            csv1 = os.path.join(tmpdir1, "synthetic_challenge_features.csv")
            self.assertTrue(os.path.exists(json1))
            self.assertTrue(os.path.exists(csv1))

    def test_synthetic_generation_does_not_modify_production_db(self):
        """CRITICAL: Ensure synthetic generation never writes records to the production database."""
        prod_db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "smartwake.db",
        )
        if not os.path.exists(prod_db_path):
            self.skipTest("smartwake.db not found at root")

        # Read attempt count before
        conn = sqlite3.connect(prod_db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM challenge_attempts")
        attempts_before = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM wake_sessions")
        sessions_before = cur.fetchone()[0]
        conn.close()

        # Run synthetic generator
        with tempfile.TemporaryDirectory() as tmpdir:
            SyntheticMLDataGenerator(seed=42).generate(num_users=2, days_per_user=2, output_dir=tmpdir)

        # Check counts after
        conn = sqlite3.connect(prod_db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM challenge_attempts")
        attempts_after = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM wake_sessions")
        sessions_after = cur.fetchone()[0]
        conn.close()

        self.assertEqual(attempts_before, attempts_after, "Synthetic generator modified production database attempts!")
        self.assertEqual(sessions_before, sessions_after, "Synthetic generator modified production database sessions!")


if __name__ == "__main__":
    unittest.main()
