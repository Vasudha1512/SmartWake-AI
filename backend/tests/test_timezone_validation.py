"""Automated test suite for IANA timezone validation in SmartWake AI.

Validates that:
A. Creating a user with timezone = 'Asia/Kolkata' succeeds.
B. Creating a user with timezone = 'UTC' succeeds.
C. Creating a user with timezone = 'America/New_York' succeeds.
D. Creating a user with an invalid timezone (e.g. 'invalid_timezone', 'Mumbai', 'India', '') fails with 422 / InvalidTimezoneError.
E. Creating a user without specifying timezone preserves the existing 'UTC' default.
F. Existing user and alarm API endpoints continue to work as expected.
Both service-level and API-level validation paths are tested.
"""
import asyncio
import json
import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.exceptions import InvalidTimezoneError
from backend.app.database.base import Base
import backend.app.database.session  # Ensures SQLite pragma listener is registered
from backend.app.database.session import get_db
from backend.app.main import app
import backend.app.models
from backend.app.services import user_service


class SimpleASGIClient:
    """Lightweight ASGI test client using Python standard library asyncio."""

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


class TestTimezoneValidation(unittest.TestCase):
    """Test suite for IANA timezone validation at both service and API levels."""

    @classmethod
    def setUpClass(cls):
        """Set up isolated in-memory SQLite database and FastAPI dependency override."""
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

    # --- Service-Level Tests ---

    def test_service_valid_timezones(self):
        """Verify service layer accepts valid IANA timezone identifiers."""
        with self.TestingSessionLocal() as db:
            u1 = user_service.create_user(db, username="u_kolkata", timezone="Asia/Kolkata")
            self.assertEqual(u1.timezone, "Asia/Kolkata")

            u2 = user_service.create_user(db, username="u_utc", timezone="UTC")
            self.assertEqual(u2.timezone, "UTC")

            u3 = user_service.create_user(db, username="u_ny", timezone="America/New_York")
            self.assertEqual(u3.timezone, "America/New_York")

            u4 = user_service.create_user(db, username="u_dubai", timezone="Asia/Dubai")
            self.assertEqual(u4.timezone, "Asia/Dubai")

            u5 = user_service.create_user(db, username="u_london", timezone="Europe/London")
            self.assertEqual(u5.timezone, "Europe/London")

    def test_service_default_timezone_when_none(self):
        """Verify service layer defaults to 'UTC' when timezone is None."""
        with self.TestingSessionLocal() as db:
            u = user_service.create_user(db, username="u_default", timezone=None)
            self.assertEqual(u.timezone, "UTC")

    def test_service_invalid_timezones_raise_exception(self):
        """Verify service layer raises InvalidTimezoneError for invalid timezone strings."""
        invalid_timezones = ["invalid_timezone", "Mumbai", "India", "random", "", "   "]
        with self.TestingSessionLocal() as db:
            for inv_tz in invalid_timezones:
                with self.subTest(timezone=inv_tz):
                    with self.assertRaises(InvalidTimezoneError):
                        user_service.create_user(db, username=f"user_{inv_tz[:5]}", timezone=inv_tz)

    # --- API-Level Tests ---

    def test_api_create_user_asia_kolkata(self):
        """Requirement A: Creating a user with timezone = 'Asia/Kolkata' succeeds."""
        payload = {"username": "kolkata_user", "timezone": "Asia/Kolkata"}
        resp = self.client.post("/api/v1/users", json=payload)
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["timezone"], "Asia/Kolkata")
        self.assertEqual(data["username"], "kolkata_user")

    def test_api_create_user_utc(self):
        """Requirement B: Creating a user with timezone = 'UTC' succeeds."""
        payload = {"username": "utc_user", "timezone": "UTC"}
        resp = self.client.post("/api/v1/users", json=payload)
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["timezone"], "UTC")
        self.assertEqual(data["username"], "utc_user")

    def test_api_create_user_america_new_york(self):
        """Requirement C: Creating a user with timezone = 'America/New_York' succeeds."""
        payload = {"username": "ny_user", "timezone": "America/New_York"}
        resp = self.client.post("/api/v1/users", json=payload)
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["timezone"], "America/New_York")
        self.assertEqual(data["username"], "ny_user")

    def test_api_create_user_invalid_timezone_fails(self):
        """Requirement D: Creating a user with an invalid timezone fails with HTTP 422."""
        invalid_timezones = ["invalid_timezone", "Mumbai", "India", "random", ""]
        for idx, inv_tz in enumerate(invalid_timezones):
            with self.subTest(invalid_tz=inv_tz):
                payload = {"username": f"bad_tz_user_{idx}", "timezone": inv_tz}
                resp = self.client.post("/api/v1/users", json=payload)
                self.assertEqual(resp.status_code, 422, f"Expected 422 for timezone: '{inv_tz}'")

    def test_api_create_user_without_specifying_timezone_uses_utc(self):
        """Requirement E: Creating a user without specifying timezone uses UTC default."""
        payload = {"username": "default_tz_user"}
        resp = self.client.post("/api/v1/users", json=payload)
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["timezone"], "UTC")

    def test_api_retrieve_user_preserves_validated_timezone(self):
        """Requirement F: Retrieving a created user returns the validated timezone."""
        create_resp = self.client.post(
            "/api/v1/users",
            json={"username": "profile_check", "timezone": "Asia/Kolkata"},
        )
        self.assertEqual(create_resp.status_code, 201)
        user_id = create_resp.json()["id"]

        get_resp = self.client.get(f"/api/v1/users/{user_id}")
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(get_resp.json()["timezone"], "Asia/Kolkata")


if __name__ == "__main__":
    unittest.main()
