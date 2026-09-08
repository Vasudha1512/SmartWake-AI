"""Service layer for User creation and retrieval operations."""
import os
from typing import Optional
import zoneinfo
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.exceptions import InvalidTimezoneError, UserAlreadyExistsError
from backend.app.models.user import User


def _ensure_tzpath() -> None:
    """Ensure zoneinfo.TZPATH includes valid timezone data directories on Windows if needed."""
    if not zoneinfo.TZPATH:
        candidate_paths = [
            r"C:\Program Files\Git\mingw64\share\zoneinfo",
            r"C:\Program Files (x86)\Git\mingw64\share\zoneinfo",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Git\mingw64\share\zoneinfo"),
            os.path.expandvars(r"%USERPROFILE%\AppData\Local\Programs\Git\mingw64\share\zoneinfo"),
        ]
        valid_paths = [p for p in candidate_paths if os.path.isdir(p)]
        if valid_paths:
            zoneinfo.reset_tzpath(to=valid_paths)


# Initialize zoneinfo search paths on module load
_ensure_tzpath()


def validate_timezone(timezone_str: Optional[str]) -> str:
    """Validate that the timezone string is a recognized IANA timezone identifier.

    Args:
        timezone_str: Timezone string to validate (e.g. 'UTC', 'Asia/Kolkata').
                      If None, defaults to 'UTC'.

    Returns:
        The validated IANA timezone key string.

    Raises:
        InvalidTimezoneError: If timezone string is empty or not recognized by ZoneInfo.
    """
    if timezone_str is None:
        return "UTC"

    clean_tz = timezone_str.strip() if isinstance(timezone_str, str) else ""
    if not clean_tz:
        raise InvalidTimezoneError(
            "Timezone cannot be empty. Must be a valid IANA timezone identifier (e.g. 'UTC', 'Asia/Kolkata')."
        )

    try:
        zi = ZoneInfo(clean_tz)
        return zi.key
    except Exception as exc:
        raise InvalidTimezoneError(
            f"Invalid IANA timezone '{timezone_str}'. Must be a valid IANA timezone identifier (e.g. 'UTC', 'Asia/Kolkata', 'America/New_York')."
        ) from exc


def create_user(
    db: Session,
    username: str,
    email: Optional[str] = None,
    timezone: Optional[str] = "UTC",
) -> User:
    """Create a new user record in the database.

    Args:
        db: Active SQLAlchemy database session.
        username: Unique username handle.
        email: Optional unique email address.
        timezone: Local IANA timezone identifier (defaults to 'UTC').

    Returns:
        The newly created and refreshed User instance.

    Raises:
        ValueError: If username is empty or whitespace.
        InvalidTimezoneError: If timezone is not a valid IANA timezone identifier.
        UserAlreadyExistsError: If a user with the same username or email already exists.
    """
    clean_username = username.strip() if username else ""
    if not clean_username:
        raise ValueError("Username cannot be empty.")

    clean_timezone = validate_timezone(timezone)

    user = User(
        username=clean_username,
        email=email.strip() if email else None,
        timezone=clean_timezone,
    )

    try:
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    except IntegrityError as exc:
        db.rollback()
        raise UserAlreadyExistsError(
            f"User with username '{clean_username}' or email '{email}' already exists."
        ) from exc
    except Exception:
        db.rollback()
        raise


def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    """Retrieve a user by their primary key ID.

    Args:
        db: Active SQLAlchemy database session.
        user_id: User integer primary key.

    Returns:
        The User instance if found, otherwise None.
    """
    return db.get(User, user_id)


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    """Retrieve a user by their unique username.

    Args:
        db: Active SQLAlchemy database session.
        username: User display name handle.

    Returns:
        The User instance if found, otherwise None.
    """
    stmt = select(User).where(User.username == username.strip())
    return db.execute(stmt).scalar_one_or_none()
