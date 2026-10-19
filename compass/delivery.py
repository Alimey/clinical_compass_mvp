"""Durable reminders, escalation queue and genuine encrypted Web Push."""

import base64
import json
import os
from pathlib import Path
import time
import tempfile
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from flask import abort, g, jsonify, current_app
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from pywebpush import webpush, WebPushException
from compass.db import db, rows, now, notify, audit
from compass.care import CLINIC_TZ, local_today, timestamp
from compass.assistants import ai_settings


def init_delivery():
    db().executescript(
        """
    CREATE TABLE IF NOT EXISTS push_subscriptions(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL REFERENCES users(id),endpoint TEXT NOT NULL UNIQUE,subscription_json TEXT NOT NULL,created_at TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS push_jobs(id INTEGER PRIMARY KEY AUTOINCREMENT,notification_id INTEGER NOT NULL REFERENCES notifications(id),subscription_id INTEGER NOT NULL REFERENCES push_subscriptions(id),status TEXT NOT NULL DEFAULT 'pending',attempts INTEGER NOT NULL DEFAULT 0,next_attempt REAL NOT NULL DEFAULT 0,lease_until REAL NOT NULL DEFAULT 0,last_error TEXT NOT NULL DEFAULT '',sent_at TEXT,UNIQUE(notification_id,subscription_id));
    """
    )
    db().commit()


def vapid_keys():
    path = Path(current_app.config["DATABASE"]).resolve().parent / "push-vapid.pem"
    if not path.exists():
        key = ec.generate_private_key(ec.SECP256R1())
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as output:
            temporary = Path(output.name)
            output.write(
                key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                )
            )
        try:
            os.link(temporary, path)
        except FileExistsError:
            pass
        finally:
            temporary.unlink(missing_ok=True)
    private = serialization.load_pem_private_key(path.read_bytes(), password=None)
    public = private.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return path, base64.urlsafe_b64encode(public).decode().rstrip("=")


def reminders_and_escalations():
    stamp = now()
    clock = datetime.now(timezone.utc)
    today = local_today()

    def once(key, user, patient, title, body):
        inserted = (
            db()
            .execute("INSERT OR IGNORE INTO reminder_events VALUES(?,?)", (key, stamp))
            .rowcount
        )
        if inserted:
            notify(user, patient, title, body)

    with db() as con:
        for item in con.execute(
            "SELECT * FROM survey_assignments WHERE status='assigned'"
        ).fetchall():
            due = timestamp(item["due_at"])
            if due - timedelta(hours=24) <= clock <= due:
                once(
                    "survey-due:" + str(item["id"]),
                    item["patient_id"],
                    item["patient_id"],
                    "Напоминание об опросе",
                    "Опрос ожидает ответа. Проверьте дедлайн в приложении.",
                )
            elif clock > due:
                once(
                    "survey-overdue:" + str(item["id"]),
                    item["patient_id"],
                    item["patient_id"],
                    "Дедлайн опроса прошёл",
                    "Ответить ещё можно. При необходимости обсудите срок со специалистом.",
                )
                once(
                    "survey-overdue-doctor:" + str(item["id"]),
                    item["doctor_id"],
                    item["patient_id"],
                    "Опрос просрочен",
                    "Пациент пока не ответил на назначенный опрос.",
                )
        for item in con.execute(
            "SELECT * FROM prescriptions WHERE active=1 AND starts_on<=? AND ends_on>=?",
            (today.isoformat(), today.isoformat()),
        ).fetchall():
            for schedule in json.loads(item["times_json"]):
                due = datetime.combine(
                    today, datetime.strptime(schedule, "%H:%M").time(), CLINIC_TZ
                ).astimezone(timezone.utc)
                marked = con.execute(
                    "SELECT 1 FROM medication_marks WHERE prescription_id=? AND day=? AND scheduled_time=?",
                    (item["id"], today.isoformat(), schedule),
                ).fetchone()
                if due <= clock < due + timedelta(hours=2) and not marked:
                    once(
                        f"medication:{item['id']}:{today}:{schedule}",
                        item["patient_id"],
                        item["patient_id"],
                        "Напоминание о таблетнице",
                        "Проверьте учебное назначение и отметьте выполнение.",
                    )
        for item in con.execute(
            "SELECT * FROM appointments WHERE status='booked'"
        ).fetchall():
            due = timestamp(item["starts_at"])
            if due - timedelta(hours=24) <= clock < due:
                for user in (item["doctor_id"], item["patient_id"]):
                    once(
                        f"appointment:{item['id']}:{user}",
                        user,
                        item["patient_id"],
                        "Напоминание о консультации",
                        "В ближайшие сутки запланирована консультация.",
                    )
        delay = max(1, int(os.environ.get("COMPASS_ESCALATION_MINUTES", "15")))
        for item in con.execute(
            "SELECT a.*,u.doctor_id FROM alerts a JOIN users u ON u.id=a.patient_id WHERE a.status='new'"
        ).fetchall():
            if timestamp(item["created_at"]) + timedelta(minutes=delay) > clock:
                continue
            inserted = con.execute(
                "INSERT OR IGNORE INTO escalations(alert_id,doctor_id,patient_id,created_at,note) VALUES(?,?,?,?,?)",
                (
                    item["id"],
                    item["doctor_id"],
                    item["patient_id"],
                    stamp,
                    "Внешний протокол не задан. Событие поставлено во внутреннюю очередь эскалации, а не отправлено в организацию.",
                ),
            ).rowcount
            if inserted:
                notify(
                    item["doctor_id"],
                    item["patient_id"],
                    "Требуется эскалация",
                    "Сигнал остаётся непросмотренным. Внешний протокол необходимо определить.",
                )
                audit(
                    item["doctor_id"],
                    item["patient_id"],
                    "escalation.queued",
                    "Событие в очереди, внешняя доставка не настроена",
                )
        # Do not send historical notifications to a newly subscribed device.
        con.execute(
            """INSERT OR IGNORE INTO push_jobs(notification_id,subscription_id)
            SELECT n.id,s.id FROM notifications n JOIN push_subscriptions s ON s.user_id=n.user_id
            WHERE s.active=1 AND n.created_at>=s.created_at AND n.read_at IS NULL"""
        )
        con.execute(
            "INSERT OR REPLACE INTO service_state VALUES('worker_heartbeat',?)",
            (stamp,),
        )


