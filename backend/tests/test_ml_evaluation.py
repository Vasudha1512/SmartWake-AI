"""Unit tests for Phase 3.6.1 — Offline Model Evaluation & Classification Metrics.

Verifies:
1. Split sizes strictly match canonical chronological ratio (210/45/45).
2. Evaluation target is explicitly labeled 'heuristic-derived baseline target'.
3. Input features contain strictly the 30 pre-challenge features (zero post-challenge leakage).
4. Metrics (Accuracy, Macro Precision, Recall, F1, Weighted F1) are mathematically sound.
5. Confusion matrix row sums equal class support counts.
6. Confidence statistics are bounded within [0.0, 1.0].
7. Evaluation report JSON artifact is generated and conforms to schema.
"""
import json
import os
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

from ml.evaluation.evaluate_model import (
    TARGET_SEMANTICS_METADATA,
    evaluate_split_detailed,
    run_offline_evaluation,
)
from ml.training.train_baseline import (
    DIFFICULTY_CLASSES,
    MODEL_INPUT_FEATURES,
    generate_ground_truth_labels,
    load_and_validate_dataset,
    split_chronological,
)


class TestMLEvaluation(unittest.TestCase):
    """Test suite for Phase 3.6.1 offline model evaluation."""

    @classmethod
    def setUpClass(cls):
        cls.project_root = Path(__file__).resolve().parents[2]
        cls.data_path = cls.project_root / "ml" / "data" / "raw" / "synthetic_challenge_features.csv"
        cls.model_path = cls.project_root / "ml" / "models" / "baseline_difficulty_classifier.joblib"
        cls.report_path = cls.project_root / "ml" / "evaluation" / "evaluation_report.json"

    def test_canonical_split_sizes(self):
        """Verify chronological split sizes match 210 train / 45 val / 45 test."""
        df = load_and_validate_dataset(str(self.data_path))
        train_df, val_df, test_df = split_chronological(df)

        self.assertEqual(len(train_df), 210)
        self.assertEqual(len(val_df), 45)
        self.assertEqual(len(test_df), 45)
        self.assertEqual(len(train_df) + len(val_df) + len(test_df), len(df))

    def test_target_semantics_metadata(self):
        """Verify target is explicitly categorized as heuristic-derived baseline target."""
        self.assertEqual(
            TARGET_SEMANTICS_METADATA["target_type"], "heuristic-derived baseline target"
        )
        self.assertIn("heuristic", TARGET_SEMANTICS_METADATA["target_type"])
        self.assertNotIn("objective ground truth", TARGET_SEMANTICS_METADATA["description"].lower())

    def test_zero_post_challenge_features_in_evaluation_inputs(self):
        """CRITICAL: Ensure evaluation inputs strictly comprise 30 pre-challenge features."""
        self.assertEqual(len(MODEL_INPUT_FEATURES), 30)
        forbidden_outcomes = [
            "target_is_successful",
            "target_duration_seconds",
            "target_verification_score",
            "target_attempt_number",
            "is_successful",
            "duration_seconds",
            "verification_score",
            "attempt_number",
            "failure_reason",
            "completed_at",
            "user_selected_difficulty",
            "is_adaptive_preference",
        ]
        for field in forbidden_outcomes:
            self.assertNotIn(
                field,
                MODEL_INPUT_FEATURES,
                f"LEAKAGE: Post-challenge outcome '{field}' found in MODEL_INPUT_FEATURES!",
            )

    def test_evaluation_report_artifact_structure(self):
        """Verify that evaluation_report.json exists and conforms to full schema."""
        self.assertTrue(
            self.report_path.exists(),
            f"Evaluation report not found at {self.report_path}",
        )
        with open(self.report_path, "r", encoding="utf-8") as f:
            report = json.load(f)

        self.assertIn("evaluation_metrics", report)
        self.assertIn("split_sizes", report)
        self.assertIn("target_semantics", report)

        for split in ["train", "val", "test"]:
            self.assertIn(split, report["evaluation_metrics"])
            split_data = report["evaluation_metrics"][split]

            # Overall metrics check
            overall = split_data["overall_metrics"]
            self.assertIn("accuracy", overall)
            self.assertIn("macro_precision", overall)
            self.assertIn("macro_recall", overall)
            self.assertIn("macro_f1", overall)
            self.assertIn("weighted_f1", overall)

            self.assertGreaterEqual(overall["accuracy"], 0.0)
            self.assertLessEqual(overall["accuracy"], 1.0)
            self.assertGreaterEqual(overall["macro_f1"], 0.0)
            self.assertLessEqual(overall["macro_f1"], 1.0)

            # Per-class metrics check
            per_class = split_data["per_class_metrics"]
            for cls_name in DIFFICULTY_CLASSES:
                self.assertIn(cls_name, per_class)
                c_metrics = per_class[cls_name]
                self.assertIn("precision", c_metrics)
                self.assertIn("recall", c_metrics)
                self.assertIn("f1_score", c_metrics)
                self.assertIn("support", c_metrics)

            # Confusion matrix row sums equal support counts
            cm_raw = split_data["confusion_matrix_raw"]
            for cls_name in DIFFICULTY_CLASSES:
                row_sum = sum(cm_raw[cls_name].values())
                self.assertEqual(
                    row_sum,
                    per_class[cls_name]["support"],
                    f"Confusion matrix row sum for {cls_name} ({row_sum}) does not match support ({per_class[cls_name]['support']})",
                )

            # Confidence statistics check
            conf = split_data["confidence_statistics"]
            self.assertGreaterEqual(conf["mean_confidence"], 0.0)
            self.assertLessEqual(conf["mean_confidence"], 1.0)
            self.assertGreaterEqual(conf["min_confidence"], 0.0)
            self.assertLessEqual(conf["max_confidence"], 1.0)

    def test_heuristic_comparison_in_evaluation_report(self):
        """Verify that heuristic_comparison section exists and contains all baselines."""
        with open(self.report_path, "r", encoding="utf-8") as f:
            report = json.load(f)

        self.assertIn(
            "heuristic_comparison",
            report,
            "heuristic_comparison section missing from evaluation_report.json!",
        )
        h_comp = report["heuristic_comparison"]
        self.assertIn("metadata", h_comp)
        self.assertEqual(
            h_comp["metadata"]["evaluation_nature"], "fair_prechallenge_comparison"
        )
        self.assertIn("splits", h_comp)

        expected_strategies = [
            "ml_baseline_model",
            "majority_class",
            "stage_0_task_demand",
            "stage_1_contextual",
        ]
        for split in ["train", "val", "test"]:
            self.assertIn(split, h_comp["splits"])
            split_strategies = h_comp["splits"][split]
            for strat in expected_strategies:
                self.assertIn(strat, split_strategies)
                res = split_strategies[strat]
                self.assertIn("overall_metrics", res)
                self.assertIn("operational_error_profile", res)
                if strat != "ml_baseline_model":
                    self.assertIn("comparative_delta_vs_ml", res)
                    deltas = res["comparative_delta_vs_ml"]
                    self.assertIn("accuracy_delta_ml_minus_heuristic", deltas)
                    self.assertIn("macro_f1_delta_ml_minus_heuristic", deltas)

    def test_fair_heuristics_consume_zero_post_challenge_features(self):
        """CRITICAL: Ensure deterministic heuristics produce predictions without post-challenge columns."""
        from ml.evaluation.heuristic_comparison import (
            predict_majority_class,
            predict_stage_0_task_demand,
            predict_stage_1_contextual,
        )

        df = load_and_validate_dataset(str(self.data_path))
        # Create a DataFrame stripped of all target outcome columns
        forbidden = [
            "target_is_successful",
            "target_duration_seconds",
            "target_verification_score",
            "target_attempt_number",
            "user_selected_difficulty",
            "is_adaptive_preference",
        ]
        df_stripped = df.drop(columns=[c for c in forbidden if c in df.columns])

        # All 3 heuristics must execute cleanly on stripped DataFrame
        pred_maj = predict_majority_class(df_stripped)
        pred_s0 = predict_stage_0_task_demand(df_stripped)
        pred_s1 = predict_stage_1_contextual(df_stripped)

        self.assertEqual(len(pred_maj), len(df))
        self.assertEqual(len(pred_s0), len(df))
        self.assertEqual(len(pred_s1), len(df))

        for pred in [pred_maj, pred_s0, pred_s1]:
            self.assertTrue(set(pred.unique()).issubset(set(DIFFICULTY_CLASSES)))

    def test_heuristic_predictions_are_100_percent_deterministic(self):
        """Verify repeated invocations on identical data produce identical predictions."""
        from ml.evaluation.heuristic_comparison import (
            predict_majority_class,
            predict_stage_0_task_demand,
            predict_stage_1_contextual,
        )

        df = load_and_validate_dataset(str(self.data_path))
        for fn in [predict_majority_class, predict_stage_0_task_demand, predict_stage_1_contextual]:
            p1 = fn(df)
            p2 = fn(df)
            self.assertTrue((p1 == p2).all(), f"Heuristic function {fn.__name__} is non-deterministic!")


if __name__ == "__main__":
    unittest.main()

