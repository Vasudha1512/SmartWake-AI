"""Service layer for WakeSession lifecycle operations, validation, and transitions."""
from datetime import datetime
from typing import List, Optional, Set
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.exceptions import (
    ActiveSessionExistsError,
    AlarmNotFoundError,
    AlarmOwnershipError,
    InactiveAlarmError,
    InvalidSessionTransitionError,
    UserNotFoundError,
    WakeSessionNotFoundError,
)
from backend.app.models.alarm import Alarm
from backend.app.models.user import User
from backend.app.models.wake_session import WakeSession

# Status definitions aligning with WakeSession model and schema design
STATUS_RINGING: str = "ringing"
STATUS_IN_CHALLENGE: str = "in_challenge"
STATUS_COMPLETED: str = "completed"
STATUS_ABANDONED: str = "abandoned"
STATUS_SNOOZED: str = "snoozed"

ACTIVE_STATUSES: Set[str] = {STATUS_RINGING, STATUS_IN_CHALLENGE, STATUS_SNOOZED}
TERMINAL_STATUSES: Set[str] = {STATUS_COMPLETED, STATUS_ABANDONED}


def create_wake_session(
    db: Session,
    user_id: int,
    alarm_id: int,
    scheduled_time: Optional[datetime] = None,
) -> WakeSession:
    """Create and start a new WakeSession for an active alarm occurrence.

    Validation Rules:
    1. user_id must exist in database.
    2. alarm_id must exist in database.
    3. alarm must belong to the specified user.
    4. alarm must be active (alarm.is_active == True).
    5. A user/alarm cannot have multiple simultaneous active sessions.

    IMPORTANT PRODUCT RULES:
    - Creating a WakeSession records the occurrence only.
    - Alarm configuration (time, days_of_week, selected_challenge_type, difficulty)
      is NEVER modified during wake session creation or updates.

    Args:
        db: Database session.
        user_id: ID of the user.
        alarm_id: ID of the alarm.
        scheduled_time: Optional planned ring time (defaults to current time).

    Returns:
        The newly created WakeSession instance with initial status 'ringing'.

    Raises:
        UserNotFoundError: If user does not exist.
        AlarmNotFoundError: If alarm does not exist.
        AlarmOwnershipError: If alarm does not belong to the user.
        InactiveAlarmError: If alarm is inactive.
        ActiveSessionExistsError: If an active session is already in progress.
    """
    # 1. Validate user
    user = db.get(User, user_id)
    if not user:
        raise UserNotFoundError(f"User with id {user_id} not found.")

    # 2. Validate alarm
    alarm = db.get(Alarm, alarm_id)
    if not alarm:
        raise AlarmNotFoundError(f"Alarm with id {alarm_id} not found.")

    # 3. Verify ownership
    if alarm.user_id != user_id:
        raise AlarmOwnershipError(
            f"Alarm with id {alarm_id} does not belong to user {user_id}."
        )

    # 4. Verify alarm is active
    if not alarm.is_active:
        raise InactiveAlarmError(
            f"Cannot start wake session for inactive alarm {alarm_id}."
        )

    # 5. Prevent duplicate active session for the same user and alarm
    existing_active = db.scalars(
        select(WakeSession).where(
            WakeSession.user_id == user_id,
            WakeSession.alarm_id == alarm_id,
            WakeSession.status.in_(ACTIVE_STATUSES),
        )
    ).first()
    if existing_active:
        raise ActiveSessionExistsError(
            f"An active wake session (id={existing_active.id}, status='{existing_active.status}') "
            f"already exists for alarm {alarm_id}."
        )

    # 6. Instantiate new WakeSession
    now = datetime.utcnow()
    target_scheduled = scheduled_time if scheduled_time is not None else now

    wake_session = WakeSession(
        user_id=user_id,
        alarm_id=alarm_id,
        scheduled_time=target_scheduled,
        initial_ring_time=now,
        status=STATUS_RINGING,
        total_snooze_count=0,
    )
    db.add(wake_session)
    db.commit()
    db.refresh(wake_session)
    return wake_session


def get_wake_session_by_id(db: Session, session_id: int) -> Optional[WakeSession]:
    """Retrieve a WakeSession by primary key ID.

    Args:
        db: Database session.
        session_id: WakeSession ID.

    Returns:
        WakeSession instance or None if not found.
    """
    return db.get(WakeSession, session_id)


