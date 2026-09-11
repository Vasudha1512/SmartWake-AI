"""Comprehensive Automated Security and Data Hardening Test Suite (Phase 4.8-B).

Validates:
1. Personalization Context Security Sanitization:
   - Security/credential fields stripped: api_key, apikey, secret, api_secret, client_secret,
     private_key, credential, credentials, password, passphrase, jwt, bearer, access_token,
     auth_token, refresh_token, session_token, user_id, session_id, alarm_id.
   - Legitimate non-sensitive context fields containing 'key' remain usable without false positives
     (e.g., keyboard_preference, hockey_fan, monkey_mode, keynote_speaker).
   - SafePersonalizationContext preserves allowed fields and forbids extra arbitrary fields.
2. Gemini API Key Transport & Error Sanitization:
   - Uses x-goog-api-key header consistently; URL does not contain query string secrets.
   - Test secrets ('TEST_FAKE_API_KEY_123') are strictly redacted to [REDACTED] in error messages.
   - Secrets never leak into GenAIError exceptions.
3. Template & Attempt Input Validation Hardening:
   - Forbidden challenge type ('number_guessing') rejected with HTTP 400.
   - Invalid/unknown challenge type rejected with HTTP 400.
   - Invalid difficulty tier ('insane') rejected with HTTP 400.
   - Template challenge type mismatch against requested type rejected with HTTP 400.
   - Template challenge type mismatch against alarm type rejected with HTTP 400.
   - Template difficulty mismatch against requested difficulty rejected with HTTP 400.
4. Snooze Duration Boundaries:
   - Non-positive duration (<= 0) rejected with HTTP 400.
   - Excessive duration (> 1440 minutes / 24 hours) rejected with HTTP 400.
   - Valid duration (e.g. 5, 15, 60 minutes) succeeds.
5. Resource Ownership & Access Control:
   - Cross-user challenge attempt start denied with HTTP 403.
   - Cross-user challenge attempt submission denied with HTTP 403.
   - Cross-user challenge attempt retrieval denied with HTTP 403.
   - Cross-user session attempts history listing denied with HTTP 403.
   - Cross-user wake session creation on another user's alarm denied with HTTP 400.
   - Cross-user snooze attempt on another user's wake session denied with HTTP 400.
6. Error Handling & Leakage Prevention:
   - Standard domain / HTTP errors (400, 403, 404, 409, 422) preserve their status codes and details.
   - Truly unhandled server exceptions return HTTP 500 with '{"detail": "Internal server error."}'.
   - Zero filesystem paths, database internals, or stack traces leaked in responses.
7. Data Minimization & Persistence Integrity:
   - ChallengeAttempt prompt_content contains only sanitized challenge specs with zero secrets.
"""
import asyncio
from datetime import datetime
from email.message import Message
import json
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.constants import FORBIDDEN_CHALLENGE_TYPES, VALID_CHALLENGE_TYPES
from backend.app.core.exceptions import (
    AlarmOwnershipError,
    ChallengeAttemptOwnershipError,
    GenAIConfigurationError,
    GenAIError,
    InvalidChallengeTypeError,
    InvalidDifficultyError,
    InvalidSnoozeDurationError,
)
from backend.app.database.base import Base
from backend.app.database.session import get_db
from backend.app.main import app
from backend.app.models.alarm import Alarm
from backend.app.models.challenge import Challenge
from backend.app.models.challenge_attempt import ChallengeAttempt
from backend.app.models.user import User
from backend.app.models.wake_session import WakeSession
from backend.app.schemas.challenge_content_schemas import (
    FORBIDDEN_CONTEXT_KEYS,
    SafePersonalizationContext,
)
from backend.app.schemas.challenge_schemas import (
    ChallengeAttemptStartRequest,
    ChallengeAttemptSubmitRequest,
)
from backend.app.schemas.genai_schemas import GenAIContentRequest
from backend.app.services.challenge_execution_service import (
    get_challenge_attempt,
    list_attempts_for_wake_session,
    start_challenge_attempt,
    submit_challenge_attempt,
)
from backend.app.services.genai.gemini_provider import GeminiProvider
from backend.app.services.runtime_personalization_bridge import (
    RuntimePersonalizationBridge,
)
from backend.app.services.wake_session_service import (
    create_wake_session,
    record_snooze,
)