def dispatch_push():
    with db() as con:
        con.execute(
            "UPDATE push_jobs SET status='failed',last_error='LeaseExpired' WHERE status='sending' AND attempts>=6 AND lease_until<?",
            (time.time(),),
        )
    candidates = rows(
        """SELECT j.id FROM push_jobs j JOIN push_subscriptions s ON s.id=j.subscription_id
        WHERE s.active=1 AND j.attempts<6 AND j.next_attempt<=? AND
        (j.status='pending' OR (j.status='sending' AND j.lease_until<?)) ORDER BY j.id LIMIT 20""",
        (time.time(), time.time()),
    )
    if not candidates:
        return
    private, _ = vapid_keys()
    for candidate in candidates:
        with db() as con:
            con.execute("BEGIN IMMEDIATE")
            item = con.execute(
                """SELECT j.*,s.subscription_json,s.active,n.read_at FROM push_jobs j
                JOIN push_subscriptions s ON s.id=j.subscription_id JOIN notifications n ON n.id=j.notification_id WHERE j.id=?""",
                (candidate["id"],),
            ).fetchone()
            if (
                not item
                or not item["active"]
                or item["status"] not in ("pending", "sending")
                or (item["status"] == "sending" and item["lease_until"] > time.time())
            ):
                continue
            if item["read_at"]:
                con.execute(
                    "UPDATE push_jobs SET status='cancelled' WHERE id=?", (item["id"],)
                )
                continue
            con.execute(
                "UPDATE push_jobs SET status='sending',lease_until=?,attempts=attempts+1 WHERE id=?",
                (time.time() + 120, item["id"]),
            )
        try:
            webpush(
                subscription_info=json.loads(item["subscription_json"]),
                data=json.dumps(
                    {
                        "title": "Клинический компас",
                        "body": "В приложении новое событие. Откройте его для просмотра.",
                        "tag": "compass-" + str(item["notification_id"]),
                        "url": "/",
                    },
                    ensure_ascii=False,
                ),
                vapid_private_key=str(private),
                vapid_claims={
                    "sub": os.environ.get(
                        "COMPASS_PUSH_CONTACT", "mailto:demo@example.invalid"
                    )
                },
                ttl=3600,
                timeout=15,
            )
            with db() as con:
                con.execute(
                    "UPDATE push_jobs SET status='sent',sent_at=?,last_error='' WHERE id=?",
                    (now(), item["id"]),
                )
        except Exception as error:
            expired = (
                isinstance(error, WebPushException)
                and error.response is not None
                and error.response.status_code in (404, 410)
            )
            with db() as con:
                if expired:
                    con.execute(
                        "UPDATE push_subscriptions SET active=0 WHERE id=?",
                        (item["subscription_id"],),
                    )
                con.execute(
                    "UPDATE push_jobs SET status=?,next_attempt=?,last_error=? WHERE id=?",
                    (
                        "failed" if expired or item["attempts"] >= 5 else "pending",
                        time.time() + min(3600, 30 * 2 ** item["attempts"]),
                        type(error).__name__,
                        item["id"],
                    ),
                )


