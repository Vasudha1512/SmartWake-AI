"""SQLAlchemy ORM models package for SmartWake AI.

Exports all core database entities and registers them on DeclarativeBase metadata.
"""
from backend.app.models.user import User
from backend.app.models.alarm import Alarm
from backend.app.models.wake_session import WakeSession
from backend.app.models.snooze_event import SnoozeEvent
from backend.app.models.challenge import Challenge
from backend.app.models.challenge_attempt import ChallengeAttempt
from backend.app.models.ml_adaptive_log import MLAdaptiveLog

__all__ = [
    "User",
    "Alarm",
    "WakeSession",
    "SnoozeEvent",
    "Challenge",
    "ChallengeAttempt",
    "MLAdaptiveLog",
]
