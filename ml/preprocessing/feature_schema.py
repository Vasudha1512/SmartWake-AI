"""Canonical feature schema definitions and typed structures for ML adaptive intelligence.

CRITICAL DATA-LEAKAGE PREVENTION RULE:
Features defined in this schema represent exclusively historical context, prior session behavior,
and pre-challenge session state available BEFORE the current challenge outcome is determined.
Target variables (such as target_is_successful, target_duration_seconds, target_verification_score)
are strictly kept distinct from input features and must NEVER be used as prediction inputs
for the same challenge.
"""
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


# Canonical category definitions
USER_HISTORY_FEATURES: List[str] = [
    "user_total_wake_sessions",
    "user_successful_wake_sessions",
    "user_failed_wake_sessions",
    "user_historical_success_rate",
    "user_avg_completion_time_seconds",
    "user_avg_attempts_per_session",
    "user_avg_snooze_count",
    "user_total_snooze_count",
    "user_recent_snooze_count",
    "user_recent_challenge_success_rate",
]

CHALLENGE_HISTORY_FEATURES: List[str] = [
    "challenge_type_total_attempts",
    "challenge_type_successful_attempts",
    "challenge_type_success_rate",
    "challenge_type_avg_completion_time",
    "challenge_type_avg_attempts_per_session",
    "challenge_type_easy_attempts",
    "challenge_type_easy_success_rate",
    "challenge_type_medium_attempts",
    "challenge_type_medium_success_rate",
    "challenge_type_hard_attempts",
    "challenge_type_hard_success_rate",
]

SNOOZE_HISTORY_FEATURES: List[str] = [
    "current_session_snooze_count",
    "current_session_snooze_duration_minutes",
    "current_session_wake_delay_seconds",
]

ALARM_CONTEXT_FEATURES: List[str] = [
    "alarm_scheduled_hour",
    "alarm_scheduled_minute",
    "alarm_day_of_week",
    "alarm_is_weekend",
    "historical_snooze_avg_around_alarm_time",
]

CURRENT_CONTEXT_FEATURES: List[str] = [
    "selected_challenge_type",
    "user_selected_difficulty",
    "is_adaptive_preference",
]

# All input features (28 features)
FEATURE_COLUMNS: List[str] = (
    USER_HISTORY_FEATURES
    + CHALLENGE_HISTORY_FEATURES
    + SNOOZE_HISTORY_FEATURES
    + ALARM_CONTEXT_FEATURES
    + CURRENT_CONTEXT_FEATURES
)

# Supervised training targets (strictly decoupled from input features)
TARGET_COLUMNS: List[str] = [
    "target_is_successful",
    "target_duration_seconds",
    "target_verification_score",
    "target_attempt_number",
]

# Metadata columns for auditing, tracing, and joins
METADATA_COLUMNS: List[str] = [
    "user_id",
    "wake_session_id",
    "challenge_attempt_id",
    "alarm_id",
    "timestamp",
]

ALL_DATASET_COLUMNS: List[str] = METADATA_COLUMNS + FEATURE_COLUMNS + TARGET_COLUMNS


@dataclass
class ChallengeFeatureRecord:
    """Strongly typed representation of one observation in the ML feature space.

    All attributes in USER_HISTORY, CHALLENGE_HISTORY, SNOOZE_HISTORY, ALARM_CONTEXT,
    and CURRENT_CONTEXT must be computed using strictly information available BEFORE
    the challenge outcome.
    """
    # Metadata
    user_id: int
    wake_session_id: int
    challenge_attempt_id: Optional[int]
    alarm_id: Optional[int]
    timestamp: str  # ISO-formatted UTC string

    # 1. USER_HISTORY
    user_total_wake_sessions: int = 0
    user_successful_wake_sessions: int = 0
    user_failed_wake_sessions: int = 0
    user_historical_success_rate: float = 0.0
    user_avg_completion_time_seconds: float = 0.0
    user_avg_attempts_per_session: float = 0.0
    user_avg_snooze_count: float = 0.0
    user_total_snooze_count: int = 0
    user_recent_snooze_count: int = 0
    user_recent_challenge_success_rate: float = 0.0

    # 2. CHALLENGE_HISTORY
    challenge_type_total_attempts: int = 0
    challenge_type_successful_attempts: int = 0
    challenge_type_success_rate: float = 0.0
    challenge_type_avg_completion_time: float = 0.0
    challenge_type_avg_attempts_per_session: float = 0.0
    challenge_type_easy_attempts: int = 0
    challenge_type_easy_success_rate: float = 0.0
    challenge_type_medium_attempts: int = 0
    challenge_type_medium_success_rate: float = 0.0
    challenge_type_hard_attempts: int = 0
    challenge_type_hard_success_rate: float = 0.0

    # 3. SNOOZE_HISTORY (Pre-attempt telemetry in current session)
    current_session_snooze_count: int = 0
    current_session_snooze_duration_minutes: int = 0
    current_session_wake_delay_seconds: float = 0.0

    # 4. ALARM_CONTEXT
    alarm_scheduled_hour: int = 7
    alarm_scheduled_minute: int = 0
    alarm_day_of_week: int = 0
    alarm_is_weekend: int = 0
    historical_snooze_avg_around_alarm_time: float = 0.0

    # 5. CURRENT_CONTEXT
    selected_challenge_type: str = "tongue_twister"
    user_selected_difficulty: str = "adaptive"
    is_adaptive_preference: int = 1

    # 6. SUPERVISED TARGET LABELS (Only populated if target attempt outcome is known)
    target_is_successful: Optional[int] = None
    target_duration_seconds: Optional[float] = None
    target_verification_score: Optional[float] = None
    target_attempt_number: Optional[int] = None

    def to_dict(self, include_targets: bool = True, include_metadata: bool = True) -> Dict[str, Any]:
        """Convert to dictionary representation, optionally omitting targets or metadata."""
        d = asdict(self)
        if not include_targets:
            for col in TARGET_COLUMNS:
                d.pop(col, None)
        if not include_metadata:
            for col in METADATA_COLUMNS:
                d.pop(col, None)
        return d

    def to_feature_vector(self) -> List[Any]:
        """Return ordered feature values matching FEATURE_COLUMNS."""
        d = asdict(self)
        return [d[col] for col in FEATURE_COLUMNS]
