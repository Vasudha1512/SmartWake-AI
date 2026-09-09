"""Challenge Verification Engine for SmartWake AI.

Pure in-memory, deterministic verification engine that evaluates user submissions
against RuntimeChallenge specifications.

ARCHITECTURAL RULES:
1. Zero persistence: Does NOT create ChallengeAttempt records or mutate the database.
2. User choice preservation: The user chooses the challenge type; verification never alters it.
3. Strict non-number-guessing rule: Memory challenges strictly evaluate visual sequence,
   spatial pattern, matrix, or symbol recall. Number guessing is rejected.
4. No ML/CV/STT: Dance, tongue-twister, and push-up verification use explicit development/manual
   confirmation pathways without claiming active sensor/AI models.
"""
from typing import Any, Dict, List, Optional, Union

from backend.app.core.constants import FORBIDDEN_CHALLENGE_TYPES, VALID_CHALLENGE_TYPES
from backend.app.core.exceptions import InvalidChallengeTypeError
from backend.app.schemas.challenge_schemas import (
    ChallengeVerificationResult,
    RuntimeChallengeResponse,
)


def _extract_challenge_field(challenge: Union[RuntimeChallengeResponse, Dict[str, Any]], key: str) -> Any:
    """Extract a field from either a RuntimeChallengeResponse model or dictionary."""
    if isinstance(challenge, RuntimeChallengeResponse):
        return getattr(challenge, key, None)
    elif isinstance(challenge, dict):
        return challenge.get(key)
    return None


# =============================================================================
# 1. MATH VERIFIER
# =============================================================================
def verify_math(
    runtime_challenge: Union[RuntimeChallengeResponse, Dict[str, Any]],
    submission_data: Optional[Dict[str, Any]],
) -> ChallengeVerificationResult:
    """Verify a user's arithmetic submission against the expected answer(s).

    Supports:
    - Single question answer: {"answer": 17} or {"answer": "17"}
    - Multi-question answers list: {"answers": [11, 11, 14]} or {"answers": ["11", 11, 14]}
    """
    if submission_data is None or not isinstance(submission_data, dict):
        return ChallengeVerificationResult(
            is_successful=False,
            verification_score=0.0,
            verification_result="failed",
            failure_reason="missing_submission",
            diagnostic_details={"error": "Submission data must be a non-empty dictionary."},
        )

    expected = _extract_challenge_field(runtime_challenge, "expected_answer")
    if expected is None:
        return ChallengeVerificationResult(
            is_successful=False,
            verification_score=0.0,
            verification_result="failed",
            failure_reason="missing_expected_answer",
            diagnostic_details={"error": "Runtime challenge does not contain expected answers."},
        )

    # Normalize expected to a list of ints
    expected_list: List[int]
    if isinstance(expected, list):
        expected_list = [int(x) for x in expected]
    else:
        try:
            expected_list = [int(expected)]
        except (ValueError, TypeError):
            return ChallengeVerificationResult(
                is_successful=False,
                verification_score=0.0,
                verification_result="failed",
                failure_reason="invalid_expected_answer_format",
                diagnostic_details={"expected": expected},
            )

    # Extract submitted answer(s)
    submitted_raw = submission_data.get("answers")
    if submitted_raw is None and "answer" in submission_data:
        single_ans = submission_data.get("answer")
        if single_ans is None:
            return ChallengeVerificationResult(
                is_successful=False,
                verification_score=0.0,
                verification_result="failed",
                failure_reason="missing_answer",
                diagnostic_details={"error": "Answer field cannot be null/None."},
            )
        submitted_raw = [single_ans]

    if submitted_raw is None:
        return ChallengeVerificationResult(
            is_successful=False,
            verification_score=0.0,
            verification_result="failed",
            failure_reason="missing_answer",
            diagnostic_details={"error": "Submission must contain 'answer' or 'answers' key."},
        )

    # Convert submitted values safely to integer list
    if not isinstance(submitted_raw, list):
        submitted_raw = [submitted_raw]

    submitted_list: List[int] = []
    for idx, val in enumerate(submitted_raw):
        if val is None or val == "":
            return ChallengeVerificationResult(
                is_successful=False,
                verification_score=0.0,
                verification_result="failed",
                failure_reason="malformed_answer",
                diagnostic_details={"error": f"Answer at index {idx} is empty or None."},
            )
        try:
            submitted_list.append(int(val))
        except (ValueError, TypeError):
            return ChallengeVerificationResult(
                is_successful=False,
                verification_score=0.0,
                verification_result="failed",
                failure_reason="malformed_answer",
                diagnostic_details={"error": f"Value '{val}' could not be parsed as an integer."},
            )

    # Compare answers
    if submitted_list == expected_list:
        return ChallengeVerificationResult(
            is_successful=True,
            verification_score=1.0,
            verification_result="exact_match",
            failure_reason=None,
            diagnostic_details={
                "match": True,
                "total_questions": len(expected_list),
                "correct_count": len(expected_list),
            },
        )

    return ChallengeVerificationResult(
        is_successful=False,
        verification_score=0.0,
        verification_result="failed",
        failure_reason="incorrect_answer",
        diagnostic_details={
            "match": False,
            "total_questions": len(expected_list),
            "submitted_answers": submitted_list,
            "expected_answers": expected_list,
        },
    )


