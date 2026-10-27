"""Isolated local HTTP benchmarks and recovery drills. Run with repo .venv Python."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
import csv
import http.cookiejar
import json
import math
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid

ROOT = Path(os.environ.get("COMPASS_REPO", Path(__file__).resolve().parents[2]))
OUT = Path(os.environ.get("COMPASS_METRICS_OUT", ROOT / "test-results" / "metrics"))
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT))
os.environ.update(
    COMPASS_AI_API_KEY="",
    COMPASS_AI_BASE_URL="",
    COMPASS_AI_MODEL="",
    COMPASS_TELEGRAM_BOT_TOKEN="",
    COMPASS_PUBLIC_URL="",
    COMPASS_DISABLE_WORKER="1",
    COMPASS_SECURE_COOKIES="0",
)
from app import create_app
from compass.backup import backup
from compass.care import local_today
from runtime import revision, server_command, server_label, stop_server, system_info

DATA = {
    "commit": revision(ROOT),
    "started_at": datetime.now(timezone.utc).isoformat(),
    "environment": {
        **system_info(),
        "server": server_label(),
        "sqlite": sqlite3.sqlite_version,
        "workers": 1,
        "threads": 4,
        "network": "HTTP loopback 127.0.0.1; no TLS/WAN",
        "scheduler": "disabled for API isolation",
    },
    "single": {},
    "load": [],
    "scale": [],
    "recovery": {},
    "negative": [],
}
RESUME = "--post-load" in sys.argv
if RESUME:
    DATA = json.loads((OUT / "benchmark-results.json").read_text())
    DATA["scale"] = []
    DATA["resume_note"] = (
        "Load stages completed previously; scale/recovery resumed after correcting a synthetic ID collision with the seeded relative. No application changes."
    )


def save():
    (OUT / "benchmark-results.json").write_text(
        json.dumps(DATA, ensure_ascii=False, indent=2)
    )


def stats(values):
    values = sorted(values)
    return (
        {
            "n": len(values),
            "p50_ms": round(values[math.ceil(0.50 * len(values)) - 1], 3),
            "p95_ms": round(values[math.ceil(0.95 * len(values)) - 1], 3),
            "p99_ms": round(values[math.ceil(0.99 * len(values)) - 1], 3),
            "max_ms": round(values[-1], 3),
        }
        if values
        else {"n": 0}
    )


class Client:
    def __init__(self, base):
        self.base = base
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPCookieProcessor(self.cookies),
        )
        self.csrf = ""

    def call(self, path, data=None, key=None):
        headers = {"Content-Type": "application/json"}
        if self.csrf:
            headers["X-CSRF-Token"] = self.csrf
        if key:
            headers["Idempotency-Key"] = key
        payload = (
            json.dumps(data, ensure_ascii=False).encode() if data is not None else None
        )
        start = time.perf_counter()
        try:
            response = self.opener.open(
                urllib.request.Request(self.base + path, data=payload, headers=headers),
                timeout=20,
            )
            code = response.status
            raw = response.read()
            response.close()
        except urllib.error.HTTPError as error:
            code = error.code
            raw = error.read()
        except Exception as error:
            return (
                0,
                {"transport_error": type(error).__name__},
                (time.perf_counter() - start) * 1000,
            )
        elapsed = (time.perf_counter() - start) * 1000
        try:
            body = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            body = {"bytes": len(raw)}
        return code, body, elapsed

    def login(self, username):
        code, result, elapsed = self.call(
            "/api/auth/login", {"username": username, "password": "compass-demo"}
        )
        assert code == 200, (code, result)
        self.csrf = result["csrf"]
        return elapsed


def report(note="Synthetic HTTP benchmark", safety=False):
    return dict(
        mood=6,
        anxiety=4,
        adherence="Да",
        adverse_effects="",
        note=note,
        safety_signal=safety,
    )


@contextmanager
def server(path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {**os.environ, "COMPASS_DB": str(path), "PORT": str(port)}
    log = (OUT / "benchmark-server.log").open("a")
    started = time.perf_counter()
    process = subprocess.Popen(
        server_command(ROOT, port),
        cwd=ROOT,
        env=env,
        stdout=log,
        stderr=log,
        start_new_session=True,
    )
    base = f"http://127.0.0.1:{port}"
    probe = Client(base)
    try:
        for _ in range(300):
            if process.poll() is not None:
                raise RuntimeError("Benchmark server exited; see log")
            if probe.call("/api/health")[0] == 200:
                break
            time.sleep(0.03)
        else:
            raise RuntimeError("Benchmark server not ready")
        yield base, process, (time.perf_counter() - started) * 1000
    finally:
        stop_server(process)
        log.close()


def fixture(path, count, start=1000):
    with closing(sqlite3.connect(path)) as con, con:
        hashed = con.execute(
            "SELECT password_hash FROM credentials WHERE user_id=2"
        ).fetchone()[0]
        stamp = datetime.now(timezone.utc)
        today = local_today().isoformat()
        for ident in range(start, start + count):
            con.execute(
                "INSERT INTO users(id,role,name,doctor_id) VALUES(?,?,?,?)",
                (ident, "patient", f"Нагрузочный пациент {ident}", 1),
            )
            con.execute(
                "INSERT INTO credentials VALUES(?,?,?)",
                (ident, f"audit-{ident}", hashed),
            )
            con.execute(
                "INSERT INTO profiles(patient_id,age,occupation,context,goal,intolerance) VALUES(?,?,?,?,?,?)",
                (ident, 30, "Синтетический профиль", "Тестовая база", "Измерение", ""),
            )
            con.execute(
                "INSERT INTO prescriptions(id,patient_id,doctor_id,choice,title,times_json,starts_on,ends_on,note,created_at) VALUES(?,?,1,?,?,?,?,?,?,?)",
                (
                    ident,
                    ident,
                    "demo-alpha",
                    "Тестовое назначение",
                    '["00:00"]',
                    today,
                    today,
                    "Синтетический benchmark",
                    stamp.isoformat(),
                ),
            )
            for day in range(20):
                con.execute(
                    "INSERT INTO reports(patient_id,created_at,mood,anxiety,adherence,adverse_effects,safety_signal,note) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        ident,
                        (stamp - timedelta(days=day)).isoformat(),
                        6,
                        4,
                        "Да",
                        "",
                        0,
                        "Тестовая история",
                    ),
                )


def counts(path):
    with closing(sqlite3.connect(path)) as con, con:
        return {
            table: con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in [
                "users",
                "reports",
                "alerts",
                "notifications",
                "audit",
                "messages",
                "medication_marks",
                "decisions",
            ]
        }


def main():
    raw_file = (OUT / "load-requests.csv").open("a" if RESUME else "w", newline="")
    raw_writer = csv.writer(raw_file)
    if not RESUME:
        raw_writer.writerow(
            ["repeat", "sessions", "role", "operation", "status", "expected", "ms"]
        )

    with tempfile.TemporaryDirectory(prefix="ccb-") as directory:
        temp = Path(directory)
        path = temp / "base.db"
        create_app(path, seed_demo=False, testing=True)
        fixture(path, 100)
        clients = []
        with server(path) as (base, process, start_ms):
            DATA["startup_ms"] = start_ms
            for i in range(50):
                client = Client(base)
                username = "doctor" if i % 5 == 0 else f"audit-{1000+i}"
                client.login(username)
                clients.append(client)
            patient = Client(base)
            patient.login("audit-1000")
            doctor = Client(base)
            doctor.login("doctor")
            for name, actor, url, data, expected in (
                []
                if RESUME
                else [
                    ("patient_card", patient, "/api/patients/1000", None, 200),
                    ("doctor_patients", doctor, "/api/patients", None, 200),
                    (
                        "report_save",
                        patient,
                        "/api/patients/1000/reports",
                        report(),
                        201,
                    ),
                    (
                        "medication_mark",
                        patient,
                        "/api/prescriptions/1000/mark",
                        {
                            "day": local_today().isoformat(),
                            "time": "00:00",
                            "status": "taken",
                        },
                        200,
                    ),
                    ("doctor_notifications", doctor, "/api/notifications", None, 200),
                ]
            ):
                for _ in range(5):
                    actor.call(url, data)
                durations = []
                errors = []
                for _ in range(100):
                    code, body, ms = actor.call(
                        url, data, uuid.uuid4().hex if data else None
                    )
                    durations.append(ms)
                    if code != expected:
                        errors.append({"status": code, "body": body})
                DATA["single"][name] = {**stats(durations), "errors": errors}
            # Malformed and foreign operations: prove failed validation does not write.
            before = counts(path)
            variants = [
                ("mood_missing", {k: v for k, v in report().items() if k != "mood"}),
                ("mood_string", {**report(), "mood": "5"}),
                ("mood_bool", {**report(), "mood": True}),
                ("mood_low", {**report(), "mood": -1}),
                ("mood_high", {**report(), "mood": 11}),
                ("anxiety_none", {**report(), "anxiety": None}),
                ("anxiety_float", {**report(), "anxiety": 2.5}),
                (
                    "safety_missing",
                    {k: v for k, v in report().items() if k != "safety_signal"},
                ),
                ("safety_string", {**report(), "safety_signal": "false"}),
                ("safety_none", {**report(), "safety_signal": None}),
                ("adherence_invalid", {**report(), "adherence": "other"}),
                ("note_object", {**report(), "note": {}}),
                ("note_long", {**report(), "note": "x" * 501}),
                ("sleep_high", {**report(), "sleep": 11}),
                ("energy_bool", {**report(), "energy": False}),
            ]
            for name, body in [] if RESUME else variants:
                code, result, ms = patient.call("/api/patients/1000/reports", body)
                DATA["negative"].append(
                    {"name": name, "expected": 400, "actual": code, "ms": ms}
                )
            for name, actor, url, body, expected in (
                []
                if RESUME
                else [
                    ("anonymous_card", Client(base), "/api/patients/1000", None, 401),
                    ("foreign_card", patient, "/api/patients/1001", None, 404),
                    (
                        "foreign_report",
                        patient,
                        "/api/patients/1001/reports",
                        report(),
                        404,
                    ),
                    (
                        "patient_decision",
                        patient,
                        "/api/patients/1000/decisions",
                        {"decision": "test", "note": "synthetic"},
                        403,
                    ),
                ]
            ):
                code, result, ms = actor.call(url, body)
                DATA["negative"].append(
                    {"name": name, "expected": expected, "actual": code, "ms": ms}
                )
            DATA["negative_no_changes"] = before == counts(path)
            DATA["fixture_counts"] = counts(path)
            save()
        master = backup(path, temp / "master.db")
        for repeat in [] if RESUME else [1, 2]:
            for sessions in [1, 5, 10, 25, 50]:
                stage = backup(master, temp / f"load-{repeat}-{sessions}.db")
                with server(stage) as (base, process, ready):
                    # Select patient for the one-session stage; 20% doctor sessions above it.
                    actors = [clients[1]] if sessions == 1 else clients[:sessions]
                    for actor in actors:
                        actor.base = base
                    gate = threading.Barrier(len(actors))

                    def work(index, actor):
                        is_doctor = (
                            actor is not clients[1] and clients.index(actor) % 5 == 0
                        )
                        ident = 1000 + clients.index(actor)
                        gate.wait()
                        start = time.monotonic()
                        rows = []
                        turn = 0
                        while time.monotonic() - start < 14:
                            phase = turn % 10
                            if is_doctor:
                                op = (
                                    "doctor_list"
                                    if phase % 2 == 0
                                    else "doctor_notifications"
                                )
                                url = (
                                    "/api/patients"
                                    if phase % 2 == 0
                                    else "/api/notifications"
                                )
                                body = None
                                expected = 200
                            elif phase < 6:
                                op = "patient_card"
                                url = f"/api/patients/{ident}"
                                body = None
                                expected = 200
                            elif phase < 8:
                                op = "report_save"
                                url = f"/api/patients/{ident}/reports"
                                body = report()
                                expected = 201
                            elif phase == 8:
                                op = "medication_mark"
                                url = f"/api/prescriptions/{ident}/mark"
                                body = {
                                    "day": local_today().isoformat(),
                                    "time": "00:00",
                                    "status": "taken",
                                }
                                expected = 200
                            else:
                                op = "chat_send"
                                url = f"/api/patients/{ident}/messages"
                                body = {"body": "Синтетическая нагрузка"}
                                expected = 201
                            offset = time.monotonic() - start
                            code, result, ms = actor.call(
                                url, body, uuid.uuid4().hex if body else None
                            )
                            if offset >= 2:
                                rows.append(
                                    (
                                        repeat,
                                        sessions,
                                        "doctor" if is_doctor else "patient",
                                        op,
                                        code,
                                        expected,
                                        ms,
                                    )
                                )
                            turn += 1
                        return rows

                    started = time.perf_counter()
                    with ThreadPoolExecutor(max_workers=sessions) as pool:
                        rows = [
                            r
                            for group in pool.map(
                                lambda pair: work(*pair), enumerate(actors)
                            )
                            for r in group
                        ]
                    elapsed = time.perf_counter() - started
                    for r in rows:
                        raw_writer.writerow(r)
                    raw_file.flush()
                    errors = [r for r in rows if r[4] != r[5]]
                    measurement_seconds = elapsed - 2
                    result = {
                        "repeat": repeat,
                        "sessions": sessions,
                        **stats([r[6] for r in rows]),
                        "measurement_seconds": round(measurement_seconds, 3),
                        "rps": round(len(rows) / measurement_seconds, 2),
                        "errors": len(errors),
                        "error_percent": round(100 * len(errors) / len(rows), 3),
                        "status_counts": {
                            str(c): sum(r[4] == c for r in rows)
                            for c in set(r[4] for r in rows)
                        },
                        "operations": {
                            op: sum(r[3] == op for r in rows)
                            for op in set(r[3] for r in rows)
                        },
                    }
                    DATA["load"].append(result)
                    save()
                    print("LOAD", json.dumps(result), flush=True)
        for added in [0, 400, 900]:
            stage = backup(master, temp / f"scale-{added}.db")
            if added:
                fixture(stage, added, start=10000)
            with server(stage) as (base, process, ready):
                actor = Client(base)
                actor.login("doctor")
                for _ in range(5):
                    actor.call("/api/patients")
                values = []
                sizes = []
                errors = 0
                for _ in range(30):
                    code, result, ms = actor.call("/api/patients")
                    values.append(ms)
                    sizes.append(len(json.dumps(result, ensure_ascii=False).encode()))
                    errors += code != 200
                result = {
                    "added_patients": 100 + added,
                    "total_patients": 103 + added,
                    **stats(values),
                    "response_bytes": max(sizes),
                    "errors": errors,
                }
                DATA["scale"].append(result)
                save()
                print("SCALE", json.dumps(result), flush=True)
        recovery_db = backup(master, temp / "crash.db")
        with server(recovery_db) as (base, process, ready):
            actor = Client(base)
            actor.login("audit-1000")
            accepted = []
            last_key = uuid.uuid4().hex
            for i in range(50):
                code, body, ms = actor.call(
                    "/api/patients/1000/reports",
                    report("Crash drill accepted"),
                    last_key if i == 49 else uuid.uuid4().hex,
                )
                assert code == 201, (code, body)
                accepted.append(body["id"])
            before = counts(recovery_db)
            start = time.perf_counter()
            stop_server(process, force=True)
        with server(recovery_db) as (base, process, ready):
            recovered_ms = (time.perf_counter() - start) * 1000
            actor.base = base
            code, body, ms = actor.call(
                "/api/patients/1000/reports", report("Crash drill accepted"), last_key
            )
            after = counts(recovery_db)
            with closing(sqlite3.connect(recovery_db)) as con, con:
                found = {
                    r[0]
                    for r in con.execute(
                        "SELECT id FROM reports WHERE id IN ("
                        + ",".join("?" * len(accepted))
                        + ")",
                        accepted,
                    )
                }
                integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
            DATA["recovery"]["process_crash"] = {
                "accepted": len(accepted),
                "found": len(found),
                "lost": len(set(accepted) - found),
                "health_ready_ms": round(recovered_ms, 3),
                "integrity": integrity,
                "retry_status": code,
                "retry_same_id": body.get("id") == accepted[-1],
                "counts_unchanged_after_retry": before == after,
            }
            copy = temp / "snapshot.db"
            start = time.perf_counter()
            backup(recovery_db, copy)
            backup_ms = (time.perf_counter() - start) * 1000
            snapshot_counts = counts(copy)
            tail = []
            for i in range(10):
                code, result, ms = actor.call(
                    "/api/patients/1000/reports",
                    report("After snapshot"),
                    uuid.uuid4().hex,
                )
                assert code == 201
                tail.append(result["id"])
        restored = temp / "restored.db"
        start = time.perf_counter()
        backup(copy, restored)
        with server(restored) as (base, process, ready):
            actor.base = base
            code, result, ms = actor.call("/api/patients/1000")
            rto_ms = (time.perf_counter() - start) * 1000
            with closing(sqlite3.connect(restored)) as con, con:
                missing = sum(
                    con.execute(
                        "SELECT COUNT(*) FROM reports WHERE id=?", (ident,)
                    ).fetchone()[0]
                    == 0
                    for ident in tail
                )
            DATA["recovery"]["snapshot"] = {
                "backup_ms": round(backup_ms, 3),
                "restore_to_card_ms": round(rto_ms, 3),
                "snapshot_counts_preserved": snapshot_counts == counts(restored),
                "snapshot_report_count": snapshot_counts["reports"],
                "intentionally_post_backup_records": len(tail),
                "post_backup_records_absent": missing,
                "persistent_backup_schedule": "not configured/tested",
            }
            save()
        DATA["finished_at"] = datetime.now(timezone.utc).isoformat()
        save()
    raw_file.close()
    print("COMPLETE local benchmarks and recovery drills", flush=True)


if __name__ == "__main__":
    main()
