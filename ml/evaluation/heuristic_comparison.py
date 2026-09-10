"""Fair ML vs. Deterministic Heuristic Comparison for SmartWake AI (Phase 3.6.2).

Benchmarks deterministic heuristic strategies against the baseline ML model
on the canonical Train, Validation, and Test splits.

FAIRNESS GUARANTEES:
1. Both ML and heuristic predictions consume ONLY pre-challenge information
   available at decision time T0.
2. Post-challenge outcomes (target_is_successful, target_duration_seconds,
   target_verification_score, target_attempt_number, failure_reason, completed_at)
   are strictly FORBIDDEN from input to heuristics.
3. Zero telemetry fabrication: missing historical fields default safely without
   inventing artificial telemetry.
4. Evaluation measures agreement with the developmental heuristic-derived baseline
   target, NOT clinical or real-world human wake-up efficacy.
"""
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable, Dict, List, Optional, Union, cast

# Ensure project root is in sys.path
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

from ml.training.train_baseline import (
    DIFFICULTY_CLASSES,
    MODEL_INPUT_FEATURES,
    generate_ground_truth_labels,
    load_and_validate_dataset,
    split_chronological,
)

# Canonical task classifications matching ColdStartRouter
HIGH_COGNITIVE_CHALLENGES = {"math", "memory"}
PHYSICAL_SPEECH_CHALLENGES = {"dance", "tongue_twister", "push_ups"}


# -----------------------------------------------------------------------------
# Fair Deterministic Heuristic Baseline Predictors (T_0 Only)
# -----------------------------------------------------------------------------

def predict_majority_class(df: pd.DataFrame) -> pd.Series:
    """Majority Class Baseline: Predicts 'medium' (the empirical modal class).

    Consumes zero pre-challenge features. Represents static unpersonalized guessing.
    """
    return pd.Series(["medium"] * len(df), index=df.index, name="majority_pred")


def predict_stage_0_task_demand(df: pd.DataFrame) -> pd.Series:
    """Stage 0 Heuristic Baseline: Cognitive vs Physical Task Demand + Snooze Inertia.

    Consumes strictly:
    - selected_challenge_type (cognitive -> 'easy', physical -> 'medium')
    - current_session_snooze_count (>= 2 -> downgrade to 'easy')

    Zero post-challenge outcome features used.
    """
    def _map_row(row: pd.Series) -> str:
        ctype = str(row["selected_challenge_type"]).strip().lower()
        snooze_count = int(row["current_session_snooze_count"])

        if ctype in HIGH_COGNITIVE_CHALLENGES:
            base_diff = "easy"
        else:
            base_diff = "medium"

        if snooze_count >= 2:
            base_diff = "easy"

        return base_diff

    return df.apply(_map_row, axis=1)


def predict_stage_1_contextual(df: pd.DataFrame) -> pd.Series:
    """Stage 1 Contextual Baseline: Pre-Challenge Moving Averages & Inertia.

    Consumes strictly pre-challenge cumulative telemetry:
    - user_avg_completion_time_seconds
    - user_historical_success_rate
    - user_failed_wake_sessions
    - current_session_snooze_count

    Rule logic:
    - If user has past failures (user_failed_wake_sessions > 0) OR sluggish average (> 40.0s) -> 'easy'
    - If 100% past success (hist_rate == 1.0) AND fast (< 15.0s) AND total_sessions > 0 -> 'hard'
    - Otherwise -> 'medium'
    - Snooze inertia floor: if snooze_count >= 3, 'hard' is capped at 'medium'.

    Zero post-challenge outcome features used.
    """
    def _map_row(row: pd.Series) -> str:
        snooze_count = int(row.get("current_session_snooze_count", 0))
        total_sessions = int(row.get("user_total_wake_sessions", 0))
        failed_sessions = int(row.get("user_failed_wake_sessions", 0))
        avg_dur = float(row.get("user_avg_completion_time_seconds", 0.0))
        hist_rate = float(row.get("user_historical_success_rate", 0.0))

        # 1. Struggle / Sluggishness -> 'easy'
        if failed_sessions > 0 or avg_dur > 40.0 or snooze_count >= 2:
            return "easy"

        # 2. Mastery -> 'hard' (if not sluggish and high rate)
        if total_sessions > 0 and hist_rate >= 1.0 and avg_dur < 15.0:
            if snooze_count >= 3:
                return "medium"  # Sleep inertia guardrail floor
            return "hard"

        # 3. Balanced engagement default
        return "medium"

    return df.apply(_map_row, axis=1)


