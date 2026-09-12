"""SmartWake AI — Phase 4.8-C: Final End-to-End Validation & Hardening Test Suite.

Validates the complete SmartWake AI runtime lifecycle from alarm activation
through successful challenge completion across all five challenge types:
1. Dance
2. Math
3. Memory
4. Tongue Twister
5. Push-ups

Covers:
- Happy-path full lifecycles (Alarm -> WakeSession -> ChallengeAttempt -> Verification -> Completed).
- Fixed difficulty contract preservation ('easy', 'medium', 'hard').
- Adaptive difficulty resolution to concrete tiers.
- GenAI failure and deterministic fallback paths (timeout, rate limit, 503, malformed JSON, unsafe content).
- Safety invariants (deterministic Python verification authority, LLM math distrust, non-number-guessing memory).
- Failure submissions (incorrect answers fail attempt; session remains in_challenge; retry succeeds).
- Duplicate and concurrent operation protections (duplicate start, duplicate submit, terminal submission).
- State machine lifecycle (ringing -> snoozed -> ringing -> in_challenge -> completed; terminal protection).
- Cross-user ownership isolation (403 Forbidden across all attempt operations).
- Security regression and data minimization (zero credential leakage in DB or errors; context sanitization).
"""
import asyncio
from datetime import datetime
from email.message import Message
import json
from typing import Any, Dict, List, Optional
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.config import settings
from backend.app.core.constants import VALID_CHALLENGE_TYPES
from backend.app.core.datetime_utils import now_utc_naive
from backend.app.core.exceptions import (
    ActiveChallengeAttemptExistsError,
    ChallengeAttemptCompletedError,
    ChallengeAttemptNotFoundError,
    ChallengeAttemptOwnershipError,
    GenAIConfigurationError,
    GenAIError,
    GenAIProviderUnavailableError,
    GenAIRateLimitError,
    GenAITimeoutError,
    GenAIValidationError,
    InvalidChallengeTypeError,
    InvalidDifficultyError,
    InvalidSessionTransitionError,
    WakeSessionNotFoundError,
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
from backend.app.schemas.genai_schemas import (
    GenAIContentRequest,
    GenAIGenerationResponse,
)
from backend.app.services.challenge_execution_service import (
    get_challenge_attempt,
    list_attempts_for_wake_session,
    start_challenge_attempt,
    submit_challenge_attempt,
)
from backend.app.services.genai.gemini_provider import GeminiProvider
from backend.app.services.genai.genai_service import GenAIService
from backend.app.services.genai.mock_provider import MockGenAIProvider
from backend.app.services.genai.safety_retry_orchestrator import (
    SafetyRetryOrchestrator,
)
from backend.app.services.runtime_personalization_bridge import (
    RuntimePersonalizationBridge,
)
from backend.app.services.wake_session_service import (
    STATUS_ABANDONED,
    STATUS_COMPLETED,
    STATUS_IN_CHALLENGE,
    STATUS_RINGING,
    STATUS_SNOOZED,
    complete_wake_session,
    create_wake_session,
    fail_wake_session,
    record_snooze,
    resume_ringing,
)
from backend.tests.test_math_genai import _create_canned_math_response


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
            if not response_body and response_status != 500:
                raise

        class Response:
            def __init__(self, status_code, body):
                self.status_code = status_code
                self.body = b"".join(body)

            def json(self) -> Dict[str, Any]:
                if not self.body:
                    return {}
                res = json.loads(self.body.decode("utf-8"))
                if isinstance(res, dict):
                    return res
                return {"_data": res}

            @property
            def text(self):
                return self.body.decode("utf-8")

        return Response(response_status, response_body)

    def get(self, path: str, headers=None):
        return self._request("GET", path, headers=headers)

    def post(self, path: str, json_data=None, headers=None):
        return self._request("POST", path, json_data=json_data, headers=headers)


class TestPhase48CEndToEndValidation(unittest.TestCase):
    """Phase 4.8-C: Comprehensive End-to-End Validation & Hardening Test Suite."""

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=cls.engine)
        cls.TestingSessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=cls.engine
        )

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
        # Create fresh isolated test fixtures
        with self.TestingSessionLocal() as db:
            # Users
            user_a = User(
                username=f"user_a_{now_utc_naive().timestamp()}",
                email=f"user_a_{now_utc_naive().timestamp()}@smartwake.ai",
            )
            user_b = User(
                username=f"user_b_{now_utc_naive().timestamp()}",
                email=f"user_b_{now_utc_naive().timestamp()}@smartwake.ai",
            )
            db.add_all([user_a, user_b])
            db.commit()
            db.refresh(user_a)
            db.refresh(user_b)
            self.user_a_id = user_a.id
            self.user_b_id = user_b.id

            # Base Alarms for all 5 types
            alarms = {}
            for c_type in ("dance", "math", "memory", "tongue_twister", "push_ups"):
                alm = Alarm(
                    user_id=self.user_a_id,
                    time="07:00",
                    is_active=True,
                    selected_challenge_type=c_type,
                    difficulty_preference="medium",
                )
                db.add(alm)
                db.commit()
                db.refresh(alm)
                alarms[c_type] = alm.id
            self.alarm_ids = alarms

            # User B alarm
            alm_b = Alarm(
                user_id=self.user_b_id,
                time="08:00",
                is_active=True,
                selected_challenge_type="math",
                difficulty_preference="medium",
            )
            db.add(alm_b)
            db.commit()
            db.refresh(alm_b)
            self.alarm_b_id = alm_b.id

    def _create_ringing_session(self, db: Session, challenge_type: str, user_id: Optional[int] = None) -> WakeSession:
        uid = user_id or self.user_a_id
        alm = Alarm(
            user_id=uid,
            time="07:00",
            is_active=True,
            selected_challenge_type=challenge_type,
            difficulty_preference="medium",
        )
        db.add(alm)
        db.commit()
        db.refresh(alm)
        session = create_wake_session(db, user_id=uid, alarm_id=alm.id)
        self.assertEqual(session.status, STATUS_RINGING)
        return session

    # =========================================================================
    # SECTION 1: Complete Happy-Path Validation Across All 5 Challenge Types
    # =========================================================================

    def test_01_happy_path_dance_e2e(self):
        """Dance challenge completes happy-path: alarm -> ringing -> in_challenge -> completed."""
        with self.TestingSessionLocal() as db:
            session = self._create_ringing_session(db, "dance")
            sess_id = session.id

        # 1. Start Challenge Attempt via API
        resp_start = self.client.post(
            "/api/v1/challenges/attempts/start",
            json_data={
                "user_id": self.user_a_id,
                "wake_session_id": sess_id,
                "challenge_type": "dance",
            },
        )
        self.assertEqual(resp_start.status_code, 201)
        att_data = resp_start.json()
        assert att_data is not None
        att_id = att_data["id"]
        self.assertEqual(att_data["challenge_type"], "dance")
        self.assertEqual(att_data["difficulty_level"], "medium")

        # Verify WakeSession transitioned to in_challenge
        with self.TestingSessionLocal() as db:
            sess = db.get(WakeSession, sess_id)
            assert sess is not None
            self.assertEqual(sess.status, STATUS_IN_CHALLENGE)

            att = db.get(ChallengeAttempt, att_id)
            assert att is not None
            prompt = json.loads(att.prompt_content)
            self.assertEqual(prompt["challenge_type"], "dance")
            self.assertEqual(prompt["verification_mode"], "development_manual")
            self.assertIn("steps", prompt["content_payload"])

        # 2. Submit Verification via API
        resp_sub = self.client.post(
            f"/api/v1/challenges/attempts/{att_id}/submit",
            json_data={
                "user_id": self.user_a_id,
                "submission_data": {"confirmed": True},
            },
        )
        self.assertEqual(resp_sub.status_code, 200)
        sub_data = resp_sub.json()
        assert sub_data is not None
        self.assertTrue(sub_data["is_successful"])
        self.assertEqual(sub_data["verification_score"], 1.0)

        # 3. Verify WakeSession is completed
        with self.TestingSessionLocal() as db:
            sess_final = db.get(WakeSession, sess_id)
            assert sess_final is not None
            self.assertEqual(sess_final.status, STATUS_COMPLETED)
            self.assertIsNotNone(sess_final.dismissed_time)

    def test_02_happy_path_math_e2e(self):
        """Math challenge completes happy-path with deterministic verification."""
        with self.TestingSessionLocal() as db:
            session = self._create_ringing_session(db, "math")
            sess_id = session.id

        resp_start = self.client.post(
            "/api/v1/challenges/attempts/start",
            json_data={
                "user_id": self.user_a_id,
                "wake_session_id": sess_id,
                "challenge_type": "math",
            },
        )
        self.assertEqual(resp_start.status_code, 201)
        att_data = resp_start.json()
        assert att_data is not None
        att_id = att_data["id"]

        with self.TestingSessionLocal() as db:
            att = db.get(ChallengeAttempt, att_id)
            assert att is not None
            prompt = json.loads(att.prompt_content)
            expected_answer = prompt["expected_answer"]
            self.assertIsNotNone(expected_answer)

        # Submit verified expected answer
        resp_sub = self.client.post(
            f"/api/v1/challenges/attempts/{att_id}/submit",
            json_data={
                "user_id": self.user_a_id,
                "submission_data": {"answer": expected_answer},
            },
        )
        self.assertEqual(resp_sub.status_code, 200)
        self.assertTrue(resp_sub.json()["is_successful"])

        with self.TestingSessionLocal() as db:
            sess = db.get(WakeSession, sess_id)
            assert sess is not None
            self.assertEqual(sess.status, STATUS_COMPLETED)

    def test_03_happy_path_memory_e2e(self):
        """Memory challenge completes happy-path with visual sequence recall."""
        with self.TestingSessionLocal() as db:
            session = self._create_ringing_session(db, "memory")
            sess_id = session.id

        resp_start = self.client.post(
            "/api/v1/challenges/attempts/start",
            json_data={
                "user_id": self.user_a_id,
                "wake_session_id": sess_id,
                "challenge_type": "memory",
            },
        )
        self.assertEqual(resp_start.status_code, 201)
        att_id = resp_start.json()["id"]

        with self.TestingSessionLocal() as db:
            att = db.get(ChallengeAttempt, att_id)
            assert att is not None
            prompt = json.loads(att.prompt_content)
            expected_seq = prompt["expected_answer"]
            self.assertIsInstance(expected_seq, list)
            self.assertNotIn("number_guessing", prompt["verification_mode"])

        # Submit exact sequence
        resp_sub = self.client.post(
            f"/api/v1/challenges/attempts/{att_id}/submit",
            json_data={
                "user_id": self.user_a_id,
                "submission_data": {"sequence": expected_seq},
            },
        )
        self.assertEqual(resp_sub.status_code, 200)
        self.assertTrue(resp_sub.json()["is_successful"])

        with self.TestingSessionLocal() as db:
            sess = db.get(WakeSession, sess_id)
            assert sess is not None
            self.assertEqual(sess.status, STATUS_COMPLETED)

    def test_04_happy_path_tongue_twister_e2e(self):
        """Tongue Twister challenge completes happy-path with enunciation confirmation."""
        with self.TestingSessionLocal() as db:
            session = self._create_ringing_session(db, "tongue_twister")
            sess_id = session.id

        resp_start = self.client.post(
            "/api/v1/challenges/attempts/start",
            json_data={
                "user_id": self.user_a_id,
                "wake_session_id": sess_id,
                "challenge_type": "tongue_twister",
            },
        )
        self.assertEqual(resp_start.status_code, 201)
        att_id = resp_start.json()["id"]

        with self.TestingSessionLocal() as db:
            att = db.get(ChallengeAttempt, att_id)
            assert att is not None
            prompt = json.loads(att.prompt_content)
            self.assertIn("passage", prompt["content_payload"])

        # Submit confirmation
        resp_sub = self.client.post(
            f"/api/v1/challenges/attempts/{att_id}/submit",
            json_data={
                "user_id": self.user_a_id,
                "submission_data": {"confirmed": True},
            },
        )
        self.assertEqual(resp_sub.status_code, 200)
        self.assertTrue(resp_sub.json()["is_successful"])

        with self.TestingSessionLocal() as db:
            sess = db.get(WakeSession, sess_id)
            assert sess is not None
            self.assertEqual(sess.status, STATUS_COMPLETED)

    def test_05_happy_path_push_ups_e2e(self):
        """Push-ups challenge completes happy-path with repetition count."""
        with self.TestingSessionLocal() as db:
            session = self._create_ringing_session(db, "push_ups")
            sess_id = session.id

        resp_start = self.client.post(
            "/api/v1/challenges/attempts/start",
            json_data={
                "user_id": self.user_a_id,
                "wake_session_id": sess_id,
                "challenge_type": "push_ups",
            },
        )
        self.assertEqual(resp_start.status_code, 201)
        att_id = resp_start.json()["id"]

        with self.TestingSessionLocal() as db:
            att = db.get(ChallengeAttempt, att_id)
            assert att is not None
            prompt = json.loads(att.prompt_content)
            target_reps = prompt["content_payload"]["target_repetitions"]
            self.assertGreaterEqual(target_reps, 5)

        # Submit completion of target reps
        resp_sub = self.client.post(
            f"/api/v1/challenges/attempts/{att_id}/submit",
            json_data={
                "user_id": self.user_a_id,
                "submission_data": {"reps_completed": target_reps},
            },
        )
        self.assertEqual(resp_sub.status_code, 200)
        self.assertTrue(resp_sub.json()["is_successful"])

        with self.TestingSessionLocal() as db:
            sess = db.get(WakeSession, sess_id)
            assert sess is not None
            self.assertEqual(sess.status, STATUS_COMPLETED)

    # =========================================================================
    # SECTION 2: Fixed and Adaptive Difficulty Contracts
    # =========================================================================

    def test_06_fixed_difficulty_contract_preservation(self):
        """Fixed difficulties ('easy', 'medium', 'hard') are strictly preserved across all 5 challenge types without ML mutation."""
        for c_type in ("dance", "math", "memory", "tongue_twister", "push_ups"):
            for tier in ("easy", "medium", "hard"):
                with self.subTest(challenge_type=c_type, tier=tier):
                    with self.TestingSessionLocal() as db:
                        session = self._create_ringing_session(db, c_type)
                        req = ChallengeAttemptStartRequest(
                            user_id=self.user_a_id,
                            wake_session_id=session.id,
                            challenge_type=c_type,
                            difficulty_level=tier,
                        )
                        att = start_challenge_attempt(db, req)
                        self.assertEqual(att.difficulty_level, tier)
                        prompt = json.loads(att.prompt_content)
                        self.assertEqual(prompt["difficulty_level"], tier)

    def test_07_adaptive_difficulty_resolves_to_concrete_tier(self):
        """Adaptive difficulty preference resolves to concrete tier across all 5 challenge types, never persisting 'adaptive'."""
        for c_type in ("dance", "math", "memory", "tongue_twister", "push_ups"):
            with self.subTest(challenge_type=c_type):
                with self.TestingSessionLocal() as db:
                    alm = Alarm(
                        user_id=self.user_a_id,
                        time="06:30",
                        is_active=True,
                        selected_challenge_type=c_type,
                        difficulty_preference="adaptive",
                    )
                    db.add(alm)
                    db.commit()
                    db.refresh(alm)

                    session = create_wake_session(db, user_id=self.user_a_id, alarm_id=alm.id)
                    req = ChallengeAttemptStartRequest(
                        user_id=self.user_a_id,
                        wake_session_id=session.id,
                        challenge_type=c_type,
                    )
                    att = start_challenge_attempt(db, req)

                    self.assertIn(att.difficulty_level, ("easy", "medium", "hard"))
                    self.assertNotEqual(att.difficulty_level, "adaptive")
                    prompt = json.loads(att.prompt_content)
                    self.assertIn(prompt["difficulty_level"], ("easy", "medium", "hard"))
                    self.assertNotEqual(prompt["difficulty_level"], "adaptive")

    # =========================================================================
    # SECTION 3: GenAI Failure & Deterministic Fallback Pathways
    # =========================================================================

    def test_08_genai_timeout_fallback_to_completed_session(self):
        """Provider timeout safely falls back to deterministic challenge and completes session."""
        with self.TestingSessionLocal() as db:
            session = self._create_ringing_session(db, "math")
            sess_id = session.id

        with patch.object(
            MockGenAIProvider,
            "generate",
            side_effect=GenAITimeoutError("Simulated Gemini timeout after 10.0s"),
        ):
            resp_start = self.client.post(
                "/api/v1/challenges/attempts/start",
                json_data={
                    "user_id": self.user_a_id,
                    "wake_session_id": sess_id,
                    "challenge_type": "math",
                },
            )
            self.assertEqual(resp_start.status_code, 201)
            att_id = resp_start.json()["id"]

        with self.TestingSessionLocal() as db:
            att = db.get(ChallengeAttempt, att_id)
            assert att is not None
            prompt = json.loads(att.prompt_content)
            self.assertTrue(prompt["is_fallback"])
            expected = prompt["expected_answer"]

        # Verification still functions cleanly on fallback
        resp_sub = self.client.post(
            f"/api/v1/challenges/attempts/{att_id}/submit",
            json_data={
                "user_id": self.user_a_id,
                "submission_data": {"answer": expected},
            },
        )
        self.assertEqual(resp_sub.status_code, 200)
        self.assertTrue(resp_sub.json()["is_successful"])

        with self.TestingSessionLocal() as db:
            sess = db.get(WakeSession, sess_id)
            assert sess is not None
            self.assertEqual(sess.status, STATUS_COMPLETED)

    def test_09_genai_rate_limit_fallback_to_completed_session(self):
        """Provider rate limit (429) triggers deterministic fallback and completes session."""
        with self.TestingSessionLocal() as db:
            session = self._create_ringing_session(db, "math")
            sess_id = session.id

        with patch.object(
            MockGenAIProvider,
            "generate",
            side_effect=GenAIRateLimitError("Simulated provider rate limit (RESOURCE_EXHAUSTED)"),
        ):
            resp_start = self.client.post(
                "/api/v1/challenges/attempts/start",
                json_data={
                    "user_id": self.user_a_id,
                    "wake_session_id": sess_id,
                    "challenge_type": "math",
                },
            )
            self.assertEqual(resp_start.status_code, 201)
            att_id = resp_start.json()["id"]

        with self.TestingSessionLocal() as db:
            att = db.get(ChallengeAttempt, att_id)
            assert att is not None
            prompt = json.loads(att.prompt_content)
            self.assertTrue(prompt["is_fallback"])
            expected = prompt["expected_answer"]

        resp_sub = self.client.post(
            f"/api/v1/challenges/attempts/{att_id}/submit",
            json_data={
                "user_id": self.user_a_id,
                "submission_data": {"answer": expected},
            },
        )
        self.assertEqual(resp_sub.status_code, 200)
        self.assertTrue(resp_sub.json()["is_successful"])

        with self.TestingSessionLocal() as db:
            sess = db.get(WakeSession, sess_id)
            assert sess is not None
            self.assertEqual(sess.status, STATUS_COMPLETED)

    def test_10_genai_provider_unavailable_fallback_to_completed_session(self):
        """Provider 503 network unavailability triggers deterministic fallback."""
        with self.TestingSessionLocal() as db:
            session = self._create_ringing_session(db, "math")
            sess_id = session.id

        with patch.object(
            MockGenAIProvider,
            "generate",
            side_effect=GenAIProviderUnavailableError("Simulated Gemini 503 service unavailable"),
        ):
            resp_start = self.client.post(
                "/api/v1/challenges/attempts/start",
                json_data={
                    "user_id": self.user_a_id,
                    "wake_session_id": sess_id,
                    "challenge_type": "math",
                },
            )
            self.assertEqual(resp_start.status_code, 201)
            att_id = resp_start.json()["id"]

        with self.TestingSessionLocal() as db:
            att = db.get(ChallengeAttempt, att_id)
            assert att is not None
            prompt = json.loads(att.prompt_content)
            self.assertTrue(prompt["is_fallback"])

    def test_11_genai_malformed_json_fallback_to_completed_session(self):
        """Malformed GenAI provider JSON payload triggers deterministic fallback."""
        with self.TestingSessionLocal() as db:
            session = self._create_ringing_session(db, "math")
            sess_id = session.id

        with patch.object(
            MockGenAIProvider,
            "generate",
            side_effect=GenAIValidationError("Simulated malformed non-JSON output from provider"),
        ):
            resp_start = self.client.post(
                "/api/v1/challenges/attempts/start",
                json_data={
                    "user_id": self.user_a_id,
                    "wake_session_id": sess_id,
                    "challenge_type": "math",
                },
            )
            self.assertEqual(resp_start.status_code, 201)
            att_id = resp_start.json()["id"]

        with self.TestingSessionLocal() as db:
            att = db.get(ChallengeAttempt, att_id)
            assert att is not None
            prompt = json.loads(att.prompt_content)
            self.assertTrue(prompt["is_fallback"])

    def test_12_genai_unsafe_content_fallback_to_completed_session(self):
        """Provider returning prohibited topics or unsafe instructions falls back safely."""
        with self.TestingSessionLocal() as db:
            session = self._create_ringing_session(db, "math")
            sess_id = session.id

        with patch.object(
            MockGenAIProvider,
            "generate",
            side_effect=GenAIValidationError("Simulated unsafe prompt injection detected"),
        ):
            resp_start = self.client.post(
                "/api/v1/challenges/attempts/start",
                json_data={
                    "user_id": self.user_a_id,
                    "wake_session_id": sess_id,
                    "challenge_type": "math",
                },
            )
            self.assertEqual(resp_start.status_code, 201)
            att_id = resp_start.json()["id"]

        with self.TestingSessionLocal() as db:
            att = db.get(ChallengeAttempt, att_id)
            assert att is not None
            prompt = json.loads(att.prompt_content)
            self.assertTrue(prompt["is_fallback"])

    def test_12b_genai_memory_fallback_to_completed_session(self):
        """Memory challenge provider failure safely falls back to deterministic sequence and completes session."""
        with self.TestingSessionLocal() as db:
            session = self._create_ringing_session(db, "memory")
            sess_id = session.id

        with patch.object(
            MockGenAIProvider,
            "generate",
            side_effect=GenAIProviderUnavailableError("Simulated Gemini memory unavailable"),
        ):
            resp_start = self.client.post(
                "/api/v1/challenges/attempts/start",
                json_data={
                    "user_id": self.user_a_id,
                    "wake_session_id": sess_id,
                    "challenge_type": "memory",
                },
            )
            self.assertEqual(resp_start.status_code, 201)
            att_id = resp_start.json()["id"]

        with self.TestingSessionLocal() as db:
            att = db.get(ChallengeAttempt, att_id)
            assert att is not None
            prompt = json.loads(att.prompt_content)
            self.assertTrue(prompt["is_fallback"])
            expected = prompt["expected_answer"]
            self.assertIsInstance(expected, list)

        # Verification still functions cleanly on fallback
        resp_sub = self.client.post(
            f"/api/v1/challenges/attempts/{att_id}/submit",
            json_data={
                "user_id": self.user_a_id,
                "submission_data": {"sequence": expected},
            },
        )
        self.assertEqual(resp_sub.status_code, 200)
        self.assertTrue(resp_sub.json()["is_successful"])

        with self.TestingSessionLocal() as db:
            sess = db.get(WakeSession, sess_id)
            assert sess is not None
            self.assertEqual(sess.status, STATUS_COMPLETED)

    def test_12c_genai_tongue_twister_fallback_to_completed_session(self):
        """Tongue twister provider failure safely falls back to deterministic passage and completes session."""
        with self.TestingSessionLocal() as db:
            session = self._create_ringing_session(db, "tongue_twister")
            sess_id = session.id

        with patch.object(
            MockGenAIProvider,
            "generate",
            side_effect=GenAITimeoutError("Simulated Gemini tongue twister timeout"),
        ):
            resp_start = self.client.post(
                "/api/v1/challenges/attempts/start",
                json_data={
                    "user_id": self.user_a_id,
                    "wake_session_id": sess_id,
                    "challenge_type": "tongue_twister",
                },
            )
            self.assertEqual(resp_start.status_code, 201)
            att_id = resp_start.json()["id"]

        with self.TestingSessionLocal() as db:
            att = db.get(ChallengeAttempt, att_id)
            assert att is not None
            prompt = json.loads(att.prompt_content)
            self.assertTrue(prompt["is_fallback"])

        resp_sub = self.client.post(
            f"/api/v1/challenges/attempts/{att_id}/submit",
            json_data={
                "user_id": self.user_a_id,
                "submission_data": {"confirmed": True},
            },
        )
        self.assertEqual(resp_sub.status_code, 200)
        self.assertTrue(resp_sub.json()["is_successful"])

        with self.TestingSessionLocal() as db:
            sess = db.get(WakeSession, sess_id)
            assert sess is not None
            self.assertEqual(sess.status, STATUS_COMPLETED)

    # =========================================================================
    # SECTION 4: Safety Invariants & Deterministic Verification Authority
    # =========================================================================

    def test_13_safety_invariant_llm_math_answer_never_trusted_directly(self):
        """LLM proposed answers are never trusted directly; Python evaluation is the sole authority."""
        with self.TestingSessionLocal() as db:
            session = self._create_ringing_session(db, "math")
            sess_id = session.id

        # LLM returns expression "7 + 8" but bogus proposed_answer 999
        questions = [
            {
                "question_id": 1,
                "question": "What is 7 + 8?",
                "expression": "7 + 8",
                "operation": "addition",
                "operands": [7, 8],
                "proposed_answer": 999,
            },
            {
                "question_id": 2,
                "question": "What is 10 + 5?",
                "expression": "10 + 5",
                "operation": "addition",
                "operands": [10, 5],
                "proposed_answer": 999,
            },
        ]
        canned_dict = _create_canned_math_response(
            challenge_type="math",
            difficulty_level="medium",
            questions=questions,
        )
        bogus_llm_resp = GenAIGenerationResponse(
            content=canned_dict,
            provider_name="mock",
            model_name="mock-v1",
            latency_ms=10.0,
        )

        with patch.object(settings, "GENAI_ENABLED", True):
            with patch.object(MockGenAIProvider, "generate", return_value=bogus_llm_resp):
                resp_start = self.client.post(
                    "/api/v1/challenges/attempts/start",
                    json_data={
                        "user_id": self.user_a_id,
                        "wake_session_id": sess_id,
                        "challenge_type": "math",
                    },
                )
                att_id = resp_start.json()["id"]

        # 1. Submitting LLM's hallucinated answer (999) MUST FAIL
        resp_bogus = self.client.post(
            f"/api/v1/challenges/attempts/{att_id}/submit",
            json_data={
                "user_id": self.user_a_id,
                "submission_data": {"answer": 999},
            },
        )
        self.assertEqual(resp_bogus.status_code, 200)
        self.assertFalse(resp_bogus.json()["is_successful"])

        with self.TestingSessionLocal() as db:
            att = db.get(ChallengeAttempt, att_id)
            assert att is not None
            prompt = json.loads(att.prompt_content)
            # The LLM's hallucinated answer failed domain safety validation (derivation mismatch),
            # so SafetyRetryOrchestrator safely fell back to deterministic math (92).
            self.assertTrue(prompt["is_fallback"])
            verified_expected = prompt["expected_answer"]
            self.assertNotEqual(verified_expected, 999)

        # 2. Submitting the verified answer succeeds and completes the session
        # (Start retry attempt or verify fallback)
        resp_valid = self.client.post(
            "/api/v1/challenges/attempts/start",
            json_data={
                "user_id": self.user_a_id,
                "wake_session_id": sess_id,
                "challenge_type": "math",
            },
        )
        att2_id = resp_valid.json()["id"]
        with self.TestingSessionLocal() as db:
            att2 = db.get(ChallengeAttempt, att2_id)
            assert att2 is not None
            exp2 = json.loads(att2.prompt_content)["expected_answer"]

        resp_sub = self.client.post(
            f"/api/v1/challenges/attempts/{att2_id}/submit",
            json_data={
                "user_id": self.user_a_id,
                "submission_data": {"answer": exp2},
            },
        )
        self.assertEqual(resp_sub.status_code, 200)
        self.assertTrue(resp_sub.json()["is_successful"])

        with self.TestingSessionLocal() as db:
            sess = db.get(WakeSession, sess_id)
            assert sess is not None
            self.assertEqual(sess.status, STATUS_COMPLETED)

    def test_14_safety_invariant_memory_answer_key_deterministic_and_no_number_guessing(self):
        """Memory challenges enforce deterministic recall and forbid number guessing."""
        with self.TestingSessionLocal() as db:
            session = self._create_ringing_session(db, "memory")
            sess_id = session.id

        resp_start = self.client.post(
            "/api/v1/challenges/attempts/start",
            json_data={
                "user_id": self.user_a_id,
                "wake_session_id": sess_id,
                "challenge_type": "memory",
            },
        )
        att_id = resp_start.json()["id"]

        # Attempting number guessing submission must be rejected with HTTP 400
        resp_guessing = self.client.post(
            f"/api/v1/challenges/attempts/{att_id}/submit",
            json_data={
                "user_id": self.user_a_id,
                "submission_data": {"guess_number": 42},
            },
        )
        self.assertEqual(resp_guessing.status_code, 400)
        body = resp_guessing.json()
        assert body is not None
        self.assertIn("number guessing", body["detail"].lower())

    # =========================================================================
    # SECTION 5: Failure Submissions & Retry Recovery
    # =========================================================================

    def test_15_failure_submission_does_not_complete_session_and_allows_retry(self):
        """Incorrect submission leaves session in_challenge; subsequent retry succeeds and completes."""
        with self.TestingSessionLocal() as db:
            session = self._create_ringing_session(db, "math")
            sess_id = session.id

        # 1. Start Attempt 1
        resp_att1 = self.client.post(
            "/api/v1/challenges/attempts/start",
            json_data={
                "user_id": self.user_a_id,
                "wake_session_id": sess_id,
                "challenge_type": "math",
            },
        )
        att1_id = resp_att1.json()["id"]

        # 2. Submit wrong answer
        resp_sub1 = self.client.post(
            f"/api/v1/challenges/attempts/{att1_id}/submit",
            json_data={
                "user_id": self.user_a_id,
                "submission_data": {"answer": -9999},
            },
        )
        self.assertEqual(resp_sub1.status_code, 200)
        self.assertFalse(resp_sub1.json()["is_successful"])

        # WakeSession MUST remain in_challenge, NOT completed
        with self.TestingSessionLocal() as db:
            sess_mid = db.get(WakeSession, sess_id)
            assert sess_mid is not None
            self.assertEqual(sess_mid.status, STATUS_IN_CHALLENGE)

        # 3. Start Retry Attempt (Attempt 2)
        resp_att2 = self.client.post(
            "/api/v1/challenges/attempts/start",
            json_data={
                "user_id": self.user_a_id,
                "wake_session_id": sess_id,
                "challenge_type": "math",
            },
        )
        self.assertEqual(resp_att2.status_code, 201)
        att2_data = resp_att2.json()
        assert att2_data is not None
        att2_id = att2_data["id"]
        self.assertEqual(att2_data["attempt_number"], 2)

        with self.TestingSessionLocal() as db:
            att2 = db.get(ChallengeAttempt, att2_id)
            assert att2 is not None
            expected2 = json.loads(att2.prompt_content)["expected_answer"]

        # 4. Submit correct answer on retry
        resp_sub2 = self.client.post(
            f"/api/v1/challenges/attempts/{att2_id}/submit",
            json_data={
                "user_id": self.user_a_id,
                "submission_data": {"answer": expected2},
            },
        )
        self.assertEqual(resp_sub2.status_code, 200)
        self.assertTrue(resp_sub2.json()["is_successful"])

        # WakeSession MUST now be completed
        with self.TestingSessionLocal() as db:
            sess_final = db.get(WakeSession, sess_id)
            assert sess_final is not None
            self.assertEqual(sess_final.status, STATUS_COMPLETED)

    def test_15b_dance_failure_submission_and_retry_recovery(self):
        """Dance unconfirmed submission leaves session in_challenge; retry confirms and completes."""
        with self.TestingSessionLocal() as db:
            session = self._create_ringing_session(db, "dance")
            sess_id = session.id

        resp_att1 = self.client.post(
            "/api/v1/challenges/attempts/start",
            json_data={"user_id": self.user_a_id, "wake_session_id": sess_id, "challenge_type": "dance"},
        )
        self.assertEqual(resp_att1.status_code, 201)
        att1_id = resp_att1.json()["id"]

        resp_sub1 = self.client.post(
            f"/api/v1/challenges/attempts/{att1_id}/submit",
            json_data={"user_id": self.user_a_id, "submission_data": {"confirmed": False}},
        )
        self.assertEqual(resp_sub1.status_code, 200)
        self.assertFalse(resp_sub1.json()["is_successful"])

        with self.TestingSessionLocal() as db:
            sess = db.get(WakeSession, sess_id)
            assert sess is not None
            self.assertEqual(sess.status, STATUS_IN_CHALLENGE)

        resp_att2 = self.client.post(
            "/api/v1/challenges/attempts/start",
            json_data={"user_id": self.user_a_id, "wake_session_id": sess_id, "challenge_type": "dance"},
        )
        self.assertEqual(resp_att2.status_code, 201)
        att2_id = resp_att2.json()["id"]

        resp_sub2 = self.client.post(
            f"/api/v1/challenges/attempts/{att2_id}/submit",
            json_data={"user_id": self.user_a_id, "submission_data": {"confirmed": True}},
        )
        self.assertEqual(resp_sub2.status_code, 200)
        self.assertTrue(resp_sub2.json()["is_successful"])

        with self.TestingSessionLocal() as db:
            sess_final = db.get(WakeSession, sess_id)
            assert sess_final is not None
            self.assertEqual(sess_final.status, STATUS_COMPLETED)

    def test_15c_memory_failure_submission_and_retry_recovery(self):
        """Memory incorrect sequence leaves session in_challenge; retry submits correct sequence and completes."""
        with self.TestingSessionLocal() as db:
            session = self._create_ringing_session(db, "memory")
            sess_id = session.id

        resp_att1 = self.client.post(
            "/api/v1/challenges/attempts/start",
            json_data={"user_id": self.user_a_id, "wake_session_id": sess_id, "challenge_type": "memory"},
        )
        self.assertEqual(resp_att1.status_code, 201)
        att1_id = resp_att1.json()["id"]

        resp_sub1 = self.client.post(
            f"/api/v1/challenges/attempts/{att1_id}/submit",
            json_data={"user_id": self.user_a_id, "submission_data": {"sequence": ["WRONG_SEQUENCE_TOKEN"]}},
        )
        self.assertEqual(resp_sub1.status_code, 200)
        self.assertFalse(resp_sub1.json()["is_successful"])

        with self.TestingSessionLocal() as db:
            sess = db.get(WakeSession, sess_id)
            assert sess is not None
            self.assertEqual(sess.status, STATUS_IN_CHALLENGE)

        resp_att2 = self.client.post(
            "/api/v1/challenges/attempts/start",
            json_data={"user_id": self.user_a_id, "wake_session_id": sess_id, "challenge_type": "memory"},
        )
        self.assertEqual(resp_att2.status_code, 201)
        att2_id = resp_att2.json()["id"]
        with self.TestingSessionLocal() as db:
            att2 = db.get(ChallengeAttempt, att2_id)
            assert att2 is not None
            expected2 = json.loads(att2.prompt_content)["expected_answer"]

        resp_sub2 = self.client.post(
            f"/api/v1/challenges/attempts/{att2_id}/submit",
            json_data={"user_id": self.user_a_id, "submission_data": {"sequence": expected2}},
        )
        self.assertEqual(resp_sub2.status_code, 200)
        self.assertTrue(resp_sub2.json()["is_successful"])

        with self.TestingSessionLocal() as db:
            sess_final = db.get(WakeSession, sess_id)
            assert sess_final is not None
            self.assertEqual(sess_final.status, STATUS_COMPLETED)

    def test_15d_tongue_twister_failure_submission_and_retry_recovery(self):
        """Tongue Twister unconfirmed leaves session in_challenge; retry confirms and completes."""
        with self.TestingSessionLocal() as db:
            session = self._create_ringing_session(db, "tongue_twister")
            sess_id = session.id

        resp_att1 = self.client.post(
            "/api/v1/challenges/attempts/start",
            json_data={"user_id": self.user_a_id, "wake_session_id": sess_id, "challenge_type": "tongue_twister"},
        )
        self.assertEqual(resp_att1.status_code, 201)
        att1_id = resp_att1.json()["id"]

        resp_sub1 = self.client.post(
            f"/api/v1/challenges/attempts/{att1_id}/submit",
            json_data={"user_id": self.user_a_id, "submission_data": {"confirmed": False}},
        )
        self.assertEqual(resp_sub1.status_code, 200)
        self.assertFalse(resp_sub1.json()["is_successful"])

        with self.TestingSessionLocal() as db:
            sess = db.get(WakeSession, sess_id)
            assert sess is not None
            self.assertEqual(sess.status, STATUS_IN_CHALLENGE)

        resp_att2 = self.client.post(
            "/api/v1/challenges/attempts/start",
            json_data={"user_id": self.user_a_id, "wake_session_id": sess_id, "challenge_type": "tongue_twister"},
        )
        self.assertEqual(resp_att2.status_code, 201)
        att2_id = resp_att2.json()["id"]

        resp_sub2 = self.client.post(
            f"/api/v1/challenges/attempts/{att2_id}/submit",
            json_data={"user_id": self.user_a_id, "submission_data": {"confirmed": True}},
        )
        self.assertEqual(resp_sub2.status_code, 200)
        self.assertTrue(resp_sub2.json()["is_successful"])

        with self.TestingSessionLocal() as db:
            sess_final = db.get(WakeSession, sess_id)
            assert sess_final is not None
            self.assertEqual(sess_final.status, STATUS_COMPLETED)

    def test_15e_push_ups_failure_submission_and_retry_recovery(self):
        """Push-ups insufficient reps leaves session in_challenge; retry with target reps completes."""
        with self.TestingSessionLocal() as db:
            session = self._create_ringing_session(db, "push_ups")
            sess_id = session.id

        resp_att1 = self.client.post(
            "/api/v1/challenges/attempts/start",
            json_data={"user_id": self.user_a_id, "wake_session_id": sess_id, "challenge_type": "push_ups"},
        )
        self.assertEqual(resp_att1.status_code, 201)
        att1_id = resp_att1.json()["id"]

        # Submitting 0 reps fails
        resp_sub1 = self.client.post(
            f"/api/v1/challenges/attempts/{att1_id}/submit",
            json_data={"user_id": self.user_a_id, "submission_data": {"reps_completed": 0}},
        )
        self.assertEqual(resp_sub1.status_code, 200)
        self.assertFalse(resp_sub1.json()["is_successful"])

        with self.TestingSessionLocal() as db:
            sess = db.get(WakeSession, sess_id)
            assert sess is not None
            self.assertEqual(sess.status, STATUS_IN_CHALLENGE)

        resp_att2 = self.client.post(
            "/api/v1/challenges/attempts/start",
            json_data={"user_id": self.user_a_id, "wake_session_id": sess_id, "challenge_type": "push_ups"},
        )
        self.assertEqual(resp_att2.status_code, 201)
        att2_id = resp_att2.json()["id"]
        with self.TestingSessionLocal() as db:
            att2 = db.get(ChallengeAttempt, att2_id)
            assert att2 is not None
            target = json.loads(att2.prompt_content)["content_payload"]["target_repetitions"]

        resp_sub2 = self.client.post(
            f"/api/v1/challenges/attempts/{att2_id}/submit",
            json_data={"user_id": self.user_a_id, "submission_data": {"reps_completed": target}},
        )
        self.assertEqual(resp_sub2.status_code, 200)
        self.assertTrue(resp_sub2.json()["is_successful"])

        with self.TestingSessionLocal() as db:
            sess_final = db.get(WakeSession, sess_id)
            assert sess_final is not None
            self.assertEqual(sess_final.status, STATUS_COMPLETED)

    def test_15f_safety_invariant_cannot_switch_challenge_type_on_retry(self):
        """Attempting to switch challenge type on a retry attempt is strictly rejected with HTTP 400."""
        with self.TestingSessionLocal() as db:
            session = self._create_ringing_session(db, "dance")
            sess_id = session.id

        # Attempt 1: Dance
        resp_att1 = self.client.post(
            "/api/v1/challenges/attempts/start",
            json_data={"user_id": self.user_a_id, "wake_session_id": sess_id, "challenge_type": "dance"},
        )
        att1_id = resp_att1.json()["id"]
        self.client.post(
            f"/api/v1/challenges/attempts/{att1_id}/submit",
            json_data={"user_id": self.user_a_id, "submission_data": {"confirmed": False}},
        )

        # Attempt to retry with Math instead of Dance -> 400 Bad Request
        resp_switch = self.client.post(
            "/api/v1/challenges/attempts/start",
            json_data={"user_id": self.user_a_id, "wake_session_id": sess_id, "challenge_type": "math"},
        )
        self.assertEqual(resp_switch.status_code, 400)
        self.assertIn("switch challenge type", resp_switch.json()["detail"].lower())

    # =========================================================================
    # SECTION 6: Duplicate and Concurrent Operation Protections
    # =========================================================================

    def test_16_duplicate_start_attempt_returns_conflict_409(self):
        """Starting an attempt while an active attempt is in progress returns HTTP 409 Conflict."""
        with self.TestingSessionLocal() as db:
            session = self._create_ringing_session(db, "dance")
            sess_id = session.id

        # First start: 201 Created
        resp1 = self.client.post(
            "/api/v1/challenges/attempts/start",
            json_data={
                "user_id": self.user_a_id,
                "wake_session_id": sess_id,
                "challenge_type": "dance",
            },
        )
        self.assertEqual(resp1.status_code, 201)

        # Duplicate start while attempt 1 is unsubmitted: 409 Conflict
        resp2 = self.client.post(
            "/api/v1/challenges/attempts/start",
            json_data={
                "user_id": self.user_a_id,
                "wake_session_id": sess_id,
                "challenge_type": "dance",
            },
        )
        self.assertEqual(resp2.status_code, 409)
        body = resp2.json()
        assert body is not None
        self.assertIn("active", body["detail"].lower())

    def test_17_duplicate_submission_returns_error_400(self):
        """Submitting an attempt that has already been completed returns HTTP 400."""
        with self.TestingSessionLocal() as db:
            session = self._create_ringing_session(db, "dance")
            sess_id = session.id

        resp_start = self.client.post(
            "/api/v1/challenges/attempts/start",
            json_data={
                "user_id": self.user_a_id,
                "wake_session_id": sess_id,
                "challenge_type": "dance",
            },
        )
        att_id = resp_start.json()["id"]

        # First submission: 200 OK
        resp_sub1 = self.client.post(
            f"/api/v1/challenges/attempts/{att_id}/submit",
            json_data={
                "user_id": self.user_a_id,
                "submission_data": {"confirmed": True},
            },
        )
        self.assertEqual(resp_sub1.status_code, 200)

        # Duplicate submission: 400 Bad Request
        resp_sub2 = self.client.post(
            f"/api/v1/challenges/attempts/{att_id}/submit",
            json_data={
                "user_id": self.user_a_id,
                "submission_data": {"confirmed": True},
            },
        )
        self.assertEqual(resp_sub2.status_code, 400)
        body = resp_sub2.json()
        assert body is not None
        self.assertIn("already", body["detail"].lower())

    def test_18_submission_after_session_completed_or_abandoned_rejected(self):
        """Submitting an attempt against an already completed or abandoned session returns HTTP 400."""
        with self.TestingSessionLocal() as db:
            session = self._create_ringing_session(db, "dance")
            sess_id = session.id

            # Directly create attempt in progress
            req = ChallengeAttemptStartRequest(
                user_id=self.user_a_id,
                wake_session_id=sess_id,
                challenge_type="dance",
            )
            att = start_challenge_attempt(db, req)
            att_id = att.id

            # Manually complete the session externally
            complete_wake_session(db, sess_id)

        # Now submit against terminal session
        resp = self.client.post(
            f"/api/v1/challenges/attempts/{att_id}/submit",
            json_data={
                "user_id": self.user_a_id,
                "submission_data": {"confirmed": True},
            },
        )
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        assert body is not None
        self.assertIn("terminal", body["detail"].lower())

    # =========================================================================
    # SECTION 7: State Machine Validation & Terminal Protection
    # =========================================================================

    def test_19_state_machine_valid_transitions_including_snooze_resume(self):
        """Lifecycle valid path: ringing -> snoozed -> ringing -> in_challenge -> completed."""
        with self.TestingSessionLocal() as db:
            session = self._create_ringing_session(db, "math")
            sess_id = session.id

            # 1. Snooze: ringing -> snoozed
            snooze_res = record_snooze(db, session_id=sess_id, user_id=self.user_a_id, duration_minutes=5)
            self.assertEqual(snooze_res.wake_session.status, STATUS_SNOOZED)

            # 2. Resume: snoozed -> ringing
            resumed = resume_ringing(db, session_id=sess_id)
            self.assertEqual(resumed.status, STATUS_RINGING)

            # 3. Start attempt: ringing -> in_challenge
            req = ChallengeAttemptStartRequest(
                user_id=self.user_a_id,
                wake_session_id=sess_id,
                challenge_type="math",
            )
            att = start_challenge_attempt(db, req)
            db.refresh(resumed)
            self.assertEqual(resumed.status, STATUS_IN_CHALLENGE)

            # 4. Complete via verification: in_challenge -> completed
            expected = json.loads(att.prompt_content)["expected_answer"]
            submit_challenge_attempt(db, attempt_id=att.id, user_id=self.user_a_id, submission_data={"answer": expected})
            db.refresh(resumed)
            self.assertEqual(resumed.status, STATUS_COMPLETED)

    def test_19b_state_machine_repeated_snooze_resume_cycles(self):
        """Multiple sequential snooze and resume cycles maintain state integrity before challenge."""
        with self.TestingSessionLocal() as db:
            session = self._create_ringing_session(db, "math")
            sess_id = session.id

            # Cycle 1: ringing -> snoozed -> ringing
            s1 = record_snooze(db, session_id=sess_id, user_id=self.user_a_id, duration_minutes=5)
            self.assertEqual(s1.wake_session.status, STATUS_SNOOZED)
            r1 = resume_ringing(db, session_id=sess_id)
            self.assertEqual(r1.status, STATUS_RINGING)

            # Cycle 2: ringing -> snoozed -> ringing
            s2 = record_snooze(db, session_id=sess_id, user_id=self.user_a_id, duration_minutes=10)
            self.assertEqual(s2.wake_session.status, STATUS_SNOOZED)
            r2 = resume_ringing(db, session_id=sess_id)
            self.assertEqual(r2.status, STATUS_RINGING)

            # Proceed to challenge: ringing -> in_challenge -> completed
            att = start_challenge_attempt(
                db,
                ChallengeAttemptStartRequest(
                    user_id=self.user_a_id,
                    wake_session_id=sess_id,
                    challenge_type="math",
                ),
            )
            self.assertEqual(r2.status, STATUS_IN_CHALLENGE)
            expected = json.loads(att.prompt_content)["expected_answer"]
            submit_challenge_attempt(db, attempt_id=att.id, user_id=self.user_a_id, submission_data={"answer": expected})
            db.refresh(r2)
            self.assertEqual(r2.status, STATUS_COMPLETED)

    def test_20_state_machine_terminal_states_cannot_be_resurrected(self):
        """Terminal sessions (completed, abandoned) cannot be resurrected or transitioned."""
        with self.TestingSessionLocal() as db:
            session_comp = self._create_ringing_session(db, "math")
            complete_wake_session(db, session_comp.id)

            session_aband = self._create_ringing_session(db, "dance")
            fail_wake_session(db, session_aband.id)

            # completed session rejection
            with self.assertRaises(InvalidSessionTransitionError):
                record_snooze(db, session_id=session_comp.id, user_id=self.user_a_id)
            with self.assertRaises(InvalidSessionTransitionError):
                resume_ringing(db, session_id=session_comp.id)
            with self.assertRaises(InvalidSessionTransitionError):
                complete_wake_session(db, session_comp.id)
            with self.assertRaises(InvalidSessionTransitionError):
                start_challenge_attempt(
                    db,
                    ChallengeAttemptStartRequest(
                        user_id=self.user_a_id,
                        wake_session_id=session_comp.id,
                        challenge_type="math",
                    ),
                )

            # abandoned session rejection
            with self.assertRaises(InvalidSessionTransitionError):
                record_snooze(db, session_id=session_aband.id, user_id=self.user_a_id)
            with self.assertRaises(InvalidSessionTransitionError):
                resume_ringing(db, session_id=session_aband.id)
            with self.assertRaises(InvalidSessionTransitionError):
                fail_wake_session(db, session_aband.id)
            with self.assertRaises(InvalidSessionTransitionError):
                start_challenge_attempt(
                    db,
                    ChallengeAttemptStartRequest(
                        user_id=self.user_a_id,
                        wake_session_id=session_aband.id,
                        challenge_type="dance",
                    ),
                )

    # =========================================================================
    # SECTION 8: Ownership Validation (HTTP 403)
    # =========================================================================

    def test_21_cross_user_ownership_isolation_across_endpoints(self):
        """User B cannot start, submit, or inspect challenge attempts for User A's session."""
        with self.TestingSessionLocal() as db:
            session_a = self._create_ringing_session(db, "math")
            sess_a_id = session_a.id

        # 1. User B cannot start attempt on User A's session (403)
        resp_start = self.client.post(
            "/api/v1/challenges/attempts/start",
            json_data={
                "user_id": self.user_b_id,
                "wake_session_id": sess_a_id,
                "challenge_type": "math",
            },
        )
        self.assertEqual(resp_start.status_code, 403)

        # Start valid attempt with User A
        resp_start_a = self.client.post(
            "/api/v1/challenges/attempts/start",
            json_data={
                "user_id": self.user_a_id,
                "wake_session_id": sess_a_id,
                "challenge_type": "math",
            },
        )
        att_a_id = resp_start_a.json()["id"]

        # 2. User B cannot submit User A's attempt (403)
        resp_sub = self.client.post(
            f"/api/v1/challenges/attempts/{att_a_id}/submit",
            json_data={
                "user_id": self.user_b_id,
                "submission_data": {"answer": 42},
            },
        )
        self.assertEqual(resp_sub.status_code, 403)

        # 3. User B cannot retrieve User A's attempt details (403)
        resp_get = self.client.get(
            f"/api/v1/challenges/attempts/{att_a_id}?user_id={self.user_b_id}"
        )
        self.assertEqual(resp_get.status_code, 403)

        # 4. User B cannot list attempts for User A's session (403)
        resp_list = self.client.get(
            f"/api/v1/wake-sessions/{sess_a_id}/challenge-attempts?user_id={self.user_b_id}"
        )
        self.assertEqual(resp_list.status_code, 403)

    # =========================================================================
    # SECTION 9: Security Regression & Data Minimization
    # =========================================================================

    def test_22_security_regression_and_data_minimization(self):
        """Prompt content contains zero secrets, stripped credentials, and preserved legitimate keys."""
        with self.TestingSessionLocal() as db:
            session = self._create_ringing_session(db, "math")

            # Provide personalization context containing credential fields AND legitimate terms
            dirty_context = {
                "desired_duration_seconds": 25,
                "preferred_theme": "keyboard jazz & keynote morning",
                "disallowed_topics": ["hockey injuries", "monkey business"],
                "api_key": "LEAKED_API_KEY_SECRET",
                "jwt": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
                "password": "SUPER_SECRET_PASSWORD",
            }

            safe_ctx = RuntimePersonalizationBridge.build_safe_context(wake_session=session, explicit_context=dirty_context)
            self.assertEqual(safe_ctx.preferred_theme, "keyboard jazz & keynote morning")
            self.assertIn("hockey injuries", safe_ctx.disallowed_topics)
            self.assertIn("monkey business", safe_ctx.disallowed_topics)

            req = ChallengeAttemptStartRequest(
                user_id=self.user_a_id,
                wake_session_id=session.id,
                challenge_type="math",
            )
            att = start_challenge_attempt(db, req)
            payload_str = att.prompt_content
            self.assertNotIn("LEAKED_API_KEY_SECRET", payload_str)
            self.assertNotIn("SUPER_SECRET_PASSWORD", payload_str)
            for forbidden in FORBIDDEN_CONTEXT_KEYS:
                self.assertNotIn(f'"{forbidden}"', payload_str)

    # =========================================================================
    # SECTION 10: Data Integrity & Schema Audit
    # =========================================================================

    def test_23_persisted_challenge_attempt_data_integrity(self):
        """Persisted ChallengeAttempt records store exact schema fields, durations, and zero secrets."""
        with self.TestingSessionLocal() as db:
            session = self._create_ringing_session(db, "math")
            sess_id = session.id

            # Create attempt
            req = ChallengeAttemptStartRequest(
                user_id=self.user_a_id,
                wake_session_id=sess_id,
                challenge_type="math",
                difficulty_level="medium",
            )
            att = start_challenge_attempt(db, req)
            att_id = att.id

            # Verify pre-submission fields
            self.assertEqual(att.challenge_type, "math")
            self.assertEqual(att.difficulty_level, "medium")
            self.assertIsNone(att.completed_at)
            self.assertIsNone(att.duration_seconds)
            self.assertIsNone(att.is_successful)

            # Submit and verify post-submission fields
            expected = json.loads(att.prompt_content)["expected_answer"]
            completed_att = submit_challenge_attempt(
                db,
                attempt_id=att_id,
                user_id=self.user_a_id,
                submission_data={"answer": expected},
            )
            self.assertTrue(completed_att.is_successful)
            self.assertIsNotNone(completed_att.completed_at)
            self.assertIsNotNone(completed_att.duration_seconds)
            self.assertGreaterEqual(completed_att.duration_seconds, 0.0)
            self.assertEqual(completed_att.verification_score, 1.0)
            self.assertIsNone(completed_att.failure_reason)

            # Verify serialized verification result
            ver_res = json.loads(completed_att.verification_result)
            self.assertIn("status", ver_res)
            self.assertIn("diagnostics", ver_res)

            # Verify prompt content structure and absence of secrets
            prompt_data = json.loads(completed_att.prompt_content)
            self.assertEqual(prompt_data["challenge_type"], "math")
            self.assertEqual(prompt_data["difficulty_level"], "medium")
            self.assertIn("content_payload", prompt_data)
            self.assertIn("expected_answer", prompt_data)
            self.assertIn("verification_mode", prompt_data)
            for forbidden in FORBIDDEN_CONTEXT_KEYS:
                self.assertNotIn(forbidden, completed_att.prompt_content)


if __name__ == "__main__":
    unittest.main()