# =============================================================================
# 2. MEMORY VERIFIER (Strictly Visual/Spatial/Pattern Recall)
# =============================================================================
def verify_memory(
    runtime_challenge: Union[RuntimeChallengeResponse, Dict[str, Any]],
    submission_data: Optional[Dict[str, Any]],
) -> ChallengeVerificationResult:
    """Verify a user's visual sequence or spatial pattern recall.

    Enforces strict non-number-guessing rules. Compares:
    - visual color sequences
    - spatial positions / grid cells
    - dynamic paths
    - symbol chronological orders
    """
    if submission_data is None or not isinstance(submission_data, dict):
        return ChallengeVerificationResult(
            is_successful=False,
            verification_score=0.0,
            verification_result="failed",
            failure_reason="missing_submission",
            diagnostic_details={"error": "Submission data must be a non-empty dictionary."},
        )

    # Check for forbidden number-guessing patterns in submission
    for key, val in submission_data.items():
        key_str = str(key).lower()
        val_str = str(val).lower()
        if "number_guessing" in key_str or "number_guessing" in val_str or "guess_number" in key_str:
            raise InvalidChallengeTypeError(
                "Number guessing is strictly forbidden in SmartWake AI memory challenges."
            )

    expected = _extract_challenge_field(runtime_challenge, "expected_answer")
    if expected is None:
        return ChallengeVerificationResult(
            is_successful=False,
            verification_score=0.0,
            verification_result="failed",
            failure_reason="missing_expected_answer",
            diagnostic_details={"error": "Runtime challenge does not contain expected memory sequence."},
        )

    # Extract submitted sequence/positions/pattern
    submitted = (
        submission_data.get("sequence")
        if "sequence" in submission_data
        else submission_data.get("positions")
        if "positions" in submission_data
        else submission_data.get("pattern")
        if "pattern" in submission_data
        else submission_data.get("answers")
    )

    if submitted is None:
        return ChallengeVerificationResult(
            is_successful=False,
            verification_score=0.0,
            verification_result="failed",
            failure_reason="missing_submission",
            diagnostic_details={
                "error": "Memory submission must contain 'sequence', 'positions', or 'pattern' key."
            },
        )

    if not isinstance(submitted, (list, dict)):
        return ChallengeVerificationResult(
            is_successful=False,
            verification_score=0.0,
            verification_result="failed",
            failure_reason="malformed_submission",
            diagnostic_details={"error": "Memory submission must be a list or dictionary."},
        )

    # Handle dictionary expected (e.g. dual_alternating_pattern)
    if isinstance(expected, dict):
        if not isinstance(submitted, dict):
            return ChallengeVerificationResult(
                is_successful=False,
                verification_score=0.0,
                verification_result="failed",
                failure_reason="malformed_submission",
                diagnostic_details={"error": "Expected structured dictionary pattern."},
            )
        # Compare inner keys
        if submitted == expected:
            return ChallengeVerificationResult(
                is_successful=True,
                verification_score=1.0,
                verification_result="exact_match",
                failure_reason=None,
                diagnostic_details={"match": True, "mode": "dual_pattern"},
            )
        return ChallengeVerificationResult(
            is_successful=False,
            verification_score=0.0,
            verification_result="failed",
            failure_reason="pattern_mismatch",
            diagnostic_details={"match": False, "mode": "dual_pattern"},
        )

    # Handle list expected
    if isinstance(expected, list):
        if not isinstance(submitted, list):
            return ChallengeVerificationResult(
                is_successful=False,
                verification_score=0.0,
                verification_result="failed",
                failure_reason="malformed_submission",
                diagnostic_details={"error": "Submitted sequence must be a list."},
            )

        # Check sequence length variations
        if len(submitted) < len(expected):
            return ChallengeVerificationResult(
                is_successful=False,
                verification_score=0.0,
                verification_result="failed",
                failure_reason="partial_sequence",
                diagnostic_details={
                    "error": f"Partial sequence submitted: expected {len(expected)} items, got {len(submitted)}."
                },
            )

        if len(submitted) > len(expected):
            return ChallengeVerificationResult(
                is_successful=False,
                verification_score=0.0,
                verification_result="failed",
                failure_reason="extra_elements",
                diagnostic_details={
                    "error": f"Extra items in sequence: expected {len(expected)} items, got {len(submitted)}."
                },
            )

        # Spatial grid coordinate matching: if elements are coordinate pairs [r, c]
        is_spatial_grid = len(expected) > 0 and isinstance(expected[0], list) and len(expected[0]) == 2
        gen_content = _extract_challenge_field(runtime_challenge, "generated_content") or {}
        recall_mode = gen_content.get("recall_mode") if isinstance(gen_content, dict) else None

        if is_spatial_grid and recall_mode == "spatial_pattern_recall":
            # For un-ordered spatial cells, set comparison is appropriate
            expected_cells = {tuple(c) for c in expected if isinstance(c, list)}
            submitted_cells = {tuple(c) for c in submitted if isinstance(c, list)}
            if expected_cells == submitted_cells:
                return ChallengeVerificationResult(
                    is_successful=True,
                    verification_score=1.0,
                    verification_result="exact_match",
                    failure_reason=None,
                    diagnostic_details={"match": True, "recall_mode": "spatial_pattern_recall"},
                )
            return ChallengeVerificationResult(
                is_successful=False,
                verification_score=0.0,
                verification_result="failed",
                failure_reason="sequence_mismatch",
                diagnostic_details={"match": False, "recall_mode": "spatial_pattern_recall"},
            )

        # Ordered sequence matching (visual color sequence, dynamic path, symbols)
        if submitted == expected:
            return ChallengeVerificationResult(
                is_successful=True,
                verification_score=1.0,
                verification_result="exact_match",
                failure_reason=None,
                diagnostic_details={"match": True, "sequence_length": len(expected)},
            )

        # Check if items are right but order is wrong
        if sorted(str(s) for s in submitted) == sorted(str(e) for e in expected):
            return ChallengeVerificationResult(
                is_successful=False,
                verification_score=0.0,
                verification_result="failed",
                failure_reason="wrong_order",
                diagnostic_details={
                    "error": "Sequence contains the correct elements but in the incorrect order."
                },
            )

        return ChallengeVerificationResult(
            is_successful=False,
            verification_score=0.0,
            verification_result="failed",
            failure_reason="sequence_mismatch",
            diagnostic_details={
                "match": False,
                "submitted_length": len(submitted),
                "expected_length": len(expected),
            },
        )

    return ChallengeVerificationResult(
        is_successful=False,
        verification_score=0.0,
        verification_result="failed",
        failure_reason="unsupported_memory_structure",
        diagnostic_details={"error": "Unsupported expected memory structure."},
    )


