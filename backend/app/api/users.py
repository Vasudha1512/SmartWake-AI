"""API route handlers for User operations."""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.exceptions import InvalidTimezoneError, UserAlreadyExistsError
from backend.app.database.session import get_db
from backend.app.schemas.alarm_schemas import AlarmResponse
from backend.app.schemas.user_schemas import UserCreate, UserResponse
from backend.app.schemas.wake_session_schemas import WakeSessionResponse
from backend.app.services import alarm_service, user_service, wake_session_service

router = APIRouter()


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create User",
)
def create_user_endpoint(
    user_in: UserCreate,
    db: Session = Depends(get_db),
):
    """Create a new user with a unique username and optional email/timezone."""
    try:
        user = user_service.create_user(
            db=db,
            username=user_in.username,
            email=user_in.email,
            timezone=user_in.timezone,
        )
        return user
    except UserAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except (ValueError, InvalidTimezoneError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get User by ID",
)
def get_user_endpoint(
    user_id: int,
    db: Session = Depends(get_db),
):
    """Retrieve a specific user profile by primary key ID."""
    user = user_service.get_user_by_id(db=db, user_id=user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with id {user_id} not found.",
        )
    return user


@router.get(
    "/{user_id}/alarms",
    response_model=List[AlarmResponse],
    status_code=status.HTTP_200_OK,
    summary="Get User Alarms",
)
def get_user_alarms_endpoint(
    user_id: int,
    db: Session = Depends(get_db),
):
    """Retrieve all alarms configured by a specific user."""
    user = user_service.get_user_by_id(db=db, user_id=user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with id {user_id} not found.",
        )
    return alarm_service.get_alarms_by_user(db=db, user_id=user_id)


@router.get(
    "/{user_id}/wake-sessions",
    response_model=List[WakeSessionResponse],
    status_code=status.HTTP_200_OK,
    summary="Get User Wake Sessions History",
)
def get_user_wake_sessions_endpoint(
    user_id: int,
    db: Session = Depends(get_db),
):
    """Retrieve all historical wake sessions for a specific user, newest first."""
    user = user_service.get_user_by_id(db=db, user_id=user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with id {user_id} not found.",
        )
    return wake_session_service.get_wake_sessions_by_user(db=db, user_id=user_id)

