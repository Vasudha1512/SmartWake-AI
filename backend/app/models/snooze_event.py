"""SQLAlchemy model for SnoozeEvent behavioral telemetry."""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database.base import Base


class SnoozeEvent(Base):
    """Granular snooze behavior telemetry.

    Captures timestamped interaction data each time the user presses Snooze,
    providing critical behavioral history for the adaptive ML system to quantify
    morning sleep inertia and fatigue.
    """
    __tablename__ = "snooze_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    wake_session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("wake_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    snooze_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1st, 2nd, 3rd snooze in session
    snoozed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    ring_resumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    snooze_duration_minutes: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    wake_session: Mapped["WakeSession"] = relationship("WakeSession", back_populates="snooze_events")

    def __repr__(self) -> str:
        return f"<SnoozeEvent id={self.id} session_id={self.wake_session_id} snooze_no={self.snooze_number}>"
