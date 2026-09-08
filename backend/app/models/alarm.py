"""SQLAlchemy model for Alarm configurations."""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database.base import Base


class Alarm(Base):
    """Scheduled alarm configuration.

    Stores the user's desired wake-up time and recurrence rules.
    NOTE: The ML system adaptively selects the wake-up challenge and difficulty,
    but must NOT automatically modify the user's explicit alarm time.
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
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    challenge_mode: Mapped[str] = mapped_column(
        String(20), default="adaptive", nullable=False
    )  # "adaptive" (AI/heuristic selected) or "manual"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="alarms")
    wake_sessions: Mapped[List["WakeSession"]] = relationship(
        "WakeSession", back_populates="alarm"
    )

    def __repr__(self) -> str:
        return f"<Alarm id={self.id} time='{self.time}' is_active={self.is_active}>"
