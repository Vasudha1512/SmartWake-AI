"""Structural repetition avoidance service for AI-Powered Challenge Personalization (Phase 4.5).

Provides a lightweight, deterministic, privacy-preserving structural repetition
mechanism for personalized wake challenge content across all five canonical challenge types:
- math
- memory
- tongue_twister
- dance
- push_ups

CRITICAL INVARIANTS:
1. Purely structural: Signatures describe structural dimensions, NOT raw challenge text or wording.
2. Bounded length: All signatures are strictly <= 60 characters (safe for PersonalizedChallengeProfile).
3. Deterministic & canonical: Normalized ordering, whitespace, and category bucketing; no LLMs or embeddings.
4. Bounded LRU window: Maximum K = 5 entries, newest-first, duplicate promotion.
5. Strict security: Zero database IDs, PII, credentials, control characters, or post-challenge outcomes.
6. Zero Dict[str, Any]: Strictly typed input models with extra="forbid" and strict=True.
7. T0 boundary: Operates solely on historical pre-T0 structural attributes with zero database access.
"""
from typing import Dict, List, Literal, Optional, Sequence, Set, Union, cast
from pydantic import BaseModel, ConfigDict, Field

from backend.app.schemas.challenge_content_schemas import FORBIDDEN_CONTEXT_KEYS
from backend.app.schemas.personalization_content_schemas import (
    CanonicalChallengeType,
    CanonicalDifficultyLevel,
    DancePersonalizationParams,
    MathPersonalizationParams,
    MemoryPersonalizationParams,
    PersonalizedChallengeProfile,
    PushUpPersonalizationParams,
    TongueTwisterPersonalizationParams,
    VALID_CANONICAL_CHALLENGE_TYPES,
)

# Maximum character length for any structural signature
MAX_SIGNATURE_LENGTH: int = 60

# Maximum capacity for recent structural signatures window
MAX_WINDOW_CAPACITY: int = 5


# =============================================================================
# EXCEPTIONS
# =============================================================================

class StructuralRepetitionError(ValueError):
    """Base exception for structural repetition errors."""
    pass


class InvalidStructuralInputError(StructuralRepetitionError):
    """Raised when structural input data is invalid, malformed, or contains PII."""
    pass


class InvalidSignatureFormatError(StructuralRepetitionError):
    """Raised when a structural signature string violates format or security bounds."""
    pass


# =============================================================================
# TYPED STRUCTURAL INPUT MODELS (Strict, extra="forbid", zero Dict[str, Any])
# =============================================================================

class MathStructuralInput(BaseModel):
    """Bounded, typed structural parameters for math challenges."""

    operation: Literal["addition", "subtraction", "multiplication", "division", "mixed"] = Field(
        ...,
        description="Canonical arithmetic operation category.",
    )
    operand_scale: Literal["compact", "standard", "large"] = Field(
        default=cast(Literal["compact", "standard", "large"], "standard"),
        description="Magnitude category of operands (compact: <=12, standard: <=99, large: >=100).",
    )
    expression_type: Literal["binary", "multi_operand"] = Field(
        default=cast(Literal["binary", "multi_operand"], "binary"),
        description="Structural expression complexity (binary: 2 operands, multi_operand: 3+).",
    )
    difficulty: Optional[CanonicalDifficultyLevel] = Field(
        default=None,
        description="Optional authoritative difficulty tier for structural distinction.",
    )

    model_config = ConfigDict(extra="forbid", strict=True)


class MemoryStructuralInput(BaseModel):
    """Bounded, typed structural parameters for memory challenges."""

    recall_mode: Literal[
        "visual_sequence",
        "spatial_pattern_recall",
        "dynamic_spatial_path",
        "symbol_chronological_order",
    ] = Field(
        ...,
        description="Authoritative memory recall mode.",
    )
    sequence_length_bucket: Optional[Literal["short", "medium", "long"]] = Field(
        default=None,
        description="Sequence length bucket (short: 2-4, medium: 5-7, long: 8-12).",
    )
    matrix_size: Optional[Literal["2x2", "3x3", "4x4", "5x5", "6x6"]] = Field(
        default=None,
        description="Grid dimension for spatial modes.",
    )
    palette_theme: Optional[
        Literal["colors", "geometric_shapes", "cardinal_directions", "emojis"]
    ] = Field(
        default=None,
        description="Non-numeric symbol palette theme.",
    )

    model_config = ConfigDict(extra="forbid", strict=True)


