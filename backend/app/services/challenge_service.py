"""Service layer for Challenge catalog operations in SmartWake AI.

ARCHITECTURAL RULES:
1. The user explicitly selects the challenge type when creating an alarm.
2. The five mandatory challenge types are: dance, math, memory, tongue_twister, push_ups.
3. Memory challenges must NOT be implemented as number guessing.
4. The service operates strictly against actual Challenge database records.
5. ML and challenge verification are deferred to later phases.
"""
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.constants import FORBIDDEN_CHALLENGE_TYPES, VALID_CHALLENGE_TYPES
from backend.app.core.exceptions import InvalidChallengeTypeError
from backend.app.models.challenge import Challenge
from backend.app.services.challenge_execution_service import (
    get_challenge_attempt,
    list_attempts_for_wake_session,
    start_challenge_attempt,
    submit_challenge_attempt,
)
from backend.app.services.challenge_generation_service import generate_challenge
from backend.app.services.challenge_seed_service import (
    DEFAULT_CHALLENGE_CATALOG,
    SeedResult,
    seed_default_challenges,
)
from backend.app.services.challenge_verification_service import verify_challenge


def validate_challenge_type(task_type: str) -> str:
    """Validate that the challenge type is one of the five approved task categories.

    Explicitly rejects number-guessing and unknown task types.

    Args:
        task_type: The challenge type string to validate.

    Returns:
        Clean, validated challenge type string.

    Raises:
        InvalidChallengeTypeError: If task_type is invalid or forbidden.
    """
    clean_type = task_type.strip().lower() if task_type else ""
    if clean_type in FORBIDDEN_CHALLENGE_TYPES:
        raise InvalidChallengeTypeError(
            f"Challenge type '{task_type}' is strictly forbidden. "
            f"Memory challenges must NOT be implemented as number guessing."
        )
    if clean_type not in VALID_CHALLENGE_TYPES:
        raise InvalidChallengeTypeError(
            f"Invalid challenge type '{task_type}'. Must be one of: {sorted(list(VALID_CHALLENGE_TYPES))}."
        )
    return clean_type


def list_active_challenges(db: Session) -> List[Challenge]:
    """Retrieve all active Challenge records currently stored in the database.

    Args:
        db: Active SQLAlchemy database session.

    Returns:
        List of active Challenge instances ordered by id ascending.
    """
    stmt = (
        select(Challenge)
        .where(Challenge.is_active == True)  # noqa: E712
        .order_by(Challenge.id.asc())
    )
    return list(db.scalars(stmt).all())


def get_challenge_by_id(db: Session, challenge_id: int) -> Optional[Challenge]:
    """Retrieve an individual Challenge record by primary key ID.

    Args:
        db: Active SQLAlchemy database session.
        challenge_id: ID of the challenge.

    Returns:
        Challenge instance or None if not found.
    """
    return db.get(Challenge, challenge_id)


def get_challenge_by_type(db: Session, challenge_type: str) -> Optional[Challenge]:
    """Retrieve an active Challenge record for a validated challenge type.

    Validates challenge_type against canonical VALID_CHALLENGE_TYPES.

    Args:
        db: Active SQLAlchemy database session.
        challenge_type: Challenge category string (e.g. 'dance', 'math', 'memory',
                        'tongue_twister', 'push_ups').

    Returns:
        Challenge instance or None if no active record exists for this type in the database.

    Raises:
        InvalidChallengeTypeError: If challenge_type is not a valid challenge category.
    """
    clean_type = validate_challenge_type(challenge_type)
    stmt = (
        select(Challenge)
        .where(Challenge.challenge_type == clean_type, Challenge.is_active == True)  # noqa: E712
        .order_by(Challenge.id.asc())
    )
    return db.scalars(stmt).first()


def list_active_challenge_types(db: Session) -> List[str]:
    """Retrieve distinct challenge types currently active in the database.

    Args:
        db: Active SQLAlchemy database session.

    Returns:
        List of distinct challenge type strings active in the database.
    """
    stmt = (
        select(Challenge.challenge_type)
        .where(Challenge.is_active == True)  # noqa: E712
        .distinct()
        .order_by(Challenge.challenge_type.asc())
    )
    return list(db.scalars(stmt).all())
