"""API route handlers for Alarm operations."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.exceptions import (
    InvalidAlarmTimeError,
    InvalidChallengeTypeError,
    InvalidDaysOfWeekError,
    InvalidDifficultyError,
    UserNotFoundError,
)
from backend.app.database.session import get_db
from backend.app.schemas.alarm_schemas import AlarmCreate, AlarmResponse, AlarmUpdate
from backend.app.services import alarm_service

router = APIRouter()


@router.post(
    "",
    response_model=AlarmResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Alarm",
)
def create_alarm_endpoint(
    alarm_in: AlarmCreate,
    db: Session = Depends(get_db),
):
    """Create a new scheduled alarm for an existing user.

    IMPORTANT PRODUCT RULES:
    1. The user explicitly controls the requested alarm time.
    2. The user explicitly selects the wake-up task type:
       'dance', 'math', 'memory', 'tongue_twister', 'push_ups'.
    3. The user sets baseline difficulty: 'adaptive', 'easy', 'medium', 'hard'.
    4. ML does not choose the task type or change the requested alarm time.
    """
    try:
        alarm = alarm_service.create_alarm(
            db=db,
            user_id=alarm_in.user_id,
            time=alarm_in.time,
            selected_challenge_type=alarm_in.selected_challenge_type,
            difficulty_preference=alarm_in.difficulty_preference,
            label=alarm_in.label or "Alarm",
            days_of_week=alarm_in.days_of_week,
            is_active=True if alarm_in.is_active is None else alarm_in.is_active,
        )
        return alarm
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except (
        InvalidAlarmTimeError,
        InvalidChallengeTypeError,
        InvalidDifficultyError,
        InvalidDaysOfWeekError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.get(
    "/{alarm_id}",
    response_model=AlarmResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Alarm by ID",
)
def get_alarm_endpoint(
    alarm_id: int,
    db: Session = Depends(get_db),
):
    """Retrieve an alarm configuration by primary key ID."""
    alarm = alarm_service.get_alarm_by_id(db=db, alarm_id=alarm_id)
    if not alarm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alarm with id {alarm_id} not found.",
        )
    return alarm


@router.put(
    "/{alarm_id}",
    response_model=AlarmResponse,
    status_code=status.HTTP_200_OK,
    summary="Update Alarm",
)
def update_alarm_endpoint(
    alarm_id: int,
    alarm_in: AlarmUpdate,
    db: Session = Depends(get_db),
):
    """Update supported configuration fields of an existing alarm.

    NOTE: user_id cannot be changed via this endpoint.
    """
    try:
        updated_alarm = alarm_service.update_alarm(
            db=db,
            alarm_id=alarm_id,
            time=alarm_in.time,
            selected_challenge_type=alarm_in.selected_challenge_type,
            difficulty_preference=alarm_in.difficulty_preference,
            label=alarm_in.label,
            days_of_week=alarm_in.days_of_week,
            is_active=alarm_in.is_active,
        )
        if not updated_alarm:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Alarm with id {alarm_id} not found.",
            )
        return updated_alarm
    except (
        InvalidAlarmTimeError,
        InvalidChallengeTypeError,
        InvalidDifficultyError,
        InvalidDaysOfWeekError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.patch(
    "/{alarm_id}/toggle",
    response_model=AlarmResponse,
    status_code=status.HTTP_200_OK,
    summary="Toggle Alarm Active State",
)
def toggle_alarm_endpoint(
    alarm_id: int,
    db: Session = Depends(get_db),
):
    """Toggle an alarm's active state between enabled (True) and disabled (False).

    Preserves historical relationships and returns the updated AlarmResponse.
    """
    toggled_alarm = alarm_service.toggle_alarm(db=db, alarm_id=alarm_id)
    if not toggled_alarm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alarm with id {alarm_id} not found.",
        )
    return toggled_alarm


@router.delete(
    "/{alarm_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete Alarm",
)
def delete_alarm_endpoint(
    alarm_id: int,
    db: Session = Depends(get_db),
):
    """Deactivate (logically delete) an alarm by primary key ID.

    Preserves the alarm row in the database with is_active = False to protect
    historical wake-session and ML telemetry.
    """
    deleted = alarm_service.delete_alarm(db=db, alarm_id=alarm_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alarm with id {alarm_id} not found.",
        )
    return {"detail": f"Alarm with id {alarm_id} deleted successfully."}

