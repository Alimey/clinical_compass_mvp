"""Account provisioning, invite ownership and persistence across app restarts."""

from pathlib import Path
import tempfile
import time
import unittest

from app import create_app
from compass.db import db
from compass.onboarding import digest


class RegistrationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "accounts.db"
        self.app = create_app(self.path, seed_demo=False, testing=True)
        self.public = self.app.test_client()

    def tearDown(self):
        self.temp.cleanup()

    def login(self, username, password="compass-demo", app=None):
        client = (app or self.app).test_client()
        response = client.post(
            "/api/auth/login", json={"username": username, "password": password}
        )
        self.assertEqual(response.status_code, 200, response.json)
        return client, {"X-CSRF-Token": response.json["csrf"]}

    def account(self, **extra):
        return {
            "name": "Новый Пользователь",
            "phone": "+70000000971",
            "password": "registration-test",
            **extra,
        }

    def test_doctor_has_private_empty_workspace_and_survives_restart(self):
        data = self.account(
            role="patient", doctor_id=1, profession="Психолог", organization="Команда"
        )
        response = self.public.post("/api/intake/doctor", json=data)
        self.assertEqual(response.status_code, 201, response.json)
        doctor, headers = self.login(data["phone"], data["password"])
        self.assertEqual(doctor.get("/api/auth/me").json["user"]["role"], "doctor")
        self.assertEqual(doctor.get("/api/patients").json, [])
        self.assertEqual(doctor.get("/api/patients/2").status_code, 404)
        invite = doctor.post("/api/invites", json={}, headers=headers)
        self.assertEqual(invite.status_code, 201)
        patient_data = self.account(
            token=invite.json["token"],
            doctor_id=1,
            age=28,
            sex="Не указан",
            height=170,
            weight=60,
            phone="+70000000972",
        )
        patient = self.public.post("/api/intake/register", json=patient_data)
        self.assertEqual(patient.status_code, 201, patient.json)
        reopened = create_app(self.path, seed_demo=False, testing=True)
        doctor, _ = self.login(data["phone"], data["password"], reopened)
        self.assertEqual(
            [p["id"] for p in doctor.get("/api/patients").json], [patient.json["id"]]
        )
        with reopened.app_context():
            stored = (
                db()
                .execute(
                    "SELECT password_hash FROM credentials WHERE user_id=?",
                    (response.json["id"],),
                )
                .fetchone()[0]
            )
            self.assertNotEqual(stored, data["password"])

    def test_duplicate_phone_and_invalid_fields_do_not_create_accounts(self):
        for data in [
            self.account(name="A"),
            self.account(password="short"),
            self.account(phone="bad"),
        ]:
            self.assertEqual(
                self.public.post("/api/intake/doctor", json=data).status_code, 400
            )
        for phone in ["+70000000002", "+7 (000) 000-00-02"]:
            self.assertEqual(
                self.public.post(
                    "/api/intake/doctor", json=self.account(phone=phone)
                ).status_code,
                409,
            )
        data = self.account()
        self.assertEqual(
            self.public.post("/api/intake/doctor", json=data).status_code, 201
        )
        self.assertEqual(
            self.public.post("/api/intake/doctor", json=data).status_code, 409
        )

    def test_relative_invite_binding_permissions_reuse_and_revocation(self):
        patient, headers = self.login("patient-a")
        self.assertEqual(
            self.public.post("/api/relative-invites", json={}).status_code, 401
        )
        doctor, dh = self.login("doctor")
        self.assertEqual(
            doctor.post("/api/relative-invites", json={}, headers=dh).status_code, 403
        )
        self.assertEqual(
            patient.post("/api/relative-invites", json={}).status_code, 403
        )
        invitation = patient.post(
            "/api/relative-invites", json={}, headers=headers
        ).json
        token = invitation["token"]
        info = self.public.post("/api/intake/relative-info", json={"token": token})
        self.assertEqual(info.json, {"patient": {"name": "Александра Морозова"}})
        data = self.account(token=token, patient_id=3, role="doctor")
        self.assertEqual(
            self.public.post(
                "/api/intake/relative", json={**data, "phone": "+70000000002"}
            ).status_code,
            409,
        )
        # Failed validation leaves the single-use link usable.
        response = self.public.post("/api/intake/relative", json=data)
        self.assertEqual(response.status_code, 201, response.json)
        self.assertEqual(
            self.public.post("/api/intake/relative", json=data).status_code, 410
        )
        relative, _ = self.login(data["phone"], data["password"])
        self.assertEqual(relative.get("/api/auth/me").json["user"]["role"], "relative")
        self.assertEqual(relative.get("/api/relative").json["patients"], [])
        self.assertEqual(relative.get("/api/patients/2").status_code, 404)
        patient.post(
            "/api/patients/2/preferences", json={"relative_sos": True}, headers=headers
        )
        self.assertEqual(
            [p["id"] for p in relative.get("/api/relative").json["patients"]], [2]
        )
        patient.post(
            "/api/patients/2/preferences", json={"relative_sos": False}, headers=headers
        )
        self.assertEqual(relative.get("/api/relative").json["patients"], [])
        with self.app.app_context():
            links = (
                db()
                .execute(
                    "SELECT patient_id FROM relative_links WHERE relative_id=?",
                    (response.json["id"],),
                )
                .fetchall()
            )
            self.assertEqual([r[0] for r in links], [2])

    def test_expired_wrong_kind_and_cross_origin_invites(self):
        patient, headers = self.login("patient-a")
        token = patient.post("/api/relative-invites", json={}, headers=headers).json[
            "token"
        ]
        self.assertEqual(
            self.public.post("/api/intake/info", json={"token": token}).status_code, 410
        )
        self.assertEqual(
            self.public.post(
                "/api/intake/relative-info", json={"token": "unknown"}
            ).status_code,
            410,
        )
        self.assertEqual(
            self.public.post(
                "/api/intake/doctor",
                json=self.account(),
                headers={"Origin": "https://elsewhere.example"},
            ).status_code,
            403,
        )
        with self.app.app_context(), db() as con:
            con.execute(
                "UPDATE relative_invites SET expires_at=? WHERE token_hash=?",
                (time.time() - 10, digest(token)),
            )
        self.assertEqual(
            self.public.post(
                "/api/intake/relative-info", json={"token": token}
            ).status_code,
            410,
        )
        self.assertEqual(
            self.public.post(
                "/api/intake/relative", json=self.account(token=token)
            ).status_code,
            410,
        )


if __name__ == "__main__":
    unittest.main()
