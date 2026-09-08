"""Service layer for Alarm creation, validation, and retrieval operations."""
import json
import re
from typing import List, Optional, Set, Union
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.exceptions import (
    InvalidAlarmTimeError,
    InvalidChallengeTypeError,
    InvalidDifficultyError,
    UserNotFoundError,
)
from backend.app.models.alarm import Alarm
from backend.app.models.user import User

# The five mandatory wake-up task types supported by SmartWake AI.
# NOTE: 'memory' represents an actual pattern/sequence recall challenge, NOT number guessing.
VALID_CHALLENGE_TYPES: Set[str] = {
    "dance",
    "math",
    "memory",
    "tongue_twister",
    "push_ups",
}

# Supported baseline difficulty preferences
VALID_DIFFICULTIES: Set[str] = {
    "easy",
    "medium",
    "hard",
    "adaptive",
}

# 24-hour time format regex: "00:00" to "23:59"
TIME_REGEX = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def validate_alarm_time(time_str: str) -> str:
    """Validate that the alarm time string follows 24-hour 'HH:MM' format.

    Args:
        time_str: Time string to validate.

    Returns:
        The validated time string.

    Raises:
        InvalidAlarmTimeError: If time format is invalid.
    """
    clean_time = time_str.strip() if time_str else ""
    if not TIME_REGEX.match(clean_time):
        raise InvalidAlarmTimeError(
            f"Invalid alarm time '{time_str}'. Time must be in 24-hour 'HH:MM' format (e.g. '07:00', '23:30')."
        )
    return clean_time


def validate_challenge_type(task_type: str) -> str:
    """Validate that the challenge type is one of the five approved task categories.

    IMPORTANT PRODUCT RULE:
    The user explicitly selects the challenge type. The service layer must NEVER
    substitute or automatically select a challenge type.

    Args:
        task_type: The challenge type chosen by the user.

    Returns:
        The validated and lowercased task type string.

    Raises:
        InvalidChallengeTypeError: If task type is not supported.
    """
    clean_type = task_type.strip().lower() if task_type else ""
    if clean_type not in VALID_CHALLENGE_TYPES:
        raise InvalidChallengeTypeError(
            f"Invalid challenge type '{task_type}'. Must be one of: {sorted(list(VALID_CHALLENGE_TYPES))}."
        )
    return clean_type


def validate_difficulty_preference(difficulty: str) -> str:
    """Validate the baseline difficulty preference.

    Args:
        difficulty: The difficulty chosen by the user ('adaptive', 'easy', 'medium', 'hard').

    Returns:
        The validated and lowercased difficulty string.

    Raises:
        InvalidDifficultyError: If difficulty value is unrecognized.
    """
    clean_diff = difficulty.strip().lower() if difficulty else ""
    if clean_diff not in VALID_DIFFICULTIES:
        raise InvalidDifficultyError(
            f"Invalid difficulty preference '{difficulty}'. Must be one of: {sorted(list(VALID_DIFFICULTIES))}."
        )
    return clean_diff


def create_alarm(
    db: Session,
    user_id: int,
    time: str,
    selected_challenge_type: str,
    difficulty_preference: str = "adaptive",
    label: str = "Alarm",
    days_of_week: Union[str, List[int]] = "[0,1,2,3,4]",
    is_active: bool = True,
) -> Alarm:
    """Create a new Alarm record for an existing User.

    IMPORTANT PRODUCT RULES:
    1. The user explicitly controls the alarm time and the wake-up task type.
    2. The service layer MUST NOT choose or alter the task type.
    3. 'adaptive' difficulty means ML may adapt parameters within the selected task later;
       it does NOT give ML authority to choose the task type.

    Args:
        db: Active SQLAlchemy database session.
        user_id: ID of the user who owns this alarm.
        time: Requested alarm time in 'HH:MM' format.
        selected_challenge_type: User's chosen challenge ('dance', 'math', 'memory', 'tongue_twister', 'push_ups').
        difficulty_preference: User's baseline difficulty ('adaptive', 'easy', 'medium', 'hard').
        label: Custom label for the alarm.
        days_of_week: JSON array string or list of integers (0=Mon, 6=Sun).
        is_active: Master toggle flag for the alarm.

    Returns:
        The newly created and refreshed Alarm instance.

    Raises:
        UserNotFoundError: If the referenced user_id does not exist.
        InvalidAlarmTimeError: If time format is invalid.
        InvalidChallengeTypeError: If challenge type is unsupported.
        InvalidDifficultyError: If difficulty preference is invalid.
    """
    # 1. Verify that referenced user exists
    user = db.get(User, user_id)
    if not user:
        raise UserNotFoundError(f"Cannot create alarm: User with id {user_id} does not exist.")

    # 2. Validate user inputs
    clean_time = validate_alarm_time(time)
    clean_challenge_type = validate_challenge_type(selected_challenge_type)
    clean_difficulty = validate_difficulty_preference(difficulty_preference)

    # 3. Format days_of_week
    if isinstance(days_of_week, list):
        days_str = json.dumps(days_of_week)
    else:
        days_str = days_of_week.strip() if days_of_week else "[0,1,2,3,4]"

    # 4. Instantiate model
    alarm = Alarm(
        user_id=user_id,
        time=clean_time,
        selected_challenge_type=clean_challenge_type,
        difficulty_preference=clean_difficulty,
        label=label.strip() if label else "Alarm",
        days_of_week=days_str,
        is_active=is_active,
    )

    # 5. Persist with transaction safety
    try:
        db.add(alarm)
        db.commit()
        db.refresh(alarm)
        return alarm
    except Exception:
        db.rollback()
        raise


