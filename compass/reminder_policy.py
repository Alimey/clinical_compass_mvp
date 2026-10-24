"""Recheck reminder relevance and patient consent immediately before delivery."""

import os
from datetime import datetime, timedelta, timezone
from compass.db import db, now
from compass.care import timestamp, CLINIC_TZ


def inactivity_hours():
    return max(1, int(os.environ.get("COMPASS_INACTIVITY_HOURS", "72")))


def record_presence(ident):
    db().execute(
        "INSERT INTO user_presence VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET last_seen=excluded.last_seen",
        (ident, now()),
    )


def guard_is_current(guard, recipient):
    if guard["cancelled"]:
        return False
    kind, resource = guard["kind"], guard["resource_id"]
    if kind in ("survey", "assessment"):
        if (
            kind == "assessment"
            and db()
            .execute(
                "SELECT 1 FROM assessment_assignments WHERE id=? AND kind IN ('mmpi','beck_hopelessness','beck_depression')",
                (resource,),
            )
            .fetchone()
        ):
            return False
        table = "survey_assignments" if kind == "survey" else "assessment_assignments"
        return bool(
            db()
            .execute(
                f"SELECT 1 FROM {table} WHERE id=? AND status='assigned'", (resource,)
            )
            .fetchone()
        )
    if kind == "medication":
        day, schedule = guard["episode"].split("|")
        due = datetime.fromisoformat(day + "T" + schedule).replace(tzinfo=CLINIC_TZ)
        if due + timedelta(hours=24) <= datetime.now(timezone.utc):
            return False
        return (
            bool(
                db()
                .execute(
                    "SELECT 1 FROM prescriptions WHERE id=? AND active=1 AND starts_on<=? AND ends_on>=?",
                    (resource, day, day),
                )
                .fetchone()
            )
            and not db()
            .execute(
                "SELECT 1 FROM medication_marks WHERE prescription_id=? AND day=? AND scheduled_time=? AND status='taken'",
                (resource, day, schedule),
            )
            .fetchone()
        )
    if kind == "absence":
        person = (
            db()
            .execute(
                "SELECT u.doctor_id,p.last_seen FROM users u JOIN user_presence p ON p.user_id=u.id WHERE u.id=?",
                (guard["patient_id"],),
            )
            .fetchone()
        )
        if (
            not person
            or person["last_seen"] != guard["episode"]
            or timestamp(person["last_seen"]) + timedelta(hours=inactivity_hours())
            > datetime.now(timezone.utc)
        ):
            return False
        if person["doctor_id"] == recipient:
            return True
        from compass.sections import preferences

        prefs = preferences(guard["patient_id"])
        return bool(
            prefs["relative_sos"]
            and prefs["relative_away"]
            and db()
            .execute(
                "SELECT 1 FROM relative_links WHERE relative_id=? AND patient_id=?",
                (recipient, guard["patient_id"]),
            )
            .fetchone()
        )
    return False


def cancel_stale_reminders(user=None):
    query = "SELECT g.*,n.user_id FROM notification_guards g JOIN notifications n ON n.id=g.notification_id WHERE g.cancelled=0"
    params = ()
    if user is not None:
        query += " AND n.user_id=?"
        params = (user,)
    for guard in db().execute(query, params).fetchall():
        if not guard_is_current(guard, guard["user_id"]):
            db().execute(
                "UPDATE notification_guards SET cancelled=1 WHERE notification_id=?",
                (guard["notification_id"],),
            )
            db().execute(
                "UPDATE push_jobs SET status='cancelled' WHERE notification_id=? AND status IN ('pending','sending')",
                (guard["notification_id"],),
            )
