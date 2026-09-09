"""Challenge Execution and Attempt Tracking Service for SmartWake AI.

Connects WakeSession, RuntimeChallenge Generation, and Phase 2.8 Verification
to record the historical execution and outcomes of alarm wake-up challenges.

ARCHITECTURAL RULES:
1. Reuses existing ChallengeAttempt model; zero schema modifications or migrations.
2. Preserves user-selected challenge type throughout execution and retries.
3. Strictly non-number-guessing for memory challenges.
4. Directly invokes Phase 2.8 verify_challenge without duplicating verification logic.
5. Atomic transaction safety across WakeSession state updates and attempt tracking.
"""
import json
from typing import Any, Dict, List, Optional
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.datetime_utils import diff_seconds, now_utc_naive
from backend.app.core.exceptions import (
    ActiveChallengeAttemptExistsError,
    ChallengeAttemptCompletedError,
    ChallengeAttemptNotFoundError,
    ChallengeAttemptOwnershipError,
    ChallengeNotFoundError,
    InactiveChallengeError,
    InvalidChallengeTypeError,
    InvalidSessionTransitionError,
    WakeSessionNotFoundError,
)
from backend.app.models.alarm import Alarm
from backend.app.models.challenge import Challenge
from backend.app.models.challenge_attempt import ChallengeAttempt
from backend.app.models.wake_session import WakeSession
from backend.app.schemas.challenge_schemas import (
    ChallengeAttemptStartRequest,
    RuntimeChallengeGenerationRequest,
)
from backend.app.services.challenge_generation_service import generate_challenge
from backend.app.services.challenge_verification_service import verify_challenge
from backend.app.services.wake_session_service import (
    STATUS_COMPLETED,
    STATUS_IN_CHALLENGE,
    STATUS_RINGING,
    STATUS_SNOOZED,
    TERMINAL_STATUSES,
    complete_wake_session,
)