# -----------------------------------------------------------------------------
# Metric & Error Profile Calculation
# -----------------------------------------------------------------------------

def evaluate_predictions(
    y_true: Union[pd.Series, Any],
    y_pred: Union[pd.Series, Any],
    df_features: Union[pd.DataFrame, Any],
    strategy_name: str,
) -> Dict[str, Any]:
    """Compute multi-class metrics and operational error profile for any strategy."""
    acc = float(accuracy_score(y_true, y_pred))
    macro_p = float(precision_score(y_true, y_pred, average="macro", zero_division=0))
    macro_r = float(recall_score(y_true, y_pred, average="macro", zero_division=0))
    macro_f1 = float(f1_score(y_true, y_pred, average="macro", zero_division=0))
    weighted_f1 = float(f1_score(y_true, y_pred, average="weighted", zero_division=0))

    # Per-class metrics
    p_per, r_per, f1_per, sup_per = precision_recall_fscore_support(
        y_true, y_pred, labels=DIFFICULTY_CLASSES, zero_division=0
    )
    per_class: Dict[str, Dict[str, Any]] = {}
    for i, cls_name in enumerate(DIFFICULTY_CLASSES):
        per_class[cls_name] = {
            "precision": round(float(p_per[i]), 4),
            "recall": round(float(r_per[i]), 4),
            "f1_score": round(float(f1_per[i]), 4),
            "support": int(sup_per[i]),
        }

    # Operational error profiles
    # 1. Over-challenging sluggish users: predicting 'hard' when snooze >= 2
    snooze_mask = df_features["current_session_snooze_count"] >= 2
    total_sluggish = int(np.sum(snooze_mask))
    over_challenging_count = int(np.sum((y_pred == "hard") & snooze_mask))
    over_challenging_rate = (
        round(over_challenging_count / total_sluggish, 4) if total_sluggish > 0 else 0.0
    )

    # 2. Under-challenging alert users: predicting 'easy' when user was fast and alert in target
    high_alert_target = y_true == "hard"
    total_alert = int(np.sum(high_alert_target))
    under_challenging_count = int(np.sum((y_pred == "easy") & high_alert_target))
    under_challenging_rate = (
        round(under_challenging_count / total_alert, 4) if total_alert > 0 else 0.0
    )

    return {
        "strategy_name": strategy_name,
        "sample_count": len(y_true),
        "overall_metrics": {
            "accuracy": round(acc, 4),
            "macro_precision": round(macro_p, 4),
            "macro_recall": round(macro_r, 4),
            "macro_f1": round(macro_f1, 4),
            "weighted_f1": round(weighted_f1, 4),
        },
        "per_class_metrics": per_class,
        "operational_error_profile": {
            "sluggish_sessions_count": total_sluggish,
            "over_challenging_count": over_challenging_count,
            "over_challenging_rate": over_challenging_rate,
            "alert_sessions_count": total_alert,
            "under_challenging_count": under_challenging_count,
            "under_challenging_rate": under_challenging_rate,
        },
    }


