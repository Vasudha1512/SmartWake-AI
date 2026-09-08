"""SQLAlchemy model for runtime ChallengeAttempt executions."""
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database.base import Base


class ChallengeAttempt(Base):
    """Represents the actual runtime execution of a challenge during a wake session.

    Stores the specific prompt generated for the user, timing metrics, attempt number,
    final success/failure outcome, and verification telemetry (e.g., speech transcription
    word-error rate, push-up repetition counts, dance motion energy, or math answers).
    """
    __tablename__ = "challenge_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    wake_session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("wake_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    challenge_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("challenges.id", ondelete="SET NULL"), nullable=True, index=True
    )
    challenge_type: Mapped[str] = mapped_column(String(30), nullable=False)
    difficulty_level: Mapped[str] = mapped_column(String(20), nullable=False)
    prompt_content: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # JSON or text of actual served content (e.g. generated math problem, tongue twister passage)
    attempt_number: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False
    )  # 1 for initial attempt, 2+ for retries
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_successful: Mapped[Optional[bool]] = mapped_column(
        Boolean, nullable=True
    )  # True = passed task, False = failed/abandoned/timed out
    verification_result: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # JSON string of verification data (speech STT transcript, vision rep counts, memory match details)
    verification_score: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )  # Normalized accuracy/confidence score (0.0 to 1.0)
    failure_reason: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )  # Diagnostic (e.g. "pronunciation_mismatch", "wrong_answer", "timeout")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    wake_session: Mapped["WakeSession"] = relationship("WakeSession", back_populates="challenge_attempts")
    challenge: Mapped[Optional["Challenge"]] = relationship("Challenge", back_populates="attempts")

    def __repr__(self) -> str:
        return (
            f"<ChallengeAttempt id={self.id} type='{self.challenge_type}' "
            f"diff='{self.difficulty_level}' success={self.is_successful}>"
        )
