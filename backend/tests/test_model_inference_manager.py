"""Unit tests for Phase 3.3.3 — Model Inference Manager.

Verifies:
1. Model loading, lazy loading, and instance caching.
2. Prediction execution, difficulty class, and probability mapping.
3. Class ordering fidelity matching pipeline.classes_.
4. Confidence threshold configuration and reporting.
5. Error handling for missing, corrupt, and schema-mismatched artifacts.
6. Exclusion of user preference and target leakage fields from model inputs.
7. Preservation of selected_challenge_type.
"""
import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from backend.app.schemas.personalization_schemas import VALID_DIFFICULTY_LEVELS
from backend.app.services.model_inference_manager import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    EXPECTED_FEATURE_COUNT,
    EXPECTED_MODEL_FEATURES,
    IncompatibleFeatureSchemaError,
    ModelCorruptError,
    ModelInferenceManager,
    ModelInferenceResult,
    ModelMetadataError,
    ModelNotFoundError,
)
from ml.preprocessing.feature_schema import ChallengeFeatureRecord


def make_valid_feature_dict(challenge_type: str = "math") -> dict:
    """Helper to build a valid dictionary with all 30 model features."""
    return {
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
        "selected_challenge_type": challenge_type,
    }


class TestModelInferenceManager(unittest.TestCase):
    """Test suite for ModelInferenceManager runtime inference."""

    @classmethod
    def setUpClass(cls):
        cls.manager = ModelInferenceManager()

    def test_model_artifact_loads_successfully(self):
        """Verify baseline model pipeline loads and contains predict_proba."""
        pipeline = self.manager.get_model()
        self.assertIsNotNone(pipeline)
        self.assertTrue(hasattr(pipeline, "predict_proba"))
        self.assertTrue(self.manager.is_loaded)

    def test_lazy_loading_and_caching(self):
        """Verify model is not loaded until requested and is cached across invocations."""
        mgr = ModelInferenceManager()
        self.assertFalse(mgr.is_loaded)

        m1 = mgr.get_model()
        self.assertTrue(mgr.is_loaded)

        m2 = mgr.get_model()
        self.assertIs(m1, m2)  # Exact same in-memory object

    def test_valid_dict_prediction(self):
        """Verify prediction on a valid 30-feature dictionary."""
        feats = make_valid_feature_dict(challenge_type="math")
        res = self.manager.predict(feats)

        self.assertIsInstance(res, ModelInferenceResult)
        self.assertIn(res.predicted_difficulty, VALID_DIFFICULTY_LEVELS)
        self.assertGreaterEqual(res.confidence, 0.0)
        self.assertLessEqual(res.confidence, 1.0)
        self.assertEqual(res.model_name, "baseline_difficulty_classifier")

    def test_valid_challenge_feature_record_prediction(self):
        """Verify prediction using a strongly typed ChallengeFeatureRecord."""
        record = ChallengeFeatureRecord(
            user_id=1,
            wake_session_id=10,
            challenge_attempt_id=None,
            alarm_id=5,
            timestamp="2026-09-09T23:00:00Z",
            user_total_wake_sessions=15,
            user_successful_wake_sessions=14,
            user_failed_wake_sessions=1,
            user_historical_success_rate=0.933,
            user_avg_completion_time_seconds=14.0,
            user_avg_attempts_per_session=1.0,
            user_avg_snooze_count=0.2,
            user_total_snooze_count=3,
            user_recent_snooze_count=0,
            user_recent_challenge_success_rate=1.0,
            challenge_type_total_attempts=8,
            challenge_type_successful_attempts=8,
            challenge_type_success_rate=1.0,
            challenge_type_avg_completion_time=13.5,
            challenge_type_avg_attempts_per_session=1.0,
            challenge_type_easy_attempts=2,
            challenge_type_easy_success_rate=1.0,
            challenge_type_medium_attempts=5,
            challenge_type_medium_success_rate=1.0,
            challenge_type_hard_attempts=1,
            challenge_type_hard_success_rate=1.0,
            current_session_snooze_count=0,
            current_session_snooze_duration_minutes=0,
            current_session_wake_delay_seconds=15.0,
            alarm_scheduled_hour=7,
            alarm_scheduled_minute=0,
            alarm_day_of_week=3,
            alarm_is_weekend=0,
            historical_snooze_avg_around_alarm_time=0.3,
            selected_challenge_type="dance",
            # Additional non-model fields:
            user_selected_difficulty="adaptive",
            is_adaptive_preference=1,
            target_is_successful=1,
            target_duration_seconds=14.0,
        )

        res = self.manager.predict(record)
        self.assertIn(res.predicted_difficulty, VALID_DIFFICULTY_LEVELS)
        self.assertEqual(res.feature_snapshot["selected_challenge_type"], "dance")

    def test_probabilities_sum_and_structure(self):
        """Verify probabilities dict contains all classes and sums approximately to 1.0."""
        feats = make_valid_feature_dict(challenge_type="push_ups")
        res = self.manager.predict(feats)

        self.assertEqual(set(res.probabilities.keys()), VALID_DIFFICULTY_LEVELS)
        prob_sum = sum(res.probabilities.values())
        self.assertAlmostEqual(prob_sum, 1.0, places=2)

    def test_confidence_equals_max_probability(self):
        """Verify confidence strictly equals the maximum class probability."""
        feats = make_valid_feature_dict(challenge_type="tongue_twister")
        res = self.manager.predict(feats)

        max_prob = max(res.probabilities.values())
        self.assertEqual(res.confidence, max_prob)

        best_class = max(res.probabilities, key=lambda k: res.probabilities[k])
        self.assertEqual(res.predicted_difficulty, best_class)

    def test_actual_model_class_ordering_respected(self):
        """Verify probabilities faithfully map to pipeline.classes_."""
        pipeline = self.manager.get_model()
        classes = pipeline.classes_

        feats = make_valid_feature_dict(challenge_type="memory")
        res = self.manager.predict(feats)

        df = pd.DataFrame([res.feature_snapshot], columns=EXPECTED_MODEL_FEATURES)
        raw_probs = pipeline.predict_proba(df)[0]

        for cls_name, raw_p in zip(classes, raw_probs):
            self.assertAlmostEqual(res.probabilities[cls_name], round(raw_p, 4), places=4)

    def test_confidence_threshold_configuration(self):
        """Verify confidence_threshold defaults to 0.60 and correctly sets meets_confidence_threshold."""
        self.assertEqual(self.manager.confidence_threshold, DEFAULT_CONFIDENCE_THRESHOLD)

        feats = make_valid_feature_dict(challenge_type="math")

        # Threshold set low: meets_confidence_threshold must be True
        low_mgr = ModelInferenceManager(confidence_threshold=0.01)
        res_low = low_mgr.predict(feats)
        self.assertTrue(res_low.meets_confidence_threshold)
        self.assertEqual(res_low.confidence_threshold, 0.01)

        # Threshold set impossibly high: meets_confidence_threshold must be False
        high_mgr = ModelInferenceManager(confidence_threshold=0.999)
        res_high = high_mgr.predict(feats)
        self.assertFalse(res_high.meets_confidence_threshold)
        self.assertEqual(res_high.confidence_threshold, 0.999)
        # Even if threshold not met, predicted_difficulty is still returned
        self.assertIn(res_high.predicted_difficulty, VALID_DIFFICULTY_LEVELS)

    def test_missing_model_artifact_raises_error(self):
        """Verify missing model file raises ModelNotFoundError."""
        bad_mgr = ModelInferenceManager(model_path="nonexistent_model_file.joblib")
        with self.assertRaises(ModelNotFoundError) as cm:
            bad_mgr.get_model()
        self.assertIn("not found", str(cm.exception))

    def test_corrupt_model_artifact_raises_error(self):
        """Verify unreadable/corrupt model file raises ModelCorruptError."""
        with tempfile.NamedTemporaryFile(suffix=".joblib", delete=False) as tf:
            tf.write(b"this is not a valid joblib file serialized data")
            corrupt_path = tf.name

        try:
            bad_mgr = ModelInferenceManager(model_path=corrupt_path)
            with self.assertRaises(ModelCorruptError) as cm:
                bad_mgr.get_model()
            self.assertIn("Failed to load/deserialize", str(cm.exception))
        finally:
            Path(corrupt_path).unlink(missing_ok=True)

    def test_missing_metadata_artifact_raises_error(self):
        """Verify missing metadata file raises ModelMetadataError."""
        bad_mgr = ModelInferenceManager(metadata_path="nonexistent_meta.json")
        with self.assertRaises(ModelMetadataError) as cm:
            bad_mgr.load_metadata()
        self.assertIn("not found", str(cm.exception))

    def test_corrupt_metadata_artifact_raises_error(self):
        """Verify invalid metadata JSON raises ModelMetadataError."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            tf.write(b"{invalid_json: true,}")
            corrupt_path = tf.name

        try:
            bad_mgr = ModelInferenceManager(metadata_path=corrupt_path)
            with self.assertRaises(ModelMetadataError) as cm:
                bad_mgr.load_metadata()
            self.assertIn("Failed to parse model metadata", str(cm.exception))
        finally:
            Path(corrupt_path).unlink(missing_ok=True)

    def test_incompatible_feature_schema_missing_fields(self):
        """Verify missing model features raise IncompatibleFeatureSchemaError."""
        feats = make_valid_feature_dict()
        del feats["current_session_snooze_count"]  # Remove 1 required feature

        with self.assertRaises(IncompatibleFeatureSchemaError) as cm:
            self.manager.predict(feats)
        self.assertIn("missing 1 required model inputs", str(cm.exception))

    def test_strictly_30_features_in_snapshot_and_excluded_fields(self):
        """Verify snapshot contains strictly the 30 model features and excludes non-model fields."""
        feats = make_valid_feature_dict()
        # Add extraneous and forbidden leakage fields
        feats["user_selected_difficulty"] = "adaptive"
        feats["is_adaptive_preference"] = 1
        feats["target_is_successful"] = 1
        feats["target_duration_seconds"] = 18.0
        feats["extra_unrelated_field"] = "ignored"

        res = self.manager.predict(feats)
        self.assertEqual(len(res.feature_snapshot), EXPECTED_FEATURE_COUNT)

        # Excluded fields must NOT be in feature_snapshot
        self.assertNotIn("user_selected_difficulty", res.feature_snapshot)
        self.assertNotIn("is_adaptive_preference", res.feature_snapshot)
        self.assertNotIn("target_is_successful", res.feature_snapshot)
        self.assertNotIn("target_duration_seconds", res.feature_snapshot)
        self.assertNotIn("extra_unrelated_field", res.feature_snapshot)

    def test_selected_challenge_type_preserved_across_all_types(self):
        """Verify selected_challenge_type is fed as input and preserved across all 5 canonical types."""
        canonical_types = ["dance", "math", "memory", "tongue_twister", "push_ups"]
        for ctype in canonical_types:
            feats = make_valid_feature_dict(challenge_type=ctype)
            res = self.manager.predict(feats)
            self.assertEqual(res.feature_snapshot["selected_challenge_type"], ctype)
            self.assertIn(res.predicted_difficulty, VALID_DIFFICULTY_LEVELS)


if __name__ == "__main__":
    unittest.main()
