"""API route handlers for user authentication and session management."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_user
from backend.app.core.exceptions import InvalidTimezoneError, UserAlreadyExistsError
from backend.app.core.security import AuthenticationError
from backend.app.database.session import get_db
from backend.app.models.user import User
from backend.app.schemas.auth_schemas import TokenResponse, UserLogin, UserRegister
from backend.app.schemas.user_schemas import UserResponse
from backend.app.services import auth_service

router = APIRouter()


@router.post(
    "/signup",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="User Registration",
)
def signup_endpoint(
    reg_data: UserRegister,
    db: Session = Depends(get_db),
):
    """Register a new user account with hashed password and unique constraints."""
    try:
        user = auth_service.register_user(db=db, reg_data=reg_data)
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


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="User Login",
)
def login_endpoint(
    login_data: UserLogin,
    db: Session = Depends(get_db),
):
    """Authenticate user credentials and issue an RFC 7519 HS256 JWT access token."""
    try:
        return auth_service.login_user(db=db, login_data=login_data)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Current User Profile",
)
def get_me_endpoint(
    current_user: User = Depends(get_current_user),
):
    """Retrieve the profile of the currently authenticated user."""
    return current_user