# =============================================================================
# 3. DANCE VERIFIER (Development / Manual Verification)
# =============================================================================
def verify_dance(
    runtime_challenge: Union[RuntimeChallengeResponse, Dict[str, Any]],
    submission_data: Optional[Dict[str, Any]],
) -> ChallengeVerificationResult:
    """Verify dance movement routine via development / manual confirmation.

    DOES NOT claim real computer vision or pose estimation is active.
    """
    if submission_data is None or not isinstance(submission_data, dict):
        return ChallengeVerificationResult(
            is_successful=False,
            verification_score=0.0,
            verification_result="failed",
            failure_reason="malformed_submission",
            diagnostic_details={
                "verification_mode": "manual_development",
                "error": "Submission data must be a valid dictionary.",
            },
        )

    confirmed = (
        submission_data.get("confirmed")
        if "confirmed" in submission_data
        else submission_data.get("completed")
        if "completed" in submission_data
        else submission_data.get("routine_completed")
    )

    if confirmed is True:
        return ChallengeVerificationResult(
            is_successful=True,
            verification_score=1.0,
            verification_result="manual_confirmed",
            failure_reason=None,
            diagnostic_details={
                "verification_mode": "development_manual",
                "camera_cv_active": False,
                "note": "Manual development confirmation path. Real CV pose estimation deferred.",
            },
        )
    elif confirmed is False:
        return ChallengeVerificationResult(
            is_successful=False,
            verification_score=0.0,
            verification_result="manual_rejected",
            failure_reason="routine_incomplete",
            diagnostic_details={
                "verification_mode": "development_manual",
                "camera_cv_active": False,
                "note": "User or test explicitly flagged routine as incomplete.",
            },
        )

    return ChallengeVerificationResult(
        is_successful=False,
        verification_score=0.0,
        verification_result="failed",
        failure_reason="malformed_submission",
        diagnostic_details={
            "verification_mode": "development_manual",
            "error": "Dance submission must contain a boolean 'confirmed' or 'completed' field.",
        },
    )


