"""API route handlers for WakeSession lifecycle operations."""
from fastapi import APIRouter, Depends, HTTPException, status
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
from backend.app.database.session import get_db
from backend.app.schemas.wake_session_schemas import WakeSessionCreate, WakeSessionResponse
from backend.app.services import wake_session_service

router = APIRouter()


@router.post(
    "",
    response_model=WakeSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create / Start Wake Session",
)
def create_wake_session_endpoint(
    session_in: WakeSessionCreate,
    db: Session = Depends(get_db),
):
    """Create and start a new wake session for an active alarm occurrence.

    Validation Rules:
    - user_id must exist (404 if missing).
    - alarm_id must exist (404 if missing).
    - alarm must belong to the user (400 if mismatched).
    - alarm must be active (400 if inactive).
    - duplicate simultaneous active session is prevented (409 Conflict).
    """
    try:
        wake_session = wake_session_service.create_wake_session(
            db=db,
            user_id=session_in.user_id,
            alarm_id=session_in.alarm_id,
            scheduled_time=session_in.scheduled_time,
        )
        return wake_session
    except (UserNotFoundError, AlarmNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except (AlarmOwnershipError, InactiveAlarmError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ActiveSessionExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get(
    "/{session_id}",
    response_model=WakeSessionResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Wake Session by ID",
)
def get_wake_session_endpoint(
    session_id: int,
    db: Session = Depends(get_db),
):
    """Retrieve a wake session by primary key ID."""
    wake_session = wake_session_service.get_wake_session_by_id(db=db, session_id=session_id)
    if not wake_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Wake session with id {session_id} not found.",
        )
    return wake_session


@router.patch(
    "/{session_id}/in-progress",
    response_model=WakeSessionResponse,
    status_code=status.HTTP_200_OK,
    summary="Transition Session to IN_PROGRESS",
)
@router.patch(
    "/{session_id}/start-challenge",
    response_model=WakeSessionResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
def transition_in_progress_endpoint(
    session_id: int,
    db: Session = Depends(get_db),
):
    """Transition a ringing wake session into IN_PROGRESS ('in_challenge')."""
    try:
        return wake_session_service.transition_to_in_progress(db=db, session_id=session_id)
    except WakeSessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except InvalidSessionTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.patch(
    "/{session_id}/complete",
    response_model=WakeSessionResponse,
    status_code=status.HTTP_200_OK,
    summary="Complete Wake Session",
)
def complete_wake_session_endpoint(
    session_id: int,
    db: Session = Depends(get_db),
):
    """Complete a wake session successfully (challenge passed, alarm dismissed)."""
    try:
        return wake_session_service.complete_wake_session(db=db, session_id=session_id)
    except WakeSessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except InvalidSessionTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.patch(
    "/{session_id}/fail",
    response_model=WakeSessionResponse,
    status_code=status.HTTP_200_OK,
    summary="Fail / Abandon Wake Session",
)
@router.patch(
    "/{session_id}/abandon",
    response_model=WakeSessionResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
def fail_wake_session_endpoint(
    session_id: int,
    db: Session = Depends(get_db),
):
    """Mark a wake session as failed or abandoned."""
    try:
        return wake_session_service.fail_wake_session(db=db, session_id=session_id)
    except WakeSessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except InvalidSessionTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
