"""FastAPI endpoint router for the Challenge Catalog."""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.exceptions import (
    ActiveChallengeAttemptExistsError,
    ChallengeAttemptCompletedError,
    ChallengeAttemptNotFoundError,
    ChallengeAttemptOwnershipError,
    ChallengeNotFoundError,
    InactiveChallengeError,
    InvalidChallengeTypeError,
    InvalidDifficultyError,
    InvalidSessionTransitionError,
    InvalidTemplatePayloadError,
    TemplateConfigurationError,
    WakeSessionNotFoundError,
)
from backend.app.database.session import get_db
from backend.app.schemas.challenge_schemas import (
    ChallengeAttemptResponse,
    ChallengeAttemptStartRequest,
    ChallengeAttemptSubmitRequest,
    ChallengeResponse,
    ChallengeVerificationRequest,
    ChallengeVerificationResult,
    RuntimeChallengeGenerationRequest,
    RuntimeChallengeResponse,
)
from backend.app.services import challenge_service

router = APIRouter()


@router.post(
    "/attempts/start",
    response_model=ChallengeAttemptResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start Challenge Attempt",
)
def start_challenge_attempt_endpoint(
    request: ChallengeAttemptStartRequest,
    db: Session = Depends(get_db),
):
    """Start and persist a new challenge execution attempt for an active WakeSession."""
    try:
        return challenge_service.start_challenge_attempt(db=db, request=request)
    except WakeSessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ChallengeAttemptOwnershipError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except ActiveChallengeAttemptExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except ChallengeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except (
        InvalidSessionTransitionError,
        InvalidChallengeTypeError,
        InactiveChallengeError,
        InvalidDifficultyError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/attempts/{attempt_id}/submit",
    response_model=ChallengeAttemptResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit Challenge Attempt",
)
def submit_challenge_attempt_endpoint(
    attempt_id: int,
    request: ChallengeAttemptSubmitRequest,
    db: Session = Depends(get_db),
):
    """Submit a challenge answer/result for verification and complete/retry tracking."""
    try:
        return challenge_service.submit_challenge_attempt(
            db=db,
            attempt_id=attempt_id,
            user_id=request.user_id,
            submission_data=request.submission_data,
        )
    except ChallengeAttemptNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ChallengeAttemptOwnershipError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except (
        ChallengeAttemptCompletedError,
        InvalidSessionTransitionError,
        InvalidChallengeTypeError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get(
    "/attempts/{attempt_id}",
    response_model=ChallengeAttemptResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Challenge Attempt by ID",
)
def get_challenge_attempt_endpoint(
    attempt_id: int,
    user_id: int,
    db: Session = Depends(get_db),
):
    """Retrieve an individual ChallengeAttempt by ID with ownership verification."""
    try:
        return challenge_service.get_challenge_attempt(
            db=db, attempt_id=attempt_id, user_id=user_id
        )
    except ChallengeAttemptNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ChallengeAttemptOwnershipError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


@router.post(
    "/verify",
    response_model=ChallengeVerificationResult,
    status_code=status.HTTP_200_OK,
    summary="Verify Challenge Submission",
)
def verify_challenge_endpoint(
    request: ChallengeVerificationRequest,
):
    """Verify a user submission against a RuntimeChallenge without database mutation.

    Deterministically validates answers or patterns according to the challenge type.
    """
    try:
        return challenge_service.verify_challenge(
            runtime_challenge=request.runtime_challenge,
            submission_data=request.submission_data,
        )
    except InvalidChallengeTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.post(
    "/generate",
    response_model=RuntimeChallengeResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate Runtime Challenge",
)
def generate_challenge_endpoint(
    request: RuntimeChallengeGenerationRequest,
    db: Session = Depends(get_db),
):
    """Generate an in-memory runtime challenge instance from an active catalog template.

    Accepts challenge_type and optional difficulty_level, or a specific template_id.
    Procedurally creates concrete tasks (equations, visual sequence, routine, text, reps)
    without persisting to the database.
    """
    try:
        return challenge_service.generate_challenge(db=db, request=request)
    except (
        InvalidChallengeTypeError,
        InvalidDifficultyError,
        InactiveChallengeError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ChallengeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except (InvalidTemplatePayloadError, TemplateConfigurationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.get(
    "",
    response_model=List[ChallengeResponse],
    status_code=status.HTTP_200_OK,
    summary="List Active Challenges",
)
@router.get(
    "/",
    response_model=List[ChallengeResponse],
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
def list_challenges_endpoint(db: Session = Depends(get_db)):
    """Retrieve all active challenge records currently stored in the database."""
    return challenge_service.list_active_challenges(db=db)


@router.get(
    "/{challenge_id}",
    response_model=ChallengeResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Challenge by ID",
)
def get_challenge_by_id_endpoint(challenge_id: int, db: Session = Depends(get_db)):
    """Retrieve an individual challenge record by primary key ID."""
    challenge = challenge_service.get_challenge_by_id(db=db, challenge_id=challenge_id)
    if not challenge:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Challenge with id {challenge_id} not found.",
        )
    return challenge


@router.get(
    "/type/{challenge_type}",
    response_model=ChallengeResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Challenge by Type",
)
def get_challenge_by_type_endpoint(challenge_type: str, db: Session = Depends(get_db)):
    """Retrieve an active challenge record for the specified challenge type.

    Validates challenge_type against canonical VALID_CHALLENGE_TYPES.
    Returns 400 for invalid/forbidden challenge types.
    Returns 404 if no active challenge record of this type exists in the database.
    """
    try:
        challenge = challenge_service.get_challenge_by_type(db=db, challenge_type=challenge_type)
    except InvalidChallengeTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if not challenge:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Challenge of type '{challenge_type}' not found in database.",
        )
    return challenge
