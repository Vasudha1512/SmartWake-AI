"""Pydantic schemas for Alarm request and response models."""
import json
from datetime import datetime
from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.core.exceptions import InvalidDaysOfWeekError
from backend.app.services.alarm_service import validate_days_of_week


class AlarmCreate(BaseModel):
    """Request schema for creating a new Alarm.

    IMPORTANT PRODUCT RULES:
    1. The user explicitly controls the alarm time.
    2. The user explicitly selects the challenge type:
       'dance', 'math', 'memory', 'tongue_twister', 'push_ups'.
    3. Memory represents an actual pattern/sequence recall challenge, NOT number guessing.
    4. The user sets baseline difficulty: 'adaptive', 'easy', 'medium', 'hard'.
    5. ML does NOT choose the challenge type or alter the requested alarm time.
    """
    user_id: int = Field(..., description="ID of the user who owns this alarm")
    time: str = Field(..., description="Scheduled alarm time in 24-hour 'HH:MM' format (e.g. '07:00')")
    selected_challenge_type: str = Field(
        default="tongue_twister",
        description="User-selected challenge: 'dance', 'math', 'memory', 'tongue_twister', 'push_ups'",
    )
    difficulty_preference: str = Field(
        default="adaptive",
        description="Baseline difficulty preference: 'adaptive', 'easy', 'medium', 'hard'",
    )
    label: Optional[str] = Field("Alarm", max_length=100, description="Optional alarm label")
    days_of_week: Optional[List[int]] = Field(
        default=[0, 1, 2, 3, 4],
        description="List of active weekday integers (0=Mon, 6=Sun)",
    )
    is_active: Optional[bool] = Field(True, description="Master alarm active toggle switch")

    @field_validator("days_of_week", mode="before")
    @classmethod
    def validate_days(cls, v: Any) -> Optional[List[int]]:
        """Validate days_of_week JSON array input."""
        if v is None:
            return [0, 1, 2, 3, 4]
        if isinstance(v, str):
            raise ValueError("days_of_week must be a JSON array of integers, not a string.")
        try:
            return validate_days_of_week(v)
        except InvalidDaysOfWeekError as exc:
            raise ValueError(str(exc)) from exc

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": 1,
                "time": "07:00",
                "selected_challenge_type": "tongue_twister",
                "difficulty_preference": "adaptive",
                "label": "Morning Routine",
                "days_of_week": [0, 1, 2, 3, 4],
                "is_active": True,
            }
        }
    )


class AlarmUpdate(BaseModel):
    """Request schema for updating an existing Alarm.

    NOTE: The owning user_id CANNOT be modified through this update model.
    """
    time: Optional[str] = Field(None, description="24-hour format 'HH:MM' (e.g. '07:15')")
    selected_challenge_type: Optional[str] = Field(
        None,
        description="User-selected task: 'dance', 'math', 'memory', 'tongue_twister', 'push_ups'",
    )
    difficulty_preference: Optional[str] = Field(
        None,
        description="Baseline difficulty: 'adaptive', 'easy', 'medium', 'hard'",
    )
    label: Optional[str] = Field(None, max_length=100, description="Optional alarm label")
    days_of_week: Optional[List[int]] = Field(
        None, description="List of active weekday integers (0=Mon, 6=Sun)"
    )
    is_active: Optional[bool] = Field(None, description="Master alarm active toggle switch")

    @field_validator("days_of_week", mode="before")
    @classmethod
    def validate_days(cls, v: Any) -> Optional[List[int]]:
        """Validate days_of_week JSON array input."""
        if v is None:
            return None
        if isinstance(v, str):
            raise ValueError("days_of_week must be a JSON array of integers, not a string.")
        try:
            return validate_days_of_week(v)
        except InvalidDaysOfWeekError as exc:
            raise ValueError(str(exc)) from exc

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "time": "07:15",
                "selected_challenge_type": "math",
                "difficulty_preference": "medium",
                "label": "Updated Routine",
                "days_of_week": [0, 1, 2, 3, 4],
                "is_active": True,
            }
        }
    )


class AlarmResponse(BaseModel):
    """Response schema representing a persisted Alarm."""
    id: int
    user_id: int
    time: str
    label: Optional[str] = None
    days_of_week: List[int]
    selected_challenge_type: str
    difficulty_preference: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("days_of_week", mode="before")
    @classmethod
    def deserialize_days(cls, v: Any) -> List[int]:
        """Deserialize JSON string or list into sorted List[int]."""
        if isinstance(v, str):
            try:
                v = json.loads(v)
            except Exception as exc:
                raise ValueError(f"Invalid days_of_week stored in database: {exc}") from exc
        try:
            return validate_days_of_week(v)
        except InvalidDaysOfWeekError as exc:
            raise ValueError(str(exc)) from exc

