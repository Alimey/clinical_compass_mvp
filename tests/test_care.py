import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from app import create_app
from compass.db import db, now
from compass.care import local_today
from compass.delivery import reminders_and_escalations, dispatch_push
from compass.telegram_bot import handle_update
from compass.name_crypto import unseal


class CareTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "db.sqlite"
        self.app = create_app(self.path, seed_demo=False, testing=True)
        self.doctor, self.dc = self.login("doctor")
        self.patient, self.pc = self.login("patient-a")

    def tearDown(self):
        self.temp.cleanup()

    def login(self, username, password="compass-demo"):
        client = self.app.test_client()
        result = client.post(
            "/api/auth/login", json={"username": username, "password": password}
        )
        self.assertEqual(result.status_code, 200, result.json)
        return client, result.json["csrf"]

    def post(self, client, url, data, token=None, key=None):
        headers = {
            "X-CSRF-Token": token or (self.dc if client is self.doctor else self.pc)
        }
        if key:
            headers["Idempotency-Key"] = key
        return client.post(url, json=data, headers=headers)

    def detail(self, client=None):
        return (client or self.doctor).get("/api/patients/2").json

    def assign(self, repeat=0):
        template = self.doctor.get("/api/surveys/templates").json[0]
        deadline = (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat()
        result = self.post(
            self.doctor,
            "/api/patients/2/surveys",
            {"template_id": template["id"], "due_at": deadline, "repeat_days": repeat},
        )
        self.assertEqual(result.status_code, 201, result.json)
        return result.json["id"]

    def prescribe(self):
        today = local_today().isoformat()
        r = self.post(
            self.doctor,
            "/api/patients/2/prescriptions",
            {
                "choice": "demo-alpha",
                "times": ["00:00"],
                "starts_on": today,
                "ends_on": today,
                "note": "Вымышленное назначение, без дозировки",
            },
        )
        self.assertEqual(r.status_code, 201, r.json)
        return r.json["id"]

    def test_appointment_concurrent_booking_and_isolation(self):
        other, token = self.login("patient-b")
        slot = self.patient.get("/api/appointments/slots").json["slots"][0]

        def book(client, csrf):
            return self.post(
                client, "/api/appointments", {"starts_at": slot, "patient_id": 5}, csrf
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(book, self.patient, self.pc)
            second = executor.submit(book, other, token)
            self.assertEqual(sorted([first.result(), second.result()]), [201, 409])
        records = self.doctor.get("/api/appointments").json
        self.assertEqual(len(records), 1)
        self.assertIn(records[0]["patient_id"], [2, 3])
        foreign, csrf = self.login("doctor-other")
        self.assertEqual(foreign.get("/api/appointments").json, [])
        self.assertEqual(
            self.post(
                foreign,
                f"/api/appointments/{records[0]['id']}/status",
                {"status": "cancelled"},
                csrf,
            ).status_code,
            404,
        )

    def test_appointment_cancel_frees_slot_and_future_completion_rejected(self):
        slot = self.patient.get("/api/appointments/slots").json["slots"][0]
        r = self.post(self.patient, "/api/appointments", {"starts_at": slot})
        self.assertEqual(r.status_code, 201)
        ident = r.json["id"]
        self.assertEqual(
            self.post(
                self.doctor,
                f"/api/appointments/{ident}/status",
                {"status": "completed"},
            ).status_code,
            409,
        )
        self.assertEqual(
            self.post(
                self.patient,
                f"/api/appointments/{ident}/status",
                {"status": "cancelled"},
            ).status_code,
            200,
        )
        self.assertIn(slot, self.patient.get("/api/appointments/slots").json["slots"])
        self.assertEqual(
            self.post(
                self.patient,
                f"/api/appointments/{ident}/status",
                {"status": "cancelled"},
            ).status_code,
            409,
        )

    def test_appointment_rejects_past_and_unlisted_slots(self):
        for value in (
            "invalid",
            (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
            (datetime.now(timezone.utc) + timedelta(days=70)).isoformat(),
        ):
            self.assertEqual(
                self.post(
                    self.patient, "/api/appointments", {"starts_at": value}
                ).status_code,
                400,
            )

    def test_surveys_answers_deadline_recurrence_and_idempotency(self):
        ident = self.assign(1)
        stranger, csrf = self.login("patient-b")
        answers = {"1": 4, "2": False, "3": "Вымышленный ответ"}
        self.assertEqual(
            self.post(
                stranger, f"/api/surveys/{ident}/submit", {"answers": answers}, csrf
            ).status_code,
            404,
        )
        self.assertEqual(
            self.post(
                self.patient, f"/api/surveys/{ident}/submit", {"answers": {"1": 11}}
            ).status_code,
            400,
        )
        for _ in range(2):
            r = self.post(
                self.patient,
                f"/api/surveys/{ident}/submit",
                {"answers": answers},
                key="survey-retry",
            )
            self.assertEqual(r.status_code, 201, r.json)
        items = self.detail()["care"]["surveys"]
        self.assertEqual(len(items), 2)
        finished = next(i for i in items if i["id"] == ident)
        self.assertEqual(finished["answers"], answers)
        self.assertTrue(finished["interpretation"])
        self.assertEqual(sum(i["status"] == "assigned" for i in items), 1)
        self.assertEqual(
            self.post(
                self.patient, f"/api/surveys/{ident}/submit", {"answers": answers}
            ).status_code,
            409,
        )

    def test_template_ownership_and_snapshot(self):
        r = self.post(
            self.doctor,
            "/api/surveys/templates",
            {
                "title": "Мой опрос",
                "description": "Демо",
                "questions": [{"type": "text", "label": "Что обсудим?"}],
            },
        )
        self.assertEqual(r.status_code, 201)
        ident = r.json["id"]
        other, csrf = self.login("doctor-other")
        self.assertNotIn(
            ident, [t["id"] for t in other.get("/api/surveys/templates").json]
        )
        deadline = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        self.assertEqual(
            self.post(
                other,
                "/api/patients/5/surveys",
                {"template_id": ident, "due_at": deadline},
                csrf,
            ).status_code,
            404,
        )
        self.assertEqual(
            self.post(
                self.doctor,
                "/api/patients/2/surveys",
                {"template_id": ident, "due_at": deadline},
            ).status_code,
            201,
        )
        with sqlite3.connect(self.path) as con:
            con.execute(
                "UPDATE survey_templates SET schema_json='[]' WHERE id=?", (ident,)
            )
        self.assertEqual(
            self.detail()["care"]["surveys"][0]["questions"][0]["label"], "Что обсудим?"
        )

    def test_cancellation_stops_assignment_and_enforces_ownership(self):
        ident = self.assign(1)
        self.assertEqual(
            self.post(self.patient, f"/api/surveys/{ident}/cancel", {}).status_code, 403
        )
        self.assertEqual(
            self.post(self.doctor, f"/api/surveys/{ident}/cancel", {}).status_code, 200
        )
        self.assertEqual(
            self.post(
                self.patient,
                f"/api/surveys/{ident}/submit",
                {"answers": {"1": 5, "2": True, "3": ""}},
            ).status_code,
            409,
        )
        self.assertEqual(self.detail()["care"]["surveys"][0]["status"], "cancelled")

    def test_contact_phone_alias_cannot_collide(self):
        self.assertEqual(
            self.post(
                self.doctor, "/api/contact", {"phone": "+70000000002"}
            ).status_code,
            409,
        )
        self.assertEqual(
            self.post(
                self.doctor,
                "/api/contact",
                {
                    "phone": "+7 (000) 000-00-11",
                    "profession": "Психотерапевт",
                    "organization": "Демо",
                },
            ).status_code,
            200,
        )
        self.login("+7 (000) 000-00-11")

    def test_survey_late_answers_are_accepted(self):
        ident = self.assign()
        with sqlite3.connect(self.path) as con:
            con.execute(
                "UPDATE survey_assignments SET due_at=? WHERE id=?",
                ((datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(), ident),
            )
        self.assertTrue(self.detail()["care"]["surveys"][0]["overdue"])
        self.assertEqual(
            self.post(
                self.patient,
                f"/api/surveys/{ident}/submit",
                {"answers": {"1": 5, "2": True, "3": ""}},
            ).status_code,
            201,
        )

    def test_prescription_marks_stop_and_access(self):
        ident = self.prescribe()
        day = local_today().isoformat()
        data = {"day": day, "time": "00:00", "status": "taken"}
        for _ in range(2):
            self.assertEqual(
                self.post(
                    self.patient,
                    f"/api/prescriptions/{ident}/mark",
                    data,
                    key="mark-once",
                ).status_code,
                200,
            )
        self.assertEqual(len(self.detail()["care"]["medication_marks"]), 1)
        other, csrf = self.login("patient-b")
        self.assertEqual(
            self.post(
                other, f"/api/prescriptions/{ident}/mark", data, csrf
            ).status_code,
            404,
        )
        self.assertEqual(
            self.post(
                self.patient, f"/api/prescriptions/{ident}/stop", {"note": "Демо"}
            ).status_code,
            403,
        )
        self.assertEqual(
            self.post(
                self.doctor, f"/api/prescriptions/{ident}/stop", {"note": "Демо отмена"}
            ).status_code,
            200,
        )
        self.assertEqual(
            self.post(
                self.patient,
                f"/api/prescriptions/{ident}/mark",
                {**data, "status": "skipped"},
            ).status_code,
            409,
        )

    def test_prescription_incompatibility_and_bad_time(self):
        today = local_today().isoformat()
        data = {
            "choice": "demo-beta",
            "times": ["09:00"],
            "starts_on": today,
            "ends_on": today,
            "note": "Демо",
        }
        self.assertEqual(
            self.post(self.doctor, "/api/patients/2/prescriptions", data).status_code,
            409,
        )
        self.assertEqual(
            self.post(
                self.doctor,
                "/api/patients/2/prescriptions",
                {**data, "choice": "demo-alpha", "times": ["99:99"]},
            ).status_code,
            400,
        )

    def test_encounters_labs_and_document_access(self):
        r = self.post(
            self.doctor,
            "/api/patients/2/labs",
            {
                "title": "ДЕМО-анализ",
                "result": "Маркер 7 усл. ед.",
                "note": "Вымышленный",
            },
        )
        self.assertEqual(r.status_code, 201)
        ident = r.json["id"]
        response = self.patient.get(f"/api/labs/{ident}/download")
        self.assertEqual(response.status_code, 200)
        self.assertIn("СИНТЕТИЧЕСКИЙ", response.data.decode())
        other, _ = self.login("patient-b")
        self.assertEqual(other.get(f"/api/labs/{ident}/download").status_code, 404)
        self.assertEqual(
            self.post(
                self.patient,
                "/api/patients/2/encounters",
                {"title": "Нельзя", "summary": "Демо", "plan": "Демо"},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.post(
                self.doctor,
                "/api/patients/2/encounters",
                {
                    "title": "Встреча",
                    "summary": "Обсудили дневник",
                    "plan": "Согласовали новую встречу",
                },
            ).status_code,
            201,
        )
        self.assertEqual(
            self.detail(self.patient)["care"]["encounters"][0]["title"], "Встреча"
        )

    def test_invite_creates_bound_card_and_phone_login(self):
        invite = self.post(self.doctor, "/api/invites", {}).json["token"]
        public = self.app.test_client()
        self.assertEqual(
            public.post("/api/intake/info", json={"token": invite}).status_code, 200
        )
        data = {
            "token": invite,
            "doctor_id": 4,
            "name": "Синтетический Новый",
            "sex": "Мужской",
            "age": 30,
            "height": 180,
            "weight": 75,
            "phone": "+70000000991",
            "context": "Вымышленный контекст",
            "password": "new-demo-password",
        }
        result = public.post("/api/intake/register", json=data)
        self.assertEqual(result.status_code, 201, result.json)
        ident = result.json["id"]
        self.assertIn(ident, [p["id"] for p in self.doctor.get("/api/patients").json])
        new, csrf = self.login(data["phone"], data["password"])
        self.assertEqual(
            new.get(f"/api/patients/{ident}").json["patient"]["doctor_id"], 1
        )
        self.assertEqual(
            public.post("/api/intake/register", json=data).status_code, 410
        )
        self.assertEqual(self.patient.get(f"/api/patients/{ident}").status_code, 404)

    def test_invite_expiry_and_duplicate_phone(self):
        invite = self.post(self.doctor, "/api/invites", {}).json["token"]
        data = {
            "token": invite,
            "name": "Демо Имя",
            "sex": "Женский",
            "age": 28,
            "height": 168,
            "weight": 60,
            "phone": "+70000000002",
            "context": "",
            "password": "demo-pass-new",
        }
        client = self.app.test_client()
        self.assertEqual(
            client.post("/api/intake/register", json=data).status_code, 409
        )
        with sqlite3.connect(self.path) as con:
            con.execute("UPDATE invites SET expires_at=0")
        self.assertEqual(
            client.post("/api/intake/info", json={"token": invite}).status_code, 410
        )

    def test_telegram_flow_deduplicates_and_activates(self):
        invite = self.post(self.doctor, "/api/invites", {}).json["token"]
        texts = [
            "/start " + invite,
            "Тестовый Пациент",
            "Женский",
            "28",
            "170",
            "65",
            "+70000000992",
            "Синтетическая анкета",
            "Подтверждаю",
        ]
        with patch.dict(
            os.environ, {"COMPASS_PUBLIC_URL": "http://localhost:8000"}
        ), self.app.app_context():
            for i, text in enumerate(texts):
                update = {
                    "update_id": i + 1,
                    "message": {"chat": {"id": 900, "type": "private"}, "text": text},
                }
                handle_update(update)
                handle_update(update)
            self.assertEqual(
                db().execute("SELECT COUNT(*) FROM users").fetchone()[0], 6
            )
            body = (
                db()
                .execute("SELECT body FROM telegram_outbox ORDER BY id DESC LIMIT 1")
                .fetchone()[0]
            )
            self.assertTrue(body.startswith("pcenc:v1:outbox:"))
            token = unseal(body, "outbox").split("#activate=")[1].split("\n")[0]
        public = self.app.test_client()
        self.assertEqual(
            public.post(
                "/api/intake/activate",
                json={"token": token, "password": "active-pass-new"},
            ).status_code,
            200,
        )
        self.assertEqual(
            public.post(
                "/api/intake/activate",
                json={"token": token, "password": "active-pass-new"},
            ).status_code,
            410,
        )
        self.login("+70000000992", "active-pass-new")

    def test_reminders_and_escalation_are_durable_and_once(self):
        ident = self.assign()
        report = dict(
            mood=3,
            anxiety=8,
            adherence="Да",
            adverse_effects="",
            note="Демо",
            safety_signal=True,
        )
        self.assertEqual(
            self.post(self.patient, "/api/patients/2/reports", report).status_code, 201
        )
        with self.app.app_context():
            with db() as con:
                con.execute(
                    "UPDATE alerts SET created_at=?",
                    ((datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),),
                )
            reminders_and_escalations()
            reminders_and_escalations()
            self.assertEqual(
                db().execute("SELECT COUNT(*) FROM escalations").fetchone()[0], 1
            )
            self.assertEqual(
                db()
                .execute(
                    "SELECT COUNT(*) FROM reminder_events WHERE key=?",
                    ("survey-due:" + str(ident),),
                )
                .fetchone()[0],
                1,
            )
        self.assertEqual(
            self.doctor.get("/api/escalations").json[0]["status"], "protocol_pending"
        )
        self.assertEqual(self.patient.get("/api/escalations").status_code, 403)

    def subscription(self):
        key = (
            ec.generate_private_key(ec.SECP256R1())
            .public_key()
            .public_bytes(
                serialization.Encoding.X962,
                serialization.PublicFormat.UncompressedPoint,
            )
        )
        b64 = lambda b: base64.urlsafe_b64encode(b).decode().rstrip("=")
        return {
            "endpoint": "https://fcm.googleapis.com/fcm/send/synthetic-test-endpoint",
            "keys": {"auth": b64(b"x" * 16), "p256dh": b64(key)},
        }

    def test_push_subscription_validation_queue_and_retry(self):
        subscription = self.subscription()
        self.assertEqual(
            self.post(
                self.patient,
                "/api/push/subscribe",
                {
                    "subscription": {
                        **subscription,
                        "endpoint": "https://127.0.0.1/private",
                    }
                },
            ).status_code,
            400,
        )
        self.assertEqual(
            self.post(
                self.patient, "/api/push/subscribe", {"subscription": subscription}
            ).status_code,
            200,
        )
        key = self.patient.get("/api/push/key").json["public_key"]
        self.assertTrue(key)
        self.post(
            self.doctor,
            "/api/patients/2/decisions",
            {"decision": "Другое", "note": "Демо решение"},
        )
        with self.app.app_context():
            reminders_and_escalations()
            with patch(
                "compass.delivery.webpush",
                side_effect=RuntimeError("transport unavailable"),
            ):
                dispatch_push()
            row = db().execute("SELECT * FROM push_jobs").fetchone()
            self.assertEqual(row["status"], "pending")
            self.assertEqual(row["attempts"], 1)
            with db() as con:
                con.execute("UPDATE push_jobs SET next_attempt=0")
            with patch("compass.delivery.webpush") as transport:
                dispatch_push()
                self.assertTrue(transport.called)
                message = json.loads(transport.call_args.kwargs["data"])
                self.assertNotIn("Демо решение", message["body"])
            self.assertEqual(
                db().execute("SELECT status FROM push_jobs").fetchone()[0], "sent"
            )

    def test_ai_api_transport_persists_only_draft(self):
        captured = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                captured.append(body)
                content = json.dumps(
                    {
                        "choices": [
                            {
                                "message": {
                                    "content": "Синтетическая сводка от тестового HTTP-провайдера"
                                }
                            }
                        ]
                    },
                    ensure_ascii=False,
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.dict(
                os.environ,
                {
                    "COMPASS_AI_BASE_URL": f"http://127.0.0.1:{server.server_port}/v1",
                    "COMPASS_AI_MODEL": "test-model",
                    "COMPASS_AI_API_KEY": "test-only-not-a-real-key",
                },
            ):
                result = self.post(
                    self.doctor,
                    "/api/patients/2/assistant",
                    {"question": "Сводка динамики"},
                )
                self.assertEqual(result.status_code, 200, result.json)
                self.assertEqual(result.json["kind"], "ai-draft")
                self.assertEqual(captured[0]["model"], "test-model")
                self.assertTrue(self.doctor.get("/api/patients/2/assistant").json)
                self.assertEqual(self.detail()["profile"]["plan"], "")
                self.assertEqual(self.detail()["decisions"], [])
                self.assertEqual(
                    self.post(
                        self.patient,
                        "/api/patients/2/assistant",
                        {"question": "Нельзя"},
                    ).status_code,
                    403,
                )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_generated_survey_is_validated_draft_until_specialist_saves(self):
        draft = {
            "title": "Черновик ИИ",
            "description": "Учебный",
            "questions": [{"label": "Как прошёл день?", "type": "scale"}],
        }
        before = len(self.doctor.get("/api/surveys/templates").json)
        with patch(
            "compass.assistants.complete",
            return_value=json.dumps(draft, ensure_ascii=False),
        ):
            result = self.post(
                self.doctor, "/api/surveys/generate", {"prompt": "Создай учебный опрос"}
            )
        self.assertEqual(result.status_code, 200, result.json)
        self.assertEqual(result.json["kind"], "ai-draft")
        self.assertEqual(len(self.doctor.get("/api/surveys/templates").json), before)
        self.assertEqual(
            self.post(self.doctor, "/api/surveys/templates", result.json).status_code,
            201,
        )
        with patch("compass.assistants.complete", return_value='{"questions":[]}'):
            self.assertEqual(
                self.post(
                    self.doctor, "/api/surveys/generate", {"prompt": "Демо"}
                ).status_code,
                503,
            )
        self.assertEqual(
            len(self.doctor.get("/api/surveys/templates").json), before + 1
        )

    def test_ai_missing_settings_is_explicit_not_fake(self):
        with patch.dict(
            os.environ,
            {
                "COMPASS_AI_BASE_URL": "",
                "COMPASS_AI_MODEL": "",
                "COMPASS_AI_API_KEY": "",
            },
        ):
            r = self.post(
                self.doctor, "/api/patients/2/assistant", {"question": "Сводка"}
            )
            self.assertEqual(r.status_code, 503)
            self.assertIn("не подключён", r.json["error"])
        self.assertEqual(self.doctor.get("/api/patients/2/assistant").json, [])


if __name__ == "__main__":
    unittest.main()
