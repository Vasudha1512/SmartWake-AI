"""SQLAlchemy model for MLAdaptiveLog decision audits."""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.datetime_utils import now_utc_naive
from backend.app.database.base import Base


class MLAdaptiveLog(Base):
    """Auditing and training ground-truth store for adaptive ML challenge parameter decisions.

    IMPORTANT PRODUCT RULE:
    The USER chooses the wake-up task type when configuring the alarm.
    The ML system NEVER selects or changes the task type.
    The ML system ONLY adapts:
      - difficulty level ('easy', 'medium', 'hard')
      - challenge parameters (e.g. minimum word count, phonetic complexity bounds, rep count targets)
      - dynamic generated content within the user's selected task type

    CRITICAL DATA LEAKAGE PREVENTION RULE:
    This model strictly snapshots the HISTORICAL and pre-challenge features available
    at the exact moment of decision (e.g. prior days' rolling snoozes, past accuracy in the
    selected task type, current session snooze count prior to challenge, day of week, scheduled hour).

    The post-event outcomes of the CURRENT challenge (such as duration_seconds,
    is_successful, or dismissed_time) are NEVER stored here as input features. They are
    stored exclusively in `challenge_attempts` and `wake_sessions` to serve as the future
    supervised training targets (y).
    """
    __tablename__ = "ml_adaptive_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    wake_session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("wake_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    decision_timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=now_utc_naive, nullable=False
    )
    historical_features_snapshot: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # Serialized JSON of historical/pre-challenge features used at decision time
    user_selected_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # USER CHOICE: "dance", "math", "memory", "tongue_twister", "push_ups"
    adaptive_difficulty: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # ML ADAPTATION: "easy", "medium", "hard"
    adaptive_parameters: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # JSON string of adapted parameters (e.g., target sentence length, phonetic friction, target reps)
    model_policy_version: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # e.g. "rf_adaptive_v1.0" or "cold_start_heuristic_v1.0"
    confidence_score: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )  # Model confidence or classification probability
    decision_rationale: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # Explainable rationale (e.g. "User selected tongue_twister; historical performance supports medium difficulty.")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc_naive, nullable=False)

    # Relationships
    wake_session: Mapped["WakeSession"] = relationship("WakeSession", back_populates="ml_adaptive_logs")

    def __repr__(self) -> str:
        return (
            f"<MLAdaptiveLog id={self.id} session_id={self.wake_session_id} "
            f"user_type='{self.user_selected_type}' adaptive_diff='{self.adaptive_difficulty}'>"
        )
