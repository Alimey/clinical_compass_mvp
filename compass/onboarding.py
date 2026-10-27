"""Приглашения, регистрация и привязка пациента к специалисту."""

import hashlib
import os
import re
import secrets
import time

from flask import abort, g, jsonify
from werkzeug.security import generate_password_hash
from urllib.parse import urlsplit
from compass.db import db, rows, now, audit, notify


def digest(token):
    return hashlib.sha256(str(token).encode()).hexdigest()


def phone_number(value):
    if not isinstance(value, str):
        raise ValueError("Укажите телефон")
    number = re.sub(r"[\s()\-]", "", value)
    if not re.fullmatch(r"\+[1-9]\d{9,14}", number):
        raise ValueError("Телефон: + и от 10 до 15 цифр")
    return number


def init_onboarding():
    db().executescript(
        """
    CREATE TABLE IF NOT EXISTS invites(token_hash TEXT PRIMARY KEY, doctor_id INTEGER NOT NULL REFERENCES users(id), expires_at REAL NOT NULL, used_by INTEGER REFERENCES users(id), telegram_chat INTEGER, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS relative_invites(token_hash TEXT PRIMARY KEY, patient_id INTEGER NOT NULL REFERENCES users(id), expires_at REAL NOT NULL, used_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS activations(token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), expires_at REAL NOT NULL, used_at TEXT);
    CREATE TABLE IF NOT EXISTS telegram_sessions(chat_id INTEGER PRIMARY KEY, invite_hash TEXT NOT NULL, stage TEXT NOT NULL, data_json TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS telegram_updates(update_id INTEGER PRIMARY KEY, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS telegram_outbox(id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL, body TEXT NOT NULL, sent_at TEXT, attempts INTEGER NOT NULL DEFAULT 0, next_attempt REAL NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS service_state(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """
    )
    db().commit()


def available_phone(value):
    phone = phone_number(value)
    if any(
        db().execute(query, (phone,)).fetchone()
        for query in (
            "SELECT 1 FROM credentials WHERE username=?",
            "SELECT 1 FROM demographics WHERE phone=?",
            "SELECT 1 FROM contacts WHERE phone=?",
        )
    ):
        abort(409, "Этот телефон уже зарегистрирован. Войдите в свой аккаунт")
    return phone


def relative_invite_record(token):
    item = (
        db()
        .execute("SELECT * FROM relative_invites WHERE token_hash=?", (digest(token),))
        .fetchone()
    )
    if not item or item["used_by"] is not None or item["expires_at"] <= time.time():
        abort(
            410,
            "Приглашение истекло или уже использовано. Попросите новую ссылку у пациента",
        )
    return item


def invite_record(token, chat_id=None):
    item = (
        db()
        .execute("SELECT * FROM invites WHERE token_hash=?", (digest(token),))
        .fetchone()
    )
    if not item or item["expires_at"] <= time.time() or item["used_by"] is not None:
        abort(
            410,
            "Приглашение истекло или уже использовано. Попросите новую ссылку у специалиста",
        )
    if item["telegram_chat"] is not None and item["telegram_chat"] != chat_id:
        abort(409, "Приглашение уже открыто в Telegram. Продолжите регистрацию там")
    return item


