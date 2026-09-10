"""Pydantic schemas and data contracts for AI-Generated Tongue Twister Challenges (Phase 4.4).

Defines:
- TongueTwisterChallengePayload: Structured payload for tongue twister challenge content.
  Enforces extra="forbid" and strict=True to strictly reject unexpected fields and type coercion.
"""
import re
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Only English is supported in Phase 4.4
SUPPORTED_TONGUE_TWISTER_LANGUAGES = {"en"}


class TongueTwisterChallengePayload(BaseModel):
    """Complete structured payload for an AI-generated tongue twister challenge.

    Enclosed inside ValidatedChallengeContent.content_payload.
    Strictly forbids unexpected fields via extra="forbid" and prevents type coercion via strict=True.
    """

    passage: str = Field(
        ...,
        min_length=10,
        max_length=350,
        description="The articulated tongue-twister passage",
    )
    target_repetitions: Optional[int] = Field(
        None,
        ge=1,
        le=5,
        description="Optional untrusted repetition target; validated against authoritative tier bounds",
    )
    phonetic_focus: Optional[str] = Field(
        None,
        max_length=60,
        description="Optional descriptive label for sound pattern focus (e.g., 's_and_sh_alternation')",
    )
    target_word_count: Optional[int] = Field(
        None,
        ge=4,
        le=50,
        description="Optional untrusted declared word count; validated against actual passage words",
    )
    speaking_duration_seconds: Optional[int] = Field(
        None,
        ge=10,
        le=90,
        description="Optional untrusted speaking duration; validated against authoritative tier bounds",
    )
    language: str = Field(
        default="en",
        description="Language code; locked strictly to 'en' in Phase 4.4",
    )
    proposed_answer: Optional[str] = Field(
        None,
        description="Untrusted LLM-proposed answer; validated independently by TongueTwisterAnswerValidator",
    )

    model_config = ConfigDict(from_attributes=True, extra="forbid", strict=True)

    @field_validator("passage")
    @classmethod
    def validate_passage(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("Passage must be a string.")
        clean = v.strip()
        if not clean:
            raise ValueError("Passage cannot be empty or whitespace only.")
        # Reject control characters or newlines
        if any(ord(c) < 32 and c not in ("\t",) for c in clean):
            raise ValueError("Passage contains control characters or forbidden newlines.")
        return clean

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        clean = v.strip().lower() if isinstance(v, str) else ""
        if clean not in SUPPORTED_TONGUE_TWISTER_LANGUAGES:
            raise ValueError(
                f"Unsupported tongue twister language '{v}'. Phase 4.4 strictly supports English ('en')."
            )
        return clean

    @field_validator("phonetic_focus")
    @classmethod
    def validate_phonetic_focus(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        clean = v.strip()
        if not clean:
            return None
        if any(ord(c) < 32 for c in clean):
            raise ValueError("phonetic_focus cannot contain control characters.")
        return clean

    @model_validator(mode="after")
    def validate_word_count_consistency(self) -> "TongueTwisterChallengePayload":
        """Verify that declared word count matches actual words if declared."""
        if self.target_word_count is not None:
            actual_words = re.findall(r"\b[a-zA-Z]+(?:'[a-zA-Z]+)?\b", self.passage)
            actual_count = len(actual_words)
            if self.target_word_count != actual_count:
                raise ValueError(
                    f"Declared target_word_count ({self.target_word_count}) does not match "
                    f"actual passage word count ({actual_count})."
                )
        return self
