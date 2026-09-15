"""Service layer for authentication, user registration, and login operations."""
from typing import Optional
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.exceptions import UserAlreadyExistsError
from backend.app.core.security import (
    AuthenticationError,
    create_access_token,
    hash_password,
    verify_password,
)
from backend.app.models.user import User
from backend.app.schemas.auth_schemas import TokenResponse, UserLogin, UserRegister
from backend.app.schemas.user_schemas import UserResponse
from backend.app.services.user_service import get_user_by_email, get_user_by_username


def register_user(db: Session, reg_data: UserRegister) -> User:
    """Register a new user with hashed password and unique identity constraints.

    Safely handles race conditions and unique constraint collisions using database IntegrityError.

    Args:
        db: Active SQLAlchemy session.
        reg_data: Validated UserRegister schema payload.

    Returns:
        The newly created and committed User model instance.

    Raises:
        UserAlreadyExistsError: If username or email is already registered.
    """
    clean_username = reg_data.username.strip()
    clean_email = reg_data.email.strip().lower()

    # Pre-check for cleaner error messages
    if get_user_by_email(db, clean_email):
        raise UserAlreadyExistsError(f"User with email '{clean_email}' already exists.")
    if get_user_by_username(db, clean_username):
        raise UserAlreadyExistsError(f"User with username '{clean_username}' already exists.")

    password_hash = hash_password(reg_data.password)

    user = User(
        username=clean_username,
        email=clean_email,
        hashed_password=password_hash,
        is_active=True,
        timezone=reg_data.timezone or "UTC",
    )

    try:
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    except IntegrityError as exc:
        db.rollback()
        raise UserAlreadyExistsError(
            "An account with this email or username already exists."
        ) from exc
    except Exception:
        db.rollback()
        raise


# Precomputed valid-format PBKDF2-HMAC-SHA256 hash (600,000 iterations)
# used for constant-time verification when a user or password hash does not exist.
DUMMY_PASSWORD_HASH = (
    "pbkdf2_sha256$600000$241f0c4c5d5008f25d102bca47dd49b3$"
    "c0f737491584ff1ce025490d4b29cd523ced864be28031797d52229ea70dac13"
)


def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    """Authenticate user credentials using constant-time password verification.

    Returns None for nonexistent users, inactive users, or invalid passwords
    without disclosing whether the account exists. Performs a dummy PBKDF2-HMAC-SHA256
    verification (600,000 iterations) using a precomputed hash when the account
    does not exist, preventing timing side-channel account enumeration.

    Args:
        db: Active SQLAlchemy session.
        email: Candidate user email.
        password: Candidate plaintext password.

    Returns:
        The User instance if authentication succeeds, otherwise None.
    """
    clean_email = email.strip().lower() if email else ""
    user = get_user_by_email(db, clean_email) if clean_email else None

    if not user or not user.is_active or not user.hashed_password:
        # Constant-time dummy verification using precomputed 600,000 round hash
        verify_password(password, DUMMY_PASSWORD_HASH)
        return None

    if not verify_password(password, user.hashed_password):
        return None

    return user



def login_user(db: Session, login_data: UserLogin) -> TokenResponse:
    """Authenticate credentials and issue a signed JWT access token.

    Args:
        db: Active SQLAlchemy session.
        login_data: Validated UserLogin payload.

    Returns:
        TokenResponse containing the JWT access token and public User profile.

    Raises:
        AuthenticationError: If credentials fail verification (generic message).
    """
    user = authenticate_user(
        db=db,
        email=login_data.email,
        password=login_data.password,
    )

    if not user:
        raise AuthenticationError("Invalid email or password.")

    access_token = create_access_token(user_id=user.id)
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )
