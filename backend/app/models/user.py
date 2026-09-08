"""SQLAlchemy model for User entities."""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database.base import Base


class User(Base):
    """User entity storing profile, timezone, and personal alarm preferences.

    Designed for lightweight single-user capstone usage while maintaining
    full multi-tenant relational readiness.
    """
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(120), unique=True, nullable=True)
    timezone: Mapped[str] = mapped_column(String(50), default="UTC", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    alarms: Mapped[List["Alarm"]] = relationship(
        "Alarm", back_populates="user", cascade="all, delete-orphan"
    )
    wake_sessions: Mapped[List["WakeSession"]] = relationship(
        "WakeSession", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username='{self.username}'>"
