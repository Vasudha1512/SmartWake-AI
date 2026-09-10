"""Deterministic Tongue Twister Answer Validator for SmartWake AI (Phase 4.4).

CRITICAL TRUST BOUNDARY:
- Never treats GenAI-provided answers as authoritative.
- Strictly validates language (English only).
- Enforces targeted non-numeric rules on passage (rejects digits and arithmetic).
- Employs a lightweight orthographic sound-pattern heuristic (not phonetics).
- Enforces application authority over repetitions and speaking duration (rejects out-of-tier values).
- Derives authoritative expected answer deterministically via whitespace normalization.
"""
import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from backend.app.core.exceptions import TongueTwisterEvaluationError
from backend.app.schemas.tongue_twister_challenge_schemas import (
    SUPPORTED_TONGUE_TWISTER_LANGUAGES,
    TongueTwisterChallengePayload,
)
from backend.app.services.genai.tongue_twister_generation_constraints import (
    FORBIDDEN_TONGUE_TWISTER_PHRASES,
    TongueTwisterGenerationConstraints,
    get_tongue_twister_difficulty_constraints,
)

# Regex matching any digit character in passage
DIGIT_REGEX = re.compile(r"\d")
ARITHMETIC_EXPR_REGEX = re.compile(r"[0-9]+[\s]*[\+\-\*\/\%][\s]*[0-9]+")

# Repeated punctuation abuse regex (e.g. ???, !!!, ---, ....)
REPEATED_PUNCTUATION_REGEX = re.compile(r"([?!.\-]){2,}")

# Common English orthographic consonant onset clusters
ORTHOGRAPHIC_ONSET_CLUSTERS: List[str] = [
    # 3-letter clusters
    "str", "spl", "spr", "scr",
    # 2-letter digraphs & blends
    "sh", "ch", "th", "ph", "wh",
    "sl", "fl", "gl", "bl", "cl", "pl",
    "br", "cr", "dr", "fr", "gr", "pr", "tr",
    "sk", "sm", "sn", "sp", "st", "sw",
]


