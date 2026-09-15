"""Comprehensive test suite and timing benchmark for SmartWake AI Authentication Foundation.

Tests:
- Configuration validation (enforcing 32+ char JWT_SECRET_KEY, no hardcoded fallbacks).
- PBKDF2-HMAC-SHA256 password hashing (600,000 iterations, salting, constant-time verification).
- RFC 7519 HS256 JWT creation, decoding, minimal payload (sub, iat, exp only), and clock skew tolerance.
- Registration endpoint (/api/v1/auth/signup): success, input validation, duplicate handling, IntegrityError safety.
- Login endpoint (/api/v1/auth/login): success, incorrect password, nonexistent user (generic error).
- Protected profile endpoint (/api/v1/auth/me): valid Bearer token, missing token, expired token, invalid signature.
- Timing benchmark: valid password vs incorrect password vs nonexistent email.
"""
import asyncio
import json
import os
import time
import unittest
from datetime import timedelta
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure test JWT secret is set before importing app config
TEST_JWT_SECRET = "smartwake-super-secret-test-key-32-chars-long!"
os.environ["JWT_SECRET_KEY"] = TEST_JWT_SECRET

from backend.app.core.config import Settings, settings
from backend.app.core.exceptions import UserAlreadyExistsError
from backend.app.core.security import (
    CLOCK_SKEW_TOLERANCE_SECONDS,
    HASH_ALGORITHM,
    PBKDF2_ITERATIONS,
    InvalidTokenError,
    _b64url_decode,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from backend.app.database.base import Base
import backend.app.models  # Register all models
from backend.app.database.session import get_db
from backend.app.main import app
from backend.app.models.user import User
from backend.app.schemas.auth_schemas import UserRegister
from backend.app.services.auth_service import (
    authenticate_user,
    login_user,
    register_user,
)


class SimpleASGIClient:
    """Lightweight ASGI test client using Python asyncio and standard library."""

    def __init__(self, asgi_app):
        self.app = asgi_app

    def _request(self, method: str, path: str, json_data=None, headers=None):
        return asyncio.run(self._async_request(method, path, json_data, headers))

    async def _async_request(self, method: str, path: str, json_data=None, headers=None):
        headers_list = []
        if headers:
            for k, v in headers.items():
                headers_list.append((k.lower().encode("latin1"), v.encode("latin1")))

        body_bytes = b""
        if json_data is not None:
            body_bytes = json.dumps(json_data).encode("utf-8")
            headers_list.append((b"content-type", b"application/json"))
            headers_list.append((b"content-length", str(len(body_bytes)).encode("latin1")))

        raw_path = path.encode("ascii")
        query_string = b""
        if "?" in path:
            p, qs = path.split("?", 1)
            raw_path = p.encode("ascii")
            path = p
            query_string = qs.encode("ascii")

        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.0"},
            "http_version": "1.1",
            "method": method.upper(),
            "scheme": "http",
            "path": path,
            "raw_path": raw_path,
            "query_string": query_string,
            "headers": headers_list,
            "server": ("127.0.0.1", 8000),
            "client": ("127.0.0.1", 50000),
        }

        messages = []
        sent_body = False

        async def receive():
            nonlocal sent_body
            if not sent_body:
                sent_body = True
                return {"type": "http.request", "body": body_bytes, "more_body": False}
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            messages.append(message)

        await self.app(scope, receive, send)

        status_code = next(m["status"] for m in messages if m["type"] == "http.response.start")
        raw_body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")

        class Response:
            def __init__(self, code, body):
                self.status_code = code
                self.text = body.decode("utf-8", errors="replace")

            def json(self):
                return json.loads(self.text)

        return Response(status_code, raw_body)

    def get(self, path: str, headers: dict = None):
        return self._request("GET", path, headers=headers)

    def post(self, path: str, json: dict = None, headers: dict = None):
        return self._request("POST", path, json_data=json, headers=headers)


