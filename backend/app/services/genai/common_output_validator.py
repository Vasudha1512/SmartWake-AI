"""Common Output Validation Boundary for GenAI Challenge Content (Phase 4.6.2).

Implements the common, challenge-type-agnostic safety validation boundary that sits
conceptually between untrusted GenAI provider output and downstream domain validators.

CORE ARCHITECTURAL PRINCIPLES:
1. Provider is UNTRUSTED: Generated type, difficulty, instructions, and fields are never authoritative.
   Expected canonical challenge_type and concrete difficulty_level originate strictly from application context.
2. Pure In-Memory Validation: No database access, no network calls, no LLM provider calls, no side-effects.
3. No Silent Sanitization: Malformed, mutated, injected, or harmful content is strictly REJECTED (is_safe=False),
   never silently mutated, truncated, or rewritten.
4. Determinism: Equivalent expected context and generated output produce bitwise/model-identical reports.
5. Privacy by Construction: Zero PII, zero database IDs, zero ORM objects, zero generic Dict[str, Any].
"""
from typing import List, Mapping, Optional, Sequence, Set
from pydantic import BaseModel
import re

from backend.app.schemas.challenge_content_schemas import FORBIDDEN_CONTEXT_KEYS
from backend.app.schemas.challenge_safety_schemas import (
    SafetySeverity,
    SafetyValidationReport,
    SafetyViolation,
    SafetyViolationCode,
    SafetyViolationDetails,
)
from backend.app.schemas.personalization_content_schemas import (
    CanonicalChallengeType,
    CanonicalDifficultyLevel,
    VALID_CANONICAL_CHALLENGE_TYPES,
    VALID_CANONICAL_DIFFICULTIES,
)

# Rule Identifiers recorded in SafetyValidationReport.checked_rules
RULE_STRUCTURAL_SANITY = "RULE_STRUCTURAL_SANITY"
RULE_TYPE_IMMUTABILITY = "RULE_TYPE_IMMUTABILITY"
RULE_DIFFICULTY_IMMUTABILITY = "RULE_DIFFICULTY_IMMUTABILITY"
RULE_TITLE_BOUNDS = "RULE_TITLE_BOUNDS"
RULE_INSTRUCTION_BOUNDS = "RULE_INSTRUCTION_BOUNDS"
RULE_CONTROL_CHARACTER_DEFENSE = "RULE_CONTROL_CHARACTER_DEFENSE"
RULE_PROMPT_INJECTION_GUARD = "RULE_PROMPT_INJECTION_GUARD"
RULE_HARMFUL_CONTENT_GUARD = "RULE_HARMFUL_CONTENT_GUARD"

ALL_COMMON_RULES: List[str] = [
    RULE_STRUCTURAL_SANITY,
    RULE_TYPE_IMMUTABILITY,
    RULE_DIFFICULTY_IMMUTABILITY,
    RULE_TITLE_BOUNDS,
    RULE_INSTRUCTION_BOUNDS,
    RULE_CONTROL_CHARACTER_DEFENSE,
    RULE_PROMPT_INJECTION_GUARD,
    RULE_HARMFUL_CONTENT_GUARD,
]

# Conservative text length bounds
MIN_TITLE_LENGTH = 1
MAX_TITLE_LENGTH = 200
MIN_INSTRUCTIONS_LENGTH = 1
MAX_INSTRUCTIONS_LENGTH = 1000

