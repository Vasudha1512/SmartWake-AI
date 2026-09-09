"""Automated test suite for Phase 2.8 Challenge Verification Engine.

Tests:
Math:
1. Correct answer succeeds
2. Incorrect answer fails
3. Missing answer fails
4. Malformed answer fails

Memory:
5. Correct visual sequence succeeds
6. Incorrect sequence fails
7. Wrong order fails
8. Partial sequence fails
9. Extra sequence elements fail
10. Spatial pattern verification works
11. No number guessing implementation exists

Dance:
12. Manual confirmation succeeds
13. Manual rejection fails
14. Malformed submission fails
15. Diagnostic result identifies manual/development verification

Tongue Twister:
16. Manual confirmation succeeds
17. Manual rejection fails
18. Malformed submission fails
19. No fake STT is implemented

Push-ups:
20. Manual confirmation succeeds
21. Manual rejection fails
22. Malformed submission fails
23. No fake CV/pose verification is implemented

Dispatcher & API:
24. Correct verifier selected for each challenge type
25. Unsupported challenge type rejected
26. Invalid runtime payload handled safely
27. REST API POST /api/v1/challenges/verify works accurately

Regression:
28. Existing challenge generation tests continue passing
29. Existing challenge catalog remains unchanged
30. Database remains unchanged by verification
"""
import asyncio
import json
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.constants import FORBIDDEN_CHALLENGE_TYPES, VALID_CHALLENGE_TYPES
from backend.app.core.exceptions import InvalidChallengeTypeError
from backend.app.database.base import Base
import backend.app.database.session  # Ensures pragma listeners
from backend.app.database.session import get_db
from backend.app.main import app
from backend.app.models.challenge import Challenge
from backend.app.models.challenge_attempt import ChallengeAttempt
from backend.app.schemas.challenge_schemas import (
    ChallengeVerificationResult,
    RuntimeChallengeGenerationRequest,
)
from backend.app.services.challenge_generation_service import generate_challenge
from backend.app.services.challenge_seed_service import seed_default_challenges
from backend.app.services.challenge_verification_service import (
    verify_challenge,
    verify_dance,
    verify_math,
    verify_memory,
    verify_push_ups,
    verify_tongue_twister,
)


class SimpleASGIClient:
    """Lightweight ASGI test client using Python asyncio standard library."""

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

    def post(self, path: str, json_data: dict = None, headers: dict = None):
        return self._request("POST", path, json_data=json_data, headers=headers)