class TongueTwisterStructuralInput(BaseModel):
    """Bounded, typed structural parameters for tongue twister challenges."""

    target_sound_family: Literal["sibilants", "plosives", "liquids", "nasals", "any"] = Field(
        ...,
        description="Target phonetic sound pattern family.",
    )
    repetition_bucket: Literal["1_rep", "2_rep", "3_plus", "1", "2", "3+"] = Field(
        default=cast(Literal["1_rep", "2_rep", "3_plus", "1", "2", "3+"], "2_rep"),
        description="Repetition count bucket (1_rep: 1, 2_rep: 2, 3_plus: >=3).",
    )
    word_count_bucket: Optional[Literal["short", "medium", "long"]] = Field(
        default=None,
        description="Passage length bucket (short: <=8, medium: 9-16, long: >=17).",
    )
    theme_style: Optional[Literal["nature", "animals", "workday", "whimsical", "rhyme"]] = Field(
        default=None,
        description="Thematic passage style.",
    )

    model_config = ConfigDict(extra="forbid", strict=True)


class DanceStructuralInput(BaseModel):
    """Bounded, typed structural parameters for procedural dance challenges."""

    movement_style: Literal["rhythm_groove", "arm_raises", "step_touch", "standard"] = Field(
        default=cast(
            Literal["rhythm_groove", "arm_raises", "step_touch", "standard"],
            "standard",
        ),
        description="Procedural movement routine style.",
    )
    pacing: Literal["slow", "moderate", "dynamic"] = Field(
        default=cast(Literal["slow", "moderate", "dynamic"], "moderate"),
        description="Routine tempo and pacing.",
    )
    routine_length_bucket: Optional[Literal["short", "medium", "long"]] = Field(
        default=None,
        description="Routine duration/step bucket (short: <=4 steps, medium: 5-8, long: >=9).",
    )

    model_config = ConfigDict(extra="forbid", strict=True)


class PushUpStructuralInput(BaseModel):
    """Bounded, typed structural parameters for procedural push-up challenges."""

    cadence_style: Literal["steady", "tempo_pause", "standard"] = Field(
        default=cast(Literal["steady", "tempo_pause", "standard"], "standard"),
        description="Cadence and form pacing emphasis.",
    )
    repetition_bucket: Literal["tier_min", "tier_median", "tier_max", "low", "medium", "high"] = Field(
        default=cast(
            Literal["tier_min", "tier_median", "tier_max", "low", "medium", "high"],
            "tier_median",
        ),
        description="Repetition volume bucket.",
    )
    rom_requirement: Optional[Literal["standard", "strict"]] = Field(
        default=None,
        description="Range-of-motion threshold indicator.",
    )

    model_config = ConfigDict(extra="forbid", strict=True)


StructuralInputType = Union[
    MathStructuralInput,
    MemoryStructuralInput,
    TongueTwisterStructuralInput,
    DanceStructuralInput,
    PushUpStructuralInput,
]


# =============================================================================
# CANONICALIZATION & BUCKETING HELPERS
# =============================================================================

def canonicalize_text(text: str) -> str:
    """Normalize text: strip whitespace, lowercase, collapse internal whitespace.

    Inspects original input before normalization to reject control characters
    (including newline, carriage return, tab) and forbidden PII keys.
    """
    if not isinstance(text, str):
        raise InvalidStructuralInputError("Text must be a string.")
    if any(ord(c) < 32 for c in text):
        raise InvalidStructuralInputError("Text contains forbidden control characters.")
    clean = " ".join(text.strip().split()).lower()
    if not clean:
        raise InvalidStructuralInputError("Text cannot be empty or whitespace only.")
    for forbidden in FORBIDDEN_CONTEXT_KEYS:
        if forbidden in clean:
            raise InvalidStructuralInputError(f"Text contains forbidden identity key '{forbidden}'.")
    return clean