# Deterministic prompt injection pattern set (Section 6.F)
PROMPT_INJECTION_PATTERNS: List[re.Pattern[str]] = [
    re.compile(r"\bignore\s+(all\s+)?previous\s+instructions\b", re.IGNORECASE),
    re.compile(r"\bdisregard\s+(all\s+)?(system|previous)\s+instructions\b", re.IGNORECASE),
    re.compile(r"\boverride\s+(system\s+rules|application\s+rules)\b", re.IGNORECASE),
    re.compile(r"\breveal\s+(the\s+)?(system\s+prompt|hidden\s+instructions)\b", re.IGNORECASE),
    re.compile(r"\bact\s+as\s+(the\s+)?system\b", re.IGNORECASE),
    re.compile(r"\bdeveloper\s+message\b", re.IGNORECASE),
    re.compile(r"\bsystem\s+message\b", re.IGNORECASE),
    re.compile(r"\bjailbreak(-style)?\s+instruction\b", re.IGNORECASE),
    re.compile(r"\bfollow\s+these\s+new\s+instructions\s+instead\b", re.IGNORECASE),
    re.compile(r"\bdo\s+not\s+follow\s+the\s+application\s+rules\b", re.IGNORECASE),
]

# Deterministic baseline harmful content pattern set (Section 6.G)
HARMFUL_CONTENT_PATTERNS: List[re.Pattern[str]] = [
    # Self-harm
    re.compile(r"\b(kill|harm|cut|hurt|injure)\s+yourself\b", re.IGNORECASE),
    re.compile(r"\bcommit\s+suicide\b", re.IGNORECASE),
    re.compile(r"\bend\s+your\s+life\b", re.IGNORECASE),
    # Violence towards others
    re.compile(
        r"\b(attack|assault|stab|shoot|poison)\s+(someone|others|people|anybody|a\s+person)\b",
        re.IGNORECASE,
    ),
    # Dangerous physical actions for wake-up challenge
    re.compile(r"\b(jump|leap)\s+(from|off)\s+(the\s+)?(roof|balcony|window|bridge)\b", re.IGNORECASE),
    re.compile(r"\bswallow\s+(bleach|poison|pills|chemicals|glass)\b", re.IGNORECASE),
    re.compile(r"\bhold\s+your\s+breath\s+until\s+you\s+pass\s+out\b", re.IGNORECASE),
    re.compile(r"\belectrocute\s+yourself\b", re.IGNORECASE),
    re.compile(r"\bset\s+(yourself|your\s+(room|bed|house))\s+on\s+fire\b", re.IGNORECASE),
]

# Sensitive key redaction pattern for diagnostic text
REDACTION_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in sorted(FORBIDDEN_CONTEXT_KEYS)) + r")\b",
    re.IGNORECASE,
)


def _sanitize_diagnostic_snippet(snippet: str) -> str:
    """Sanitize raw match snippets to prevent PII/identity keys from entering diagnostic details."""
    cleaned = REDACTION_PATTERN.sub("[REDACTED]", snippet).strip()
    return re.sub(r"[\x00-\x1f\x7f]", " ", cleaned)[:100]


def _has_dangerous_control_characters(text: str) -> bool:
    """Check whether text contains non-printing or dangerous control characters."""
    return any((ord(c) < 32 and c not in ("\t", "\n", "\r")) or ord(c) == 127 for c in text)


def _extract_field(obj: object, field_name: str) -> Optional[object]:
    """Safely extract a field value from a Mapping or BaseModel."""
    if isinstance(obj, Mapping):
        return obj.get(field_name)
    return getattr(obj, field_name, None)


