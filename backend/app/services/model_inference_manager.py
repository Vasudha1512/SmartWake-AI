"""Runtime Model Inference Manager for SmartWake AI (Phase 3.3).

Safely manages lazy loading, schema validation, feature vector conversion,
and probability prediction for the Phase 3.2 baseline difficulty classifier.

ARCHITECTURAL RULES:
1. Pure runtime inference: never retrains, rewrites, or modifies model artifacts.
2. Read-only caching: loads the serialized pipeline once into memory.
3. Strict 30-feature boundary:
   - 29 numerical features (StandardScaler)
   - 1 categorical feature: selected_challenge_type (OneHotEncoder)
   - user_selected_difficulty, is_adaptive_preference, and post-challenge
     outcome fields are strictly EXCLUDED from model inputs.
4. Uses the model pipeline's actual classes_ order to map probabilities.
5. Emits typed exceptions for missing, unreadable, or invalid artifacts.
6. Does not write to smartwake.db or modify application code.
"""
from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

import joblib
import pandas as pd

from backend.app.schemas.personalization_schemas import (
    VALID_DIFFICULTY_LEVELS,
    DifficultyLevel,
)
from ml.preprocessing.feature_schema import (
    ALARM_CONTEXT_FEATURES,
    CHALLENGE_HISTORY_FEATURES,
    ChallengeFeatureRecord,
    SNOOZE_HISTORY_FEATURES,
    USER_HISTORY_FEATURES,
)

# Canonical 30 model input features (29 numerical + 1 categorical)
MODEL_NUMERICAL_FEATURES: List[str] = (
    USER_HISTORY_FEATURES
    + CHALLENGE_HISTORY_FEATURES
    + SNOOZE_HISTORY_FEATURES
    + ALARM_CONTEXT_FEATURES
)
MODEL_CATEGORICAL_FEATURES: List[str] = ["selected_challenge_type"]
EXPECTED_MODEL_FEATURES: List[str] = (
    MODEL_NUMERICAL_FEATURES + MODEL_CATEGORICAL_FEATURES
)
EXPECTED_FEATURE_COUNT = 30

# Strictly excluded features to prevent data leakage and circular preference bias
EXCLUDED_FEATURES: Set[str] = {
    "user_selected_difficulty",
    "is_adaptive_preference",
    "target_is_successful",
    "target_duration_seconds",
    "target_verification_score",
    "target_attempt_number",
    "user_id",
    "wake_session_id",
    "challenge_attempt_id",
    "alarm_id",
    "timestamp",
}

# Approved default confidence threshold for ML policy
DEFAULT_CONFIDENCE_THRESHOLD: float = 0.60


class ModelArtifactError(Exception):
    """Base exception for model artifact and serialization errors."""

    pass


class ModelNotFoundError(ModelArtifactError):
    """Raised when the serialized model file cannot be found on disk."""

    pass


class ModelCorruptError(ModelArtifactError):
    """Raised when the serialized model file cannot be deserialized or is invalid."""

    pass


class ModelMetadataError(ModelArtifactError):
    """Raised when model metadata file is missing, malformed, or has incompatible schema."""

    pass


class IncompatibleFeatureSchemaError(ValueError):
    """Raised when provided features do not match the required 30 model input features."""

    pass


@dataclass
class ModelInferenceResult:
    """Strongly typed result of a model inference operation.

    Attributes:
        predicted_difficulty: The difficulty class with the highest probability ('easy', 'medium', 'hard').
        confidence: Top class probability (between 0.0 and 1.0).
        probabilities: Dictionary mapping every class to its predicted probability.
        meets_confidence_threshold: Whether confidence >= configured confidence_threshold.
        confidence_threshold: The threshold against which confidence was checked.
        feature_snapshot: Dictionary of the exact 30 features passed to the model.
        model_name: Identifier name of the model from metadata.
    """

    predicted_difficulty: str
    confidence: float
    probabilities: Dict[str, float]
    meets_confidence_threshold: bool
    confidence_threshold: float
    feature_snapshot: Dict[str, Any]
    model_name: Optional[str] = None


