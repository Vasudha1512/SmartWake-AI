"""Service layer for Scheduler Time, Recurrence evaluation, and Execution in SmartWake AI.

PHASE 2.6.2.1: Pure time and recurrence decision engine.
PHASE 2.6.2.2: Scheduler execution and WakeSession creation engine.

CORE PRODUCT RULES:
1. The user controls the alarm time.
2. The user controls the selected challenge type.
3. The scheduler MUST NOT modify the alarm time.
4. The scheduler MUST NOT choose or modify the challenge type.
5. The scheduler MUST NOT perform ML/adaptive decisions.
6. The scheduler only determines whether an active recurring alarm is due,
   and creates initial 'ringing' WakeSessions where appropriate.
7. This module does NOT run background loops (APScheduler, Celery, Redis),
   send push notifications, or modify alarm configurations.

SCHEDULER EXECUTION FLOW:
current_time
    ↓
due-alarm detection (get_due_alarms)
    ↓
duplicate active-session & occurrence safety check (has_active_or_occurrence_session)
    ↓
WakeSession creation (wake_session_service.create_wake_session)
    ↓
initial status = "ringing"
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import os
from typing import List, Optional, Tuple, Union
import zoneinfo
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, joinedload

from backend.app.core.datetime_utils import ensure_naive_utc, now_utc
from backend.app.core.exceptions import (
    ActiveSessionExistsError,
    InvalidAlarmTimeError,
    InvalidDaysOfWeekError,
    InvalidTimezoneError,
)
from backend.app.models.alarm import Alarm
from backend.app.models.user import User
from backend.app.models.wake_session import WakeSession
from backend.app.services import wake_session_service
from backend.app.services.alarm_service import (
    validate_alarm_time,
    validate_days_of_week,
)
from backend.app.services.user_service import _ensure_tzpath, validate_timezone
from backend.app.services.wake_session_service import ACTIVE_STATUSES

# Ensure zoneinfo search paths are configured on Windows
_ensure_tzpath()


@dataclass
class SchedulerExecutionResult:
    """Summary result of a scheduler execution run."""

    processed: int = 0
    created: int = 0
    skipped: int = 0
    sessions: List[WakeSession] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert result to a plain dictionary."""
        return {
            "processed": self.processed,
            "created": self.created,
            "skipped": self.skipped,
            "sessions": self.sessions,
        }

    def __getitem__(self, key: str):
        """Allow dict-like subscripting (e.g. result['created'])."""
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)


def resolve_timezone(tz: Union[str, ZoneInfo]) -> ZoneInfo:
    """Resolve a timezone identifier or ZoneInfo instance into a validated ZoneInfo object.

    Args:
        tz: IANA timezone string (e.g. 'UTC', 'Asia/Kolkata') or ZoneInfo instance.

    Returns:
        ZoneInfo instance.

    Raises:
        InvalidTimezoneError: If the timezone identifier cannot be resolved.
    """
    if isinstance(tz, ZoneInfo):
        return tz

    clean_key = validate_timezone(tz)
    try:
        return ZoneInfo(clean_key)
    except Exception as exc:
        raise InvalidTimezoneError(f"Failed to load timezone '{tz}': {exc}") from exc


def to_user_local_time(
    dt: Optional[datetime],
    user_tz: Union[str, ZoneInfo],
) -> datetime:
    """Convert a timezone-aware datetime into the user's local timezone.

    Args:
        dt: Timezone-aware datetime to convert. If None, defaults to current UTC time.
        user_tz: User's IANA timezone string or ZoneInfo object.

    Returns:
        Timezone-aware datetime in the user's local timezone.

    Raises:
        ValueError: If dt is a naive datetime (dt.tzinfo is None).
        InvalidTimezoneError: If user_tz is invalid.
    """
    zone = resolve_timezone(user_tz)

    if dt is None:
        dt = now_utc()
    elif dt.tzinfo is None:
        raise ValueError(
            "Supplied datetime must be timezone-aware (tzinfo cannot be None). "
            "Use e.g. now_utc() or attach a timezone."
        )

    return dt.astimezone(zone)