class TestAuthenticationFoundation(unittest.TestCase):
    """Full unit and integration test suite for Authentication Foundation."""

    @classmethod
    def setUpClass(cls):
        """Initialize in-memory SQLite database and override get_db dependency."""
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.TestingSessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=cls.engine
        )
        Base.metadata.create_all(bind=cls.engine)

        def override_get_db():
            db: Session = cls.TestingSessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = SimpleASGIClient(app)

    @classmethod
    def tearDownClass(cls):
        """Clean up dependency overrides and drop all tables."""
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=cls.engine)

    def setUp(self):
        """Ensure fresh tables for each test method."""
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = self.TestingSessionLocal()

    def tearDown(self):
        """Close active test session."""
        self.db.close()

    # -----------------------------------------------------------------------
    # 1. Config Validation Tests
    # -----------------------------------------------------------------------

    def test_config_validation_missing_key_raises_error(self):
        """validate_auth_config must raise ValueError if JWT_SECRET_KEY is empty."""
        test_settings = Settings(JWT_SECRET_KEY="")
        with self.assertRaises(ValueError) as ctx:
            test_settings.validate_auth_config()
        self.assertIn("JWT_SECRET_KEY environment variable is required", str(ctx.exception))

    def test_config_validation_short_key_raises_error(self):
        """validate_auth_config must raise ValueError if JWT_SECRET_KEY is under 32 chars."""
        test_settings = Settings(JWT_SECRET_KEY="short-secret-key")
        with self.assertRaises(ValueError) as ctx:
            test_settings.validate_auth_config()
        self.assertIn("at least 32 characters", str(ctx.exception))

    def test_config_validation_valid_key_passes(self):
        """validate_auth_config passes cleanly when key has 32+ characters."""
        test_settings = Settings(JWT_SECRET_KEY="this-key-is-sufficiently-long-and-secure-32-chars")
        # Should not raise
        test_settings.validate_auth_config()

    def test_config_validation_invalid_expire_minutes_raises_error(self):
        """validate_auth_config must raise ValueError if ACCESS_TOKEN_EXPIRE_MINUTES is <= 0."""
        test_settings = Settings(
            JWT_SECRET_KEY="this-key-is-sufficiently-long-and-secure-32-chars",
            ACCESS_TOKEN_EXPIRE_MINUTES=0,
        )
        with self.assertRaises(ValueError) as ctx:
            test_settings.validate_auth_config()
        self.assertIn("ACCESS_TOKEN_EXPIRE_MINUTES must be an integer greater than 0", str(ctx.exception))

        test_settings_neg = Settings(
            JWT_SECRET_KEY="this-key-is-sufficiently-long-and-secure-32-chars",
            ACCESS_TOKEN_EXPIRE_MINUTES=-30,
        )
        with self.assertRaises(ValueError) as ctx:
            test_settings_neg.validate_auth_config()
        self.assertIn("ACCESS_TOKEN_EXPIRE_MINUTES must be an integer greater than 0", str(ctx.exception))

    def test_config_validation_non_hs256_algorithm_raises_error(self):
        """validate_auth_config must raise ValueError if JWT_ALGORITHM is not HS256."""
        test_settings = Settings(
            JWT_SECRET_KEY="this-key-is-sufficiently-long-and-secure-32-chars",
            JWT_ALGORITHM="RS256",
        )
        with self.assertRaises(ValueError) as ctx:
            test_settings.validate_auth_config()
        self.assertIn("Authentication strictly supports HS256 algorithm only", str(ctx.exception))

    def test_init_db_migration_error_surfaces_cleanly(self):
        """init_db must allow SQLite migration errors to surface and not silently swallow them."""
        from backend.app.database.init_db import init_db
        from unittest.mock import patch

        with patch("backend.app.database.init_db.engine.connect") as mock_conn:
            mock_conn.side_effect = RuntimeError("Simulated SQLite connection failure")
            with self.assertRaises(RuntimeError) as ctx:
                init_db()
            self.assertIn("Simulated SQLite connection failure", str(ctx.exception))

    def test_init_db_idempotent(self):
        """init_db must be idempotent and safe to run multiple times without error."""
        from backend.app.database.init_db import init_db
        # Calling init_db twice must not raise any duplicate column errors
        init_db()
        init_db()


    # -----------------------------------------------------------------------
    # 2. Password Security & Hashing Tests
    # -----------------------------------------------------------------------

    def test_password_hash_format_and_iteration_count(self):
        """Password hash must use PBKDF2-HMAC-SHA256 with exactly 600,000 iterations."""
        pw = "SecretPassword123!"
        hashed = hash_password(pw)
        self.assertTrue(hashed.startswith("pbkdf2_sha256$600000$"))
        parts = hashed.split("$")
        self.assertEqual(len(parts), 4)
        self.assertEqual(int(parts[1]), 600_000)
        # Salt should be 16 bytes = 32 hex chars
        self.assertEqual(len(parts[2]), 32)
        # SHA-256 hash should be 32 bytes = 64 hex chars
        self.assertEqual(len(parts[3]), 64)

    def test_password_hash_is_salted(self):
        """Two hashes of the exact same password must produce distinct hashes."""
        pw = "MySecurePassword2026"
        h1 = hash_password(pw)
        h2 = hash_password(pw)
        self.assertNotEqual(h1, h2)
        self.assertTrue(verify_password(pw, h1))
        self.assertTrue(verify_password(pw, h2))

    def test_verify_password_correct_and_incorrect(self):
        """verify_password returns True for valid password, False for incorrect."""
        pw = "CorrectHorseBatteryStaple!"
        hashed = hash_password(pw)
        self.assertTrue(verify_password(pw, hashed))
        self.assertFalse(verify_password("WrongPassword!", hashed))
        self.assertFalse(verify_password("", hashed))
        self.assertFalse(verify_password(pw, None))
        self.assertFalse(verify_password(pw, "invalid_hash_string"))

    # -----------------------------------------------------------------------
    # 3. JWT Token Generation & Validation (RFC 7519, Minimal Payload)
    # -----------------------------------------------------------------------

    def test_create_and_decode_jwt_minimal_payload(self):
        """JWT payload must strictly contain only 'sub', 'iat', and 'exp' (no email)."""
        token = create_access_token(user_id=42)
        self.assertIsInstance(token, str)
        parts = token.split(".")
        self.assertEqual(len(parts), 3)

        decoded = decode_access_token(token)
        # Strictly verify payload keys
        self.assertEqual(set(decoded.keys()), {"sub", "iat", "exp"})
        self.assertEqual(decoded["sub"], "42")
        self.assertIsInstance(decoded["iat"], int)
        self.assertIsInstance(decoded["exp"], int)
        self.assertGreater(decoded["exp"], decoded["iat"])

    def test_jwt_tampered_signature_rejected(self):
        """Tokens with modified payload or invalid signature must be rejected."""
        token = create_access_token(user_id=1)
        parts = token.split(".")
        # Tamper with signature
        tampered_token = f"{parts[0]}.{parts[1]}.tampered_signature"
        with self.assertRaises(InvalidTokenError):
            decode_access_token(tampered_token)

    def test_jwt_expired_token_rejected_beyond_skew(self):
        """Tokens expired by more than 60 seconds clock-skew tolerance must be rejected."""
        # Expired 90 seconds ago
        expired_delta = timedelta(seconds=-90)
        token = create_access_token(user_id=1, expires_delta=expired_delta)
        with self.assertRaises(InvalidTokenError) as ctx:
            decode_access_token(token)
        self.assertIn("expired", str(ctx.exception).lower())

    def test_jwt_expired_within_clock_skew_accepted(self):
        """Tokens expired by <= 60 seconds are tolerated due to clock-skew allowance."""
        # Expired 30 seconds ago (within 60s tolerance)
        expired_delta = timedelta(seconds=-30)
        token = create_access_token(user_id=7, expires_delta=expired_delta)
        decoded = decode_access_token(token)
        self.assertEqual(decoded["sub"], "7")

    def test_jwt_iat_in_future_rejected_if_beyond_skew(self):
        """Tokens where iat is more than 60 seconds in the future must be rejected."""
        token = create_access_token(user_id=5)
        parts = token.split(".")
        # Decode and modify iat to +120 seconds in future
        payload = json.loads(_b64url_decode(parts[1]).decode("utf-8"))
        payload["iat"] = int(time.time()) + 120
        # Re-sign using security helpers
        import hashlib, hmac
        from backend.app.core.security import _b64url_encode
        new_payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        signing_input = f"{parts[0]}.{new_payload_b64}".encode("ascii")
        sig = hmac.new(settings.JWT_SECRET_KEY.encode("utf-8"), signing_input, hashlib.sha256).digest()
        future_token = f"{parts[0]}.{new_payload_b64}.{_b64url_encode(sig)}"

        with self.assertRaises(InvalidTokenError) as ctx:
            decode_access_token(future_token)
        self.assertIn("future", str(ctx.exception).lower())

    def test_jwt_iat_up_to_60s_in_future_accepted(self):
        """Tokens where iat is up to 60 seconds in the future are accepted (clock-skew)."""
        token = create_access_token(user_id=5)
        parts = token.split(".")
        payload = json.loads(_b64url_decode(parts[1]).decode("utf-8"))
        payload["iat"] = int(time.time()) + 45  # 45s in future <= 60s
        import hashlib, hmac
        from backend.app.core.security import _b64url_encode
        new_payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        signing_input = f"{parts[0]}.{new_payload_b64}".encode("ascii")
        sig = hmac.new(settings.JWT_SECRET_KEY.encode("utf-8"), signing_input, hashlib.sha256).digest()
        future_token = f"{parts[0]}.{new_payload_b64}.{_b64url_encode(sig)}"

        decoded = decode_access_token(future_token)
        self.assertEqual(decoded["sub"], "5")

    # -----------------------------------------------------------------------
    # 4. User Registration API Tests (/api/v1/auth/signup)
    # -----------------------------------------------------------------------

    def test_signup_success(self):
        """POST /api/v1/auth/signup registers a user with 201 Created and safe response."""
        payload = {
            "username": "alice",
            "email": "alice@example.com",
            "password": "Password123!",
            "timezone": "America/New_York",
        }
        res = self.client.post("/api/v1/auth/signup", json=payload)
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data["username"], "alice")
        self.assertEqual(data["email"], "alice@example.com")
        self.assertEqual(data["timezone"], "America/New_York")
        self.assertTrue(data["is_active"])
        self.assertNotIn("password", data)
        self.assertNotIn("hashed_password", data)

        # Verify DB entry
        user = self.db.query(User).filter_by(username="alice").first()
        self.assertIsNotNone(user)
        self.assertTrue(user.hashed_password.startswith("pbkdf2_sha256$600000$"))
        self.assertTrue(verify_password("Password123!", user.hashed_password))

    def test_signup_duplicate_email_rejected(self):
        """Duplicate email registration returns 400 Bad Request."""
        payload1 = {
            "username": "user1",
            "email": "duplicate@example.com",
            "password": "Password123!",
        }
        res1 = self.client.post("/api/v1/auth/signup", json=payload1)
        self.assertEqual(res1.status_code, 201)

        payload2 = {
            "username": "user2",
            "email": "duplicate@example.com",
            "password": "Password456!",
        }
        res2 = self.client.post("/api/v1/auth/signup", json=payload2)
        self.assertEqual(res2.status_code, 400)
        self.assertIn("already exists", res2.json()["detail"])

    def test_signup_duplicate_username_rejected(self):
        """Duplicate username registration returns 400 Bad Request."""
        payload1 = {
            "username": "samename",
            "email": "unique1@example.com",
            "password": "Password123!",
        }
        res1 = self.client.post("/api/v1/auth/signup", json=payload1)
        self.assertEqual(res1.status_code, 201)

        payload2 = {
            "username": "samename",
            "email": "unique2@example.com",
            "password": "Password456!",
        }
        res2 = self.client.post("/api/v1/auth/signup", json=payload2)
        self.assertEqual(res2.status_code, 400)
        self.assertIn("already exists", res2.json()["detail"])

    def test_signup_database_integrity_error_safety(self):
        """Database IntegrityError during register_user must rollback and return UserAlreadyExistsError safely."""
        reg_data = UserRegister(
            username="concurrent_user",
            email="concurrent@example.com",
            password="Password123!",
        )
        # Pre-insert raw user with same email to bypass pre-checks and trigger DB IntegrityError
        raw_user = User(username="concurrent_user", email="concurrent@example.com", hashed_password="dummy")
        self.db.add(raw_user)
        self.db.commit()

        # Attempting register_user with same data must catch IntegrityError and raise UserAlreadyExistsError
        with patch("backend.app.services.auth_service.get_user_by_email", return_value=None), \
             patch("backend.app.services.auth_service.get_user_by_username", return_value=None):
            with self.assertRaises(UserAlreadyExistsError):
                register_user(self.db, reg_data)

    def test_signup_invalid_inputs(self):
        """Short passwords (<8 chars) or invalid email format return 422 Unprocessable Entity."""
        # Short password
        res = self.client.post("/api/v1/auth/signup", json={
            "username": "shortpass",
            "email": "short@example.com",
            "password": "123",
        })
        self.assertEqual(res.status_code, 422)

        # Invalid email
        res = self.client.post("/api/v1/auth/signup", json={
            "username": "bademail",
            "email": "not-an-email",
            "password": "ValidPassword123!",
        })
        self.assertEqual(res.status_code, 422)

    # -----------------------------------------------------------------------
    # 5. User Login API Tests (/api/v1/auth/login)
    # -----------------------------------------------------------------------

    def test_login_success(self):
        """POST /api/v1/auth/login returns 200 OK with valid JWT and User profile."""
        # Register user first
        signup_payload = {
            "username": "bob",
            "email": "bob@example.com",
            "password": "BobsPassword123!",
            "timezone": "UTC",
        }
        self.client.post("/api/v1/auth/signup", json=signup_payload)

        login_payload = {
            "email": "bob@example.com",
            "password": "BobsPassword123!",
        }
        res = self.client.post("/api/v1/auth/login", json=login_payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("access_token", data)
        self.assertEqual(data["token_type"], "bearer")
        self.assertEqual(data["user"]["username"], "bob")
        self.assertEqual(data["user"]["email"], "bob@example.com")

        # Decode token to verify minimal payload
        payload = decode_access_token(data["access_token"])
        self.assertEqual(set(payload.keys()), {"sub", "iat", "exp"})

    def test_login_incorrect_password_generic_error(self):
        """Login with wrong password returns 401 with generic error message."""
        signup_payload = {
            "username": "carol",
            "email": "carol@example.com",
            "password": "CarolsPassword123!",
        }
        self.client.post("/api/v1/auth/signup", json=signup_payload)

        res = self.client.post("/api/v1/auth/login", json={
            "email": "carol@example.com",
            "password": "WrongPassword999!",
        })
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["detail"], "Invalid email or password.")

    def test_login_nonexistent_email_generic_error(self):
        """Login with nonexistent email returns identical 401 generic error message."""
        res = self.client.post("/api/v1/auth/login", json={
            "email": "nonexistent@example.com",
            "password": "AnyPassword123!",
        })
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["detail"], "Invalid email or password.")

    # -----------------------------------------------------------------------
    # 6. Current User Profile API Tests (/api/v1/auth/me)
    # -----------------------------------------------------------------------

    def test_get_me_authenticated(self):
        """GET /api/v1/auth/me with valid Bearer token returns current user profile."""
        signup_payload = {
            "username": "dave",
            "email": "dave@example.com",
            "password": "DavesPassword123!",
        }
        self.client.post("/api/v1/auth/signup", json=signup_payload)

        login_res = self.client.post("/api/v1/auth/login", json={
            "email": "dave@example.com",
            "password": "DavesPassword123!",
        })
        token = login_res.json()["access_token"]

        me_res = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(me_res.status_code, 200)
        me_data = me_res.json()
        self.assertEqual(me_data["username"], "dave")
        self.assertEqual(me_data["email"], "dave@example.com")

    def test_get_me_missing_token_returns_401(self):
        """GET /api/v1/auth/me without Authorization header returns 401 Unauthorized."""
        res = self.client.get("/api/v1/auth/me")
        self.assertEqual(res.status_code, 401)
        self.assertIn("credentials were not provided", res.json()["detail"].lower())

    def test_get_me_invalid_token_returns_401(self):
        """GET /api/v1/auth/me with invalid token returns 401 Unauthorized."""
        res = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer not.a.valid.jwt.token"},
        )
        self.assertEqual(res.status_code, 401)

    # -----------------------------------------------------------------------
    # 7. Authentication Timing Benchmark
    # -----------------------------------------------------------------------

    def test_timing_benchmark(self):
        """Benchmark authentication timing for:
          - valid password
          - incorrect password
          - nonexistent email

        Verifies PBKDF2-HMAC-SHA256 at 600,000 iterations without reducing work factor.
        """
        # Register a test user for benchmarking
        user_reg = UserRegister(
            username="bench_user",
            email="bench@example.com",
            password="BenchmarkPassword123!",
        )
        user = register_user(self.db, user_reg)

        # 1. Valid password
        t0 = time.perf_counter()
        valid_res = authenticate_user(self.db, "bench@example.com", "BenchmarkPassword123!")
        time_valid = time.perf_counter() - t0
        self.assertIsNotNone(valid_res)

        # 2. Incorrect password
        t0 = time.perf_counter()
        invalid_res = authenticate_user(self.db, "bench@example.com", "WrongPassword123!")
        time_invalid = time.perf_counter() - t0
        self.assertIsNone(invalid_res)

        # 3. Nonexistent email
        t0 = time.perf_counter()
        nonexistent_res = authenticate_user(self.db, "nobody@example.com", "AnyPassword123!")
        time_nonexistent = time.perf_counter() - t0
        self.assertIsNone(nonexistent_res)

        print("\n" + "=" * 60)
        print("AUTHENTICATION TIMING BENCHMARK (PBKDF2 600,000 rounds)")
        print("=" * 60)
        print(f"  Valid Password:       {time_valid:.4f}s")
        print(f"  Incorrect Password:   {time_invalid:.4f}s")
        print(f"  Nonexistent Email:    {time_nonexistent:.4f}s")
        print("=" * 60)

        # Valid, invalid password, and nonexistent email should all involve PBKDF2 computation (> 0.05s)
        self.assertGreater(time_valid, 0.05)
        self.assertGreater(time_invalid, 0.05)
        self.assertGreater(time_nonexistent, 0.05)



if __name__ == "__main__":
    unittest.main()
