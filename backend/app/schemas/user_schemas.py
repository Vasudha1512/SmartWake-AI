"""Pydantic schemas for User request and response models."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.core.exceptions import InvalidTimezoneError
from backend.app.services.user_service import validate_timezone


class UserCreate(BaseModel):
    """Request schema for creating a new User."""
    username: str = Field(..., min_length=1, max_length=50, description="Unique user display handle")
    email: Optional[str] = Field(None, max_length=120, description="Optional user email address")
    timezone: Optional[str] = Field("UTC", max_length=50, description="User local timezone")

    @field_validator("timezone", mode="before")
    @classmethod
    def validate_tz(cls, v: Optional[str]) -> str:
        """Validate timezone string against recognized IANA identifiers."""
        if v is None:
            return "UTC"
        try:
            return validate_timezone(v)
        except InvalidTimezoneError as exc:
            raise ValueError(str(exc)) from exc

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "username": "alex",
                "email": "alex@example.com",
                "timezone": "UTC",
            }
        }
    )


class UserResponse(BaseModel):
    """Response schema representing a persisted User."""
    id: int
    username: str
    email: Optional[str] = None
    timezone: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
