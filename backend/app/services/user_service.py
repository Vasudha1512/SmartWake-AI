"""Service layer for User creation and retrieval operations."""
from typing import Optional
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.exceptions import UserAlreadyExistsError
from backend.app.models.user import User


def create_user(
    db: Session,
    username: str,
    email: Optional[str] = None,
    timezone: str = "UTC",
) -> User:
    """Create a new user record in the database.

    Args:
        db: Active SQLAlchemy database session.
        username: Unique username handle.
        email: Optional unique email address.
        timezone: Local timezone (defaults to 'UTC').

    Returns:
        The newly created and refreshed User instance.

    Raises:
        ValueError: If username is empty or whitespace.
        UserAlreadyExistsError: If a user with the same username or email already exists.
    """
    clean_username = username.strip() if username else ""
    if not clean_username:
        raise ValueError("Username cannot be empty.")

    user = User(
        username=clean_username,
        email=email.strip() if email else None,
        timezone=timezone.strip() if timezone else "UTC",
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
