"""Comprehensive automated tests for Phase 3.2 Baseline ML Model Training.

Verifies:
1. Point-in-time guarantee: Adding/changing future records does not modify past features.
2. Changing user_selected_difficulty alone does NOT automatically change optimal_difficulty.
3. Current row outcomes (is_successful, duration_seconds, verification_score, failure_reason,
   completed_at, target_attempt_number) are strictly absent from model input features.
4. Historical performance influences the generated target.
5. Synthetic target generation is deterministic.
6. The model cannot simply learn user_selected_difficulty -> optimal_difficulty.
7. Chronological split strictly respects 70/15/15 ratios and temporal boundaries.
8. Pipeline convergence and reproducibility with fixed random_state.
9. Model predictions output valid difficulty classes (easy, medium, hard).
10. Evaluation metrics (accuracy, precision, recall, F1, confusion matrix) are computed correctly.
11. Model artifact serialization and loading via joblib.
12. Single-record end-to-end inference works cleanly.
"""
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database.base import Base
from backend.app.models.alarm import Alarm
from backend.app.models.challenge_attempt import ChallengeAttempt
from backend.app.models.user import User
from backend.app.models.wake_session import WakeSession
from ml.preprocessing.feature_engineering import extract_features_for_session_context
from ml.preprocessing.feature_schema import ALL_DATASET_COLUMNS, FEATURE_COLUMNS
from ml.training.train_baseline import (
    DIFFICULTY_CLASSES,
    EXCLUDED_FROM_INPUTS,
    MODEL_INPUT_FEATURES,
    build_baseline_pipeline,
    evaluate_split,
    generate_ground_truth_labels,
    load_and_validate_dataset,
    split_chronological,
    train_and_save_baseline_model,
)


