import json
from pathlib import Path
import tempfile
import unittest

from app import create_app
from compass.db import db


class Revision8Test(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = create_app(Path(self.temp.name) / "test.db", testing=True)
        self.patient = self.app.test_client()
        self.pc = self.patient.post(
            "/api/auth/login",
            json={"username": "patient-a", "password": "compass-demo"},
        ).json["csrf"]
        self.doctor = self.app.test_client()
        self.dc = self.doctor.post(
            "/api/auth/login", json={"username": "doctor", "password": "compass-demo"}
        ).json["csrf"]

    def tearDown(self):
        self.temp.cleanup()

    def test_demo_forms_exercises_and_role_validation(self):
        for kind in [
            "mmpi",
            "leonhard",
            "beck_hopelessness",
            "beck_depression",
            "spielberger",
            "hcl33",
            "mdq",
            "dembo",
            "cope",
        ]:
            path = "/api/patients/2/assessments"
            result = self.patient.post(
                path,
                json={"kind": kind, "answers": [1] * 6},
                headers={"X-CSRF-Token": self.pc},
            )
            self.assertEqual(result.status_code, 201, result.json)
            self.assertEqual(
                self.patient.post(
                    path,
                    json={"kind": kind, "answers": [1] * 5},
                    headers={"X-CSRF-Token": self.pc},
                ).status_code,
                400,
            )
            self.assertEqual(
                self.doctor.post(
                    path,
                    json={"kind": kind, "answers": [1] * 6},
                    headers={"X-CSRF-Token": self.dc},
                ).status_code,
                403,
            )
        self.patient.post(
            path,
            json={"kind": "serial7", "answers": [100 - 7 * (i + 1) for i in range(13)]},
            headers={"X-CSRF-Token": self.pc},
        )
        self.patient.post(
            path,
            json={"kind": "schulte", "answers": [27]},
            headers={"X-CSRF-Token": self.pc},
        )
        results = self.doctor.get("/api/patients/2/workspace").json["assessments"]
        self.assertEqual(
            next(r for r in results if r["kind"] == "serial7")["score"], 13
        )
        self.assertEqual(
            next(r for r in results if r["kind"] == "schulte")["score"], 27
        )
        self.assertEqual(next(r for r in results if r["kind"] == "mmpi")["score"], 0)

    def test_counter_title_is_saved_and_private(self):
        result = self.patient.post(
            "/api/patients/2/preferences",
            json={"streak_label": "Дни заботы о себе"},
            headers={"X-CSRF-Token": self.pc},
        )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(
            self.patient.get("/api/patients/2/workspace").json["preferences"][
                "streak_label"
            ],
            "Дни заботы о себе",
        )
        self.assertNotIn(
            "streak_label",
            self.doctor.get("/api/patients/2/workspace").json["preferences"],
        )

    def test_earned_colors_stable_on_refresh(self):
        with self.app.app_context(), db() as con:
            con.execute("UPDATE appointments SET status='completed' WHERE patient_id=2")
            con.execute(
                "INSERT INTO medication_marks(prescription_id,patient_id,day,scheduled_time,status,marked_at) SELECT id,2,'2026-10-24','09:00','taken','2026-10-24T09:00:00Z' FROM prescriptions WHERE patient_id=2 LIMIT 1"
            )
        first = self.patient.get("/api/patients/2/wellbeing").json["tree_rewards"]
        self.assertIn("medication", {f["kind"] for f in first})
        self.assertIn("visit", {f["kind"] for f in first})
        self.assertIn("diary", {f["kind"] for f in first})
        self.assertEqual(
            first, self.patient.get("/api/patients/2/wellbeing").json["tree_rewards"]
        )
        self.assertEqual(len(first), len({f["id"] for f in first}))


if __name__ == "__main__":
    unittest.main()
