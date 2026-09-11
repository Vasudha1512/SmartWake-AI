"""Domain-Specific Safety Validation Boundary for SmartWake AI (Phase 4.6.3 - 4.6.6).

Applies domain-specific safety and constraint validation across canonical challenge types:
1. Math: Expression solvability, non-zero divisor, integer division, numeric bounds, answer derivation.
2. Memory: Non-empty sequence, mode preservation, strict non-numeric rule (no number guessing), matrix bounds.
3. Tongue Twister: Non-empty passage, non-numeric rule, word count limits, sound/alliteration density.
4. Procedural Physical (Dance & Push-ups): Safe repetition bounds, cadence, and duration limits.

PIPELINE ORDER:
1. Common output validation (via CommonOutputValidator)
2. Domain-specific safety validation (this module)
3. Final aggregated SafetyValidationReport

CRITICAL INVARIANTS:
- No silent sanitization: invalid content is strictly rejected (is_safe=False).
- Pure in-memory service: zero DB, zero network, zero LLM calls, zero Dict[str, Any].
- Reuses existing domain constraint resolvers and validators without duplicating logic.
"""
import re
from typing import List, Mapping, Optional, Sequence, Set, Tuple
from pydantic import BaseModel

from backend.app.core.exceptions import (
    MathEvaluationError,
    MemoryEvaluationError,
    TongueTwisterEvaluationError,
)
from backend.app.schemas.challenge_safety_schemas import (
    SafetySeverity,
    SafetyValidationReport,
    SafetyViolation,
    SafetyViolationCode,
    SafetyViolationDetails,
)
from backend.app.schemas.math_challenge_schemas import MathQuestionItem
from backend.app.schemas.memory_challenge_schemas import (
    VALID_RECALL_MODES,
    MemoryChallengePayload,
)

VALID_PALETTE_THEMES: Set[str] = {
    "colors",
    "geometric_shapes",
    "cardinal_directions",
    "emojis",
}
from backend.app.schemas.personalization_content_schemas import (
    CanonicalChallengeType,
    CanonicalDifficultyLevel,
)
from backend.app.schemas.tongue_twister_challenge_schemas import (
    SUPPORTED_TONGUE_TWISTER_LANGUAGES,
    TongueTwisterChallengePayload,
)
from backend.app.services.genai.common_output_validator import (
    CommonOutputValidator,
    _extract_field,
)
from backend.app.services.genai.math_answer_validator import (
    MathAnswerValidator,
    SafeArithmeticEvaluator,
)
from backend.app.services.genai.math_generation_constraints import (
    get_math_difficulty_constraints,
)
from backend.app.services.genai.memory_answer_validator import (
    MemoryAnswerValidator,
    NUMERIC_ITEM_REGEX,
)
from backend.app.services.genai.memory_generation_constraints import (
    get_memory_difficulty_constraints,
)
from backend.app.services.genai.tongue_twister_answer_validator import (
    TongueTwisterAnswerValidator,
)
from backend.app.services.genai.tongue_twister_generation_constraints import (
    get_tongue_twister_difficulty_constraints,
)

# Domain Rule Identifiers
RULE_MATH_SAFETY_VALIDATION = "RULE_MATH_SAFETY_VALIDATION"
RULE_MEMORY_SAFETY_VALIDATION = "RULE_MEMORY_SAFETY_VALIDATION"
RULE_TONGUE_TWISTER_SAFETY_VALIDATION = "RULE_TONGUE_TWISTER_SAFETY_VALIDATION"
RULE_PHYSICAL_SAFETY_VALIDATION = "RULE_PHYSICAL_SAFETY_VALIDATION"

# Physical Exertion Safety Bounds for morning wake-up
DANCE_MIN_STEPS = 2
DANCE_MAX_STEPS = 30
DANCE_MIN_DURATION_SECONDS = 10
DANCE_MAX_DURATION_SECONDS = 120
DANCE_MIN_TEMPO_BPM = 60
DANCE_MAX_TEMPO_BPM = 180

