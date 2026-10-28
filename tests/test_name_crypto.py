"""Защита имён в хранилище, миграция, ключи и выгрузки по кодам."""

from contextlib import closing
import csv
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet
from app import create_app
from compass.backup import backup
from compass.db import db, notify
from compass.name_crypto import (
    NameCipher,
    NameEncryptionError,
    PREFIX,
    seal,
    unseal,
    restore_migration_backup,
)
from compass.telegram_bot import handle_update


class NameCryptoTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.path = self.folder / "patients.db"
        self.environment = patch.dict(
            os.environ, {"COMPASS_NAME_KEY": "", "COMPASS_NAME_KEY_FILE": ""}
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def app(self):
        return create_app(self.path, seed_demo=False, testing=True)

    def login(self, app, username):
        client = app.test_client()
        response = client.post(
            "/api/auth/login", json={"username": username, "password": "compass-demo"}
        )
        self.assertEqual(response.status_code, 200, response.json)
        return client, {"X-CSRF-Token": response.json["csrf"]}

    def raw(self, sql, args=()):
        with closing(sqlite3.connect(self.path)) as con:
            return con.execute(sql, args).fetchall()

    def test_names_are_ciphertext_but_authorized_views_and_restarts_work(self):
        app = self.app()
        raw = self.raw("SELECT name FROM users WHERE id=2")[0][0]
        self.assertTrue(raw.startswith(PREFIX + "name:"))
        self.assertNotIn("Александра", raw)
        doctor, _ = self.login(app, "doctor")
        patient, _ = self.login(app, "patient-a")
        self.assertEqual(
            patient.get("/api/auth/me").json["user"]["name"], "Александра Морозова"
        )
        self.assertEqual(
            doctor.get("/api/patients/2").json["patient"]["name"], "Александра Морозова"
        )
        restarted = self.app()
        client, _ = self.login(restarted, "patient-a")
        self.assertEqual(
            client.get("/api/auth/me").json["user"]["name"], "Александра Морозова"
        )
        self.assertEqual(self.raw("SELECT name FROM users WHERE id=2")[0][0], raw)
        if os.name != "nt":
            self.assertEqual(
                (self.folder / "patient-names.key").stat().st_mode & 0o777, 0o600
            )

    def test_new_accounts_encrypt_names_and_do_not_decode_user_text_as_ciphertext(self):
        app = self.app()
        client = app.test_client()
        literal = "pcenc:v1:name:literal-user-input"
        response = client.post(
            "/api/intake/doctor",
            json={
                "name": literal,
                "phone": "+70000000981",
                "password": "test-strong-password",
            },
        )
        self.assertEqual(response.status_code, 201, response.json)
        login = client.post(
            "/api/auth/login",
            json={"username": "+70000000981", "password": "test-strong-password"},
        )
        self.assertEqual(login.json["user"]["name"], literal)
        self.assertNotEqual(
            self.raw("SELECT name FROM users WHERE id=?", (login.json["user"]["id"],))[
                0
            ][0],
            literal,
        )
        with app.app_context():
            self.assertNotEqual(seal("Одинаковое имя"), seal("Одинаковое имя"))

    def test_missing_or_wrong_key_stops_startup_without_rewriting_data(self):
        self.app()
        before = self.raw("SELECT name FROM users WHERE id=2")[0][0]
        key_file = self.folder / "patient-names.key"
        key = key_file.read_bytes()
        key_file.unlink()
        with self.assertRaises(NameEncryptionError):
            self.app()
        self.assertFalse(key_file.exists())
        self.assertEqual(self.raw("SELECT name FROM users WHERE id=2")[0][0], before)
        key_file.write_bytes(key)
        with patch.dict(
            os.environ, {"COMPASS_NAME_KEY": Fernet.generate_key().decode()}
        ):
            with self.assertRaises(NameEncryptionError):
                self.app()
        self.assertEqual(self.raw("SELECT name FROM users WHERE id=2")[0][0], before)
        self.app()

    def test_legacy_migration_has_encrypted_recovery_copy_and_removes_old_pages(self):
        unique = "ЗащищаемоеИмя УникальнаяФамилия"
        with closing(sqlite3.connect(self.path)) as con, con:
            con.execute(
                "CREATE TABLE users(id INTEGER PRIMARY KEY,role TEXT,name TEXT,doctor_id INTEGER)"
            )
            con.execute("INSERT INTO users VALUES(2,'patient',?,1)", (unique,))
        app = self.app()
        self.assertTrue(
            self.raw("SELECT name FROM users WHERE id=2")[0][0].startswith(PREFIX)
        )
        self.assertNotIn(unique.encode(), self.path.read_bytes())
        copies = list(self.folder.glob("*.before-names-*.enc"))
        self.assertEqual(len(copies), 1)
        self.assertNotIn(unique.encode(), copies[0].read_bytes())
        key = (self.folder / "patient-names.key").read_bytes()
        restored = self.folder / "recovery-inspection.db"
        restore_migration_backup(copies[0], restored, NameCipher(key))
        with closing(sqlite3.connect(restored)) as con:
            self.assertEqual(
                con.execute("SELECT name FROM users WHERE id=2").fetchone()[0], unique
            )
            dump = b"psicompass-sqlite-dump-v1\n" + "\n".join(con.iterdump()).encode()
        portable = self.folder / "portable.enc"
        portable.write_bytes(NameCipher(key).cipher("migration-backup").encrypt(dump))
        portable_db = self.folder / "portable.db"
        restore_migration_backup(portable, portable_db, NameCipher(key))
        with closing(sqlite3.connect(portable_db)) as con:
            self.assertEqual(
                con.execute("SELECT name FROM users WHERE id=2").fetchone()[0], unique
            )
        with self.assertRaises(FileExistsError):
            restore_migration_backup(copies[0], restored, NameCipher(key))
        patient, _ = self.login(app, "patient-a")
        self.assertEqual(patient.get("/api/auth/me").json["user"]["name"], unique)
        self.app()
        self.assertEqual(len(list(self.folder.glob("*.before-names-*.enc"))), 1)

    def test_notices_are_encrypted_and_only_authorized_api_reads_plaintext(self):
        app = self.app()
        with app.app_context(), db():
            ident = notify(1, 2, "Тест", "Александра Морозова отправила запись")
        raw = self.raw("SELECT body FROM notifications WHERE id=?", (ident,))[0][0]
        self.assertTrue(raw.startswith(PREFIX + "notice:"))
        doctor, _ = self.login(app, "doctor")
        patient, _ = self.login(app, "patient-a")
        items = doctor.get("/api/notifications").json["items"]
        self.assertEqual(
            next(r["body"] for r in items if r["id"] == ident),
            "Александра Морозова отправила запись",
        )
        self.assertNotIn(
            ident, [r["id"] for r in patient.get("/api/notifications").json["items"]]
        )
        with app.app_context():
            with self.assertRaises(NameEncryptionError):
                unseal(raw, "name")

    def test_tampered_ciphertext_is_rejected(self):
        app = self.app()
        with app.app_context():
            value = seal("Имя пациента")
            i = len(value) // 2
            modified = value[:i] + ("A" if value[i] != "A" else "B") + value[i + 1 :]
            with self.assertRaises(NameEncryptionError):
                unseal(modified)

    def test_invited_patient_name_is_encrypted_on_first_write(self):
        app = self.app()
        doctor, headers = self.login(app, "doctor")
        token = doctor.post("/api/invites", json={}, headers=headers).json["token"]
        result = app.test_client().post(
            "/api/intake/register",
            json={
                "token": token,
                "name": "Новая Пациентка",
                "phone": "+70000000982",
                "password": "patient-strong-password",
                "age": 28,
                "height": 170,
                "weight": 60,
                "sex": "Женский",
                "context": "Тест регистрации",
            },
        )
        self.assertEqual(result.status_code, 201, result.json)
        value = self.raw(
            "SELECT name FROM users WHERE id=(SELECT user_id FROM credentials WHERE username=?)",
            ("+70000000982",),
        )[0][0]
        self.assertTrue(value.startswith(PREFIX + "name:"))
        self.assertNotIn("Пациентка", value)

    def test_telegram_draft_and_outgoing_confirmation_do_not_store_name_plainly(self):
        app = self.app()
        doctor, headers = self.login(app, "doctor")
        token = doctor.post("/api/invites", json={}, headers=headers).json["token"]
        with app.app_context():
            for index, text in enumerate(["/start " + token, "СекретноеИмя Фамилия"]):
                handle_update(
                    {
                        "update_id": index + 1,
                        "message": {
                            "chat": {"id": 921, "type": "private"},
                            "text": text,
                        },
                    }
                )
            draft = (
                db()
                .execute("SELECT data_json FROM telegram_sessions WHERE chat_id=921")
                .fetchone()[0]
            )
            self.assertTrue(draft.startswith(PREFIX + "intake:"))
            self.assertEqual(
                json.loads(unseal(draft, "intake"))["name"], "СекретноеИмя Фамилия"
            )
        self.assertTrue(
            all(
                r[0].startswith(PREFIX + "outbox:")
                for r in self.raw("SELECT body FROM telegram_outbox")
            )
        )

    def test_exports_use_one_code_and_keep_names_out_for_both_roles(self):
        app = self.app()
        doctor, dh = self.login(app, "doctor")
        patient, ph = self.login(app, "patient-a")
        lab = doctor.post(
            "/api/patients/2/labs",
            json={
                "title": "Анализ: Александра Морозова",
                "result": "АЛЕКСАНДРА: показатель 5",
                "note": "Морозова — результат",
            },
            headers=dh,
        )
        self.assertEqual(lab.status_code, 201, lab.json)
        body = doctor.get(f"/api/labs/{lab.json['id']}/download").get_data(as_text=True)
        self.assertEqual(
            body,
            patient.get(f"/api/labs/{lab.json['id']}/download").get_data(as_text=True),
        )
        for word in ["александра", "морозова"]:
            self.assertNotIn(word, body.casefold())
        self.assertIn("показатель 5", body)
        self.assertEqual(
            patient.post(
                "/api/patients/2/preferences", json={"research": True}, headers=ph
            ).status_code,
            200,
        )
        data = list(
            csv.DictReader(
                io.StringIO(
                    doctor.get("/api/research.csv")
                    .get_data(as_text=True)
                    .lstrip("\ufeff")
                )
            )
        )
        code = self.raw("SELECT code FROM research_codes WHERE patient_id=2")[0][0]
        self.assertIn("Пациент: " + code, body)
        self.assertIn(code, [r["code"] for r in data])
        self.assertNotIn("name", data[0])
        self.assertNotIn("Александра", str(data))
        other, _ = self.login(app, "doctor-other")
        self.assertEqual(
            other.get(f"/api/labs/{lab.json['id']}/download").status_code, 404
        )
        self.assertEqual(
            app.test_client().get(f"/api/labs/{lab.json['id']}/download").status_code,
            401,
        )

    def test_database_backup_needs_same_key_on_another_directory(self):
        app = self.app()
        dest = self.folder / "other" / "copy.db"
        backup(self.path, dest)
        with self.assertRaises(NameEncryptionError):
            create_app(dest, seed_demo=False, testing=True)
        with patch.dict(
            os.environ,
            {"COMPASS_NAME_KEY_FILE": str(self.folder / "patient-names.key")},
        ):
            restored = create_app(dest, seed_demo=False, testing=True)
            client, _ = self.login(restored, "patient-a")
            self.assertEqual(
                client.get("/api/auth/me").json["user"]["name"], "Александра Морозова"
            )

    def test_cleanup_resumes_after_an_old_reader_releases_the_wal(self):
        self.app()
        with closing(sqlite3.connect(self.path)) as writer, writer:
            writer.execute("UPDATE users SET name='ИмяДоМиграции' WHERE id=2")
        with closing(sqlite3.connect(self.path)) as reader:
            reader.execute("BEGIN")
            reader.execute("SELECT name FROM users").fetchall()
            with self.assertRaises(NameEncryptionError):
                self.app()
            self.assertEqual(
                self.raw(
                    "SELECT value FROM name_encryption_state WHERE key='cleanup_pending'"
                )[0][0],
                "1",
            )
        app = self.app()
        self.assertEqual(
            self.raw(
                "SELECT value FROM name_encryption_state WHERE key='cleanup_pending'"
            )[0][0],
            "0",
        )
        patient, _ = self.login(app, "patient-a")
        self.assertEqual(
            patient.get("/api/auth/me").json["user"]["name"], "ИмяДоМиграции"
        )