def bucket_number(
    value: int,
    low_cutoff: int,
    medium_cutoff: int,
) -> Literal["short", "medium", "long"]:
    """Bucket a numeric count into standardized short/medium/long categories."""
    if value <= low_cutoff:
        return "short"
    elif value <= medium_cutoff:
        return "medium"
    return "long"


def bucket_duration(duration_seconds: int) -> Literal["short", "medium", "long"]:
    """Bucket interaction duration in seconds into short/medium/long categories."""
    return bucket_number(duration_seconds, low_cutoff=20, medium_cutoff=45)


def bucket_sequence_length(length: int) -> Literal["short", "medium", "long"]:
    """Bucket memory sequence length (short: <=4, medium: 5-7, long: >=8)."""
    return bucket_number(length, low_cutoff=4, medium_cutoff=7)


def bucket_word_count(count: int) -> Literal["short", "medium", "long"]:
    """Bucket passage word count (short: <=8, medium: 9-16, long: >=17)."""
    return bucket_number(count, low_cutoff=8, medium_cutoff=16)


def bucket_repetition_count(reps: int) -> Literal["1", "2", "3+"]:
    """Bucket repetition count (1: 1, 2: 2, 3+: >=3)."""
    if reps <= 1:
        return "1"
    elif reps == 2:
        return "2"
    return "3+"


bucket_repetition = bucket_repetition_count


def bucket_push_up_reps(reps: int) -> Literal["low", "medium", "high"]:
    """Bucket raw push-up repetitions (low: <=5, medium: 6-12, high: >=13)."""
    if reps <= 5:
        return "low"
    elif reps <= 12:
        return "medium"
    return "high"


def bucket_dance_steps(steps: int) -> Literal["short", "medium", "long"]:
    """Bucket dance routine step count (short: <=4, medium: 5-8, long: >=9)."""
    return bucket_number(steps, low_cutoff=4, medium_cutoff=8)


def bucket_operand_scale_from_values(operands: Sequence[int]) -> Literal["compact", "standard", "large"]:
    """Bucket operand magnitudes based on maximum absolute operand value."""
    if not operands:
        return "standard"
    max_val = max(abs(x) for x in operands)
    if max_val <= 12:
        return "compact"
    elif max_val <= 99:
        return "standard"
    return "large"


def canonicalize_operation_name(
    op: str,
) -> Literal["addition", "subtraction", "multiplication", "division", "mixed"]:
    """Normalize arithmetic operation names and mathematical operator symbols."""
    clean = op.strip().lower() if isinstance(op, str) else ""
    op_map: Dict[
        str,
        Literal["addition", "subtraction", "multiplication", "division", "mixed"],
    ] = {
        "+": "addition",
        "add": "addition",
        "addition": "addition",
        "-": "subtraction",
        "sub": "subtraction",
        "subtraction": "subtraction",
        "*": "multiplication",
        "x": "multiplication",
        "mult": "multiplication",
        "multiplication": "multiplication",
        "/": "division",
        "div": "division",
        "division": "division",
        "mixed": "mixed",
        "mix": "mixed",
    }
    if clean not in op_map:
        raise InvalidStructuralInputError(f"Unsupported math operation: '{op}'.")
    return op_map[clean]


normalize_operation = canonicalize_operation_name


def normalize_scale(scale: str) -> Literal["compact", "standard", "large"]:
    """Normalize operand scale string representation."""
    clean = scale.strip().lower() if isinstance(scale, str) else ""
    scale_map = {
        "compact": "compact",
        "small": "compact",
        "single": "compact",
        "standard": "standard",
        "medium": "standard",
        "normal": "standard",
        "large": "large",
        "big": "large",
    }
    if clean not in scale_map:
        raise InvalidStructuralInputError(f"Unsupported operand scale: '{scale}'.")
    return scale_map[clean]  # type: ignore