# =============================================================================
# 4. TONGUE TWISTER VERIFIER (Development / Manual Verification)
# =============================================================================
def verify_tongue_twister(
    runtime_challenge: Union[RuntimeChallengeResponse, Dict[str, Any]],
    submission_data: Optional[Dict[str, Any]],
) -> ChallengeVerificationResult:
    """Verify tongue twister enunciation via development / manual confirmation.

    DOES NOT claim speech recognition or microphone STT is active.
    """
    if submission_data is None or not isinstance(submission_data, dict):
        return ChallengeVerificationResult(
            is_successful=False,
            verification_score=0.0,
            verification_result="failed",
            failure_reason="malformed_submission",
            diagnostic_details={
                "verification_mode": "manual_development",
                "error": "Submission data must be a valid dictionary.",
            },
        )

    confirmed = submission_data.get("confirmed")

    # Also support development transcript matching if supplied
    if confirmed is None and "transcript" in submission_data:
        transcript = str(submission_data["transcript"]).strip().lower()
        expected = str(_extract_challenge_field(runtime_challenge, "expected_answer") or "").strip().lower()
        confirmed = (transcript == expected)

    if confirmed is True:
        return ChallengeVerificationResult(
            is_successful=True,
            verification_score=1.0,
            verification_result="manual_confirmed",
            failure_reason=None,
            diagnostic_details={
                "verification_mode": "development_manual",
                "speech_stt_active": False,
                "note": "Manual development confirmation path. Real STT speech recognition deferred.",
            },
        )
    elif confirmed is False:
        return ChallengeVerificationResult(
            is_successful=False,
            verification_score=0.0,
            verification_result="manual_rejected",
            failure_reason="articulation_unconfirmed",
            diagnostic_details={
                "verification_mode": "development_manual",
                "speech_stt_active": False,
                "note": "User or test explicitly rejected articulation confirmation.",
            },
        )

    return ChallengeVerificationResult(
        is_successful=False,
        verification_score=0.0,
        verification_result="failed",
        failure_reason="malformed_submission",
        diagnostic_details={
            "verification_mode": "development_manual",
            "error": "Tongue twister submission must contain a boolean 'confirmed' or 'transcript' field.",
        },
    )


