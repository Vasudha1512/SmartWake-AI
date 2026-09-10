"""Challenge Personalization Service and Precedence Engine (Phase 4.5 Step 3).

Coordinates and personalizes content parameters for wake-up challenges:
- Phase 3 authoritative canonical challenge_type (strictly immutable)
- Phase 3 authoritative concrete difficulty_level (strictly immutable)
- SafePersonalizationContext from Phase 4.1 (sanitized explicit user preferences)
- BehavioralPersonalizationSignals from Step 1 (non-clinical pre-T0 behavioral metrics)
- Recent structural signatures from Step 2 (bounded historical repetition avoidance)

AUTHORITATIVE PRECEDENCE HIERARCHY:
1. SAFETY:
   - Forbid forbidden challenge types (number guessing, numeric memory).
   - Validate canonical challenge type and concrete difficulty tier.
   - Enforce disallowed_topics as CONTENT/TOPIC constraints only on topic-like fields
     (math focus_topic, memory palette_theme, tongue twister theme_style, dance movement_style,
     push-up target_rep_styling).
   - Never reject control/structural parameters (scale, op, mode, pacing, cadence, diff, type).
   - Forbid identity keys and PII.
2. CHALLENGE TYPE:
   - Authoritative caller input; strictly immutable.
3. DIFFICULTY:
   - Authoritative concrete tier ('easy', 'medium', 'hard'); strictly immutable.
4. EXPLICIT USER PREFERENCES:
   - preferred_theme, desired_duration_seconds, language from SafePersonalizationContext.
5. BEHAVIORAL SIGNALS:
   - Recent snooze, retry indicator, historical success rate, failure count.
   - historical_success_rate=None is treated strictly as NO HISTORY.
6. STRUCTURAL REPETITION:
   - Deterministic candidate signature check against recent history (max 5).
   - Up to 3 bounded deterministic alternative attempts.
   - Safe fallback preserving type and difficulty if all alternatives repeat.
7. SAFE DEFAULTS:
   - Deterministic, canonical typed parameter defaults.

CRITICAL INVARIANTS:
- Operates strictly before T0 (zero post-challenge outcome usage).
- Pure in-memory, synchronous, and 100% deterministic (no random, no timestamps, no UUIDs).
- Zero database access, ORM models, LLM calls, or network calls.
- Zero Dict[str, Any] structures (strict Pydantic models only).
"""
from typing import List, Literal, Optional, Sequence, Set, Tuple, cast

from backend.app.core.constants import FORBIDDEN_CHALLENGE_TYPES
from backend.app.schemas.challenge_content_schemas import (
    FORBIDDEN_CONTEXT_KEYS,
    SAFE_TOPIC_REGEX,
    SafePersonalizationContext,
)
from backend.app.schemas.personalization_content_schemas import (
    BehavioralPersonalizationSignals,
    CanonicalChallengeType,
    CanonicalDifficultyLevel,
    DancePersonalizationParams,
    MathPersonalizationParams,
    MemoryPersonalizationParams,
    PersonalizationParamsType,
    PersonalizedChallengeProfile,
    PushUpPersonalizationParams,
    TongueTwisterPersonalizationParams,
    VALID_CANONICAL_CHALLENGE_TYPES,
    VALID_CANONICAL_DIFFICULTIES,
)
from backend.app.services.genai.structural_repetition import (
    MAX_WINDOW_CAPACITY,
    build_signature_from_profile,
    is_structural_repeat,
    validate_structural_signature,
)

# Maximum number of deterministic alternative attempts when structural repetition occurs
MAX_REPETITION_ATTEMPTS: int = 3

# Type aliases for topic-like parameter literals
MemoryPaletteLiteral = Literal["colors", "geometric_shapes", "cardinal_directions", "emojis"]
TongueTwisterThemeLiteral = Literal["nature", "animals", "workday", "whimsical", "rhyme"]
DanceStyleLiteral = Literal["rhythm_groove", "arm_raises", "step_touch", "standard"]
PushUpRepLiteral = Literal["tier_min", "tier_median", "tier_max"]


# =============================================================================
# DOMAIN EXCEPTIONS
# =============================================================================

class PersonalizationServiceError(ValueError):
    """Base exception for challenge personalization service errors."""
    pass


class ForbiddenChallengeTypeError(PersonalizationServiceError):
    """Raised when an explicitly forbidden challenge type is supplied."""
    pass


class InvalidChallengeTypeError(PersonalizationServiceError):
    """Raised when an unsupported or malformed challenge type is supplied."""
    pass


class InvalidDifficultyLevelError(PersonalizationServiceError):
    """Raised when an unsupported or malformed difficulty level is supplied."""
    pass


# =============================================================================
# SAFETY & TOPIC FILTERING HELPERS
# =============================================================================