def get_alarm_by_id(db: Session, alarm_id: int) -> Optional[Alarm]:
    """Retrieve an alarm by its primary key ID.

    Args:
        db: Active SQLAlchemy database session.
        alarm_id: Alarm integer primary key.

    Returns:
        The Alarm instance if found, otherwise None.
    """
    return db.get(Alarm, alarm_id)


def get_alarms_by_user(db: Session, user_id: int) -> List[Alarm]:
    """Retrieve all alarms belonging to a specific user.

    Args:
        db: Active SQLAlchemy database session.
        user_id: User integer primary key.

    Returns:
        List of Alarm instances configured by the user.
    """
    stmt = select(Alarm).where(Alarm.user_id == user_id).order_by(Alarm.time)
    return list(db.execute(stmt).scalars().all())


def update_alarm(
    db: Session,
    alarm_id: int,
    time: Optional[str] = None,
    selected_challenge_type: Optional[str] = None,
    difficulty_preference: Optional[str] = None,
    label: Optional[str] = None,
    days_of_week: Optional[Union[str, List[int]]] = None,
    is_active: Optional[bool] = None,
) -> Optional[Alarm]:
    """Update an existing alarm's configuration.

    IMPORTANT:
    - Does NOT permit changing the owning user_id.
    - Validates updated time, challenge type, and difficulty preference.

    Args:
        db: Active SQLAlchemy database session.
        alarm_id: ID of the alarm to update.
        time: Optional new alarm time ("HH:MM").
        selected_challenge_type: Optional new challenge type.
        difficulty_preference: Optional new difficulty preference.
        label: Optional new label string.
        days_of_week: Optional new days array string or integer list.
        is_active: Optional new active flag.

    Returns:
        The updated and refreshed Alarm instance, or None if not found.

    Raises:
        InvalidAlarmTimeError: If new time format is invalid.
        InvalidChallengeTypeError: If new challenge type is unsupported.
        InvalidDifficultyError: If new difficulty preference is invalid.
    """
    alarm = db.get(Alarm, alarm_id)
    if not alarm:
        return None

    if time is not None:
        alarm.time = validate_alarm_time(time)

    if selected_challenge_type is not None:
        alarm.selected_challenge_type = validate_challenge_type(selected_challenge_type)

    if difficulty_preference is not None:
        alarm.difficulty_preference = validate_difficulty_preference(difficulty_preference)

    if label is not None:
        alarm.label = label.strip()

    if days_of_week is not None:
        if isinstance(days_of_week, list):
            alarm.days_of_week = json.dumps(days_of_week)
        else:
            alarm.days_of_week = days_of_week.strip()

    if is_active is not None:
        alarm.is_active = is_active

    try:
        db.commit()
        db.refresh(alarm)
        return alarm
    except Exception:
        db.rollback()
        raise


def delete_alarm(db: Session, alarm_id: int) -> bool:
    """Delete an alarm by primary key ID.

    Args:
        db: Active SQLAlchemy database session.
        alarm_id: ID of the alarm to delete.

    Returns:
        True if the alarm was found and deleted, False if not found.
    """
    alarm = db.get(Alarm, alarm_id)
    if not alarm:
        return False

    try:
        db.delete(alarm)
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