def canonicalize_recall_mode_token(mode: str) -> str:
    """Map memory recall modes to compact canonical tokens guaranteeing <= 60 char signatures."""
    clean = mode.strip().lower() if isinstance(mode, str) else ""
    mode_map = {
        "visual_sequence": "visual_seq",
        "visual_seq": "visual_seq",
        "spatial_pattern_recall": "spatial_pat",
        "spatial_pattern": "spatial_pat",
        "spatial_pat": "spatial_pat",
        "dynamic_spatial_path": "dynamic_path",
        "dynamic_path": "dynamic_path",
        "symbol_chronological_order": "symbol_order",
        "symbol_order": "symbol_order",
    }
    if clean not in mode_map:
        raise InvalidStructuralInputError(f"Unsupported memory recall mode: '{mode}'.")
    return mode_map[clean]


normalize_memory_mode = canonicalize_recall_mode_token


def canonicalize_palette_theme_token(theme: str) -> str:
    """Map palette theme to canonical compact token."""
    clean = theme.strip().lower() if isinstance(theme, str) else ""
    theme_map = {
        "colors": "colors",
        "geometric_shapes": "shapes",
        "shapes": "shapes",
        "cardinal_directions": "directions",
        "directions": "directions",
        "emojis": "emojis",
        "emoji": "emojis",
    }
    if clean not in theme_map:
        raise InvalidStructuralInputError(f"Unsupported palette theme: '{theme}'.")
    return theme_map[clean]


def canonicalize_sound_family_token(family: str) -> str:
    """Canonicalize sound family to validated literal."""
    clean = family.strip().lower() if isinstance(family, str) else ""
    valid = {"sibilants", "plosives", "liquids", "nasals", "any"}
    if clean not in valid:
        raise InvalidStructuralInputError(f"Unsupported sound family: '{family}'.")
    return clean


normalize_sound_family = canonicalize_sound_family_token


def canonicalize_repetition_token(reps: str) -> str:
    """Canonicalize tongue twister repetition bucket to compact token."""
    clean = reps.strip().lower() if isinstance(reps, str) else ""
    rep_map = {
        "1_rep": "1",
        "1": "1",
        "2_rep": "2",
        "2": "2",
        "3_plus": "3+",
        "3+": "3+",
        "3": "3+",
    }
    if clean not in rep_map:
        raise InvalidStructuralInputError(f"Unsupported repetition bucket: '{reps}'.")
    return rep_map[clean]


def canonicalize_dance_style_token(style: str) -> str:
    """Canonicalize movement style to validated literal."""
    clean = style.strip().lower() if isinstance(style, str) else ""
    valid = {"rhythm_groove", "arm_raises", "step_touch", "standard"}
    if clean not in valid:
        raise InvalidStructuralInputError(f"Unsupported dance movement style: '{style}'.")
    return clean


normalize_movement_style = canonicalize_dance_style_token


def normalize_pace(pace: str) -> Literal["slow", "moderate", "dynamic"]:
    """Canonicalize dance routine tempo pacing."""
    clean = pace.strip().lower() if isinstance(pace, str) else ""
    valid = {"slow", "moderate", "dynamic"}
    if clean not in valid:
        raise InvalidStructuralInputError(f"Unsupported dance pacing: '{pace}'.")
    return clean  # type: ignore


def canonicalize_cadence_token(cadence: str) -> str:
    """Canonicalize cadence to validated literal."""
    clean = cadence.strip().lower() if isinstance(cadence, str) else ""
    valid = {"steady", "tempo_pause", "standard"}
    if clean not in valid:
        raise InvalidStructuralInputError(f"Unsupported push-up cadence: '{cadence}'.")
    return clean


normalize_cadence = canonicalize_cadence_token


# =============================================================================
# SIGNATURE VALIDATION & SECURITY SANITIZATION
# =============================================================================

