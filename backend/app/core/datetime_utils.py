"""Centralized datetime and timezone utility functions for SmartWake AI.

ARCHITECTURAL RULES & CONVENTIONS:
1. User scheduling: Configured alarm times ('HH:MM') and recurrence days are
   interpreted strictly in the user's configured IANA timezone (e.g., 'Asia/Kolkata').
2. Absolute event timestamps: All backend event timestamps (session creation,
   snooze, resume, completion, abandonment, challenge attempts, audit logs)
   represent absolute points in time, standardized in UTC.
3. SQLite DateTime persistence: The underlying SQLite database and SQLAlchemy
   DateTime columns store naive UTC datetimes. By design in SmartWake AI,
   ANY naive datetime inside the persistence layer or ORM models represents UTC,
   NOT local time.
4. Boundaries: When interacting with SQLite or comparing against database-loaded
   columns, timestamps are normalized to naive UTC via `ensure_naive_utc()` or
   compared using `diff_seconds()` to prevent Python TypeError crashes.
"""
from datetime import datetime, timezone
from typing import Optional


def now_utc() -> datetime:
    """Return the current time as a timezone-aware UTC datetime.

    Returns:
        datetime: Current UTC time with tzinfo=timezone.utc.
    """
    return datetime.now(timezone.utc)


def now_utc_naive() -> datetime:
    """Return the current UTC time as an offset-naive datetime.

    Specifically designed for column defaults and persistence in SQLite / SQLAlchemy
    DateTime columns without tzinfo offsets.

    Returns:
        datetime: Current UTC time with tzinfo=None.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensure a datetime is timezone-aware in UTC.

    CRITICAL SEMANTIC RULE:
    - If dt is naive (tzinfo is None), it is INTERPRETED as UTC without altering
      its clock values (i.e. dt.replace(tzinfo=timezone.utc)). Naive datetimes in
      SmartWake AI always represent UTC, never local time.
    - If dt is timezone-aware (tzinfo is not None), it is converted to UTC via
      .astimezone(timezone.utc).
    - If dt is None, returns None.

    Args:
        dt: Optional datetime object.

    Returns:
        Optional[datetime]: Timezone-aware UTC datetime, or None if input was None.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def ensure_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Normalize a datetime to UTC and remove tzinfo for SQLite persistence/queries.

    - If dt is naive, it is assumed to be UTC and returned directly.
    - If dt is timezone-aware, it is converted to UTC and its tzinfo is stripped.
    - If dt is None, returns None.

    Args:
        dt: Optional datetime object.

    Returns:
        Optional[datetime]: Offset-naive UTC datetime, or None if input was None.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def diff_seconds(dt1: datetime, dt2: datetime) -> float:
    """Calculate the difference in seconds (dt1 - dt2) safely.

    Both datetimes are consistently normalized to timezone-aware UTC prior
    to subtraction so combinations of naive and aware datetimes cannot raise
    `TypeError: can't subtract offset-naive and offset-aware datetimes`.

    Args:
        dt1: First datetime (end time).
        dt2: Second datetime (start time).

    Returns:
        float: Difference in seconds (dt1 - dt2).
    """
    aware_dt1 = ensure_utc(dt1)
    aware_dt2 = ensure_utc(dt2)
    if aware_dt1 is None or aware_dt2 is None:
        raise ValueError("Cannot calculate difference with None datetime.")
    return (aware_dt1 - aware_dt2).total_seconds()