def start_challenge_attempt(
    db: Session, request: ChallengeAttemptStartRequest
) -> ChallengeAttempt:
    """Start and persist a new challenge execution attempt for an active WakeSession.

    Args:
        db: Active SQLAlchemy database session.
        request: ChallengeAttemptStartRequest parameters.

    Returns:
        ChallengeAttempt: The newly created and persisted attempt record.

    Raises:
        WakeSessionNotFoundError: If wake session does not exist.
        ChallengeAttemptOwnershipError: If wake session does not belong to user.
        InvalidSessionTransitionError: If wake session is in terminal status.
        ActiveChallengeAttemptExistsError: If an uncompleted attempt is already active.
        ChallengeNotFoundError: If explicitly requested template ID is not found.
        InactiveChallengeError: If requested template is inactive.
        InvalidChallengeTypeError: If attempt tries to switch challenge type on retry.
    """
    # 1. Validate WakeSession existence and ownership
    session = db.get(WakeSession, request.wake_session_id)
    if not session:
        raise WakeSessionNotFoundError(
            f"Wake session with id {request.wake_session_id} not found."
        )

    if session.user_id != request.user_id:
        raise ChallengeAttemptOwnershipError(
            f"Wake session {session.id} does not belong to user {request.user_id}."
        )

    # Validate non-terminal status
    if session.status in TERMINAL_STATUSES:
        raise InvalidSessionTransitionError(
            f"Cannot start challenge attempt for wake session {session.id} "
            f"because it is already in terminal status '{session.status}'."
        )

    # 2. Prevent concurrent active attempts on the same WakeSession
    active_stmt = select(ChallengeAttempt).where(
        ChallengeAttempt.wake_session_id == session.id,
        ChallengeAttempt.completed_at.is_(None),
    )
    active_attempt = db.scalars(active_stmt).first()
    if active_attempt:
        raise ActiveChallengeAttemptExistsError(
            f"An active challenge attempt (id {active_attempt.id}) is already in progress "
            f"for wake session {session.id}."
        )

    # 3. Fetch existing attempts to determine retry sequence and enforce type consistency
    history_stmt = (
        select(ChallengeAttempt)
        .where(ChallengeAttempt.wake_session_id == session.id)
        .order_by(ChallengeAttempt.attempt_number.asc())
    )
    existing_attempts = list(db.scalars(history_stmt).all())

    # Resolve challenge type & difficulty
    target_type: str
    target_diff: Optional[str] = request.difficulty_level

    if existing_attempts:
        # Retries MUST preserve the exact same challenge type selected for this session
        required_type = existing_attempts[0].challenge_type
        if request.challenge_type and request.challenge_type.lower() != required_type.lower():
            raise InvalidChallengeTypeError(
                f"Cannot switch challenge type during retries. "
                f"Active session challenge type is '{required_type}'."
            )
        target_type = required_type
        if not target_diff:
            target_diff = existing_attempts[0].difficulty_level
    else:
        # First attempt: resolve from request, alarm, or fallback default
        if request.challenge_type:
            target_type = request.challenge_type
        elif session.alarm_id:
            alarm = db.get(Alarm, session.alarm_id)
            target_type = alarm.selected_challenge_type if alarm else "math"
            if not target_diff and alarm:
                target_diff = (
                    alarm.difficulty_preference
                    if alarm.difficulty_preference != "adaptive"
                    else "medium"
                )
        else:
            target_type = "math"

    if not target_diff:
        target_diff = "medium"

    # Resolve template ID if specified
    template_id_to_use = request.challenge_id
    if template_id_to_use is not None:
        template = db.get(Challenge, template_id_to_use)
        if not template:
            raise ChallengeNotFoundError(
                f"Challenge template with id {template_id_to_use} not found."
            )
        if not template.is_active:
            raise InactiveChallengeError(
                f"Cannot execute inactive challenge template id {template.id} ('{template.title}')."
            )
        if existing_attempts and template.challenge_type.lower() != required_type.lower():
            raise InvalidChallengeTypeError(
                f"Template type '{template.challenge_type}' does not match session "
                f"challenge type '{required_type}'."
            )
        target_type = template.challenge_type
        target_diff = template.difficulty_level

    # 4. Generate in-memory RuntimeChallenge instance
    gen_req = RuntimeChallengeGenerationRequest(
        template_id=template_id_to_use,
        challenge_type=target_type if template_id_to_use is None else None,
        difficulty_level=target_diff if template_id_to_use is None else None,
    )
    runtime_res = generate_challenge(db, gen_req)

    # 5. Determine sequential attempt number
    attempt_number = len(existing_attempts) + 1

    # 6. Serialize runtime challenge into prompt_content
    prompt_payload = {
        "challenge_id": runtime_res.challenge_id,
        "challenge_type": runtime_res.challenge_type,
        "difficulty_level": runtime_res.difficulty_level,
        "title": runtime_res.title,
        "generated_content": runtime_res.generated_content,
        "parameters": runtime_res.parameters,
        "expected_answer": runtime_res.expected_answer,
        "verification_mode": runtime_res.verification_mode,
        "min_duration_seconds": runtime_res.min_duration_seconds,
        "generated_at": runtime_res.generated_at.isoformat(),
    }

    started_at = now_utc_naive()

    # 7. Create ChallengeAttempt record
    attempt = ChallengeAttempt(
        wake_session_id=session.id,
        challenge_id=runtime_res.challenge_id,
        challenge_type=runtime_res.challenge_type,
        difficulty_level=runtime_res.difficulty_level,
        prompt_content=json.dumps(prompt_payload),
        attempt_number=attempt_number,
        started_at=started_at,
        completed_at=None,
        duration_seconds=None,
        is_successful=None,
        verification_result=None,
        verification_score=None,
        failure_reason=None,
    )
    db.add(attempt)

    # 8. Update WakeSession status to in_challenge
    if session.status in (STATUS_RINGING, STATUS_SNOOZED):
        session.status = STATUS_IN_CHALLENGE

    db.commit()
    db.refresh(attempt)
    db.refresh(session)
    return attempt