def is_alarm_active(alarm: Alarm) -> bool:
    """Check if an alarm is active.

    Args:
        alarm: Alarm instance to check.

    Returns:
        True if alarm is active, False otherwise.
    """
    return bool(alarm.is_active)


def get_alarm_days(alarm: Alarm) -> List[int]:
    """Extract and validate the days of the week configured for an alarm.

    Conventions:
        0 = Monday, 1 = Tuesday, 2 = Wednesday, 3 = Thursday,
        4 = Friday, 5 = Saturday, 6 = Sunday.

    Args:
        alarm: Alarm instance.

    Returns:
        Sorted list of unique weekday integers (e.g. [0, 1, 2, 3, 4]).

    Raises:
        InvalidDaysOfWeekError: If alarm.days_of_week is malformed.
    """
    return validate_days_of_week(alarm.days_of_week)


def is_alarm_day(alarm: Alarm, local_dt: datetime) -> bool:
    """Check if the local datetime's weekday is enabled in the alarm's recurrence schedule.

    Args:
        alarm: Alarm instance.
        local_dt: Local datetime for the user.

    Returns:
        True if local_dt's weekday is an enabled day for this alarm.
    """
    local_weekday = local_dt.weekday()  # 0=Monday, 6=Sunday
    configured_days = get_alarm_days(alarm)
    return local_weekday in configured_days


def parse_alarm_time(time_str: str) -> Tuple[int, int]:
    """Parse and validate an 'HH:MM' alarm time string into hour and minute integers.

    Args:
        time_str: Time string formatted as 'HH:MM'.

    Returns:
        Tuple of (hour, minute) as integers.

    Raises:
        InvalidAlarmTimeError: If time string format is invalid.
    """
    clean_time = validate_alarm_time(time_str)
    hour_str, minute_str = clean_time.split(":")
    return int(hour_str), int(minute_str)


def is_alarm_time_due(alarm_time: str, local_dt: datetime) -> bool:
    """Determine whether the local time matches the alarm's configured 'HH:MM'.

    Seconds are explicitly ignored per Phase 2.6.2.1 specification:
    - 07:00:00 -> due
    - 07:00:15 -> due
    - 07:00:59 -> due
    - 07:01:00 -> not due

    Args:
        alarm_time: Alarm time string in 'HH:MM' format.
        local_dt: Local datetime for the user.

    Returns:
        True if local_dt's hour and minute match alarm_time, False otherwise.
    """
    alarm_hour, alarm_minute = parse_alarm_time(alarm_time)
    return local_dt.hour == alarm_hour and local_dt.minute == alarm_minute


