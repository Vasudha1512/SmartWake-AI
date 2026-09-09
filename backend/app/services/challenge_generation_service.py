"""Runtime Challenge Generation Service for SmartWake AI.

Converts persisted Challenge catalog templates into concrete, in-memory runtime
challenge instances (RuntimeChallengeResponse) for a WakeSession and future
ChallengeAttempt records.

ARCHITECTURAL RULES:
1. The user selects the challenge type. The generator NEVER alters or chooses between
   challenge categories ('dance', 'math', 'memory', 'tongue_twister', 'push_ups').
2. Memory challenges strictly employ visual sequence, spatial matrix, dynamic path,
   or symbol recall. Number guessing is strictly forbidden and rejected.
3. No ML, LLM, or AI external APIs. All generation is rule-based and algorithmic.
4. No database schema changes; runtime generation outputs are in-memory data structures.
5. All templates and payloads are rigorously validated before generation.
"""
from datetime import datetime
import json
import random
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.constants import FORBIDDEN_CHALLENGE_TYPES, VALID_CHALLENGE_TYPES
from backend.app.core.datetime_utils import now_utc
from backend.app.core.exceptions import (
    ChallengeNotFoundError,
    InactiveChallengeError,
    InvalidChallengeTypeError,
    InvalidDifficultyError,
    InvalidTemplatePayloadError,
    TemplateConfigurationError,
)
from backend.app.models.challenge import Challenge
from backend.app.schemas.challenge_schemas import (
    RuntimeChallengeGenerationRequest,
    RuntimeChallengeResponse,
)

VALID_DIFFICULTIES = {"easy", "medium", "hard"}

# Predefined safe catalog of alternative tongue twister passages for variety
TONGUE_TWISTER_CATALOG: Dict[str, List[Dict[str, Any]]] = {
    "easy": [
        {
            "passage": "She sells sea shells by the sea shore.",
            "phonetic_focus": "s_and_sh_alternation",
            "target_word_count": 8,
        },
        {
            "passage": "Peter Piper picked a peck of pickled peppers.",
            "phonetic_focus": "plosive_p_repetition",
            "target_word_count": 8,
        },
        {
            "passage": "Red lorry, yellow lorry, red lorry, yellow lorry.",
            "phonetic_focus": "liquid_l_and_r_alternation",
            "target_word_count": 8,
        },
    ],
    "medium": [
        {
            "passage": "Six slippery snails slid slowly southward down the steep stone slope.",
            "phonetic_focus": "sibilant_s_clusters",
            "target_word_count": 10,
        },
        {
            "passage": "The thirty-three thieves thought that they thrilled the throne throughout Thursday.",
            "phonetic_focus": "dental_fricative_th",
            "target_word_count": 10,
        },
        {
            "passage": "Fuzzy Wuzzy was a bear, Fuzzy Wuzzy had no hair, Fuzzy Wuzzy wasn't fuzzy, was he?",
            "phonetic_focus": "fricative_z_and_w",
            "target_word_count": 16,
        },
    ],
    "hard": [
        {
            "passage": (
                "How much ground would a groundhog grind if a groundhog could grind ground? "
                "A groundhog would grind all the ground he could grind."
            ),
            "phonetic_focus": "compound_cluster_gr_nd",
            "target_word_count": 21,
        },
        {
            "passage": (
                "Betty Botter bought some butter, but she said the butter's bitter. "
                "If I put it in my batter, it will make my batter bitter, "
                "but a bit of better butter will make my bitter batter better."
            ),
            "phonetic_focus": "rapid_plosive_vowel_shifts",
            "target_word_count": 31,
        },
        {
            "passage": (
                "Pad kid poured curd pulled cod. "
                "A skunk sat on a stump and thunk the stump stunk, "
                "but the stump thunk the skunk stunk."
            ),
            "phonetic_focus": "dense_consonant_dissonance",
            "target_word_count": 21,
        },
    ],
}


