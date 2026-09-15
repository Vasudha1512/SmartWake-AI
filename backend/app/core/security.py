"""Security, password hashing, and JWT token utilities for SmartWake AI.

Implements NIST / OWASP-aligned PBKDF2-HMAC-SHA256 password hashing (600,000 iterations)
and standard RFC 7519 HS256 JWT generation and verification using Python's standard library.
"""
import base64
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from backend.app.core.config import settings
from backend.app.core.exceptions import (
    AuthenticationError,
    InvalidTokenError,
    SmartWakeException,
)

# Security Constants
HASH_ALGORITHM = "sha256"
PBKDF2_ITERATIONS = 600_000
SALT_BYTES = 16
CLOCK_SKEW_TOLERANCE_SECONDS = 60



# ---------------------------------------------------------------------------
# Password Security (PBKDF2-HMAC-SHA256, 600,000 rounds)
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Hash a plaintext password using PBKDF2-HMAC-SHA256 with 600,000 iterations.

    Args:
        password: Plaintext user password string.

    Returns:
        Formatted string: "pbkdf2_sha256$iterations$salt_hex$hash_hex"
    """
    if not isinstance(password, str) or not password:
        raise ValueError("Password must be a non-empty string.")

    salt = secrets.token_bytes(SALT_BYTES)
    derived = hashlib.pbkdf2_hmac(
        HASH_ALGORITHM,
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${derived.hex()}"


def verify_password(plain_password: str, hashed_password: Optional[str]) -> bool:
    """Verify a candidate password against a stored PBKDF2 hash using constant-time comparison.

    Args:
        plain_password: Plaintext password candidate.
        hashed_password: Stored formatted hash string.

    Returns:
        True if the candidate matches the stored hash, False otherwise.
    """
    if not plain_password or not hashed_password or not isinstance(hashed_password, str):
        return False

    parts = hashed_password.split("$")
    if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
        return False

    try:
        iterations = int(parts[1])
        salt = bytes.fromhex(parts[2])
        stored_hash = bytes.fromhex(parts[3])
    except (ValueError, TypeError):
        return False

    candidate_hash = hashlib.pbkdf2_hmac(
        HASH_ALGORITHM,
        plain_password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(candidate_hash, stored_hash)


# ---------------------------------------------------------------------------
# JWT Token Handling (RFC 7519, HS256, Minimal Payload)
# ---------------------------------------------------------------------------

def _b64url_encode(data: bytes) -> str:
    """Encode bytes into standard Base64URL string without trailing padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    """Decode a Base64URL string into bytes, restoring proper padding."""
    if not isinstance(s, str):
        raise InvalidTokenError("Invalid token encoding.")
    padding = 4 - (len(s) % 4)
    if padding != 4:
        s += "=" * padding
    try:
        return base64.urlsafe_b64decode(s.encode("ascii"))
    except Exception as exc:
        raise InvalidTokenError("Invalid token encoding.") from exc


def create_access_token(
    user_id: int,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Generate an RFC 7519 HS256 JWT access token with minimal payload.

    Payload strictly contains:
      - sub: user_id string
      - iat: issued-at timestamp (epoch seconds)
      - exp: expiration timestamp (epoch seconds)

    Args:
        user_id: The primary key ID of the user.
        expires_delta: Optional custom lifetime duration.

    Returns:
        Compact dot-delimited JWT string: header.payload.signature
    """
    settings.validate_auth_config()
    secret_key = settings.JWT_SECRET_KEY.strip()

    now_epoch = int(time.time())
    if expires_delta:
        expire_epoch = int((datetime.now(timezone.utc) + expires_delta).timestamp())
    else:
        expire_epoch = now_epoch + (settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60)

    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": str(user_id),
        "iat": now_epoch,
        "exp": expire_epoch,
    }

    header_bytes = json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")

    header_b64 = _b64url_encode(header_bytes)
    payload_b64 = _b64url_encode(payload_bytes)

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = hmac.new(secret_key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    signature_b64 = _b64url_encode(signature)

    return f"{header_b64}.{payload_b64}.{signature_b64}"


def decode_access_token(token: str) -> Dict[str, Any]:
    """Rigorously validate and decode an RFC 7519 HS256 JWT access token.

    Performs full cryptographic and semantic validation:
      1. Validates 3-part structure.
      2. Validates header claims: strictly requires alg == 'HS256' and typ == 'JWT'.
      3. Verifies HMAC-SHA256 signature using constant-time comparison.
      4. Validates payload claims:
         - sub: non-empty user identifier
         - exp: token must not be expired (allows 60s clock skew)
         - iat: token must not be issued > 60s in the future

    Args:
        token: Compact JWT string.

    Returns:
        Decoded payload dictionary.

    Raises:
        InvalidTokenError: If any verification check fails.
    """
    settings.validate_auth_config()
    secret_key = settings.JWT_SECRET_KEY.strip()

    if not token or not isinstance(token, str):
        raise InvalidTokenError("Authentication token is missing or empty.")

    parts = token.strip().split(".")
    if len(parts) != 3:
        raise InvalidTokenError("Invalid token structure.")

    header_b64, payload_b64, signature_b64 = parts

    # 1. Decode and strictly validate Header
    try:
        header_raw = _b64url_decode(header_b64)
        header = json.loads(header_raw.decode("utf-8"))
    except Exception as exc:
        raise InvalidTokenError("Invalid token header.") from exc

    if not isinstance(header, dict):
        raise InvalidTokenError("Invalid token header format.")

    # Strictly reject unsigned ('none'), missing, or unsupported algorithms
    if header.get("alg") != "HS256" or header.get("typ") != "JWT":
        raise InvalidTokenError("Unsupported or invalid token algorithm.")

    # 2. Verify Signature using constant-time comparison
    try:
        candidate_sig = _b64url_decode(signature_b64)
    except Exception as exc:
        raise InvalidTokenError("Invalid token signature encoding.") from exc

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected_sig = hmac.new(secret_key.encode("utf-8"), signing_input, hashlib.sha256).digest()

    if not hmac.compare_digest(candidate_sig, expected_sig):
        raise InvalidTokenError("Invalid token signature.")

    # 3. Decode Payload
    try:
        payload_raw = _b64url_decode(payload_b64)
        payload = json.loads(payload_raw.decode("utf-8"))
    except Exception as exc:
        raise InvalidTokenError("Invalid token payload.") from exc

    if not isinstance(payload, dict):
        raise InvalidTokenError("Invalid token payload format.")

    now_epoch = int(time.time())

    # 4. Validate 'sub' claim
    sub = payload.get("sub")
    if not sub or not isinstance(sub, str):
        raise InvalidTokenError("Token missing valid subject claim.")

    # 5. Validate 'iat' claim with explicit clock-skew rule:
    # Reject tokens where iat is more than 60 seconds in the future
    iat = payload.get("iat")
    if iat is None or not isinstance(iat, (int, float)):
        raise InvalidTokenError("Token missing valid issued-at timestamp.")
    if iat > now_epoch + CLOCK_SKEW_TOLERANCE_SECONDS:
        raise InvalidTokenError("Token issued in the future beyond clock-skew tolerance.")

    # 6. Validate 'exp' claim with clock-skew tolerance
    exp = payload.get("exp")
    if exp is None or not isinstance(exp, (int, float)):
        raise InvalidTokenError("Token missing valid expiration timestamp.")
    if exp < now_epoch - CLOCK_SKEW_TOLERANCE_SECONDS:
        raise InvalidTokenError("Token has expired.")

    return payload
