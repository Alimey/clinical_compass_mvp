"""Подключение SQLite, схема данных и журнал действий."""

import sqlite3
from datetime import datetime, timezone
from flask import current_app, g
from compass.name_crypto import name_row_factory, seal, unseal


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"], timeout=10)
        g.db.row_factory = name_row_factory
        g.db.create_function("open_notice", 1, lambda value: unseal(value, "notice"))
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


def rows(sql, args=()):
    return [dict(row) for row in db().execute(sql, args).fetchall()]


def audit(actor, patient, action, detail):
    db().execute(
        "INSERT INTO audit(actor_id,patient_id,action,detail,created_at) VALUES(?,?,?,?,?)",
        (actor, patient, action, detail, now()),
    )


def notify(user, patient, title, body, alert=None):
    result = db().execute(
        "INSERT INTO notifications(user_id,patient_id,title,body,alert_id,created_at) VALUES(?,?,?,?,?,?)",
        (user, patient, title, seal(body, "notice"), alert, now()),
    )
    return result.lastrowid


def init_db():
    db().execute("PRAGMA journal_mode=WAL")
    db().executescript(
        """
    CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, role TEXT NOT NULL, name TEXT NOT NULL, doctor_id INTEGER);
    CREATE TABLE IF NOT EXISTS reports (id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL, created_at TEXT NOT NULL, mood INTEGER NOT NULL, anxiety INTEGER NOT NULL, adherence TEXT NOT NULL, adverse_effects TEXT NOT NULL, safety_signal INTEGER NOT NULL, note TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS alerts (id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL, report_id INTEGER NOT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'new', explanation TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS decisions (id INTEGER PRIMARY KEY AUTOINCREMENT, doctor_id INTEGER NOT NULL, patient_id INTEGER NOT NULL, created_at TEXT NOT NULL, decision TEXT NOT NULL, note TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS credentials (user_id INTEGER PRIMARY KEY REFERENCES users(id), username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS profiles (patient_id INTEGER PRIMARY KEY REFERENCES users(id), age INTEGER NOT NULL, occupation TEXT NOT NULL, context TEXT NOT NULL, goal TEXT NOT NULL, intolerance TEXT NOT NULL, plan TEXT NOT NULL DEFAULT '', plan_note TEXT NOT NULL DEFAULT '');
    CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), csrf TEXT NOT NULL, expires_at REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS login_attempts (identity TEXT PRIMARY KEY, count INTEGER NOT NULL, until REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL REFERENCES users(id), sender_id INTEGER NOT NULL REFERENCES users(id), body TEXT NOT NULL, created_at TEXT NOT NULL, read_at TEXT);
    CREATE TABLE IF NOT EXISTS proposals (id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL REFERENCES users(id), report_id INTEGER, kind TEXT NOT NULL, tier TEXT NOT NULL, title TEXT NOT NULL, reason TEXT NOT NULL, choice TEXT NOT NULL DEFAULT '', rule_version TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL, resolved_at TEXT, resolved_by INTEGER, resolution_note TEXT NOT NULL DEFAULT '', UNIQUE(patient_id, report_id, kind));
    CREATE TABLE IF NOT EXISTS notifications (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id), patient_id INTEGER NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL, alert_id INTEGER, created_at TEXT NOT NULL, delivered_at TEXT, read_at TEXT);
    CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, actor_id INTEGER NOT NULL, patient_id INTEGER NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS idempotency (user_id INTEGER NOT NULL, key TEXT NOT NULL, fingerprint TEXT NOT NULL, response TEXT NOT NULL, status INTEGER NOT NULL, PRIMARY KEY(user_id,key));
    CREATE TABLE IF NOT EXISTS demo_state (key TEXT PRIMARY KEY);
    CREATE INDEX IF NOT EXISTS ix_reports_patient ON reports(patient_id,id DESC);
    CREATE INDEX IF NOT EXISTS ix_alerts_patient ON alerts(patient_id,status);
    CREATE INDEX IF NOT EXISTS ix_messages_patient ON messages(patient_id,id);
    CREATE INDEX IF NOT EXISTS ix_notifications_user ON notifications(user_id,id DESC);
    CREATE INDEX IF NOT EXISTS ix_proposals_patient ON proposals(patient_id,status);
    CREATE INDEX IF NOT EXISTS ix_audit_patient ON audit(patient_id,id DESC);
    """
    )
    db().commit()