class TongueTwisterAnswerValidator:
    """Pure in-memory validation and answer derivation engine for tongue twister challenges."""

    @classmethod
    def scan_for_forbidden_concepts(cls, text: str) -> None:
        """Scan text for context-aware forbidden phrases and prompt injection patterns."""
        if not text or not isinstance(text, str):
            return
        lower_text = text.lower()
        # Sort by length descending so longer phrases match first
        for phrase in sorted(FORBIDDEN_TONGUE_TWISTER_PHRASES, key=len, reverse=True):
            if len(phrase) <= 4 and " " not in phrase and "_" not in phrase:
                if re.search(rf"\b{re.escape(phrase)}\b", lower_text):
                    raise TongueTwisterEvaluationError(
                        f"Forbidden concept '{phrase}' detected in challenge text."
                    )
            elif phrase in lower_text:
                raise TongueTwisterEvaluationError(
                    f"Forbidden concept '{phrase}' detected in challenge text."
                )

    @classmethod
    def validate_non_numeric_passage(cls, passage: str) -> None:
        """Enforce strict non-numeric rule on tongue-twister passage text."""
        if DIGIT_REGEX.search(passage):
            raise TongueTwisterEvaluationError(
                "Tongue twister passage contains forbidden digit characters (0-9). "
                "Numbers in tongue twisters must be spelled out as words (e.g. 'thirty-three')."
            )
        if ARITHMETIC_EXPR_REGEX.search(passage):
            raise TongueTwisterEvaluationError(
                "Tongue twister passage contains forbidden arithmetic expression."
            )

    @classmethod
    def validate_text_structure(
        cls,
        passage: str,
        constraints: TongueTwisterGenerationConstraints,
    ) -> List[str]:
        """Validate text length, word count, punctuation hygiene, and degeneracy safeguard."""
        # Check repeated punctuation abuse
        if REPEATED_PUNCTUATION_REGEX.search(passage):
            raise TongueTwisterEvaluationError(
                "Tongue twister passage contains abusive repeated punctuation (e.g. '??', '!!')."
            )

        # Extract words (letters and apostrophes)
        words = re.findall(r"\b[a-zA-Z]+(?:'[a-zA-Z]+)?\b", passage)
        word_count = len(words)

        if word_count < constraints.min_word_count or word_count > constraints.max_word_count:
            raise TongueTwisterEvaluationError(
                f"Passage word count ({word_count}) is outside permitted range "
                f"[{constraints.min_word_count}, {constraints.max_word_count}] "
                f"for difficulty '{constraints.difficulty_level}'."
            )

        # Check individual word lengths
        for idx, w in enumerate(words):
            if len(w) > 22:
                raise TongueTwisterEvaluationError(
                    f"Passage contains excessively long word '{w}' ({len(w)} chars) at index {idx}."
                )

        # Degeneracy safeguard: prevent pathological single-word looping (e.g. "red red red red")
        unique_words = set(w.lower() for w in words)
        unique_ratio = len(unique_words) / word_count
        if unique_ratio < constraints.min_unique_word_ratio:
            raise TongueTwisterEvaluationError(
                f"Passage failed degeneracy safeguard (unique word ratio {unique_ratio:.2f} is below "
                f"minimum threshold {constraints.min_unique_word_ratio:.2f})."
            )

        return words

    @classmethod
    def validate_orthographic_sound_pattern(
        cls,
        words: List[str],
        constraints: TongueTwisterGenerationConstraints,
    ) -> None:
        """Validate alliteration-like sound pattern using lightweight orthographic heuristic.

        NOTE: This is explicitly a lightweight spelling-pattern heuristic, NOT a true phonetic
        or pronunciation classifier. English orthography does not represent phonemes 1:1.
        """
        onset_counts: Dict[str, int] = {}

        for word in words:
            clean_word = word.lower().lstrip("'")
            if len(clean_word) < 2:
                continue

            matched_cluster: Optional[str] = None
            for cluster in ORTHOGRAPHIC_ONSET_CLUSTERS:
                if clean_word.startswith(cluster):
                    matched_cluster = cluster
                    break

            if matched_cluster:
                onset_counts[matched_cluster] = onset_counts.get(matched_cluster, 0) + 1
            else:
                first_letter = clean_word[0]
                if first_letter.isalpha():
                    onset_counts[first_letter] = onset_counts.get(first_letter, 0) + 1

        if not onset_counts:
            raise TongueTwisterEvaluationError(
                "Passage contains insufficient valid words for sound pattern validation."
            )

        max_repetitions = max(onset_counts.values())
        distinct_repeating = sum(1 for c in onset_counts.values() if c >= 3)

        # For Easy: at least 1 onset repeated >= min_onset_repetition_count (3)
        # For Medium/Hard: dominant onset >= min_repetition OR at least 2 onsets repeated >= 3 times
        required_dominant = constraints.min_onset_repetition_count
        if max_repetitions < required_dominant and distinct_repeating < 2:
            raise TongueTwisterEvaluationError(
                f"Passage failed orthographic sound-pattern heuristic for difficulty '{constraints.difficulty_level}'. "
                f"Max repeated onset pattern was {max_repetitions} (required dominant: {required_dominant}, "
                f"or at least 2 distinct patterns repeating 3+ times). Text lacks sufficient tongue-twister alliteration."
            )

    @classmethod
    def validate_repetition_and_duration(
        cls,
        payload: TongueTwisterChallengePayload,
        constraints: TongueTwisterGenerationConstraints,
    ) -> Tuple[int, int]:
        """Validate and resolve authoritative target repetitions and speaking duration.

        CRITICAL TRUST BOUNDARY:
        - If provided by provider, values outside tier bounds MUST BE REJECTED (NO silent clamping).
        - If omitted by provider, application supplies authoritative tier defaults.
        """
        # Repetitions
        if payload.target_repetitions is not None:
            if (
                payload.target_repetitions < constraints.min_repetitions
                or payload.target_repetitions > constraints.max_repetitions
            ):
                raise TongueTwisterEvaluationError(
                    f"Provider target_repetitions ({payload.target_repetitions}) is outside authoritative range "
                    f"[{constraints.min_repetitions}, {constraints.max_repetitions}] "
                    f"for difficulty '{constraints.difficulty_level}'."
                )
            authoritative_reps = payload.target_repetitions
        else:
            authoritative_reps = constraints.default_repetitions

        # Speaking duration
        if payload.speaking_duration_seconds is not None:
            if (
                payload.speaking_duration_seconds < constraints.min_speaking_duration_seconds
                or payload.speaking_duration_seconds > constraints.max_speaking_duration_seconds
            ):
                raise TongueTwisterEvaluationError(
                    f"Provider speaking_duration_seconds ({payload.speaking_duration_seconds}) is outside authoritative range "
                    f"[{constraints.min_speaking_duration_seconds}, {constraints.max_speaking_duration_seconds}] "
                    f"for difficulty '{constraints.difficulty_level}'."
                )
            authoritative_duration = payload.speaking_duration_seconds
        else:
            authoritative_duration = constraints.default_speaking_duration_seconds

        return authoritative_reps, authoritative_duration

    @classmethod
    def derive_authoritative_answer(cls, passage: str) -> str:
        """Derive canonical authoritative expected answer via whitespace normalization."""
        return " ".join(passage.strip().split())

    @classmethod
    def validate_and_derive_answer(
        cls,
        payload: TongueTwisterChallengePayload,
        difficulty_level: str,
    ) -> Tuple[TongueTwisterChallengePayload, str, int, int]:
        """Validate tongue twister payload and derive authoritative expected answer.

        Returns:
            Tuple[TongueTwisterChallengePayload, str, int, int]:
                (payload, authoritative_expected_answer, authoritative_reps, authoritative_duration)

        Raises:
            TongueTwisterEvaluationError: On any validation, bounds, or heuristic failure.
        """
        constraints = get_tongue_twister_difficulty_constraints(difficulty_level)

        # 1. Language check
        if payload.language not in SUPPORTED_TONGUE_TWISTER_LANGUAGES:
            raise TongueTwisterEvaluationError(
                f"Unsupported language '{payload.language}'. Only English ('en') is supported."
            )

        # 2. Non-numeric passage check
        cls.validate_non_numeric_passage(payload.passage)

        # 3. Forbidden concepts & prompt-injection check
        cls.scan_for_forbidden_concepts(payload.passage)
        if payload.phonetic_focus:
            cls.scan_for_forbidden_concepts(payload.phonetic_focus)

        # 4. Text structure, length, word count, and degeneracy safeguard
        words = cls.validate_text_structure(payload.passage, constraints)

        # 5. Orthographic sound-pattern heuristic
        cls.validate_orthographic_sound_pattern(words, constraints)

        # 6. Authoritative repetition and speaking duration validation (no silent clamping)
        authoritative_reps, authoritative_duration = cls.validate_repetition_and_duration(
            payload, constraints
        )

        # 7. Authoritative expected answer derivation
        authoritative_answer = cls.derive_authoritative_answer(payload.passage)

        # 8. Optional proposed answer consistency check
        if payload.proposed_answer is not None:
            proposed_canonical = " ".join(str(payload.proposed_answer).strip().split())
            if proposed_canonical.lower() != authoritative_answer.lower():
                raise TongueTwisterEvaluationError(
                    f"LLM proposed answer '{payload.proposed_answer}' conflicts with "
                    f"derived authoritative answer '{authoritative_answer}'."
                )

        return payload, authoritative_answer, authoritative_reps, authoritative_duration

    @classmethod
    def validate_and_compute_payload(
        cls,
        raw_payload: Union[TongueTwisterChallengePayload, Dict[str, Any]],
        difficulty_level: str,
    ) -> Tuple[TongueTwisterChallengePayload, str, int, int]:
        """Validate raw dictionary or model payload and derive authoritative answer."""
        if isinstance(raw_payload, dict):
            try:
                payload_model = TongueTwisterChallengePayload(**raw_payload)
            except Exception as exc:
                raise TongueTwisterEvaluationError(f"Malformed tongue twister payload: {exc}") from exc
        elif isinstance(raw_payload, TongueTwisterChallengePayload):
            payload_model = raw_payload
        else:
            raise TongueTwisterEvaluationError(
                f"Payload must be a dictionary or TongueTwisterChallengePayload, got {type(raw_payload).__name__}."
            )

        return cls.validate_and_derive_answer(payload_model, difficulty_level)
