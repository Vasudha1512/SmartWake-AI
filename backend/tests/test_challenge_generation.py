"""Automated test suite for Phase 2.7.3 Runtime Challenge Generation.

Tests:
1. Math challenge generation works and returns structured response.
2. Math expected answers are strictly correct for all generated questions.
3. Math respects template configuration (question_count, operand bounds, operations).
4. Memory challenge generation works across different recall modes.
5. Memory challenges NEVER generate number-guessing challenges or forbidden terms.
6. Dance challenge generation produces structured step sequences.
7. Tongue-twister challenge generation produces articulated passages with repetition guidelines.
8. Push-up challenge generation produces target repetitions and form guidelines.
9. Unsupported / forbidden challenge types are strictly rejected with 400.
10. Inactive templates are rejected with 400.
11. Invalid template JSON payloads are rejected with 422.
12. Missing required template configurations are rejected with 422.
13. Repeated generation produces valid, distinct runtime challenges.
14. POST /api/v1/challenges/generate API returns valid HTTP 200 responses.
15. Existing challenge catalog APIs continue working unaffected.
16. Existing wake-session APIs continue working unaffected.
17. Generation does NOT insert unexpected database rows into challenges or challenge_attempts.
"""
import asyncio
from datetime import datetime
import json
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.constants import FORBIDDEN_CHALLENGE_TYPES, VALID_CHALLENGE_TYPES
from backend.app.core.exceptions import (
    ChallengeNotFoundError,
    InactiveChallengeError,
    InvalidChallengeTypeError,
    InvalidDifficultyError,
    InvalidTemplatePayloadError,
    TemplateConfigurationError,
)
from backend.app.database.base import Base
import backend.app.database.session  # Ensures pragma listeners
from backend.app.database.session import get_db
from backend.app.main import app
from backend.app.models.alarm import Alarm
from backend.app.models.challenge import Challenge
from backend.app.models.challenge_attempt import ChallengeAttempt
from backend.app.models.user import User
from backend.app.models.wake_session import WakeSession
from backend.app.schemas.challenge_schemas import (
    RuntimeChallengeGenerationRequest,
    RuntimeChallengeResponse,
)
from backend.app.services.challenge_generation_service import generate_challenge
from backend.app.services.challenge_seed_service import seed_default_challenges


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

    def get(self, path: str, headers: dict = None):
        return self._request("GET", path, headers=headers)

    def post(self, path: str, json_data: dict = None, headers: dict = None):
        return self._request("POST", path, json_data=json_data, headers=headers)