def is_topic_disallowed(topic: Optional[str], disallowed_topics: Sequence[str]) -> bool:
    """Check whether a candidate topic-like string matches any disallowed topic.

    CRITICAL RULES:
    - Applies ONLY to topic-like fields (focus_topic, palette_theme, theme_style,
      movement_style, target_rep_styling).
    - Deterministic and case-insensitive matching.
    - No semantic embeddings, NLP classification, LLM calls, or fuzzy matching.
    - Structural/control parameters must NEVER be passed to this function.
    """
    if not topic:
        return False

    clean_topic = topic.strip().lower()
    if not clean_topic:
        return False

    # Extract word tokens from candidate topic (split on spaces, hyphens, and underscores)
    tokens: Set[str] = set(clean_topic.replace("-", " ").replace("_", " ").split())

    for disallowed in disallowed_topics:
        if not isinstance(disallowed, str):
            continue
        clean_disallowed = disallowed.strip().lower()
        if not clean_disallowed:
            continue

        # Exact match
        if clean_disallowed == clean_topic:
            return True

        # Candidate topic contains the disallowed token as a distinct word
        if clean_disallowed in tokens:
            return True

        # Disallowed phrase is a distinct substring of the candidate topic
        if clean_disallowed in clean_topic:
            return True

    return False


def sanitize_input_signatures(
    raw_signatures: Optional[Sequence[Optional[str]]],
    max_capacity: int = MAX_WINDOW_CAPACITY,
) -> List[str]:
    """Sanitize and bound caller-supplied recent structural signatures.

    GUARANTEES:
    - Discards invalid, non-string, or PII-containing signatures safely.
    - Bounded to max_capacity entries (<= 5).
    - Preserves ordering from newest to oldest.
    """
    if not raw_signatures:
        return []

    clean_list: List[str] = []
    for sig in raw_signatures:
        if not isinstance(sig, str):
            continue
        try:
            valid_sig = validate_structural_signature(sig)
            if valid_sig not in clean_list:
                clean_list.append(valid_sig)
        except (ValueError, Exception):
            continue

        if len(clean_list) >= max_capacity:
            break

    return clean_list


# =============================================================================
# CHALLENGE PERSONALIZATION SERVICE
# =============================================================================

