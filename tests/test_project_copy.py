from pathlib import Path
import tempfile
import unittest

from app import create_app
from compass.db import db


class ProjectCopyTest(unittest.TestCase):
    def test_seed_is_repeatable_and_preserves_user_letters(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "demo.db"
            app = create_app(path, testing=True)
            with app.app_context(), db() as con:
                self.assertEqual(
                    con.execute("SELECT count(*) FROM care_letters").fetchone()[0], 4
                )
                before = con.execute("SELECT count(*) FROM forum_threads").fetchone()[0]
                con.execute(
                    "INSERT INTO care_letters(patient_id,sender_id,category,subject,body,created_at) VALUES(2,2,'Другое','Личное письмо','Мой текст','2026-10-24T12:00:00Z')"
                )
            reopened = create_app(path, testing=True)
            with reopened.app_context():
                self.assertEqual(
                    db().execute("SELECT count(*) FROM care_letters").fetchone()[0], 5
                )
                self.assertEqual(
                    db().execute("SELECT count(*) FROM forum_threads").fetchone()[0],
                    before,
                )
                self.assertEqual(
                    db()
                    .execute(
                        "SELECT body FROM care_letters WHERE subject='Личное письмо'"
                    )
                    .fetchone()[0],
                    "Мой текст",
                )

    def test_licensed_forms_are_not_available_online(self):
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(Path(directory) / "demo.db", testing=True)
            doctor, patient = app.test_client(), app.test_client()
            dc = doctor.post(
                "/api/auth/login",
                json={"username": "doctor", "password": "compass-demo"},
            ).json["csrf"]
            pc = patient.post(
                "/api/auth/login",
                json={"username": "patient-a", "password": "compass-demo"},
            ).json["csrf"]
            for kind in ["mmpi", "beck_hopelessness", "beck_depression"]:
                r = doctor.post(
                    "/api/patients/2/assessment-assignments",
                    json={"kind": kind, "due_at": "2030-01-01T12:00:00Z"},
                    headers={"X-CSRF-Token": dc},
                )
                self.assertEqual(r.status_code, 403)
                self.assertIn("по лицензии", r.json["error"])
                self.assertEqual(
                    patient.post(
                        "/api/patients/2/assessments",
                        json={"kind": kind, "answers": [1] * 6},
                        headers={"X-CSRF-Token": pc},
                    ).status_code,
                    403,
                )
