"""Automated test suite for Alarm lifecycle preservation and toggle operations in SmartWake AI.

Validates that:
A. Alarm creation defaults to is_active = True.
B. DELETE /api/v1/alarms/{id} logically deactivates (is_active = False) without physically deleting the row.
C. GET /api/v1/alarms/{id} after DELETE still returns the alarm with is_active = False.
D. User alarm listing (GET /api/v1/users/{id}/alarms) still contains the deactivated alarm.
E. PATCH /api/v1/alarms/{id}/toggle switches active state from True to False.
F. PATCH /api/v1/alarms/{id}/toggle switches active state from False to True.
G. Toggle on a nonexistent alarm returns HTTP 404 Not Found.
H. DELETE on a nonexistent alarm returns HTTP 404 Not Found.
I. Historical WakeSession relationships remain intact after alarm deactivation (no foreign key NULLing).
J. Existing PUT behavior for updating is_active continues to work.
"""
import asyncio
import json
from datetime import datetime
import unittest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.datetime_utils import now_utc_naive
from backend.app.database.base import Base
import backend.app.database.session  # Ensures SQLite connection event listener is active
from backend.app.database.session import get_db
from backend.app.main import app
import backend.app.models
from backend.app.models.alarm import Alarm
from backend.app.models.wake_session import WakeSession
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

    def patch(self, path: str, json: dict = None, headers: dict = None):
        return self._request("PATCH", path, json_data=json, headers=headers)

    def delete(self, path: str, headers: dict = None):
        return self._request("DELETE", path, headers=headers)


