"""Persistent tree positions, graph snapshots and genuine-model summary behavior."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app import create_app
from compass.assistants import AssistantUnavailable


class PatientRevision2Test(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "revision2.db"
        self.app = create_app(self.path, seed_demo=False, testing=True)
        self.p, self.pc = self.login("patient-a")
        self.d, self.dc = self.login("doctor")
        self.other, self.oc = self.login("doctor-other")

    def tearDown(self):
        self.temp.cleanup()

    def login(self, name):
        client = self.app.test_client()
        result = client.post(
            "/api/auth/login", json={"username": name, "password": "compass-demo"}
        )
        self.assertEqual(result.status_code, 200)
        return client, result.json["csrf"]

    def post(self, path, data=None, client=None, csrf=None, key=None):
        headers = {"X-CSRF-Token": csrf or self.pc}
        if key:
            headers["Idempotency-Key"] = key
        return (client or self.p).post(
            "/api/patients/2/" + path,
            json={} if data is None else data,
            headers=headers,
        )

    def report(self):
        return self.post(
            "reports",
            {
                "mood": 6,
                "anxiety": 4,
                "sleep": 7,
                "energy": 5,
                "adherence": "Да",
                "safety_signal": False,
                "adverse_effects": "",
                "note": "private-text-not-for-model",
            },
        )

    def test_tree_coordinates_persist_and_retry_does_not_duplicate(self):
        for _ in range(2):
            response = self.post("tree", {"x": 84.5, "y": 142.25}, key="same-flower")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json["flower"]["x"], 84.5)
        data = self.p.get("/api/patients/2/wellbeing").json
        self.assertEqual(len(data["tree_flowers"]), 1)
        self.assertEqual(data["tree_flowers"][0]["y"], 142.25)
        self.assertEqual(data["practice_count"], 0)
        self.assertEqual(data["activities"], [])
        reopened = create_app(self.path, seed_demo=False, testing=True)
        client = reopened.test_client()
        client.post(
            "/api/auth/login",
            json={"username": "patient-a", "password": "compass-demo"},
        )
        self.assertEqual(
            client.get("/api/patients/2/wellbeing").json["tree_flowers"],
            data["tree_flowers"],
        )

    def test_tree_rejects_invalid_positions_and_bounds_stored_flowers(self):
        for value in (-1, 301, True, "150", None, float("nan"), float("inf")):
            self.assertEqual(self.post("tree", {"x": value, "y": 100}).status_code, 400)
        for i in range(122):
            self.assertEqual(self.post("tree", {"x": i, "y": 100}).status_code, 200)
        data = self.p.get("/api/patients/2/wellbeing").json
        self.assertEqual(len(data["tree_flowers"]), 120)
        self.assertEqual(data["tree_flowers"][0]["x"], 2)

    def test_summary_is_owned_and_empty_data_never_calls_model(self):
        self.assertEqual(
            self.post("chart-summary", client=self.d, csrf=self.dc).status_code, 403
        )
        self.assertEqual(
            self.post("chart-summary", client=self.other, csrf=self.oc).status_code, 404
        )
        self.assertEqual(
            self.p.post(
                "/api/patients/3/chart-summary",
                json={},
                headers={"X-CSRF-Token": self.pc},
            ).status_code,
            404,
        )
        self.assertEqual(
            self.p.post("/api/patients/2/chart-summary", json={}).status_code, 403
        )
        with patch("compass.insights.complete") as model:
            self.assertEqual(self.post("chart-summary").json["status"], "empty")
            model.assert_not_called()

    def test_summary_calls_real_adapter_contract_and_caches_only_matching_snapshot(
        self,
    ):
        self.assertEqual(self.report().status_code, 201)
        reply = json.dumps({"items": ["Средняя тревога в записях — 4 из 10."]})
        with patch(
            "compass.insights.ai_settings",
            return_value=("https://model.example/v1", "test-model", "key"),
        ), patch("compass.insights.complete", return_value=reply) as model:
            first = self.post("chart-summary")
            self.assertEqual(first.status_code, 200)
            self.assertFalse(first.json["cached"])
            context = json.loads(model.call_args.args[1])
            self.assertEqual(context["last_week"]["mean"]["anxiety"], 4)
            self.assertNotIn("private-text", model.call_args.args[1])
            self.assertNotIn("Александра", model.call_args.args[1])
            self.assertTrue(self.post("chart-summary").json["cached"])
            self.assertEqual(model.call_count, 1)
            self.report()
            self.assertFalse(self.post("chart-summary").json["cached"])
            self.assertEqual(model.call_count, 2)

    def test_summary_has_no_canned_fallback_or_cache_on_provider_failure(self):
        self.report()
        with patch.dict(
            os.environ,
            {
                "COMPASS_AI_API_KEY": "",
                "COMPASS_AI_MODEL": "",
                "COMPASS_AI_BASE_URL": "",
            },
        ):
            self.assertEqual(self.post("chart-summary").status_code, 503)
        for answer in ("{}", '{"items":[]}', '{"items":[42]}', "not json"):
            with patch("compass.insights.complete", return_value=answer):
                self.assertEqual(self.post("chart-summary").status_code, 503)
        with patch(
            "compass.insights.complete", side_effect=AssistantUnavailable("Недоступно")
        ):
            self.assertEqual(self.post("chart-summary").status_code, 503)

    def test_own_scale_chart_points_have_scores_without_changing_patient_interpretation(
        self,
    ):
        self.assertEqual(
            self.post("assessments", {"kind": "gad7", "answers": [1] * 7}).status_code,
            201,
        )
        data = self.p.get("/api/patients/2/workspace").json
        self.assertNotIn("score", data["assessments"][0])
        self.assertEqual(data["scale_series"][0]["score"], 7)
        self.assertNotIn("answers", data["scale_series"][0])
        self.assertEqual(self.other.get("/api/patients/2/workspace").status_code, 404)

    def test_completed_breathing_session_counts_once(self):
        for _ in range(2):
            self.assertEqual(
                self.post(
                    "wellbeing", {"activity": "breathing-rhythm"}, key="breath-session"
                ).status_code,
                201,
            )
        data = self.p.get("/api/patients/2/wellbeing").json
        self.assertEqual(data["practice_count"], 1)
        self.assertEqual(data["activities"][0]["title"], "Дыхание 4 · 2 · 6")


if __name__ == "__main__":
    unittest.main()
