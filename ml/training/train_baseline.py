"""Baseline ML Model Training Pipeline for SmartWake AI (Phase 3.2).

CRITICAL POINT-IN-TIME & TARGET LEAKAGE SAFEGUARDS:
1. Ground truth target 'optimal_difficulty' is derived solely from objective performance
   evidence (feasibility, duration, verification score, attempt number, snooze inertia).
   It does NOT read or copy 'user_selected_difficulty'.
2. Model inputs strictly comprise 30 pre-challenge features:
   - 29 numerical features (StandardScaler)
   - 1 categorical feature: selected_challenge_type (OneHotEncoder)
3. 'user_selected_difficulty' and 'is_adaptive_preference' are treated as user decision
   context for Phase 3.3 and are EXCLUDED from model input features.
4. Current row post-challenge outcomes (is_successful, duration_seconds, verification_score,
   attempt_number, failure_reason, completed_at) are strictly EXCLUDED from model inputs.
5. Chronological splitting (70% train / 15% val / 15% test) guarantees zero look-ahead leakage.
"""
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

# Ensure project root is in sys.path when executed directly
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from ml.preprocessing.feature_schema import (
    ALARM_CONTEXT_FEATURES,
    ALL_DATASET_COLUMNS,
    CHALLENGE_HISTORY_FEATURES,
    FEATURE_COLUMNS,
    METADATA_COLUMNS,
    SNOOZE_HISTORY_FEATURES,
    TARGET_COLUMNS,
    USER_HISTORY_FEATURES,
)

# 29 Numerical pre-challenge features
MODEL_NUMERICAL_FEATURES: List[str] = (
    USER_HISTORY_FEATURES
    + CHALLENGE_HISTORY_FEATURES
    + SNOOZE_HISTORY_FEATURES
    + ALARM_CONTEXT_FEATURES
)

# 1 Categorical pre-challenge feature
MODEL_CATEGORICAL_FEATURES: List[str] = ["selected_challenge_type"]

# Total Model Input Features: 30 features
MODEL_INPUT_FEATURES: List[str] = MODEL_NUMERICAL_FEATURES + MODEL_CATEGORICAL_FEATURES

# Excluded from model input features to prevent leakage or circularity
EXCLUDED_FROM_INPUTS: List[str] = (
    METADATA_COLUMNS
    + TARGET_COLUMNS
    + ["user_selected_difficulty", "is_adaptive_preference"]
)

DIFFICULTY_CLASSES: List[str] = ["easy", "medium", "hard"]


def load_and_validate_dataset(csv_path: str) -> pd.DataFrame:
    """Load feature dataset CSV and validate required column schema.

    Args:
        csv_path: Path to dataset CSV.

    Returns:
        Validated pandas DataFrame with parsed timestamps and sorted index.
    """
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Feature dataset not found at: {csv_path}")

    df = pd.read_csv(csv_path)

    # Validate all canonical Phase 3.0 columns exist
    missing_cols = [c for c in ALL_DATASET_COLUMNS if c not in df.columns]
    if missing_cols:
        raise ValueError(f"Dataset missing required canonical columns: {missing_cols}")

    # Check for NaN / null values in input features
    null_counts = df[MODEL_INPUT_FEATURES].isnull().sum()
    if null_counts.any():
        cols_with_nulls = null_counts[null_counts > 0].to_dict()
        raise ValueError(f"Dataset contains null values in input features: {cols_with_nulls}")

    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values(by=["user_id", "timestamp"]).reset_index(drop=True)
    return df