class ModelInferenceManager:
    """Manages lazy-loading and inference execution for the baseline ML classifier.

    Attributes:
        model_path: Path to the .joblib pipeline file.
        metadata_path: Path to the metadata .json file.
        confidence_threshold: Minimum confidence probability to recommend ML decision.
    """

    def __init__(
        self,
        model_path: Optional[Union[str, Path]] = None,
        metadata_path: Optional[Union[str, Path]] = None,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    ) -> None:
        """Initialize ModelInferenceManager with paths and confidence configuration."""
        # Locate project root (4 levels up from this file)
        project_root = Path(__file__).resolve().parents[3]

        self.model_path = (
            Path(model_path)
            if model_path is not None
            else project_root / "ml" / "models" / "baseline_difficulty_classifier.joblib"
        )
        self.metadata_path = (
            Path(metadata_path)
            if metadata_path is not None
            else project_root / "ml" / "models" / "baseline_metadata.json"
        )
        self.confidence_threshold = confidence_threshold

        # Internal cached instances
        self._model: Optional[Any] = None
        self._metadata: Optional[Dict[str, Any]] = None
        self._expected_features: List[str] = list(EXPECTED_MODEL_FEATURES)

    @property
    def is_loaded(self) -> bool:
        """Return True if model is currently loaded in memory."""
        return self._model is not None

    def clear_cache(self) -> None:
        """Clear loaded model and metadata from cache."""
        self._model = None
        self._metadata = None

    def load_metadata(self) -> Dict[str, Any]:
        """Read and validate the baseline model metadata JSON file.

        Returns:
            Dict containing parsed model metadata.

        Raises:
            ModelMetadataError: If metadata file is missing, invalid JSON, or has mismatched schema.
        """
        if self._metadata is not None:
            return self._metadata

        if not self.metadata_path.exists():
            raise ModelMetadataError(
                f"Model metadata file not found at: {self.metadata_path}"
            )

        try:
            with open(self.metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        except Exception as exc:
            raise ModelMetadataError(
                f"Failed to parse model metadata JSON from {self.metadata_path}: {exc}"
            ) from exc

        if not isinstance(metadata, dict):
            raise ModelMetadataError("Model metadata root must be a JSON dictionary.")

        # Validate feature count and schema if declared in metadata
        input_count = metadata.get("input_features_count")
        if input_count is not None and input_count != EXPECTED_FEATURE_COUNT:
            raise ModelMetadataError(
                f"Model metadata declares {input_count} features, but exactly "
                f"{EXPECTED_FEATURE_COUNT} are expected."
            )

        input_features = metadata.get("input_features")
        if input_features is not None:
            missing = set(self._expected_features) - set(input_features)
            if missing:
                raise ModelMetadataError(
                    f"Model metadata input_features is missing required features: {missing}"
                )

        self._metadata = metadata
        return self._metadata

    def get_model(self) -> Any:
        """Retrieve the cached model pipeline, lazy-loading from disk if not yet loaded.

        Returns:
            Fitted Scikit-Learn Pipeline.

        Raises:
            ModelNotFoundError: If model file does not exist on disk.
            ModelCorruptError: If model file cannot be loaded or is invalid.
        """
        if self._model is not None:
            return self._model

        # Ensure metadata is valid before loading model
        self.load_metadata()

        if not self.model_path.exists():
            raise ModelNotFoundError(
                f"Baseline model artifact not found at: {self.model_path}"
            )

        try:
            pipeline = joblib.load(self.model_path)
        except Exception as exc:
            raise ModelCorruptError(
                f"Failed to load/deserialize model pipeline from {self.model_path}: {exc}"
            ) from exc

        # Validate that the loaded object is a usable estimator with predict_proba
        if not hasattr(pipeline, "predict_proba"):
            raise ModelCorruptError(
                f"Loaded object from {self.model_path} does not implement 'predict_proba'."
            )

        self._model = pipeline
        return self._model

    def extract_model_features(
        self, features: Union[ChallengeFeatureRecord, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Extract and validate strictly the 30 canonical model input features.

        Guarantees:
        - Excludes user preferences (user_selected_difficulty, is_adaptive_preference).
        - Excludes all post-challenge outcome fields.
        - Excludes metadata fields (IDs, timestamps).
        - Verifies that all 30 expected model inputs are present.

        Args:
            features: ChallengeFeatureRecord or equivalent dictionary.

        Returns:
            Dictionary containing strictly the 30 model input features.

        Raises:
            IncompatibleFeatureSchemaError: If any required feature is missing.
        """
        if isinstance(features, ChallengeFeatureRecord):
            raw_dict = features.to_dict(include_targets=False, include_metadata=False)
        elif isinstance(features, dict):
            raw_dict = dict(features)
        else:
            raise IncompatibleFeatureSchemaError(
                f"Features must be a ChallengeFeatureRecord or dict, received: {type(features).__name__}"
            )

        # Check for missing features
        missing = [f for f in self._expected_features if f not in raw_dict]
        if missing:
            raise IncompatibleFeatureSchemaError(
                f"Input features missing {len(missing)} required model inputs: {missing}"
            )

        # Build clean dictionary strictly containing the 30 model features
        clean_features = {f: raw_dict[f] for f in self._expected_features}

        # Verify selected_challenge_type is a valid non-empty string
        ctype = clean_features.get("selected_challenge_type")
        if not isinstance(ctype, str) or not ctype.strip():
            raise IncompatibleFeatureSchemaError(
                "selected_challenge_type must be a non-empty string."
            )

        return clean_features

    def predict(
        self, features: Union[ChallengeFeatureRecord, Dict[str, Any]]
    ) -> ModelInferenceResult:
        """Execute baseline model inference for a single pre-challenge observation.

        Args:
            features: ChallengeFeatureRecord or feature dictionary containing
                      the 30 model inputs.

        Returns:
            ModelInferenceResult with predicted difficulty, confidence, and class probabilities.

        Raises:
            IncompatibleFeatureSchemaError: If input features do not match expected schema.
            ModelNotFoundError: If model file is missing.
            ModelCorruptError: If model file is corrupt.
            ModelMetadataError: If metadata file is missing or corrupt.
        """
        # 1. Extract strictly the 30 model features
        feature_dict = self.extract_model_features(features)

        # 2. Lazy load the model pipeline
        pipeline = self.get_model()

        # 3. Format as a 1-row DataFrame with expected column order
        df = pd.DataFrame([feature_dict], columns=self._expected_features)

        # 4. Predict probabilities
        try:
            raw_probs = pipeline.predict_proba(df)[0]
        except Exception as exc:
            raise ModelCorruptError(
                f"Error executing predict_proba on baseline pipeline: {exc}"
            ) from exc

        # 5. Determine class ordering from pipeline
        classes = getattr(pipeline, "classes_", None)
        if classes is None:
            # Fallback to classifier step's classes_
            classifier = getattr(pipeline, "named_steps", {}).get("classifier")
            classes = getattr(classifier, "classes_", None)

        if classes is None or len(classes) != len(raw_probs):
            raise ModelCorruptError(
                "Pipeline does not expose valid 'classes_' matching predict_proba output."
            )

        # 6. Map probabilities to class names dynamically (respecting actual order)
        prob_dict: Dict[str, float] = {
            str(cls_name): round(float(prob), 4)
            for cls_name, prob in zip(classes, raw_probs)
        }

        # Ensure all canonical difficulty classes are represented
        for diff in VALID_DIFFICULTY_LEVELS:
            if diff not in prob_dict:
                prob_dict[diff] = 0.0

        # 7. Identify top predicted class and confidence
        best_class = max(prob_dict, key=lambda k: prob_dict[k])
        confidence = prob_dict[best_class]

        # 8. Check confidence threshold
        meets_threshold = confidence >= self.confidence_threshold

        metadata = self.load_metadata()
        model_name = metadata.get("model_name", "baseline_difficulty_classifier")

        return ModelInferenceResult(
            predicted_difficulty=best_class,
            confidence=confidence,
            probabilities=prob_dict,
            meets_confidence_threshold=meets_threshold,
            confidence_threshold=self.confidence_threshold,
            feature_snapshot=feature_dict,
            model_name=model_name,
        )