def provision(token, data, password=None, chat_id=None):
    """Called inside a transaction; doctor binding never comes from user input."""
    invitation = invite_record(token, chat_id)
    name = data.get("name", "")
    if not isinstance(name, str) or not 2 <= len(name.strip()) <= 100:
        raise ValueError("Имя: от 2 до 100 символов")
    sex = data.get("sex", "Не указан")
    if sex not in ("Женский", "Мужской", "Не указан"):
        raise ValueError("Выберите пол")
    for key, lo, hi in [("age", 18, 100), ("height", 100, 250), ("weight", 30, 350)]:
        if type(data.get(key)) not in (int, float) or not lo <= data[key] <= hi:
            raise ValueError(
                "Проверьте возраст, рост и вес; демо рассчитано на взрослых"
            )
    if type(data["age"]) is not int:
        raise ValueError("Возраст должен быть целым числом")
    phone = phone_number(data.get("phone"))
    complaint = data.get("context", "")
    if not isinstance(complaint, str) or len(complaint) > 1000:
        raise ValueError("Комментарий: до 1000 символов")
    if password is not None and (
        not isinstance(password, str) or not 8 <= len(password) <= 200
    ):
        raise ValueError("Пароль: от 8 до 200 символов")
    if (
        db().execute("SELECT 1 FROM credentials WHERE username=?", (phone,)).fetchone()
        or db().execute("SELECT 1 FROM demographics WHERE phone=?", (phone,)).fetchone()
        or db().execute("SELECT 1 FROM contacts WHERE phone=?", (phone,)).fetchone()
    ):
        abort(
            409,
            "Этот телефон уже зарегистрирован. Используйте вход или другой синтетический номер",
        )
    user = (
        db()
        .execute(
            "INSERT INTO users(role,name,doctor_id) VALUES('patient',?,?)",
            (name.strip(), invitation["doctor_id"]),
        )
        .lastrowid
    )
    db().execute(
        "INSERT INTO credentials VALUES(?,?,?)",
        (user, phone, generate_password_hash(password or secrets.token_urlsafe(48))),
    )
    db().execute(
        "INSERT INTO profiles(patient_id,age,occupation,context,goal,intolerance) VALUES(?,?,?,?,?,?)",
        (
            user,
            data["age"],
            "",
            complaint.strip(),
            "Обсудить цель на первой встрече",
            "",
        ),
    )
    db().execute(
        "INSERT INTO demographics VALUES(?,?,?,?,?)",
        (user, sex, data["height"], data["weight"], phone),
    )
    db().execute(
        "UPDATE invites SET used_by=? WHERE token_hash=?",
        (user, invitation["token_hash"]),
    )
    audit(user, user, "intake.completed", "Карточка создана по приглашению специалиста")
    notify(
        invitation["doctor_id"],
        user,
        "Новый пациент",
        "Пациент завершил первичную анкету. Карточка создана.",
    )
    if chat_id is not None and isinstance(data.get("_ai_summary"), str):
        from compass.assistants import ai_settings

        db().execute(
            "INSERT INTO assistant_runs(patient_id,doctor_id,provider,model,question,answer,created_at) VALUES(?,?,?,?,?,?,?)",
            (
                user,
                invitation["doctor_id"],
                urlsplit(ai_settings()[0]).hostname or "configured-api",
                str(data.get("_ai_model", ""))[:100],
                "Первичная анкета через Telegram",
                data["_ai_summary"][:16000],
                now(),
            ),
        )
    activation = None
    if password is None:
        activation = secrets.token_urlsafe(32)
        db().execute(
            "INSERT INTO activations VALUES(?,?,?,NULL)",
            (digest(activation), user, time.time() + 86400),
        )
    return user, activation