def generate_ground_truth_labels(df: pd.DataFrame) -> pd.Series:
    """Derive ground-truth optimal difficulty strictly from performance evidence.

    CRITICAL LEAKAGE PREVENTION RULE:
    Does NOT read, copy, or correlate with 'user_selected_difficulty' or 'is_adaptive_preference'.
    Changing user_selected_difficulty alone produces 0.0% change in this target.

    Decision thresholds grounded in Phase 3.1 strategy:
    - S=0 (failure), or duration > 45s, or retries > 1, or score < 0.65, or heavy snooze inertia -> 'easy'
    - S=1, score >= 0.80, duration < 14s, snooze <= 1, historical rate >= 0.5 -> 'hard'
    - Balanced waking engagement -> 'medium'
    """
    def _map_row(row: pd.Series) -> str:
        succ = int(row["target_is_successful"])
        dur = float(row["target_duration_seconds"])
        score = float(row["target_verification_score"])
        att = int(row["target_attempt_number"])
        snooze_count = int(row["current_session_snooze_count"])
        hist_rate = float(row["user_historical_success_rate"])
        total_sessions = int(row["user_total_wake_sessions"])

        # 1. Struggle / Failure / Severe Sleep Inertia -> 'easy'
        if succ == 0 or dur > 45.0 or att > 1 or score < 0.65 or (snooze_count >= 2 and dur > 25.0):
            return "easy"

        # 2. Mastery / Rapid completion / High accuracy / Sharp alertness -> 'hard'
        if succ == 1 and score >= 0.80 and dur < 14.0 and snooze_count <= 1 and (hist_rate >= 0.5 or total_sessions == 0):
            return "hard"

        # 3. Standard / Balanced engagement zone -> 'medium'
        return "medium"

    labels = df.apply(_map_row, axis=1)
    labels.name = "optimal_difficulty"
    return labels


