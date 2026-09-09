"""SQLAlchemy model for Challenge catalog templates."""
from datetime import datetime
from typing import List

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.datetime_utils import now_utc_naive
from backend.app.database.base import Base


class Challenge(Base):
    """Master challenge catalog and template definition store.

    Defines available challenge categories and parameterized templates across difficulty tiers.
    Runtime challenge instances presented to the user are generated from these templates.

    Supported challenge types:
      - 'dance': Physical coordination and movement routines
      - 'math': Multi-step arithmetic problems
      - 'memory': Visual sequence and pattern recall (strictly non-number guessing)
      - 'tongue_twister': Substantial sentences and passages scaling in length and phonetic friction
      - 'push_ups': Physical exercise repetition tracking

    Difficulty tiers ('easy', 'medium', 'hard') scale task complexity. For Tongue Twisters,
    difficulty increases sentence length and phonetic complexity rather than merely retry counts.
    """
    __tablename__ = "challenges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    challenge_type: Mapped[str] = mapped_column(
        String(30), nullable=False, index=True
    )  # "dance", "math", "memory", "tongue_twister", "push_ups"
    difficulty_level: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )  # "easy", "medium", "hard"
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    template_payload: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # JSON string containing template parameters, minimum word counts, phonetic rules, or operator bounds
    min_duration_seconds: Mapped[int] = mapped_column(
        Integer, default=10, nullable=False
    )  # Prevents sleepy bypass by enforcing minimum expected interaction time
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc_naive, nullable=False)

    # Relationships
    attempts: Mapped[List["ChallengeAttempt"]] = relationship(
        "ChallengeAttempt", back_populates="challenge"
    )

    def __repr__(self) -> str:
        return f"<Challenge id={self.id} type='{self.challenge_type}' diff='{self.difficulty_level}'>"