class SimpleASGIClient:
    """Lightweight ASGI test client using asyncio and standard library."""

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

        response_status = 500
        response_headers = []
        response_body = []

        async def receive():
            return {"type": "http.request", "body": body_bytes, "more_body": False}

        async def send(message):
            nonlocal response_status, response_headers, response_body
            if message["type"] == "http.response.start":
                response_status = message["status"]
                response_headers = message.get("headers", [])
            elif message["type"] == "http.response.body":
                response_body.append(message.get("body", b""))

        try:
            await self.app(scope, receive, send)
        except Exception:
            # Starlette's ServerErrorMiddleware re-raises exceptions after executing the 500 handler;
            # allow the generated 500 response to be returned to the caller for inspection.
            if not response_body and response_status != 500:
                raise

        class Response:
            def __init__(self, status_code, body):
                self.status_code = status_code
                self.body = b"".join(body)

            def json(self):
                if not self.body:
                    return None
                return json.loads(self.body.decode("utf-8"))

            @property
            def text(self):
                return self.body.decode("utf-8")

        return Response(response_status, response_body)

    def get(self, path: str, headers=None):
        return self._request("GET", path, headers=headers)

    def post(self, path: str, json_data=None, headers=None):
        return self._request("POST", path, json_data=json_data, headers=headers)

    def put(self, path: str, json_data=None, headers=None):
        return self._request("PUT", path, json_data=json_data, headers=headers)

    def delete(self, path: str, headers=None):
        return self._request("DELETE", path, headers=headers)