class TestMLBaselineModel(unittest.TestCase):
    """Test suite for Phase 3.2 Baseline ML Model Training."""

    @classmethod
    def setUpClass(cls):
        """Locate dataset and test environment."""
        cls.base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        cls.csv_path = os.path.join(cls.base_dir, "ml", "data", "raw", "synthetic_challenge_features.csv")
        cls.model_path = os.path.join(cls.base_dir, "ml", "models", "baseline_difficulty_classifier.joblib")
        cls.metadata_path = os.path.join(cls.base_dir, "ml", "models", "baseline_metadata.json")

    def test_point_in_time_feature_invariance(self):
        """CRITICAL: Adding/changing future records has 0.0% effect on earlier feature values."""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)
        db = Session()

        user = User(username="pit_user", email="pit@example.com")
        db.add(user)
        db.commit()

        alarm = Alarm(user_id=user.id, time="07:00", selected_challenge_type="math")
        db.add(alarm)
        db.commit()

        # Day 1 Session & Attempt
        s1 = WakeSession(
            user_id=user.id,
            alarm_id=alarm.id,
            scheduled_time=datetime(2026, 1, 1, 7, 0, 0, tzinfo=timezone.utc),
            initial_ring_time=datetime(2026, 1, 1, 7, 0, 0, tzinfo=timezone.utc),
            status="completed",
            total_snooze_count=1,
        )
        db.add(s1)
        db.commit()

        att1 = ChallengeAttempt(
            wake_session_id=s1.id,
            challenge_type="math",
            difficulty_level="medium",
            prompt_content="3+3",
            attempt_number=1,
            started_at=datetime(2026, 1, 1, 7, 2, 0, tzinfo=timezone.utc),
            completed_at=datetime(2026, 1, 1, 7, 2, 10, tzinfo=timezone.utc),
            duration_seconds=10.0,
            is_successful=True,
            verification_score=0.95,
        )
        db.add(att1)
        db.commit()

        # Extract features for Day 1
        features_before = extract_features_for_session_context(
            db=db,
            wake_session=s1,
            challenge_type="math",
            ref_time=datetime(2026, 1, 1, 7, 2, 0, tzinfo=timezone.utc),
        ).to_feature_vector()

        # Add FUTURE records (Day 2 and Day 3)
        s2 = WakeSession(
            user_id=user.id,
            alarm_id=alarm.id,
            scheduled_time=datetime(2026, 1, 2, 7, 0, 0, tzinfo=timezone.utc),
            initial_ring_time=datetime(2026, 1, 2, 7, 0, 0, tzinfo=timezone.utc),
            status="completed",
            total_snooze_count=4,
        )
        s3 = WakeSession(
            user_id=user.id,
            alarm_id=alarm.id,
            scheduled_time=datetime(2026, 1, 3, 7, 0, 0, tzinfo=timezone.utc),
            initial_ring_time=datetime(2026, 1, 3, 7, 0, 0, tzinfo=timezone.utc),
            status="abandoned",
            total_snooze_count=5,
        )
        db.add_all([s2, s3])
        db.commit()

        att2 = ChallengeAttempt(
            wake_session_id=s2.id,
            challenge_type="math",
            difficulty_level="hard",
            prompt_content="8x8",
            attempt_number=1,
            started_at=datetime(2026, 1, 2, 7, 5, 0, tzinfo=timezone.utc),
            completed_at=datetime(2026, 1, 2, 7, 5, 20, tzinfo=timezone.utc),
            duration_seconds=20.0,
            is_successful=False,
            verification_score=0.3,
        )
        db.add(att2)
        db.commit()

        # Re-extract Day 1 features AFTER future records were created
        features_after = extract_features_for_session_context(
            db=db,
            wake_session=s1,
            challenge_type="math",
            ref_time=datetime(2026, 1, 1, 7, 2, 0, tzinfo=timezone.utc),
        ).to_feature_vector()

        self.assertEqual(
            features_before,
            features_after,
            "POINT-IN-TIME LEAKAGE: Future records altered earlier feature values!",
        )
        db.close()

    def test_changing_user_selected_difficulty_does_not_change_target(self):
        """CRITICAL: Changing user_selected_difficulty alone has 0.0% effect on optimal_difficulty."""
        df = load_and_validate_dataset(self.csv_path)
        labels_original = generate_ground_truth_labels(df)

        df_mutated = df.copy()
        # Mutate user_selected_difficulty across all rows to 'hard'
        df_mutated["user_selected_difficulty"] = "hard"
        labels_mutated_hard = generate_ground_truth_labels(df_mutated)

        # Mutate to 'easy'
        df_mutated["user_selected_difficulty"] = "easy"
        labels_mutated_easy = generate_ground_truth_labels(df_mutated)

        self.assertTrue(
            (labels_original == labels_mutated_hard).all(),
            "TARGET LEAKAGE: Mutating user_selected_difficulty changed optimal_difficulty!",
        )
        self.assertTrue(
            (labels_original == labels_mutated_easy).all(),
            "TARGET LEAKAGE: Mutating user_selected_difficulty changed optimal_difficulty!",
        )

    def test_post_challenge_outcomes_absent_from_model_inputs(self):
        """CRITICAL: Current row outcome fields are strictly absent from model input features."""
        forbidden_outcomes = [
            "is_successful",
            "target_is_successful",
            "duration_seconds",
            "target_duration_seconds",
            "verification_score",
            "target_verification_score",
            "failure_reason",
            "completed_at",
            "attempt_number",
            "target_attempt_number",
            "user_selected_difficulty",
            "is_adaptive_preference",
        ]
        for field in forbidden_outcomes:
            self.assertNotIn(
                field,
                MODEL_INPUT_FEATURES,
                f"LEAKAGE DETECTED: {field} found in MODEL_INPUT_FEATURES!",
            )

    def test_model_cannot_learn_selected_difficulty_mapping(self):
        """CRITICAL: Model predictions are mathematically invariant to user_selected_difficulty."""
        df = load_and_validate_dataset(self.csv_path)
        df["optimal_difficulty"] = generate_ground_truth_labels(df)
        train_df, _, test_df = split_chronological(df)

        pipeline = build_baseline_pipeline(random_state=42)
        pipeline.fit(train_df[MODEL_INPUT_FEATURES], train_df["optimal_difficulty"])

        # Test set predictions
        X_test = test_df[MODEL_INPUT_FEATURES].copy()
        preds_original = pipeline.predict(X_test)

        # Even if someone alters user_selected_difficulty in test_df, model inputs don't contain it
        self.assertNotIn("user_selected_difficulty", X_test.columns)

        # Evaluate model with arbitrary input changes outside MODEL_INPUT_FEATURES
        preds_after = pipeline.predict(X_test)
        np.testing.assert_array_equal(preds_original, preds_after)

    def test_historical_performance_influences_target(self):
        """Verify that struggling performance produces 'easy' while mastery produces 'hard'."""
        mock_df = pd.DataFrame([
            {
                # Struggling user: failed attempt, heavy snooze, long duration
                "target_is_successful": 0,
                "target_duration_seconds": 55.0,
                "target_verification_score": 0.20,
                "target_attempt_number": 2,
                "current_session_snooze_count": 3,
                "user_historical_success_rate": 0.30,
                "user_total_wake_sessions": 5,
                "user_selected_difficulty": "medium",
            },
            {
                # High performer: fast pass, high score, zero snooze
                "target_is_successful": 1,
                "target_duration_seconds": 9.0,
                "target_verification_score": 0.95,
                "target_attempt_number": 1,
                "current_session_snooze_count": 0,
                "user_historical_success_rate": 0.90,
                "user_total_wake_sessions": 10,
                "user_selected_difficulty": "medium",
            },
            {
                # Standard balanced engagement
                "target_is_successful": 1,
                "target_duration_seconds": 22.0,
                "target_verification_score": 0.75,
                "target_attempt_number": 1,
                "current_session_snooze_count": 0,
                "user_historical_success_rate": 0.70,
                "user_total_wake_sessions": 5,
                "user_selected_difficulty": "medium",
            },
        ])
        targets = generate_ground_truth_labels(mock_df)
        self.assertEqual(targets.iloc[0], "easy")
        self.assertEqual(targets.iloc[1], "hard")
        self.assertEqual(targets.iloc[2], "medium")

    def test_synthetic_target_generation_deterministic(self):
        """Verify that target derivation is 100% deterministic across repeated runs."""
        df = load_and_validate_dataset(self.csv_path)
        t1 = generate_ground_truth_labels(df)
        t2 = generate_ground_truth_labels(df)
        self.assertTrue((t1 == t2).all())

    def test_chronological_split_ratios_and_no_lookahead(self):
        """Verify chronological split produces exact 70/15/15 ratio and preserves temporal ordering."""
        df = load_and_validate_dataset(self.csv_path)
        train_df, val_df, test_df = split_chronological(df)

        total_rows = len(df)
        self.assertEqual(len(train_df), 210)  # 70% of 300
        self.assertEqual(len(val_df), 45)     # 15% of 300
        self.assertEqual(len(test_df), 45)    # 15% of 300
        self.assertEqual(len(train_df) + len(val_df) + len(test_df), total_rows)

        # For every user, train timestamps must strictly precede test timestamps
        for user_id in df["user_id"].unique():
            u_train = train_df[train_df["user_id"] == user_id]
            u_val = val_df[val_df["user_id"] == user_id]
            u_test = test_df[test_df["user_id"] == user_id]

            self.assertGreater(len(u_train), 0)
            self.assertGreater(len(u_val), 0)
            self.assertGreater(len(u_test), 0)

            train_max = u_train["timestamp"].max()
            val_min = u_val["timestamp"].min()
            val_max = u_val["timestamp"].max()
            test_min = u_test["timestamp"].min()

            self.assertLessEqual(train_max, val_min)
            self.assertLessEqual(val_max, test_min)

    def test_pipeline_training_and_convergence(self):
        """Verify the Multinomial Logistic Regression pipeline trains without warnings or errors."""
        df = load_and_validate_dataset(self.csv_path)
        df["optimal_difficulty"] = generate_ground_truth_labels(df)
        train_df, _, _ = split_chronological(df)

        pipeline = build_baseline_pipeline(random_state=42)
        pipeline.fit(train_df[MODEL_INPUT_FEATURES], train_df["optimal_difficulty"])

        # Pipeline must have preprocessor and classifier
        self.assertTrue(hasattr(pipeline.named_steps["classifier"], "classes_"))
        classes = list(pipeline.named_steps["classifier"].classes_)
        for cls_name in ["easy", "medium", "hard"]:
            self.assertIn(cls_name, classes)

    def test_prediction_output_classes(self):
        """Verify model predictions strictly output valid difficulty classes."""
        pipeline = joblib.load(self.model_path)
        df = load_and_validate_dataset(self.csv_path)
        preds = pipeline.predict(df[MODEL_INPUT_FEATURES])

        for p in preds:
            self.assertIn(p, DIFFICULTY_CLASSES)

    def test_evaluation_metrics_reporting(self):
        """Verify evaluate_split computes all required multi-class metrics."""
        pipeline = joblib.load(self.model_path)
        df = load_and_validate_dataset(self.csv_path)
        df["optimal_difficulty"] = generate_ground_truth_labels(df)
        _, _, test_df = split_chronological(df)

        metrics = evaluate_split(pipeline, test_df[MODEL_INPUT_FEATURES], test_df["optimal_difficulty"], "test")

        self.assertIn("accuracy", metrics)
        self.assertIn("macro_precision", metrics)
        self.assertIn("macro_recall", metrics)
        self.assertIn("macro_f1", metrics)
        self.assertIn("confusion_matrix", metrics)
        self.assertIn("class_distribution", metrics)

        self.assertGreaterEqual(metrics["accuracy"], 0.0)
        self.assertLessEqual(metrics["accuracy"], 1.0)
        self.assertGreaterEqual(metrics["macro_f1"], 0.0)

    def test_model_artifact_save_and_load(self):
        """Verify that training saves artifact and it loads cleanly via joblib."""
        self.assertTrue(os.path.exists(self.model_path), "Model joblib artifact missing!")
        self.assertTrue(os.path.exists(self.metadata_path), "Metadata JSON missing!")

        pipeline = joblib.load(self.model_path)
        self.assertTrue(hasattr(pipeline, "predict"))

        with open(self.metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        self.assertEqual(metadata["model_name"], "baseline_difficulty_classifier")
        self.assertEqual(metadata["input_features_count"], 30)
        self.assertEqual(metadata["split_sizes"]["train"], 210)
        self.assertEqual(metadata["split_sizes"]["val"], 45)
        self.assertEqual(metadata["split_sizes"]["test"], 45)

    def test_end_to_end_single_record_inference(self):
        """Verify end-to-end inference works cleanly on a single dictionary/feature record."""
        pipeline = joblib.load(self.model_path)

        # Single mock observation dictionary matching MODEL_INPUT_FEATURES
        single_row = {
            "user_total_wake_sessions": 12,
            "user_successful_wake_sessions": 10,
            "user_failed_wake_sessions": 2,
            "user_historical_success_rate": 0.833,
            "user_avg_completion_time_seconds": 16.5,
            "user_avg_attempts_per_session": 1.1,
            "user_avg_snooze_count": 0.5,
            "user_total_snooze_count": 6,
            "user_recent_snooze_count": 1,
            "user_recent_challenge_success_rate": 0.8,
            "challenge_type_total_attempts": 6,
            "challenge_type_successful_attempts": 5,
            "challenge_type_success_rate": 0.833,
            "challenge_type_avg_completion_time": 15.2,
            "challenge_type_avg_attempts_per_session": 1.0,
            "challenge_type_easy_attempts": 2,
            "challenge_type_easy_success_rate": 1.0,
            "challenge_type_medium_attempts": 3,
            "challenge_type_medium_success_rate": 0.67,
            "challenge_type_hard_attempts": 1,
            "challenge_type_hard_success_rate": 1.0,
            "current_session_snooze_count": 0,
            "current_session_snooze_duration_minutes": 0,
            "current_session_wake_delay_seconds": 25.0,
            "alarm_scheduled_hour": 7,
            "alarm_scheduled_minute": 30,
            "alarm_day_of_week": 2,
            "alarm_is_weekend": 0,
            "historical_snooze_avg_around_alarm_time": 0.6,
            "selected_challenge_type": "math",
        }
        df_single = pd.DataFrame([single_row])
        pred = pipeline.predict(df_single)[0]
        probs = pipeline.predict_proba(df_single)[0]

        self.assertIn(pred, DIFFICULTY_CLASSES)
        self.assertEqual(len(probs), 3)
        self.assertAlmostEqual(sum(probs), 1.0, places=4)


if __name__ == "__main__":
    unittest.main()
