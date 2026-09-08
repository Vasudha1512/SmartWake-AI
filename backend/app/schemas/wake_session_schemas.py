"""Pydantic schemas for WakeSession request and response models."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class WakeSessionCreate(BaseModel):
    """Request schema for starting a new WakeSession occurrence.

    A wake session represents one complete occurrence of an alarm ring.
    The client provides user_id and alarm_id. The backend automatically generates
    and manages timestamps, ring status, and telemetry.
    """
    user_id: int = Field(..., description="ID of the user experiencing this wake session")
    alarm_id: int = Field(..., description="ID of the active alarm triggering this session")
    scheduled_time: Optional[datetime] = Field(
        None,
        description="Optional scheduled firing datetime. Defaults to current UTC time if omitted.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": 1,
                "alarm_id": 1,
            }
        }
    )


class WakeSessionResponse(BaseModel):
    """Response schema representing a persisted WakeSession."""
    id: int
    user_id: int
    alarm_id: Optional[int] = None
    scheduled_time: datetime
    initial_ring_time: datetime
    dismissed_time: Optional[datetime] = None
    total_snooze_count: int = 0
    total_wake_delay_seconds: Optional[float] = None
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
