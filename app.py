"""Clinical Compass: authenticated synthetic PWA, never for real patient care."""

import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time
from urllib.parse import urlsplit

from flask import Flask, abort, g, jsonify, request
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash
from dotenv import load_dotenv
from compass.care import init_care, register_care, care_bundle
from compass.onboarding import init_onboarding, register_onboarding, phone_number
from compass.assistants import register_assistants
from compass.delivery import init_delivery, register_delivery
from compass.wellbeing import init_wellbeing, register_wellbeing
from compass.sections import init_sections, register_sections, preferences

from compass.db import audit, db, init_db, notify, now, rows
from compass.demo import seed
from compass.rules import add_proposals, CATALOG, VERSION


def create_app(database=None, *, seed_demo=True, testing=False):
    load_dotenv(Path(__file__).with_name(".env"))
    app = Flask(__name__, static_folder="static")
    app.config.update(
        DATABASE=str(
            database
            or os.environ.get(
                "COMPASS_DB", Path(__file__).with_name("instance") / "compass.db"
            )
        ),
        MAX_CONTENT_LENGTH=65536,
        TESTING=testing,
        SECURE_COOKIE=os.environ.get("COMPASS_SECURE_COOKIES") == "1",
    )
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)

    @app.teardown_appcontext
    def close_db(_error):
        con = g.pop("db", None)
        if con is not None:
            con.close()

    with app.app_context():
        init_db()
        seed(seed_demo)
        init_care(seed_demo)
        init_onboarding()
        init_delivery()
        init_wellbeing()
        init_sections(seed_demo)

    @app.before_request
    def authenticate():
        g.user, g.csrf = None, None
        if request.method == "POST":
            origin = request.headers.get("Origin")
            if request.headers.get("Sec-Fetch-Site") == "cross-site" or (
                origin
                and (
                    urlsplit(origin).scheme not in ("http", "https")
                    or urlsplit(origin).netloc != request.host
                )
            ):
                abort(403, "Запрос с другого сайта запрещён")
        if not request.path.startswith("/api/") or request.path == "/api/health":
            return
        token = request.cookies.get("compass_session", "")
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        account = (
            db()
            .execute(
                """SELECT u.*, s.csrf FROM sessions s JOIN users u ON u.id=s.user_id
            WHERE s.token_hash=? AND s.expires_at>?""",
                (token_hash, time.time()),
            )
            .fetchone()
        )
        if account:
            g.user = dict(account)
            g.csrf = g.user.pop("csrf")
            g.token_hash = token_hash
        if request.path in (
            "/api/auth/login",
            "/api/auth/me",
        ) or request.path.startswith("/api/intake/"):
            return
        if not g.user:
            abort(401, "Войдите в демо-аккаунт")
        if request.method == "POST" and not secrets.compare_digest(
            request.headers.get("X-CSRF-Token", "").encode(), g.csrf.encode()
        ):
            abort(403, "Сессия формы устарела. Обновите страницу")

    @app.after_request
    def security_headers(response):
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "same-origin",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'",
                "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
            }
        )
        return response

    @app.errorhandler(ValueError)
    def invalid(error):
        return jsonify(error=str(error)), 400

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error=error.description), error.code

    @app.errorhandler(sqlite3.OperationalError)
    def database_error(error):
        app.logger.exception("Database operation failed")
        return (
            jsonify(error="Хранилище временно недоступно. Повторите запрос позже"),
            503,
        )

    def require_role(role):
        if g.user["role"] != role:
            abort(403, "Недостаточно прав для этого действия")

    def patient(ident):
        record = (
            db()
            .execute("SELECT * FROM users WHERE id=? AND role='patient'", (ident,))
            .fetchone()
        )
        if (
            not record
            or g.user["role"] not in ("doctor", "patient")
            or (g.user["role"] == "doctor" and record["doctor_id"] != g.user["id"])
            or (g.user["role"] == "patient" and ident != g.user["id"])
        ):
            abort(404, "Пациент не найден или недоступен")
        return dict(record)

    def payload():
        data = request.get_json()
        if not isinstance(data, dict):
            raise ValueError("Ожидается JSON-объект")
        return data

    def text(data, key, limit=500, required=False):
        value = data.get(key, "")
        if (
            not isinstance(value, str)
            or len(value) > limit
            or (required and not value.strip())
        ):
            raise ValueError(
                f'Поле {key}: {"обязательно, " if required else ""}до {limit} символов'
            )
        return value.strip()

    def write_once(data, action):
        """Commit data, audit, notifications and response atomically; retry safely."""
        key = request.headers.get("Idempotency-Key", "")
        if len(key) > 100:
            raise ValueError("Слишком длинный ключ запроса")
        fingerprint = hashlib.sha256(
            (request.path + json.dumps(data, sort_keys=True)).encode()
        ).hexdigest()
        with db() as con:
            con.execute("BEGIN IMMEDIATE")
            if key:
                old = con.execute(
                    "SELECT * FROM idempotency WHERE user_id=? AND key=?",
                    (g.user["id"], key),
                ).fetchone()
                if old:
                    if old["fingerprint"] != fingerprint:
                        abort(409, "Ключ запроса уже использован для других данных")
                    return jsonify(json.loads(old["response"])), old["status"]
            result, code = action()
            if key:
                con.execute(
                    "INSERT INTO idempotency VALUES(?,?,?,?,?)",
                    (g.user["id"], key, fingerprint, json.dumps(result), code),
                )
        return jsonify(result), code

    @app.get("/")
    def index():
        return app.send_static_file("index.html")

    @app.get("/sw.js")
    def worker():
        return app.send_static_file("sw.js")

    @app.get("/api/health")
    def health():
        db().execute("SELECT 1").fetchone()
        return jsonify(status="ok", mode="synthetic-demo", version=VERSION)

    @app.get("/api/auth/me")
    def me():
        return jsonify(user=g.user, csrf=g.csrf)

    @app.post("/api/auth/login")
    def login():
        data = payload()
        username, password = text(data, "username", 80, True), text(
            data, "password", 200, True
        )
        if username.startswith("+"):
            username = phone_number(username)
        identity = hashlib.sha256(
            ((request.remote_addr or "") + "|" + username.lower()).encode()
        ).hexdigest()
        stamp = time.time()
        with db() as con:
            con.execute("BEGIN IMMEDIATE")
            attempt = con.execute(
                "SELECT * FROM login_attempts WHERE identity=?", (identity,)
            ).fetchone()
            if attempt and attempt["count"] >= 6 and attempt["until"] > stamp:
                return (
                    jsonify(error="Слишком много попыток. Повторите через 5 минут"),
                    429,
                )
            account = con.execute(
                "SELECT * FROM credentials WHERE username=? OR user_id IN (SELECT user_id FROM contacts WHERE phone=?) OR user_id IN (SELECT patient_id FROM demographics WHERE phone=?)",
                (
                    username,
                    username,
                    username,
                ),
            ).fetchone()
            valid = account and check_password_hash(account["password_hash"], password)
            if not valid:
                count = (
                    attempt["count"] + 1 if attempt and attempt["until"] > stamp else 1
                )
                con.execute(
                    "INSERT OR REPLACE INTO login_attempts VALUES(?,?,?)",
                    (identity, count, stamp + 300),
                )
                return jsonify(error="Неверный логин или пароль"), 401
            con.execute("DELETE FROM login_attempts WHERE identity=?", (identity,))
            con.execute("DELETE FROM sessions WHERE expires_at<=?", (stamp,))
            if getattr(g, "token_hash", None):
                con.execute("DELETE FROM sessions WHERE token_hash=?", (g.token_hash,))
            token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
            con.execute(
                "INSERT INTO sessions VALUES(?,?,?,?)",
                (
                    hashlib.sha256(token.encode()).hexdigest(),
                    account["user_id"],
                    csrf,
                    stamp + 28800,
                ),
            )
        user = rows("SELECT * FROM users WHERE id=?", (account["user_id"],))[0]
        response = jsonify(user=user, csrf=csrf)
        response.set_cookie(
            "compass_session",
            token,
            max_age=28800,
            httponly=True,
            secure=app.config["SECURE_COOKIE"],
            samesite="Strict",
        )
        return response

    @app.post("/api/auth/logout")
    def logout():
        payload()
        with db() as con:
            con.execute("DELETE FROM sessions WHERE token_hash=?", (g.token_hash,))
        response = jsonify(ok=True)
        response.delete_cookie(
            "compass_session",
            httponly=True,
            secure=app.config["SECURE_COOKIE"],
            samesite="Strict",
        )
        return response

    @app.get("/api/patients")
    def patients():
        condition, value = (
            ("u.doctor_id", g.user["id"])
            if g.user["role"] == "doctor"
            else ("u.id", g.user["id"])
        )
        result = rows(
            f"""SELECT u.id,u.name,p.age,p.occupation,p.goal,
            ((SELECT COUNT(*) FROM alerts a WHERE a.patient_id=u.id AND a.status='new') + (SELECT COUNT(*) FROM support_events s WHERE s.patient_id=u.id AND s.doctor_read_at IS NULL)) AS unread,
            (SELECT COUNT(*) FROM messages m WHERE m.patient_id=u.id AND m.sender_id!=? AND m.read_at IS NULL) AS unread_messages,
            (SELECT mood FROM reports r WHERE r.patient_id=u.id ORDER BY id DESC LIMIT 1) AS mood,
            (SELECT anxiety FROM reports r WHERE r.patient_id=u.id ORDER BY id DESC LIMIT 1) AS anxiety,
            (SELECT created_at FROM reports r WHERE r.patient_id=u.id ORDER BY id DESC LIMIT 1) AS last_report
            FROM users u LEFT JOIN profiles p ON p.patient_id=u.id WHERE u.role='patient' AND {condition}=? ORDER BY u.id""",
            (g.user["id"], value),
        )
        if g.user["role"] == "doctor":
            for record in result:
                if not preferences(record["id"])["share_mood"]:
                    record["mood"] = record["anxiety"] = record["last_report"] = None
        return jsonify(result)

    @app.get("/api/patients/<int:ident>")
    def detail(ident):
        account = patient(ident)
        reports = rows(
            "SELECT * FROM reports WHERE patient_id=? ORDER BY id DESC LIMIT 100",
            (ident,),
        )
        shared_reports = g.user["role"] == "patient" or preferences(ident)["share_mood"]
        if not shared_reports:
            reports = []
        recent = reports[:7]
        applicable = [r for r in recent if r["adherence"] != "Не применимо"]
        adherence = (
            round(
                sum(
                    {"Да": 1, "Частично": 0.5, "Нет": 0}[r["adherence"]]
                    for r in applicable
                )
                / len(applicable)
                * 100
            )
            if applicable
            else None
        )
        profile = rows("SELECT * FROM profiles WHERE patient_id=?", (ident,))
        if profile:
            extra = rows("SELECT * FROM demographics WHERE patient_id=?", (ident,))
            if extra:
                profile[0].update(extra[0])
        doctor = rows(
            "SELECT u.id,u.name,c.phone,c.profession,c.organization FROM users u LEFT JOIN contacts c ON c.user_id=u.id WHERE u.id=?",
            (account["doctor_id"],),
        )[0]
        return jsonify(
            care=care_bundle(ident),
            patient=account,
            profile=profile[0] if profile else {},
            reports=reports,
            reports_shared=shared_reports,
            reports_total=(
                db()
                .execute("SELECT COUNT(*) FROM reports WHERE patient_id=?", (ident,))
                .fetchone()[0]
                if shared_reports
                else 0
            ),
            adherence=adherence,
            doctor=doctor,
            alerts=rows(
                "SELECT * FROM alerts WHERE patient_id=? ORDER BY id DESC LIMIT 100",
                (ident,),
            ),
            proposals=(
                rows(
                    "SELECT * FROM proposals WHERE patient_id=? ORDER BY id DESC LIMIT 100",
                    (ident,),
                )
                if g.user["role"] == "doctor"
                else []
            ),
            decisions=rows(
                "SELECT * FROM decisions WHERE patient_id=? ORDER BY id DESC LIMIT 100",
                (ident,),
            ),
            catalog=CATALOG,
            rule_version=VERSION,
        )

    @app.post("/api/patients/<int:ident>/reports")
    def report(ident):
        account = patient(ident)
        require_role("patient")
        data = payload()
        for key in ("mood", "anxiety"):
            if type(data.get(key)) is not int or not 0 <= data[key] <= 10:
                raise ValueError("Настроение и тревога: целые числа от 0 до 10")
        if type(data.get("safety_signal")) is not bool:
            raise ValueError("Укажите сигнал безопасности")
        if data.get("adherence") not in ("Да", "Частично", "Нет", "Не применимо"):
            raise ValueError("Выберите соблюдение рекомендаций")
        adverse, note = text(data, "adverse_effects"), text(data, "note")
        for key in ("sleep", "energy"):
            if data.get(key) is not None and (
                type(data[key]) is not int or not 0 <= data[key] <= 10
            ):
                raise ValueError("Сон и энергия: целые числа от 0 до 10")

        def action():
            stamp = now()
            cur = db().execute(
                "INSERT INTO reports(patient_id,created_at,mood,anxiety,adherence,adverse_effects,safety_signal,note,sleep,energy) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    ident,
                    stamp,
                    data["mood"],
                    data["anxiety"],
                    data["adherence"],
                    adverse,
                    int(data["safety_signal"]),
                    note,
                    data.get("sleep"),
                    data.get("energy"),
                ),
            )
            report_id = cur.lastrowid
            add_proposals(ident, report_id, data)
            if data["safety_signal"]:
                alert = (
                    db()
                    .execute(
                        "INSERT INTO alerts(patient_id,report_id,created_at,explanation) VALUES(?,?,?,?)",
                        (
                            ident,
                            report_id,
                            stamp,
                            "Самоотчёт содержит опасения за безопасность · учебное правило S-01",
                        ),
                    )
                    .lastrowid
                )
                notify(
                    account["doctor_id"],
                    ident,
                    "Сигнал безопасности",
                    account["name"] + " отметил(а) опасения за безопасность.",
                    alert,
                )
            else:
                notify(
                    account["doctor_id"],
                    ident,
                    "Новый самоотчёт",
                    account["name"] + " заполнил(а) дневник.",
                )
            audit(
                g.user["id"],
                ident,
                "report.created",
                "Сохранён самоотчёт #" + str(report_id),
            )
            return {"id": report_id, "safety_signal": data["safety_signal"]}, 201

        return write_once(data, action)

    @app.post("/api/alerts/<int:ident>/review")
    def review(ident):
        require_role("doctor")
        payload()
        alert = rows("SELECT * FROM alerts WHERE id=?", (ident,))
        if not alert:
            abort(404, "Сигнал не найден")
        patient(alert[0]["patient_id"])
        with db() as con:
            con.execute("BEGIN IMMEDIATE")
            changed = con.execute(
                "UPDATE alerts SET status='reviewed' WHERE id=? AND status='new'",
                (ident,),
            ).rowcount
            con.execute(
                "UPDATE notifications SET read_at=COALESCE(read_at,?) WHERE alert_id=? AND user_id=?",
                (now(), ident, g.user["id"]),
            )
            if changed:
                con.execute(
                    "UPDATE escalations SET status='resolved' WHERE alert_id=? AND doctor_id=?",
                    (ident, g.user["id"]),
                )
                audit(
                    g.user["id"],
                    alert[0]["patient_id"],
                    "alert.reviewed",
                    "Просмотрен сигнал #" + str(ident),
                )
        return jsonify(status="reviewed")

    @app.post("/api/patients/<int:ident>/decisions")
    def decision(ident):
        patient(ident)
        require_role("doctor")
        data = payload()
        action, note = text(data, "decision", 100, True), text(data, "note", 500, True)
        if action not in (
            "Продолжить наблюдение",
            "Назначить очную консультацию",
            "Рассмотреть направление к специалисту",
            "Другое",
        ):
            raise ValueError("Выберите действие врача")

        def save():
            cur = db().execute(
                "INSERT INTO decisions(doctor_id,patient_id,created_at,decision,note) VALUES(?,?,?,?,?)",
                (g.user["id"], ident, now(), action, note),
            )
            audit(g.user["id"], ident, "decision.created", action)
            notify(ident, ident, "Новое решение врача", action)
            return {"id": cur.lastrowid}, 201

        return write_once(data, save)

    @app.post("/api/patients/<int:ident>/proposals")
    def propose(ident):
        patient(ident)
        require_role("doctor")
        data = payload()
        choice = text(data, "choice", 80, True)
        option = next((item for item in CATALOG if item["id"] == choice), None)
        if not option:
            raise ValueError("Неизвестный демо-вариант")

        def save():
            profile = (
                db()
                .execute("SELECT * FROM profiles WHERE patient_id=?", (ident,))
                .fetchone()
            )
            if profile and profile["intolerance"] == choice:
                abort(409, "В профиле есть учебная несовместимость с этим вариантом")
            if (
                db()
                .execute(
                    "SELECT 1 FROM proposals WHERE patient_id=? AND choice=? AND status='pending'",
                    (ident, choice),
                )
                .fetchone()
            ):
                abort(409, "Такой вариант уже ожидает решения")
            cur = db().execute(
                """INSERT INTO proposals(patient_id,kind,tier,title,reason,choice,rule_version,created_at)
                VALUES(?,'therapy','desirable',?,?,?,?,?)""",
                (
                    ident,
                    "Рассмотреть " + option["name"],
                    "Вымышленный вариант сопровождения; не лекарство и не назначение.",
                    choice,
                    VERSION,
                    now(),
                ),
            )
            audit(g.user["id"], ident, "proposal.created", option["name"])
            return {"id": cur.lastrowid}, 201

        return write_once(data, save)

    @app.post("/api/proposals/<int:ident>/resolve")
    def resolve(ident):
        require_role("doctor")
        data = payload()
        resolution = text(data, "status", 20, True)
        note = text(data, "note", 500, True)
        if resolution not in ("accepted", "rejected"):
            raise ValueError("Выберите подтверждение или отклонение")

        def save():
            record = (
                db().execute("SELECT * FROM proposals WHERE id=?", (ident,)).fetchone()
            )
            if not record:
                abort(404, "Предложение не найдено")
            patient(record["patient_id"])
            if record["status"] != "pending":
                abort(409, "Решение уже принято. Обновите карточку")
            if record["kind"] == "therapy" and resolution == "accepted":
                profile = (
                    db()
                    .execute(
                        "SELECT * FROM profiles WHERE patient_id=?",
                        (record["patient_id"],),
                    )
                    .fetchone()
                )
                if not profile:
                    abort(409, "Профиль пациента не заполнен")
                if profile["intolerance"] == record["choice"]:
                    abort(409, "В профиле есть учебная несовместимость")
                db().execute(
                    "UPDATE profiles SET plan=?,plan_note=? WHERE patient_id=?",
                    (record["choice"], note, record["patient_id"]),
                )
            stamp = now()
            db().execute(
                "UPDATE proposals SET status=?,resolved_at=?,resolved_by=?,resolution_note=? WHERE id=?",
                (resolution, stamp, g.user["id"], note, ident),
            )
            decision_text = (
                "Подтверждено: " if resolution == "accepted" else "Отклонено: "
            ) + record["title"]
            db().execute(
                "INSERT INTO decisions(doctor_id,patient_id,created_at,decision,note) VALUES(?,?,?,?,?)",
                (g.user["id"], record["patient_id"], stamp, decision_text, note),
            )
            audit(
                g.user["id"],
                record["patient_id"],
                "proposal." + resolution,
                record["title"],
            )
            notify(
                record["patient_id"],
                record["patient_id"],
                "Решение по плану",
                decision_text,
            )
            return {"status": resolution}, 200

        return write_once(data, save)

    @app.get("/api/patients/<int:ident>/messages")
    def messages(ident):
        patient(ident)
        return jsonify(
            rows(
                """SELECT m.*,u.name AS sender_name,u.role AS sender_role FROM messages m
            JOIN users u ON u.id=m.sender_id WHERE patient_id=? ORDER BY id DESC LIMIT 100""",
                (ident,),
            )[::-1]
        )

    @app.post("/api/patients/<int:ident>/messages")
    def send_message(ident):
        account = patient(ident)
        data = payload()
        body = text(data, "body", 1000, True)

        def save():
            cur = db().execute(
                "INSERT INTO messages(patient_id,sender_id,body,created_at) VALUES(?,?,?,?)",
                (ident, g.user["id"], body, now()),
            )
            recipient = account["doctor_id"] if g.user["role"] == "patient" else ident
            notify(
                recipient,
                ident,
                "Новое сообщение",
                g.user["name"] + " отправил(а) сообщение.",
            )
            audit(
                g.user["id"], ident, "message.sent", "Сообщение #" + str(cur.lastrowid)
            )
            return {"id": cur.lastrowid}, 201

        return write_once(data, save)

    @app.post("/api/patients/<int:ident>/messages/read")
    def read_messages(ident):
        patient(ident)
        data = payload()
        ids = data.get("ids")
        if (
            not isinstance(ids, list)
            or len(ids) > 100
            or any(type(i) is not int for i in ids)
        ):
            raise ValueError("Укажите до 100 идентификаторов показанных сообщений")
        if ids:
            placeholders = ",".join("?" for _ in ids)
            with db() as con:
                con.execute(
                    f"UPDATE messages SET read_at=? WHERE patient_id=? AND sender_id!=? AND read_at IS NULL AND id IN ({placeholders})",
                    (now(), ident, g.user["id"], *ids),
                )
        return jsonify(ok=True)

    @app.get("/api/notifications")
    def notifications():
        return jsonify(
            items=rows(
                "SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 50",
                (g.user["id"],),
            ),
            unread=db()
            .execute(
                "SELECT COUNT(*) FROM notifications WHERE user_id=? AND read_at IS NULL",
                (g.user["id"],),
            )
            .fetchone()[0],
            server_time=now(),
        )

    @app.post("/api/notifications/delivered")
    def delivered_notifications():
        data = payload()
        ids = data.get("ids")
        if (
            not isinstance(ids, list)
            or not 1 <= len(ids) <= 50
            or any(type(i) is not int for i in ids)
        ):
            raise ValueError("Укажите от 1 до 50 идентификаторов уведомлений")
        ids = list(set(ids))
        placeholders = ",".join("?" for _ in ids)
        stamp = now()
        with db() as con:
            con.execute("BEGIN IMMEDIATE")
            count = con.execute(
                f"SELECT COUNT(*) FROM notifications WHERE user_id=? AND id IN ({placeholders})",
                (g.user["id"], *ids),
            ).fetchone()[0]
            if count != len(ids):
                abort(404, "Уведомление не найдено")
            con.execute(
                f"UPDATE notifications SET delivered_at=COALESCE(delivered_at,?) WHERE user_id=? AND id IN ({placeholders})",
                (stamp, g.user["id"], *ids),
            )
        return jsonify(delivered_at=stamp)

    @app.post("/api/notifications/read")
    def read_notifications():
        data = payload()
        ident = data.get("id")
        if type(ident) is not int:
            raise ValueError("Укажите уведомление")
        with db() as con:
            if not con.execute(
                "UPDATE notifications SET read_at=COALESCE(read_at,?),delivered_at=COALESCE(delivered_at,?) WHERE user_id=? AND id=?",
                (now(), now(), g.user["id"], ident),
            ).rowcount:
                abort(404, "Уведомление не найдено")
        return jsonify(ok=True)

    @app.get("/api/patients/<int:ident>/audit")
    def journal(ident):
        patient(ident)
        require_role("doctor")
        return jsonify(
            rows(
                """SELECT a.*,u.name AS actor_name FROM audit a JOIN users u ON u.id=a.actor_id
            WHERE patient_id=? ORDER BY a.id DESC LIMIT 100""",
                (ident,),
            )
        )

    register_care(app, patient, require_role, payload, text, write_once)
    register_onboarding(app, require_role, payload, text, write_once)
    register_assistants(app, patient, require_role, payload, text, write_once)
    register_delivery(app, require_role, payload)
    register_wellbeing(app, patient, require_role, payload, write_once)
    register_sections(app, patient, require_role, payload, text, write_once)
    return app


if __name__ == "__main__":
    application = create_app()
    if os.environ.get("COMPASS_DISABLE_WORKER") != "1":
        from compass.worker import start_worker

        start_worker(application)
    application.run(
        host=os.environ.get("COMPASS_HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
        debug=False,
    )
