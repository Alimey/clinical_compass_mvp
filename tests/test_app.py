import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from app import create_app
from compass.backup import backup


class CompassTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "test.db"
        self.app = create_app(self.path, seed_demo=False, testing=True)
        self.client = self.app.test_client()
        self.doctor, self.doctor_csrf = self.login("doctor")
        self.patient, self.patient_csrf = self.login("patient-a")
        self.report = dict(
            mood=7,
            anxiety=3,
            adherence="Да",
            adverse_effects="",
            note="Вымышленный пример",
            safety_signal=False,
        )

    def tearDown(self):
        self.temp.cleanup()

    def login(self, username):
        client = self.app.test_client()
        result = client.post(
            "/api/auth/login", json={"username": username, "password": "compass-demo"}
        )
        self.assertEqual(result.status_code, 200)
        return client, result.json["csrf"]

    def post(self, client, path, data, csrf=None, key=None):
        token = csrf or (
            self.doctor_csrf if client is self.doctor else self.patient_csrf
        )
        headers = {"X-CSRF-Token": token}
        if key:
            headers["Idempotency-Key"] = key
        return client.post(path, json=data, headers=headers)

    def submit(self, **changes):
        result = self.post(
            self.patient, "/api/patients/2/reports", {**self.report, **changes}
        )
        self.assertEqual(result.status_code, 201, result.json)
        return result

    def detail(self):
        return self.doctor.get("/api/patients/2").json

    def test_auth_required_and_role_isolation(self):
        self.assertEqual(self.client.get("/api/patients").status_code, 401)
        self.assertEqual(len(self.doctor.get("/api/patients").json), 2)
        self.assertEqual([p["id"] for p in self.patient.get("/api/patients").json], [2])
        for route in (
            "/api/patients/3",
            "/api/patients/3/messages",
            "/api/patients/3/audit",
        ):
            self.assertEqual(self.patient.get(route).status_code, 404)
        self.assertEqual(self.doctor.get("/api/patients/5").status_code, 404)
        self.assertEqual(self.patient.get("/api/patients/2/audit").status_code, 403)
        self.assertEqual(
            self.post(self.doctor, "/api/patients/2/reports", self.report).status_code,
            403,
        )
        self.assertEqual(
            self.post(
                self.patient,
                "/api/patients/2/decisions",
                {"decision": "Другое", "note": "Демо"},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.post(
                self.patient, "/api/patients/3/messages", {"body": "Демо"}
            ).status_code,
            404,
        )

    def test_csrf_and_cross_origin(self):
        self.assertEqual(
            self.patient.post("/api/patients/2/reports", json=self.report).status_code,
            403,
        )
        self.assertEqual(
            self.post(
                self.patient, "/api/patients/2/reports", self.report, csrf="bad"
            ).status_code,
            403,
        )
        r = self.patient.post(
            "/api/patients/2/reports",
            json=self.report,
            headers={
                "X-CSRF-Token": self.patient_csrf,
                "Origin": "https://evil.example",
            },
        )
        self.assertEqual(r.status_code, 403)
        # Preserve Host at HTTPS proxy; scheme difference alone is allowed.
        client = self.app.test_client()
        r = client.post(
            "/api/auth/login",
            json={"username": "patient-a", "password": "compass-demo"},
            headers={"Host": "compass.example", "Origin": "https://compass.example"},
        )
        self.assertEqual(r.status_code, 200)

    def test_logout_revokes_session(self):
        self.assertTrue(self.patient.get("/api/auth/me").json["user"])
        self.assertEqual(
            self.post(self.patient, "/api/auth/logout", {}).status_code, 200
        )
        self.assertIsNone(self.patient.get("/api/auth/me").json["user"])
        self.assertEqual(self.patient.get("/api/patients").status_code, 401)
        with sqlite3.connect(self.path) as con:
            self.assertEqual(
                con.execute("SELECT COUNT(*) FROM sessions WHERE user_id=2").fetchone()[
                    0
                ],
                0,
            )

    def test_expired_sessions(self):
        with sqlite3.connect(self.path) as con:
            con.execute("UPDATE sessions SET expires_at=0 WHERE user_id=2")
        self.assertEqual(self.patient.get("/api/patients").status_code, 401)

    def test_cookie_flags_and_login_throttle(self):
        result = self.client.post(
            "/api/auth/login", json={"username": "doctor", "password": "compass-demo"}
        )
        cookie = result.headers["Set-Cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        for i in range(6):
            self.assertEqual(
                self.client.post(
                    "/api/auth/login", json={"username": "unknown", "password": "wrong"}
                ).status_code,
                401,
            )
        self.assertEqual(
            self.client.post(
                "/api/auth/login", json={"username": "unknown", "password": "wrong"}
            ).status_code,
            429,
        )

    def test_report_alert_notification_and_audit_atomic(self):
        result = self.submit(
            safety_signal=True, adherence="Нет", adverse_effects="Вымышленная усталость"
        )
        detail = self.detail()
        self.assertEqual(detail["alerts"][0]["report_id"], result.json["id"])
        self.assertEqual(len(detail["proposals"]), 3)
        self.assertEqual(detail["profile"]["plan"], "")
        notification = self.doctor.get("/api/notifications").json
        self.assertEqual(notification["unread"], 1)
        self.assertIsNone(notification["items"][0]["delivered_at"])
        self.assertEqual(
            self.post(
                self.doctor,
                "/api/notifications/delivered",
                {"ids": [notification["items"][0]["id"]]},
            ).status_code,
            200,
        )
        self.assertIsNotNone(
            self.doctor.get("/api/notifications").json["items"][0]["delivered_at"]
        )
        self.assertIsNone(notification["items"][0]["read_at"])
        alert = detail["alerts"][0]["id"]
        self.assertEqual(
            self.post(self.patient, f"/api/alerts/{alert}/review", {}).status_code, 403
        )
        self.assertEqual(
            self.post(self.doctor, f"/api/alerts/{alert}/review", {}).status_code, 200
        )
        self.assertEqual(self.doctor.get("/api/notifications").json["unread"], 0)
        self.assertEqual(self.detail()["alerts"][0]["status"], "reviewed")
        audit = self.doctor.get("/api/patients/2/audit").json
        self.assertEqual(
            [a["action"] for a in audit], ["alert.reviewed", "report.created"]
        )

    def test_transaction_rollback_on_notification_failure(self):
        with patch("app.notify", side_effect=RuntimeError("simulated failure")):
            with self.assertRaises(RuntimeError):
                self.submit(safety_signal=True)
        detail = self.detail()
        self.assertEqual(detail["reports"], [])
        self.assertEqual(detail["alerts"], [])
        self.assertEqual(detail["proposals"], [])

    def test_report_without_safety_no_alert(self):
        self.submit()
        self.assertEqual(self.detail()["alerts"], [])
        self.assertEqual(self.detail()["proposals"], [])

    def test_idempotency_prevents_duplicate_report_and_effects(self):
        data = {**self.report, "safety_signal": True}
        route = "/api/patients/2/reports"
        first = self.post(self.patient, route, data, key="retry-1")
        second = self.post(self.patient, route, data, key="retry-1")
        self.assertEqual(first.json, second.json)
        self.assertEqual(len(self.detail()["reports"]), 1)
        self.assertEqual(len(self.detail()["alerts"]), 1)
        self.assertEqual(self.doctor.get("/api/notifications").json["unread"], 1)
        self.assertEqual(
            self.post(self.patient, route, self.report, key="retry-1").status_code, 409
        )

    def test_invalid_input_never_writes(self):
        for change in (
            {"mood": -1},
            {"anxiety": 11},
            {"mood": True},
            {"mood": 2.5},
            {"safety_signal": "false"},
            {"adherence": "other"},
            {"note": "x" * 501},
            {"adverse_effects": None},
        ):
            with self.subTest(change=change):
                self.assertEqual(
                    self.post(
                        self.patient,
                        "/api/patients/2/reports",
                        {**self.report, **change},
                    ).status_code,
                    400,
                )
        for data in ([], None, "text"):
            result = self.patient.post(
                "/api/patients/2/reports",
                data=json.dumps(data),
                content_type="application/json",
                headers={"X-CSRF-Token": self.patient_csrf},
            )
            self.assertEqual(result.status_code, 400)
        self.assertEqual(self.detail()["reports"], [])

    def test_proposal_confirmation_changes_plan_only_after_confirmation(self):
        result = self.post(
            self.doctor, "/api/patients/2/proposals", {"choice": "demo-alpha"}
        )
        self.assertEqual(result.status_code, 201)
        self.assertEqual(self.detail()["profile"]["plan"], "")
        ident = result.json["id"]
        route = f"/api/proposals/{ident}/resolve"
        self.assertEqual(
            self.post(
                self.patient, route, {"status": "accepted", "note": "Демо"}
            ).status_code,
            403,
        )
        self.assertEqual(
            self.post(
                self.doctor, route, {"status": "accepted", "note": ""}
            ).status_code,
            400,
        )
        data = {"status": "accepted", "note": "Согласовали учебный вариант"}
        self.assertEqual(
            self.post(self.doctor, route, data, key="resolve-1").status_code, 200
        )
        self.assertEqual(
            self.post(self.doctor, route, data, key="resolve-1").status_code, 200
        )
        self.assertEqual(
            self.post(self.doctor, route, data, key="resolve-2").status_code, 409
        )
        detail = self.detail()
        self.assertEqual(detail["profile"]["plan"], "demo-alpha")
        self.assertEqual(len(detail["decisions"]), 1)
        self.assertEqual(self.patient.get("/api/notifications").json["unread"], 1)
        self.assertEqual(self.patient.get("/api/patients/2").json["proposals"], [])

    def test_rejected_proposal_does_not_change_plan(self):
        r = self.post(
            self.doctor, "/api/patients/2/proposals", {"choice": "demo-gamma"}
        )
        self.assertEqual(
            self.post(
                self.doctor,
                f"/api/proposals/{r.json['id']}/resolve",
                {"status": "rejected", "note": "Демо отказ"},
            ).status_code,
            200,
        )
        self.assertEqual(self.detail()["profile"]["plan"], "")
        self.assertIn("Отклонено", self.detail()["decisions"][0]["decision"])

    def test_synthetic_incompatibility_enforced_on_server(self):
        self.assertEqual(
            self.post(
                self.doctor, "/api/patients/2/proposals", {"choice": "demo-beta"}
            ).status_code,
            409,
        )
        r = self.post(
            self.doctor, "/api/patients/2/proposals", {"choice": "demo-gamma"}
        )
        with sqlite3.connect(self.path) as con:
            con.execute(
                "UPDATE profiles SET intolerance='demo-gamma' WHERE patient_id=2"
            )
        self.assertEqual(
            self.post(
                self.doctor,
                f"/api/proposals/{r.json['id']}/resolve",
                {"status": "accepted", "note": "Демо"},
            ).status_code,
            409,
        )
        self.assertEqual(self.detail()["profile"]["plan"], "")

    def test_other_doctor_cannot_resolve_or_review(self):
        other, csrf = self.login("doctor-other")
        self.submit(safety_signal=True)
        proposal = self.detail()["proposals"][0]["id"]
        alert = self.detail()["alerts"][0]["id"]
        self.assertEqual(
            self.post(
                other,
                f"/api/proposals/{proposal}/resolve",
                {"status": "accepted", "note": "Демо"},
                csrf,
            ).status_code,
            404,
        )
        self.assertEqual(
            self.post(other, f"/api/alerts/{alert}/review", {}, csrf).status_code, 404
        )
        self.assertEqual([p["id"] for p in other.get("/api/patients").json], [5])

    def test_messages_isolation_receipts_and_idempotency(self):
        route = "/api/patients/2/messages"
        r = self.post(
            self.patient, route, {"body": "<script>demo</script>"}, key="message-1"
        )
        self.assertEqual(r.status_code, 201)
        self.assertEqual(
            self.post(
                self.patient, route, {"body": "<script>demo</script>"}, key="message-1"
            ).json,
            r.json,
        )
        self.assertEqual(len(self.doctor.get(route).json), 1)
        self.assertIsNone(self.patient.get(route).json[0]["read_at"])
        self.post(self.doctor, route + "/read", {"ids": [r.json["id"]]})
        self.assertIsNotNone(self.patient.get(route).json[0]["read_at"])
        self.assertEqual(
            self.post(self.doctor, route, {"body": "   "}).status_code, 400
        )
        self.assertEqual(
            self.post(self.doctor, route, {"body": "x" * 1001}).status_code, 400
        )
        self.assertEqual(self.doctor.get("/api/patients/3/messages").json, [])

    def test_notification_read_is_owned(self):
        self.submit()
        item = self.doctor.get("/api/notifications").json["items"][0]
        self.assertEqual(
            self.post(
                self.patient, "/api/notifications/read", {"id": item["id"]}
            ).status_code,
            404,
        )
        self.assertEqual(
            self.post(
                self.patient, "/api/notifications/delivered", {"ids": [item["id"]]}
            ).status_code,
            404,
        )
        self.assertEqual(
            self.post(
                self.doctor, "/api/notifications/read", {"id": item["id"]}
            ).status_code,
            200,
        )
        self.assertEqual(self.doctor.get("/api/notifications").json["unread"], 0)

    def test_manual_decision_and_persistence(self):
        self.assertEqual(
            self.post(
                self.doctor,
                "/api/patients/2/decisions",
                {"decision": "Другое", "note": "Демо заметка"},
            ).status_code,
            201,
        )
        other = create_app(self.path, seed_demo=False, testing=True).test_client()
        r = other.post(
            "/api/auth/login",
            json={"username": "patient-a", "password": "compass-demo"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            other.get("/api/patients/2").json["decisions"][0]["note"], "Демо заметка"
        )

    def test_concurrent_confirmation_creates_exactly_one_decision(self):
        from concurrent.futures import ThreadPoolExecutor

        result = self.post(
            self.doctor, "/api/patients/2/proposals", {"choice": "demo-alpha"}
        )
        ident = result.json["id"]
        second, csrf = self.login("doctor")

        def resolve(client, token):
            return self.post(
                client,
                f"/api/proposals/{ident}/resolve",
                {"status": "accepted", "note": "Демо подтверждение"},
                csrf=token,
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            a = executor.submit(resolve, self.doctor, self.doctor_csrf)
            b = executor.submit(resolve, second, csrf)
            self.assertEqual(sorted([a.result(), b.result()]), [200, 409])
        self.assertEqual(len(self.detail()["decisions"]), 1)

    def test_adherence_excludes_not_applicable(self):
        for adherence in ("Да", "Частично", "Нет", "Не применимо"):
            self.submit(adherence=adherence)
        self.assertEqual(self.detail()["adherence"], 50)

    def test_backup_round_trip_preserves_state(self):
        self.submit(safety_signal=True)
        destination = Path(self.temp.name) / "backup.db"
        backup(self.path, destination)
        with self.assertRaises(FileExistsError):
            backup(self.path, destination)
        restored = create_app(destination, seed_demo=False, testing=True).test_client()
        restored.post(
            "/api/auth/login", json={"username": "doctor", "password": "compass-demo"}
        )
        self.assertEqual(len(restored.get("/api/patients/2").json["alerts"]), 1)

    def test_seed_is_repeatable_and_does_not_overwrite_existing_reports(self):
        self.submit(note="Сохранить мою запись")
        create_app(self.path, seed_demo=True, testing=True)
        self.assertEqual(len(self.detail()["reports"]), 1)
        path = Path(self.temp.name) / "showcase.db"
        first = create_app(path, testing=True)
        second = create_app(path, testing=True)
        with sqlite3.connect(path) as con:
            self.assertEqual(
                con.execute("SELECT COUNT(*) FROM reports").fetchone()[0], 21
            )
        self.assertTrue(first and second)

    def test_legacy_database_migration(self):
        original = Path(__file__).resolve().parents[1] / "demo.db"
        copy = Path(self.temp.name) / "legacy.db"
        with sqlite3.connect(original) as source, sqlite3.connect(copy) as target:
            before = source.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
            source.backup(target)
        legacy = create_app(copy, seed_demo=False, testing=True).test_client()
        legacy.post(
            "/api/auth/login", json={"username": "doctor", "password": "compass-demo"}
        )
        self.assertEqual(legacy.get("/api/patients/2").status_code, 200)
        with sqlite3.connect(copy) as con:
            self.assertEqual(
                con.execute("SELECT COUNT(*) FROM reports").fetchone()[0], before
            )

    def test_pwa_assets_and_security_headers(self):
        self.assertEqual(self.client.get("/api/health").json["status"], "ok")
        for url in (
            "/",
            "/sw.js",
            "/static/app.js",
            "/static/style.css",
            "/static/icon-192.png",
            "/static/icon-512.png",
            "/static/icon-maskable.png",
        ):
            with self.client.get(url) as response:
                self.assertEqual(response.status_code, 200, url)
                self.assertEqual(response.headers["Cache-Control"], "no-store")
        with self.client.get("/static/manifest.webmanifest") as r:
            self.assertEqual(json.loads(r.data)["display"], "standalone")
        with self.client.get("/") as r:
            self.assertIn(
                "frame-ancestors 'none'", r.headers["Content-Security-Policy"]
            )


if __name__ == "__main__":
    unittest.main()
