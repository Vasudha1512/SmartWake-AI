"""Integration tests for SmartWake AI User and Alarm API endpoints.

Uses an isolated in-memory SQLite database (sqlite:///:memory:) with FastAPI's
dependency_overrides to ensure the development database (smartwake.db) is never touched.
Employs standard library ASGI dispatch so external dependencies like httpx are not required.
"""
import asyncio
import json
import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.database.base import Base
import backend.app.models  # Ensure all SQLAlchemy models are registered
from backend.app.database.session import get_db
from backend.app.main import app


class SimpleASGIClient:
    """Lightweight ASGI test client using Python asyncio and standard library.

    Provides get, post, put, delete methods returning a simple Response object.
    """

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

    def put(self, path: str, json: dict = None, headers: dict = None):
        return self._request("PUT", path, json_data=json, headers=headers)

    def patch(self, path: str, json: dict = None, headers: dict = None):
        return self._request("PATCH", path, json_data=json, headers=headers)

    def delete(self, path: str, headers: dict = None):
        return self._request("DELETE", path, headers=headers)


class TestApiEndpoints(unittest.TestCase):
    """Integration test suite for SmartWake AI User and Alarm API endpoints."""

    @classmethod
    def setUpClass(cls):
        """Configure an isolated in-memory database and override get_db dependency."""
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
        """Clean up in-memory database tables and remove dependency overrides."""
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=cls.engine)
        cls.engine.dispose()

    def setUp(self):
        """Clear database tables before each test for clean isolation."""
        with self.TestingSessionLocal() as session:
            for table in reversed(Base.metadata.sorted_tables):
                session.execute(table.delete())
            session.commit()

    # --- Health & Root Endpoints ---

    def test_root_endpoint(self):
        """Verify root endpoint returns 200 with service information."""
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "healthy")
        self.assertIn("service", data)

    def test_health_endpoints(self):
        """Verify /health and /api/v1/health endpoints return 200 OK."""
        resp1 = self.client.get("/health")
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp1.json().get("status"), "healthy")

        resp2 = self.client.get("/api/v1/health")
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2.json().get("status"), "healthy")

    # --- User Endpoints ---

    def test_create_user_success(self):
        """Verify successful user creation returns 201 with persisted fields."""
        payload = {
            "username": "alex",
            "email": "alex@example.com",
            "timezone": "America/New_York",
        }
        resp = self.client.post("/api/v1/users", json=payload)
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertIn("id", data)
        self.assertEqual(data["username"], "alex")
        self.assertEqual(data["email"], "alex@example.com")
        self.assertEqual(data["timezone"], "America/New_York")
        self.assertIn("created_at", data)
        self.assertIn("updated_at", data)

    def test_create_user_duplicate_username(self):
        """Verify creating a user with a duplicate username returns 400 Bad Request."""
        payload = {"username": "duplicate_user"}
        resp1 = self.client.post("/api/v1/users", json=payload)
        self.assertEqual(resp1.status_code, 201)

        resp2 = self.client.post("/api/v1/users", json=payload)
        self.assertEqual(resp2.status_code, 400)
        self.assertIn("already exists", resp2.json()["detail"].lower())

    def test_create_user_missing_username(self):
        """Verify creating a user without username returns 422 Unprocessable Entity."""
        resp = self.client.post("/api/v1/users", json={})
        self.assertEqual(resp.status_code, 422)

    def test_get_user_success(self):
        """Verify retrieving an existing user by ID returns 200 with user data."""
        create_resp = self.client.post("/api/v1/users", json={"username": "sarah"})
        user_id = create_resp.json()["id"]

        resp = self.client.get(f"/api/v1/users/{user_id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["id"], user_id)
        self.assertEqual(data["username"], "sarah")

    def test_get_user_not_found(self):
        """Verify retrieving a non-existent user returns 404 Not Found."""
        resp = self.client.get("/api/v1/users/99999")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("not found", resp.json()["detail"].lower())

    # --- Alarm Endpoints ---

    def test_create_alarm_success(self):
        """Verify alarm creation preserves user's time, challenge type, and difficulty."""
        u_resp = self.client.post("/api/v1/users", json={"username": "alarm_tester"})
        user_id = u_resp.json()["id"]

        alarm_payload = {
            "user_id": user_id,
            "time": "06:45",
            "selected_challenge_type": "tongue_twister",
            "difficulty_preference": "medium",
            "label": "Workday Wakeup",
            "days_of_week": [0, 1, 2, 3, 4],
            "is_active": True,
        }
        resp = self.client.post("/api/v1/alarms", json=alarm_payload)
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertIn("id", data)
        self.assertEqual(data["user_id"], user_id)
        # Verify preservation of user choices
        self.assertEqual(data["time"], "06:45")
        self.assertEqual(data["selected_challenge_type"], "tongue_twister")
        self.assertEqual(data["difficulty_preference"], "medium")
        self.assertEqual(data["label"], "Workday Wakeup")
        self.assertTrue(data["is_active"])

    def test_create_alarm_all_approved_challenge_types(self):
        """Verify all 5 approved wake-up challenge types are accepted."""
        u_resp = self.client.post("/api/v1/users", json={"username": "challenge_user"})
        user_id = u_resp.json()["id"]

        approved_types = ["dance", "math", "memory", "tongue_twister", "push_ups"]
        for ctype in approved_types:
            payload = {
                "user_id": user_id,
                "time": "07:00",
                "selected_challenge_type": ctype,
                "difficulty_preference": "adaptive",
            }
            resp = self.client.post("/api/v1/alarms", json=payload)
            self.assertEqual(resp.status_code, 201, f"Failed for challenge type: {ctype}")
            self.assertEqual(resp.json()["selected_challenge_type"], ctype)

    def test_create_alarm_all_approved_difficulties(self):
        """Verify all 4 approved difficulty settings are accepted."""
        u_resp = self.client.post("/api/v1/users", json={"username": "diff_user"})
        user_id = u_resp.json()["id"]

        approved_diffs = ["easy", "medium", "hard", "adaptive"]
        for diff in approved_diffs:
            payload = {
                "user_id": user_id,
                "time": "07:30",
                "selected_challenge_type": "math",
                "difficulty_preference": diff,
            }
            resp = self.client.post("/api/v1/alarms", json=payload)
            self.assertEqual(resp.status_code, 201, f"Failed for difficulty: {diff}")
            self.assertEqual(resp.json()["difficulty_preference"], diff)

    def test_create_alarm_invalid_user(self):
        """Verify creating an alarm for a non-existent user returns 404."""
        payload = {
            "user_id": 99999,
            "time": "08:00",
            "selected_challenge_type": "math",
            "difficulty_preference": "easy",
        }
        resp = self.client.post("/api/v1/alarms", json=payload)
        self.assertEqual(resp.status_code, 404)
        self.assertIn("does not exist", resp.json()["detail"])

    def test_create_alarm_invalid_challenge_type(self):
        """Verify creating an alarm with an unsupported challenge type returns 422."""
        u_resp = self.client.post("/api/v1/users", json={"username": "test_invalid_type"})
        user_id = u_resp.json()["id"]

        payload = {
            "user_id": user_id,
            "time": "07:00",
            "selected_challenge_type": "number_guessing",  # Explicitly forbidden
            "difficulty_preference": "easy",
        }
        resp = self.client.post("/api/v1/alarms", json=payload)
        self.assertEqual(resp.status_code, 422)
        self.assertIn("invalid challenge type", resp.json()["detail"].lower())

    def test_create_alarm_invalid_difficulty(self):
        """Verify creating an alarm with an unsupported difficulty returns 422."""
        u_resp = self.client.post("/api/v1/users", json={"username": "test_invalid_diff"})
        user_id = u_resp.json()["id"]

        payload = {
            "user_id": user_id,
            "time": "07:00",
            "selected_challenge_type": "math",
            "difficulty_preference": "impossible",
        }
        resp = self.client.post("/api/v1/alarms", json=payload)
        self.assertEqual(resp.status_code, 422)
        self.assertIn("invalid difficulty preference", resp.json()["detail"].lower())

    def test_create_alarm_invalid_time_format(self):
        """Verify creating an alarm with an invalid time format returns 422."""
        u_resp = self.client.post("/api/v1/users", json={"username": "test_invalid_time"})
        user_id = u_resp.json()["id"]

        for invalid_time in ["25:00", "7:00", "12:60", "morning", ""]:
            payload = {
                "user_id": user_id,
                "time": invalid_time,
                "selected_challenge_type": "math",
                "difficulty_preference": "easy",
            }
            resp = self.client.post("/api/v1/alarms", json=payload)
            self.assertEqual(resp.status_code, 422, f"Expected 422 for time: '{invalid_time}'")

    def test_create_alarm_missing_required_fields(self):
        """Verify creating an alarm without required fields returns 422."""
        resp = self.client.post("/api/v1/alarms", json={})
        self.assertEqual(resp.status_code, 422)

    def test_get_alarm_success(self):
        """Verify retrieving an alarm by ID returns 200 with persisted details."""
        u_resp = self.client.post("/api/v1/users", json={"username": "alarm_getter"})
        user_id = u_resp.json()["id"]

        create_resp = self.client.post(
            "/api/v1/alarms",
            json={
                "user_id": user_id,
                "time": "06:15",
                "selected_challenge_type": "memory",
                "difficulty_preference": "adaptive",
                "label": "Morning Brain",
            },
        )
        alarm_id = create_resp.json()["id"]

        resp = self.client.get(f"/api/v1/alarms/{alarm_id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["id"], alarm_id)
        self.assertEqual(data["time"], "06:15")
        self.assertEqual(data["selected_challenge_type"], "memory")
        self.assertEqual(data["difficulty_preference"], "adaptive")

    def test_get_alarm_not_found(self):
        """Verify retrieving a non-existent alarm returns 404."""
        resp = self.client.get("/api/v1/alarms/99999")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("not found", resp.json()["detail"].lower())

    def test_get_user_alarms_success(self):
        """Verify retrieving all alarms for a specific user returns 200 with list."""
        u_resp = self.client.post("/api/v1/users", json={"username": "multi_alarm_user"})
        user_id = u_resp.json()["id"]

        # Create two alarms for this user
        self.client.post(
            "/api/v1/alarms",
            json={
                "user_id": user_id,
                "time": "06:00",
                "selected_challenge_type": "push_ups",
                "difficulty_preference": "hard",
            },
        )
        self.client.post(
            "/api/v1/alarms",
            json={
                "user_id": user_id,
                "time": "08:00",
                "selected_challenge_type": "math",
                "difficulty_preference": "easy",
            },
        )

        resp = self.client.get(f"/api/v1/users/{user_id}/alarms")
        self.assertEqual(resp.status_code, 200)
        alarms = resp.json()
        self.assertEqual(len(alarms), 2)
        self.assertEqual(alarms[0]["time"], "06:00")
        self.assertEqual(alarms[1]["time"], "08:00")

    def test_get_user_alarms_user_not_found(self):
        """Verify retrieving alarms for a non-existent user returns 404."""
        resp = self.client.get("/api/v1/users/99999/alarms")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("not found", resp.json()["detail"].lower())

    def test_update_alarm_success(self):
        """Verify updating an alarm modifies configuration fields correctly."""
        u_resp = self.client.post("/api/v1/users", json={"username": "updater"})
        user_id = u_resp.json()["id"]

        create_resp = self.client.post(
            "/api/v1/alarms",
            json={
                "user_id": user_id,
                "time": "07:00",
                "selected_challenge_type": "math",
                "difficulty_preference": "easy",
                "label": "Original",
            },
        )
        alarm_id = create_resp.json()["id"]

        update_payload = {
            "time": "07:45",
            "selected_challenge_type": "dance",
            "difficulty_preference": "hard",
            "label": "Dance Wakeup",
            "is_active": False,
        }
        resp = self.client.put(f"/api/v1/alarms/{alarm_id}", json=update_payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["time"], "07:45")
        self.assertEqual(data["selected_challenge_type"], "dance")
        self.assertEqual(data["difficulty_preference"], "hard")
        self.assertEqual(data["label"], "Dance Wakeup")
        self.assertFalse(data["is_active"])

    def test_update_alarm_does_not_change_user_id(self):
        """Verify update cannot alter the owning user_id."""
        u_resp = self.client.post("/api/v1/users", json={"username": "orig_owner"})
        user_id = u_resp.json()["id"]

        create_resp = self.client.post(
            "/api/v1/alarms",
            json={
                "user_id": user_id,
                "time": "07:00",
                "selected_challenge_type": "math",
                "difficulty_preference": "easy",
            },
        )
        alarm_id = create_resp.json()["id"]

        # Attempt to pass a different user_id
        update_payload = {"user_id": 99999, "time": "07:30"}
        resp = self.client.put(f"/api/v1/alarms/{alarm_id}", json=update_payload)
        self.assertEqual(resp.status_code, 200)
        # user_id must remain the original
        self.assertEqual(resp.json()["user_id"], user_id)

    def test_update_alarm_invalid_fields(self):
        """Verify updating an alarm with invalid inputs returns 422."""
        u_resp = self.client.post("/api/v1/users", json={"username": "update_validator"})
        user_id = u_resp.json()["id"]

        create_resp = self.client.post(
            "/api/v1/alarms",
            json={
                "user_id": user_id,
                "time": "07:00",
                "selected_challenge_type": "math",
                "difficulty_preference": "easy",
            },
        )
        alarm_id = create_resp.json()["id"]

        # Invalid time
        resp1 = self.client.put(f"/api/v1/alarms/{alarm_id}", json={"time": "invalid_time"})
        self.assertEqual(resp1.status_code, 422)

        # Invalid challenge type
        resp2 = self.client.put(f"/api/v1/alarms/{alarm_id}", json={"selected_challenge_type": "magic"})
        self.assertEqual(resp2.status_code, 422)

        # Invalid difficulty
        resp3 = self.client.put(f"/api/v1/alarms/{alarm_id}", json={"difficulty_preference": "godmode"})
        self.assertEqual(resp3.status_code, 422)

    def test_update_alarm_not_found(self):
        """Verify updating a non-existent alarm returns 404."""
        resp = self.client.put("/api/v1/alarms/99999", json={"time": "08:00"})
        self.assertEqual(resp.status_code, 404)
        self.assertIn("not found", resp.json()["detail"].lower())

    def test_delete_alarm_success(self):
        """Verify deleting an alarm deactivates it (is_active=False) while preserving the record."""
        u_resp = self.client.post("/api/v1/users", json={"username": "delete_tester"})
        user_id = u_resp.json()["id"]

        create_resp = self.client.post(
            "/api/v1/alarms",
            json={
                "user_id": user_id,
                "time": "09:00",
                "selected_challenge_type": "math",
                "difficulty_preference": "easy",
            },
        )
        alarm_id = create_resp.json()["id"]

        del_resp = self.client.delete(f"/api/v1/alarms/{alarm_id}")
        self.assertEqual(del_resp.status_code, 200)

        # Confirm the record still exists and is deactivated (is_active == False)
        get_resp = self.client.get(f"/api/v1/alarms/{alarm_id}")
        self.assertEqual(get_resp.status_code, 200)
        self.assertFalse(get_resp.json()["is_active"])

    def test_delete_alarm_not_found(self):
        """Verify deleting a non-existent alarm returns 404."""
        resp = self.client.delete("/api/v1/alarms/99999")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("not found", resp.json()["detail"].lower())


if __name__ == "__main__":
    unittest.main()