# =============================================================================
# 5. PUSH-UPS VERIFIER (Development / Manual Verification)
# =============================================================================
def verify_push_ups(
    runtime_challenge: Union[RuntimeChallengeResponse, Dict[str, Any]],
    submission_data: Optional[Dict[str, Any]],
) -> ChallengeVerificationResult:
    """Verify calisthenics push-ups via development / manual confirmation.

    DOES NOT claim camera repetition counting is active.
    """
    if submission_data is None or not isinstance(submission_data, dict):
        return ChallengeVerificationResult(
            is_successful=False,
            verification_score=0.0,
            verification_result="failed",
            failure_reason="malformed_submission",
            diagnostic_details={
                "verification_mode": "manual_development",
                "error": "Submission data must be a valid dictionary.",
            },
        )

    # Check for direct repetition count submission: {"reps_completed": 10}
    expected = _extract_challenge_field(runtime_challenge, "expected_answer")
    target_reps = 10
    if isinstance(expected, dict) and "target_repetitions" in expected:
        target_reps = int(expected["target_repetitions"])
    elif isinstance(expected, (int, float)):
        target_reps = int(expected)

    if "reps_completed" in submission_data:
        try:
            reps = int(submission_data["reps_completed"])
            if reps >= target_reps:
                return ChallengeVerificationResult(
                    is_successful=True,
                    verification_score=1.0,
                    verification_result="manual_confirmed",
                    failure_reason=None,
                    diagnostic_details={
                        "verification_mode": "development_manual",
                        "camera_cv_active": False,
                        "reps_completed": reps,
                        "target_repetitions": target_reps,
                        "note": "Manual repetition reporting path. Real vision counter deferred.",
                    },
                )
            else:
                return ChallengeVerificationResult(
                    is_successful=False,
                    verification_score=0.0,
                    verification_result="manual_rejected",
                    failure_reason="target_reps_not_met",
                    diagnostic_details={
                        "verification_mode": "development_manual",
                        "camera_cv_active": False,
                        "reps_completed": reps,
                        "target_repetitions": target_reps,
                    },
                )
        except (ValueError, TypeError):
            return ChallengeVerificationResult(
                is_successful=False,
                verification_score=0.0,
                verification_result="failed",
                failure_reason="malformed_submission",
                diagnostic_details={"error": "Field 'reps_completed' must be an integer."},
            )

    # Check for boolean confirmed
    confirmed = submission_data.get("confirmed")
    if confirmed is True:
        return ChallengeVerificationResult(
            is_successful=True,
            verification_score=1.0,
            verification_result="manual_confirmed",
            failure_reason=None,
            diagnostic_details={
                "verification_mode": "development_manual",
                "camera_cv_active": False,
                "note": "Manual development confirmation path. Real vision counter deferred.",
            },
        )
    elif confirmed is False:
        return ChallengeVerificationResult(
            is_successful=False,
            verification_score=0.0,
            verification_result="manual_rejected",
            failure_reason="target_reps_not_met",
            diagnostic_details={
                "verification_mode": "development_manual",
                "camera_cv_active": False,
            },
        )

    return ChallengeVerificationResult(
        is_successful=False,
        verification_score=0.0,
        verification_result="failed",
        failure_reason="malformed_submission",
        diagnostic_details={
            "verification_mode": "development_manual",
            "error": "Push-up submission must contain 'confirmed' boolean or 'reps_completed' integer.",
        },
    )


# =============================================================================
# DISPATCHER
# =============================================================================
def verify_challenge(
    runtime_challenge: Union[RuntimeChallengeResponse, Dict[str, Any]],
    submission_data: Optional[Dict[str, Any]],
) -> ChallengeVerificationResult:
    """Route verification to the appropriate type verifier based on challenge_type.

    Args:
        runtime_challenge: RuntimeChallengeResponse object or dictionary.
        submission_data: User-submitted response payload.

    Returns:
        ChallengeVerificationResult: Verification outcome, score, and diagnostics.

    Raises:
        InvalidChallengeTypeError: If challenge_type is unsupported or forbidden.
        ValueError: If runtime_challenge is missing or invalid.
    """
    if runtime_challenge is None:
        raise ValueError("RuntimeChallenge cannot be None.")

    c_type = _extract_challenge_field(runtime_challenge, "challenge_type")
    if not c_type:
        raise ValueError("RuntimeChallenge is missing 'challenge_type'.")

    clean_type = str(c_type).strip().lower()

    if clean_type in FORBIDDEN_CHALLENGE_TYPES:
        raise InvalidChallengeTypeError(
            f"Challenge type '{clean_type}' is strictly forbidden. "
            f"Memory challenges must NOT be implemented as number guessing."
        )

    if clean_type not in VALID_CHALLENGE_TYPES:
        raise InvalidChallengeTypeError(
            f"Invalid challenge type '{clean_type}'. Must be one of: {sorted(list(VALID_CHALLENGE_TYPES))}."
        )

    if clean_type == "math":
        return verify_math(runtime_challenge, submission_data)
    elif clean_type == "memory":
        return verify_memory(runtime_challenge, submission_data)
    elif clean_type == "dance":
        return verify_dance(runtime_challenge, submission_data)
    elif clean_type == "tongue_twister":
        return verify_tongue_twister(runtime_challenge, submission_data)
    elif clean_type == "push_ups":
        return verify_push_ups(runtime_challenge, submission_data)

    raise InvalidChallengeTypeError(f"Unsupported challenge type '{clean_type}'.")
