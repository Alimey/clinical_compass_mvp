"""Persistence, role boundaries and validation for the prototype's new workflows."""

import tempfile
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

from app import create_app


class WellbeingTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "test.db"
        self.app = create_app(self.path, seed_demo=False, testing=True)
        self.patient, self.pc = self.login("patient-a")
        self.doctor, self.dc = self.login("doctor")
        self.other, self.oc = self.login("doctor-other")

    def tearDown(self):
        self.temp.cleanup()

    def login(self, name):
        client = self.app.test_client()
        response = client.post(
            "/api/auth/login", json={"username": name, "password": "compass-demo"}
        )
        self.assertEqual(response.status_code, 200)
        return client, response.json["csrf"]

    def post(self, client, csrf, data, path="wellbeing", key=None):
        headers = {"X-CSRF-Token": csrf}
        if key:
            headers["Idempotency-Key"] = key
        return client.post("/api/patients/2/" + path, json=data, headers=headers)

    def test_sleep_and_energy_persist_and_legacy_payload_still_works(self):
        data = {
            "mood": 6,
            "anxiety": 3,
            "adherence": "Да",
            "safety_signal": False,
            "note": "",
            "adverse_effects": "",
        }
        self.assertEqual(
            self.post(self.patient, self.pc, data, "reports").status_code, 201
        )
        data.update(sleep=7, energy=8)
        self.assertEqual(
            self.post(self.patient, self.pc, data, "reports").status_code, 201
        )
        reports = self.doctor.get("/api/patients/2").json["reports"]
        self.assertEqual((reports[0]["sleep"], reports[0]["energy"]), (7, 8))
        self.assertEqual((reports[1]["sleep"], reports[1]["energy"]), (None, None))
        # Reopening an existing database preserves the new data.
        reopened = create_app(self.path, seed_demo=False, testing=True)
        self.assertEqual(reopened.test_client().get("/api/health").status_code, 200)
        self.assertEqual(
            self.patient.get("/api/patients/2").json["reports"][0]["sleep"], 7
        )

    def test_tree_taps_are_owned_durable_idempotent_and_do_not_create_health_records(
        self,
    ):
        for _ in range(2):
            result = self.post(self.patient, self.pc, {}, "tree", key="flower-1")
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json["blossoms"], 1)
        self.assertEqual(
            self.post(self.patient, self.pc, {}, "tree").json["blossoms"], 2
        )
        data = self.patient.get("/api/patients/2/wellbeing").json
        self.assertEqual(data["tree_blossoms"], 2)
        self.assertEqual(data["activities"], [])
        self.assertEqual(self.patient.get("/api/patients/2").json["reports_total"], 0)
        self.assertEqual(self.post(self.doctor, self.dc, {}, "tree").status_code, 403)
        self.assertEqual(self.other.get("/api/patients/2/wellbeing").status_code, 404)
        self.assertEqual(
            self.patient.post(
                "/api/patients/3/tree", json={}, headers={"X-CSRF-Token": self.pc}
            ).status_code,
            404,
        )
        self.assertEqual(
            self.patient.post("/api/patients/2/tree", json={}).status_code, 403
        )
        reopened = create_app(self.path, seed_demo=False, testing=True)
        client = reopened.test_client()
        client.post(
            "/api/auth/login",
            json={"username": "patient-a", "password": "compass-demo"},
        )
        self.assertEqual(
            client.get("/api/patients/2/wellbeing").json["tree_blossoms"], 2
        )

    def test_calendar_plans_complete_once_and_can_be_cancelled_and_readded(self):
        today = datetime.now(ZoneInfo("Europe/Moscow")).date().isoformat()
        result = self.post(
            self.patient, self.pc, {"activity": "walk", "day": today}, "activity-plans"
        )
        self.assertEqual(result.status_code, 200)
        ident = result.json["id"]
        duplicate = self.post(
            self.patient, self.pc, {"activity": "walk", "day": today}, "activity-plans"
        )
        self.assertEqual(duplicate.json["id"], ident)
        path = f"activity-plans/{ident}/cancel"
        self.assertEqual(self.post(self.patient, self.pc, {}, path).status_code, 200)
        self.assertEqual(
            self.post(
                self.patient, self.pc, {}, f"activity-plans/{ident}/complete"
            ).status_code,
            400,
        )
        self.post(
            self.patient, self.pc, {"activity": "walk", "day": today}, "activity-plans"
        )
        for _ in range(2):
            self.assertEqual(
                self.post(
                    self.patient, self.pc, {}, f"activity-plans/{ident}/complete"
                ).status_code,
                200,
            )
        data = self.doctor.get("/api/patients/2/wellbeing").json
        self.assertEqual(len(data["activities"]), 1)
        self.assertEqual(data["plans"][0]["status"], "done")
        self.assertEqual(
            data["plans"][0]["completed_at"], data["activities"][0]["created_at"]
        )
        self.assertEqual(self.post(self.patient, self.pc, {}, path).status_code, 400)

    def test_calendar_validates_dates_keys_ownership_and_future_completion(self):
        today = datetime.now(ZoneInfo("Europe/Moscow")).date()
        tomorrow = (today + timedelta(days=1)).isoformat()
        for key, day in [
            ("stretch", str(today)),
            ("breathing", str(today)),
            ("walk", "2026-02-30"),
            ("walk", None),
            ("walk", (today + timedelta(days=367)).isoformat()),
        ]:
            self.assertEqual(
                self.post(
                    self.patient,
                    self.pc,
                    {"activity": key, "day": day},
                    "activity-plans",
                ).status_code,
                400,
            )
        ident = self.post(
            self.patient,
            self.pc,
            {"activity": "desk", "day": tomorrow},
            "activity-plans",
        ).json["id"]
        self.assertEqual(
            self.post(
                self.patient, self.pc, {}, f"activity-plans/{ident}/complete"
            ).status_code,
            400,
        )
        self.assertEqual(
            self.post(
                self.doctor,
                self.dc,
                {"activity": "desk", "day": str(today)},
                "activity-plans",
            ).status_code,
            403,
        )
        self.assertEqual(
            self.patient.post(
                f"/api/patients/3/activity-plans/{ident}/cancel",
                json={},
                headers={"X-CSRF-Token": self.pc},
            ).status_code,
            404,
        )
        self.assertEqual(
            self.post(
                self.patient, self.pc, {}, "activity-plans/9999/cancel"
            ).status_code,
            404,
        )

    def test_observation_period_is_from_existing_records_not_occupation(self):
        data = {
            "mood": 5,
            "anxiety": 4,
            "adherence": "Да",
            "safety_signal": False,
            "note": "",
            "adverse_effects": "",
        }
        self.post(self.patient, self.pc, data, "reports")
        record = self.doctor.get("/api/patients").json[0]
        self.assertEqual(
            record["observed_since"],
            self.patient.get("/api/patients/2").json["reports"][0]["created_at"],
        )

    def test_counter_start_uses_server_clock_and_is_private_and_idempotent(self):
        first = self.post(self.patient, self.pc, {}, "counter/start", key="counter-1")
        self.assertEqual(first.status_code, 200)
        prefs = self.patient.get("/api/patients/2/workspace").json["preferences"]
        self.assertTrue(prefs["streak_on"])
        self.assertLessEqual(
            datetime.fromisoformat(prefs["streak_start"]), datetime.now(ZoneInfo("UTC"))
        )
        self.post(self.patient, self.pc, {}, "counter/start", key="counter-1")
        self.assertEqual(
            self.patient.get("/api/patients/2/workspace").json["preferences"][
                "streak_start"
            ],
            prefs["streak_start"],
        )
        self.assertNotIn(
            "streak_start",
            self.doctor.get("/api/patients/2/workspace").json["preferences"],
        )
        self.assertEqual(
            self.post(self.doctor, self.dc, {}, "counter/start").status_code, 403
        )

    def test_invalid_wellbeing_values_never_write_reports(self):
        base = {
            "mood": 6,
            "anxiety": 3,
            "adherence": "Да",
            "safety_signal": False,
            "note": "",
            "adverse_effects": "",
        }
        for field in ("sleep", "energy"):
            for value in (-1, 11, True, "5", 3.5):
                with self.subTest(field=field, value=value):
                    result = self.post(
                        self.patient, self.pc, {**base, field: value}, "reports"
                    )
                    self.assertEqual(result.status_code, 400)
        self.assertEqual(self.patient.get("/api/patients/2").json["reports_total"], 0)

    def test_activity_is_owned_and_readable_by_assigned_specialist(self):
        response = self.post(self.patient, self.pc, {"activity": "breathing"})
        self.assertEqual(response.status_code, 201)
        items = self.doctor.get("/api/patients/2/wellbeing").json["activities"]
        self.assertEqual(items[0]["title"], "Спокойная пауза")
        self.assertEqual(items[0]["duration_seconds"], 60)
        self.assertEqual(self.other.get("/api/patients/2/wellbeing").status_code, 404)
        self.assertEqual(
            self.post(self.doctor, self.dc, {"activity": "breathing"}).status_code, 403
        )
        self.assertEqual(
            self.patient.post(
                "/api/patients/3/wellbeing",
                json={"activity": "breathing"},
                headers={"X-CSRF-Token": self.pc},
            ).status_code,
            404,
        )

    def test_lesson_and_retry_do_not_duplicate_but_new_practice_can(self):
        first = self.post(
            self.patient, self.pc, {"activity": "diary"}, key="lesson-first"
        )
        second = self.post(
            self.patient, self.pc, {"activity": "diary"}, key="lesson-repeat"
        )
        self.assertEqual(first.json["id"], second.json["id"])
        for _ in range(2):
            self.assertEqual(
                self.post(
                    self.patient, self.pc, {"activity": "grounding"}, key="same-session"
                ).status_code,
                201,
            )
        self.assertEqual(
            self.post(
                self.patient, self.pc, {"activity": "grounding"}, key="new-session"
            ).status_code,
            201,
        )
        data = self.patient.get("/api/patients/2/wellbeing").json
        self.assertEqual(data["lessons"], ["diary"])
        self.assertEqual(len(data["activities"]), 3)

    def test_activity_rejects_unknown_or_malformed_key_and_requires_csrf(self):
        for key in ("real-diagnosis", None, [], {"activity": "diary"}):
            self.assertEqual(
                self.post(self.patient, self.pc, {"activity": key}).status_code, 400
            )
        self.assertEqual(
            self.patient.post(
                "/api/patients/2/wellbeing", json={"activity": "diary"}
            ).status_code,
            403,
        )
        self.assertEqual(
            len(self.patient.get("/api/patients/2/wellbeing").json["activities"]), 0
        )
