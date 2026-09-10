"""Offline Difficulty Predictor for SmartWake AI (Phase 3.6.3).

Provides a lightweight, reproducible interface for offline batch/single-sample
inference, probability inspection, and cross-parity testing against runtime
ModelInferenceManager.

ARCHITECTURAL RULES:
1. Pure consumer: strictly loads the existing baseline model artifact (read-only).
2. Reuses canonical schema: relies on EXPECTED_MODEL_FEATURES from the canonical schema.
3. Zero duplicate preprocessing: delegates scaling and encoding strictly to the fitted
   scikit-learn ColumnTransformer within the serialized joblib artifact.
4. Parity with ModelInferenceManager: guaranteed identical outputs on canonical 30-feature vectors.
"""
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import joblib
import numpy as np
import pandas as pd

from backend.app.schemas.personalization_schemas import (
    VALID_DIFFICULTY_LEVELS,
    DifficultyLevel,
)
from backend.app.services.model_inference_manager import (
    EXPECTED_FEATURE_COUNT,
    EXPECTED_MODEL_FEATURES,
    IncompatibleFeatureSchemaError,
    ModelArtifactError,
    ModelCorruptError,
    ModelNotFoundError,
)
from ml.preprocessing.feature_schema import ChallengeFeatureRecord


@dataclass
class PredictionOutput:
    """Strongly typed output of an offline prediction operation."""

    predicted_difficulty: str
    confidence: float
    probabilities: Dict[str, float]
    feature_snapshot: Dict[str, Any]


class DifficultyPredictor:
    """Offline inference wrapper around the baseline difficulty classifier pipeline.

    Reuses canonical feature schema and fitted pipeline transformations without
    duplicating preprocessing logic.
    """

    def __init__(
        self,
        model_path: Optional[Union[str, Path]] = None,
    ) -> None:
        """Initialize DifficultyPredictor by loading the serialized model artifact."""
        if model_path is None:
            project_root = Path(__file__).resolve().parents[2]
            model_path = project_root / "ml" / "models" / "baseline_difficulty_classifier.joblib"

        self.model_path = Path(model_path)
        if not self.model_path.exists():
            raise ModelNotFoundError(f"Baseline model artifact not found at: {self.model_path}")

        try:
            self._pipeline = joblib.load(self.model_path)
        except Exception as exc:
            raise ModelCorruptError(
                f"Failed to load model pipeline from {self.model_path}: {exc}"
            ) from exc

        if not hasattr(self._pipeline, "predict_proba"):
            raise ModelCorruptError(
                f"Loaded pipeline from {self.model_path} does not implement predict_proba."
            )

        # Cache class names and expected features
        classes = getattr(self._pipeline, "classes_", None)
        if classes is None:
            classifier = getattr(self._pipeline, "named_steps", {}).get("classifier")
            classes = getattr(classifier, "classes_", None)
        if classes is None:
            raise ModelCorruptError("Loaded pipeline does not expose valid 'classes_'.")

        self.classes_: List[str] = [str(c) for c in classes]
        self.expected_features: List[str] = list(EXPECTED_MODEL_FEATURES)

    def extract_canonical_features(
        self, features: Union[ChallengeFeatureRecord, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Extract and validate strictly the 30 canonical model input features."""
        if isinstance(features, ChallengeFeatureRecord):
            raw = features.to_dict(include_targets=False, include_metadata=False)
        elif isinstance(features, dict):
            raw = dict(features)
        else:
            raise IncompatibleFeatureSchemaError(
                f"Expected ChallengeFeatureRecord or dict, received: {type(features).__name__}"
            )

        missing = [f for f in self.expected_features if f not in raw]
        if missing:
            raise IncompatibleFeatureSchemaError(
                f"Features dictionary missing {len(missing)} canonical features: {missing}"
            )

        clean = {f: raw[f] for f in self.expected_features}
        ctype = clean.get("selected_challenge_type")
        if not isinstance(ctype, str) or not ctype.strip():
            raise IncompatibleFeatureSchemaError(
                "selected_challenge_type must be a non-empty string."
            )

        return clean

    def predict(
        self, features: Union[ChallengeFeatureRecord, Dict[str, Any]]
    ) -> PredictionOutput:
        """Execute single-observation prediction with probability inspection."""
        clean_features = self.extract_canonical_features(features)
        df = pd.DataFrame([clean_features], columns=self.expected_features)

        raw_probs = self._pipeline.predict_proba(df)[0]
        prob_dict: Dict[str, float] = {
            cls_name: round(float(prob), 4)
            for cls_name, prob in zip(self.classes_, raw_probs)
        }

        # Ensure all canonical difficulty levels exist
        for diff in VALID_DIFFICULTY_LEVELS:
            if diff not in prob_dict:
                prob_dict[diff] = 0.0

        best_class = max(prob_dict, key=lambda k: prob_dict[k])
        confidence = prob_dict[best_class]

        return PredictionOutput(
            predicted_difficulty=best_class,
            confidence=confidence,
            probabilities=prob_dict,
            feature_snapshot=clean_features,
        )

    def predict_batch(
        self, features_list: List[Union[ChallengeFeatureRecord, Dict[str, Any]]]
    ) -> List[PredictionOutput]:
        """Execute high-throughput batch prediction over a list of observations."""
        if not features_list:
            return []

        clean_rows = [self.extract_canonical_features(f) for f in features_list]
        df = pd.DataFrame(clean_rows, columns=self.expected_features)

        raw_probs_matrix = self._pipeline.predict_proba(df)

        outputs: List[PredictionOutput] = []
        for i, raw_probs in enumerate(raw_probs_matrix):
            prob_dict = {
                cls_name: round(float(prob), 4)
                for cls_name, prob in zip(self.classes_, raw_probs)
            }
            for diff in VALID_DIFFICULTY_LEVELS:
                if diff not in prob_dict:
                    prob_dict[diff] = 0.0

            best_class = max(prob_dict, key=lambda k: prob_dict[k])
            confidence = prob_dict[best_class]

            outputs.append(
                PredictionOutput(
                    predicted_difficulty=best_class,
                    confidence=confidence,
                    probabilities=prob_dict,
                    feature_snapshot=clean_rows[i],
                )
            )

        return outputs
