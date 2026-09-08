"""Pydantic schemas for User request and response models."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class UserCreate(BaseModel):
    """Request schema for creating a new User."""
    username: str = Field(..., min_length=1, max_length=50, description="Unique user display handle")
    email: Optional[str] = Field(None, max_length=120, description="Optional user email address")
    timezone: Optional[str] = Field("UTC", max_length=50, description="User local timezone")

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