def submit_challenge_attempt(
    db: Session,
    attempt_id: int,
    user_id: int,
    submission_data: Dict[str, Any],
) -> ChallengeAttempt:
    """Submit a challenge response, execute Phase 2.8 verification, and update state.

    Args:
        db: Active SQLAlchemy database session.
        attempt_id: Primary key ID of the ChallengeAttempt.
        user_id: ID of the submitting user (ownership check).
        submission_data: User response dictionary.

    Returns:
        ChallengeAttempt: Updated attempt record with verification outcomes.

    Raises:
        ChallengeAttemptNotFoundError: If attempt does not exist.
        ChallengeAttemptOwnershipError: If attempt does not belong to user.
        ChallengeAttemptCompletedError: If attempt was already submitted.
    """
    # 1. Find attempt
    attempt = db.get(ChallengeAttempt, attempt_id)
    if not attempt:
        raise ChallengeAttemptNotFoundError(
            f"Challenge attempt with id {attempt_id} not found."
        )

    # 2. Verify ownership via associated WakeSession
    session = db.get(WakeSession, attempt.wake_session_id)
    if not session or session.user_id != user_id:
        raise ChallengeAttemptOwnershipError(
            f"User {user_id} is not authorized to submit challenge attempt {attempt_id}."
        )

    # 3. Prevent duplicate submission on already completed attempt
    if attempt.completed_at is not None or attempt.is_successful is not None:
        raise ChallengeAttemptCompletedError(
            f"Challenge attempt {attempt_id} has already been completed and submitted."
        )

    # 4. Record completion time and compute non-negative duration
    now = now_utc_naive()
    duration_seconds = max(0.0, diff_seconds(now, attempt.started_at))
    attempt.completed_at = now
    attempt.duration_seconds = duration_seconds

    # 5. Deserialize runtime challenge specifications and verify via Phase 2.8
    runtime_dict = json.loads(attempt.prompt_content)
    verification = verify_challenge(
        runtime_challenge=runtime_dict,
        submission_data=submission_data,
    )

    # 6. Persist verification outcomes
    attempt.is_successful = verification.is_successful
    attempt.verification_score = verification.verification_score
    attempt.failure_reason = verification.failure_reason
    attempt.verification_result = json.dumps({
        "status": verification.verification_result,
        "diagnostics": verification.diagnostic_details,
    })

    # 7. Update WakeSession lifecycle
    if verification.is_successful:
        complete_wake_session(db=db, session_id=session.id)
    else:
        # Failed attempts leave session in_challenge ready for retry
        session.status = STATUS_IN_CHALLENGE

    db.commit()
    db.refresh(attempt)
    db.refresh(session)
    return attempt


def get_challenge_attempt(
    db: Session, attempt_id: int, user_id: int
) -> ChallengeAttempt:
    """Retrieve an individual ChallengeAttempt record by ID with ownership check.

    Args:
        db: Active SQLAlchemy database session.
        attempt_id: Challenge attempt ID.
        user_id: ID of requesting user.

    Returns:
        ChallengeAttempt instance.

    Raises:
        ChallengeAttemptNotFoundError: If attempt does not exist.
        ChallengeAttemptOwnershipError: If attempt does not belong to user.
    """
    attempt = db.get(ChallengeAttempt, attempt_id)
    if not attempt:
        raise ChallengeAttemptNotFoundError(
            f"Challenge attempt with id {attempt_id} not found."
        )

    session = db.get(WakeSession, attempt.wake_session_id)
    if not session or session.user_id != user_id:
        raise ChallengeAttemptOwnershipError(
            f"User {user_id} is not authorized to access challenge attempt {attempt_id}."
        )

    return attempt


def list_attempts_for_wake_session(
    db: Session, session_id: int, user_id: int
) -> List[ChallengeAttempt]:
    """Retrieve all chronological execution attempts for a given WakeSession.

    Args:
        db: Active SQLAlchemy database session.
        session_id: WakeSession ID.
        user_id: ID of requesting user.

    Returns:
        List of ChallengeAttempt records ordered by attempt_number ascending.

    Raises:
        WakeSessionNotFoundError: If wake session does not exist.
        ChallengeAttemptOwnershipError: If wake session does not belong to user.
    """
    session = db.get(WakeSession, session_id)
    if not session:
        raise WakeSessionNotFoundError(
            f"Wake session with id {session_id} not found."
        )

    if session.user_id != user_id:
        raise ChallengeAttemptOwnershipError(
            f"User {user_id} is not authorized to view attempts for wake session {session_id}."
        )

    stmt = (
        select(ChallengeAttempt)
        .where(ChallengeAttempt.wake_session_id == session_id)
        .order_by(ChallengeAttempt.attempt_number.asc())
    )
    return list(db.scalars(stmt).all())
