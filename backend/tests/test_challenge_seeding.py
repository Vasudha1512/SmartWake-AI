"""Automated test suite for Phase 2.7.2 Dedicated Challenge Seeding Mechanism.

Validates:
1. Initial seed inserts expected records (30 templates).
2. All five supported challenge types exist (dance, math, memory, tongue_twister, push_ups).
3. Easy/medium/hard difficulty tiers are represented for every challenge type.
4. Memory challenges are NOT number guessing (strictly visual/pattern/spatial recall).
5. All seeded records are active (is_active == True).
6. Seeding is strictly idempotent (running twice does not create duplicates).
7. Existing challenge records are preserved and never deleted.
8. Template payloads parse to valid JSON with structured parameters.
9. Challenge REST APIs return seeded records accurately.
"""
import asyncio
import json
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.constants import FORBIDDEN_CHALLENGE_TYPES, VALID_CHALLENGE_TYPES
from backend.app.database.base import Base
import backend.app.database.session  # Ensures pragma listeners
from backend.app.database.session import get_db
from backend.app.main import app
from backend.app.models.challenge import Challenge
from backend.app.services.challenge_seed_service import (
    DEFAULT_CHALLENGE_CATALOG,
    SeedResult,
    seed_default_challenges,
)
from backend.app.services.challenge_service import (
    get_challenge_by_id,
    get_challenge_by_type,
    list_active_challenge_types,
    list_active_challenges,
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


class TestChallengeSeeding(unittest.TestCase):
    """Isolated unit test suite for Challenge Catalog Seeding (Phase 2.7.2)."""

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
    # 1. Initial seed inserts expected records
    # ----------------------------------------------------------------------
    def test_01_initial_seed_inserts_expected_records(self):
        """Verify initial seeding inserts all 30 templates into an empty challenges table."""
        with self.TestingSessionLocal() as db:
            result: SeedResult = seed_default_challenges(db)
            self.assertEqual(result.inserted, 30)
            self.assertEqual(result.skipped, 0)
            self.assertEqual(result.total_catalog, 30)
            self.assertEqual(result.total_in_db, 30)

            # Query database directly to confirm row count
            count = len(list_active_challenges(db))
            self.assertEqual(count, 30)

    # ----------------------------------------------------------------------
    # 2. All five supported challenge types exist
    # ----------------------------------------------------------------------
    def test_02_all_five_supported_challenge_types_exist(self):
        """Verify all five canonical challenge types exist in the seeded catalog."""
        with self.TestingSessionLocal() as db:
            seed_default_challenges(db)
            seeded_types = set(list_active_challenge_types(db))
            self.assertEqual(seeded_types, VALID_CHALLENGE_TYPES)
            self.assertEqual(
                seeded_types,
                {"dance", "math", "memory", "tongue_twister", "push_ups"},
            )

    # ----------------------------------------------------------------------
    # 3. Easy, medium, and hard are represented for all 5 types
    # ----------------------------------------------------------------------
    def test_03_all_difficulties_represented_for_each_type(self):
        """Verify easy, medium, and hard difficulty levels exist for each challenge type."""
        expected_difficulties = {"easy", "medium", "hard"}
        with self.TestingSessionLocal() as db:
            seed_default_challenges(db)
            for c_type in VALID_CHALLENGE_TYPES:
                stmt = select(Challenge.difficulty_level).where(
                    Challenge.challenge_type == c_type
                )
                type_difficulties = set(db.scalars(stmt).all())
                self.assertEqual(
                    type_difficulties,
                    expected_difficulties,
                    f"Challenge type '{c_type}' is missing difficulty levels. Found: {type_difficulties}",
                )

                # Verify exactly 2 templates per difficulty level
                for diff in expected_difficulties:
                    diff_stmt = select(Challenge).where(
                        Challenge.challenge_type == c_type,
                        Challenge.difficulty_level == diff,
                    )
                    records = list(db.scalars(diff_stmt).all())
                    self.assertGreaterEqual(
                        len(records),
                        2,
                        f"Expected at least 2 templates for {c_type}/{diff}, got {len(records)}",
                    )

    # ----------------------------------------------------------------------
    # 4. Memory challenges are NOT number guessing
    # ----------------------------------------------------------------------
    def test_04_memory_challenges_are_not_number_guessing(self):
        """Strictly verify memory challenges use visual pattern recall, NOT number guessing."""
        with self.TestingSessionLocal() as db:
            seed_default_challenges(db)

            # Query all memory challenges
            stmt = select(Challenge).where(Challenge.challenge_type == "memory")
            memory_challenges = list(db.scalars(stmt).all())
            self.assertGreaterEqual(len(memory_challenges), 6)

            forbidden_terms = [
                "number_guessing",
                "guess_number",
                "numeric_memory",
                "guess the number",
                "number guessing",
            ]

            for chal in memory_challenges:
                # 1. Check title and description
                text_content = f"{chal.title} {chal.description}".lower()
                for term in forbidden_terms:
                    self.assertNotIn(
                        term,
                        text_content,
                        f"Memory challenge '{chal.title}' contains forbidden term '{term}'",
                    )

                # 2. Check payload JSON
                payload = json.loads(chal.template_payload)
                payload_str = json.dumps(payload).lower()
                for term in forbidden_terms:
                    self.assertNotIn(
                        term,
                        payload_str,
                        f"Memory challenge '{chal.title}' payload contains forbidden term '{term}'",
                    )

                # 3. Check memory concept adherence (visual/pattern/spatial)
                category = payload.get("category", "")
                recall_mode = payload.get("recall_mode", "")
                self.assertEqual(category, "visual_pattern")
                self.assertIn(
                    recall_mode,
                    [
                        "visual_sequence",
                        "spatial_pattern_recall",
                        "dynamic_spatial_path",
                        "dual_alternating_pattern",
                        "symbol_chronological_order",
                    ],
                )

    # ----------------------------------------------------------------------
    # 5. All seeded records are active
    # ----------------------------------------------------------------------
    def test_05_all_seeded_records_are_active(self):
        """Verify all seeded challenges have is_active == True."""
        with self.TestingSessionLocal() as db:
            seed_default_challenges(db)
            all_challenges = list(db.scalars(select(Challenge)).all())
            self.assertEqual(len(all_challenges), 30)
            for c in all_challenges:
                self.assertTrue(c.is_active, f"Challenge '{c.title}' is unexpectedly inactive")
                self.assertGreater(c.min_duration_seconds, 0)
                self.assertIsNotNone(c.created_at)

    # ----------------------------------------------------------------------
    # 6. Running seed twice does not create duplicates (Idempotency)
    # ----------------------------------------------------------------------
    def test_06_running_seed_twice_is_idempotent(self):
        """Verify subsequent seeding runs do not insert duplicates or increase record count."""
        with self.TestingSessionLocal() as db:
            # First run: inserts 30, skips 0
            res1 = seed_default_challenges(db)
            self.assertEqual(res1.inserted, 30)
            self.assertEqual(res1.skipped, 0)
            self.assertEqual(res1.total_in_db, 30)

            # Second run: inserts 0, skips 30
            res2 = seed_default_challenges(db)
            self.assertEqual(res2.inserted, 0)
            self.assertEqual(res2.skipped, 30)
            self.assertEqual(res2.total_in_db, 30)

            # Third run: still inserts 0, skips 30
            res3 = seed_default_challenges(db)
            self.assertEqual(res3.inserted, 0)
            self.assertEqual(res3.skipped, 30)
            self.assertEqual(res3.total_in_db, 30)

            # Verify total count in table is strictly 30
            count = len(list(db.scalars(select(Challenge)).all()))
            self.assertEqual(count, 30)

    # ----------------------------------------------------------------------
    # 7. Existing challenge records are not deleted
    # ----------------------------------------------------------------------
    def test_07_existing_challenge_records_are_preserved(self):
        """Verify that pre-existing custom challenge records are not deleted or overwritten."""
        with self.TestingSessionLocal() as db:
            # Insert a custom challenge beforehand
            custom = Challenge(
                challenge_type="math",
                difficulty_level="easy",
                title="Custom Pre-existing Math Problem",
                description="Custom user-defined math challenge.",
                template_payload=json.dumps({"custom": True}),
                min_duration_seconds=12,
                is_active=True,
            )
            db.add(custom)
            db.commit()
            db.refresh(custom)
            custom_id = custom.id

            # Now run the default seed
            result = seed_default_challenges(db)
            self.assertEqual(result.inserted, 30)
            self.assertEqual(result.total_in_db, 31)

            # Confirm custom challenge still exists and is untouched
            reloaded_custom = db.get(Challenge, custom_id)
            self.assertIsNotNone(reloaded_custom)
            self.assertEqual(reloaded_custom.title, "Custom Pre-existing Math Problem")

            # Run seed again: custom record + 30 default records remain untouched
            result2 = seed_default_challenges(db)
            self.assertEqual(result2.inserted, 0)
            self.assertEqual(result2.skipped, 30)
            self.assertEqual(result2.total_in_db, 31)

    # ----------------------------------------------------------------------
    # 8. Template payloads parse to valid JSON with structured parameters
    # ----------------------------------------------------------------------
    def test_08_all_template_payloads_are_valid_json(self):
        """Verify all template_payload entries are valid JSON with expected structural keys."""
        with self.TestingSessionLocal() as db:
            seed_default_challenges(db)
            all_challenges = list(db.scalars(select(Challenge)).all())
            self.assertEqual(len(all_challenges), 30)

            for c in all_challenges:
                try:
                    payload = json.loads(c.template_payload)
                except Exception as exc:
                    self.fail(f"Challenge '{c.title}' has invalid JSON payload: {exc}")

                self.assertIsInstance(payload, dict)
                self.assertIn("category", payload)
                self.assertIn("verification_mode", payload)

    # ----------------------------------------------------------------------
    # 9. Challenge REST APIs return seeded records accurately
    # ----------------------------------------------------------------------
    def test_09_api_endpoints_return_seeded_records(self):
        """Verify GET /api/v1/challenges and /type/{type} correctly return seeded records."""
        with self.TestingSessionLocal() as db:
            seed_default_challenges(db)

        # GET /api/v1/challenges
        resp = self.client.get("/api/v1/challenges")
        self.assertEqual(resp.status_code, 200)
        items = resp.json()
        self.assertEqual(len(items), 30)

        # Verify required schema fields in response
        first_item = items[0]
        self.assertIn("id", first_item)
        self.assertIn("challenge_type", first_item)
        self.assertIn("difficulty_level", first_item)
        self.assertIn("title", first_item)
        self.assertIn("template_payload", first_item)
        self.assertIn("min_duration_seconds", first_item)
        self.assertIn("is_active", first_item)

        # GET /api/v1/challenges/type/memory (no longer 404!)
        resp_mem = self.client.get("/api/v1/challenges/type/memory")
        self.assertEqual(resp_mem.status_code, 200)
        mem_data = resp_mem.json()
        self.assertEqual(mem_data["challenge_type"], "memory")
        self.assertTrue(mem_data["is_active"])

        # GET /api/v1/challenges/{id}
        first_id = first_item["id"]
        resp_id = self.client.get(f"/api/v1/challenges/{first_id}")
        self.assertEqual(resp_id.status_code, 200)
        id_data = resp_id.json()
        self.assertEqual(id_data["id"], first_id)
        self.assertEqual(id_data["title"], first_item["title"])

        # GET /api/v1/challenges/type/push_ups
        resp_push = self.client.get("/api/v1/challenges/type/push_ups")
        self.assertEqual(resp_push.status_code, 200)
        self.assertEqual(resp_push.json()["challenge_type"], "push_ups")


if __name__ == "__main__":
    unittest.main()
