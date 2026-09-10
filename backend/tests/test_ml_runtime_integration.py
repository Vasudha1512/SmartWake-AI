"""Test suite for Phase 3.6.3 — Offline <-> Runtime Prediction Parity.

Verifies:
1. 100% parity between offline DifficultyPredictor and runtime ModelInferenceManager.
2. Identical top predicted class on diverse feature observations.
3. Probability difference < 1e-6 across all classes.
4. Invariance to dictionary key ordering permutations.
5. Canonical 30-feature schema enforcement and rejection of malformed inputs.
6. Batch prediction consistency matching single-row predictions.
7. Parity on features produced by database feature extraction.
"""
from datetime import datetime, timezone
import random
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.database.base import Base
from backend.app.models.alarm import Alarm
from backend.app.models.challenge_attempt import ChallengeAttempt
from backend.app.models.user import User
from backend.app.models.wake_session import WakeSession
from backend.app.services.model_inference_manager import (
    EXPECTED_FEATURE_COUNT,
    EXPECTED_MODEL_FEATURES,
    IncompatibleFeatureSchemaError,
    ModelInferenceManager,
)
from ml.prediction.predictor import DifficultyPredictor
from ml.preprocessing.feature_engineering import extract_features_for_session_context
from ml.training.train_baseline import load_and_validate_dataset


