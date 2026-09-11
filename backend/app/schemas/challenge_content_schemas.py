"""Pydantic schemas and data contracts for Personalized Challenge Content Framework (Phase 4.1).

Defines:
- SafePersonalizationContext: Sanitized, identity-free generation context.
- ChallengeGenerationConstraints: Generic framework constraints and structural boundaries.
- ValidatedChallengeContent: Internal domain representation of validated generated challenge content.
- ContentValidationResult: Outcome of content validation inspection.
"""
import re
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.core.constants import FORBIDDEN_CHALLENGE_TYPES, VALID_CHALLENGE_TYPES

# Forbidden identity and sensitive keys that must NEVER enter GenAI context
FORBIDDEN_CONTEXT_KEYS: Set[str] = {
    "user_id",
    "email",
    "username",
    "name",
    "phone",
    "alarm_id",
    "session_id",
    "wake_session_id",
    "password",
    "passphrase",
    "password_hash",
    "token",
    "access_token",
    "auth_token",
    "refresh_token",
    "session_token",
    "auth",
    "authorization",
    "cookie",
    "api_key",
    "apikey",
    "secret",
    "api_secret",
    "client_secret",
    "private_key",
    "credential",
    "credentials",
    "jwt",
    "bearer",
}

# Regex pattern allowing alphanumeric words, spaces, hyphens, and underscores for topics
SAFE_TOPIC_REGEX = re.compile(r"^[a-zA-Z0-9_\- ]+$")



class SafePersonalizationContext(BaseModel):
    """Sanitized, non-identifiable context for GenAI challenge content generation.

    Strictly excludes database identity (user_id, session_id, alarm_id) and PII.
    Only contains purpose-specific parameters that safely shape challenge content.
    """

    desired_duration_seconds: Optional[int] = Field(
        default=None,
        ge=5,
        le=300,
        description="User desired challenge duration in seconds (generation styling preference only, NOT an ML target)",
    )
    current_session_snooze_count: int = Field(
        default=0,
        ge=0,
        le=20,
        description="Bounded session snooze count indicating sleep inertia level",
    )
    current_attempt_number: int = Field(
        default=1,
        ge=1,
        le=10,
        description="Bounded attempt sequence number for this session",
    )
    preferred_theme: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Optional high-level challenge theme or style (e.g., 'morning motivation')",
    )
    language: str = Field(
        default="en",
        max_length=10,
        description="Language code for generated content (default 'en')",
    )
    disallowed_topics: List[str] = Field(
        default_factory=list,
        description="Strictly bounded list of topics or words to avoid",
    )

    model_config = ConfigDict(extra="forbid")

    @field_validator("preferred_theme")
    @classmethod
    def validate_preferred_theme(cls, v: Optional[str]) -> Optional[str]:
        """Validate and sanitize preferred_theme."""
        if v is None:
            return None
        clean = v.strip()
        if not clean:
            return None
        # Reject control characters or newlines
        if any(ord(c) < 32 for c in clean):
            raise ValueError("preferred_theme cannot contain control characters or newlines.")
        if len(clean) > 50:
            raise ValueError("preferred_theme cannot exceed 50 characters.")
        return clean

    @field_validator("disallowed_topics", mode="before")
    @classmethod
    def validate_disallowed_topics(cls, topics: Any) -> List[str]:
        """Validate disallowed_topics against strict bounds and character safety rules.

        Rejects oversized or malformed values rather than silently truncating.
        """
        if topics is None:
            return []

        if not isinstance(topics, list):
            raise ValueError("disallowed_topics must be a list of strings.")

        if len(topics) > 10:
            raise ValueError(
                f"disallowed_topics cannot exceed 10 topics (received {len(topics)})."
            )

        cleaned_topics: List[str] = []
        total_len = 0

        for idx, item in enumerate(topics):
            if not isinstance(item, str):
                raise ValueError(
                    f"disallowed_topics[{idx}] must be a string, got {type(item).__name__}."
                )

            # Check for control characters or newlines
            if any(ord(c) < 32 for c in item):
                raise ValueError(f"disallowed_topics[{idx}] contains control characters or newlines.")

            clean_item = item.strip().lower()
            if not clean_item:
                raise ValueError(f"disallowed_topics[{idx}] cannot be empty or whitespace only.")

            if len(clean_item) > 30:
                raise ValueError(
                    f"disallowed_topics[{idx}] '{clean_item[:15]}...' exceeds maximum length of 30 characters."
                )

            # Check for allowed characters
            if not SAFE_TOPIC_REGEX.match(clean_item):
                raise ValueError(
                    f"disallowed_topics[{idx}] '{clean_item}' contains invalid characters. "
                    "Only alphanumeric characters, spaces, hyphens, and underscores are permitted."
                )

            if clean_item not in cleaned_topics:
                cleaned_topics.append(clean_item)
                total_len += len(clean_item)

        if total_len > 300:
            raise ValueError(
                f"Total serialized length of disallowed_topics ({total_len}) exceeds maximum limit of 300 characters."
            )


        return cleaned_topics