class CommonOutputValidator:
    """Pure in-memory common safety validation boundary for generated challenge content."""

    @classmethod
    def validate(
        cls,
        expected_type: CanonicalChallengeType,
        expected_difficulty: CanonicalDifficultyLevel,
        generated_output: object,
    ) -> SafetyValidationReport:
        """Validate untrusted generated output against application-authoritative expected parameters.

        Args:
            expected_type: Application-authoritative canonical challenge type ('dance', 'math',
                           'memory', 'tongue_twister', 'push_ups').
            expected_difficulty: Application-authoritative concrete difficulty tier ('easy', 'medium', 'hard').
            generated_output: Untrusted raw generated output (Mapping, BaseModel, or arbitrary object).

        Returns:
            SafetyValidationReport: Fully populated safety report containing pass/fail verdict,
                                   violations, and executed rule identifiers.
        """
        # Validate application context arguments
        if expected_type not in VALID_CANONICAL_CHALLENGE_TYPES:
            raise ValueError(
                f"Invalid expected challenge_type '{expected_type}'. "
                f"Must be one of: {sorted(list(VALID_CANONICAL_CHALLENGE_TYPES))}."
            )
        if expected_difficulty not in VALID_CANONICAL_DIFFICULTIES:
            raise ValueError(
                f"Invalid expected difficulty_level '{expected_difficulty}'. "
                f"Must be one of: {sorted(list(VALID_CANONICAL_DIFFICULTIES))}."
            )

        violations: List[SafetyViolation] = []
        checked_rules: List[str] = []

        # ------------------------------------------------------------------
        # RULE A: STRUCTURAL / SCHEMA SANITY (Top-level inspection)
        # ------------------------------------------------------------------
        checked_rules.append(RULE_STRUCTURAL_SANITY)

        if generated_output is None:
            violations.append(
                SafetyViolation(
                    code=SafetyViolationCode.SCHEMA_MALFORMED,
                    message="Generated output is None; expected structured challenge content.",
                    field=None,
                    severity=SafetySeverity.CRITICAL,
                    details=SafetyViolationDetails(
                        rule_id=RULE_STRUCTURAL_SANITY,
                        diagnostic_note="Encountered null or None generated output.",
                    ),
                )
            )
            return SafetyValidationReport(
                is_safe=False,
                challenge_type=expected_type,
                difficulty_level=expected_difficulty,
                violations=violations,
                checked_rules=checked_rules,
            )

        if not isinstance(generated_output, (Mapping, BaseModel)):
            violations.append(
                SafetyViolation(
                    code=SafetyViolationCode.SCHEMA_MALFORMED,
                    message=(
                        f"Generated output must be a structured object or dictionary, "
                        f"got {type(generated_output).__name__}."
                    ),
                    field=None,
                    severity=SafetySeverity.CRITICAL,
                    details=SafetyViolationDetails(
                        rule_id=RULE_STRUCTURAL_SANITY,
                        observed_value=type(generated_output).__name__[:100],
                        diagnostic_note="Top-level output structure is not a mapping or BaseModel.",
                    ),
                )
            )
            return SafetyValidationReport(
                is_safe=False,
                challenge_type=expected_type,
                difficulty_level=expected_difficulty,
                violations=violations,
                checked_rules=checked_rules,
            )

        # Extract core fields
        raw_type = _extract_field(generated_output, "challenge_type")
        raw_diff = _extract_field(generated_output, "difficulty_level")
        raw_title = _extract_field(generated_output, "title")
        raw_instructions = _extract_field(generated_output, "instructions")
        if raw_instructions is None:
            # Fallback to 'description' if instructions not present
            raw_instructions = _extract_field(generated_output, "description")

        raw_payload = _extract_field(generated_output, "content_payload")
        if raw_payload is None:
            raw_payload = _extract_field(generated_output, "generated_content")
        if raw_payload is None:
            raw_payload = _extract_field(generated_output, "content")

        # Verify missing common fields
        if raw_type is None:
            violations.append(
                SafetyViolation(
                    code=SafetyViolationCode.SCHEMA_MALFORMED,
                    message="Missing required field 'challenge_type' in generated output.",
                    field="challenge_type",
                    severity=SafetySeverity.CRITICAL,
                    details=SafetyViolationDetails(
                        rule_id=RULE_STRUCTURAL_SANITY,
                        diagnostic_note="Missing required key 'challenge_type'.",
                    ),
                )
            )

        if raw_diff is None:
            violations.append(
                SafetyViolation(
                    code=SafetyViolationCode.SCHEMA_MALFORMED,
                    message="Missing required field 'difficulty_level' in generated output.",
                    field="difficulty_level",
                    severity=SafetySeverity.CRITICAL,
                    details=SafetyViolationDetails(
                        rule_id=RULE_STRUCTURAL_SANITY,
                        diagnostic_note="Missing required key 'difficulty_level'.",
                    ),
                )
            )

        if raw_title is None:
            violations.append(
                SafetyViolation(
                    code=SafetyViolationCode.SCHEMA_MALFORMED,
                    message="Missing required field 'title' in generated output.",
                    field="title",
                    severity=SafetySeverity.CRITICAL,
                    details=SafetyViolationDetails(
                        rule_id=RULE_STRUCTURAL_SANITY,
                        diagnostic_note="Missing required key 'title'.",
                    ),
                )
            )

        if raw_instructions is None:
            violations.append(
                SafetyViolation(
                    code=SafetyViolationCode.SCHEMA_MALFORMED,
                    message="Missing required field 'instructions' in generated output.",
                    field="instructions",
                    severity=SafetySeverity.CRITICAL,
                    details=SafetyViolationDetails(
                        rule_id=RULE_STRUCTURAL_SANITY,
                        diagnostic_note="Missing required key 'instructions'.",
                    ),
                )
            )

        if raw_payload is None:
            violations.append(
                SafetyViolation(
                    code=SafetyViolationCode.SCHEMA_MALFORMED,
                    message="Missing required challenge payload structure in generated output.",
                    field="content_payload",
                    severity=SafetySeverity.CRITICAL,
                    details=SafetyViolationDetails(
                        rule_id=RULE_STRUCTURAL_SANITY,
                        diagnostic_note="Missing required content payload structure.",
                    ),
                )
            )

        # Verify field data types
        if raw_type is not None and not isinstance(raw_type, str):
            violations.append(
                SafetyViolation(
                    code=SafetyViolationCode.SCHEMA_MALFORMED,
                    message=f"Field 'challenge_type' must be a string, got {type(raw_type).__name__}.",
                    field="challenge_type",
                    severity=SafetySeverity.CRITICAL,
                    details=SafetyViolationDetails(
                        rule_id=RULE_STRUCTURAL_SANITY,
                        observed_value=type(raw_type).__name__[:100],
                        diagnostic_note="Invalid field type for challenge_type.",
                    ),
                )
            )

        if raw_diff is not None and not isinstance(raw_diff, str):
            violations.append(
                SafetyViolation(
                    code=SafetyViolationCode.SCHEMA_MALFORMED,
                    message=f"Field 'difficulty_level' must be a string, got {type(raw_diff).__name__}.",
                    field="difficulty_level",
                    severity=SafetySeverity.CRITICAL,
                    details=SafetyViolationDetails(
                        rule_id=RULE_STRUCTURAL_SANITY,
                        observed_value=type(raw_diff).__name__[:100],
                        diagnostic_note="Invalid field type for difficulty_level.",
                    ),
                )
            )

        if raw_title is not None and not isinstance(raw_title, str):
            violations.append(
                SafetyViolation(
                    code=SafetyViolationCode.SCHEMA_MALFORMED,
                    message=f"Field 'title' must be a string, got {type(raw_title).__name__}.",
                    field="title",
                    severity=SafetySeverity.CRITICAL,
                    details=SafetyViolationDetails(
                        rule_id=RULE_STRUCTURAL_SANITY,
                        observed_value=type(raw_title).__name__[:100],
                        diagnostic_note="Invalid field type for title.",
                    ),
                )
            )

        if raw_instructions is not None and not isinstance(raw_instructions, str):
            violations.append(
                SafetyViolation(
                    code=SafetyViolationCode.SCHEMA_MALFORMED,
                    message=f"Field 'instructions' must be a string, got {type(raw_instructions).__name__}.",
                    field="instructions",
                    severity=SafetySeverity.CRITICAL,
                    details=SafetyViolationDetails(
                        rule_id=RULE_STRUCTURAL_SANITY,
                        observed_value=type(raw_instructions).__name__[:100],
                        diagnostic_note="Invalid field type for instructions.",
                    ),
                )
            )

        # ------------------------------------------------------------------
        # RULE B: CHALLENGE TYPE IMMUTABILITY
        # ------------------------------------------------------------------
        checked_rules.append(RULE_TYPE_IMMUTABILITY)
        if isinstance(raw_type, str):
            clean_gen_type = raw_type.strip().lower()
            if clean_gen_type != expected_type:
                violations.append(
                    SafetyViolation(
                        code=SafetyViolationCode.TYPE_MUTATION,
                        message=(
                            f"Challenge type mutation detected: requested '{expected_type}', "
                            f"but generated content specified '{clean_gen_type}'."
                        ),
                        field="challenge_type",
                        severity=SafetySeverity.CRITICAL,
                        details=SafetyViolationDetails(
                            rule_id=RULE_TYPE_IMMUTABILITY,
                            observed_value=clean_gen_type[:100],
                            expected_bound=expected_type,
                            diagnostic_note="Provider attempted to change the authoritative challenge type.",
                        ),
                    )
                )
            elif clean_gen_type not in VALID_CANONICAL_CHALLENGE_TYPES:
                violations.append(
                    SafetyViolation(
                        code=SafetyViolationCode.TYPE_MUTATION,
                        message=f"Generated challenge type '{clean_gen_type}' is not a valid canonical type.",
                        field="challenge_type",
                        severity=SafetySeverity.CRITICAL,
                        details=SafetyViolationDetails(
                            rule_id=RULE_TYPE_IMMUTABILITY,
                            observed_value=clean_gen_type[:100],
                            diagnostic_note="Generated challenge type is unknown or invalid.",
                        ),
                    )
                )

        # ------------------------------------------------------------------
        # RULE C: DIFFICULTY IMMUTABILITY
        # ------------------------------------------------------------------
        checked_rules.append(RULE_DIFFICULTY_IMMUTABILITY)
        if isinstance(raw_diff, str):
            clean_gen_diff = raw_diff.strip().lower()
            if clean_gen_diff == "adaptive":
                violations.append(
                    SafetyViolation(
                        code=SafetyViolationCode.DIFFICULTY_MUTATION,
                        message=(
                            "Generated difficulty level cannot be 'adaptive'. "
                            f"Must match authoritative concrete difficulty '{expected_difficulty}'."
                        ),
                        field="difficulty_level",
                        severity=SafetySeverity.CRITICAL,
                        details=SafetyViolationDetails(
                            rule_id=RULE_DIFFICULTY_IMMUTABILITY,
                            observed_value="adaptive",
                            expected_bound=expected_difficulty,
                            diagnostic_note="Adaptive is not a concrete generated difficulty tier.",
                        ),
                    )
                )
            elif clean_gen_diff != expected_difficulty:
                violations.append(
                    SafetyViolation(
                        code=SafetyViolationCode.DIFFICULTY_MUTATION,
                        message=(
                            f"Difficulty level mutation detected: requested '{expected_difficulty}', "
                            f"but generated content specified '{clean_gen_diff}'."
                        ),
                        field="difficulty_level",
                        severity=SafetySeverity.CRITICAL,
                        details=SafetyViolationDetails(
                            rule_id=RULE_DIFFICULTY_IMMUTABILITY,
                            observed_value=clean_gen_diff[:100],
                            expected_bound=expected_difficulty,
                            diagnostic_note="Provider attempted to change the authoritative difficulty tier.",
                        ),
                    )
                )
            elif clean_gen_diff not in VALID_CANONICAL_DIFFICULTIES:
                violations.append(
                    SafetyViolation(
                        code=SafetyViolationCode.DIFFICULTY_MUTATION,
                        message=f"Generated difficulty '{clean_gen_diff}' is not a valid concrete difficulty.",
                        field="difficulty_level",
                        severity=SafetySeverity.CRITICAL,
                        details=SafetyViolationDetails(
                            rule_id=RULE_DIFFICULTY_IMMUTABILITY,
                            observed_value=clean_gen_diff[:100],
                            diagnostic_note="Difficulty value is outside standard concrete tiers.",
                        ),
                    )
                )

        # ------------------------------------------------------------------
        # RULE D: TITLE & INSTRUCTION BOUNDS
        # ------------------------------------------------------------------
        checked_rules.append(RULE_TITLE_BOUNDS)
        if isinstance(raw_title, str):
            clean_title = raw_title.strip()
            if len(clean_title) < MIN_TITLE_LENGTH:
                violations.append(
                    SafetyViolation(
                        code=SafetyViolationCode.SCHEMA_MALFORMED,
                        message="Challenge title cannot be empty or whitespace.",
                        field="title",
                        severity=SafetySeverity.CRITICAL,
                        details=SafetyViolationDetails(
                            rule_id=RULE_TITLE_BOUNDS,
                            numeric_measurement=float(len(clean_title)),
                            expected_bound=f">= {MIN_TITLE_LENGTH}",
                            diagnostic_note="Empty or whitespace title.",
                        ),
                    )
                )
            elif len(clean_title) > MAX_TITLE_LENGTH:
                violations.append(
                    SafetyViolation(
                        code=SafetyViolationCode.SCHEMA_MALFORMED,
                        message=(
                            f"Challenge title length ({len(clean_title)}) exceeds "
                            f"maximum allowed limit ({MAX_TITLE_LENGTH})."
                        ),
                        field="title",
                        severity=SafetySeverity.CRITICAL,
                        details=SafetyViolationDetails(
                            rule_id=RULE_TITLE_BOUNDS,
                            numeric_measurement=float(len(clean_title)),
                            expected_bound=f"<= {MAX_TITLE_LENGTH}",
                            diagnostic_note="Title exceeded maximum length limit.",
                        ),
                    )
                )

        checked_rules.append(RULE_INSTRUCTION_BOUNDS)
        if isinstance(raw_instructions, str):
            clean_inst = raw_instructions.strip()
            if len(clean_inst) < MIN_INSTRUCTIONS_LENGTH:
                violations.append(
                    SafetyViolation(
                        code=SafetyViolationCode.SCHEMA_MALFORMED,
                        message="Challenge instructions cannot be empty or whitespace.",
                        field="instructions",
                        severity=SafetySeverity.CRITICAL,
                        details=SafetyViolationDetails(
                            rule_id=RULE_INSTRUCTION_BOUNDS,
                            numeric_measurement=float(len(clean_inst)),
                            expected_bound=f">= {MIN_INSTRUCTIONS_LENGTH}",
                            diagnostic_note="Empty or whitespace instructions.",
                        ),
                    )
                )
            elif len(clean_inst) > MAX_INSTRUCTIONS_LENGTH:
                violations.append(
                    SafetyViolation(
                        code=SafetyViolationCode.SCHEMA_MALFORMED,
                        message=(
                            f"Challenge instructions length ({len(clean_inst)}) exceeds "
                            f"maximum allowed limit ({MAX_INSTRUCTIONS_LENGTH})."
                        ),
                        field="instructions",
                        severity=SafetySeverity.CRITICAL,
                        details=SafetyViolationDetails(
                            rule_id=RULE_INSTRUCTION_BOUNDS,
                            numeric_measurement=float(len(clean_inst)),
                            expected_bound=f"<= {MAX_INSTRUCTIONS_LENGTH}",
                            diagnostic_note="Instructions exceeded maximum length limit.",
                        ),
                    )
                )

        # ------------------------------------------------------------------
        # RULE E: CONTROL CHARACTER DEFENSE
        # ------------------------------------------------------------------
        checked_rules.append(RULE_CONTROL_CHARACTER_DEFENSE)
        if isinstance(raw_title, str) and _has_dangerous_control_characters(raw_title):
            violations.append(
                SafetyViolation(
                    code=SafetyViolationCode.SCHEMA_MALFORMED,
                    message="Field 'title' contains prohibited non-printing control characters.",
                    field="title",
                    severity=SafetySeverity.CRITICAL,
                    details=SafetyViolationDetails(
                        rule_id=RULE_CONTROL_CHARACTER_DEFENSE,
                        diagnostic_note="Detected control characters in title field.",
                    ),
                )
            )

        if isinstance(raw_instructions, str) and _has_dangerous_control_characters(raw_instructions):
            violations.append(
                SafetyViolation(
                    code=SafetyViolationCode.SCHEMA_MALFORMED,
                    message="Field 'instructions' contains prohibited non-printing control characters.",
                    field="instructions",
                    severity=SafetySeverity.CRITICAL,
                    details=SafetyViolationDetails(
                        rule_id=RULE_CONTROL_CHARACTER_DEFENSE,
                        diagnostic_note="Detected control characters in instructions field.",
                    ),
                )
            )

        # ------------------------------------------------------------------
        # Collect visible text targets for Injection and Harmful Content scan
        # ------------------------------------------------------------------
        text_targets: List[tuple[str, str]] = []
        if isinstance(raw_title, str):
            text_targets.append(("title", raw_title))
        if isinstance(raw_instructions, str):
            text_targets.append(("instructions", raw_instructions))

        # ------------------------------------------------------------------
        # RULE F: PROMPT-INJECTION GUARD (Deterministic baseline)
        # ------------------------------------------------------------------
        checked_rules.append(RULE_PROMPT_INJECTION_GUARD)
        for field_name, text_value in text_targets:
            for pattern in PROMPT_INJECTION_PATTERNS:
                match = pattern.search(text_value)
                if match:
                    snippet = _sanitize_diagnostic_snippet(match.group(0))
                    violations.append(
                        SafetyViolation(
                            code=SafetyViolationCode.PROMPT_INJECTION,
                            message=f"Prompt injection pattern detected in field '{field_name}'.",
                            field=field_name,
                            severity=SafetySeverity.CRITICAL,
                            details=SafetyViolationDetails(
                                rule_id=RULE_PROMPT_INJECTION_GUARD,
                                observed_value=snippet,
                                diagnostic_note="Deterministic instruction-override marker matched.",
                            ),
                        )
                    )
                    break  # One injection report per field is sufficient

        # ------------------------------------------------------------------
        # RULE G: HARMFUL CONTENT GUARD (Deterministic baseline)
        # ------------------------------------------------------------------
        checked_rules.append(RULE_HARMFUL_CONTENT_GUARD)
        for field_name, text_value in text_targets:
            for pattern in HARMFUL_CONTENT_PATTERNS:
                match = pattern.search(text_value)
                if match:
                    snippet = _sanitize_diagnostic_snippet(match.group(0))
                    violations.append(
                        SafetyViolation(
                            code=SafetyViolationCode.HARMFUL_CONTENT,
                            message=f"Harmful or unsafe content detected in field '{field_name}'.",
                            field=field_name,
                            severity=SafetySeverity.CRITICAL,
                            details=SafetyViolationDetails(
                                rule_id=RULE_HARMFUL_CONTENT_GUARD,
                                observed_value=snippet,
                                diagnostic_note="Deterministic unsafe instruction marker matched.",
                            ),
                        )
                    )
                    break  # One harmful report per field is sufficient

        # ------------------------------------------------------------------
        # REPORT ASSEMBLY (is_safe requires zero CRITICAL violations)
        # ------------------------------------------------------------------
        has_critical = any(v.severity == SafetySeverity.CRITICAL for v in violations)
        is_safe = not has_critical

        return SafetyValidationReport(
            is_safe=is_safe,
            challenge_type=expected_type,
            difficulty_level=expected_difficulty,
            violations=violations,
            checked_rules=checked_rules,
        )


def validate_common_output(
    expected_type: CanonicalChallengeType,
    expected_difficulty: CanonicalDifficultyLevel,
    generated_output: object,
) -> SafetyValidationReport:
    """Convenience functional interface for CommonOutputValidator.validate."""
    return CommonOutputValidator.validate(expected_type, expected_difficulty, generated_output)
