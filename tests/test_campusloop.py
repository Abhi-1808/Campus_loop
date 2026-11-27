import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from campusloop.__main__ import set_user
from campusloop.app import create_app
from campusloop.config import Settings
from campusloop.db import backup, connect
from campusloop.security import hash_password

ORIGIN = "http://127.0.0.1:8000"
HEADERS = {"Origin": ORIGIN, "X-CampusLoop-Request": "1"}
PASSWORD = "campusloop-test-password"
REGISTRATION = {"department": "Computer Science", "year": "2"}


class CampusLoopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password_hash = hash_password(PASSWORD)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = Settings(Path(self.temp.name) / "db.sqlite3", ORIGIN, False)
        self.app = create_app(self.settings)
        self.client = self.enterContext(TestClient(self.app, base_url=ORIGIN))
        self.assertEqual(self.client.get("/healthz").status_code, 200)
        with connect(self.settings.database, write=True) as connection:
            connection.executemany(
                "INSERT INTO users (email, name, password_hash, role) VALUES (?, ?, ?, ?)",
                [(f"{name}@fixture.example", name.title(), self.password_hash, role)
                 for name, role in (("student", "student"), ("peer", "student"),
                                    ("organizer", "organizer"), ("other", "organizer"))],
            )

    def sign_in(self, name, client=None):
        client = client if client is not None else self.client
        response = client.post("/api/session", json={"email": f"{name}@fixture.example", "password": PASSWORD},
                               headers=HEADERS)
        self.assertEqual(response.status_code, 200, response.text)
        return response

    def request(self, method, url, payload=None, *, client=None):
        client = client if client is not None else self.client
        return client.request(method, url, json={} if payload is None else payload, headers=HEADERS)

    def event_form(self, **overrides):
        relative_now = datetime.now(self.settings.zone)
        return {
            "title": "Campus Fixture Event", "category": "Technical", "organizer": "Code Circle",
            "venue": "Lab A", "description": "An opportunity to try a campus project.",
            "eligibility": "Open to all students.", "capacity": 35, "status": "published",
            "starts_at": (relative_now + timedelta(days=2)).isoformat(timespec="minutes")[:16],
            "ends_at": (relative_now + timedelta(days=2, hours=3)).isoformat(timespec="minutes")[:16],
            "closes_at": (relative_now + timedelta(days=1)).isoformat(timespec="minutes")[:16],
            **overrides,
        }

    def make_event(self, **overrides):
        self.sign_in("organizer")
        response = self.request("POST", "/api/organizer/events", self.event_form(**overrides))
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["event"]

    def test_public_search_and_filter_casefold(self):
        event = self.make_event(title="ÉLAN Research Night")
        response = self.client.get("/api/events", params={"q": "élan", "category": "Technical"})
        self.assertEqual(response.json()["total"], 1)
        self.assertEqual(response.json()["events"][0]["id"], event["id"])
        self.assertNotIn("version", response.json()["events"][0])
        self.assertEqual(self.client.get("/api/events", params={"category": "Sports"}).json()["total"], 0)

    def test_cross_origin_and_non_json_writes_rejected(self):
        payload = {"email": "student@fixture.example", "password": PASSWORD}
        self.assertEqual(self.client.post("/api/session", json=payload).status_code, 403)
        self.assertEqual(self.client.post("/api/session", json=payload,
            headers={**HEADERS, "Origin": "https://another.example"}).status_code, 403)
        self.assertEqual(self.client.post("/api/session", data=payload, headers=HEADERS).status_code, 415)
        self.assertEqual(self.client.post("/api/session", json={**payload, "password": "x" * 17_000},
            headers=HEADERS).status_code, 413)
        self.assertEqual(self.client.get("/api/session", headers={"Host": "another.example"}).status_code, 400)

    def test_signed_in_session_rotates_and_expires_on_logout(self):
        login = self.sign_in("student")
        old = self.client.cookies.get(self.settings.cookie_name)
        self.assertIn("HttpOnly", login.headers["set-cookie"])
        self.assertIn("SameSite=lax", login.headers["set-cookie"])
        self.assertIn("no-store", login.headers["cache-control"])
        self.sign_in("organizer")
        self.assertNotEqual(old, self.client.cookies.get(self.settings.cookie_name))
        stale = TestClient(self.app, base_url=ORIGIN, cookies={self.settings.cookie_name: old})
        self.addCleanup(stale.close)
        self.assertIsNone(stale.get("/api/session").json()["user"])
        self.assertEqual(self.request("DELETE", "/api/session").status_code, 200)
        self.assertIsNone(self.client.get("/api/session").json()["user"])

    def test_sign_in_requires_a_matching_selected_role(self):
        for name, other_role in (("student", "organizer"), ("organizer", "student")):
            credentials = {"email": f"{name}@fixture.example", "password": PASSWORD}
            wrong = self.request("POST", "/api/session", {**credentials, "role": other_role})
            self.assertEqual(wrong.status_code, 403)
            self.assertNotIn("Set-Cookie", wrong.headers)
            self.assertIsNone(self.client.get("/api/session").json()["user"])
            correct = self.request("POST", "/api/session", {**credentials, "role": name})
            self.assertEqual(correct.status_code, 200)
            self.assertEqual(correct.json()["user"]["role"], name)
            self.assertEqual(self.request("DELETE", "/api/session").status_code, 200)

    def test_password_preserves_outer_whitespace(self):
        password = " deliberately spaced passphrase "
        with connect(self.settings.database, write=True) as connection:
            connection.execute("UPDATE users SET password_hash = ? WHERE email = ?",
                               (hash_password(password), "student@fixture.example"))
        response = self.request("POST", "/api/session",
                                {"email": "student@fixture.example", "password": password})
        self.assertEqual(response.status_code, 200)

    def test_production_cookie_headers_and_origin(self):
        settings = Settings(self.settings.database, "https://campus.fixture.example", True)
        with TestClient(create_app(settings), base_url=settings.origin) as client:
            response = client.post("/api/session", json={"email": "student@fixture.example", "password": PASSWORD},
                headers={"Origin": settings.origin, "X-CampusLoop-Request": "1"})
            self.assertEqual(response.status_code, 200)
            self.assertIn("__Host-campusloop=", response.headers["set-cookie"])
            self.assertIn("Secure", response.headers["set-cookie"])
            self.assertIn("HttpOnly", response.headers["set-cookie"])
            self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
            self.assertEqual(response.headers["Strict-Transport-Security"], "max-age=31536000")

    def test_organizer_ownership_and_student_role(self):
        event = self.make_event()
        base = "/api/organizer/events/" + event["id"]
        self.sign_in("student")
        self.assertEqual(self.client.get(base + "/attendees").status_code, 403)
        self.assertEqual(self.request("POST", "/api/organizer/events", self.event_form()).status_code, 403)
        self.sign_in("other")
        self.assertEqual(self.client.get(base + "/attendees").status_code, 404)
        self.assertEqual(self.request("PUT", base, self.event_form(version=event["version"])).status_code, 404)
        self.assertEqual(self.request("POST", "/api/events/" + event["id"] + "/registration",
                                     REGISTRATION).status_code, 403)

    def test_drafts_versions_and_archiving(self):
        event = self.make_event(status="draft")
        path = "/api/organizer/events/" + event["id"]
        self.assertEqual(self.client.get("/api/events").json()["total"], 0)
        self.sign_in("student")
        self.assertEqual(self.client.get("/api/events/" + event["id"]).status_code, 404)
        self.sign_in("organizer")
        published = self.request("PUT", path, self.event_form(version=event["version"]))
        self.assertEqual(published.status_code, 200, published.text)
        self.assertEqual(self.request("PUT", path, self.event_form(version=event["version"])).status_code, 409)
        version = published.json()["event"]["version"]
        self.assertEqual(self.request("DELETE", path, {"version": version}).status_code, 409)
        self.assertEqual(self.request("POST", path + "/cancel", {"version": version}).status_code, 200)
        self.assertEqual(self.client.get("/api/events", params={"status": "past"}).json()["total"], 1)
        self.assertEqual(self.request("DELETE", path, {"version": version + 1}).status_code, 200)
        self.assertEqual(self.client.get("/api/events", params={"status": "all"}).json()["total"], 0)
        self.assertEqual(self.request("DELETE", path, {"version": version + 1}).status_code, 200)

    def test_registration_cancel_rebook_and_record_isolation(self):
        event = self.make_event(capacity=1)
        endpoint = "/api/events/" + event["id"] + "/registration"
        self.sign_in("student")
        result = self.request("POST", endpoint, REGISTRATION)
        self.assertEqual(result.status_code, 201, result.text)
        first = result.json()["registration"]
        summary = self.client.get("/api/my-events").json()["items"][0]
        self.assertEqual(summary["registration"]["id"], first["id"])
        self.assertEqual(summary["event"]["id"], event["id"])
        self.assertEqual(self.request("POST", endpoint, REGISTRATION).status_code, 409)
        self.sign_in("peer")
        self.assertEqual(self.client.get("/api/my-events").json()["items"], [])
        self.assertEqual(self.request("DELETE", endpoint).status_code, 404)
        self.assertEqual(self.request("POST", endpoint, REGISTRATION).status_code, 409)
        self.sign_in("student")
        self.assertEqual(self.request("DELETE", endpoint).status_code, 200)
        self.assertEqual(self.request("DELETE", endpoint).status_code, 200)
        self.assertIsNotNone(self.client.get("/api/my-events").json()["items"][0]["registration"]["cancelled_at"])
        second = self.request("POST", endpoint, REGISTRATION)
        self.assertEqual(second.status_code, 201, second.text)
        self.assertNotEqual(first["id"], second.json()["registration"]["id"])
        stale = self.request("DELETE", endpoint, {"registration_id": first["id"]})
        self.assertEqual(stale.status_code, 409)
        self.assertIsNone(self.client.get("/api/my-events").json()["items"][0]["registration"]["cancelled_at"])
        self.sign_in("organizer")
        attendees = self.client.get(f"/api/organizer/events/{event['id']}/attendees").json()["items"]
        self.assertEqual(len(attendees), 1)
        self.assertEqual(attendees[0]["email"], "student@fixture.example")

    def test_simultaneous_last_seat(self):
        event = self.make_event(capacity=1)
        endpoint = "/api/events/" + event["id"] + "/registration"
        clients = [TestClient(self.app, base_url=ORIGIN) for _ in range(2)]
        for name, client in zip(("student", "peer"), clients):
            self.addCleanup(client.close)
            self.sign_in(name, client)
        gate = Barrier(2)

        def reserve(client):
            gate.wait(timeout=10)
            return self.request("POST", endpoint, REGISTRATION, client=client).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(reserve, clients)), [201, 409])
        self.assertEqual(self.client.get("/api/events/" + event["id"]).json()["event"]["seats_left"], 0)

    def test_invalid_dates_deadline_and_capacity(self):
        self.sign_in("organizer")
        form = self.event_form()
        invalid = self.request("POST", "/api/organizer/events", {**form, "ends_at": form["starts_at"]})
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(self.request("POST", "/api/organizer/events", {**form, "capacity": 0}).status_code, 422)
        event = self.make_event()
        with connect(self.settings.database, write=True) as connection:
            connection.execute("UPDATE events SET closes_at = 1 WHERE id = ?", (event["id"],))
        self.sign_in("student")
        self.assertEqual(self.request("POST", f"/api/events/{event['id']}/registration", REGISTRATION).status_code, 409)

    def test_account_rate_limit_and_no_credential_echo(self):
        for _ in range(8):
            response = self.request("POST", "/api/session",
                                    {"email": "student@fixture.example", "password": "incorrect"})
            self.assertEqual(response.status_code, 401)
            self.assertNotIn("incorrect", response.json()["detail"].replace("password is incorrect", ""))
        throttled = self.request("POST", "/api/session", {"email": "student@fixture.example", "password": PASSWORD})
        self.assertEqual(throttled.status_code, 429)
        self.assertGreater(int(throttled.headers["retry-after"]), 0)
        self.sign_in("peer")

    def test_backup_preserves_events_without_restoring_old_sessions(self):
        self.make_event()
        destination = Path(self.temp.name) / "backup.sqlite3"
        backup(self.settings.database, destination)
        with connect(destination) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM events").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM login_attempts").fetchone()[0], 0)
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertEqual(self.client.get("/api/session").json()["user"]["role"], "organizer")
        with self.assertRaises(FileExistsError):
            backup(self.settings.database, destination)

    def test_successful_logins_release_the_shared_ip_reservation(self):
        invalid = {"email": "student@fixture.example", "password": "invalid test password"}
        self.assertEqual(self.request("POST", "/api/session", invalid).status_code, 401)
        self.sign_in("organizer")
        self.sign_in("peer")
        with connect(self.settings.database) as connection:
            rows = connection.execute("SELECT attempts FROM login_attempts WHERE scope LIKE 'ip:%'").fetchall()
        self.assertEqual([row["attempts"] for row in rows], [1])

    def test_organizer_cannot_reopen_an_event_that_already_started(self):
        event = self.make_event()
        moment = int(datetime.now(self.settings.zone).timestamp())
        with connect(self.settings.database, write=True) as connection:
            connection.execute(
                "UPDATE events SET starts_at = ?, closes_at = ? WHERE id = ?",
                (moment - 60, moment - 120, event["id"]),
            )
        result = self.request("PUT", "/api/organizer/events/" + event["id"],
                              self.event_form(version=event["version"]))
        self.assertEqual(result.status_code, 409)

    def test_account_role_change_preserves_access_to_existing_history(self):
        event = self.make_event()
        self.sign_in("student")
        self.assertEqual(
            self.request("POST", f"/api/events/{event['id']}/registration", REGISTRATION).status_code, 201
        )
        for account, role in (("student", "organizer"), ("organizer", "student")):
            args = SimpleNamespace(email=f"{account}@fixture.example", name=account, role=role, update=True)
            with patch("campusloop.__main__.getpass.getpass", return_value="unused-new-test-password"):
                with self.assertRaisesRegex(ValueError, "event history"):
                    set_user(self.settings, args)


if __name__ == "__main__":
    unittest.main()
