from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from werkzeug.security import generate_password_hash
from app import create_app
from compass.db import db, now
from compass.delivery import reminders_and_escalations, dispatch_push
from compass.reminder_policy import record_presence

CLOCK = datetime(2026, 10, 24, 10, tzinfo=timezone.utc)


class FixedClock(datetime):
    @classmethod
    def now(cls, tz=None):
        return CLOCK if tz else CLOCK.replace(tzinfo=None)


class ReminderPresenceTest(unittest.TestCase):
    def setUp(self):
        self.policy_clock = patch("compass.reminder_policy.datetime", FixedClock)
        self.policy_clock.start()
        self.temp = tempfile.TemporaryDirectory()
        self.app = create_app(
            Path(self.temp.name) / "test.db", seed_demo=False, testing=True
        )
        self.patient = self.app.test_client()
        self.doctor = self.app.test_client()
        self.pc = self.patient.post(
            "/api/auth/login",
            json={"username": "patient-a", "password": "compass-demo"},
        ).json["csrf"]
        self.dc = self.doctor.post(
            "/api/auth/login", json={"username": "doctor", "password": "compass-demo"}
        ).json["csrf"]
        with self.app.app_context(), db() as con:
            self.family = con.execute(
                "INSERT INTO users(role,name) VALUES('relative','Близкий')"
            ).lastrowid
            con.execute(
                "INSERT INTO credentials VALUES(?,?,?)",
                (self.family, "family", generate_password_hash("compass-demo")),
            )
            con.execute("INSERT INTO relative_links VALUES(?,2)", (self.family,))
            self.settings = {"relative_sos": True, "relative_away": True}
            self.set_preferences(con)
            for user in (1, 2, self.family):
                con.execute(
                    "INSERT INTO push_subscriptions(user_id,endpoint,subscription_json,created_at) VALUES(?,?,?,?)",
                    (
                        user,
                        f"https://fcm.googleapis.com/fcm/send/test{user}",
                        json.dumps(
                            {
                                "endpoint": f"https://fcm.googleapis.com/fcm/send/test{user}"
                            }
                        ),
                        (CLOCK - timedelta(days=10)).isoformat(),
                    ),
                )

    def tearDown(self):
        self.policy_clock.stop()
        self.temp.cleanup()

    def set_preferences(self, con):
        con.execute(
            "INSERT OR REPLACE INTO patient_preferences VALUES(2,?)",
            (json.dumps(self.settings),),
        )

    def tick(self):
        with patch("compass.delivery.datetime", FixedClock), patch(
            "compass.delivery.local_today", return_value=CLOCK.date()
        ):
            reminders_and_escalations()

    def absent(self):
        db().execute(
            "UPDATE user_presence SET last_seen=? WHERE user_id=2",
            ((CLOCK - timedelta(hours=73)).isoformat(),),
        )
        db().commit()

    def test_absence_once_and_consent_rechecked_before_push(self):
        with self.app.app_context():
            self.absent()
            self.tick()
            self.tick()
            self.assertEqual(
                db()
                .execute(
                    "SELECT count(*) FROM notification_guards WHERE kind='absence'"
                )
                .fetchone()[0],
                2,
            )
            self.settings["relative_away"] = False
            with db() as con:
                self.set_preferences(con)
            with patch("compass.delivery.webpush") as send:
                dispatch_push()
                self.assertEqual(send.call_count, 1)
                payload = send.call_args.kwargs["data"]
                self.assertNotIn("Морозова", payload)
                self.assertNotIn("73", payload)
            relative = self.app.test_client()
            relative.post(
                "/api/auth/login",
                json={"username": "family", "password": "compass-demo"},
            )
            self.assertEqual(relative.get("/api/notifications").json["unread"], 0)

    def test_return_cancels_queued_absence_and_allows_new_episode(self):
        with self.app.app_context():
            self.absent()
            self.tick()
        response = self.patient.post(
            "/api/activity/heartbeat", json={}, headers={"X-CSRF-Token": self.pc}
        )
        self.assertEqual(response.status_code, 200)
        with self.app.app_context():
            with patch("compass.delivery.webpush") as send:
                dispatch_push()
                send.assert_not_called()
            db().execute(
                "UPDATE user_presence SET last_seen=? WHERE user_id=2",
                ((CLOCK - timedelta(hours=74)).isoformat(),),
            )
            db().commit()
            self.tick()
            self.assertEqual(
                db()
                .execute(
                    "SELECT count(*) FROM notification_guards WHERE kind='absence' AND cancelled=0"
                )
                .fetchone()[0],
                2,
            )

    def test_no_false_absence_from_old_diary_and_heartbeat_permissions(self):
        with self.app.app_context():
            self.tick()
            self.assertEqual(
                db()
                .execute(
                    "SELECT count(*) FROM notification_guards WHERE kind='absence'"
                )
                .fetchone()[0],
                0,
            )
        self.assertEqual(
            self.patient.post("/api/activity/heartbeat", json={}).status_code, 403
        )
        self.assertEqual(
            self.doctor.post(
                "/api/activity/heartbeat", json={}, headers={"X-CSRF-Token": self.dc}
            ).status_code,
            403,
        )

    def test_absence_threshold_is_three_days(self):
        with self.app.app_context():
            db().execute(
                "UPDATE user_presence SET last_seen=? WHERE user_id=2",
                ((CLOCK - timedelta(hours=71, minutes=59)).isoformat(),),
            )
            db().commit()
            self.tick()
            self.assertEqual(
                db()
                .execute(
                    "SELECT count(*) FROM notification_guards WHERE kind='absence'"
                )
                .fetchone()[0],
                0,
            )
            db().execute(
                "UPDATE user_presence SET last_seen=? WHERE user_id=2",
                ((CLOCK - timedelta(hours=72, seconds=1)).isoformat(),),
            )
            db().commit()
            self.tick()
            self.assertEqual(
                db()
                .execute(
                    "SELECT count(*) FROM notification_guards WHERE kind='absence'"
                )
                .fetchone()[0],
                2,
            )

    def test_unmarked_and_skipped_dose_then_taken_cancel_delivery(self):
        with self.app.app_context(), db() as con:
            ident = con.execute(
                "INSERT INTO prescriptions(patient_id,doctor_id,choice,title,times_json,starts_on,ends_on,note,created_at) VALUES(2,1,'demo-alpha','Пример',?,'2026-10-24','2026-10-24','',?)",
                (json.dumps(["12:00"]), now()),
            ).lastrowid
        with self.app.app_context():
            self.tick()
            self.tick()
            self.assertEqual(
                db()
                .execute(
                    "SELECT count(*) FROM notification_guards WHERE kind='medication'"
                )
                .fetchone()[0],
                1,
            )
            db().execute(
                "INSERT INTO medication_marks(prescription_id,patient_id,day,scheduled_time,status,marked_at) VALUES(?,2,'2026-10-24','12:00','skipped',?)",
                (ident, now()),
            )
            db().commit()
            self.tick()
            self.assertEqual(
                db()
                .execute(
                    "SELECT count(*) FROM notification_guards WHERE kind='medication' AND cancelled=0"
                )
                .fetchone()[0],
                1,
            )
            db().execute(
                "UPDATE medication_marks SET status='taken' WHERE prescription_id=?",
                (ident,),
            )
            db().commit()
            with patch("compass.delivery.webpush") as send:
                dispatch_push()
                send.assert_not_called()
            self.assertEqual(self.patient.get("/api/notifications").json["unread"], 0)

    def test_new_assessment_deadline_cancel_and_no_duplicates(self):
        with self.app.app_context(), db() as con:
            ident = con.execute(
                "INSERT INTO assessment_assignments(patient_id,doctor_id,kind,due_at,created_at) VALUES(2,1,'cope',?,?)",
                ((CLOCK - timedelta(hours=1)).isoformat(), now()),
            ).lastrowid
        with self.app.app_context():
            self.tick()
            self.tick()
            self.assertEqual(
                db()
                .execute(
                    "SELECT count(*) FROM notification_guards WHERE kind='assessment'"
                )
                .fetchone()[0],
                2,
            )
            db().execute(
                "UPDATE assessment_assignments SET status='cancelled' WHERE id=?",
                (ident,),
            )
            db().commit()
            with patch("compass.delivery.webpush") as send:
                dispatch_push()
                send.assert_not_called()

    def test_test_notification_uses_authenticated_account(self):
        self.assertEqual(self.doctor.post("/api/push/test", json={}).status_code, 403)
        response = self.doctor.post(
            "/api/push/test", json={}, headers={"X-CSRF-Token": self.dc}
        )
        self.assertEqual(response.status_code, 201)
        with self.app.app_context():
            self.tick()
            with patch("compass.delivery.webpush") as send:
                dispatch_push()
                self.assertEqual(send.call_count, 1)


if __name__ == "__main__":
    unittest.main()
