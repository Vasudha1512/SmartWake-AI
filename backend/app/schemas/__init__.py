"""Pydantic schemas package for SmartWake AI."""
from backend.app.schemas.user_schemas import UserCreate, UserResponse
from backend.app.schemas.alarm_schemas import AlarmCreate, AlarmUpdate, AlarmResponse

__all__ = [
    "UserCreate",
    "UserResponse",
    "AlarmCreate",
    "AlarmUpdate",
    "AlarmResponse",
]