def is_alarm_due(
    alarm: Alarm,
    current_time: Optional[datetime] = None,
    user_tz: Optional[Union[str, ZoneInfo]] = None,
) -> bool:
    """Determine whether an alarm is due at a supplied point in time.

    Evaluation steps:
    1. Verify alarm is active (inactive alarms return False immediately).
    2. Determine the user's timezone:
       - user_tz argument if provided
       - alarm.user.timezone if alarm has user relationship loaded
       - Raises ValueError if timezone cannot be determined.
    3. Convert current_time (or current UTC) to user local time.
    4. Verify local weekday matches alarm's recurrence schedule (days_of_week).
    5. Verify local hour and minute match alarm's time (HH:MM).

    IMPORTANT: This function does NOT modify the Alarm object.

    Args:
        alarm: Alarm instance to check.
        current_time: Timezone-aware datetime (defaults to current UTC if None).
        user_tz: Optional explicit timezone string or ZoneInfo. If None,
                 attempts to read from alarm.user.timezone.

    Returns:
        True if alarm is due at the specified time, False otherwise.

    Raises:
        ValueError: If datetime is naive or timezone cannot be determined.
        InvalidTimezoneError: If timezone is invalid.
        InvalidAlarmTimeError: If alarm.time format is invalid.
        InvalidDaysOfWeekError: If alarm.days_of_week is invalid.
    """
    # 1. Inactive alarm check
    if not is_alarm_active(alarm):
        return False

    # 2. Resolve user timezone
    resolved_tz_param: Union[str, ZoneInfo]
    if user_tz is not None:
        resolved_tz_param = user_tz
    elif getattr(alarm, "user", None) is not None and getattr(alarm.user, "timezone", None):
        resolved_tz_param = alarm.user.timezone
    else:
        raise ValueError(
            "User timezone must be provided via 'user_tz' parameter or "
            "available on 'alarm.user.timezone'."
        )

    # 3. Convert to user's local time (raises ValueError if naive)
    local_dt = to_user_local_time(current_time, resolved_tz_param)

    # 4. Check if today is one of the alarm's configured days
    if not is_alarm_day(alarm, local_dt):
        return False

    # 5. Check if local hour and minute match alarm time
    return is_alarm_time_due(alarm.time, local_dt)


def get_due_alarms(
    db: Session,
    current_time: Optional[datetime] = None,
) -> List[Alarm]:
    """Retrieve all active alarms that are due at a specified point in time.

    Queries the database for active alarms with their associated user records,
    and checks each alarm using `is_alarm_due`.

    IMPORTANT: Does NOT create WakeSessions, modify alarms, or write to database.

    Args:
        db: Active SQLAlchemy database session.
        current_time: Timezone-aware datetime (defaults to current UTC if None).

    Returns:
        List of Alarm instances that are currently due.
    """
    stmt = (
        select(Alarm)
        .options(joinedload(Alarm.user))
        .where(Alarm.is_active == True)  # noqa: E712
    )
    active_alarms = list(db.execute(stmt).scalars().all())

    due_alarms: List[Alarm] = []
    for alarm in active_alarms:
        if is_alarm_due(alarm, current_time=current_time):
            due_alarms.append(alarm)

    return due_alarms


def get_occurrence_scheduled_time(
    alarm: Alarm,
    current_time: datetime,
    user_tz: Optional[Union[str, ZoneInfo]] = None,
) -> datetime:
    """Calculate the exact scheduled occurrence datetime (in UTC) for an alarm due at current_time.

    Takes current local date and alarm's configured 'HH:MM' in the user's local timezone,
    and converts it to a UTC datetime with second=0 and microsecond=0.

    Args:
        alarm: Alarm instance.
        current_time: Timezone-aware current datetime.
        user_tz: Optional user timezone string or ZoneInfo. If None, reads from alarm.user.timezone.

    Returns:
        Timezone-aware datetime in UTC representing the alarm's scheduled occurrence time.

    Raises:
        ValueError: If current_time is naive or user timezone cannot be determined.
    """
    if current_time.tzinfo is None:
        raise ValueError("current_time must be timezone-aware.")

    resolved_tz: Union[str, ZoneInfo]
    if user_tz is not None:
        resolved_tz = user_tz
    elif getattr(alarm, "user", None) is not None and getattr(alarm.user, "timezone", None):
        resolved_tz = alarm.user.timezone
    else:
        raise ValueError("User timezone must be provided via 'user_tz' or alarm.user.timezone.")

    zone = resolve_timezone(resolved_tz)
    local_dt = to_user_local_time(current_time, zone)
    alarm_hour, alarm_minute = parse_alarm_time(alarm.time)

    local_occurrence = local_dt.replace(
        hour=alarm_hour,
        minute=alarm_minute,
        second=0,
        microsecond=0,
    )
    return local_occurrence.astimezone(timezone.utc)


