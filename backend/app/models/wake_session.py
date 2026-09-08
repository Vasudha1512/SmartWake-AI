"""SQLAlchemy model for WakeSession lifecycle tracking."""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database.base import Base


class WakeSession(Base):
    """Represents one complete alarm-to-wake-success/failure lifecycle.

    Tracks the session from initial scheduled ring, through any snooze cycles
    and challenge attempts, to final dismissal or abandonment.
    """
    __tablename__ = "wake_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alarm_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("alarms.id", ondelete="SET NULL"), nullable=True, index=True
    )
    scheduled_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    initial_ring_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    dismissed_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    total_snooze_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_wake_delay_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="ringing", nullable=False
    )  # "ringing", "snoozed", "in_challenge", "completed", "abandoned"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="wake_sessions")
    alarm: Mapped[Optional["Alarm"]] = relationship("Alarm", back_populates="wake_sessions")
    snooze_events: Mapped[List["SnoozeEvent"]] = relationship(
        "SnoozeEvent", back_populates="wake_session", cascade="all, delete-orphan"
    )
    challenge_attempts: Mapped[List["ChallengeAttempt"]] = relationship(
        "ChallengeAttempt", back_populates="wake_session", cascade="all, delete-orphan"
    )
    ml_adaptive_logs: Mapped[List["MLAdaptiveLog"]] = relationship(
        "MLAdaptiveLog", back_populates="wake_session", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<WakeSession id={self.id} status='{self.status}' snoozes={self.total_snooze_count}>"
