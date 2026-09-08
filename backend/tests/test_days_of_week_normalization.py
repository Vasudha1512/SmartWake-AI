"""Automated test suite for days_of_week normalization and validation in SmartWake AI.

Validates that:
A. Default days_of_week is preserved ([0, 1, 2, 3, 4]).
B. Valid Monday-Friday input [0, 1, 2, 3, 4] creates successfully.
C. Valid weekend [5, 6] creates successfully.
D. All seven days [0, 1, 2, 3, 4, 5, 6] creates successfully.
E. Unordered valid input is normalized by sorting: [4, 2, 0, 3] -> [0, 2, 3, 4].
F. Duplicate values are rejected (e.g. [1, 1, 2]).
G. Negative day values are rejected (e.g. [-1, 0, 1]).
H. Values greater than 6 are rejected (e.g. [0, 7], [0, 99]).
I. String values are rejected (e.g. [0, 'monday'], ['0', '1']).
J. Empty list is rejected ([]).
K. Invalid serialized strings are rejected in the service layer.
L. GET alarm endpoint returns List[int], not a serialized JSON string.
M. PUT alarm endpoint correctly updates days_of_week.
N. User alarm listing (GET /api/v1/users/{id}/alarms) returns List[int].
O. Existing alarm validation behavior is maintained.
"""
import asyncio
import json
import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.exceptions import InvalidDaysOfWeekError
from backend.app.database.base import Base
import backend.app.database.session  # Ensures SQLite connection event listener is active
from backend.app.database.session import get_db
from backend.app.main import app
import backend.app.models
from backend.app.services import alarm_service, user_service


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

    def put(self, path: str, json: dict = None, headers: dict = None):
        return self._request("PUT", path, json_data=json, headers=headers)


