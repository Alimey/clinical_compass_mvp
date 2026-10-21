"""Authorization and durable records for all sections of the mobile mockup."""

import tempfile
import unittest
from pathlib import Path

from app import create_app


class SectionsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = create_app(Path(self.temp.name) / "test.db", testing=True)
        self.users = {}
        for name in ("doctor", "patient-a", "patient-b", "doctor-other", "relative"):
            client = self.app.test_client()
            response = client.post(
                "/api/auth/login", json={"username": name, "password": "compass-demo"}
            )
            self.assertEqual(response.status_code, 200)
            self.users[name] = (client, response.json["csrf"])

    def tearDown(self):
        self.temp.cleanup()

    def get(self, name, path):
        return self.users[name][0].get(path)

    def post(self, name, path, data, key=None):
        client, csrf = self.users[name]
        headers = {"X-CSRF-Token": csrf}
        if key:
            headers["Idempotency-Key"] = key
        return client.post(path, json=data, headers=headers)

    def workspace(self, name="patient-a"):
        return self.get(name, "/api/patients/2/workspace").json

    def test_relative_is_separate_role_and_never_receives_private_card(self):
        self.assertEqual(
            self.get("relative", "/api/relative").json["patients"][0]["id"], 2
        )
        for path in (
            "/api/patients/2",
            "/api/patients/2/messages",
            "/api/patients/2/workspace",
            "/api/patients/2/wellbeing",
        ):
            self.assertEqual(self.get("relative", path).status_code, 404, path)
        self.assertEqual(self.get("patient-a", "/api/relative").status_code, 403)
        self.assertEqual(
            self.get("doctor-other", "/api/patients/2/workspace").status_code, 404
        )

    def test_relative_consent_revokes_access_and_optional_fields_are_enforced(self):
        self.post(
            "patient-a",
            "/api/patients/2/preferences",
            {"relative_adherence": True, "relative_wellbeing": True},
        )
        person = self.get("relative", "/api/relative").json["patients"][0]
        self.assertIn("adherence", person)
        self.assertIn("wellbeing", person)
        self.assertNotIn("reports", person)
        self.post("patient-a", "/api/patients/2/preferences", {"relative_sos": False})
        self.assertEqual(self.get("relative", "/api/relative").json["patients"], [])
        self.assertTrue(self.workspace()["consent_history"])

    def test_private_notes_and_streak_do_not_reach_specialist_or_audit(self):
        self.post(
            "patient-a",
            "/api/patients/2/entries",
            {"kind": "note", "text": "private-only-marker", "shared": False},
        )
        self.post(
            "patient-a",
            "/api/patients/2/entries",
            {"kind": "thought", "situation": "shared-marker", "shared": True},
        )
        self.post(
            "patient-a",
            "/api/patients/2/preferences",
            {"streak_on": True, "streak_best": 12},
        )
        own = self.workspace()
        doctor = self.workspace("doctor")
        self.assertEqual(len(own["entries"]), 2)
        self.assertEqual(len(doctor["entries"]), 1)
        self.assertNotIn("streak_on", doctor["preferences"])
        self.assertNotIn(
            "streak_", str(self.get("doctor", "/api/patients/2/audit").json)
        )
        self.assertNotIn("private-only-marker", str(doctor))
        self.assertNotIn(
            "private-only-marker", str(self.get("doctor", "/api/patients/2/audit").json)
        )

    def test_diary_consent_removes_reports_from_specialist_detail_and_list(self):
        self.assertTrue(self.get("doctor", "/api/patients/2").json["reports"])
        self.post("patient-a", "/api/patients/2/preferences", {"share_mood": False})
        self.assertEqual(self.get("doctor", "/api/patients/2").json["reports"], [])
        self.assertFalse(self.get("doctor", "/api/patients/2").json["reports_shared"])
        self.assertIsNone(self.get("doctor", "/api/patients").json[0]["mood"])
        self.assertTrue(self.get("patient-a", "/api/patients/2").json["reports"])

    def test_sos_is_durable_once_and_never_claims_emergency_call(self):
        a = self.post("patient-a", "/api/patients/2/sos", {}, "same-sos")
        b = self.post("patient-a", "/api/patients/2/sos", {}, "same-sos")
        self.assertEqual(a.json["id"], b.json["id"])
        self.assertFalse(a.json["emergency_called"])
        events = self.get("relative", "/api/relative").json["patients"][0]["events"]
        self.assertEqual(len(events), 1)
        self.assertEqual(
            self.post(
                "doctor-other", f'/api/support-events/{a.json["id"]}/read', {}
            ).status_code,
            404,
        )
        self.assertEqual(
            self.post(
                "relative", f'/api/support-events/{a.json["id"]}/read', {}
            ).status_code,
            200,
        )
        self.assertEqual(
            self.post(
                "doctor", f'/api/support-events/{a.json["id"]}/read', {}
            ).status_code,
            200,
        )
        self.assertIsNotNone(self.workspace()["events"][0]["doctor_read_at"])

    def test_scales_validate_every_answer_and_keep_scores_with_specialist(self):
        self.assertEqual(
            self.post(
                "patient-a", "/api/patients/2/assessments", {"kind": [], "answers": []}
            ).status_code,
            400,
        )
        self.assertEqual(
            self.post("patient-a", "/api/patients/2/entries", {"kind": {}}).status_code,
            400,
        )
        for data in (
            {"kind": "gad7", "answers": [0] * 6},
            {"kind": "gad7", "answers": [True] * 7},
            {"kind": "hama", "answers": [0] * 14},
        ):
            self.assertIn(
                self.post("patient-a", "/api/patients/2/assessments", data).status_code,
                (400, 403),
            )
        response = self.post(
            "patient-a",
            "/api/patients/2/assessments",
            {"kind": "phq9", "answers": [1] * 9},
        )
        self.assertEqual(response.status_code, 201)
        self.assertNotIn("score", self.workspace()["assessments"][0])
        self.assertEqual(self.workspace("doctor")["assessments"][0]["score"], 9)
        # A scale safety item is not shared with the relative as an SOS.
        self.assertEqual(
            self.get("relative", "/api/relative").json["patients"][0]["events"], []
        )
        self.assertEqual(
            self.post(
                "doctor",
                "/api/patients/2/assessments",
                {"kind": "hama", "answers": [2] * 14},
            ).status_code,
            201,
        )

    def test_safety_plan_agreement_and_patient_acknowledgement(self):
        body = {
            k: "Синтетический пункт"
            for k in ("signs", "self", "distract", "people", "pros", "safe")
        }
        self.assertEqual(
            self.post("patient-a", "/api/patients/2/safety-plan", body).status_code, 403
        )
        self.assertEqual(
            self.post("doctor", "/api/patients/2/safety-plan", body).status_code, 200
        )
        self.assertEqual(self.workspace()["plan"]["body"], body)
        self.post(
            "doctor",
            "/api/patients/2/agreement",
            {"body": "Учебные договорённости", "days": 28},
        )
        self.assertEqual(
            self.post(
                "patient-a", "/api/patients/2/agreement", {"accepted": True}
            ).status_code,
            200,
        )
        self.assertTrue(self.workspace()["agreement"]["patient_signed_at"])
        self.assertEqual(
            self.post(
                "patient-b", "/api/patients/2/agreement", {"accepted": True}
            ).status_code,
            404,
        )

    def test_letters_replies_and_forum_persist_with_role_checks(self):
        sent = self.post(
            "patient-a",
            "/api/patients/2/letters",
            {
                "category": "Документы",
                "subject": "Тема",
                "body": "Синтетическое письмо",
            },
        )
        self.assertEqual(sent.status_code, 201)
        ident = sent.json["id"]
        self.assertEqual(
            self.post(
                "doctor-other", f"/api/letters/{ident}/reply", {"body": "Ответ"}
            ).status_code,
            404,
        )
        self.assertEqual(
            self.post(
                "doctor", f"/api/letters/{ident}/reply", {"body": "Ответ специалиста"}
            ).status_code,
            200,
        )
        self.assertEqual(self.workspace()["letters"][0]["reply"], "Ответ специалиста")
        thread = self.post(
            "doctor",
            "/api/forum",
            {
                "title": "Новая тема",
                "category": "Вопрос коллегам",
                "body": "Синтетический вопрос",
            },
        )
        self.assertEqual(thread.status_code, 201)
        ident = thread.json["id"]
        self.assertEqual(
            self.post(
                "doctor-other", f"/api/forum/{ident}/posts", {"body": "Ответ коллеги"}
            ).status_code,
            201,
        )
        self.assertEqual(
            len(self.get("doctor", f"/api/forum/{ident}").json["posts"]), 2
        )
        self.assertEqual(self.get("patient-a", "/api/forum").status_code, 403)

    def test_research_export_requires_consent_and_never_contains_free_text(self):
        self.assertEqual(self.get("doctor", "/api/research").json, [])
        self.post("patient-a", "/api/patients/2/preferences", {"research": True})
        data = self.get("doctor", "/api/research").json
        self.assertEqual(len(data), 1)
        self.assertEqual(
            set(data[0]),
            {"code", "age_band", "sex", "reports", "mood_mean", "anxiety_mean"},
        )
        csv = self.get("doctor", "/api/research.csv").data.decode()
        for word in ("Морозова", "+7000", "note", "chat"):
            self.assertNotIn(word, csv)
        self.assertEqual(self.get("doctor-other", "/api/research").json, [])
        self.post("patient-a", "/api/patients/2/preferences", {"research": False})
        self.assertEqual(self.get("doctor", "/api/research").json, [])
        self.assertEqual(self.get("relative", "/api/research.csv").status_code, 403)

    def test_patient_ai_has_no_canned_fallback(self):
        from unittest.mock import patch

        with patch.dict(
            "os.environ",
            {
                "COMPASS_AI_API_KEY": "",
                "COMPASS_AI_MODEL": "",
                "COMPASS_AI_BASE_URL": "",
            },
        ):
            self.assertEqual(
                self.post(
                    "patient-a",
                    "/api/patients/2/patient-assistant",
                    {"question": "Как вести дневник?"},
                ).status_code,
                503,
            )