class TestSecurityAndDataHardening(unittest.TestCase):
    """Regression test suite for Phase 4.8-B security and data hardening."""

    @classmethod
    def setUpClass(cls):
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
            db = cls.TestingSessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = SimpleASGIClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=cls.engine)

    def setUp(self):
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)

        with self.TestingSessionLocal() as db:
            user_a = User(username="alice", email="alice@example.com", timezone="UTC")
            user_b = User(username="bob", email="bob@example.com", timezone="UTC")
            db.add_all([user_a, user_b])
            db.commit()
            db.refresh(user_a)
            db.refresh(user_b)
            self.user_a_id = user_a.id
            self.user_b_id = user_b.id

            alarm_a = Alarm(
                user_id=self.user_a_id,
                time="07:00",
                selected_challenge_type="math",
                difficulty_preference="medium",
                label="Alice Alarm",
                days_of_week="[0,1,2,3,4]",
                is_active=True,
            )
            alarm_b = Alarm(
                user_id=self.user_b_id,
                time="08:00",
                selected_challenge_type="dance",
                difficulty_preference="easy",
                label="Bob Alarm",
                days_of_week="[0,1,2,3,4]",
                is_active=True,
            )
            db.add_all([alarm_a, alarm_b])
            db.commit()
            db.refresh(alarm_a)
            db.refresh(alarm_b)
            self.alarm_a_id = alarm_a.id
            self.alarm_b_id = alarm_b.id

            # Seed a default math challenge template
            math_tmpl = Challenge(
                challenge_type="math",
                difficulty_level="medium",
                title="Standard Math",
                description="Solve arithmetic equation",
                template_payload=json.dumps({
                    "question_count": 1,
                    "operation_types": ["addition"],
                    "operand_min": 1,
                    "operand_max": 20,
                }),
                min_duration_seconds=5,
                is_active=True,
            )
            # Seed a dance challenge template
            dance_tmpl = Challenge(
                challenge_type="dance",
                difficulty_level="easy",
                title="Morning Groove",
                description="Move to the rhythm",
                template_payload=json.dumps({
                    "step_count": 4,
                    "duration_seconds": 20,
                    "tempo_bpm": 100,
                }),
                min_duration_seconds=10,
                is_active=True,
            )
            db.add_all([math_tmpl, dance_tmpl])
            db.commit()
            db.refresh(math_tmpl)
            db.refresh(dance_tmpl)
            self.math_tmpl_id = math_tmpl.id
            self.dance_tmpl_id = dance_tmpl.id

    def _create_session_for_user_a(self, db):
        sess = create_wake_session(db, user_id=self.user_a_id, alarm_id=self.alarm_a_id)
        return sess

    # =========================================================================
    # AREA 1: Personalization Context Sanitization (No False Positives)
    # =========================================================================

    def test_01_credential_and_security_fields_stripped_from_context(self):
        """Security-sensitive keys are strictly stripped from explicit personalization context."""
        sensitive_context = {
            "api_key": "secret_key_123",
            "apikey": "secret_key_456",
            "secret": "top_secret_val",
            "api_secret": "xyz_secret",
            "client_secret": "oauth_client_sec",
            "private_key": "-----BEGIN RSA PRIVATE KEY-----",
            "credential": "admin_credential",
            "credentials": {"token": "jwt_val"},
            "password": "super_secret_password",
            "passphrase": "passphrase_phrase",
            "jwt": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
            "bearer": "bearer_token_abc",
            "access_token": "access_tok_999",
            "auth_token": "auth_tok_888",
            "refresh_token": "refresh_tok_777",
            "session_token": "session_tok_666",
            "user_id": 999,
            "session_id": 888,
            "alarm_id": 777,
            # Legitimate non-sensitive styling parameters:
            "desired_duration_seconds": 30,
            "preferred_theme": "sunrise energizer",
            "language": "en",
            "disallowed_topics": ["politics", "finance"],
        }

        with self.TestingSessionLocal() as db:
            sess = self._create_session_for_user_a(db)
            safe_ctx = RuntimePersonalizationBridge.build_safe_context(
                wake_session=sess,
                current_attempt_number=1,
                explicit_context=sensitive_context,
            )

            # Legitimate fields must be preserved:
            self.assertEqual(safe_ctx.desired_duration_seconds, 30)
            self.assertEqual(safe_ctx.preferred_theme, "sunrise energizer")
            self.assertEqual(safe_ctx.language, "en")
            self.assertEqual(safe_ctx.disallowed_topics, ["politics", "finance"])

            # Dump model to dict and verify zero sensitive keys present:
            dumped = safe_ctx.model_dump()
            for forbidden_key in FORBIDDEN_CONTEXT_KEYS:
                self.assertNotIn(forbidden_key, dumped)

    def test_02_legitimate_words_containing_key_are_not_falsely_stripped(self):
        """Non-sensitive context fields containing letters 'key' are NOT falsely stripped."""
        # e.g., words like keyboard, hockey, monkey, keynote should not trigger blanket key stripping
        non_sensitive_context = {
            "desired_duration_seconds": 45,
            "preferred_theme": "keyboard jazz & keynote morning",
            "language": "en",
            "disallowed_topics": ["hockey injuries", "monkey business"],
        }

        with self.TestingSessionLocal() as db:
            sess = self._create_session_for_user_a(db)
            safe_ctx = RuntimePersonalizationBridge.build_safe_context(
                wake_session=sess,
                current_attempt_number=1,
                explicit_context=non_sensitive_context,
            )

            self.assertEqual(safe_ctx.desired_duration_seconds, 45)
            self.assertEqual(safe_ctx.preferred_theme, "keyboard jazz & keynote morning")
            self.assertIn("hockey injuries", safe_ctx.disallowed_topics)
            self.assertIn("monkey business", safe_ctx.disallowed_topics)

    def test_03_safe_personalization_context_forbids_extra_fields(self):
        """SafePersonalizationContext model strictly rejects extra unexpected fields."""
        with self.assertRaises(ValueError):
            SafePersonalizationContext(
                **{"desired_duration_seconds": 30, "extra_untrusted_field": "should_be_rejected"}
            )

    # =========================================================================
    # AREA 2: Gemini API Key Transport and Error Sanitization
    # =========================================================================

    def test_04_gemini_provider_uses_x_goog_api_key_header_consistently(self):
        """GeminiProvider sends key via x-goog-api-key header; URL does NOT expose key."""
        fake_secret = "TEST_FAKE_API_KEY_123"
        provider = GeminiProvider(api_key=fake_secret)

        url = provider._build_endpoint_url()
        self.assertNotIn(fake_secret, url)
        self.assertNotIn("?key=", url)

        # Mock urllib.request.urlopen to inspect Request headers
        req_obj = GenAIContentRequest(challenge_type="math", difficulty_level="medium")
        captured_request = None

        def mock_urlopen(request, timeout=None):
            nonlocal captured_request
            captured_request = request
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps({
                "candidates": [{
                    "content": {"parts": [{"text": json.dumps({"expression": "5 + 5", "proposed_answer": 10})}]},
                    "finishReason": "STOP",
                }],
                "usageMetadata": {"totalTokenCount": 20},
            }).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            resp = provider.generate(req_obj)
            self.assertIsNotNone(resp)
            self.assertIsNotNone(captured_request)
            assert captured_request is not None
            # Verify header is present and url query param is absent
            self.assertEqual(captured_request.get_header("X-goog-api-key"), fake_secret)
            self.assertNotIn(fake_secret, captured_request.full_url)
            self.assertNotIn("?key=", captured_request.full_url)

    def test_05_gemini_provider_sanitizes_fake_secrets_in_errors(self):
        """GeminiProvider redacts fake secrets in HTTP and URL error messages."""
        fake_secret = "TEST_FAKE_API_KEY_123"
        provider = GeminiProvider(api_key=fake_secret)
        req_obj = GenAIContentRequest(challenge_type="math", difficulty_level="medium")

        # Simulate HTTP 401 error containing the secret in the response body or URL
        http_err = urllib.error.HTTPError(
            url=f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={fake_secret}",
            code=401,
            msg="Unauthorized",
            hdrs=Message(),
            fp=MagicMock(read=lambda: f"Invalid API key {fake_secret}".encode("utf-8")),
        )

        with patch("urllib.request.urlopen", side_effect=http_err):
            with self.assertRaises(GenAIConfigurationError) as ctx:
                provider.generate(req_obj)

            err_msg = str(ctx.exception)
            # Secret MUST NOT appear in the exception message:
            self.assertNotIn(fake_secret, err_msg)
            # Redaction marker MUST appear:
            self.assertIn("[REDACTED]", err_msg)

    # =========================================================================
    # AREA 3: Template & Attempt Input Validation Hardening
    # =========================================================================

    def test_06_forbidden_challenge_type_rejected_at_attempt_start(self):
        """Memory challenges as number guessing are rejected with HTTP 400."""
        with self.TestingSessionLocal() as db:
            sess = self._create_session_for_user_a(db)

            req = ChallengeAttemptStartRequest(
                user_id=self.user_a_id,
                wake_session_id=sess.id,
                challenge_type="number_guessing",
            )
            with self.assertRaises(InvalidChallengeTypeError):
                start_challenge_attempt(db, req)

        # Via HTTP API:
        resp = self.client.post(
            "/api/v1/challenges/attempts/start",
            json_data={
                "user_id": self.user_a_id,
                "wake_session_id": sess.id,
                "challenge_type": "number_guessing",
            },
        )
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        assert body is not None
        self.assertIn("forbidden", body["detail"].lower())

    def test_07_invalid_challenge_type_rejected_at_attempt_start(self):
        """Unknown challenge types are rejected with HTTP 400."""
        with self.TestingSessionLocal() as db:
            sess = self._create_session_for_user_a(db)

            req = ChallengeAttemptStartRequest(
                user_id=self.user_a_id,
                wake_session_id=sess.id,
                challenge_type="astrology_quiz",
            )
            with self.assertRaises(InvalidChallengeTypeError):
                start_challenge_attempt(db, req)

        # Via HTTP API:
        resp = self.client.post(
            "/api/v1/challenges/attempts/start",
            json_data={
                "user_id": self.user_a_id,
                "wake_session_id": sess.id,
                "challenge_type": "astrology_quiz",
            },
        )
        self.assertEqual(resp.status_code, 400)

    def test_08_invalid_difficulty_level_rejected_at_attempt_start(self):
        """Unsupported difficulty preferences are rejected with HTTP 400."""
        with self.TestingSessionLocal() as db:
            sess = self._create_session_for_user_a(db)

            req = ChallengeAttemptStartRequest(
                user_id=self.user_a_id,
                wake_session_id=sess.id,
                challenge_type="math",
                difficulty_level="insane_tier",
            )
            with self.assertRaises(InvalidDifficultyError):
                start_challenge_attempt(db, req)

        # Via HTTP API:
        resp = self.client.post(
            "/api/v1/challenges/attempts/start",
            json_data={
                "user_id": self.user_a_id,
                "wake_session_id": sess.id,
                "challenge_type": "math",
                "difficulty_level": "insane_tier",
            },
        )
        self.assertEqual(resp.status_code, 400)

    def test_09_template_type_mismatch_against_requested_type_rejected(self):
        """Supplying a template ID of differing type from requested type is rejected (400)."""
        with self.TestingSessionLocal() as db:
            sess = self._create_session_for_user_a(db)

            # math_tmpl_id is 'math', but request asks for 'dance'
            req = ChallengeAttemptStartRequest(
                user_id=self.user_a_id,
                wake_session_id=sess.id,
                challenge_id=self.math_tmpl_id,
                challenge_type="dance",
            )
            with self.assertRaises(InvalidChallengeTypeError):
                start_challenge_attempt(db, req)

        # Via HTTP API:
        resp = self.client.post(
            "/api/v1/challenges/attempts/start",
            json_data={
                "user_id": self.user_a_id,
                "wake_session_id": sess.id,
                "challenge_id": self.math_tmpl_id,
                "challenge_type": "dance",
            },
        )
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        assert body is not None
        self.assertIn("does not match requested challenge type", body["detail"])

    def test_10_template_type_mismatch_against_alarm_type_rejected(self):
        """Supplying a template ID differing from the alarm's challenge type is rejected (400)."""
        with self.TestingSessionLocal() as db:
            # Alarm A is configured for 'math'. Supplying dance_tmpl_id without override must fail.
            sess = self._create_session_for_user_a(db)

            req = ChallengeAttemptStartRequest(
                user_id=self.user_a_id,
                wake_session_id=sess.id,
                challenge_id=self.dance_tmpl_id,
            )
            with self.assertRaises(InvalidChallengeTypeError):
                start_challenge_attempt(db, req)

        # Via HTTP API:
        resp = self.client.post(
            "/api/v1/challenges/attempts/start",
            json_data={
                "user_id": self.user_a_id,
                "wake_session_id": sess.id,
                "challenge_id": self.dance_tmpl_id,
            },
        )
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        assert body is not None
        self.assertIn("does not match alarm's selected challenge type", body["detail"])

    def test_11_template_difficulty_mismatch_against_requested_difficulty_rejected(self):
        """Supplying a template ID differing from explicit requested difficulty is rejected (400)."""
        with self.TestingSessionLocal() as db:
            sess = self._create_session_for_user_a(db)

            # math_tmpl_id is 'medium', but request explicitly asks for 'hard'
            req = ChallengeAttemptStartRequest(
                user_id=self.user_a_id,
                wake_session_id=sess.id,
                challenge_id=self.math_tmpl_id,
                difficulty_level="hard",
            )
            with self.assertRaises(InvalidDifficultyError):
                start_challenge_attempt(db, req)

        # Via HTTP API:
        resp = self.client.post(
            "/api/v1/challenges/attempts/start",
            json_data={
                "user_id": self.user_a_id,
                "wake_session_id": sess.id,
                "challenge_id": self.math_tmpl_id,
                "difficulty_level": "hard",
            },
        )
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        assert body is not None
        self.assertIn("does not match requested difficulty level", body["detail"])

    # =========================================================================
    # AREA 4: Snooze Duration Boundaries
    # =========================================================================

    def test_12_snooze_duration_boundaries(self):
        """Snooze duration must be positive and not exceed 1440 minutes (24 hours)."""
        with self.TestingSessionLocal() as db:
            sess = self._create_session_for_user_a(db)

            # 1. Non-positive duration rejected
            with self.assertRaises(InvalidSnoozeDurationError):
                record_snooze(db, session_id=sess.id, duration_minutes=0)

            with self.assertRaises(InvalidSnoozeDurationError):
                record_snooze(db, session_id=sess.id, duration_minutes=-5)

            # 2. Excessive duration (> 1440) rejected
            with self.assertRaises(InvalidSnoozeDurationError):
                record_snooze(db, session_id=sess.id, duration_minutes=1441)

            # 3. Valid duration (e.g. 10 minutes) succeeds
            res = record_snooze(db, session_id=sess.id, duration_minutes=10)
            self.assertEqual(res.wake_session.status, "snoozed")
            self.assertEqual(res.snooze_event.snooze_duration_minutes, 10)

        # Via HTTP API:
        resp_zero = self.client.post(f"/api/v1/wake-sessions/{sess.id}/snooze", json_data={"duration_minutes": 0})
        self.assertEqual(resp_zero.status_code, 400)

        resp_excess = self.client.post(f"/api/v1/wake-sessions/{sess.id}/snooze", json_data={"duration_minutes": 5000})
        self.assertEqual(resp_excess.status_code, 400)

    # =========================================================================
    # AREA 5: Ownership and Access Control
    # =========================================================================

    def test_13_cross_user_challenge_attempt_start_forbidden(self):
        """User B cannot start an attempt for User A's session (HTTP 403)."""
        with self.TestingSessionLocal() as db:
            sess = self._create_session_for_user_a(db)

            req = ChallengeAttemptStartRequest(
                user_id=self.user_b_id,
                wake_session_id=sess.id,
                challenge_type="math",
            )
            with self.assertRaises(ChallengeAttemptOwnershipError):
                start_challenge_attempt(db, req)

        # Via HTTP API:
        resp = self.client.post(
            "/api/v1/challenges/attempts/start",
            json_data={
                "user_id": self.user_b_id,
                "wake_session_id": sess.id,
                "challenge_type": "math",
            },
        )
        self.assertEqual(resp.status_code, 403)

    def test_14_cross_user_challenge_attempt_submit_forbidden(self):
        """User B cannot submit an attempt created for User A (HTTP 403)."""
        with self.TestingSessionLocal() as db:
            sess = self._create_session_for_user_a(db)
            att = start_challenge_attempt(
                db,
                ChallengeAttemptStartRequest(
                    user_id=self.user_a_id,
                    wake_session_id=sess.id,
                    challenge_type="math",
                ),
            )
            att_id = att.id

            with self.assertRaises(ChallengeAttemptOwnershipError):
                submit_challenge_attempt(
                    db=db,
                    attempt_id=att_id,
                    user_id=self.user_b_id,
                    submission_data={"answers": [10]},
                )

        # Via HTTP API:
        resp = self.client.post(
            f"/api/v1/challenges/attempts/{att_id}/submit",
            json_data={"user_id": self.user_b_id, "submission_data": {"answers": [10]}},
        )
        self.assertEqual(resp.status_code, 403)

    def test_15_cross_user_challenge_attempt_retrieval_forbidden(self):
        """User B cannot retrieve User A's challenge attempt record (HTTP 403)."""
        with self.TestingSessionLocal() as db:
            sess = self._create_session_for_user_a(db)
            att = start_challenge_attempt(
                db,
                ChallengeAttemptStartRequest(
                    user_id=self.user_a_id,
                    wake_session_id=sess.id,
                    challenge_type="math",
                ),
            )
            att_id = att.id

            with self.assertRaises(ChallengeAttemptOwnershipError):
                get_challenge_attempt(db, attempt_id=att_id, user_id=self.user_b_id)

        # Via HTTP API:
        resp = self.client.get(f"/api/v1/challenges/attempts/{att_id}?user_id={self.user_b_id}")
        self.assertEqual(resp.status_code, 403)

    def test_16_cross_user_wake_session_history_listing_forbidden(self):
        """User B cannot view challenge attempts for User A's session (HTTP 403)."""
        with self.TestingSessionLocal() as db:
            sess = self._create_session_for_user_a(db)

            with self.assertRaises(ChallengeAttemptOwnershipError):
                list_attempts_for_wake_session(db, session_id=sess.id, user_id=self.user_b_id)

        # Via HTTP API:
        resp = self.client.get(f"/api/v1/wake-sessions/{sess.id}/challenge-attempts?user_id={self.user_b_id}")
        self.assertEqual(resp.status_code, 403)

    def test_17_cross_user_wake_session_creation_forbidden(self):
        """User B cannot start a wake session on User A's alarm (HTTP 400)."""
        with self.TestingSessionLocal() as db:
            with self.assertRaises(AlarmOwnershipError):
                create_wake_session(db, user_id=self.user_b_id, alarm_id=self.alarm_a_id)

        # Via HTTP API:
        resp = self.client.post(
            "/api/v1/wake-sessions",
            json_data={"user_id": self.user_b_id, "alarm_id": self.alarm_a_id},
        )
        self.assertEqual(resp.status_code, 400)

    def test_18_cross_user_snooze_attempt_rejected(self):
        """User B supplying their user_id to snooze User A's session is rejected (HTTP 400)."""
        with self.TestingSessionLocal() as db:
            sess = self._create_session_for_user_a(db)

            with self.assertRaises(AlarmOwnershipError):
                record_snooze(db, session_id=sess.id, user_id=self.user_b_id)

        # Via HTTP API:
        resp = self.client.post(
            f"/api/v1/wake-sessions/{sess.id}/snooze",
            json_data={"user_id": self.user_b_id},
        )
        self.assertEqual(resp.status_code, 400)

    # =========================================================================
    # AREA 6: Safe Global Error Handling
    # =========================================================================

    def test_19_expected_errors_preserve_contract_status_codes(self):
        """FastAPI HTTPExceptions and validation errors are not masked by the 500 handler."""
        # 404: Nonexistent user
        resp_404 = self.client.get("/api/v1/users/99999")
        self.assertEqual(resp_404.status_code, 404)

        # 422: Malformed alarm payload (invalid time format)
        resp_422 = self.client.post(
            "/api/v1/alarms",
            json_data={"user_id": self.user_a_id, "time": "25:99"},
        )
        self.assertEqual(resp_422.status_code, 422)

    def test_20_unexpected_internal_exceptions_return_safe_500_without_leakage(self):
        """Genuinely unhandled internal exceptions return safe generic 500 without stack traces."""
        # Patch a service method to simulate an unexpected internal runtime error
        with patch(
            "backend.app.services.challenge_service.list_active_challenges",
            side_effect=RuntimeError("Secret internal database connection failed: /var/data/smartwake.db password=root"),
        ):
            resp = self.client.get("/api/v1/challenges")
            self.assertEqual(resp.status_code, 500)
            data = resp.json()
            assert data is not None
            self.assertEqual(data["detail"], "Internal server error.")
            # Zero leakage of path, password, or exception message
            self.assertNotIn("/var/data", resp.text)
            self.assertNotIn("password=", resp.text)
            self.assertNotIn("RuntimeError", resp.text)
            self.assertNotIn("Traceback", resp.text)

    # =========================================================================
    # AREA 7: Data Minimization & Secret Persistence Prevention
    # =========================================================================

    def test_21_challenge_attempt_prompt_content_contains_zero_secrets(self):
        """Persisted ChallengeAttempt prompt_content contains only sanitized task specs."""
        with self.TestingSessionLocal() as db:
            sess = self._create_session_for_user_a(db)
            att = start_challenge_attempt(
                db,
                ChallengeAttemptStartRequest(
                    user_id=self.user_a_id,
                    wake_session_id=sess.id,
                    challenge_type="math",
                    difficulty_level="medium",
                ),
            )
            payload_str = att.prompt_content
            self.assertIsInstance(payload_str, str)
            payload = json.loads(payload_str)

            # Assert standard required task specifications exist
            self.assertEqual(payload["challenge_type"], "math")
            self.assertEqual(payload["difficulty_level"], "medium")
            self.assertIn("content_payload", payload)

            # Assert no sensitive / credential fields are stored
            for forbidden_key in FORBIDDEN_CONTEXT_KEYS:
                self.assertNotIn(forbidden_key, payload)


if __name__ == "__main__":
    unittest.main()