def validate_structural_signature(signature: str) -> str:
    """Validate a structural signature against bounds, format, and security constraints.

    GUARANTEES:
    - Must be a non-empty string.
    - Must not contain control characters or newlines.
    - Must not exceed MAX_SIGNATURE_LENGTH (60 characters).
    - Must not contain forbidden identity/PII keys.
    - Must declare a supported canonical challenge type prefix.
    """
    if not isinstance(signature, str):
        raise InvalidSignatureFormatError("Structural signature must be a string.")

    clean = signature.strip()
    if not clean:
        raise InvalidSignatureFormatError("Structural signature cannot be empty or whitespace.")

    if any(ord(c) < 32 for c in clean):
        raise InvalidSignatureFormatError(
            "Structural signature cannot contain control characters or newlines."
        )

    if len(clean) > MAX_SIGNATURE_LENGTH:
        raise InvalidSignatureFormatError(
            f"Structural signature length ({len(clean)}) exceeds maximum bound of {MAX_SIGNATURE_LENGTH} characters."
        )

    lower = clean.lower()
    for forbidden in FORBIDDEN_CONTEXT_KEYS:
        if forbidden in lower:
            raise InvalidSignatureFormatError(
                f"Structural signature contains forbidden identity key '{forbidden}'."
            )

    # Validate type prefix: format is "type=<challenge_type>|..."
    if not lower.startswith("type="):
        raise InvalidSignatureFormatError(
            "Structural signature must start with canonical 'type=' declaration."
        )

    parts = lower.split("|")
    type_part = parts[0]
    ctype = type_part.replace("type=", "").strip()
    if ctype not in VALID_CANONICAL_CHALLENGE_TYPES:
        raise InvalidSignatureFormatError(
            f"Structural signature contains unsupported challenge type '{ctype}'."
        )

    return clean


validate_signature = validate_structural_signature


# =============================================================================
# DETERMINISTIC SIGNATURE BUILDERS (By Challenge Type)
# =============================================================================

def build_math_signature(input_data: MathStructuralInput) -> str:
    """Build deterministic structural signature for math challenge content.

    Format: type=math|op=<op>|scale=<scale>[|expr=<expr>][|diff=<diff>]
    Guaranteed bounded <= 60 characters.
    """
    op = canonicalize_operation_name(input_data.operation)
    scale = input_data.operand_scale
    expr = input_data.expression_type
    diff = input_data.difficulty

    parts = ["type=math", f"op={op}", f"scale={scale}"]
    if expr and expr != "binary":
        parts.append("expr=multi")
    if diff:
        parts.append(f"diff={diff}")

    sig = "|".join(parts)
    return validate_structural_signature(sig)


def build_memory_signature(input_data: MemoryStructuralInput) -> str:
    """Build deterministic structural signature for memory challenge content.

    Format: type=memory|mode=<mode_token>[|grid=<grid>][|len=<bucket>][|theme=<theme>]
    Guaranteed bounded <= 60 characters.
    """
    mode_token = canonicalize_recall_mode_token(input_data.recall_mode)
    parts = ["type=memory", f"mode={mode_token}"]

    # Preserve optional structural fields whenever they fit within MAX_SIGNATURE_LENGTH (60).
    # If optional fields would exceed 60 characters, omit lower-priority optional fields
    # deterministically without truncation (prioritizing grid, then len, then theme).
    if input_data.matrix_size:
        candidate_with_grid = "|".join(parts + [f"grid={input_data.matrix_size}"])
        if len(candidate_with_grid) <= MAX_SIGNATURE_LENGTH:
            parts.append(f"grid={input_data.matrix_size}")

    if input_data.sequence_length_bucket:
        candidate_with_len = "|".join(parts + [f"len={input_data.sequence_length_bucket}"])
        if len(candidate_with_len) <= MAX_SIGNATURE_LENGTH:
            parts.append(f"len={input_data.sequence_length_bucket}")

    if input_data.palette_theme:
        theme_token = canonicalize_palette_theme_token(input_data.palette_theme)
        candidate_with_theme = "|".join(parts + [f"theme={theme_token}"])
        if len(candidate_with_theme) <= MAX_SIGNATURE_LENGTH:
            parts.append(f"theme={theme_token}")

    sig = "|".join(parts)
    return validate_structural_signature(sig)


def build_tongue_twister_signature(input_data: TongueTwisterStructuralInput) -> str:
    """Build deterministic structural signature for tongue twister challenge content.

    Format: type=tongue_twister|sound=<sound>|reps=<reps>[|len=<len>][|theme=<theme>]
    Guaranteed bounded <= 60 characters.
    """
    sound = canonicalize_sound_family_token(input_data.target_sound_family)
    reps = canonicalize_repetition_token(input_data.repetition_bucket)
    parts = ["type=tongue_twister", f"sound={sound}", f"reps={reps}"]

    if input_data.word_count_bucket:
        parts.append(f"len={input_data.word_count_bucket}")

    # If theme_style is provided, include it if it fits within the 60 char bound
    if input_data.theme_style:
        candidate_with_theme = "|".join(parts + [f"theme={input_data.theme_style}"])
        if len(candidate_with_theme) <= MAX_SIGNATURE_LENGTH:
            parts.append(f"theme={input_data.theme_style}")

    sig = "|".join(parts)
    return validate_structural_signature(sig)