def register_delivery(app, require_role, payload):
    @app.get("/api/integrations")
    def integrations():
        base, model, key = ai_settings()
        heartbeat = rows("SELECT value FROM service_state WHERE key='worker_heartbeat'")
        return jsonify(
            ai={"configured": bool(base and model and key), "model": model},
            telegram={
                "configured": bool(
                    os.environ.get("COMPASS_TELEGRAM_BOT_TOKEN")
                    and os.environ.get("COMPASS_PUBLIC_URL")
                ),
                "username": os.environ.get("COMPASS_TELEGRAM_BOT_USERNAME", ""),
            },
            worker_last_seen=heartbeat[0]["value"] if heartbeat else None,
            contact=rows("SELECT * FROM contacts WHERE user_id=?", (g.user["id"],)),
            push={
                "subscriptions": db()
                .execute(
                    "SELECT COUNT(*) FROM push_subscriptions WHERE user_id=? AND active=1",
                    (g.user["id"],),
                )
                .fetchone()[0]
            },
        )

    @app.get("/api/push/key")
    def public_push_key():
        return jsonify(public_key=vapid_keys()[1])

    @app.post("/api/push/subscribe")
    def subscribe():
        data = payload()
        subscription = data.get("subscription")
        if not isinstance(subscription, dict):
            raise ValueError("Не передана подписка браузера")
        endpoint = subscription.get("endpoint")
        keys = subscription.get("keys", {})
        if not isinstance(endpoint, str) or len(endpoint) > 3000:
            raise ValueError("Некорректный адрес push")
        url = urlsplit(endpoint)
        host = url.hostname or ""
        allowed = host in (
            "fcm.googleapis.com",
            "updates.push.services.mozilla.com",
            "web.push.apple.com",
        ) or host.endswith(".notify.windows.com")
        if (
            not allowed
            or url.scheme != "https"
            or url.username
            or url.password
            or (url.port and url.port != 443)
        ):
            raise ValueError("Неизвестный push-сервис")
        try:
            auth = base64.urlsafe_b64decode(
                keys["auth"] + "=" * (-len(keys["auth"]) % 4)
            )
            public = base64.urlsafe_b64decode(
                keys["p256dh"] + "=" * (-len(keys["p256dh"]) % 4)
            )
            if len(auth) != 16 or len(public) != 65:
                raise ValueError()
            ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), public)
        except (KeyError, TypeError, ValueError):
            raise ValueError("Некорректные ключи push-подписки") from None
        with db() as con:
            existing = con.execute(
                "SELECT id,user_id FROM push_subscriptions WHERE endpoint=?",
                (endpoint,),
            ).fetchone()
            if existing and existing["user_id"] != g.user["id"]:
                abort(
                    409,
                    "Подписка относится к другому аккаунту. Отключите её перед сменой пользователя",
                )
            con.execute(
                "INSERT INTO push_subscriptions(user_id,endpoint,subscription_json,created_at) VALUES(?,?,?,?) ON CONFLICT(endpoint) DO UPDATE SET subscription_json=excluded.subscription_json,active=1",
                (g.user["id"], endpoint, json.dumps(subscription), now()),
            )
        return jsonify(ok=True)

    @app.post("/api/push/unsubscribe")
    def unsubscribe():
        data = payload()
        endpoint = data.get("endpoint")
        with db() as con:
            con.execute(
                "UPDATE push_subscriptions SET active=0 WHERE user_id=? AND endpoint=?",
                (g.user["id"], endpoint),
            )
        return jsonify(ok=True)

    @app.get("/api/escalations")
    def escalations():
        require_role("doctor")
        return jsonify(
            rows(
                "SELECT * FROM escalations WHERE doctor_id=? ORDER BY id DESC LIMIT 100",
                (g.user["id"],),
            )
        )