def get_wake_sessions_by_user(db: Session, user_id: int) -> List[WakeSession]:
    """Retrieve all WakeSessions for a specific user, ordered newest first.

    Args:
        db: Database session.
        user_id: User ID.

    Returns:
        List of WakeSession instances belonging to user.

    Raises:
        UserNotFoundError: If user does not exist.
    """
    user = db.get(User, user_id)
    if not user:
        raise UserNotFoundError(f"User with id {user_id} not found.")

    return list(
        db.scalars(
            select(WakeSession)
            .where(WakeSession.user_id == user_id)
            .order_by(WakeSession.scheduled_time.desc(), WakeSession.id.desc())
        ).all()
    )


def transition_to_in_progress(db: Session, session_id: int) -> WakeSession:
    """Transition a wake session to IN_PROGRESS ('in_challenge').

    Valid transitions:
    - 'ringing' -> 'in_challenge'
    - 'snoozed' -> 'in_challenge'

    Forbidden:
    - 'in_challenge' -> 'in_challenge'
    - 'completed' -> 'in_challenge'
    - 'abandoned' -> 'in_challenge'

    Args:
        db: Database session.
        session_id: WakeSession ID.

    Returns:
        Updated WakeSession.

    Raises:
        WakeSessionNotFoundError: If session does not exist.
        InvalidSessionTransitionError: If transition is forbidden.
    """
    session = db.get(WakeSession, session_id)
    if not session:
        raise WakeSessionNotFoundError(f"Wake session with id {session_id} not found.")

    if session.status in TERMINAL_STATUSES:
        raise InvalidSessionTransitionError(
            f"Cannot transition wake session {session_id} from terminal status "
            f"'{session.status}' to '{STATUS_IN_CHALLENGE}'."
        )

    if session.status == STATUS_IN_CHALLENGE:
        raise InvalidSessionTransitionError(
            f"Wake session {session_id} is already in progress ('{STATUS_IN_CHALLENGE}')."
        )

    session.status = STATUS_IN_CHALLENGE
    db.commit()
    db.refresh(session)
    return session


def complete_wake_session(db: Session, session_id: int) -> WakeSession:
    """Complete a wake session successfully (challenge passed, alarm dismissed).

    Valid transitions:
    - 'ringing' -> 'completed'
    - 'in_challenge' -> 'completed'
    - 'snoozed' -> 'completed'

    Forbidden:
    - 'completed' -> 'completed'
    - 'abandoned' -> 'completed'

    Args:
        db: Database session.
        session_id: WakeSession ID.

    Returns:
        Updated WakeSession with status 'completed' and recorded dismissed_time.

    Raises:
        WakeSessionNotFoundError: If session does not exist.
        InvalidSessionTransitionError: If transition is forbidden.
    """
    session = db.get(WakeSession, session_id)
    if not session:
        raise WakeSessionNotFoundError(f"Wake session with id {session_id} not found.")

    if session.status in TERMINAL_STATUSES:
        raise InvalidSessionTransitionError(
            f"Cannot complete wake session {session_id} because it is already in terminal status "
            f"'{session.status}'."
        )

    now = datetime.utcnow()
    session.status = STATUS_COMPLETED
    session.dismissed_time = now
    if session.scheduled_time:
        session.total_wake_delay_seconds = max(
            0.0, (now - session.scheduled_time).total_seconds()
        )

    db.commit()
    db.refresh(session)
    return session


def fail_wake_session(db: Session, session_id: int) -> WakeSession:
    """Mark a wake session as failed / abandoned.

    Valid transitions:
    - 'ringing' -> 'abandoned'
    - 'in_challenge' -> 'abandoned'
    - 'snoozed' -> 'abandoned'

    Forbidden:
    - 'completed' -> 'abandoned'
    - 'abandoned' -> 'abandoned'

    Args:
        db: Database session.
        session_id: WakeSession ID.

    Returns:
        Updated WakeSession with status 'abandoned' and recorded dismissed_time.

    Raises:
        WakeSessionNotFoundError: If session does not exist.
        InvalidSessionTransitionError: If transition is forbidden.
    """
    session = db.get(WakeSession, session_id)
    if not session:
        raise WakeSessionNotFoundError(f"Wake session with id {session_id} not found.")

    if session.status in TERMINAL_STATUSES:
        raise InvalidSessionTransitionError(
            f"Cannot fail/abandon wake session {session_id} because it is already in terminal status "
            f"'{session.status}'."
        )

    now = datetime.utcnow()
    session.status = STATUS_ABANDONED
    session.dismissed_time = now
    if session.scheduled_time:
        session.total_wake_delay_seconds = max(
            0.0, (now - session.scheduled_time).total_seconds()
        )

    db.commit()
    db.refresh(session)
    return session


# Semantic aliases for operational convenience
start_challenge = transition_to_in_progress
abandon_wake_session = fail_wake_session
