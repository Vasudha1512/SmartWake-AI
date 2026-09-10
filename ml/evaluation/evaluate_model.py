"""Offline Model Evaluation Pipeline for SmartWake AI (Phase 3.6.1).

Rigorously evaluates the existing baseline ML model artifact on the canonical
Train, Validation, and Test chronological splits.

CONCEPTUAL GROUNDING:
- The evaluation target 'optimal_difficulty' is a heuristic-derived baseline target
  constructed from post-challenge performance thresholds.
- It is NOT an objectively discovered or clinical human ground truth.
- Model inputs strictly comprise the 30 pre-challenge features (zero post-challenge leakage).
- All metrics are dynamically computed without hard-coding historical values.
"""
import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

# Ensure project root is in sys.path when executed directly
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
    precision_score,
    recall_score,
)

from ml.preprocessing.feature_schema import (
    ALARM_CONTEXT_FEATURES,
    CHALLENGE_HISTORY_FEATURES,
    SNOOZE_HISTORY_FEATURES,
    USER_HISTORY_FEATURES,
)
from ml.training.train_baseline import (
    DIFFICULTY_CLASSES,
    MODEL_INPUT_FEATURES,
    generate_ground_truth_labels,
    load_and_validate_dataset,
    split_chronological,
)

TARGET_SEMANTICS_METADATA = {
    "target_name": "optimal_difficulty",
    "target_type": "heuristic-derived baseline target",
    "description": (
        "Deterministic benchmark derived from post-challenge execution outcomes "
        "(feasibility, duration, score, attempt sequence, snooze count). "
        "Intended solely as a developmental training and evaluation benchmark; "
        "does NOT represent objectively discovered clinical human ground truth."
    ),
    "target_classes": DIFFICULTY_CLASSES,
}


def evaluate_split_detailed(
    pipeline: Any,
    X: pd.DataFrame,
    y: pd.Series,
    split_name: str,
) -> Dict[str, Any]:
    """Compute detailed multi-class classification and confidence metrics for a split.

    Args:
        pipeline: Fitted scikit-learn Pipeline.
        X: Pre-challenge feature DataFrame (strictly 30 input features).
        y: Heuristic-derived baseline target labels.
        split_name: Name of the split ('train', 'val', 'test').

    Returns:
        Structured dictionary of multi-class metrics, per-class metrics, confusion
        matrices, and confidence statistics.
    """
    preds = pipeline.predict(X)
    probs = pipeline.predict_proba(X)

    # Validate classes alignment
    classes = getattr(pipeline, "classes_", None)
    if classes is None:
        classifier = getattr(pipeline, "named_steps", {}).get("classifier")
        classes = getattr(classifier, "classes_", None)

    # 1. Overall Metrics
    acc = float(accuracy_score(y, preds))
    macro_p = float(precision_score(y, preds, average="macro", zero_division=0))
    macro_r = float(recall_score(y, preds, average="macro", zero_division=0))
    macro_f1 = float(f1_score(y, preds, average="macro", zero_division=0))
    weighted_f1 = float(f1_score(y, preds, average="weighted", zero_division=0))

    # 2. Per-Class Metrics
    p_per, r_per, f1_per, sup_per = precision_recall_fscore_support(
        y, preds, labels=DIFFICULTY_CLASSES, zero_division=0
    )
    per_class_metrics: Dict[str, Dict[str, Any]] = {}
    for i, cls_name in enumerate(DIFFICULTY_CLASSES):
        per_class_metrics[cls_name] = {
            "precision": round(float(p_per[i]), 4),
            "recall": round(float(r_per[i]), 4),
            "f1_score": round(float(f1_per[i]), 4),
            "support": int(sup_per[i]),
        }

    # 3. Confusion Matrix: Raw and Normalized
    cm_raw = confusion_matrix(y, preds, labels=DIFFICULTY_CLASSES)
    cm_norm = confusion_matrix(y, preds, labels=DIFFICULTY_CLASSES, normalize="true")

    raw_cm_dict: Dict[str, Dict[str, int]] = {}
    norm_cm_dict: Dict[str, Dict[str, float]] = {}
    for i, true_cls in enumerate(DIFFICULTY_CLASSES):
        raw_cm_dict[true_cls] = {
            pred_cls: int(cm_raw[i][j]) for j, pred_cls in enumerate(DIFFICULTY_CLASSES)
        }
        norm_cm_dict[true_cls] = {
            pred_cls: round(float(cm_norm[i][j]), 4)
            for j, pred_cls in enumerate(DIFFICULTY_CLASSES)
        }

    # 4. Confidence Analysis
    confidences = np.max(probs, axis=1)
    is_correct = (preds == y).to_numpy()

    conf_mean = float(np.mean(confidences))
    conf_min = float(np.min(confidences))
    conf_max = float(np.max(confidences))
    conf_correct_mean = (
        float(np.mean(confidences[is_correct])) if np.any(is_correct) else 0.0
    )
    conf_incorrect_mean = (
        float(np.mean(confidences[~is_correct])) if np.any(~is_correct) else 0.0
    )

    conf_by_pred_class: Dict[str, float] = {}
    for cls_name in DIFFICULTY_CLASSES:
        mask = preds == cls_name
        if np.any(mask):
            conf_by_pred_class[cls_name] = round(float(np.mean(confidences[mask])), 4)
        else:
            conf_by_pred_class[cls_name] = 0.0

    class_dist = {str(k): int(v) for k, v in y.value_counts().to_dict().items()}

    return {
        "split": split_name,
        "sample_count": len(y),
        "overall_metrics": {
            "accuracy": round(acc, 4),
            "macro_precision": round(macro_p, 4),
            "macro_recall": round(macro_r, 4),
            "macro_f1": round(macro_f1, 4),
            "weighted_f1": round(weighted_f1, 4),
        },
        "per_class_metrics": per_class_metrics,
        "confusion_matrix_raw": raw_cm_dict,
        "confusion_matrix_normalized": norm_cm_dict,
        "confidence_statistics": {
            "mean_confidence": round(conf_mean, 4),
            "min_confidence": round(conf_min, 4),
            "max_confidence": round(conf_max, 4),
            "mean_confidence_correct": round(conf_correct_mean, 4),
            "mean_confidence_incorrect": round(conf_incorrect_mean, 4),
            "confidence_by_predicted_class": conf_by_pred_class,
        },
        "target_class_distribution": class_dist,
    }