def build_dance_signature(input_data: DanceStructuralInput) -> str:
    """Build deterministic structural signature for procedural dance challenge content.

    Format: type=dance|style=<style>|pace=<pace>[|len=<len>]
    Guaranteed bounded <= 60 characters.
    """
    style = canonicalize_dance_style_token(input_data.movement_style)
    pace = input_data.pacing
    parts = ["type=dance", f"style={style}", f"pace={pace}"]

    if input_data.routine_length_bucket:
        parts.append(f"len={input_data.routine_length_bucket}")

    sig = "|".join(parts)
    return validate_structural_signature(sig)


def build_push_ups_signature(input_data: PushUpStructuralInput) -> str:
    """Build deterministic structural signature for procedural push-up challenge content.

    Format: type=push_ups|cad=<cadence>|reps=<reps>[|rom=<rom>]
    Guaranteed bounded <= 60 characters.
    """
    cadence = canonicalize_cadence_token(input_data.cadence_style)
    reps = input_data.repetition_bucket
    parts = ["type=push_ups", f"cad={cadence}", f"reps={reps}"]

    if input_data.rom_requirement:
        parts.append(f"rom={input_data.rom_requirement}")

    sig = "|".join(parts)
    return validate_structural_signature(sig)


build_push_up_signature = build_push_ups_signature


# =============================================================================
# UNIFIED SIGNATURE GENERATION DISPATCHER
# =============================================================================

def generate_structural_signature(
    challenge_type: CanonicalChallengeType,
    structural_input: StructuralInputType,
) -> str:
    """Generate and validate a deterministic structural signature from typed structural input.

    GUARANTEES:
    - Strict challenge type and input model compatibility check.
    - Always bounded to <= 60 characters.
    - Rejects invalid or mismatched structural input models.
    """
    if challenge_type not in VALID_CANONICAL_CHALLENGE_TYPES:
        raise InvalidStructuralInputError(
            f"Unsupported canonical challenge type: '{challenge_type}'."
        )

    if challenge_type == "math":
        if not isinstance(structural_input, MathStructuralInput):
            raise InvalidStructuralInputError(
                f"Expected MathStructuralInput for 'math', got {type(structural_input).__name__}."
            )
        return build_math_signature(structural_input)

    elif challenge_type == "memory":
        if not isinstance(structural_input, MemoryStructuralInput):
            raise InvalidStructuralInputError(
                f"Expected MemoryStructuralInput for 'memory', got {type(structural_input).__name__}."
            )
        return build_memory_signature(structural_input)

    elif challenge_type == "tongue_twister":
        if not isinstance(structural_input, TongueTwisterStructuralInput):
            raise InvalidStructuralInputError(
                f"Expected TongueTwisterStructuralInput for 'tongue_twister', got {type(structural_input).__name__}."
            )
        return build_tongue_twister_signature(structural_input)

    elif challenge_type == "dance":
        if not isinstance(structural_input, DanceStructuralInput):
            raise InvalidStructuralInputError(
                f"Expected DanceStructuralInput for 'dance', got {type(structural_input).__name__}."
            )
        return build_dance_signature(structural_input)

    elif challenge_type == "push_ups":
        if not isinstance(structural_input, PushUpStructuralInput):
            raise InvalidStructuralInputError(
                f"Expected PushUpStructuralInput for 'push_ups', got {type(structural_input).__name__}."
            )
        return build_push_ups_signature(structural_input)

    raise InvalidStructuralInputError(f"Unhandled canonical challenge type: '{challenge_type}'.")