class TestDaysOfWeekNormalization(unittest.TestCase):
    """Test suite covering days_of_week normalization, validation, and serialization."""

    @classmethod
    def setUpClass(cls):
        """Set up an isolated in-memory SQLite database and FastAPI dependency override."""
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

        # Create a test user for alarm associations
        with self.TestingSessionLocal() as session:
            user = user_service.create_user(session, username="day_tester", timezone="UTC")
            self.user_id = user.id

    # --- Service-Level Validation Tests ---

    def test_service_validate_days_of_week_default(self):
        """Requirement A: Default days_of_week is preserved as [0, 1, 2, 3, 4]."""
        result = alarm_service.validate_days_of_week(None)
        self.assertEqual(result, [0, 1, 2, 3, 4])

    def test_service_validate_days_of_week_sorting(self):
        """Requirement E: Unordered input is normalized by sorting."""
        result = alarm_service.validate_days_of_week([4, 2, 0, 3])
        self.assertEqual(result, [0, 2, 3, 4])

    def test_service_validate_days_of_week_rejections(self):
        """Requirements F, G, H, I, J, K: Service layer strictly rejects invalid inputs."""
        invalid_inputs = [
            ([1, 1, 2], "duplicate values"),
            ([-1, 0, 1], "negative value"),
            ([0, 7], "value > 6"),
            ([0, 99], "value > 6"),
            ([0, "monday"], "string element"),
            (["0", "1"], "string numbers"),
            ([], "empty list"),
            ([True, False], "boolean elements"),
            ("invalid_json", "corrupt json string"),
            ("not a list", "non-list json"),
            ([0, 1, 2, 3, 4, 5, 6, 7], "more than 7 items"),
        ]
        for inv_input, reason in invalid_inputs:
            with self.subTest(input=inv_input, reason=reason):
                with self.assertRaises(InvalidDaysOfWeekError):
                    alarm_service.validate_days_of_week(inv_input)

    # --- API-Level Integration Tests ---

    def test_api_create_alarm_default_days_of_week(self):
        """Requirement A: Creating an alarm without days_of_week defaults to [0, 1, 2, 3, 4]."""
        payload = {
            "user_id": self.user_id,
            "time": "07:00",
            "selected_challenge_type": "math",
            "difficulty_preference": "adaptive",
        }
        resp = self.client.post("/api/v1/alarms", json=payload)
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["days_of_week"], [0, 1, 2, 3, 4])
        self.assertIsInstance(data["days_of_week"], list)

    def test_api_create_alarm_valid_monday_friday(self):
        """Requirement B: Valid Monday-Friday input [0, 1, 2, 3, 4] creates successfully."""
        payload = {
            "user_id": self.user_id,
            "time": "06:30",
            "selected_challenge_type": "dance",
            "difficulty_preference": "easy",
            "days_of_week": [0, 1, 2, 3, 4],
        }
        resp = self.client.post("/api/v1/alarms", json=payload)
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["days_of_week"], [0, 1, 2, 3, 4])

    def test_api_create_alarm_valid_weekend(self):
        """Requirement C: Valid weekend input [5, 6] creates successfully."""
        payload = {
            "user_id": self.user_id,
            "time": "09:00",
            "selected_challenge_type": "memory",
            "difficulty_preference": "medium",
            "days_of_week": [5, 6],
        }
        resp = self.client.post("/api/v1/alarms", json=payload)
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["days_of_week"], [5, 6])

    def test_api_create_alarm_all_seven_days(self):
        """Requirement D: All seven days [0, 1, 2, 3, 4, 5, 6] creates successfully."""
        payload = {
            "user_id": self.user_id,
            "time": "06:00",
            "selected_challenge_type": "push_ups",
            "difficulty_preference": "hard",
            "days_of_week": [0, 1, 2, 3, 4, 5, 6],
        }
        resp = self.client.post("/api/v1/alarms", json=payload)
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["days_of_week"], [0, 1, 2, 3, 4, 5, 6])

    def test_api_create_alarm_unordered_normalized(self):
        """Requirement E: Unordered input [4, 2, 0, 3] is normalized to [0, 2, 3, 4]."""
        payload = {
            "user_id": self.user_id,
            "time": "07:15",
            "selected_challenge_type": "tongue_twister",
            "difficulty_preference": "adaptive",
            "days_of_week": [4, 2, 0, 3],
        }
        resp = self.client.post("/api/v1/alarms", json=payload)
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["days_of_week"], [0, 2, 3, 4])

    def test_api_create_alarm_invalid_days_of_week_rejected(self):
        """Requirements F-J: Invalid days_of_week arrays are rejected with HTTP 422."""
        invalid_payloads = [
            ([1, 1, 2], "duplicates"),
            ([-1, 0, 1], "negative value"),
            ([0, 7], "value > 6"),
            ([0, 99], "value > 6"),
            ([0, "monday"], "string element"),
            (["0", "1"], "string array"),
            ([], "empty list"),
            ("[0, 1, 2]", "string instead of array"),
        ]
        for days_val, reason in invalid_payloads:
            with self.subTest(days=days_val, reason=reason):
                payload = {
                    "user_id": self.user_id,
                    "time": "07:30",
                    "selected_challenge_type": "math",
                    "difficulty_preference": "easy",
                    "days_of_week": days_val,
                }
                resp = self.client.post("/api/v1/alarms", json=payload)
                self.assertEqual(
                    resp.status_code,
                    422,
                    f"Expected HTTP 422 for days_of_week '{days_val}' ({reason})",
                )

    def test_api_get_alarm_returns_list_of_ints(self):
        """Requirement L: GET /api/v1/alarms/{alarm_id} returns List[int], not JSON string."""
        create_resp = self.client.post(
            "/api/v1/alarms",
            json={
                "user_id": self.user_id,
                "time": "08:15",
                "selected_challenge_type": "math",
                "difficulty_preference": "easy",
                "days_of_week": [1, 3, 5],
            },
        )
        self.assertEqual(create_resp.status_code, 201)
        alarm_id = create_resp.json()["id"]

        get_resp = self.client.get(f"/api/v1/alarms/{alarm_id}")
        self.assertEqual(get_resp.status_code, 200)
        data = get_resp.json()
        self.assertIsInstance(data["days_of_week"], list)
        self.assertEqual(data["days_of_week"], [1, 3, 5])

    def test_api_put_alarm_updates_days_of_week(self):
        """Requirement M: PUT /api/v1/alarms/{alarm_id} correctly updates days_of_week."""
        create_resp = self.client.post(
            "/api/v1/alarms",
            json={
                "user_id": self.user_id,
                "time": "07:00",
                "selected_challenge_type": "dance",
                "difficulty_preference": "easy",
                "days_of_week": [0, 1],
            },
        )
        alarm_id = create_resp.json()["id"]

        # Update to new days of week
        put_resp = self.client.put(
            f"/api/v1/alarms/{alarm_id}",
            json={"days_of_week": [4, 5, 6]},
        )
        self.assertEqual(put_resp.status_code, 200)
        self.assertEqual(put_resp.json()["days_of_week"], [4, 5, 6])

        # Reject invalid update
        put_bad = self.client.put(
            f"/api/v1/alarms/{alarm_id}",
            json={"days_of_week": [0, 7]},
        )
        self.assertEqual(put_bad.status_code, 422)

    def test_api_user_alarms_listing_returns_list_of_ints(self):
        """Requirement N: GET /api/v1/users/{id}/alarms returns List[int] for each alarm."""
        self.client.post(
            "/api/v1/alarms",
            json={
                "user_id": self.user_id,
                "time": "06:00",
                "selected_challenge_type": "push_ups",
                "difficulty_preference": "hard",
                "days_of_week": [0, 2, 4],
            },
        )
        self.client.post(
            "/api/v1/alarms",
            json={
                "user_id": self.user_id,
                "time": "08:00",
                "selected_challenge_type": "math",
                "difficulty_preference": "medium",
                "days_of_week": [5, 6],
            },
        )

        resp = self.client.get(f"/api/v1/users/{self.user_id}/alarms")
        self.assertEqual(resp.status_code, 200)
        alarms = resp.json()
        self.assertEqual(len(alarms), 2)
        for a in alarms:
            self.assertIsInstance(a["days_of_week"], list)
            for d in a["days_of_week"]:
                self.assertIsInstance(d, int)
                self.assertIn(d, range(7))


if __name__ == "__main__":
    unittest.main()