class TestChallengeVerification(unittest.TestCase):
    """Isolated test suite for Phase 2.8 Challenge Verification Engine."""

    @classmethod
    def setUpClass(cls):
        """Set up isolated in-memory SQLite database and client."""
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
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=cls.engine)
        cls.engine.dispose()

    def setUp(self):
        """Clean tables and seed 30 templates in isolated in-memory DB."""
        with self.TestingSessionLocal() as session:
            for table in reversed(Base.metadata.sorted_tables):
                session.execute(table.delete())
            session.commit()
            seed_default_challenges(session)

    # ----------------------------------------------------------------------
    # MATH TESTS (1-4)
    # ----------------------------------------------------------------------
    def test_01_math_correct_answer_succeeds(self):
        """Math: exact integer answer succeeds with score 1.0."""
        challenge = {
            "challenge_type": "math",
            "expected_answer": [17],
        }
        res = verify_math(challenge, {"answer": 17})
        self.assertTrue(res.is_successful)
        self.assertEqual(res.verification_score, 1.0)
        self.assertEqual(res.verification_result, "exact_match")
        self.assertIsNone(res.failure_reason)

        # Multi-question list match
        multi_chal = {
            "challenge_type": "math",
            "expected_answer": [12, 25, 8],
        }
        res_multi = verify_math(multi_chal, {"answers": ["12", 25, 8]})
        self.assertTrue(res_multi.is_successful)
        self.assertEqual(res_multi.verification_score, 1.0)

    def test_02_math_incorrect_answer_fails(self):
        """Math: incorrect answer fails with score 0.0."""
        challenge = {
            "challenge_type": "math",
            "expected_answer": [17],
        }
        res = verify_math(challenge, {"answer": 18})
        self.assertFalse(res.is_successful)
        self.assertEqual(res.verification_score, 0.0)
        self.assertEqual(res.verification_result, "failed")
        self.assertEqual(res.failure_reason, "incorrect_answer")

    def test_03_math_missing_answer_fails(self):
        """Math: missing or None answer fails gracefully."""
        challenge = {
            "challenge_type": "math",
            "expected_answer": [17],
        }
        res_empty = verify_math(challenge, {})
        self.assertFalse(res_empty.is_successful)
        self.assertEqual(res_empty.failure_reason, "missing_answer")

        res_none = verify_math(challenge, {"answer": None})
        self.assertFalse(res_none.is_successful)
        self.assertEqual(res_none.failure_reason, "missing_answer")

    def test_04_math_malformed_answer_fails(self):
        """Math: non-numeric string answer fails with malformed_answer."""
        challenge = {
            "challenge_type": "math",
            "expected_answer": [17],
        }
        res = verify_math(challenge, {"answer": "seventeen"})
        self.assertFalse(res.is_successful)
        self.assertEqual(res.failure_reason, "malformed_answer")

    # ----------------------------------------------------------------------
    # MEMORY TESTS (5-11)
    # ----------------------------------------------------------------------
    def test_05_memory_correct_visual_sequence_succeeds(self):
        """Memory: exact visual color sequence succeeds."""
        challenge = {
            "challenge_type": "memory",
            "expected_answer": ["red", "blue", "green", "yellow"],
        }
        res = verify_memory(challenge, {"sequence": ["red", "blue", "green", "yellow"]})
        self.assertTrue(res.is_successful)
        self.assertEqual(res.verification_score, 1.0)
        self.assertEqual(res.verification_result, "exact_match")

    def test_06_memory_incorrect_sequence_fails(self):
        """Memory: sequence with different elements fails."""
        challenge = {
            "challenge_type": "memory",
            "expected_answer": ["red", "blue", "green", "yellow"],
        }
        res = verify_memory(challenge, {"sequence": ["red", "purple", "green", "yellow"]})
        self.assertFalse(res.is_successful)
        self.assertEqual(res.failure_reason, "sequence_mismatch")

    def test_07_memory_wrong_order_fails(self):
        """Memory: sequence with correct elements but incorrect order fails."""
        challenge = {
            "challenge_type": "memory",
            "expected_answer": ["red", "blue", "green", "yellow"],
        }
        res = verify_memory(challenge, {"sequence": ["red", "green", "blue", "yellow"]})
        self.assertFalse(res.is_successful)
        self.assertEqual(res.failure_reason, "wrong_order")

    def test_08_memory_partial_sequence_fails(self):
        """Memory: partial sequence fails."""
        challenge = {
            "challenge_type": "memory",
            "expected_answer": ["red", "blue", "green", "yellow"],
        }
        res = verify_memory(challenge, {"sequence": ["red", "blue"]})
        self.assertFalse(res.is_successful)
        self.assertEqual(res.failure_reason, "partial_sequence")

    def test_09_memory_extra_sequence_elements_fail(self):
        """Memory: extra elements in sequence fail."""
        challenge = {
            "challenge_type": "memory",
            "expected_answer": ["red", "blue"],
        }
        res = verify_memory(challenge, {"sequence": ["red", "blue", "green"]})
        self.assertFalse(res.is_successful)
        self.assertEqual(res.failure_reason, "extra_elements")

    def test_10_memory_spatial_pattern_verification_works(self):
        """Memory: spatial grid cell pattern verification works regardless of coordinate order."""
        challenge = {
            "challenge_type": "memory",
            "generated_content": {"recall_mode": "spatial_pattern_recall"},
            "expected_answer": [[0, 1], [1, 2], [2, 0]],
        }
        # Inverted coordinate input order should pass for spatial pattern set
        res = verify_memory(challenge, {"positions": [[2, 0], [0, 1], [1, 2]]})
        self.assertTrue(res.is_successful)
        self.assertEqual(res.verification_score, 1.0)

        # Missing a coordinate cell fails
        res_fail = verify_memory(challenge, {"positions": [[2, 0], [0, 1]]})
        self.assertFalse(res_fail.is_successful)

    def test_11_memory_no_number_guessing_exists(self):
        """Memory: strictly rejects any number guessing submission or forbidden type."""
        challenge = {
            "challenge_type": "memory",
            "expected_answer": ["red", "blue"],
        }
        with self.assertRaises(InvalidChallengeTypeError):
            verify_memory(challenge, {"number_guessing_answer": 42})

        for forbidden in FORBIDDEN_CHALLENGE_TYPES:
            with self.assertRaises(InvalidChallengeTypeError):
                verify_challenge({"challenge_type": forbidden}, {"answer": 5})

    # ----------------------------------------------------------------------
    # DANCE TESTS (12-15)
    # ----------------------------------------------------------------------
    def test_12_dance_manual_confirmation_succeeds(self):
        """Dance: manual confirmation succeeds."""
        challenge = {"challenge_type": "dance"}
        res = verify_dance(challenge, {"confirmed": True})
        self.assertTrue(res.is_successful)
        self.assertEqual(res.verification_score, 1.0)
        self.assertEqual(res.verification_result, "manual_confirmed")

    def test_13_dance_manual_rejection_fails(self):
        """Dance: manual rejection fails."""
        challenge = {"challenge_type": "dance"}
        res = verify_dance(challenge, {"confirmed": False})
        self.assertFalse(res.is_successful)
        self.assertEqual(res.verification_result, "manual_rejected")
        self.assertEqual(res.failure_reason, "routine_incomplete")

    def test_14_dance_malformed_submission_fails(self):
        """Dance: malformed submission fails."""
        challenge = {"challenge_type": "dance"}
        res = verify_dance(challenge, {"other_key": 123})
        self.assertFalse(res.is_successful)
        self.assertEqual(res.failure_reason, "malformed_submission")

    def test_15_dance_diagnostics_identifies_manual_verification(self):
        """Dance: diagnostics explicitly identifies verification as manual/development."""
        challenge = {"challenge_type": "dance"}
        res = verify_dance(challenge, {"confirmed": True})
        self.assertIn("verification_mode", res.diagnostic_details)
        self.assertEqual(res.diagnostic_details["verification_mode"], "development_manual")
        self.assertFalse(res.diagnostic_details["camera_cv_active"])

    # ----------------------------------------------------------------------
    # TONGUE TWISTER TESTS (16-19)
    # ----------------------------------------------------------------------
    def test_16_tongue_twister_manual_confirmation_succeeds(self):
        """Tongue Twister: manual confirmation succeeds."""
        challenge = {
            "challenge_type": "tongue_twister",
            "expected_answer": "She sells sea shells by the sea shore.",
        }
        res = verify_tongue_twister(challenge, {"confirmed": True})
        self.assertTrue(res.is_successful)
        self.assertEqual(res.verification_score, 1.0)
        self.assertEqual(res.verification_result, "manual_confirmed")

    def test_17_tongue_twister_manual_rejection_fails(self):
        """Tongue Twister: manual rejection fails."""
        challenge = {"challenge_type": "tongue_twister"}
        res = verify_tongue_twister(challenge, {"confirmed": False})
        self.assertFalse(res.is_successful)
        self.assertEqual(res.failure_reason, "articulation_unconfirmed")

    def test_18_tongue_twister_malformed_submission_fails(self):
        """Tongue Twister: missing required fields fails."""
        challenge = {"challenge_type": "tongue_twister"}
        res = verify_tongue_twister(challenge, {})
        self.assertFalse(res.is_successful)
        self.assertEqual(res.failure_reason, "malformed_submission")

    def test_19_tongue_twister_no_fake_stt(self):
        """Tongue Twister: diagnostics explicitly confirms STT is not claimed."""
        challenge = {"challenge_type": "tongue_twister"}
        res = verify_tongue_twister(challenge, {"confirmed": True})
        self.assertFalse(res.diagnostic_details["speech_stt_active"])

    # ----------------------------------------------------------------------
    # PUSH-UPS TESTS (20-23)
    # ----------------------------------------------------------------------
    def test_20_push_ups_manual_confirmation_succeeds(self):
        """Push-ups: manual confirmation succeeds."""
        challenge = {
            "challenge_type": "push_ups",
            "expected_answer": {"target_repetitions": 10},
        }
        res = verify_push_ups(challenge, {"reps_completed": 10})
        self.assertTrue(res.is_successful)
        self.assertEqual(res.verification_score, 1.0)
        self.assertEqual(res.verification_result, "manual_confirmed")

        # Boolean confirmed also succeeds
        res_bool = verify_push_ups(challenge, {"confirmed": True})
        self.assertTrue(res_bool.is_successful)

    def test_21_push_ups_manual_rejection_fails(self):
        """Push-ups: incomplete reps fail."""
        challenge = {
            "challenge_type": "push_ups",
            "expected_answer": {"target_repetitions": 10},
        }
        res = verify_push_ups(challenge, {"reps_completed": 6})
        self.assertFalse(res.is_successful)
        self.assertEqual(res.failure_reason, "target_reps_not_met")

    def test_22_push_ups_malformed_submission_fails(self):
        """Push-ups: malformed submission fails."""
        challenge = {"challenge_type": "push_ups"}
        res = verify_push_ups(challenge, {"reps_completed": "not-an-int"})
        self.assertFalse(res.is_successful)
        self.assertEqual(res.failure_reason, "malformed_submission")

    def test_23_push_ups_no_fake_cv(self):
        """Push-ups: diagnostics confirms camera CV is not active."""
        challenge = {"challenge_type": "push_ups"}
        res = verify_push_ups(challenge, {"confirmed": True})
        self.assertFalse(res.diagnostic_details["camera_cv_active"])

    # ----------------------------------------------------------------------
    # DISPATCHER & API TESTS (24-27)
    # ----------------------------------------------------------------------
    def test_24_dispatcher_routes_all_five_types(self):
        """Dispatcher: correctly routes to all 5 challenge types."""
        cases = [
            ({"challenge_type": "math", "expected_answer": [10]}, {"answer": 10}),
            ({"challenge_type": "memory", "expected_answer": ["A", "B"]}, {"sequence": ["A", "B"]}),
            ({"challenge_type": "dance"}, {"confirmed": True}),
            ({"challenge_type": "tongue_twister"}, {"confirmed": True}),
            ({"challenge_type": "push_ups"}, {"confirmed": True}),
        ]
        for chal, sub in cases:
            res = verify_challenge(chal, sub)
            self.assertTrue(res.is_successful)

    def test_25_dispatcher_rejects_unsupported_type(self):
        """Dispatcher: rejects invalid challenge type with InvalidChallengeTypeError."""
        with self.assertRaises(InvalidChallengeTypeError):
            verify_challenge({"challenge_type": "trivia"}, {"answer": "x"})

    def test_26_dispatcher_handles_invalid_runtime_payload(self):
        """Dispatcher: raises ValueError on missing RuntimeChallenge or type."""
        with self.assertRaises(ValueError):
            verify_challenge(None, {})
        with self.assertRaises(ValueError):
            verify_challenge({}, {})

    def test_27_api_verify_endpoint(self):
        """API: POST /api/v1/challenges/verify returns structured verification result."""
        payload = {
            "runtime_challenge": {
                "challenge_type": "math",
                "expected_answer": [42],
            },
            "submission_data": {
                "answer": 42,
            },
        }
        resp = self.client.post("/api/v1/challenges/verify", json_data=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["is_successful"])
        self.assertEqual(data["verification_score"], 1.0)
        self.assertEqual(data["verification_result"], "exact_match")

        # Test failure via API
        fail_payload = {
            "runtime_challenge": {
                "challenge_type": "math",
                "expected_answer": [42],
            },
            "submission_data": {
                "answer": 43,
            },
        }
        resp_fail = self.client.post("/api/v1/challenges/verify", json_data=fail_payload)
        self.assertEqual(resp_fail.status_code, 200)
        fail_data = resp_fail.json()
        self.assertFalse(fail_data["is_successful"])
        self.assertEqual(fail_data["verification_score"], 0.0)
        self.assertEqual(fail_data["failure_reason"], "incorrect_answer")

        # Test forbidden type via API
        forbidden_payload = {
            "runtime_challenge": {
                "challenge_type": "number_guessing",
            },
            "submission_data": {"answer": 1},
        }
        resp_forbid = self.client.post("/api/v1/challenges/verify", json_data=forbidden_payload)
        self.assertEqual(resp_forbid.status_code, 400)

    # ----------------------------------------------------------------------
    # REGRESSION TESTS (28-30)
    # ----------------------------------------------------------------------
    def test_28_runtime_generation_integration(self):
        """Integration: runtime challenge generated by service verifies correctly."""
        with self.TestingSessionLocal() as db:
            req = RuntimeChallengeGenerationRequest(challenge_type="math", difficulty_level="easy")
            gen_res = generate_challenge(db, req)

            # Submit the exact expected answer
            correct_submission = {"answers": gen_res.expected_answer}
            verify_res = verify_challenge(gen_res, correct_submission)
            self.assertTrue(verify_res.is_successful)
            self.assertEqual(verify_res.verification_score, 1.0)

    def test_29_challenge_catalog_remains_unchanged(self):
        """Regression: challenge catalog retains all 30 templates."""
        with self.TestingSessionLocal() as db:
            count = db.query(Challenge).count()
            self.assertEqual(count, 30)

    def test_30_database_remains_unchanged_by_verification(self):
        """Regression: verification never writes to SQLite tables."""
        with self.TestingSessionLocal() as db:
            chal_count = db.query(Challenge).count()
            att_count = db.query(ChallengeAttempt).count()

            # Execute verification
            chal = {"challenge_type": "math", "expected_answer": [10]}
            verify_challenge(chal, {"answer": 10})

            # Counts must be completely unchanged
            self.assertEqual(db.query(Challenge).count(), chal_count)
            self.assertEqual(db.query(ChallengeAttempt).count(), att_count)


if __name__ == "__main__":
    unittest.main()