def build_signature_from_profile(profile: PersonalizedChallengeProfile) -> str:
    """Derive a deterministic structural signature directly from a PersonalizedChallengeProfile.

    Adapts the profile's authoritative type, difficulty, and typed_parameters without modifying schemas.
    """
    ctype = profile.challenge_type
    diff = profile.difficulty_level
    tparams = profile.typed_parameters

    if ctype == "math":
        op = "mixed"
        scale = "standard"
        if isinstance(tparams, MathPersonalizationParams):
            if tparams.preferred_operation:
                op = tparams.preferred_operation
            if tparams.operand_scale_preference:
                scale = tparams.operand_scale_preference
        input_model = MathStructuralInput(
            operation=canonicalize_operation_name(op),
            operand_scale=scale,
            difficulty=diff,
        )
        return build_math_signature(input_model)

    elif ctype == "memory":
        mode = "visual_sequence"
        palette = None
        if isinstance(tparams, MemoryPersonalizationParams):
            if tparams.preferred_mode:
                mode = tparams.preferred_mode
            if tparams.palette_theme:
                palette = tparams.palette_theme
        input_model = MemoryStructuralInput(
            recall_mode=mode,
            palette_theme=palette,
        )
        return build_memory_signature(input_model)

    elif ctype == "tongue_twister":
        sound = "any"
        theme = None
        if isinstance(tparams, TongueTwisterPersonalizationParams):
            if tparams.target_sound_family:
                sound = tparams.target_sound_family
            if tparams.theme_style:
                theme = tparams.theme_style
        input_model = TongueTwisterStructuralInput(
            target_sound_family=sound,
            theme_style=theme,
        )
        return build_tongue_twister_signature(input_model)

    elif ctype == "dance":
        style = "standard"
        pacing = "moderate"
        if isinstance(tparams, DancePersonalizationParams):
            if tparams.movement_style:
                style = tparams.movement_style
            if tparams.pacing:
                pacing = tparams.pacing
        input_model = DanceStructuralInput(
            movement_style=style,
            pacing=pacing,
        )
        return build_dance_signature(input_model)

    elif ctype == "push_ups":
        cadence = "standard"
        reps = "tier_median"
        if isinstance(tparams, PushUpPersonalizationParams):
            if tparams.cadence_tempo:
                cadence = tparams.cadence_tempo
            if tparams.target_rep_styling:
                reps = tparams.target_rep_styling
        input_model = PushUpStructuralInput(
            cadence_style=cadence,
            repetition_bucket=reps,
        )
        return build_push_ups_signature(input_model)

    raise InvalidStructuralInputError(f"Unsupported challenge type in profile: '{ctype}'.")


# =============================================================================
# REPEAT DETECTION & BOUNDED LRU WINDOW
# =============================================================================

def is_structural_repeat(
    signature: str,
    recent_signatures: Optional[Sequence[Optional[str]]],
) -> bool:
    """Determine whether a structural signature matches any historical signature.

    REQUIREMENTS:
    - Exact canonical signature comparison.
    - No semantic similarity or fuzzy matching.
    - Bounded input validation.
    - Safe handling of empty or None history -> returns False.
    - Safe handling of duplicate signatures in history.
    """
    valid_sig = validate_structural_signature(signature)

    if not recent_signatures:
        return False

    for historical in recent_signatures:
        if not isinstance(historical, str):
            continue
        try:
            clean_hist = validate_structural_signature(historical)
            if clean_hist == valid_sig:
                return True
        except (InvalidSignatureFormatError, ValueError):
            # Skip invalid entries safely without crashing
            continue

    return False


has_structural_repeat = is_structural_repeat