class ChallengeGenerationConstraints(BaseModel):
    """Generic structural boundaries and constraint slots for challenge content generation.

    Defines the framework contract that future sub-phase generators (4.2-4.5) plug into.
    """

    challenge_type: str = Field(
        ...,
        description="Canonical challenge type ('dance', 'math', 'memory', 'tongue_twister', 'push_ups')",
    )
    difficulty_level: str = Field(
        ...,
        description="Concrete difficulty tier ('easy', 'medium', 'hard')",
    )
    max_title_length: int = Field(
        default=100,
        ge=10,
        le=200,
        description="Maximum allowed character length for challenge title",
    )
    max_instructions_length: int = Field(
        default=500,
        ge=20,
        le=1000,
        description="Maximum allowed character length for instructions",
    )
    max_payload_bytes: int = Field(
        default=16384,
        ge=1024,
        le=65536,
        description="Maximum serialized JSON byte size for content_payload (16 KB default)",
    )
    forbidden_terms: Set[str] = Field(
        default_factory=set,
        description="Set of terms or concepts strictly forbidden in content",
    )
    required_payload_keys: List[str] = Field(
        default_factory=list,
        description="Generic required top-level keys in content_payload",
    )
    min_duration_seconds: int = Field(
        default=10,
        ge=5,
        le=120,
        description="Minimum expected interaction duration for anti-sleepy-bypass",
    )
    verification_mode: str = Field(
        ...,
        description="Expected Phase 2.8 verification mode string",
    )

    @field_validator("challenge_type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        clean = v.strip().lower() if isinstance(v, str) else ""
        if clean in FORBIDDEN_CHALLENGE_TYPES:
            raise ValueError(
                f"Challenge type '{v}' is strictly forbidden. Memory challenges forbid number guessing."
            )
        if clean not in VALID_CHALLENGE_TYPES:
            raise ValueError(
                f"Invalid challenge type '{v}'. Must be one of: {sorted(list(VALID_CHALLENGE_TYPES))}."
            )
        return clean

    @field_validator("difficulty_level")
    @classmethod
    def validate_diff(cls, v: str) -> str:
        clean = v.strip().lower() if isinstance(v, str) else ""
        if clean not in ("easy", "medium", "hard"):
            raise ValueError(
                f"Invalid difficulty '{v}'. Must be concrete: 'easy', 'medium', or 'hard'."
            )
        return clean


class ValidatedChallengeContent(BaseModel):
    """Internal domain representation of validated generated challenge content.

    Structurally aligned with RuntimeChallengeResponse conventions, but serves as
    the internal validated contract for the GenAI Content Framework.
    """

    challenge_type: str = Field(..., description="Canonical challenge category")
    difficulty_level: str = Field(..., description="Concrete difficulty tier ('easy', 'medium', 'hard')")
    title: str = Field(..., min_length=3, max_length=100, description="Challenge title")
    instructions: str = Field(..., min_length=10, max_length=500, description="Clear instructions for user")
    content_payload: Dict[str, Any] = Field(..., description="Generic structured challenge payload")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Configuration parameters used")
    expected_answer: Optional[Any] = Field(None, description="Expected answer for Phase 2.8 verification")
    verification_mode: str = Field(..., description="Verification mode identifier")
    min_duration_seconds: int = Field(..., ge=5, description="Minimum expected interaction seconds")
    generation_metadata: Dict[str, Any] = Field(default_factory=dict, description="Generation and validation telemetry")

    model_config = ConfigDict(from_attributes=True)


class ContentValidationResult(BaseModel):
    """Result of content validation inspection."""

    is_valid: bool = Field(..., description="Whether the challenge content passed all validation checks")
    errors: List[str] = Field(default_factory=list, description="List of validation failure reasons if any")
    validated_content: Optional[ValidatedChallengeContent] = Field(
        None, description="The validated content instance if successful"
    )

    model_config = ConfigDict(from_attributes=True)
