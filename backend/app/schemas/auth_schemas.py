"""Pydantic schemas for Authentication request and response models."""
import re
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.core.exceptions import InvalidTimezoneError
from backend.app.schemas.user_schemas import UserResponse
from backend.app.services.user_service import validate_timezone

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


class UserRegister(BaseModel):
    """Registration request payload."""
    username: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="Unique user display name (3-50 characters)",
    )
    email: str = Field(
        ...,
        min_length=5,
        max_length=120,
        description="Unique valid email address",
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="User password (minimum 8 characters)",
    )
    timezone: Optional[str] = Field(
        "UTC",
        max_length=50,
        description="User local IANA timezone identifier",
    )

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        clean = v.strip()
        if len(clean) < 3:
            raise ValueError("Username must be at least 3 characters long.")
        return clean

    @field_validator("email")
    @classmethod
    def validate_and_normalize_email(cls, v: str) -> str:
        clean = v.strip().lower()
        if not EMAIL_REGEX.match(clean):
            raise ValueError("Invalid email format.")
        return clean

    @field_validator("timezone", mode="before")
    @classmethod
    def validate_tz(cls, v: Optional[str]) -> str:
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
                "password": "strongpassword123",
                "timezone": "UTC",
            }
        }
    )


class UserLogin(BaseModel):
    """Login request payload."""
    email: str = Field(..., description="User registered email address")
    password: str = Field(..., min_length=1, description="Plaintext password candidate")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        clean = v.strip().lower()
        if not clean:
            raise ValueError("Email cannot be empty.")
        return clean

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "alex@example.com",
                "password": "strongpassword123",
            }
        }
    )


class TokenResponse(BaseModel):
    """JWT bearer token response."""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

    model_config = ConfigDict(from_attributes=True)