class StructuralSignatureWindow:
    """Bounded LRU-style recent-signature window.

    INVARIANTS:
    - Maximum capacity K = 5 (matches PersonalizedChallengeProfile.recent_structural_signatures max_length).
    - Newest signature is at index 0 (newest-first ordering).
    - LRU duplicate promotion: adding an existing signature promotes it to index 0 rather
      than consuming duplicate capacity.
      Example:
        A -> [A]
        B -> [B, A]
        C -> [C, B, A]
        B again -> [B, C, A]
    - Eviction: If window size exceeds max_capacity after insertion, oldest element at tail is evicted.
    - Strictly bounded: len(signatures) <= max_capacity at all times.
    - Purely in-memory: zero database persistence or ORM coupling.
    """

    def __init__(
        self,
        initial_signatures: Optional[Sequence[Optional[str]]] = None,
        max_capacity: int = MAX_WINDOW_CAPACITY,
    ) -> None:
        if max_capacity < 1:
            raise ValueError("max_capacity must be at least 1.")
        self.max_capacity: int = max_capacity
        self._signatures: List[str] = []

        if initial_signatures:
            # Replay initial signatures in order to build bounded LRU state
            for sig in initial_signatures:
                if isinstance(sig, str):
                    self.add_signature(sig)

    def has_signature(self, signature: str) -> bool:
        """Check whether a signature is already present in the window."""
        valid_sig = validate_structural_signature(signature)
        return valid_sig in self._signatures

    def add_signature(self, signature: str) -> None:
        """Add a signature to the window using LRU promotion.

        If already present, removes it from its current position and inserts it at index 0.
        If not present, inserts at index 0 and evicts the tail if exceeding max_capacity.
        """
        valid_sig = validate_structural_signature(signature)

        if valid_sig in self._signatures:
            self._signatures.remove(valid_sig)

        self._signatures.insert(0, valid_sig)

        if len(self._signatures) > self.max_capacity:
            self._signatures = self._signatures[: self.max_capacity]

    def get_signatures(self) -> List[str]:
        """Return a copy of the bounded recent signatures list in newest-first order."""
        return list(self._signatures)

    def __len__(self) -> int:
        return len(self._signatures)

    def __repr__(self) -> str:
        return f"StructuralSignatureWindow(capacity={self.max_capacity}, signatures={self._signatures!r})"


RecentSignatureWindow = StructuralSignatureWindow


def update_recent_signatures(
    recent_signatures: Optional[Sequence[Optional[str]]],
    new_signature: str,
    max_capacity: int = MAX_WINDOW_CAPACITY,
) -> List[str]:
    """Pure functional helper to update recent signatures list using bounded LRU promotion.

    Accepts an existing sequence of signatures (or None), adds new_signature, and returns
    a new list of strings bounded to max_capacity in newest-first order.
    """
    window = StructuralSignatureWindow(
        initial_signatures=recent_signatures,
        max_capacity=max_capacity,
    )
    window.add_signature(new_signature)
    return window.get_signatures()


__all__ = [
    # Constants
    "MAX_SIGNATURE_LENGTH",
    "MAX_WINDOW_CAPACITY",
    # Exceptions
    "StructuralRepetitionError",
    "InvalidStructuralInputError",
    "InvalidSignatureFormatError",
    # Input Models
    "MathStructuralInput",
    "MemoryStructuralInput",
    "TongueTwisterStructuralInput",
    "DanceStructuralInput",
    "PushUpStructuralInput",
    "StructuralInputType",
    # Signature Builders
    "build_math_signature",
    "build_memory_signature",
    "build_tongue_twister_signature",
    "build_dance_signature",
    "build_push_ups_signature",
    "build_push_up_signature",
    "generate_structural_signature",
    "build_signature_from_profile",
    # Bucketing Helpers
    "bucket_number",
    "bucket_duration",
    "bucket_sequence_length",
    "bucket_word_count",
    "bucket_repetition_count",
    "bucket_repetition",
    "bucket_push_up_reps",
    "bucket_dance_steps",
    "bucket_operand_scale_from_values",
    # Canonicalization & Normalization
    "canonicalize_text",
    "canonicalize_operation_name",
    "normalize_operation",
    "normalize_scale",
    "canonicalize_recall_mode_token",
    "normalize_memory_mode",
    "canonicalize_palette_theme_token",
    "canonicalize_sound_family_token",
    "normalize_sound_family",
    "canonicalize_repetition_token",
    "canonicalize_dance_style_token",
    "normalize_movement_style",
    "normalize_pace",
    "canonicalize_cadence_token",
    "normalize_cadence",
    # Validation & Windows
    "validate_structural_signature",
    "validate_signature",
    "is_structural_repeat",
    "has_structural_repeat",
    "StructuralSignatureWindow",
    "RecentSignatureWindow",
    "update_recent_signatures",
]
