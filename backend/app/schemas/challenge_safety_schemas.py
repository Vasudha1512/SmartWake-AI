"""Pydantic schemas and data contracts for GenAI Safety, Validation & Fallback (Phase 4.6.1).

Defines foundational typed contracts for the Phase 4.6 GenAI safety boundary:
- SafetyViolationCode: Canonical enumeration of safety and structural failure codes.
- SafetySeverity: Severity tier ('critical' or 'warning') indicating whether content is rejected.
- SafetyViolationDetails: Bounded, typed diagnostic metadata (zero Dict[str, Any], zero PII).
- SafetyViolation: Structured domain violation model.
- SafetyValidationReport: Outcome report for safety inspection (no sanitized_content field).
- FallbackReason: Categorical reasons triggering procedural/algorithmic fallback.
- FallbackSource: Allowed source categories for fallback content ('procedural_catalog', 'algorithmic_fallback').
- FallbackPayloadContract: Bounded reference contract for fallback content.
- FallbackResolution: Auditable record of a fallback event enforcing type & difficulty preservation.
- ValidationRetryPolicy: Bounded retry and latency budget specification (max_retries <= 2).

CRITICAL ARCHITECTURAL INVARIANTS:
1. Canonical challenge type and concrete difficulty are strictly preserved across all contracts.
2. Provider and generated content are treated as UNTRUSTED.
3. No silent sanitization: invalid content is rejected rather than silently mutated.
4. Privacy by construction: zero database IDs, PII, auth tokens, or ORM objects.
5. Zero generic Dict[str, Any] escape hatches across all schemas.
6. The contracts establish typed boundaries only; they do not perform generation, validation,
   sanitization, retries, network calls, or runtime execution.
"""
from enum import Enum
import re
from typing import List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.schemas.challenge_content_schemas import FORBIDDEN_CONTEXT_KEYS
from backend.app.schemas.personalization_content_schemas import (
    CanonicalChallengeType,
    CanonicalDifficultyLevel,
    VALID_CANONICAL_CHALLENGE_TYPES,
    VALID_CANONICAL_DIFFICULTIES,
)


class SafetyViolationCode(str, Enum):
    """Canonical machine-readable classification codes for safety and validation violations."""

    # Framework & Structural Violations
    SCHEMA_MALFORMED = "schema_malformed"
    TYPE_MUTATION = "type_mutation"
    DIFFICULTY_MUTATION = "difficulty_mutation"
    PROMPT_INJECTION = "prompt_injection"
    HARMFUL_CONTENT = "harmful_content"

    # Math Safety Violations
    MATH_UNSOLVABLE = "math_unsolvable"
    MATH_DIVISION_BY_ZERO = "math_division_by_zero"
    MATH_PRECISION_OVERFLOW = "math_precision_overflow"

    # Memory Safety Violations (Strict Non-Numeric Guarantees)
    MEMORY_NUMERIC_LEAK = "memory_numeric_leak"
    MEMORY_EMPTY_SEQUENCE = "memory_empty_sequence"
    MEMORY_INVALID_PALETTE = "memory_invalid_palette"

    # Tongue-Twister Safety Violations
    TONGUE_TWISTER_LENGTH_BOUNDS = "tongue_twister_length_bounds"
    TONGUE_TWISTER_LOW_ALLITERATION = "tongue_twister_low_alliteration"

    # Procedural Physical Safety Violations
    PHYSICAL_EXERTION_EXCEEDED = "physical_exertion_exceeded"

    # Operational & Boundary Violations
    LATENCY_BUDGET_EXCEEDED = "latency_budget_exceeded"
    PROVIDER_ERROR = "provider_error"


class SafetySeverity(str, Enum):
    """Severity tier for an observed safety or validation violation."""

    CRITICAL = "critical"
    WARNING = "warning"


FORBIDDEN_KEY_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in sorted(FORBIDDEN_CONTEXT_KEYS)) + r")\b",
    re.IGNORECASE,
)