def register_onboarding(app, require_role, payload, text, write_once):
    def account_fields(data):
        name = text(data, "name", 100, True)
        if len(name) < 2:
            raise ValueError("Имя: от 2 до 100 символов")
        password = text(data, "password", 200, True)
        if len(password) < 8:
            raise ValueError("Пароль: от 8 до 200 символов")
        return name, password

    @app.post("/api/intake/doctor")
    def register_doctor():
        data = payload()
        name, password = account_fields(data)
        profession = text(data, "profession", 100)
        organization = text(data, "organization", 100)
        with db() as con:
            con.execute("BEGIN IMMEDIATE")
            phone = available_phone(data.get("phone"))
            ident = con.execute(
                "INSERT INTO users(role,name) VALUES('doctor',?)", (name,)
            ).lastrowid
            con.execute(
                "INSERT INTO credentials VALUES(?,?,?)",
                (ident, phone, generate_password_hash(password)),
            )
            con.execute(
                "INSERT INTO contacts VALUES(?,?,?,?)",
                (ident, phone, profession, organization),
            )
        return jsonify(id=ident, username=phone), 201

    @app.post("/api/relative-invites")
    def create_relative_invite():
        require_role("patient")
        payload()
        token = secrets.token_urlsafe(24)
        with db() as con:
            con.execute(
                "INSERT INTO relative_invites VALUES(?,?,?,NULL,?)",
                (digest(token), g.user["id"], time.time() + 72 * 3600, now()),
            )
        return jsonify(token=token, expires_in_hours=72), 201

    @app.post("/api/intake/relative-info")
    def relative_info():
        data = payload()
        invitation = relative_invite_record(text(data, "token", 100, True))
        patient = rows(
            "SELECT name FROM users WHERE id=?", (invitation["patient_id"],)
        )[0]
        return jsonify(patient=patient)

    @app.post("/api/intake/relative")
    def register_relative():
        data = payload()
        name, password = account_fields(data)
        token = text(data, "token", 100, True)
        with db() as con:
            con.execute("BEGIN IMMEDIATE")
            invitation = relative_invite_record(token)
            phone = available_phone(data.get("phone"))
            ident = con.execute(
                "INSERT INTO users(role,name) VALUES('relative',?)", (name,)
            ).lastrowid
            con.execute(
                "INSERT INTO credentials VALUES(?,?,?)",
                (ident, phone, generate_password_hash(password)),
            )
            con.execute(
                "INSERT INTO relative_links VALUES(?,?)",
                (ident, invitation["patient_id"]),
            )
            con.execute(
                "UPDATE relative_invites SET used_by=? WHERE token_hash=?",
                (ident, invitation["token_hash"]),
            )
            audit(
                ident,
                invitation["patient_id"],
                "relative.registered",
                "Близкий зарегистрировался по приглашению пациента",
            )
        return jsonify(id=ident, username=phone), 201

    @app.post("/api/invites")
    def create_invite():
        require_role("doctor")
        payload()
        token = secrets.token_urlsafe(24)
        with db() as con:
            con.execute(
                "INSERT INTO invites(token_hash,doctor_id,expires_at,created_at) VALUES(?,?,?,?)",
                (digest(token), g.user["id"], time.time() + 72 * 3600, now()),
            )
        bot = os.environ.get("COMPASS_TELEGRAM_BOT_USERNAME", "").lstrip("@")
        if bot and not re.fullmatch(r"[A-Za-z0-9_]{5,32}", bot):
            bot = ""
        return (
            jsonify(
                token=token,
                expires_in_hours=72,
                telegram_url=f"https://t.me/{bot}?start={token}" if bot else None,
            ),
            201,
        )

    @app.post("/api/intake/info")
    def intake_info():
        data = payload()
        item = invite_record(text(data, "token", 100, True))
        doctor = rows(
            "SELECT u.name,c.profession,c.organization FROM users u LEFT JOIN contacts c ON c.user_id=u.id WHERE u.id=?",
            (item["doctor_id"],),
        )[0]
        return jsonify(doctor=doctor)

    @app.post("/api/intake/register")
    def intake_register():
        data = payload()
        token = text(data, "token", 100, True)
        password = text(data, "password", 200, True)
        with db() as con:
            con.execute("BEGIN IMMEDIATE")
            ident, _ = provision(token, data, password)
        return jsonify(id=ident, username=phone_number(data.get("phone"))), 201

    @app.post("/api/intake/activate")
    def activate():
        data = payload()
        token = text(data, "token", 100, True)
        password = text(data, "password", 200, True)
        if len(password) < 8:
            raise ValueError("Пароль: не менее 8 символов")
        with db() as con:
            con.execute("BEGIN IMMEDIATE")
            activation = con.execute(
                "SELECT * FROM activations WHERE token_hash=?", (digest(token),)
            ).fetchone()
            if (
                not activation
                or activation["used_at"]
                or activation["expires_at"] <= time.time()
            ):
                abort(410, "Ссылка активации истекла или использована")
            con.execute(
                "UPDATE credentials SET password_hash=? WHERE user_id=?",
                (generate_password_hash(password), activation["user_id"]),
            )
            con.execute(
                "UPDATE activations SET used_at=? WHERE token_hash=?",
                (now(), digest(token)),
            )
            con.execute(
                "DELETE FROM sessions WHERE user_id=?", (activation["user_id"],)
            )
        return jsonify(ok=True)