def run_heuristic_comparison(
    data_path: Optional[str] = None,
    model_path: Optional[str] = None,
    report_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute complete fair comparison between ML model and deterministic heuristics."""
    base_dir = Path(__file__).resolve().parents[2]
    if data_path is None:
        data_path = str(base_dir / "ml" / "data" / "raw" / "synthetic_challenge_features.csv")
    if model_path is None:
        model_path = str(base_dir / "ml" / "models" / "baseline_difficulty_classifier.joblib")
    if report_path is None:
        report_path = str(base_dir / "ml" / "evaluation" / "evaluation_report.json")

    # Load dataset & target
    df = load_and_validate_dataset(data_path)
    df["optimal_difficulty"] = generate_ground_truth_labels(df)
    train_df, val_df, test_df = split_chronological(df)

    # Load ML pipeline
    pipeline = joblib.load(model_path)

    heuristic_strategies: Dict[str, Callable[[pd.DataFrame], pd.Series]] = {
        "majority_class": predict_majority_class,
        "stage_0_task_demand": predict_stage_0_task_demand,
        "stage_1_contextual": predict_stage_1_contextual,
    }

    comparison_results: Dict[str, Any] = {
        "metadata": {
            "evaluation_nature": "fair_prechallenge_comparison",
            "target_type": "heuristic-derived baseline target",
            "target_disclaimer": (
                "Agreement with the heuristic-derived baseline target measures developmental "
                "alignment with designed objective criteria. It does NOT represent clinical "
                "or real-world human wake-up efficacy."
            ),
            "telemetry_constraint": "Strictly T_0 pre-challenge features; zero post-challenge leakage.",
        },
        "splits": {},
    }

    for split_name, s_df in [("train", train_df), ("val", val_df), ("test", test_df)]:
        X = cast(pd.DataFrame, s_df[MODEL_INPUT_FEATURES])
        y_true = cast(pd.Series, s_df["optimal_difficulty"])

        # 1. ML Model Predictions
        ml_preds = pd.Series(pipeline.predict(X), index=s_df.index, name="ml_pred")
        ml_eval = evaluate_predictions(
            y_true=y_true,
            y_pred=ml_preds,
            df_features=s_df,
            strategy_name="ml_baseline_model",
        )

        strategies_eval: Dict[str, Any] = {"ml_baseline_model": ml_eval}

        # 2. Heuristic Predictions
        for strat_key, strat_fn in heuristic_strategies.items():
            h_preds = strat_fn(s_df)
            h_eval = evaluate_predictions(
                y_true=y_true,
                y_pred=h_preds,
                df_features=s_df,
                strategy_name=strat_key,
            )

            # Compute comparative deltas relative to ML model
            delta_acc = round(
                ml_eval["overall_metrics"]["accuracy"]
                - h_eval["overall_metrics"]["accuracy"],
                4,
            )
            delta_f1 = round(
                ml_eval["overall_metrics"]["macro_f1"]
                - h_eval["overall_metrics"]["macro_f1"],
                4,
            )
            h_eval["comparative_delta_vs_ml"] = {
                "accuracy_delta_ml_minus_heuristic": delta_acc,
                "macro_f1_delta_ml_minus_heuristic": delta_f1,
            }
            strategies_eval[strat_key] = h_eval

        comparison_results["splits"][split_name] = strategies_eval

    # Enrich evaluation_report.json if it exists
    if os.path.exists(report_path):
        with open(report_path, "r", encoding="utf-8") as f:
            full_report = json.load(f)
        full_report["heuristic_comparison"] = comparison_results
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(full_report, f, indent=2)

    return comparison_results


if __name__ == "__main__":
    res = run_heuristic_comparison()
    print("=" * 80)
    print("SmartWake AI — Phase 3.6.2 Fair ML vs. Heuristic Comparison Complete")
    print("=" * 80)
    test_splits = res["splits"]["test"]
    print(f"{'Strategy':25s} | {'Accuracy':8s} | {'Macro-F1':8s} | {'Delta-Acc':10s} | {'Delta-F1':10s}")
    print("-" * 80)
    ml_acc = test_splits["ml_baseline_model"]["overall_metrics"]["accuracy"]
    ml_f1 = test_splits["ml_baseline_model"]["overall_metrics"]["macro_f1"]
    print(f"{'ml_baseline_model':25s} | {ml_acc:<8.4f} | {ml_f1:<8.4f} | {'[BASELINE]':10s} | {'[BASELINE]':10s}")
    for strat in ["majority_class", "stage_0_task_demand", "stage_1_contextual"]:
        s_m = test_splits[strat]["overall_metrics"]
        d = test_splits[strat]["comparative_delta_vs_ml"]
        print(
            f"{strat:25s} | {s_m['accuracy']:<8.4f} | {s_m['macro_f1']:<8.4f} | "
            f"{d['accuracy_delta_ml_minus_heuristic']:<+10.4f} | {d['macro_f1_delta_ml_minus_heuristic']:<+10.4f}"
        )
    print("=" * 80)