def has_active_or_occurrence_session(
    db: Session,
    alarm_id: int,
    occurrence_time_utc: datetime,
) -> bool:
    """Check whether an active session or a session for this occurrence already exists for this alarm.

    Duplicate-Prevention & Occurrence-Safety Rules:
    1. Active Session Guard: If ANY session for this alarm is in ACTIVE_STATUSES
       ('ringing', 'in_challenge', 'snoozed'), returns True (skip).
    2. Occurrence Window Guard: If a session for this alarm (even a terminal one such
       as 'completed' or 'abandoned') already exists with scheduled_time within the
       1-minute window [occurrence_time, occurrence_time + 60s), returns True (skip).
       This prevents repeated scheduler runs in the same minute from creating multiple sessions
       even if the user immediately completed or abandoned the initial session.

    ASSUMPTIONS & LIMITATIONS:
    SmartWake AI Phase 2.6.2.2 uses existing WakeSession state and scheduled_time timing
    data rather than a dedicated occurrence_id column.

    Args:
        db: Active SQLAlchemy database session.
        alarm_id: ID of the alarm.
        occurrence_time_utc: Timezone-aware or naive UTC occurrence datetime.

    Returns:
        True if an active or occurrence-matching session exists, False otherwise.
    """
    # Normalize occurrence_time_utc to naive UTC for SQLite column comparison
    naive_occurrence = ensure_naive_utc(occurrence_time_utc)
    window_start = naive_occurrence
    window_end = naive_occurrence + timedelta(minutes=1)

    stmt = select(WakeSession).where(
        WakeSession.alarm_id == alarm_id,
        or_(
            WakeSession.status.in_(ACTIVE_STATUSES),
            and_(
                WakeSession.scheduled_time >= window_start,
                WakeSession.scheduled_time < window_end,
            ),
        ),
    )
    existing = db.scalars(stmt).first()
    return existing is not None


def process_due_alarms(
    db: Session,
    current_time: Optional[datetime] = None,
) -> SchedulerExecutionResult:
    """Execute the scheduler tick: find due alarms and create WakeSessions where appropriate.

    Execution Flow:
    current_time
        ↓
    due-alarm detection via get_due_alarms(db, current_time)
        ↓
    for each due alarm:
        duplicate active-session & occurrence check
        ↓
        if no active or existing occurrence session:
            create WakeSession with initial status = 'ringing'
            (reuse wake_session_service.create_wake_session)
        ↓
        commit transaction safely

    Args:
        db: Active SQLAlchemy database session.
        current_time: Optional timezone-aware datetime. If None, defaults to current UTC time.

    Returns:
        SchedulerExecutionResult detailing processed, created, and skipped counts,
        plus the list of newly created WakeSession instances.

    Raises:
        ValueError: If current_time is a naive datetime.
    """
    if current_time is None:
        current_time = now_utc()
    elif current_time.tzinfo is None:
        raise ValueError(
            "Supplied current_time must be timezone-aware (tzinfo cannot be None). "
            "Use e.g. now_utc() or attach a timezone."
        )

    # 1. Query all active alarms due at current_time
    due_alarms = get_due_alarms(db, current_time=current_time)

    result = SchedulerExecutionResult(processed=len(due_alarms))

    for alarm in due_alarms:
        try:
            # 2. Compute exact scheduled occurrence time in UTC
            occ_time_utc = get_occurrence_scheduled_time(alarm, current_time)
            naive_occ = ensure_naive_utc(occ_time_utc)

            # 3. Check duplicate active session or occurrence session
            if has_active_or_occurrence_session(db, alarm.id, occ_time_utc):
                result.skipped += 1
                continue

            # 4. Create WakeSession using existing service layer
            try:
                session = wake_session_service.create_wake_session(
                    db=db,
                    user_id=alarm.user_id,
                    alarm_id=alarm.id,
                    scheduled_time=naive_occ,
                )
                result.created += 1
                result.sessions.append(session)
            except ActiveSessionExistsError:
                # Concurrent active session guard
                result.skipped += 1

        except Exception:
            db.rollback()
            raise

    return result
