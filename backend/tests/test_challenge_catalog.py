"""Automated test suite for Phase 2.7.1 Challenge System Foundation.

Validates that:
A. All five mandatory challenge types are represented correctly.
B. memory exists as a challenge type.
C. number_guessing does not exist (and forbidden types are strictly rejected).
D. Active challenge catalog retrieval works via service and API.
E. Get challenge by ID works via service and API.
F. Invalid challenge ID returns the standard 404 behavior.
G. Get challenge by type works via service and API.
H. Invalid challenge type returns 400 validation error; valid type without DB record returns 404.
I. Existing APIs remain unaffected.
J. Existing full test suite still passes.
"""
import asyncio
from datetime import datetime
import json
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.constants import FORBIDDEN_CHALLENGE_TYPES, VALID_CHALLENGE_TYPES
from backend.app.core.datetime_utils import now_utc_naive
from backend.app.core.exceptions import InvalidChallengeTypeError
from backend.app.database.base import Base
import backend.app.database.session  # Ensures pragma listeners
from backend.app.database.session import get_db
from backend.app.main import app
from backend.app.models.challenge import Challenge
from backend.app.services.challenge_service import (
    get_challenge_by_id,
    get_challenge_by_type,
    list_active_challenge_types,
    list_active_challenges,
    validate_challenge_type,
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

    def get(self, path: str, headers: dict = None):
        return self._request("GET", path, headers=headers)

    def post(self, path: str, json: dict = None, headers: dict = None):
        return self._request("POST", path, json_data=json, headers=headers)


class TestChallengeCatalog(unittest.TestCase):
    """Test suite for Challenge Catalog service and REST API (Phase 2.7.1)."""

    @classmethod
    def setUpClass(cls):
        """Set up isolated in-memory SQLite database and FastAPI client override."""
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
        """Clear database tables before each test for clean isolation."""
        with self.TestingSessionLocal() as session:
            for table in reversed(Base.metadata.sorted_tables):
                session.execute(table.delete())
            session.commit()

    # ----------------------------------------------------------------------
    # Requirement A: All five mandatory challenge types are represented
    # ----------------------------------------------------------------------
    def test_a_all_five_mandatory_challenge_types_represented(self):
        """Verify the five mandatory challenge types exist in canonical set."""
        expected = {"dance", "math", "memory", "tongue_twister", "push_ups"}
        self.assertEqual(VALID_CHALLENGE_TYPES, expected)
        for t in expected:
            validated = validate_challenge_type(t)
            self.assertEqual(validated, t)

    # ----------------------------------------------------------------------
    # Requirement B: memory exists as a challenge type
    # ----------------------------------------------------------------------
    def test_b_memory_exists_as_challenge_type(self):
        """Verify 'memory' is present and validated as an approved challenge type."""
        self.assertIn("memory", VALID_CHALLENGE_TYPES)
        self.assertEqual(validate_challenge_type("memory"), "memory")
        self.assertEqual(validate_challenge_type("  MEMORY  "), "memory")

    # ----------------------------------------------------------------------
    # Requirement C: number_guessing does not exist and is rejected
    # ----------------------------------------------------------------------
    def test_c_number_guessing_strictly_rejected(self):
        """Verify number guessing variants are explicitly forbidden."""
        self.assertNotIn("number_guessing", VALID_CHALLENGE_TYPES)
        self.assertNotIn("guess_number", VALID_CHALLENGE_TYPES)
        self.assertNotIn("numeric_memory", VALID_CHALLENGE_TYPES)

        for forbidden in ["number_guessing", "guess_number", "numeric_memory"]:
            with self.assertRaises(InvalidChallengeTypeError) as ctx:
                validate_challenge_type(forbidden)
            self.assertIn("strictly forbidden", str(ctx.exception))
            self.assertIn("number guessing", str(ctx.exception))

    # ----------------------------------------------------------------------
    # Requirement D: Active challenge catalog retrieval
    # ----------------------------------------------------------------------
    def test_d_active_challenge_catalog_retrieval(self):
        """Verify retrieving active challenges from empty DB and populated DB."""
        # 1. Empty database returns empty list
        with self.TestingSessionLocal() as db:
            active = list_active_challenges(db)
            self.assertEqual(active, [])

        resp_empty = self.client.get("/api/v1/challenges")
        self.assertEqual(resp_empty.status_code, 200)
        self.assertEqual(resp_empty.json(), [])

        # 2. Insert active and inactive records
        with self.TestingSessionLocal() as db:
            c1 = Challenge(
                challenge_type="math",
                difficulty_level="adaptive",
                title="Math Challenge",
                description="Solve arithmetic problems.",
                template_payload="{}",
                min_duration_seconds=10,
                is_active=True,
            )
            c2 = Challenge(
                challenge_type="dance",
                difficulty_level="adaptive",
                title="Dance Challenge",
                description="Follow motion routine.",
                template_payload="{}",
                min_duration_seconds=15,
                is_active=True,
            )
            c3_inactive = Challenge(
                challenge_type="push_ups",
                difficulty_level="adaptive",
                title="Inactive Push-ups",
                description="Disabled exercise.",
                template_payload="{}",
                min_duration_seconds=15,
                is_active=False,
            )
            db.add_all([c1, c2, c3_inactive])
            db.commit()

        # Service returns only active challenges (c1, c2)
        with self.TestingSessionLocal() as db:
            active_list = list_active_challenges(db)
            self.assertEqual(len(active_list), 2)
            types = [c.challenge_type for c in active_list]
            self.assertIn("math", types)
            self.assertIn("dance", types)
            self.assertNotIn("push_ups", types)

        # API returns only active challenges
        resp = self.client.get("/api/v1/challenges")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data), 2)
        resp_types = [item["challenge_type"] for item in data]
        self.assertIn("math", resp_types)
        self.assertIn("dance", resp_types)
        self.assertNotIn("push_ups", resp_types)

    # ----------------------------------------------------------------------
    # Requirement E: Get challenge by ID works
    # ----------------------------------------------------------------------
    def test_e_get_challenge_by_id_works(self):
        """Verify retrieving an individual challenge by primary key ID."""
        with self.TestingSessionLocal() as db:
            c = Challenge(
                challenge_type="tongue_twister",
                difficulty_level="adaptive",
                title="Tongue Twister Articulation",
                description="Phonetic friction sentences.",
                template_payload="{}",
                min_duration_seconds=10,
                is_active=True,
            )
            db.add(c)
            db.commit()
            db.refresh(c)
            challenge_id = c.id

        # Service level
        with self.TestingSessionLocal() as db:
            fetched = get_challenge_by_id(db, challenge_id)
            self.assertIsNotNone(fetched)
            self.assertEqual(fetched.challenge_type, "tongue_twister")
            self.assertEqual(fetched.title, "Tongue Twister Articulation")

        # API level
        resp = self.client.get(f"/api/v1/challenges/{challenge_id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["id"], challenge_id)
        self.assertEqual(data["challenge_type"], "tongue_twister")
        self.assertEqual(data["title"], "Tongue Twister Articulation")
        self.assertEqual(data["min_duration_seconds"], 10)
        self.assertTrue(data["is_active"])

    # ----------------------------------------------------------------------
    # Requirement F: Invalid challenge ID returns 404
    # ----------------------------------------------------------------------
    def test_f_invalid_challenge_id_returns_404(self):
        """Verify requesting a non-existent challenge ID returns 404 Not Found."""
        with self.TestingSessionLocal() as db:
            self.assertIsNone(get_challenge_by_id(db, 99999))

        resp = self.client.get("/api/v1/challenges/99999")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("not found", resp.json()["detail"].lower())

    # ----------------------------------------------------------------------
    # Requirement G: Get challenge by type works
    # ----------------------------------------------------------------------
    def test_g_get_challenge_by_type_works(self):
        """Verify retrieving an active challenge by challenge type."""
        with self.TestingSessionLocal() as db:
            c = Challenge(
                challenge_type="memory",
                difficulty_level="adaptive",
                title="Visual Memory Pattern",
                description="Visual sequence recall task (strictly non-number guessing).",
                template_payload="{}",
                min_duration_seconds=10,
                is_active=True,
            )
            db.add(c)
            db.commit()
            db.refresh(c)
            expected_id = c.id

        # Service level
        with self.TestingSessionLocal() as db:
            fetched = get_challenge_by_type(db, "memory")
            self.assertIsNotNone(fetched)
            self.assertEqual(fetched.id, expected_id)
            self.assertEqual(fetched.challenge_type, "memory")

        # API level
        resp = self.client.get("/api/v1/challenges/type/memory")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["id"], expected_id)
        self.assertEqual(data["challenge_type"], "memory")
        self.assertEqual(data["title"], "Visual Memory Pattern")

    # ----------------------------------------------------------------------
    # Requirement H: Invalid challenge type returns validation / 404 error
    # ----------------------------------------------------------------------
    def test_h_invalid_challenge_type_behavior(self):
        """Verify invalid/forbidden type returns 400; valid type without DB row returns 404."""
        # 1. Forbidden number_guessing returns 400
        resp_forbidden = self.client.get("/api/v1/challenges/type/number_guessing")
        self.assertEqual(resp_forbidden.status_code, 400)
        self.assertIn("strictly forbidden", resp_forbidden.json()["detail"].lower())

        # 2. Unknown challenge type returns 400
        resp_unknown = self.client.get("/api/v1/challenges/type/chess")
        self.assertEqual(resp_unknown.status_code, 400)
        self.assertIn("invalid challenge type", resp_unknown.json()["detail"].lower())

        # 3. Valid challenge type without a database record returns 404
        resp_not_seeded = self.client.get("/api/v1/challenges/type/dance")
        self.assertEqual(resp_not_seeded.status_code, 404)
        self.assertIn("not found", resp_not_seeded.json()["detail"].lower())

    # ----------------------------------------------------------------------
    # Requirement I: Existing APIs remain unaffected
    # ----------------------------------------------------------------------
    def test_i_existing_apis_remain_unaffected(self):
        """Verify /health and root endpoints remain operational."""
        resp_root = self.client.get("/")
        self.assertEqual(resp_root.status_code, 200)
        self.assertEqual(resp_root.json()["status"], "healthy")

        resp_health = self.client.get("/health")
        self.assertEqual(resp_health.status_code, 200)
        self.assertEqual(resp_health.json()["status"], "healthy")


if __name__ == "__main__":
    unittest.main()