class TestAlarmLifecycle(unittest.TestCase):
    """Test suite for alarm lifecycle preservation, deactivation, and toggle endpoints."""

    @classmethod
    def setUpClass(cls):
        """Configure an isolated in-memory SQLite database and override get_db dependency."""
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
            user = user_service.create_user(session, username="lifecycle_user", timezone="UTC")
            self.user_id = user.id

    def test_create_active_alarm_defaults_to_active(self):
        """Requirement A: Creating an alarm defaults to is_active = True."""
        resp = self.client.post(
            "/api/v1/alarms",
            json={
                "user_id": self.user_id,
                "time": "07:00",
                "selected_challenge_type": "math",
                "difficulty_preference": "adaptive",
            },
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertTrue(data["is_active"])

    def test_delete_endpoint_deactivates_logically(self):
        """Requirement B: DELETE endpoint deactivates without physically deleting the row."""
        create_resp = self.client.post(
            "/api/v1/alarms",
            json={
                "user_id": self.user_id,
                "time": "06:30",
                "selected_challenge_type": "dance",
                "difficulty_preference": "easy",
            },
        )
        alarm_id = create_resp.json()["id"]

        del_resp = self.client.delete(f"/api/v1/alarms/{alarm_id}")
        self.assertEqual(del_resp.status_code, 200)

        # Direct database check: the row must still exist in SQLite!
        with self.TestingSessionLocal() as session:
            alarm_in_db = session.get(Alarm, alarm_id)
            self.assertIsNotNone(alarm_in_db, "Alarm row should remain in SQLite after DELETE.")
            self.assertFalse(alarm_in_db.is_active, "alarm.is_active must be False after DELETE.")

    def test_get_alarm_after_delete_still_returns_alarm(self):
        """Requirement C: GET after DELETE still returns the alarm with is_active = False."""
        create_resp = self.client.post(
            "/api/v1/alarms",
            json={
                "user_id": self.user_id,
                "time": "07:30",
                "selected_challenge_type": "tongue_twister",
                "difficulty_preference": "medium",
            },
        )
        alarm_id = create_resp.json()["id"]

        self.client.delete(f"/api/v1/alarms/{alarm_id}")

        get_resp = self.client.get(f"/api/v1/alarms/{alarm_id}")
        self.assertEqual(get_resp.status_code, 200)
        data = get_resp.json()
        self.assertEqual(data["id"], alarm_id)
        self.assertFalse(data["is_active"])

    def test_user_alarm_listing_contains_deactivated_alarm(self):
        """Requirement D: User alarm listing still contains the deactivated alarm."""
        create_resp = self.client.post(
            "/api/v1/alarms",
            json={
                "user_id": self.user_id,
                "time": "08:00",
                "selected_challenge_type": "push_ups",
                "difficulty_preference": "hard",
            },
        )
        alarm_id = create_resp.json()["id"]

        self.client.delete(f"/api/v1/alarms/{alarm_id}")

        list_resp = self.client.get(f"/api/v1/users/{self.user_id}/alarms")
        self.assertEqual(list_resp.status_code, 200)
        alarms = list_resp.json()
        self.assertEqual(len(alarms), 1)
        self.assertEqual(alarms[0]["id"], alarm_id)
        self.assertFalse(alarms[0]["is_active"])

    def test_patch_toggle_from_true_to_false(self):
        """Requirement E: PATCH /api/v1/alarms/{id}/toggle toggles is_active from True to False."""
        create_resp = self.client.post(
            "/api/v1/alarms",
            json={
                "user_id": self.user_id,
                "time": "07:00",
                "selected_challenge_type": "memory",
                "difficulty_preference": "adaptive",
                "is_active": True,
            },
        )
        alarm_id = create_resp.json()["id"]

        toggle_resp = self.client.patch(f"/api/v1/alarms/{alarm_id}/toggle")
        self.assertEqual(toggle_resp.status_code, 200)
        data = toggle_resp.json()
        self.assertFalse(data["is_active"])
        self.assertEqual(data["id"], alarm_id)

    def test_patch_toggle_from_false_to_true(self):
        """Requirement F: PATCH /api/v1/alarms/{id}/toggle toggles is_active from False to True."""
        create_resp = self.client.post(
            "/api/v1/alarms",
            json={
                "user_id": self.user_id,
                "time": "07:00",
                "selected_challenge_type": "memory",
                "difficulty_preference": "adaptive",
                "is_active": False,
            },
        )
        alarm_id = create_resp.json()["id"]

        toggle_resp = self.client.patch(f"/api/v1/alarms/{alarm_id}/toggle")
        self.assertEqual(toggle_resp.status_code, 200)
        data = toggle_resp.json()
        self.assertTrue(data["is_active"])

    def test_patch_toggle_nonexistent_alarm_returns_404(self):
        """Requirement G: Toggling a nonexistent alarm returns HTTP 404."""
        resp = self.client.patch("/api/v1/alarms/99999/toggle")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("not found", resp.json()["detail"].lower())

    def test_delete_nonexistent_alarm_returns_404(self):
        """Requirement H: Deleting a nonexistent alarm returns HTTP 404."""
        resp = self.client.delete("/api/v1/alarms/99999")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("not found", resp.json()["detail"].lower())

    def test_historical_wake_session_relationship_preserved(self):
        """Requirement I: Historical WakeSession relationship remains intact after alarm deactivation."""
        create_resp = self.client.post(
            "/api/v1/alarms",
            json={
                "user_id": self.user_id,
                "time": "06:00",
                "selected_challenge_type": "push_ups",
                "difficulty_preference": "hard",
            },
        )
        alarm_id = create_resp.json()["id"]

        # Simulate a completed historical WakeSession linked to this alarm
        now = now_utc_naive()
        with self.TestingSessionLocal() as session:
            wake_session = WakeSession(
                user_id=self.user_id,
                alarm_id=alarm_id,
                scheduled_time=now,
                initial_ring_time=now,
                status="completed",
            )
            session.add(wake_session)
            session.commit()
            session.refresh(wake_session)
            session_id = wake_session.id

        # Deactivate the alarm via DELETE endpoint
        del_resp = self.client.delete(f"/api/v1/alarms/{alarm_id}")
        self.assertEqual(del_resp.status_code, 200)

        # Verify historical integrity in SQLite
        with self.TestingSessionLocal() as session:
            # 1. Alarm record still exists
            alarm_in_db = session.get(Alarm, alarm_id)
            self.assertIsNotNone(alarm_in_db)
            self.assertFalse(alarm_in_db.is_active)

            # 2. WakeSession record still exists
            wake_session_in_db = session.get(WakeSession, session_id)
            self.assertIsNotNone(wake_session_in_db)

            # 3. Foreign key is NOT set to NULL
            self.assertEqual(
                wake_session_in_db.alarm_id,
                alarm_id,
                "alarm_id should remain intact on historical wake session.",
            )

            # 4. ORM relationship resolves to the alarm
            self.assertIsNotNone(wake_session_in_db.alarm)
            self.assertEqual(wake_session_in_db.alarm.id, alarm_id)
            self.assertEqual(wake_session_in_db.alarm.time, "06:00")

            # 5. Back-populates relationship still navigates
            self.assertEqual(len(alarm_in_db.wake_sessions), 1)
            self.assertEqual(alarm_in_db.wake_sessions[0].id, session_id)

    def test_put_alarm_updates_is_active_consistently(self):
        """Requirement J: PUT /api/v1/alarms/{id} preserves ability to update is_active."""
        create_resp = self.client.post(
            "/api/v1/alarms",
            json={
                "user_id": self.user_id,
                "time": "07:00",
                "selected_challenge_type": "dance",
                "difficulty_preference": "easy",
                "is_active": True,
            },
        )
        alarm_id = create_resp.json()["id"]

        # PUT to deactivate
        put_resp1 = self.client.put(
            f"/api/v1/alarms/{alarm_id}",
            json={"is_active": False},
        )
        self.assertEqual(put_resp1.status_code, 200)
        self.assertFalse(put_resp1.json()["is_active"])

        # PUT to activate
        put_resp2 = self.client.put(
            f"/api/v1/alarms/{alarm_id}",
            json={"is_active": True},
        )
        self.assertEqual(put_resp2.status_code, 200)
        self.assertTrue(put_resp2.json()["is_active"])


if __name__ == "__main__":
    unittest.main()