PUSH_UP_MIN_REPS = 3
PUSH_UP_MAX_REPS_TIERS = {
    "easy": 15,
    "medium": 30,
    "hard": 50,
}
PUSH_UP_MIN_WINDOW_SECONDS = 15
PUSH_UP_MAX_WINDOW_SECONDS = 180


class DomainSafetyValidator:
    """Pure in-memory safety validator applying domain-specific challenge constraints."""

    @classmethod
    def validate_math(
        cls,
        expected_difficulty: CanonicalDifficultyLevel,
        generated_output: object,
        report: SafetyValidationReport,
    ) -> None:
        """Validate mathematical safety rules (solvability, division by zero, overflow, answer derivation)."""
        report.checked_rules.append(RULE_MATH_SAFETY_VALIDATION)
        payload = _extract_field(generated_output, "content_payload")
        if payload is None:
            payload = _extract_field(generated_output, "generated_content")

        if not isinstance(payload, (Mapping, BaseModel)):
            report.violations.append(
                SafetyViolation(
                    code=SafetyViolationCode.SCHEMA_MALFORMED,
                    message="Math challenge missing structured content payload.",
                    field="content_payload",
                    severity=SafetySeverity.CRITICAL,
                    details=SafetyViolationDetails(
                        rule_id=RULE_MATH_SAFETY_VALIDATION,
                        diagnostic_note="Missing or non-object content_payload for math challenge.",
                    ),
                )
            )
            report.is_safe = False
            return

        constraints = get_math_difficulty_constraints(expected_difficulty)

        # Extract expression or questions list
        expression = _extract_field(payload, "expression")
        questions = _extract_field(payload, "questions")

        # Single expression validation
        if expression is not None and isinstance(expression, str):
            clean_expr = expression.strip()
            # Fast-check for division by zero
            if re.search(r"/\s*0+(\.0+)?(?!\d)", clean_expr):
                report.violations.append(
                    SafetyViolation(
                        code=SafetyViolationCode.MATH_DIVISION_BY_ZERO,
                        message=f"Math expression contains division by zero: '{clean_expr}'.",
                        field="content_payload.expression",
                        severity=SafetySeverity.CRITICAL,
                        details=SafetyViolationDetails(
                            rule_id=RULE_MATH_SAFETY_VALIDATION,
                            observed_value=clean_expr[:100],
                            diagnostic_note="Division by zero detected in arithmetic expression.",
                        ),
                    )
                )
                report.is_safe = False
                return

            try:
                computed_ans, _, _ = SafeArithmeticEvaluator.parse_and_evaluate(
                    clean_expr, constraints
                )
            except MathEvaluationError as exc:
                err_msg = str(exc)
                code = SafetyViolationCode.MATH_UNSOLVABLE
                if "division by zero" in err_msg.lower():
                    code = SafetyViolationCode.MATH_DIVISION_BY_ZERO
                elif "exceeds" in err_msg.lower() or "overflow" in err_msg.lower():
                    code = SafetyViolationCode.MATH_PRECISION_OVERFLOW

                report.violations.append(
                    SafetyViolation(
                        code=code,
                        message=f"Math evaluation safety failure: {err_msg}",
                        field="content_payload.expression",
                        severity=SafetySeverity.CRITICAL,
                        details=SafetyViolationDetails(
                            rule_id=RULE_MATH_SAFETY_VALIDATION,
                            observed_value=clean_expr[:100],
                            diagnostic_note=err_msg[:200],
                        ),
                    )
                )
                report.is_safe = False
                return

            # Verify declared expected answer if present
            expected_ans = _extract_field(generated_output, "expected_answer")
            if expected_ans is not None:
                if isinstance(expected_ans, (int, float, str)):
                    try:
                        exp_int = int(expected_ans)
                        if exp_int != computed_ans:
                            report.violations.append(
                                SafetyViolation(
                                    code=SafetyViolationCode.MATH_UNSOLVABLE,
                                    message=(
                                        f"Declared expected answer ({exp_int}) does not match "
                                        f"authoritative computed answer ({computed_ans})."
                                    ),
                                    field="expected_answer",
                                    severity=SafetySeverity.CRITICAL,
                                    details=SafetyViolationDetails(
                                        rule_id=RULE_MATH_SAFETY_VALIDATION,
                                        observed_value=str(exp_int),
                                        expected_bound=str(computed_ans),
                                        diagnostic_note="Answer derivation mismatch.",
                                    ),
                                )
                            )
                            report.is_safe = False
                    except (ValueError, TypeError):
                        report.violations.append(
                            SafetyViolation(
                                code=SafetyViolationCode.MATH_UNSOLVABLE,
                                message=f"Expected answer '{expected_ans}' is not a valid integer.",
                                field="expected_answer",
                                severity=SafetySeverity.CRITICAL,
                                details=SafetyViolationDetails(
                                    rule_id=RULE_MATH_SAFETY_VALIDATION,
                                    observed_value=str(expected_ans)[:50],
                                    diagnostic_note="Non-integer expected answer.",
                                ),
                            )
                        )
                        report.is_safe = False
                else:
                    report.violations.append(
                        SafetyViolation(
                            code=SafetyViolationCode.MATH_UNSOLVABLE,
                            message=f"Expected answer must be a number or numeric string, got {type(expected_ans).__name__}.",
                            field="expected_answer",
                            severity=SafetySeverity.CRITICAL,
                        )
                    )
                    report.is_safe = False

        # Multi-question validation
        elif isinstance(questions, list):
            if len(questions) == 0:
                report.violations.append(
                    SafetyViolation(
                        code=SafetyViolationCode.MATH_UNSOLVABLE,
                        message="Math challenge questions list is empty.",
                        field="content_payload.questions",
                        severity=SafetySeverity.CRITICAL,
                        details=SafetyViolationDetails(
                            rule_id=RULE_MATH_SAFETY_VALIDATION,
                            diagnostic_note="Empty questions list.",
                        ),
                    )
                )
                report.is_safe = False
                return

            for idx, q in enumerate(questions):
                q_expr = _extract_field(q, "expression") or _extract_field(q, "prompt")
                if not q_expr or not isinstance(q_expr, str):
                    report.violations.append(
                        SafetyViolation(
                            code=SafetyViolationCode.MATH_UNSOLVABLE,
                            message=f"Question [{idx}] is missing a valid expression string.",
                            field=f"content_payload.questions[{idx}]",
                            severity=SafetySeverity.CRITICAL,
                        )
                    )
                    report.is_safe = False
                    continue

                clean_q_expr = q_expr.replace("= ?", "").replace("=", "").strip()
                if re.search(r"/\s*0+(\.0+)?(?!\d)", clean_q_expr):
                    report.violations.append(
                        SafetyViolation(
                            code=SafetyViolationCode.MATH_DIVISION_BY_ZERO,
                            message=f"Question [{idx}] contains division by zero: '{clean_q_expr}'.",
                            field=f"content_payload.questions[{idx}].expression",
                            severity=SafetySeverity.CRITICAL,
                        )
                    )
                    report.is_safe = False
                    continue

                try:
                    SafeArithmeticEvaluator.parse_and_evaluate(clean_q_expr, constraints)
                except MathEvaluationError as exc:
                    report.violations.append(
                        SafetyViolation(
                            code=SafetyViolationCode.MATH_UNSOLVABLE,
                            message=f"Question [{idx}] math evaluation failure: {exc}",
                            field=f"content_payload.questions[{idx}].expression",
                            severity=SafetySeverity.CRITICAL,
                            details=SafetyViolationDetails(
                                rule_id=RULE_MATH_SAFETY_VALIDATION,
                                diagnostic_note=str(exc)[:200],
                            ),
                        )
                    )
                    report.is_safe = False
        else:
            report.violations.append(
                SafetyViolation(
                    code=SafetyViolationCode.MATH_UNSOLVABLE,
                    message="Math payload missing both 'expression' and 'questions' fields.",
                    field="content_payload",
                    severity=SafetySeverity.CRITICAL,
                    details=SafetyViolationDetails(
                        rule_id=RULE_MATH_SAFETY_VALIDATION,
                        diagnostic_note="Unsolvable math payload structure.",
                    ),
                )
            )
            report.is_safe = False

    @classmethod
    def validate_memory(
        cls,
        expected_difficulty: CanonicalDifficultyLevel,
        generated_output: object,
        report: SafetyValidationReport,
    ) -> None:
        """Validate memory safety rules (non-numeric recall only, valid palette/mode, bounded size)."""
        report.checked_rules.append(RULE_MEMORY_SAFETY_VALIDATION)
        payload = _extract_field(generated_output, "content_payload")
        if payload is None:
            payload = _extract_field(generated_output, "generated_content")

        if not isinstance(payload, (Mapping, BaseModel)):
            report.violations.append(
                SafetyViolation(
                    code=SafetyViolationCode.SCHEMA_MALFORMED,
                    message="Memory challenge missing structured content payload.",
                    field="content_payload",
                    severity=SafetySeverity.CRITICAL,
                    details=SafetyViolationDetails(
                        rule_id=RULE_MEMORY_SAFETY_VALIDATION,
                        diagnostic_note="Missing or non-object content_payload for memory challenge.",
                    ),
                )
            )
            report.is_safe = False
            return

        constraints = get_memory_difficulty_constraints(expected_difficulty)

        # 1. Mode Validation
        mode = _extract_field(payload, "mode") or _extract_field(payload, "recall_mode")
        if mode is not None and isinstance(mode, str):
            clean_mode = mode.strip().lower()
            if clean_mode not in VALID_RECALL_MODES:
                report.violations.append(
                    SafetyViolation(
                        code=SafetyViolationCode.MEMORY_INVALID_PALETTE,
                        message=f"Invalid memory recall mode '{clean_mode}'. Must be one of: {sorted(list(VALID_RECALL_MODES))}.",
                        field="content_payload.mode",
                        severity=SafetySeverity.CRITICAL,
                        details=SafetyViolationDetails(
                            rule_id=RULE_MEMORY_SAFETY_VALIDATION,
                            observed_value=clean_mode[:50],
                        ),
                    )
                )
                report.is_safe = False

        # 2. Palette Theme Validation
        palette = _extract_field(payload, "palette_theme")
        if palette is not None and isinstance(palette, str):
            clean_palette = palette.strip().lower()
            if clean_palette not in VALID_PALETTE_THEMES:
                report.violations.append(
                    SafetyViolation(
                        code=SafetyViolationCode.MEMORY_INVALID_PALETTE,
                        message=f"Invalid memory palette_theme '{clean_palette}'.",
                        field="content_payload.palette_theme",
                        severity=SafetySeverity.CRITICAL,
                    )
                )
                report.is_safe = False

        # 3. Extract items/sequence
        items = _extract_field(payload, "sequence")
        if items is None:
            items = _extract_field(payload, "display_sequence")
        if items is None:
            items = _extract_field(payload, "items")
        if items is None:
            items = _extract_field(payload, "pattern")

        if items is None or not isinstance(items, list) or len(items) == 0:
            report.violations.append(
                SafetyViolation(
                    code=SafetyViolationCode.MEMORY_EMPTY_SEQUENCE,
                    message="Memory challenge contains an empty or missing item sequence.",
                    field="content_payload.sequence",
                    severity=SafetySeverity.CRITICAL,
                    details=SafetyViolationDetails(
                        rule_id=RULE_MEMORY_SAFETY_VALIDATION,
                        diagnostic_note="Sequence length is 0 or sequence field is missing.",
                    ),
                )
            )
            report.is_safe = False
            return

        # 4. Strict Non-Numeric Rule (CRITICAL NON-NUMBER GUESSING INVARIANT)
        for idx, item in enumerate(items):
            if isinstance(item, (int, float)) and not isinstance(item, bool):
                report.violations.append(
                    SafetyViolation(
                        code=SafetyViolationCode.MEMORY_NUMERIC_LEAK,
                        message=(
                            f"Memory item [{idx}] contains a raw numeric value ({item}). "
                            "Memory challenges strictly evaluate visual/symbol recall, never number guessing."
                        ),
                        field=f"content_payload.sequence[{idx}]",
                        severity=SafetySeverity.CRITICAL,
                        details=SafetyViolationDetails(
                            rule_id=RULE_MEMORY_SAFETY_VALIDATION,
                            observed_value=str(item)[:50],
                            diagnostic_note="Numeric memory item detected; number guessing is strictly forbidden.",
                        ),
                    )
                )
                report.is_safe = False
            elif isinstance(item, str):
                if NUMERIC_ITEM_REGEX.match(item.strip()):
                    report.violations.append(
                        SafetyViolation(
                            code=SafetyViolationCode.MEMORY_NUMERIC_LEAK,
                            message=(
                                f"Memory item [{idx}] contains a numeric digit string '{item}'. "
                                "Memory challenges strictly evaluate visual/symbol recall, never number guessing."
                            ),
                            field=f"content_payload.sequence[{idx}]",
                            severity=SafetySeverity.CRITICAL,
                            details=SafetyViolationDetails(
                                rule_id=RULE_MEMORY_SAFETY_VALIDATION,
                                observed_value=item[:50],
                                diagnostic_note="Numeric digit item detected; number guessing is strictly forbidden.",
                            ),
                        )
                    )
                    report.is_safe = False

                # Scan text for number guessing phrases
                try:
                    MemoryAnswerValidator.scan_for_forbidden_numeric_concepts(item)
                except MemoryEvaluationError as exc:
                    report.violations.append(
                        SafetyViolation(
                            code=SafetyViolationCode.MEMORY_NUMERIC_LEAK,
                            message=str(exc),
                            field=f"content_payload.sequence[{idx}]",
                            severity=SafetySeverity.CRITICAL,
                            details=SafetyViolationDetails(
                                rule_id=RULE_MEMORY_SAFETY_VALIDATION,
                                diagnostic_note="Forbidden numeric concept detected in memory item.",
                            ),
                        )
                    )
                    report.is_safe = False

        # 5. Sequence length bounds
        seq_len = len(items)
        if seq_len < constraints.min_sequence_length or seq_len > constraints.max_sequence_length:
            report.violations.append(
                SafetyViolation(
                    code=SafetyViolationCode.MEMORY_INVALID_PALETTE,
                    message=(
                        f"Memory sequence length ({seq_len}) is outside tier range "
                        f"[{constraints.min_sequence_length}, {constraints.max_sequence_length}] "
                        f"for difficulty '{expected_difficulty}'."
                    ),
                    field="content_payload.sequence",
                    severity=SafetySeverity.CRITICAL,
                    details=SafetyViolationDetails(
                        rule_id=RULE_MEMORY_SAFETY_VALIDATION,
                        numeric_measurement=float(seq_len),
                        expected_bound=f"[{constraints.min_sequence_length}, {constraints.max_sequence_length}]",
                    ),
                )
            )
            report.is_safe = False

    @classmethod
    def validate_tongue_twister(
        cls,
        expected_difficulty: CanonicalDifficultyLevel,
        generated_output: object,
        report: SafetyValidationReport,
    ) -> None:
        """Validate tongue twister safety rules (non-empty passage, non-numeric, word count, alliteration)."""
        report.checked_rules.append(RULE_TONGUE_TWISTER_SAFETY_VALIDATION)
        payload = _extract_field(generated_output, "content_payload")
        if payload is None:
            payload = _extract_field(generated_output, "generated_content")

        if not isinstance(payload, (Mapping, BaseModel)):
            report.violations.append(
                SafetyViolation(
                    code=SafetyViolationCode.SCHEMA_MALFORMED,
                    message="Tongue twister challenge missing structured content payload.",
                    field="content_payload",
                    severity=SafetySeverity.CRITICAL,
                    details=SafetyViolationDetails(
                        rule_id=RULE_TONGUE_TWISTER_SAFETY_VALIDATION,
                    ),
                )
            )
            report.is_safe = False
            return

        constraints = get_tongue_twister_difficulty_constraints(expected_difficulty)

        passage = _extract_field(payload, "passage")
        if passage is None:
            passage = _extract_field(payload, "passage_text")

        if not passage or not isinstance(passage, str) or not passage.strip():
            report.violations.append(
                SafetyViolation(
                    code=SafetyViolationCode.TONGUE_TWISTER_LENGTH_BOUNDS,
                    message="Tongue twister passage is empty or whitespace.",
                    field="content_payload.passage",
                    severity=SafetySeverity.CRITICAL,
                    details=SafetyViolationDetails(
                        rule_id=RULE_TONGUE_TWISTER_SAFETY_VALIDATION,
                        diagnostic_note="Missing or empty passage text.",
                    ),
                )
            )
            report.is_safe = False
            return

        clean_passage = passage.strip()

        # Non-numeric rule on tongue twisters (digits forbidden)
        if re.search(r"\d", clean_passage):
            report.violations.append(
                SafetyViolation(
                    code=SafetyViolationCode.SCHEMA_MALFORMED,
                    message="Tongue twister passage contains numeric digits; numbers must be spelled out.",
                    field="content_payload.passage",
                    severity=SafetySeverity.CRITICAL,
                    details=SafetyViolationDetails(
                        rule_id=RULE_TONGUE_TWISTER_SAFETY_VALIDATION,
                        diagnostic_note="Digit characters detected in tongue twister.",
                    ),
                )
            )
            report.is_safe = False

        # Validate text structure and word count limits
        words = re.findall(r"\b[a-zA-Z]+(?:'[a-zA-Z]+)?\b", clean_passage)
        word_count = len(words)

        if word_count < constraints.min_word_count or word_count > constraints.max_word_count:
            report.violations.append(
                SafetyViolation(
                    code=SafetyViolationCode.TONGUE_TWISTER_LENGTH_BOUNDS,
                    message=(
                        f"Passage word count ({word_count}) is outside permitted range "
                        f"[{constraints.min_word_count}, {constraints.max_word_count}] "
                        f"for difficulty '{expected_difficulty}'."
                    ),
                    field="content_payload.passage",
                    severity=SafetySeverity.CRITICAL,
                    details=SafetyViolationDetails(
                        rule_id=RULE_TONGUE_TWISTER_SAFETY_VALIDATION,
                        numeric_measurement=float(word_count),
                        expected_bound=f"[{constraints.min_word_count}, {constraints.max_word_count}]",
                    ),
                )
            )
            report.is_safe = False

        # Alliteration / sound pattern validation via TongueTwisterAnswerValidator
        if word_count >= constraints.min_word_count:
            try:
                TongueTwisterAnswerValidator.validate_orthographic_sound_pattern(words, constraints)
            except TongueTwisterEvaluationError as exc:
                report.violations.append(
                    SafetyViolation(
                        code=SafetyViolationCode.TONGUE_TWISTER_LOW_ALLITERATION,
                        message=str(exc),
                        field="content_payload.passage",
                        severity=SafetySeverity.CRITICAL,
                        details=SafetyViolationDetails(
                            rule_id=RULE_TONGUE_TWISTER_SAFETY_VALIDATION,
                            diagnostic_note=str(exc)[:200],
                        ),
                    )
                )
                report.is_safe = False

    @classmethod
    def validate_physical(
        cls,
        expected_type: CanonicalChallengeType,
        expected_difficulty: CanonicalDifficultyLevel,
        generated_output: object,
        report: SafetyValidationReport,
    ) -> None:
        """Validate procedural physical safety rules for Dance and Push-ups."""
        report.checked_rules.append(RULE_PHYSICAL_SAFETY_VALIDATION)
        payload = _extract_field(generated_output, "content_payload")
        if payload is None:
            payload = _extract_field(generated_output, "generated_content")

        if not isinstance(payload, (Mapping, BaseModel)):
            report.violations.append(
                SafetyViolation(
                    code=SafetyViolationCode.SCHEMA_MALFORMED,
                    message=f"{expected_type} challenge missing structured content payload.",
                    field="content_payload",
                    severity=SafetySeverity.CRITICAL,
                    details=SafetyViolationDetails(
                        rule_id=RULE_PHYSICAL_SAFETY_VALIDATION,
                    ),
                )
            )
            report.is_safe = False
            return

        if expected_type == "dance":
            steps = _extract_field(payload, "steps")
            duration = _extract_field(payload, "target_duration_seconds")
            tempo = _extract_field(payload, "tempo_bpm")

            if steps is not None and isinstance(steps, list):
                if len(steps) < DANCE_MIN_STEPS or len(steps) > DANCE_MAX_STEPS:
                    report.violations.append(
                        SafetyViolation(
                            code=SafetyViolationCode.PHYSICAL_EXERTION_EXCEEDED,
                            message=f"Dance routine step count ({len(steps)}) exceeds safe physical limits [{DANCE_MIN_STEPS}, {DANCE_MAX_STEPS}].",
                            field="content_payload.steps",
                            severity=SafetySeverity.CRITICAL,
                            details=SafetyViolationDetails(
                                rule_id=RULE_PHYSICAL_SAFETY_VALIDATION,
                                numeric_measurement=float(len(steps)),
                                expected_bound=f"[{DANCE_MIN_STEPS}, {DANCE_MAX_STEPS}]",
                            ),
                        )
                    )
                    report.is_safe = False

            if duration is not None and isinstance(duration, (int, float, str)):
                try:
                    dur_val = int(duration)
                    if dur_val < DANCE_MIN_DURATION_SECONDS or dur_val > DANCE_MAX_DURATION_SECONDS:
                        report.violations.append(
                            SafetyViolation(
                                code=SafetyViolationCode.PHYSICAL_EXERTION_EXCEEDED,
                                message=f"Dance target duration ({dur_val}s) exceeds safe bounds [{DANCE_MIN_DURATION_SECONDS}, {DANCE_MAX_DURATION_SECONDS}]s.",
                                field="content_payload.target_duration_seconds",
                                severity=SafetySeverity.CRITICAL,
                            )
                        )
                        report.is_safe = False
                except (ValueError, TypeError):
                    pass

            if tempo is not None and isinstance(tempo, (int, float, str)):
                try:
                    bpm = int(tempo)
                    if bpm < DANCE_MIN_TEMPO_BPM or bpm > DANCE_MAX_TEMPO_BPM:
                        report.violations.append(
                            SafetyViolation(
                                code=SafetyViolationCode.PHYSICAL_EXERTION_EXCEEDED,
                                message=f"Dance tempo ({bpm} BPM) exceeds safe morning wake-up pacing [{DANCE_MIN_TEMPO_BPM}, {DANCE_MAX_TEMPO_BPM}] BPM.",
                                field="content_payload.tempo_bpm",
                                severity=SafetySeverity.CRITICAL,
                            )
                        )
                        report.is_safe = False
                except (ValueError, TypeError):
                    pass

        elif expected_type == "push_ups":
            target_reps = _extract_field(payload, "target_repetitions")
            window_sec = _extract_field(payload, "completion_window_seconds")
            max_allowed = PUSH_UP_MAX_REPS_TIERS.get(expected_difficulty, 30)

            if target_reps is not None:
                if isinstance(target_reps, (int, float, str)):
                    try:
                        reps = int(target_reps)
                        if reps < PUSH_UP_MIN_REPS or reps > max_allowed:
                            report.violations.append(
                                SafetyViolation(
                                    code=SafetyViolationCode.PHYSICAL_EXERTION_EXCEEDED,
                                    message=(
                                        f"Push-ups target repetitions ({reps}) exceeds safe physical limits "
                                        f"[{PUSH_UP_MIN_REPS}, {max_allowed}] for difficulty '{expected_difficulty}'."
                                    ),
                                    field="content_payload.target_repetitions",
                                    severity=SafetySeverity.CRITICAL,
                                    details=SafetyViolationDetails(
                                        rule_id=RULE_PHYSICAL_SAFETY_VALIDATION,
                                        numeric_measurement=float(reps),
                                        expected_bound=f"[{PUSH_UP_MIN_REPS}, {max_allowed}]",
                                    ),
                                )
                            )
                            report.is_safe = False
                    except (ValueError, TypeError):
                        report.violations.append(
                            SafetyViolation(
                                code=SafetyViolationCode.SCHEMA_MALFORMED,
                                message=f"target_repetitions must be an integer, got {target_reps}.",
                                field="content_payload.target_repetitions",
                                severity=SafetySeverity.CRITICAL,
                            )
                        )
                        report.is_safe = False
                else:
                    report.violations.append(
                        SafetyViolation(
                            code=SafetyViolationCode.SCHEMA_MALFORMED,
                            message=f"target_repetitions must be an integer, got {type(target_reps).__name__}.",
                            field="content_payload.target_repetitions",
                            severity=SafetySeverity.CRITICAL,
                        )
                    )
                    report.is_safe = False

            if window_sec is not None and isinstance(window_sec, (int, float, str)):
                try:
                    w = int(window_sec)
                    if w < PUSH_UP_MIN_WINDOW_SECONDS or w > PUSH_UP_MAX_WINDOW_SECONDS:
                        report.violations.append(
                            SafetyViolation(
                                code=SafetyViolationCode.PHYSICAL_EXERTION_EXCEEDED,
                                message=f"Push-ups completion window ({w}s) exceeds safe bounds [{PUSH_UP_MIN_WINDOW_SECONDS}, {PUSH_UP_MAX_WINDOW_SECONDS}]s.",
                                field="content_payload.completion_window_seconds",
                                severity=SafetySeverity.CRITICAL,
                            )
                        )
                        report.is_safe = False
                except (ValueError, TypeError):
                    pass

    @classmethod
    def validate_challenge_safety(
        cls,
        expected_type: CanonicalChallengeType,
        expected_difficulty: CanonicalDifficultyLevel,
        generated_output: object,
    ) -> SafetyValidationReport:
        """Coordinated validation pipeline executing Common validation first, followed by Domain validation."""
        # 1. Common output validation boundary
        report = CommonOutputValidator.validate(expected_type, expected_difficulty, generated_output)

        # If common validation failed with critical structural violations, return early safely
        if not report.is_safe and any(v.code == SafetyViolationCode.SCHEMA_MALFORMED for v in report.violations):
            return report

        # 2. Domain-specific safety validation
        if expected_type == "math":
            cls.validate_math(expected_difficulty, generated_output, report)
        elif expected_type == "memory":
            cls.validate_memory(expected_difficulty, generated_output, report)
        elif expected_type == "tongue_twister":
            cls.validate_tongue_twister(expected_difficulty, generated_output, report)
        elif expected_type in ("dance", "push_ups"):
            cls.validate_physical(expected_type, expected_difficulty, generated_output, report)

        # Final pass: is_safe requires zero CRITICAL violations
        report.is_safe = not any(v.severity == SafetySeverity.CRITICAL for v in report.violations)
        return report
