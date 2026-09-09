"""SQLAlchemy model for Alarm configurations."""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.datetime_utils import now_utc_naive
from backend.app.database.base import Base


class Alarm(Base):
    """Scheduled alarm configuration.

    USER INPUTS:
    - Desired alarm time (e.g., "07:00").
    - User-selected challenge type ('dance', 'math', 'memory', 'tongue_twister', 'push_ups').
    - User baseline difficulty preference ('adaptive', 'easy', 'medium', 'hard').

    IMPORTANT PRODUCT RULE:
    The USER chooses the wake-up task type when creating the alarm.
    The ML system NEVER changes the user's alarm time and NEVER changes the user's chosen
    task type. The ML system only adapts the difficulty, parameters, and generated content
    within the user's selected task type.
    """
    __tablename__ = "alarms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    time: Mapped[str] = mapped_column(String(5), nullable=False)  # Format "HH:MM" (24-hour)
    label: Mapped[Optional[str]] = mapped_column(String(100), default="Alarm", nullable=True)
    days_of_week: Mapped[str] = mapped_column(
        String(50), default="[0,1,2,3,4]", nullable=False
    )  # JSON array string, e.g. "[0,1,2,3,4]" (0=Mon, 6=Sun)
    selected_challenge_type: Mapped[str] = mapped_column(
        String(30), default="tongue_twister", nullable=False
    )  # USER CHOICE: "dance", "math", "memory", "tongue_twister", "push_ups"
    difficulty_preference: Mapped[str] = mapped_column(
        String(20), default="adaptive", nullable=False
    )  # "adaptive" (ML tunes difficulty), "easy", "medium", "hard"
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_utc_naive, onupdate=now_utc_naive, nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="alarms")
    wake_sessions: Mapped[List["WakeSession"]] = relationship(
        "WakeSession", back_populates="alarm"
    )

    def __repr__(self) -> str:
        return f"<Alarm id={self.id} time='{self.time}' is_active={self.is_active}>"
