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

    def assigned_data(self, kind, answers):
        response = self.doctor.post(
            "/api/patients/2/assessment-assignments",
            json={"kind": kind, "due_at": "2030-01-01T12:00:00Z"},
            headers={"X-CSRF-Token": self.dc},
        )
        self.assertEqual(response.status_code, 201, response.json)
        return {"kind": kind, "answers": answers, "assignment_id": response.json["id"]}

    def test_demo_forms_exercises_and_role_validation(self):
        for kind in [
            "leonhard",
            "spielberger",
            "hcl33",
            "mdq",
            "dembo",
            "cope",
        ]:
            path = "/api/patients/2/assessments"
            result = self.patient.post(
                path,
                json=self.assigned_data(kind, [1] * 6),
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
            json=self.assigned_data("serial7", [100 - 7 * (i + 1) for i in range(13)]),
            headers={"X-CSRF-Token": self.pc},
        )
        self.patient.post(
            path,
            json=self.assigned_data("schulte", [27]),
            headers={"X-CSRF-Token": self.pc},
        )
        results = self.doctor.get("/api/patients/2/workspace").json["assessments"]
        self.assertEqual(
            next(r for r in results if r["kind"] == "serial7")["score"], 13
        )
        self.assertEqual(
            next(r for r in results if r["kind"] == "schulte")["score"], 27
        )
        self.assertEqual(next(r for r in results if r["kind"] == "cope")["score"], 0)

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

    def test_assignment_required_single_use_cancelled_and_bound(self):
        path = "/api/patients/2/assessments"
        headers = {"X-CSRF-Token": self.pc}
        self.assertEqual(
            self.patient.post(
                path, json={"kind": "cope", "answers": [1] * 6}, headers=headers
            ).status_code,
            403,
        )
        data = self.assigned_data("cope", [1] * 6)
        self.assertEqual(
            self.patient.post(
                "/api/patients/2/assessment-assignments",
                json={"kind": "cope", "due_at": "2030-01-01T12:00:00Z"},
                headers=headers,
            ).status_code,
            403,
        )
        self.assertEqual(
            self.patient.post(
                path, json={**data, "kind": "leonhard"}, headers=headers
            ).status_code,
            403,
        )
        self.assertEqual(
            self.patient.post(path, json=data, headers=headers).status_code, 201
        )
        self.assertEqual(
            self.patient.post(path, json=data, headers=headers).status_code, 409
        )
        assignments = self.patient.get("/api/patients/2/workspace").json[
            "assessment_assignments"
        ]
        self.assertEqual(assignments[0]["status"], "completed")
        data = self.assigned_data("cope", [1] * 6)
        response = self.doctor.post(
            f"/api/patients/2/assessment-assignments/{data['assignment_id']}/cancel",
            json={},
            headers={"X-CSRF-Token": self.dc},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.patient.post(path, json=data, headers=headers).status_code, 409
        )
        other = self.app.test_client()
        csrf = other.post(
            "/api/auth/login",
            json={"username": "patient-b", "password": "compass-demo"},
        ).json["csrf"]
        self.assertEqual(
            other.post(
                "/api/patients/3/assessments", json=data, headers={"X-CSRF-Token": csrf}
            ).status_code,
            403,
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