def _validate_challenge_type(task_type: Optional[str]) -> str:
    """Validate task type against canonical and forbidden sets."""
    if not task_type:
        raise InvalidChallengeTypeError("Challenge type must be specified.")
    clean = task_type.strip().lower()
    if clean in FORBIDDEN_CHALLENGE_TYPES:
        raise InvalidChallengeTypeError(
            f"Challenge type '{task_type}' is strictly forbidden. "
            f"Memory challenges must NOT be implemented as number guessing."
        )
    if clean not in VALID_CHALLENGE_TYPES:
        raise InvalidChallengeTypeError(
            f"Invalid challenge type '{task_type}'. Must be one of: {sorted(list(VALID_CHALLENGE_TYPES))}."
        )
    return clean


def _validate_difficulty(diff: Optional[str]) -> Optional[str]:
    """Validate difficulty tier if provided."""
    if diff is None:
        return None
    clean = diff.strip().lower()
    if clean not in VALID_DIFFICULTIES:
        raise InvalidDifficultyError(
            f"Invalid difficulty '{diff}'. Must be one of: {sorted(list(VALID_DIFFICULTIES))}."
        )
    return clean


def _parse_payload(payload_str: str) -> Dict[str, Any]:
    """Parse and validate that template payload is valid JSON."""
    try:
        data = json.loads(payload_str)
    except (ValueError, TypeError) as exc:
        raise InvalidTemplatePayloadError(
            f"Template payload is not valid JSON: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise InvalidTemplatePayloadError("Template payload JSON must be an object/dict.")
    return data


# =============================================================================
# 1. MATH GENERATOR
# =============================================================================
def _generate_math(
    template: Challenge, payload: Dict[str, Any]
) -> Tuple[Dict[str, Any], List[int]]:
    """Procedurally generate arithmetic problems matching template bounds."""
    # Validate required parameters
    required_keys = ["question_count", "operation_types", "operand_min", "operand_max"]
    for key in required_keys:
        if key not in payload:
            raise TemplateConfigurationError(
                f"Math template missing required configuration key '{key}'."
            )

    count = int(payload["question_count"])
    op_types = payload["operation_types"]
    if not isinstance(op_types, list) or len(op_types) == 0:
        raise TemplateConfigurationError(
            "Math template 'operation_types' must be a non-empty list."
        )

    op_min = int(payload["operand_min"])
    op_max = int(payload["operand_max"])
    if op_min > op_max:
        raise TemplateConfigurationError("Math operand_min cannot be greater than operand_max.")

    questions: List[Dict[str, Any]] = []
    expected_answers: List[int] = []

    for i in range(1, count + 1):
        chosen_op = random.choice(op_types).lower()

        if chosen_op == "addition":
            a = random.randint(op_min, op_max)
            b = random.randint(op_min, op_max)
            prompt = f"{a} + {b} = ?"
            ans = a + b

        elif chosen_op == "subtraction":
            a = random.randint(op_min, op_max)
            b = random.randint(op_min, a)  # Ensure non-negative answer
            prompt = f"{a} - {b} = ?"
            ans = a - b

        elif chosen_op == "multiplication":
            # Keep operands reasonable for mental arithmetic
            clamped_max = min(op_max, 12)
            clamped_min = max(op_min, 2)
            a = random.randint(clamped_min, clamped_max)
            b = random.randint(clamped_min, clamped_max)
            prompt = f"{a} × {b} = ?"
            ans = a * b

        elif chosen_op == "division":
            # Avoid division by zero and generate exact integer quotient: dividend / divisor = quotient
            divisor = random.randint(max(2, op_min), min(op_max, 12))
            quotient = random.randint(max(1, op_min), min(op_max, 12))
            dividend = divisor * quotient
            prompt = f"{dividend} ÷ {divisor} = ?"
            ans = quotient

        elif chosen_op in ("parentheses", "mixed", "order_of_operations"):
            # Multi-step: (a + b) * c or a * b + c
            a = random.randint(2, 9)
            b = random.randint(2, 9)
            c = random.randint(2, 5)
            if random.random() < 0.5:
                prompt = f"({a} + {b}) × {c} = ?"
                ans = (a + b) * c
            else:
                prompt = f"{a} × {b} + {c} = ?"
                ans = a * b + c

        else:
            # Default to addition
            a = random.randint(op_min, op_max)
            b = random.randint(op_min, op_max)
            prompt = f"{a} + {b} = ?"
            ans = a + b

        questions.append({
            "question_id": i,
            "prompt": prompt,
            "operation": chosen_op,
        })
        expected_answers.append(ans)

    content = {
        "question_count": count,
        "questions": questions,
        "time_limit_seconds": payload.get("time_limit_seconds", 30),
    }
    return content, expected_answers


# =============================================================================
# 2. MEMORY GENERATOR (Strictly Visual/Pattern/Spatial Recall)
# =============================================================================
def _generate_memory(
    template: Challenge, payload: Dict[str, Any]
) -> Tuple[Dict[str, Any], Any]:
    """Generate visual sequence or spatial pattern recall challenge without number guessing."""
    if "recall_mode" not in payload:
        raise TemplateConfigurationError(
            "Memory template missing required configuration key 'recall_mode'."
        )

    mode = payload["recall_mode"]
    disp_dur = payload.get("display_duration_seconds", 5)

    if mode == "visual_sequence":
        palette = payload.get("tile_palette", ["emerald", "amber", "azure", "coral"])
        seq_len = int(payload.get("sequence_length", 4))
        # Pick sequence with replacement
        sequence = [random.choice(palette) for _ in range(seq_len)]
        content = {
            "recall_mode": "visual_sequence",
            "sequence_length": seq_len,
            "display_sequence": sequence,
            "palette": palette,
            "grid_dimension": payload.get("grid_dimension", "2x2"),
            "display_duration_seconds": disp_dur,
            "instructions": "Memorize the sequence of flashing colored tiles, then tap them in exact order.",
        }
        expected = sequence

    elif mode == "spatial_pattern_recall":
        matrix_size = int(payload.get("matrix_size", 3))
        highlight_count = int(payload.get("highlight_count", 3))
        # Coordinate grid [row, col]
        all_cells = [[r, c] for r in range(matrix_size) for c in range(matrix_size)]
        chosen_cells = random.sample(all_cells, k=min(highlight_count, len(all_cells)))
        content = {
            "recall_mode": "spatial_pattern_recall",
            "matrix_size": matrix_size,
            "highlight_count": len(chosen_cells),
            "highlighted_cells": chosen_cells,
            "tile_palette": payload.get("tile_palette", ["slate", "indigo"]),
            "display_duration_seconds": disp_dur,
            "instructions": "Memorize the illuminated grid cells and re-select them once hidden.",
        }
        expected = chosen_cells

    elif mode == "dynamic_spatial_path":
        grid_dim = payload.get("grid_dimension", "3x3")
        size = 3
        seq_len = int(payload.get("sequence_length", 5))
        all_cells = [[r, c] for r in range(size) for c in range(size)]
        path = random.sample(all_cells, k=min(seq_len, len(all_cells)))
        content = {
            "recall_mode": "dynamic_spatial_path",
            "sequence_length": len(path),
            "path_steps": path,
            "grid_dimension": grid_dim,
            "speed_ms_per_step": payload.get("speed_ms_per_step", 700),
            "display_duration_seconds": disp_dur,
            "instructions": "Watch the moving illuminated light trace a path across the grid and repeat the path.",
        }
        expected = path

    elif mode == "dual_alternating_pattern":
        matrix_size = int(payload.get("matrix_size", 5))
        seq_len = int(payload.get("sequence_length", 7))
        all_cells = [[r, c] for r in range(matrix_size) for c in range(matrix_size)]
        sample = random.sample(all_cells, k=min(seq_len, len(all_cells)))
        half = len(sample) // 2
        pattern_a = sample[:half]
        pattern_b = sample[half:]
        content = {
            "recall_mode": "dual_alternating_pattern",
            "matrix_size": matrix_size,
            "pattern_a": pattern_a,
            "pattern_b": pattern_b,
            "display_duration_seconds": disp_dur,
            "instructions": "Observe the two alternating patterns and tap the combined locations.",
        }
        expected = {"pattern_a": pattern_a, "pattern_b": pattern_b}

    elif mode == "symbol_chronological_order":
        symbols = payload.get(
            "symbol_set", ["triangle", "circle", "diamond", "hexagon", "star", "crescent"]
        )
        seq_len = int(payload.get("sequence_length", 6))
        chosen_symbols = random.sample(symbols, k=min(seq_len, len(symbols)))
        content = {
            "recall_mode": "symbol_chronological_order",
            "sequence_length": len(chosen_symbols),
            "display_sequence": chosen_symbols,
            "available_symbols": sorted(list(symbols)),
            "display_duration_seconds": disp_dur,
            "instructions": "Memorize the sequence of geometric symbols and arrange them in chronological order.",
        }
        expected = chosen_symbols

    else:
        raise TemplateConfigurationError(f"Unsupported memory recall_mode '{mode}'.")

    return content, expected


# =============================================================================
# 3. DANCE GENERATOR
# =============================================================================
def _generate_dance(
    template: Challenge, payload: Dict[str, Any]
) -> Tuple[Dict[str, Any], Optional[Any]]:
    """Generate kinetic routine steps and tempo instructions."""
    required_keys = ["routine_type", "step_count", "duration_seconds"]
    for key in required_keys:
        if key not in payload:
            raise TemplateConfigurationError(
                f"Dance template missing required configuration key '{key}'."
            )

    step_count = int(payload["step_count"])
    duration = int(payload["duration_seconds"])
    routine_type = payload["routine_type"]
    tempo = payload.get("tempo_bpm", 110)

    # Core dance movement library
    movement_pool: List[str] = [
        "Step Left & Bounce",
        "Step Right & Bounce",
        "Overhead Arm Wave",
        "Cross-Body Tap Left",
        "Cross-Body Tap Right",
        "High Knee March Left",
        "High Knee March Right",
        "Salsa Forward Step",
        "Salsa Back Step",
        "Double Clap & Pivot",
    ]

    time_step = round(duration / max(step_count, 1), 1)
    steps: List[Dict[str, Any]] = []
    for i in range(1, step_count + 1):
        action = movement_pool[(i - 1) % len(movement_pool)]
        cue_second = round((i - 1) * time_step, 1)
        steps.append({
            "step_number": i,
            "action": action,
            "cue_second": cue_second,
        })

    content = {
        "routine_name": template.title,
        "routine_type": routine_type,
        "step_count": step_count,
        "steps": steps,
        "target_duration_seconds": duration,
        "tempo_bpm": tempo,
        "min_energy_threshold": payload.get("min_energy_threshold", 0.6),
        "instructions": "Follow the rhythmic movement cues shown on screen until routine completes.",
    }
    return content, None


# =============================================================================
# 4. TONGUE TWISTER GENERATOR
# =============================================================================
def _generate_tongue_twister(
    template: Challenge, payload: Dict[str, Any]
) -> Tuple[Dict[str, Any], str]:
    """Generate tongue twister passage with repetition and duration guidelines."""
    diff = template.difficulty_level.lower()
    cat_choices = TONGUE_TWISTER_CATALOG.get(diff, [])

    # Prefer an item from the curated catalog or the template payload
    if cat_choices:
        selected_item = random.choice(cat_choices)
        passage = selected_item["passage"]
        phonetic_focus = selected_item["phonetic_focus"]
        word_count = selected_item["target_word_count"]
    else:
        passage = payload.get("passage_text", "She sells sea shells by the sea shore.")
        phonetic_focus = payload.get("phonetic_focus", "general_enunciation")
        word_count = len(passage.split())

    rep_count = int(payload.get("repetition_count", 2))
    speaking_duration = int(payload.get("speaking_duration_seconds", 15))

    content = {
        "passage": passage,
        "target_repetitions": rep_count,
        "phonetic_focus": phonetic_focus,
        "target_word_count": word_count,
        "max_duration_seconds": speaking_duration,
        "instructions": f"Clearly articulate the passage aloud {rep_count} times without slurring consonants.",
    }
    return content, passage


# =============================================================================
# 5. PUSH-UPS GENERATOR
# =============================================================================
def _generate_push_ups(
    template: Challenge, payload: Dict[str, Any]
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Generate calisthenics repetition target and form guidelines."""
    if "target_repetitions" not in payload:
        raise TemplateConfigurationError(
            "Push-ups template missing required configuration key 'target_repetitions'."
        )

    target_reps = int(payload["target_repetitions"])
    window_seconds = int(payload.get("completion_window_seconds", 45))
    min_rom = int(payload.get("min_rom_percentage", 75))
    cadence = payload.get("cadence_guideline", "moderate")

    content = {
        "target_repetitions": target_reps,
        "completion_window_seconds": window_seconds,
        "min_rom_percentage": min_rom,
        "cadence_guideline": cadence,
        "form_instructions": (
            "Maintain a plank posture, lower chest to hover above floor level, "
            "and extend elbows fully at the peak of each repetition."
        ),
    }
    expected = {"target_repetitions": target_reps}
    return content, expected


# =============================================================================
# MASTER GENERATION FUNCTION
# =============================================================================
def generate_challenge(
    db: Session, request: RuntimeChallengeGenerationRequest
) -> RuntimeChallengeResponse:
    """Generate a concrete runtime challenge instance from an active database template.

    Args:
        db: Active SQLAlchemy database session.
        request: Runtime challenge generation parameters.

    Returns:
        RuntimeChallengeResponse: Structured in-memory runtime challenge.

    Raises:
        InvalidChallengeTypeError: If challenge_type is invalid or forbidden.
        InvalidDifficultyError: If difficulty_level is invalid.
        ChallengeNotFoundError: If no matching template exists in the catalog.
        InactiveChallengeError: If the resolved template is inactive.
        InvalidTemplatePayloadError: If the template payload cannot be parsed.
        TemplateConfigurationError: If required payload parameters are missing.
    """
    template: Optional[Challenge] = None

    # 1. Resolve template by ID if explicitly specified
    if request.template_id is not None:
        template = db.get(Challenge, request.template_id)
        if not template:
            raise ChallengeNotFoundError(
                f"Challenge template with id {request.template_id} not found."
            )
        # Validate that template type is canonical
        clean_type = _validate_challenge_type(template.challenge_type)

    # 2. Otherwise resolve by challenge_type (+ optional difficulty)
    else:
        clean_type = _validate_challenge_type(request.challenge_type)
        diff = _validate_difficulty(request.difficulty_level)

        stmt = select(Challenge).where(
            Challenge.challenge_type == clean_type,
            Challenge.is_active == True,  # noqa: E712
        )
        if diff:
            stmt = stmt.where(Challenge.difficulty_level == diff)

        matching_templates = list(db.scalars(stmt).all())
        if not matching_templates:
            criteria = f"type '{clean_type}'" + (f" and difficulty '{diff}'" if diff else "")
            raise ChallengeNotFoundError(
                f"No active challenge template found in database matching {criteria}."
            )

        # Randomly choose among matching active templates for variety
        template = random.choice(matching_templates)

    # 3. Validate template status
    if not template.is_active:
        raise InactiveChallengeError(
            f"Cannot generate from inactive challenge template id {template.id} ('{template.title}')."
        )

    # 4. Parse payload
    payload = _parse_payload(template.template_payload)

    # 5. Dispatch to type-specific generator
    gen_content: Dict[str, Any]
    expected: Optional[Any]

    if clean_type == "math":
        gen_content, expected = _generate_math(template, payload)
    elif clean_type == "memory":
        gen_content, expected = _generate_memory(template, payload)
    elif clean_type == "dance":
        gen_content, expected = _generate_dance(template, payload)
    elif clean_type == "tongue_twister":
        gen_content, expected = _generate_tongue_twister(template, payload)
    elif clean_type == "push_ups":
        gen_content, expected = _generate_push_ups(template, payload)
    else:
        raise InvalidChallengeTypeError(f"Unsupported challenge type '{clean_type}'.")

    # 6. Resolve verification mode from payload or fallback default
    verification_mode = payload.get("verification_mode", f"{clean_type}_standard")

    # 7. Construct and return in-memory RuntimeChallengeResponse
    return RuntimeChallengeResponse(
        challenge_id=template.id,
        challenge_type=clean_type,
        difficulty_level=template.difficulty_level,
        title=template.title,
        generated_content=gen_content,
        parameters=payload,
        expected_answer=expected,
        verification_mode=verification_mode,
        min_duration_seconds=template.min_duration_seconds,
        generated_at=now_utc(),
    )