class TestMLRuntimeIntegration(unittest.TestCase):
    """Test suite verifying cross-parity between offline and runtime prediction."""

    @classmethod
    def setUpClass(cls):
        cls.project_root = Path(__file__).resolve().parents[2]
        cls.data_path = cls.project_root / "ml" / "data" / "raw" / "synthetic_challenge_features.csv"
        cls.model_path = cls.project_root / "ml" / "models" / "baseline_difficulty_classifier.joblib"

        cls.runtime_manager = ModelInferenceManager(model_path=cls.model_path)
        cls.offline_predictor = DifficultyPredictor(model_path=cls.model_path)

        # Load feature dataset for parity sampling
        cls.df = load_and_validate_dataset(str(cls.data_path))

    def test_single_sample_exact_parity(self):
        """Verify identical predicted class and probability < 1e-6 on a single observation."""
        row_dict = self.df[EXPECTED_MODEL_FEATURES].iloc[0].to_dict()

        offline_res = self.offline_predictor.predict(row_dict)
        runtime_res = self.runtime_manager.predict(row_dict)

        self.assertEqual(
            offline_res.predicted_difficulty,
            runtime_res.predicted_difficulty,
            "Predicted difficulty mismatch between offline and runtime!",
        )
        self.assertAlmostEqual(
            offline_res.confidence,
            runtime_res.confidence,
            places=6,
            msg="Confidence mismatch between offline and runtime!",
        )
        for cls_name in ["easy", "medium", "hard"]:
            self.assertAlmostEqual(
                offline_res.probabilities[cls_name],
                runtime_res.probabilities[cls_name],
                places=6,
                msg=f"Probability for {cls_name} diverges between offline and runtime!",
            )

    def test_multi_sample_cross_parity_100_observations(self):
        """Verify exact parity across 100 diverse observations from the dataset."""
        sample_rows = self.df[EXPECTED_MODEL_FEATURES].iloc[:100].to_dict(orient="records")

        for idx, row in enumerate(sample_rows):
            offline_res = self.offline_predictor.predict(row)
            runtime_res = self.runtime_manager.predict(row)

            self.assertEqual(
                offline_res.predicted_difficulty,
                runtime_res.predicted_difficulty,
                f"Row {idx} predicted difficulty mismatch!",
            )
            self.assertAlmostEqual(
                offline_res.confidence,
                runtime_res.confidence,
                places=6,
                msg=f"Row {idx} confidence mismatch!",
            )
            for cls_name in ["easy", "medium", "hard"]:
                diff = abs(offline_res.probabilities[cls_name] - runtime_res.probabilities[cls_name])
                self.assertLess(
                    diff,
                    1e-6,
                    f"Row {idx} class {cls_name} probability divergence: {diff}",
                )

    def test_dictionary_key_ordering_invariance(self):
        """Verify that shuffling dictionary keys does NOT alter prediction outputs."""
        original_dict = self.df[EXPECTED_MODEL_FEATURES].iloc[10].to_dict()
        keys = list(original_dict.keys())

        # Create randomized key permutations
        for seed in [42, 99, 123]:
            rng = random.Random(seed)
            shuffled_keys = list(keys)
            rng.shuffle(shuffled_keys)
            shuffled_dict = {k: original_dict[k] for k in shuffled_keys}

            off_orig = self.offline_predictor.predict(original_dict)
            off_shuf = self.offline_predictor.predict(shuffled_dict)
            run_orig = self.runtime_manager.predict(original_dict)
            run_shuf = self.runtime_manager.predict(shuffled_dict)

            self.assertEqual(off_orig.predicted_difficulty, off_shuf.predicted_difficulty)
            self.assertEqual(run_orig.predicted_difficulty, run_shuf.predicted_difficulty)
            self.assertEqual(off_shuf.predicted_difficulty, run_shuf.predicted_difficulty)

            for c in ["easy", "medium", "hard"]:
                self.assertAlmostEqual(off_orig.probabilities[c], off_shuf.probabilities[c], places=6)
                self.assertAlmostEqual(run_orig.probabilities[c], run_shuf.probabilities[c], places=6)

    def test_canonical_schema_rejection_of_incomplete_features(self):
        """Verify that both predictors reject incomplete feature vectors."""
        incomplete_dict = self.df[EXPECTED_MODEL_FEATURES].iloc[0].to_dict()
        incomplete_dict.pop("alarm_scheduled_hour")

        with self.assertRaises(IncompatibleFeatureSchemaError):
            self.offline_predictor.predict(incomplete_dict)

        with self.assertRaises(IncompatibleFeatureSchemaError):
            self.runtime_manager.predict(incomplete_dict)

    def test_batch_prediction_matches_single_sample_predictions(self):
        """Verify that DifficultyPredictor.predict_batch matches repeated predict calls."""
        batch_rows = self.df[EXPECTED_MODEL_FEATURES].iloc[:20].to_dict(orient="records")

        batch_outputs = self.offline_predictor.predict_batch(batch_rows)
        self.assertEqual(len(batch_outputs), len(batch_rows))

        for single_row, batch_res in zip(batch_rows, batch_outputs):
            single_res = self.offline_predictor.predict(single_row)
            self.assertEqual(single_res.predicted_difficulty, batch_res.predicted_difficulty)
            self.assertAlmostEqual(single_res.confidence, batch_res.confidence, places=6)
            for c in ["easy", "medium", "hard"]:
                self.assertAlmostEqual(single_res.probabilities[c], batch_res.probabilities[c], places=6)

    def test_db_feature_extractor_runtime_parity(self):
        """Verify parity on real feature extraction from in-memory SQLite database."""
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(bind=engine)
        db = SessionLocal()

        user = User(username="parity_user", email="parity@example.com")
        db.add(user)
        db.commit()

        alarm = Alarm(user_id=user.id, time="07:30", selected_challenge_type="math")
        db.add(alarm)
        db.commit()

        # Seed 8 historical sessions to cross into Stage 2
        for i in range(1, 9):
            ws = WakeSession(
                user_id=user.id,
                alarm_id=alarm.id,
                scheduled_time=datetime(2026, 1, i, 7, 30, 0, tzinfo=timezone.utc),
                initial_ring_time=datetime(2026, 1, i, 7, 30, 0, tzinfo=timezone.utc),
                status="completed",
                total_snooze_count=1 if i % 2 == 0 else 0,
            )
            db.add(ws)
            db.commit()

            att = ChallengeAttempt(
                wake_session_id=ws.id,
                challenge_type="math",
                difficulty_level="medium",
                prompt_content="5+5",
                attempt_number=1,
                started_at=datetime(2026, 1, i, 7, 32, 0, tzinfo=timezone.utc),
                completed_at=datetime(2026, 1, i, 7, 32, 12, tzinfo=timezone.utc),
                duration_seconds=12.0,
                is_successful=True,
                verification_score=0.9,
            )
            db.add(att)
            db.commit()

        # Active morning session
        active_ws = WakeSession(
            user_id=user.id,
            alarm_id=alarm.id,
            scheduled_time=datetime(2026, 1, 9, 7, 30, 0, tzinfo=timezone.utc),
            initial_ring_time=datetime(2026, 1, 9, 7, 30, 0, tzinfo=timezone.utc),
            status="active",
            total_snooze_count=0,
        )
        db.add(active_ws)
        db.commit()

        # Extract features using canonical feature extraction
        feature_record = extract_features_for_session_context(
            db=db,
            wake_session=active_ws,
            challenge_type="math",
            difficulty_preference="adaptive",
            current_attempt_number=1,
        )

        # Feed to both predictors
        off_res = self.offline_predictor.predict(feature_record)
        run_res = self.runtime_manager.predict(feature_record)

        self.assertEqual(off_res.predicted_difficulty, run_res.predicted_difficulty)
        self.assertAlmostEqual(off_res.confidence, run_res.confidence, places=6)
        for c in ["easy", "medium", "hard"]:
            self.assertAlmostEqual(off_res.probabilities[c], run_res.probabilities[c], places=6)

        db.close()


if __name__ == "__main__":
    unittest.main()