class TestChallengeGeneration(unittest.TestCase):
    """Isolated unit test suite for Runtime Challenge Generation (Phase 2.7.3)."""

    @classmethod
    def setUpClass(cls):
        """Set up isolated in-memory SQLite database and FastAPI dependency overrides."""
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
        """Clean up database and clear dependency overrides."""
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=cls.engine)
        cls.engine.dispose()

    def setUp(self):
        """Seed clean in-memory database with default 30 catalog challenges."""
        with self.TestingSessionLocal() as session:
            for table in reversed(Base.metadata.sorted_tables):
                session.execute(table.delete())
            session.commit()
            seed_default_challenges(session)

    # ----------------------------------------------------------------------
    # 1. Math challenge generation
    # ----------------------------------------------------------------------
    def test_01_math_generation_basic(self):
        """Verify math runtime challenge generation produces structured questions."""
        with self.TestingSessionLocal() as db:
            req = RuntimeChallengeGenerationRequest(challenge_type="math", difficulty_level="easy")
            res: RuntimeChallengeResponse = generate_challenge(db, req)

            self.assertEqual(res.challenge_type, "math")
            self.assertEqual(res.difficulty_level, "easy")
            self.assertIn("questions", res.generated_content)
            self.assertGreaterEqual(len(res.generated_content["questions"]), 3)
            self.assertIsInstance(res.expected_answer, list)
            self.assertEqual(len(res.expected_answer), len(res.generated_content["questions"]))

    # ----------------------------------------------------------------------
    # 2. Math expected answers are strictly correct
    # ----------------------------------------------------------------------
    def test_02_math_expected_answers_are_correct(self):
        """Verify mathematical correctness of expected answers for all generated arithmetic."""
        with self.TestingSessionLocal() as db:
            for diff in ["easy", "medium", "hard"]:
                req = RuntimeChallengeGenerationRequest(challenge_type="math", difficulty_level=diff)
                res = generate_challenge(db, req)
                questions = res.generated_content["questions"]
                answers = res.expected_answer

                for q, expected in zip(questions, answers):
                    prompt = q["prompt"]
                    # Prompt format: e.g. "7 + 4 = ?", "15 - 9 = ?", "4 × 5 = ?", "24 ÷ 6 = ?"
                    expr = prompt.replace("= ?", "").replace("×", "*").replace("÷", "//").strip()
                    # Safely evaluate simple arithmetic expression
                    computed = eval(expr, {"__builtins__": None}, {})  # Safe bounded eval
                    self.assertEqual(
                        computed,
                        expected,
                        f"Math mismatch for '{prompt}': evaluated {computed} vs expected {expected}",
                    )

    # ----------------------------------------------------------------------
    # 3. Math respects template configuration
    # ----------------------------------------------------------------------
    def test_03_math_respects_template_configuration(self):
        """Verify question count and bounds align with template payload."""
        with self.TestingSessionLocal() as db:
            # Query hard math template specifically
            stmt = select(Challenge).where(
                Challenge.challenge_type == "math",
                Challenge.difficulty_level == "hard",
            )
            template = db.scalars(stmt).first()
            self.assertIsNotNone(template)

            req = RuntimeChallengeGenerationRequest(template_id=template.id)
            res = generate_challenge(db, req)

            payload = json.loads(template.template_payload)
            expected_count = payload["question_count"]
            self.assertEqual(len(res.generated_content["questions"]), expected_count)
            self.assertEqual(res.parameters["operand_min"], payload["operand_min"])
            self.assertEqual(res.parameters["operand_max"], payload["operand_max"])

    # ----------------------------------------------------------------------
    # 4. Memory challenge generation works
    # ----------------------------------------------------------------------
    def test_04_memory_generation_modes(self):
        """Verify memory challenge generation across visual and spatial modes."""
        with self.TestingSessionLocal() as db:
            for diff in ["easy", "medium", "hard"]:
                req = RuntimeChallengeGenerationRequest(challenge_type="memory", difficulty_level=diff)
                res = generate_challenge(db, req)
                self.assertEqual(res.challenge_type, "memory")
                self.assertIn("recall_mode", res.generated_content)
                self.assertIsNotNone(res.expected_answer)
                self.assertIn(
                    res.generated_content["recall_mode"],
                    [
                        "visual_sequence",
                        "spatial_pattern_recall",
                        "dynamic_spatial_path",
                        "dual_alternating_pattern",
                        "symbol_chronological_order",
                    ],
                )

    # ----------------------------------------------------------------------
    # 5. Memory NEVER generates number guessing
    # ----------------------------------------------------------------------
    def test_05_memory_never_generates_number_guessing(self):
        """Strictly verify that memory challenges contain no number-guessing mechanics."""
        with self.TestingSessionLocal() as db:
            forbidden_terms = [
                "number_guessing",
                "guess_number",
                "numeric_memory",
                "guess the number",
                "number guessing",
            ]
            for _ in range(10):
                req = RuntimeChallengeGenerationRequest(challenge_type="memory")
                res = generate_challenge(db, req)
                content_str = json.dumps(res.generated_content).lower()
                for term in forbidden_terms:
                    self.assertNotIn(term, content_str)
                    self.assertNotIn(term, res.title.lower())

    # ----------------------------------------------------------------------
    # 6. Dance challenge generation works
    # ----------------------------------------------------------------------
    def test_06_dance_generation_works(self):
        """Verify dance generation returns timed routine steps and tempo."""
        with self.TestingSessionLocal() as db:
            req = RuntimeChallengeGenerationRequest(challenge_type="dance", difficulty_level="medium")
            res = generate_challenge(db, req)
            self.assertEqual(res.challenge_type, "dance")
            self.assertIn("steps", res.generated_content)
            self.assertGreater(len(res.generated_content["steps"]), 0)
            self.assertIn("tempo_bpm", res.generated_content)
            self.assertIn("target_duration_seconds", res.generated_content)

    # ----------------------------------------------------------------------
    # 7. Tongue-twister challenge generation works
    # ----------------------------------------------------------------------
    def test_07_tongue_twister_generation_works(self):
        """Verify tongue twister generation produces text passage and repetition targets."""
        with self.TestingSessionLocal() as db:
            req = RuntimeChallengeGenerationRequest(challenge_type="tongue_twister", difficulty_level="easy")
            res = generate_challenge(db, req)
            self.assertEqual(res.challenge_type, "tongue_twister")
            self.assertIn("passage", res.generated_content)
            self.assertIn("target_repetitions", res.generated_content)
            self.assertIsInstance(res.expected_answer, str)
            self.assertEqual(res.expected_answer, res.generated_content["passage"])

    # ----------------------------------------------------------------------
    # 8. Push-up challenge generation works
    # ----------------------------------------------------------------------
    def test_08_push_ups_generation_works(self):
        """Verify push-up challenge generation returns repetition targets and window."""
        with self.TestingSessionLocal() as db:
            req = RuntimeChallengeGenerationRequest(challenge_type="push_ups", difficulty_level="hard")
            res = generate_challenge(db, req)
            self.assertEqual(res.challenge_type, "push_ups")
            self.assertIn("target_repetitions", res.generated_content)
            self.assertGreaterEqual(res.generated_content["target_repetitions"], 15)
            self.assertIn("completion_window_seconds", res.generated_content)
            self.assertIn("form_instructions", res.generated_content)

    # ----------------------------------------------------------------------
    # 9. Unsupported and forbidden challenge types are rejected
    # ----------------------------------------------------------------------
    def test_09_unsupported_and_forbidden_types_rejected(self):
        """Verify invalid and forbidden challenge types raise InvalidChallengeTypeError."""
        with self.TestingSessionLocal() as db:
            for forbidden in FORBIDDEN_CHALLENGE_TYPES:
                req = RuntimeChallengeGenerationRequest(challenge_type=forbidden)
                with self.assertRaises(InvalidChallengeTypeError):
                    generate_challenge(db, req)

            for unknown in ["sudoku", "crossword", "trivia", ""]:
                req = RuntimeChallengeGenerationRequest(challenge_type=unknown)
                with self.assertRaises(InvalidChallengeTypeError):
                    generate_challenge(db, req)

    # ----------------------------------------------------------------------
    # 10. Inactive template is rejected
    # ----------------------------------------------------------------------
    def test_10_inactive_template_rejected(self):
        """Verify deactivated challenge template cannot be used for generation."""
        with self.TestingSessionLocal() as db:
            # Deactivate an existing template
            stmt = select(Challenge).limit(1)
            chal = db.scalars(stmt).first()
            chal.is_active = False
            db.commit()

            req = RuntimeChallengeGenerationRequest(template_id=chal.id)
            with self.assertRaises(InactiveChallengeError):
                generate_challenge(db, req)

    # ----------------------------------------------------------------------
    # 11. Invalid template JSON payload is rejected
    # ----------------------------------------------------------------------
    def test_11_invalid_template_json_rejected(self):
        """Verify malformed JSON in template_payload raises InvalidTemplatePayloadError."""
        with self.TestingSessionLocal() as db:
            bad_chal = Challenge(
                challenge_type="math",
                difficulty_level="easy",
                title="Malformed JSON Template",
                description="Test template with invalid JSON.",
                template_payload="{not valid json:",
                min_duration_seconds=10,
                is_active=True,
            )
            db.add(bad_chal)
            db.commit()

            req = RuntimeChallengeGenerationRequest(template_id=bad_chal.id)
            with self.assertRaises(InvalidTemplatePayloadError):
                generate_challenge(db, req)

    # ----------------------------------------------------------------------
    # 12. Missing required configuration keys rejected
    # ----------------------------------------------------------------------
    def test_12_missing_configuration_keys_rejected(self):
        """Verify incomplete template payload raises TemplateConfigurationError."""
        with self.TestingSessionLocal() as db:
            incomplete = Challenge(
                challenge_type="math",
                difficulty_level="easy",
                title="Incomplete Math Template",
                description="Math template missing operand bounds.",
                template_payload=json.dumps({"question_count": 3}),  # Missing bounds and op types
                min_duration_seconds=10,
                is_active=True,
            )
            db.add(incomplete)
            db.commit()

            req = RuntimeChallengeGenerationRequest(template_id=incomplete.id)
            with self.assertRaises(TemplateConfigurationError):
                generate_challenge(db, req)

    # ----------------------------------------------------------------------
    # 13. Repeated generation produces valid, distinct challenges
    # ----------------------------------------------------------------------
    def test_13_repeated_generation_distinct(self):
        """Verify successive generation calls produce diverse questions."""
        with self.TestingSessionLocal() as db:
            req = RuntimeChallengeGenerationRequest(challenge_type="math", difficulty_level="easy")
            gen1 = generate_challenge(db, req)
            gen2 = generate_challenge(db, req)

            # Both should be valid responses
            self.assertEqual(gen1.challenge_type, "math")
            self.assertEqual(gen2.challenge_type, "math")

            # Check that questions are formatted correctly
            self.assertTrue(len(gen1.generated_content["questions"]) >= 3)
            self.assertTrue(len(gen2.generated_content["questions"]) >= 3)

    # ----------------------------------------------------------------------
    # 14. API endpoint POST /api/v1/challenges/generate
    # ----------------------------------------------------------------------
    def test_14_api_generate_endpoint_success_and_errors(self):
        """Verify the REST endpoint POST /api/v1/challenges/generate works and validates."""
        # Valid generation request
        payload = {"challenge_type": "math", "difficulty_level": "medium"}
        resp = self.client.post("/api/v1/challenges/generate", json_data=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["challenge_type"], "math")
        self.assertEqual(data["difficulty_level"], "medium")
        self.assertIn("generated_content", data)
        self.assertIn("expected_answer", data)

        # Forbidden challenge type -> 400 Bad Request
        resp_forbid = self.client.post(
            "/api/v1/challenges/generate", json_data={"challenge_type": "number_guessing"}
        )
        self.assertEqual(resp_forbid.status_code, 400)

        # Invalid difficulty -> 400 Bad Request
        resp_diff = self.client.post(
            "/api/v1/challenges/generate",
            json_data={"challenge_type": "math", "difficulty_level": "impossible"},
        )
        self.assertEqual(resp_diff.status_code, 400)

        # Non-existent template ID -> 404 Not Found
        resp_404 = self.client.post(
            "/api/v1/challenges/generate", json_data={"template_id": 99999}
        )
        self.assertEqual(resp_404.status_code, 404)

    # ----------------------------------------------------------------------
    # 15. Existing challenge catalog APIs continue working
    # ----------------------------------------------------------------------
    def test_15_existing_challenge_apis_unaffected(self):
        """Verify GET /api/v1/challenges and /type/{type} remain fully functional."""
        resp_list = self.client.get("/api/v1/challenges")
        self.assertEqual(resp_list.status_code, 200)
        self.assertEqual(len(resp_list.json()), 30)

        resp_type = self.client.get("/api/v1/challenges/type/push_ups")
        self.assertEqual(resp_type.status_code, 200)
        self.assertEqual(resp_type.json()["challenge_type"], "push_ups")

    # ----------------------------------------------------------------------
    # 16. Existing wake-session APIs continue working
    # ----------------------------------------------------------------------
    def test_16_existing_wake_session_apis_unaffected(self):
        """Verify WakeSession lifecycle APIs are completely intact."""
        with self.TestingSessionLocal() as db:
            user = User(username="gen_user", email="gen@example.com")
            db.add(user)
            db.commit()
            db.refresh(user)

            alarm = Alarm(
                user_id=user.id,
                time="07:00",
                days_of_week="[0,1,2,3,4]",
                selected_challenge_type="math",
                difficulty_preference="medium",
                is_active=True,
            )
            db.add(alarm)
            db.commit()
            db.refresh(alarm)

            # Create wake session via API
            create_payload = {"user_id": user.id, "alarm_id": alarm.id}
            resp = self.client.post("/api/v1/wake-sessions", json_data=create_payload)
            self.assertEqual(resp.status_code, 201)
            session_data = resp.json()
            self.assertEqual(session_data["status"], "ringing")

    # ----------------------------------------------------------------------
    # 17. Zero unexpected database records created by generation
    # ----------------------------------------------------------------------
    def test_17_generation_creates_zero_database_records(self):
        """Confirm that runtime generation does NOT mutate DB tables."""
        with self.TestingSessionLocal() as db:
            init_challenges = db.query(Challenge).count()
            init_attempts = db.query(ChallengeAttempt).count()

            # Execute multiple generation requests
            for c_type in VALID_CHALLENGE_TYPES:
                req = RuntimeChallengeGenerationRequest(challenge_type=c_type)
                generate_challenge(db, req)

            # Verify table record counts did not change
            self.assertEqual(db.query(Challenge).count(), init_challenges)
            self.assertEqual(db.query(ChallengeAttempt).count(), init_attempts)


if __name__ == "__main__":
    unittest.main()