def run_offline_evaluation(
    data_path: Optional[str] = None,
    model_path: Optional[str] = None,
    output_report_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute complete offline model evaluation and write JSON report.

    Args:
        data_path: Path to feature dataset CSV.
        model_path: Path to serialized baseline model joblib.
        output_report_path: Path to output JSON evaluation report.

    Returns:
        Structured evaluation report dictionary.
    """
    base_dir = Path(__file__).resolve().parents[2]
    if data_path is None:
        data_path = str(base_dir / "ml" / "data" / "raw" / "synthetic_challenge_features.csv")
    if model_path is None:
        model_path = str(base_dir / "ml" / "models" / "baseline_difficulty_classifier.joblib")
    if output_report_path is None:
        output_report_path = str(base_dir / "ml" / "evaluation" / "evaluation_report.json")

    # 1. Load and validate feature dataset
    df = load_and_validate_dataset(data_path)

    # 2. Derive heuristic baseline target
    df["optimal_difficulty"] = generate_ground_truth_labels(df)

    # 3. Canonical chronological split (70% train / 15% val / 15% test)
    train_df, val_df, test_df = split_chronological(df)

    # 4. Load serialized model pipeline (strictly read-only)
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model artifact not found at: {model_path}")
    pipeline = joblib.load(model_path)

    # 5. Evaluate on all three splits
    X_train = train_df[MODEL_INPUT_FEATURES]
    y_train = train_df["optimal_difficulty"]

    X_val = val_df[MODEL_INPUT_FEATURES]
    y_val = val_df["optimal_difficulty"]

    X_test = test_df[MODEL_INPUT_FEATURES]
    y_test = test_df["optimal_difficulty"]

    train_eval = evaluate_split_detailed(pipeline, X_train, y_train, "train")
    val_eval = evaluate_split_detailed(pipeline, X_val, y_val, "val")
    test_eval = evaluate_split_detailed(pipeline, X_test, y_test, "test")

    report: Dict[str, Any] = {
        "phase": "Phase 3.6.1 — Offline Model Evaluation & Metrics",
        "model_artifact": model_path,
        "dataset_source": data_path,
        "input_features_count": len(MODEL_INPUT_FEATURES),
        "input_features": MODEL_INPUT_FEATURES,
        "target_semantics": TARGET_SEMANTICS_METADATA,
        "split_sizes": {
            "train": len(train_df),
            "val": len(val_df),
            "test": len(test_df),
            "total": len(df),
        },
        "evaluation_metrics": {
            "train": train_eval,
            "val": val_eval,
            "test": test_eval,
        },
    }

    # Write evaluation report
    os.makedirs(os.path.dirname(output_report_path), exist_ok=True)
    with open(output_report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    return report


if __name__ == "__main__":
    rep = run_offline_evaluation()
    print("=" * 70)
    print("SmartWake AI — Phase 3.6.1 Offline Model Evaluation Complete")
    print("=" * 70)
    for split in ["train", "val", "test"]:
        m = rep["evaluation_metrics"][split]["overall_metrics"]
        print(
            f"[{split.upper():5s}] Acc: {m['accuracy']:.4f} | "
            f"Macro-P: {m['macro_precision']:.4f} | "
            f"Macro-R: {m['macro_recall']:.4f} | "
            f"Macro-F1: {m['macro_f1']:.4f} | "
            f"Weighted-F1: {m['weighted_f1']:.4f}"
        )
    print("=" * 70)
    print(f"Report successfully saved to: ml/evaluation/evaluation_report.json")
