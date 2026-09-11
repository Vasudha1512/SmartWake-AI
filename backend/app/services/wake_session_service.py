"""Service layer for WakeSession lifecycle operations, validation, and transitions."""
from datetime import datetime
from typing import List, NamedTuple, Optional, Set
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.datetime_utils import (
    diff_seconds,
    ensure_naive_utc,
    now_utc_naive,
)
from backend.app.core.exceptions import (
    ActiveSessionExistsError,
    AlarmNotFoundError,
    AlarmOwnershipError,
    InactiveAlarmError,
    InvalidSessionTransitionError,
    InvalidSnoozeDurationError,
    UserNotFoundError,
    WakeSessionNotFoundError,
)
from backend.app.models.alarm import Alarm
from backend.app.models.snooze_event import SnoozeEvent
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
    now = now_utc_naive()
    target_scheduled = ensure_naive_utc(scheduled_time) if scheduled_time is not None else now

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

    now = now_utc_naive()
    session.status = STATUS_COMPLETED
    session.dismissed_time = now
    if session.scheduled_time:
        session.total_wake_delay_seconds = max(
            0.0, diff_seconds(now, session.scheduled_time)
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

    now = now_utc_naive()
    session.status = STATUS_ABANDONED
    session.dismissed_time = now
    if session.scheduled_time:
        session.total_wake_delay_seconds = max(
            0.0, diff_seconds(now, session.scheduled_time)
        )

    db.commit()
    db.refresh(session)
    return session


# Semantic aliases for operational convenience
start_challenge = transition_to_in_progress
abandon_wake_session = fail_wake_session


class SnoozeResult(NamedTuple):
    """Result of a record_snooze action containing the updated WakeSession and created SnoozeEvent."""

    wake_session: WakeSession
    snooze_event: SnoozeEvent

    def __getattr__(self, name: str):
        """Delegate attribute access to the underlying WakeSession for convenience."""
        return getattr(self.wake_session, name)


def record_snooze(
    db: Session,
    session_id: int,
    user_id: Optional[int] = None,
    alarm_id: Optional[int] = None,
    duration_minutes: Optional[int] = 5,
    snoozed_at: Optional[datetime] = None,
) -> SnoozeResult:
    """Record a snooze event for an active WakeSession.

    Validation Rules:
    1. wake_session must exist (WakeSessionNotFoundError if not found).
    2. If user_id is provided:
       - user must exist (UserNotFoundError if not found).
       - wake_session.user_id must match user_id (AlarmOwnershipError if mismatched).
    3. If alarm_id is provided:
       - alarm must exist (AlarmNotFoundError if not found).
       - wake_session.alarm_id must match alarm_id (AlarmOwnershipError if mismatched).
    4. wake_session must not be in terminal status ('completed', 'abandoned').
       (InvalidSessionTransitionError if terminal).
    5. wake_session must be in an allowed active state ('ringing', 'snoozed').
       (InvalidSessionTransitionError if invalid).
    6. duration_minutes must be a positive integer (> 0).
       (InvalidSnoozeDurationError if <= 0).

    Lifecycle Effects:
    - Creates a new SnoozeEvent linked to wake_session.
    - Sets snooze_number = wake_session.total_snooze_count + 1.
    - Sets snoozed_at timestamp (defaults to current time).
    - Leaves ring_resumed_at as None (actual scheduler re-ring behavior is in a future phase).
    - Sets snooze_duration_minutes to the validated duration (defaults to model default 5).
    - Increments wake_session.total_snooze_count += 1.
    - Updates wake_session status: 'ringing' -> 'snoozed', or preserves 'snoozed' -> 'snoozed'.
    - Commits transaction atomically; rolls back safely on failure.

    Args:
        db: Active SQLAlchemy database session.
        session_id: ID of the WakeSession being snoozed.
        user_id: Optional user ID for ownership validation.
        alarm_id: Optional alarm ID for validation.
        duration_minutes: Optional duration in minutes (defaults to model default 5).
        snoozed_at: Optional datetime timestamp for snoozed_at (defaults to current time).

    Returns:
        SnoozeResult namedtuple containing (wake_session, snooze_event).

    Raises:
        WakeSessionNotFoundError: If wake session does not exist.
        UserNotFoundError: If user_id is provided but user does not exist.
        AlarmNotFoundError: If alarm_id is provided but alarm does not exist.
        AlarmOwnershipError: If user_id or alarm_id does not match session ownership.
        InvalidSessionTransitionError: If session is completed, abandoned, or in an invalid state.
        InvalidSnoozeDurationError: If duration_minutes <= 0.
    """
    dur = 5 if duration_minutes is None else duration_minutes
    if dur <= 0:
        raise InvalidSnoozeDurationError(
            f"Invalid snooze duration '{duration_minutes}'. Duration must be a positive integer (> 0)."
        )
    if dur > 1440:
        raise InvalidSnoozeDurationError(
            f"Invalid snooze duration '{duration_minutes}'. Duration cannot exceed 1440 minutes (24 hours)."
        )

    session = db.get(WakeSession, session_id)
    if not session:
        raise WakeSessionNotFoundError(f"Wake session with id {session_id} not found.")

    if user_id is not None:
        user = db.get(User, user_id)
        if not user:
            raise UserNotFoundError(f"User with id {user_id} not found.")
        if session.user_id != user_id:
            raise AlarmOwnershipError(
                f"Wake session {session_id} belongs to user {session.user_id}, not user {user_id}."
            )

    if alarm_id is not None:
        alarm = db.get(Alarm, alarm_id)
        if not alarm:
            raise AlarmNotFoundError(f"Alarm with id {alarm_id} not found.")
        if session.alarm_id != alarm_id:
            raise AlarmOwnershipError(
                f"Wake session {session_id} belongs to alarm {session.alarm_id}, not alarm {alarm_id}."
            )

    if session.status in TERMINAL_STATUSES:
        raise InvalidSessionTransitionError(
            f"Cannot snooze wake session {session_id} because it is in terminal status '{session.status}'."
        )

    if session.status not in {STATUS_RINGING, STATUS_SNOOZED}:
        raise InvalidSessionTransitionError(
            f"Cannot snooze wake session {session_id} from status '{session.status}'. "
            f"Snooze is only permitted while ringing or already snoozed."
        )

    now = ensure_naive_utc(snoozed_at) if snoozed_at is not None else now_utc_naive()
    next_snooze_no = session.total_snooze_count + 1

    snooze_event = SnoozeEvent(
        wake_session_id=session.id,
        snooze_number=next_snooze_no,
        snoozed_at=now,
        ring_resumed_at=None,
        snooze_duration_minutes=dur,
        created_at=now,
    )

    session.total_snooze_count = next_snooze_no
    session.status = STATUS_SNOOZED

    try:
        db.add(snooze_event)
        db.commit()
        db.refresh(session)
        db.refresh(snooze_event)
        return SnoozeResult(wake_session=session, snooze_event=snooze_event)
    except Exception:
        db.rollback()
        raise


def get_snooze_events_by_session(db: Session, session_id: int) -> List[SnoozeEvent]:
    """Retrieve all SnoozeEvents belonging to a specific WakeSession, ordered by snooze_number.

    Args:
        db: Active SQLAlchemy database session.
        session_id: WakeSession ID.

    Returns:
        List of SnoozeEvent instances ordered by snooze_number ascending.
    """
    return list(
        db.scalars(
            select(SnoozeEvent)
            .where(SnoozeEvent.wake_session_id == session_id)
            .order_by(SnoozeEvent.snooze_number.asc())
        ).all()
    )


def resume_ringing(
    db: Session,
    session_id: int,
    resumed_at: Optional[datetime] = None,
) -> WakeSession:
    """Transition a snoozed wake session back to 'ringing'.

    Lifecycle Transition:
    - Allowed: 'snoozed' -> 'ringing'
    - Forbidden:
      - 'ringing' -> 'ringing' (already ringing)
      - 'in_challenge' -> 'ringing' (already in challenge)
      - 'completed' -> 'ringing' (terminal)
      - 'abandoned' -> 'ringing' (terminal)

    Telemetry Effects:
    - If this session has child SnoozeEvents and the latest SnoozeEvent has
      ring_resumed_at is None, sets ring_resumed_at to the current timestamp
      to represent the backend-recorded resume event.
    - Sets session.status = STATUS_RINGING.

    IMPORTANT ARCHITECTURAL RULE:
    This is strictly a backend lifecycle/state transition. It does NOT implement
    or imply an actual alarm re-ring timer, background scheduler, audio playback,
    notification, or snooze duration waiting mechanism.

    Args:
        db: Active SQLAlchemy database session.
        session_id: ID of the WakeSession.
        resumed_at: Optional timestamp for ring_resumed_at (defaults to current time).

    Returns:
        Updated WakeSession with status='ringing'.

    Raises:
        WakeSessionNotFoundError: If session does not exist.
        InvalidSessionTransitionError: If session is not in 'snoozed' state.
    """
    session = db.get(WakeSession, session_id)
    if not session:
        raise WakeSessionNotFoundError(f"Wake session with id {session_id} not found.")

    if session.status in TERMINAL_STATUSES:
        raise InvalidSessionTransitionError(
            f"Cannot resume wake session {session_id} because it is in terminal status '{session.status}'."
        )

    if session.status == STATUS_RINGING:
        raise InvalidSessionTransitionError(
            f"Wake session {session_id} is already in ringing status."
        )

    if session.status != STATUS_SNOOZED:
        raise InvalidSessionTransitionError(
            f"Cannot resume wake session {session_id} from status '{session.status}'. "
            f"Resume is only permitted from 'snoozed' status."
        )

    now = ensure_naive_utc(resumed_at) if resumed_at is not None else now_utc_naive()

    # If child SnoozeEvents exist, record ring_resumed_at on the latest snooze event
    if session.snooze_events:
        latest_event = max(session.snooze_events, key=lambda e: e.snooze_number)
        if latest_event.ring_resumed_at is None:
            latest_event.ring_resumed_at = now

    session.status = STATUS_RINGING

    try:
        db.commit()
        db.refresh(session)
        return session
    except Exception:
        db.rollback()
        raise