def split_chronological(
    df: pd.DataFrame,
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Perform user-stratified chronological split without temporal look-ahead.

    For each user, sessions are partitioned chronologically:
    - Earliest train_ratio (default 70%) -> Training set
    - Next val_ratio (default 15%) -> Validation set
    - Final test_ratio (default 15%) -> Test set

    Returns:
        (train_df, val_df, test_df)
    """
    train_indices: List[int] = []
    val_indices: List[int] = []
    test_indices: List[int] = []

    for user_id, group in df.groupby("user_id"):
        indices = group.index.tolist()
        n = len(indices)
        n_train = int(round(n * train_ratio))
        # Distribute 15% / 15% evenly across users
        if user_id % 2 == 0:
            n_val = int(np.ceil(n * val_ratio))
        else:
            n_val = int(np.floor(n * val_ratio))
        val_end = n_train + n_val

        train_indices.extend(indices[:n_train])
        val_indices.extend(indices[n_train:val_end])
        test_indices.extend(indices[val_end:])

    train_df = df.loc[train_indices].reset_index(drop=True)
    val_df = df.loc[val_indices].reset_index(drop=True)
    test_df = df.loc[test_indices].reset_index(drop=True)

    return train_df, val_df, test_df


def build_baseline_pipeline(
    numerical_cols: List[str] = MODEL_NUMERICAL_FEATURES,
    categorical_cols: List[str] = MODEL_CATEGORICAL_FEATURES,
    random_state: int = 42,
) -> Pipeline:
    """Construct an end-to-end scikit-learn Pipeline with preprocessing and classifier.

    - StandardScaler for continuous telemetry and historical averages.
    - OneHotEncoder for selected_challenge_type.
    - Multinomial Logistic Regression with L2 regularization (C=1.0).
    """
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), numerical_cols),
            ("cat", OneHotEncoder(handle_unknown="ignore"), categorical_cols),
        ]
    )

    pipeline = Pipeline([
        ("preprocessor", preprocessor),
        (
            "classifier",
            LogisticRegression(
                solver="lbfgs",
                C=1.0,
                max_iter=1000,
                random_state=random_state,
            ),
        ),
    ])
    return pipeline


def evaluate_split(
    pipeline: Pipeline,
    X: pd.DataFrame,
    y: pd.Series,
    split_name: str,
) -> Dict[str, Any]:
    """Compute comprehensive multi-class evaluation metrics on a dataset split."""
    preds = pipeline.predict(X)
    probs = pipeline.predict_proba(X)

    acc = float(accuracy_score(y, preds))
    macro_p = float(precision_score(y, preds, average="macro", zero_division=0))
    macro_r = float(recall_score(y, preds, average="macro", zero_division=0))
    macro_f1 = float(f1_score(y, preds, average="macro", zero_division=0))

    cm = confusion_matrix(y, preds, labels=DIFFICULTY_CLASSES)
    cm_dict = {
        true_cls: {
            pred_cls: int(cm[i][j])
            for j, pred_cls in enumerate(DIFFICULTY_CLASSES)
        }
        for i, true_cls in enumerate(DIFFICULTY_CLASSES)
    }

    class_dist = {str(k): int(v) for k, v in y.value_counts().to_dict().items()}

    return {
        "split": split_name,
        "sample_count": len(y),
        "accuracy": round(acc, 4),
        "macro_precision": round(macro_p, 4),
        "macro_recall": round(macro_r, 4),
        "macro_f1": round(macro_f1, 4),
        "confusion_matrix": cm_dict,
        "class_distribution": class_dist,
    }


def train_and_save_baseline_model(
    data_path: Optional[str] = None,
    model_output_path: Optional[str] = None,
    metadata_output_path: Optional[str] = None,
    random_state: int = 42,
) -> Dict[str, Any]:
    """Execute complete Phase 3.2 baseline model training, evaluation, and serialization.

    Returns:
        Dictionary with complete training report and evaluation metrics.
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if data_path is None:
        data_path = os.path.join(base_dir, "data", "raw", "synthetic_challenge_features.csv")
    if model_output_path is None:
        model_output_path = os.path.join(base_dir, "models", "baseline_difficulty_classifier.joblib")
    if metadata_output_path is None:
        metadata_output_path = os.path.join(base_dir, "models", "baseline_metadata.json")

    os.makedirs(os.path.dirname(model_output_path), exist_ok=True)

    # 1. Load and validate
    df = load_and_validate_dataset(data_path)

    # 2. Derive ground truth labels
    df["optimal_difficulty"] = generate_ground_truth_labels(df)

    # 3. Chronological split
    train_df, val_df, test_df = split_chronological(df)

    X_train = train_df[MODEL_INPUT_FEATURES]
    y_train = train_df["optimal_difficulty"]

    X_val = val_df[MODEL_INPUT_FEATURES]
    y_val = val_df["optimal_difficulty"]

    X_test = test_df[MODEL_INPUT_FEATURES]
    y_test = test_df["optimal_difficulty"]

    # 4. Build and train pipeline
    pipeline = build_baseline_pipeline(
        numerical_cols=MODEL_NUMERICAL_FEATURES,
        categorical_cols=MODEL_CATEGORICAL_FEATURES,
        random_state=random_state,
    )
    pipeline.fit(X_train, y_train)

    # 5. Evaluate on all three splits
    metrics_train = evaluate_split(pipeline, X_train, y_train, "train")
    metrics_val = evaluate_split(pipeline, X_val, y_val, "val")
    metrics_test = evaluate_split(pipeline, X_test, y_test, "test")

    # 6. Save model artifact
    joblib.dump(pipeline, model_output_path)

    # 7. Save metadata and metrics
    metadata = {
        "model_name": "baseline_difficulty_classifier",
        "model_type": "LogisticRegression",
        "random_state": random_state,
        "input_features_count": len(MODEL_INPUT_FEATURES),
        "input_features": MODEL_INPUT_FEATURES,
        "numerical_features": MODEL_NUMERICAL_FEATURES,
        "categorical_features": MODEL_CATEGORICAL_FEATURES,
        "target_classes": DIFFICULTY_CLASSES,
        "split_sizes": {
            "train": len(train_df),
            "val": len(val_df),
            "test": len(test_df),
        },
        "metrics": {
            "train": metrics_train,
            "val": metrics_val,
            "test": metrics_test,
        },
        "model_artifact_path": model_output_path,
    }

    with open(metadata_output_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    return metadata


if __name__ == "__main__":
    results = train_and_save_baseline_model()
    print("Baseline ML Model Training Complete!")
    print(f"Artifact saved: {results['model_artifact_path']}")
    print(f"Train Accuracy: {results['metrics']['train']['accuracy']}, Macro F1: {results['metrics']['train']['macro_f1']}")
    print(f"Val Accuracy: {results['metrics']['val']['accuracy']}, Macro F1: {results['metrics']['val']['macro_f1']}")
    print(f"Test Accuracy: {results['metrics']['test']['accuracy']}, Macro F1: {results['metrics']['test']['macro_f1']}")