class ChallengePersonalizationService:
    """Authoritative service generating PersonalizedChallengeProfile under strict precedence."""

    def personalize(
        self,
        challenge_type: str,
        difficulty_level: str,
        safe_context: Optional[SafePersonalizationContext] = None,
        behavioral_signals: Optional[BehavioralPersonalizationSignals] = None,
        recent_structural_signatures: Optional[Sequence[Optional[str]]] = None,
    ) -> PersonalizedChallengeProfile:
        """Personalize challenge content parameters under strict authoritative precedence.

        PRECEDENCE ORDER:
        1. SAFETY (type validation, difficulty validation, topic constraint enforcement)
        2. CHALLENGE TYPE (authoritative, strictly immutable)
        3. DIFFICULTY (authoritative, strictly immutable)
        4. EXPLICIT USER PREFERENCES (preferred_theme, duration, language)
        5. BEHAVIORAL SIGNALS (snooze, failures, success rate, retry)
        6. STRUCTURAL REPETITION (deterministic alternative ladder, max 3 attempts)
        7. SAFE DEFAULTS (canonical typed defaults)
        """
        # ---------------------------------------------------------------------
        # 1. SAFETY & INPUT VALIDATION (Level 1, 2, 3)
        # ---------------------------------------------------------------------
        clean_type = self._validate_and_canonicalize_challenge_type(challenge_type)
        clean_diff = self._validate_and_canonicalize_difficulty(difficulty_level)

        resolved_safe_context = (
            safe_context if isinstance(safe_context, SafePersonalizationContext)
            else SafePersonalizationContext(desired_duration_seconds=None, preferred_theme=None)
        )

        resolved_signals = (
            behavioral_signals if isinstance(behavioral_signals, BehavioralPersonalizationSignals)
            else BehavioralPersonalizationSignals()
        )

        clean_recent_signatures = sanitize_input_signatures(recent_structural_signatures)

        # ---------------------------------------------------------------------
        # 2. CONSTRUCT INITIAL CANDIDATE PROFILE (Levels 4, 5, 7)
        # ---------------------------------------------------------------------
        initial_params = self._build_parameters_for_type(
            challenge_type=clean_type,
            difficulty_level=clean_diff,
            safe_context=resolved_safe_context,
            behavioral_signals=resolved_signals,
            attempt_index=0,
        )

        candidate_profile = PersonalizedChallengeProfile(
            challenge_type=clean_type,
            difficulty_level=clean_diff,
            safe_context=resolved_safe_context,
            behavioral_signals=resolved_signals,
            recent_structural_signatures=clean_recent_signatures,
            typed_parameters=initial_params,
        )

        # ---------------------------------------------------------------------
        # 3. REPETITION AVOIDANCE & ALTERNATIVE RESOLUTION (Level 6)
        # ---------------------------------------------------------------------
        final_profile = self._resolve_repetition(
            candidate_profile=candidate_profile,
            clean_type=clean_type,
            clean_diff=clean_diff,
            safe_context=resolved_safe_context,
            behavioral_signals=resolved_signals,
            recent_signatures=clean_recent_signatures,
        )

        return final_profile

    # =========================================================================
    # TYPE & DIFFICULTY VALIDATION (Strict Immutability)
    # =========================================================================

    def _validate_and_canonicalize_challenge_type(self, challenge_type: str) -> CanonicalChallengeType:
        """Validate challenge type against forbidden and valid canonical sets."""
        if not isinstance(challenge_type, str):
            raise InvalidChallengeTypeError("Challenge type must be a valid non-empty string.")

        clean = challenge_type.strip().lower()
        if not clean:
            raise InvalidChallengeTypeError("Challenge type cannot be empty or whitespace.")

        if clean in FORBIDDEN_CHALLENGE_TYPES:
            raise ForbiddenChallengeTypeError(
                f"Challenge type '{challenge_type}' is strictly forbidden. Memory challenges forbid number guessing."
            )

        if clean not in VALID_CANONICAL_CHALLENGE_TYPES:
            raise InvalidChallengeTypeError(
                f"Invalid challenge type '{challenge_type}'. Must be one of: {sorted(list(VALID_CANONICAL_CHALLENGE_TYPES))}."
            )

        return cast(CanonicalChallengeType, clean)

    def _validate_and_canonicalize_difficulty(self, difficulty_level: str) -> CanonicalDifficultyLevel:
        """Validate concrete difficulty tier against canonical set ('easy', 'medium', 'hard')."""
        if not isinstance(difficulty_level, str):
            raise InvalidDifficultyLevelError("Difficulty level must be a valid non-empty string.")

        clean = difficulty_level.strip().lower()
        if not clean:
            raise InvalidDifficultyLevelError("Difficulty level cannot be empty or whitespace.")

        if clean not in VALID_CANONICAL_DIFFICULTIES:
            raise InvalidDifficultyLevelError(
                f"Invalid difficulty '{difficulty_level}'. Must be concrete: 'easy', 'medium', or 'hard'."
            )

        return cast(CanonicalDifficultyLevel, clean)

    # =========================================================================
    # REPETITION RESOLUTION ENGINE (Level 6)
    # =========================================================================

    def _resolve_repetition(
        self,
        candidate_profile: PersonalizedChallengeProfile,
        clean_type: CanonicalChallengeType,
        clean_diff: CanonicalDifficultyLevel,
        safe_context: SafePersonalizationContext,
        behavioral_signals: BehavioralPersonalizationSignals,
        recent_signatures: List[str],
    ) -> PersonalizedChallengeProfile:
        """Evaluate structural repetition and attempt up to MAX_REPETITION_ATTEMPTS alternatives."""
        if not recent_signatures:
            return candidate_profile

        initial_sig = build_signature_from_profile(candidate_profile)
        if not is_structural_repeat(initial_sig, recent_signatures):
            return candidate_profile

        # Candidate signature matches history -> attempt deterministic alternatives
        for attempt in range(1, MAX_REPETITION_ATTEMPTS + 1):
            alt_params = self._build_parameters_for_type(
                challenge_type=clean_type,
                difficulty_level=clean_diff,
                safe_context=safe_context,
                behavioral_signals=behavioral_signals,
                attempt_index=attempt,
            )

            alt_profile = PersonalizedChallengeProfile(
                challenge_type=clean_type,
                difficulty_level=clean_diff,
                safe_context=safe_context,
                behavioral_signals=behavioral_signals,
                recent_structural_signatures=recent_signatures,
                typed_parameters=alt_params,
            )

            alt_sig = build_signature_from_profile(alt_profile)
            if not is_structural_repeat(alt_sig, recent_signatures):
                return alt_profile

        # If all deterministic alternatives repeat, return the safest valid candidate (Level 7)
        # Authoritative type and difficulty remain completely untouched.
        return candidate_profile

    # =========================================================================
    # DISPATCHER FOR PARAMETER BUILDERS
    # =========================================================================

    def _build_parameters_for_type(
        self,
        challenge_type: CanonicalChallengeType,
        difficulty_level: CanonicalDifficultyLevel,
        safe_context: SafePersonalizationContext,
        behavioral_signals: BehavioralPersonalizationSignals,
        attempt_index: int,
    ) -> PersonalizationParamsType:
        """Dispatch typed parameter construction for each canonical challenge type."""
        if challenge_type == "math":
            return self._build_math_params(difficulty_level, safe_context, behavioral_signals, attempt_index)
        elif challenge_type == "memory":
            return self._build_memory_params(difficulty_level, safe_context, behavioral_signals, attempt_index)
        elif challenge_type == "tongue_twister":
            return self._build_tongue_twister_params(difficulty_level, safe_context, behavioral_signals, attempt_index)
        elif challenge_type == "dance":
            return self._build_dance_params(difficulty_level, safe_context, behavioral_signals, attempt_index)
        elif challenge_type == "push_ups":
            return self._build_push_ups_params(difficulty_level, safe_context, behavioral_signals, attempt_index)

        raise InvalidChallengeTypeError(f"Unsupported challenge type: '{challenge_type}'.")

    # =========================================================================
    # 1. MATH PARAMETER PERSONALIZATION
    # =========================================================================

    def _build_math_params(
        self,
        diff: CanonicalDifficultyLevel,
        safe_context: SafePersonalizationContext,
        behavioral: BehavioralPersonalizationSignals,
        attempt_index: int,
    ) -> MathPersonalizationParams:
        """Build deterministic MathPersonalizationParams.

        Parameters:
        - focus_topic: Topic-like, validated against disallowed_topics and SAFE_TOPIC_REGEX.
        - preferred_operation: Control parameter (not a topic).
        - operand_scale_preference: Control parameter (not a topic).
        """
        # Topic Safety: focus_topic
        raw_theme = safe_context.preferred_theme
        focus_topic: Optional[str] = None
        if raw_theme:
            clean_theme = raw_theme.strip()
            # Must satisfy safe topic regex, bounds, and NOT be disallowed
            if (
                len(clean_theme) <= 30
                and SAFE_TOPIC_REGEX.match(clean_theme)
                and not is_topic_disallowed(clean_theme, safe_context.disallowed_topics)
            ):
                focus_topic = clean_theme

        # Behavioral friction indicators
        is_high_friction = (
            behavioral.recent_snooze_level == "high"
            or behavioral.recent_failure_count >= 2
            or (behavioral.recent_snooze_level == "moderate" and behavioral.recent_failure_count >= 1)
            or (behavioral.historical_success_rate is not None and behavioral.historical_success_rate < 0.4)
        )
        is_high_success = (
            behavioral.historical_success_rate is not None
            and behavioral.historical_success_rate >= 0.75
            and behavioral.recent_failure_count == 0
            and behavioral.recent_snooze_level in ("none", "low")
        )

        # Baseline Operation & Scale selection within Authoritative Difficulty
        if diff == "easy":
            base_op: Literal["addition", "subtraction", "multiplication", "division", "mixed"] = "addition"
            base_scale: Literal["standard", "compact"] = "compact"
        elif diff == "medium":
            base_op = "multiplication"
            base_scale = "standard"
        else:  # hard
            base_op = "mixed"
            base_scale = "standard"

        # Explicit Preference: desired_duration_seconds
        if safe_context.desired_duration_seconds is not None:
            if safe_context.desired_duration_seconds < 25:
                base_scale = "compact"
            elif safe_context.desired_duration_seconds >= 60:
                base_scale = "standard"

        # Behavioral adjustment (within same difficulty tier)
        if is_high_friction:
            base_scale = "compact"
            if diff in ("easy", "medium"):
                base_op = "addition"
            else:
                base_op = "subtraction"
        elif is_high_success:
            base_scale = "standard"
            if diff == "easy":
                base_op = "addition"
            elif diff == "medium":
                base_op = "multiplication"
            else:
                base_op = "mixed"
        elif behavioral.is_retry_attempt:
            # Vary structure from standard to break failure loop
            if diff == "easy":
                base_op = "subtraction"
                base_scale = "compact"
            elif diff == "medium":
                base_op = "mixed"
                base_scale = "compact"
            else:
                base_op = "subtraction"
                base_scale = "standard"

        # Structural Repetition Alternative Ladder (max 3 attempts)
        # Lowest priority: operand_scale_preference, Secondary: preferred_operation
        op_cycle = {
            "addition": "subtraction",
            "subtraction": "multiplication",
            "multiplication": "division",
            "division": "mixed",
            "mixed": "addition",
        }

        final_op = base_op
        final_scale = base_scale

        if attempt_index == 1:
            # Attempt 1: toggle scale
            final_scale = "standard" if base_scale == "compact" else "compact"
        elif attempt_index == 2:
            # Attempt 2: rotate operation, keep base scale
            final_op = cast(Literal["addition", "subtraction", "multiplication", "division", "mixed"], op_cycle[base_op])
        elif attempt_index >= 3:
            # Attempt 3: rotate operation and toggle scale
            final_op = cast(Literal["addition", "subtraction", "multiplication", "division", "mixed"], op_cycle[base_op])
            final_scale = "standard" if base_scale == "compact" else "compact"

        return MathPersonalizationParams(
            focus_topic=focus_topic,
            preferred_operation=final_op,
            operand_scale_preference=final_scale,
        )

    # =========================================================================
    # 2. MEMORY PARAMETER PERSONALIZATION
    # =========================================================================

    def _build_memory_params(
        self,
        diff: CanonicalDifficultyLevel,
        safe_context: SafePersonalizationContext,
        behavioral: BehavioralPersonalizationSignals,
        attempt_index: int,
    ) -> MemoryPersonalizationParams:
        """Build deterministic MemoryPersonalizationParams.

        Parameters:
        - palette_theme: Topic-like, validated against disallowed_topics.
        - preferred_mode: Control parameter (not a topic).
        """
        all_palettes: List[MemoryPaletteLiteral] = [
            "colors",
            "geometric_shapes",
            "cardinal_directions",
            "emojis",
        ]

        # Filter safe palettes against disallowed_topics
        safe_palettes: List[MemoryPaletteLiteral] = [
            p for p in all_palettes if not is_topic_disallowed(p, safe_context.disallowed_topics)
        ]
        if not safe_palettes:
            safe_palettes = ["colors"]  # canonical fallback

        # Check explicit preference
        preferred_palette: Optional[MemoryPaletteLiteral] = None
        if safe_context.preferred_theme:
            clean_theme = safe_context.preferred_theme.strip().lower()
            theme_map = {
                "colors": "colors",
                "geometric_shapes": "geometric_shapes",
                "shapes": "geometric_shapes",
                "cardinal_directions": "cardinal_directions",
                "directions": "cardinal_directions",
                "emojis": "emojis",
                "emoji": "emojis",
            }
            if clean_theme in theme_map:
                candidate = cast(MemoryPaletteLiteral, theme_map[clean_theme])
                if not is_topic_disallowed(candidate, safe_context.disallowed_topics):
                    preferred_palette = candidate

        # Behavioral indicators
        is_high_friction = (
            behavioral.recent_snooze_level == "high"
            or behavioral.recent_failure_count >= 2
            or (behavioral.recent_snooze_level == "moderate" and behavioral.recent_failure_count >= 1)
            or (behavioral.historical_success_rate is not None and behavioral.historical_success_rate < 0.4)
        )
        is_high_success = (
            behavioral.historical_success_rate is not None
            and behavioral.historical_success_rate >= 0.75
            and behavioral.recent_failure_count == 0
            and behavioral.recent_snooze_level in ("none", "low")
        )

        # Baseline mode & palette by difficulty tier
        if diff == "easy":
            base_mode: Literal["visual_sequence", "spatial_pattern_recall", "dynamic_spatial_path", "symbol_chronological_order"] = "visual_sequence"
            base_palette: MemoryPaletteLiteral = safe_palettes[0]
        elif diff == "medium":
            base_mode = "visual_sequence"
            base_palette = safe_palettes[min(1, len(safe_palettes) - 1)]
        else:  # hard
            base_mode = "spatial_pattern_recall"
            base_palette = safe_palettes[min(2, len(safe_palettes) - 1)]

        if preferred_palette:
            base_palette = preferred_palette

        # Explicit Preference: desired_duration_seconds
        if safe_context.desired_duration_seconds is not None:
            if safe_context.desired_duration_seconds < 25:
                base_mode = "visual_sequence"
            elif safe_context.desired_duration_seconds >= 60 and diff != "easy":
                base_mode = "spatial_pattern_recall"

        # Behavioral adjustments (Level 5 must not overwrite Level 4 explicit preferences)
        if is_high_friction:
            base_mode = "visual_sequence"
            if not preferred_palette:
                base_palette = safe_palettes[0]
        elif is_high_success:
            if diff == "easy":
                base_mode = "visual_sequence"
            elif diff == "medium":
                base_mode = "spatial_pattern_recall"
            else:
                base_mode = "dynamic_spatial_path"
            if not preferred_palette:
                base_palette = safe_palettes[-1]
        elif behavioral.is_retry_attempt:
            base_mode = "spatial_pattern_recall" if base_mode == "visual_sequence" else "visual_sequence"

        # Repetition Alternative Ladder
        # Lowest priority: palette_theme, Secondary: preferred_mode
        final_palette: MemoryPaletteLiteral = base_palette
        final_mode = base_mode

        if attempt_index == 1 and len(safe_palettes) > 1:
            idx = (safe_palettes.index(base_palette) + 1) % len(safe_palettes) if base_palette in safe_palettes else 0
            final_palette = safe_palettes[idx]
        elif attempt_index == 2 and len(safe_palettes) > 2:
            idx = (safe_palettes.index(base_palette) + 2) % len(safe_palettes) if base_palette in safe_palettes else 0
            final_palette = safe_palettes[idx]
        elif attempt_index >= 3:
            # Rotate mode
            mode_cycle = {
                "visual_sequence": "spatial_pattern_recall",
                "spatial_pattern_recall": "dynamic_spatial_path",
                "dynamic_spatial_path": "symbol_chronological_order",
                "symbol_chronological_order": "visual_sequence",
            }
            final_mode = cast(
                Literal["visual_sequence", "spatial_pattern_recall", "dynamic_spatial_path", "symbol_chronological_order"],
                mode_cycle[base_mode],
            )

        return MemoryPersonalizationParams(
            preferred_mode=final_mode,
            palette_theme=cast(
                Optional[Literal["colors", "geometric_shapes", "cardinal_directions", "emojis"]],
                final_palette,
            ),
        )

    # =========================================================================
    # 3. TONGUE TWISTER PARAMETER PERSONALIZATION
    # =========================================================================

    def _build_tongue_twister_params(
        self,
        diff: CanonicalDifficultyLevel,
        safe_context: SafePersonalizationContext,
        behavioral: BehavioralPersonalizationSignals,
        attempt_index: int,
    ) -> TongueTwisterPersonalizationParams:
        """Build deterministic TongueTwisterPersonalizationParams.

        Parameters:
        - theme_style: Topic-like, validated against disallowed_topics.
        - target_sound_family: Control/phonetic parameter (not a topic).
        """
        all_themes: List[TongueTwisterThemeLiteral] = [
            "nature",
            "animals",
            "workday",
            "whimsical",
            "rhyme",
        ]
        safe_themes: List[TongueTwisterThemeLiteral] = [
            t for t in all_themes if not is_topic_disallowed(t, safe_context.disallowed_topics)
        ]
        if not safe_themes:
            safe_themes = ["nature"]

        preferred_theme_style: Optional[TongueTwisterThemeLiteral] = None
        if safe_context.preferred_theme:
            clean_theme = safe_context.preferred_theme.strip().lower()
            if clean_theme in all_themes:
                candidate = cast(TongueTwisterThemeLiteral, clean_theme)
                if not is_topic_disallowed(candidate, safe_context.disallowed_topics):
                    preferred_theme_style = candidate

        is_high_friction = (
            behavioral.recent_snooze_level == "high"
            or behavioral.recent_failure_count >= 2
            or (behavioral.recent_snooze_level == "moderate" and behavioral.recent_failure_count >= 1)
            or (behavioral.historical_success_rate is not None and behavioral.historical_success_rate < 0.4)
        )
        is_high_success = (
            behavioral.historical_success_rate is not None
            and behavioral.historical_success_rate >= 0.75
            and behavioral.recent_failure_count == 0
            and behavioral.recent_snooze_level in ("none", "low")
        )

        if diff == "easy":
            base_sound: Literal["sibilants", "plosives", "liquids", "nasals", "any"] = "sibilants"
            base_theme: TongueTwisterThemeLiteral = safe_themes[0]
        elif diff == "medium":
            base_sound = "plosives"
            base_theme = safe_themes[min(1, len(safe_themes) - 1)]
        else:  # hard
            base_sound = "liquids"
            base_theme = safe_themes[min(2, len(safe_themes) - 1)]

        if preferred_theme_style:
            base_theme = preferred_theme_style

        # Behavioral adjustments (Level 5 must not overwrite Level 4 explicit preferences)
        if is_high_friction:
            base_sound = "sibilants"
            if not preferred_theme_style:
                base_theme = "rhyme" if "rhyme" in safe_themes else safe_themes[0]
        elif is_high_success:
            base_sound = "plosives" if diff == "easy" else "liquids"
            if not preferred_theme_style:
                base_theme = "whimsical" if "whimsical" in safe_themes else safe_themes[-1]
        elif behavioral.is_retry_attempt:
            base_sound = "plosives" if base_sound == "sibilants" else "sibilants"

        # Repetition Alternative Ladder
        # Lowest priority: theme_style, Secondary: target_sound_family
        final_theme: TongueTwisterThemeLiteral = base_theme
        final_sound = base_sound

        if attempt_index == 1 and len(safe_themes) > 1:
            idx = (safe_themes.index(cast(TongueTwisterThemeLiteral, base_theme)) + 1) % len(safe_themes) if base_theme in safe_themes else 0
            final_theme = safe_themes[idx]
        elif attempt_index == 2 and len(safe_themes) > 2:
            idx = (safe_themes.index(cast(TongueTwisterThemeLiteral, base_theme)) + 2) % len(safe_themes) if base_theme in safe_themes else 0
            final_theme = safe_themes[idx]
        elif attempt_index >= 3:
            sound_cycle = {
                "sibilants": "plosives",
                "plosives": "liquids",
                "liquids": "nasals",
                "nasals": "any",
                "any": "sibilants",
            }
            final_sound = cast(Literal["sibilants", "plosives", "liquids", "nasals", "any"], sound_cycle[base_sound])

        return TongueTwisterPersonalizationParams(
            target_sound_family=final_sound,
            theme_style=cast(
                Optional[Literal["nature", "animals", "workday", "whimsical", "rhyme"]],
                final_theme,
            ),
        )

    # =========================================================================
    # 4. DANCE PARAMETER PERSONALIZATION
    # =========================================================================

    def _build_dance_params(
        self,
        diff: CanonicalDifficultyLevel,
        safe_context: SafePersonalizationContext,
        behavioral: BehavioralPersonalizationSignals,
        attempt_index: int,
    ) -> DancePersonalizationParams:
        """Build deterministic DancePersonalizationParams.

        Parameters:
        - movement_style: Topic-like, validated against disallowed_topics.
        - pacing: Control parameter (not a topic).
        """
        all_styles: List[DanceStyleLiteral] = [
            "standard",
            "step_touch",
            "arm_raises",
            "rhythm_groove",
        ]
        safe_styles: List[DanceStyleLiteral] = [
            s for s in all_styles if not is_topic_disallowed(s, safe_context.disallowed_topics)
        ]
        if not safe_styles:
            safe_styles = ["standard"]

        preferred_style: Optional[DanceStyleLiteral] = None
        if safe_context.preferred_theme:
            clean_theme = safe_context.preferred_theme.strip().lower()
            if clean_theme in all_styles:
                candidate = cast(DanceStyleLiteral, clean_theme)
                if not is_topic_disallowed(candidate, safe_context.disallowed_topics):
                    preferred_style = candidate

        is_high_friction = (
            behavioral.recent_snooze_level == "high"
            or behavioral.recent_failure_count >= 2
            or (behavioral.recent_snooze_level == "moderate" and behavioral.recent_failure_count >= 1)
            or (behavioral.historical_success_rate is not None and behavioral.historical_success_rate < 0.4)
        )
        is_high_success = (
            behavioral.historical_success_rate is not None
            and behavioral.historical_success_rate >= 0.75
            and behavioral.recent_failure_count == 0
            and behavioral.recent_snooze_level in ("none", "low")
        )

        if diff == "easy":
            base_style: DanceStyleLiteral = safe_styles[0]
            base_pacing: Literal["slow", "moderate", "dynamic"] = "moderate"
        elif diff == "medium":
            base_style = safe_styles[min(1, len(safe_styles) - 1)]
            base_pacing = "moderate"
        else:  # hard
            base_style = safe_styles[-1]
            base_pacing = "dynamic"

        if preferred_style:
            base_style = preferred_style

        # Explicit Preference: desired_duration_seconds
        if safe_context.desired_duration_seconds is not None:
            if safe_context.desired_duration_seconds < 25:
                base_pacing = "slow" if diff == "easy" else "moderate"
            elif safe_context.desired_duration_seconds >= 60 and diff != "easy":
                base_pacing = "dynamic"

        # Behavioral adjustments (Level 5 must not overwrite Level 4 explicit preferences)
        if is_high_friction:
            if not preferred_style:
                base_style = safe_styles[0]
            base_pacing = "slow" if behavioral.recent_snooze_level == "high" else "moderate"
        elif is_high_success:
            if not preferred_style:
                base_style = safe_styles[-1]
            base_pacing = "dynamic"
        elif behavioral.is_retry_attempt:
            if not preferred_style:
                base_style = safe_styles[1] if len(safe_styles) > 1 else safe_styles[0]
            base_pacing = "moderate"

        # Repetition Alternative Ladder
        # Lowest priority: pacing, Secondary: movement_style
        final_pacing = base_pacing
        final_style: DanceStyleLiteral = base_style

        pacing_cycle = {
            "moderate": "dynamic",
            "dynamic": "slow",
            "slow": "moderate",
        }

        if attempt_index == 1:
            final_pacing = cast(Literal["slow", "moderate", "dynamic"], pacing_cycle[base_pacing])
        elif attempt_index == 2:
            final_pacing = cast(Literal["slow", "moderate", "dynamic"], pacing_cycle[pacing_cycle[base_pacing]])
        elif attempt_index >= 3 and len(safe_styles) > 1:
            idx = (safe_styles.index(base_style) + 1) % len(safe_styles) if base_style in safe_styles else 0
            final_style = safe_styles[idx]

        return DancePersonalizationParams(
            movement_style=cast(
                Optional[Literal["rhythm_groove", "arm_raises", "step_touch", "standard"]],
                final_style,
            ),
            pacing=final_pacing,
        )

    # =========================================================================
    # 5. PUSH-UPS PARAMETER PERSONALIZATION
    # =========================================================================

    def _build_push_ups_params(
        self,
        diff: CanonicalDifficultyLevel,
        safe_context: SafePersonalizationContext,
        behavioral: BehavioralPersonalizationSignals,
        attempt_index: int,
    ) -> PushUpPersonalizationParams:
        """Build deterministic PushUpPersonalizationParams.

        Parameters:
        - target_rep_styling: Topic-like, validated against disallowed_topics.
        - cadence_tempo: Control parameter (not a topic).
        """
        all_rep_styles: List[PushUpRepLiteral] = [
            "tier_median",
            "tier_min",
            "tier_max",
        ]
        safe_rep_styles: List[PushUpRepLiteral] = [
            r for r in all_rep_styles if not is_topic_disallowed(r, safe_context.disallowed_topics)
        ]
        if not safe_rep_styles:
            safe_rep_styles = ["tier_median"]

        is_high_friction = (
            behavioral.recent_snooze_level == "high"
            or behavioral.recent_failure_count >= 2
            or (behavioral.recent_snooze_level == "moderate" and behavioral.recent_failure_count >= 1)
            or (behavioral.historical_success_rate is not None and behavioral.historical_success_rate < 0.4)
        )
        is_high_success = (
            behavioral.historical_success_rate is not None
            and behavioral.historical_success_rate >= 0.75
            and behavioral.recent_failure_count == 0
            and behavioral.recent_snooze_level in ("none", "low")
        )

        if diff == "easy":
            base_cadence: Literal["steady", "tempo_pause", "standard"] = "standard"
            base_rep_style: PushUpRepLiteral = cast(PushUpRepLiteral, "tier_min") if "tier_min" in safe_rep_styles else safe_rep_styles[0]
        elif diff == "medium":
            base_cadence = "standard"
            base_rep_style = cast(PushUpRepLiteral, "tier_median") if "tier_median" in safe_rep_styles else safe_rep_styles[0]
        else:  # hard
            base_cadence = "steady"
            base_rep_style = cast(PushUpRepLiteral, "tier_max") if "tier_max" in safe_rep_styles else safe_rep_styles[0]

        # Explicit Preference: desired_duration_seconds
        if safe_context.desired_duration_seconds is not None:
            if safe_context.desired_duration_seconds < 25 and "tier_min" in safe_rep_styles:
                base_rep_style = cast(PushUpRepLiteral, "tier_min")
            elif safe_context.desired_duration_seconds >= 60 and "tier_max" in safe_rep_styles:
                base_rep_style = cast(PushUpRepLiteral, "tier_max")

        if is_high_friction:
            base_cadence = "steady"
            base_rep_style = cast(PushUpRepLiteral, "tier_min") if "tier_min" in safe_rep_styles else safe_rep_styles[0]
        elif is_high_success:
            base_cadence = "tempo_pause"
            base_rep_style = cast(PushUpRepLiteral, "tier_max") if "tier_max" in safe_rep_styles else safe_rep_styles[-1]
        elif behavioral.is_retry_attempt:
            base_cadence = "steady"
            base_rep_style = cast(PushUpRepLiteral, "tier_median") if "tier_median" in safe_rep_styles else safe_rep_styles[0]

        # Repetition Alternative Ladder
        # Lowest priority: cadence_tempo, Secondary: target_rep_styling
        final_cadence = base_cadence
        final_rep_style: PushUpRepLiteral = base_rep_style

        cadence_cycle = {
            "standard": "steady",
            "steady": "tempo_pause",
            "tempo_pause": "standard",
        }

        if attempt_index == 1:
            final_cadence = cast(Literal["steady", "tempo_pause", "standard"], cadence_cycle[base_cadence])
        elif attempt_index == 2:
            final_cadence = cast(Literal["steady", "tempo_pause", "standard"], cadence_cycle[cadence_cycle[base_cadence]])
        elif attempt_index >= 3 and len(safe_rep_styles) > 1:
            idx = (safe_rep_styles.index(base_rep_style) + 1) % len(safe_rep_styles) if base_rep_style in safe_rep_styles else 0
            final_rep_style = safe_rep_styles[idx]

        return PushUpPersonalizationParams(
            cadence_tempo=final_cadence,
            target_rep_styling=cast(
                Optional[Literal["tier_min", "tier_median", "tier_max"]],
                final_rep_style,
            ),
        )


__all__ = [
    "ChallengePersonalizationService",
    "PersonalizationServiceError",
    "ForbiddenChallengeTypeError",
    "InvalidChallengeTypeError",
    "InvalidDifficultyLevelError",
    "is_topic_disallowed",
    "sanitize_input_signatures",
    "MAX_REPETITION_ATTEMPTS",
]
