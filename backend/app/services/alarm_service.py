"""Service layer for Alarm creation, validation, and retrieval operations."""
import json
import re
from typing import List, Optional, Set, Union
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.exceptions import (
    InvalidAlarmTimeError,
    InvalidChallengeTypeError,
    InvalidDaysOfWeekError,
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


def validate_days_of_week(days: Union[List[int], str, None]) -> List[int]:
    """Validate and normalize alarm days of the week.

    Conventions:
      0 = Monday, 1 = Tuesday, 2 = Wednesday, 3 = Thursday,
      4 = Friday, 5 = Saturday, 6 = Sunday.

    Rules:
      - Defaults to [0, 1, 2, 3, 4] (Mon-Fri) if days is None.
      - Minimum 1 day, maximum 7 days.
      - Each day must be an integer between 0 and 6.
      - No duplicate days allowed (rejected, not silently deduped).
      - Unordered valid input is normalized by sorting.
      - Rejects non-integers (strings, floats, booleans).
      - Rejects invalid JSON strings.

    Args:
        days: List of weekday integers, valid JSON array string, or None.

    Returns:
        Sorted list of unique weekday integers (e.g. [0, 1, 2, 3, 4]).

    Raises:
        InvalidDaysOfWeekError: If days format, length, elements, or ranges are invalid.
    """
    if days is None:
        return [0, 1, 2, 3, 4]

    if isinstance(days, str):
        try:
            parsed = json.loads(days)
        except Exception as exc:
            raise InvalidDaysOfWeekError(
                f"Invalid days_of_week JSON string '{days}': must be a valid JSON array."
            ) from exc
        if not isinstance(parsed, list):
            raise InvalidDaysOfWeekError(
                f"days_of_week string must parse to a JSON array, got: {type(parsed).__name__}."
            )
        days = parsed

    if not isinstance(days, list):
        raise InvalidDaysOfWeekError(
            f"days_of_week must be a list of integers, got: {type(days).__name__}."
        )

    if len(days) == 0:
        raise InvalidDaysOfWeekError("days_of_week must contain at least 1 day (0-6).")

    if len(days) > 7:
        raise InvalidDaysOfWeekError("days_of_week cannot contain more than 7 days.")

    for d in days:
        if type(d) is not int:
            raise InvalidDaysOfWeekError(
                f"days_of_week elements must be integers, got {type(d).__name__}: {d}."
            )
        if d < 0 or d > 6:
            raise InvalidDaysOfWeekError(
                f"days_of_week values must be between 0 (Mon) and 6 (Sun), got: {d}."
            )

    if len(days) != len(set(days)):
        raise InvalidDaysOfWeekError(
            f"days_of_week cannot contain duplicate days: {days}."
        )

    return sorted(days)


def create_alarm(
    db: Session,
    user_id: int,
    time: str,
    selected_challenge_type: str,
    difficulty_preference: str = "adaptive",
    label: str = "Alarm",
    days_of_week: Optional[Union[List[int], str]] = None,
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
        days_of_week: List of weekday integers (0=Mon, 6=Sun), JSON array string, or None.
        is_active: Master toggle flag for the alarm.

    Returns:
        The newly created and refreshed Alarm instance.

    Raises:
        UserNotFoundError: If the referenced user_id does not exist.
        InvalidAlarmTimeError: If time format is invalid.
        InvalidChallengeTypeError: If challenge type is unsupported.
        InvalidDifficultyError: If difficulty preference is invalid.
        InvalidDaysOfWeekError: If days_of_week configuration is invalid.
    """
    # 1. Verify that referenced user exists
    user = db.get(User, user_id)
    if not user:
        raise UserNotFoundError(f"Cannot create alarm: User with id {user_id} does not exist.")

    # 2. Validate user inputs
    clean_time = validate_alarm_time(time)
    clean_challenge_type = validate_challenge_type(selected_challenge_type)
    clean_difficulty = validate_difficulty_preference(difficulty_preference)
    clean_days = validate_days_of_week(days_of_week)

    # 3. Format days_of_week as JSON string for SQLite storage
    days_str = json.dumps(clean_days)

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
        InvalidDaysOfWeekError: If days_of_week configuration is invalid.
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
        clean_days = validate_days_of_week(days_of_week)
        alarm.days_of_week = json.dumps(clean_days)

    if is_active is not None:
        alarm.is_active = is_active

    try:
        db.commit()
        db.refresh(alarm)
        return alarm
    except Exception:
        db.rollback()
        raise


def deactivate_alarm(db: Session, alarm_id: int) -> Optional[Alarm]:
    """Deactivate (logically delete) an alarm by primary key ID.

    Sets is_active to False to preserve historical alarm configuration
    and wake-session telemetry for future ML analytics. Does NOT physically
    delete the Alarm row from the database.

    Args:
        db: Active SQLAlchemy database session.
        alarm_id: ID of the alarm to deactivate.

    Returns:
        The updated Alarm instance with is_active=False, or None if not found.
    """
    alarm = db.get(Alarm, alarm_id)
    if not alarm:
        return None

    try:
        alarm.is_active = False
        db.commit()
        db.refresh(alarm)
        return alarm
    except Exception:
        db.rollback()
        raise


def toggle_alarm(db: Session, alarm_id: int) -> Optional[Alarm]:
    """Toggle an alarm's active state between enabled (True) and disabled (False).

    Args:
        db: Active SQLAlchemy database session.
        alarm_id: ID of the alarm to toggle.

    Returns:
        The updated Alarm instance with toggled is_active, or None if not found.
    """
    alarm = db.get(Alarm, alarm_id)
    if not alarm:
        return None

    try:
        alarm.is_active = not alarm.is_active
        db.commit()
        db.refresh(alarm)
        return alarm
    except Exception:
        db.rollback()
        raise


def delete_alarm(db: Session, alarm_id: int) -> bool:
    """Logically delete (deactivate) an alarm by primary key ID.

    Preserves historical relationships for future ML and wake session analysis.
    Sets is_active = False rather than issuing a physical SQL delete.

    Args:
        db: Active SQLAlchemy database session.
        alarm_id: ID of the alarm to deactivate.

    Returns:
        True if the alarm was found and deactivated, False if not found.
    """
    alarm = deactivate_alarm(db=db, alarm_id=alarm_id)
    return alarm is not None