class SafetyViolationDetails(BaseModel):
    """Bounded, typed diagnostic metadata for a safety violation.

    GUARANTEES:
    - Zero Dict[str, Any] or arbitrary nested JSON.
    - Zero user IDs, emails, names, or raw database records.
    - Bounded string lengths and strictly typed numeric measurements.
    """

    rule_id: Optional[str] = Field(
        default=None,
        max_length=60,
        description="Machine-readable identifier of the specific validation rule that failed",
    )
    observed_value: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Bounded snippet of the observed non-compliant value or token",
    )
    expected_bound: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Description of the expected threshold or boundary criteria",
    )
    numeric_measurement: Optional[float] = Field(
        default=None,
        description="Diagnostic numeric measurement associated with the rule check",
    )
    diagnostic_note: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Short, non-PII diagnostic annotation explaining the measurement context",
    )

    model_config = ConfigDict(extra="forbid", strict=True)

    @field_validator("rule_id", "observed_value", "expected_bound", "diagnostic_note")
    @classmethod
    def validate_no_control_chars_or_pii_keys(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        clean = v.strip()
        if not clean:
            return None
        if any(ord(c) < 32 for c in clean):
            raise ValueError("Diagnostic text cannot contain control characters or newlines.")
        match = FORBIDDEN_KEY_PATTERN.search(clean)
        if match:
            raise ValueError(
                f"Diagnostic field contains forbidden identity or sensitive key '{match.group(0)}'."
            )
        return clean


class SafetyViolation(BaseModel):
    """Domain model representing a single safety or validation violation."""

    code: SafetyViolationCode = Field(
        ...,
        description="Canonical classification code of the violation",
    )
    message: str = Field(
        ...,
        min_length=3,
        max_length=300,
        description="Clear, non-PII explanation of why the content failed validation",
    )
    field: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Target field name or content location associated with the failure",
    )
    severity: SafetySeverity = Field(
        ...,
        description="Severity classification ('critical' indicates rejection; 'warning' is non-fatal)",
    )
    details: Optional[SafetyViolationDetails] = Field(
        default=None,
        description="Optional typed and bounded diagnostic details",
    )

    model_config = ConfigDict(extra="forbid", strict=True)

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        clean = v.strip()
        if len(clean) < 3:
            raise ValueError("Violation message must be at least 3 characters.")
        if any(ord(c) < 32 for c in clean):
            raise ValueError("Violation message cannot contain control characters or newlines.")
        match = FORBIDDEN_KEY_PATTERN.search(clean)
        if match:
            raise ValueError(
                f"Violation message contains forbidden identity key '{match.group(0)}'."
            )
        return clean

    @field_validator("field")
    @classmethod
    def validate_field(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        clean = v.strip()
        if not clean:
            return None
        if any(ord(c) < 32 for c in clean):
            raise ValueError("Field path cannot contain control characters or newlines.")
        return clean


class SafetyValidationReport(BaseModel):
    """Structured inspection report summarizing GenAI safety and output validation results.

    CRITICAL BOUNDARIES:
    - Zero sanitized_content field (no silent mutations of untrusted content).
    - Zero raw provider response payloads.
    - Preserves canonical challenge type and concrete difficulty tier.
    """

    is_safe: bool = Field(
        ...,
        description="Whether the generated content passed all critical validation checks",
    )
    challenge_type: CanonicalChallengeType = Field(
        ...,
        description="Authoritative canonical challenge type requested",
    )
    difficulty_level: CanonicalDifficultyLevel = Field(
        ...,
        description="Authoritative concrete difficulty tier requested ('easy', 'medium', 'hard')",
    )
    violations: List[SafetyViolation] = Field(
        default_factory=list,
        max_length=50,
        description="List of observed safety and validation violations",
    )
    checked_rules: List[str] = Field(
        default_factory=list,
        max_length=50,
        description="Identifiers of all safety and validation rules executed during inspection",
    )

    model_config = ConfigDict(extra="forbid", strict=True)

    @field_validator("checked_rules")
    @classmethod
    def validate_checked_rules(cls, rules: List[str]) -> List[str]:
        if len(rules) > 50:
            raise ValueError("checked_rules list cannot exceed 50 items.")
        validated: List[str] = []
        for rule in rules:
            if not isinstance(rule, str):
                raise ValueError("Each checked rule must be a string identifier.")
            clean = rule.strip()
            if not clean:
                raise ValueError("Rule identifier cannot be empty or whitespace.")
            if len(clean) > 60:
                raise ValueError(f"Rule identifier '{clean[:20]}...' exceeds 60 characters.")
            if any(ord(c) < 32 for c in clean):
                raise ValueError("Rule identifier cannot contain control characters.")
            validated.append(clean)
        return validated


class FallbackReason(str, Enum):
    """Categorical reasons triggering deterministic fallback to procedural challenges."""

    VALIDATION_FAILED = "validation_failed"
    PROVIDER_TIMEOUT = "provider_timeout"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    RATE_LIMITED = "rate_limited"
    LATENCY_EXCEEDED = "latency_exceeded"
    SAFETY_VIOLATION = "safety_violation"
    MALFORMED_OUTPUT = "malformed_output"


class FallbackSource(str, Enum):
    """Supported source origins for deterministic fallback content."""

    PROCEDURAL_CATALOG = "procedural_catalog"
    ALGORITHMIC_FALLBACK = "algorithmic_fallback"


class FallbackPayloadContract(BaseModel):
    """Bounded, typed reference contract for procedural or algorithmic fallback content.

    GUARANTEES:
    - Zero Dict[str, Any] or unrestricted JSON.
    - Bounded identifier and instruction hint fields.
    - Zero database entities or PII.
    """

    fallback_identifier: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Catalog template key or algorithmic generator identifier",
    )
    instructions_hint: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Short procedural instruction hint for the challenge fallback",
    )
    parameters_tag: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Procedural parameter category or difficulty tag",
    )

    model_config = ConfigDict(extra="forbid", strict=True)

    @field_validator("fallback_identifier", "instructions_hint", "parameters_tag")
    @classmethod
    def validate_text(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        clean = v.strip()
        if not clean:
            return None
        if any(ord(c) < 32 for c in clean):
            raise ValueError("Fallback payload fields cannot contain control characters.")
        return clean


class FallbackResolution(BaseModel):
    """Auditable record of a deterministic fallback event.

    INVARIANTS:
    - preserved_type MUST ALWAYS be True.
    - preserved_difficulty MUST ALWAYS be True.
    - It is impossible for callers to claim preserved_type=False or preserved_difficulty=False.
    - challenge_type and difficulty_level remain strictly canonical and concrete.
    """

    challenge_type: CanonicalChallengeType = Field(
        ...,
        description="Canonical challenge type preserved during fallback",
    )
    difficulty_level: CanonicalDifficultyLevel = Field(
        ...,
        description="Concrete difficulty tier preserved during fallback",
    )
    fallback_reason: FallbackReason = Field(
        ...,
        description="Categorical reason triggering the fallback",
    )
    fallback_source: FallbackSource = Field(
        ...,
        description="Origin of the fallback content",
    )
    trigger_error: str = Field(
        ...,
        min_length=1,
        max_length=300,
        description="Bounded diagnostic description of the failure triggering fallback",
    )
    preserved_type: Literal[True] = Field(
        default=True,
        description="Enforced invariant: challenge type is never mutated during fallback",
    )
    preserved_difficulty: Literal[True] = Field(
        default=True,
        description="Enforced invariant: difficulty tier is never mutated during fallback",
    )
    fallback_payload: FallbackPayloadContract = Field(
        ...,
        description="Typed reference to the fallback content payload",
    )

    model_config = ConfigDict(extra="forbid", strict=True)

    @field_validator("trigger_error")
    @classmethod
    def validate_trigger_error(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("trigger_error cannot be empty or whitespace.")
        if any(ord(c) < 32 for c in clean):
            raise ValueError("trigger_error cannot contain control characters or newlines.")
        match = FORBIDDEN_KEY_PATTERN.search(clean)
        if match:
            raise ValueError(
                f"trigger_error contains forbidden identity key '{match.group(0)}'."
            )
        return clean

    @field_validator("preserved_type")
    @classmethod
    def validate_preserved_type(cls, v: bool) -> Literal[True]:
        if v is not True:
            raise ValueError(
                "preserved_type MUST ALWAYS be True. Fallback cannot mutate the canonical challenge type."
            )
        return True

    @field_validator("preserved_difficulty")
    @classmethod
    def validate_preserved_difficulty(cls, v: bool) -> Literal[True]:
        if v is not True:
            raise ValueError(
                "preserved_difficulty MUST ALWAYS be True. Fallback cannot mutate the concrete difficulty tier."
            )
        return True


class ValidationRetryPolicy(BaseModel):
    """Bounded retry and latency budget policy for GenAI content validation.

    ARCHITECTURAL CONSTRAINTS:
    - max_retries must never exceed 2 (alarm latency guarantees).
    - timeouts and budgets must be strictly positive.
    - total_latency_budget_seconds must not be smaller than timeout_per_attempt_seconds.
    - fallback_on_exhaustion MUST ALWAYS be True.
    """

    max_retries: int = Field(
        default=1,
        ge=0,
        le=2,
        description="Maximum retry attempts on validation or transient failure (strictly 0 to 2)",
    )
    timeout_per_attempt_seconds: float = Field(
        default=3.0,
        gt=0.0,
        le=30.0,
        description="Per-attempt timeout in seconds (strictly > 0)",
    )
    total_latency_budget_seconds: float = Field(
        default=6.0,
        gt=0.0,
        le=60.0,
        description="Total cumulative latency budget in seconds before forcing fallback (strictly > 0)",
    )
    fallback_on_exhaustion: Literal[True] = Field(
        default=True,
        description="Enforced invariant: always drop back to procedural fallback upon exhaustion",
    )

    model_config = ConfigDict(extra="forbid", strict=True)

    @field_validator("fallback_on_exhaustion")
    @classmethod
    def validate_fallback_on_exhaustion(cls, v: bool) -> Literal[True]:
        if v is not True:
            raise ValueError("fallback_on_exhaustion MUST ALWAYS be True.")
        return True

    @model_validator(mode="after")
    def validate_budget_gte_attempt_timeout(self) -> "ValidationRetryPolicy":
        if self.total_latency_budget_seconds < self.timeout_per_attempt_seconds:
            raise ValueError(
                f"total_latency_budget_seconds ({self.total_latency_budget_seconds}) cannot be "
                f"smaller than timeout_per_attempt_seconds ({self.timeout_per_attempt_seconds})."
            )
        return self
