"""Self-reported wellbeing activities; no clinical scoring or device measurements."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from flask import abort, g, jsonify
from compass.db import audit, db, now, rows

ACTIVITIES = {
    "breathing": ("practice", "Спокойная пауза", 60),
    "grounding": ("practice", "Пять вещей вокруг", 60),
    "morning": ("practice", "Утренняя зарядка", 420),
    "desk": ("practice", "Разминка за столом", 180),
    "walk": ("practice", "Прогулка", 1200),
    "evening": ("practice", "Растяжка перед сном", 300),
    "diary": ("lesson", "Зачем вести дневник", 0),
    "consultation": ("lesson", "Как подготовиться к встрече", 0),
    "routine": ("lesson", "Маленькие шаги в течение дня", 0),
}


def init_wellbeing():
    con = db()
    columns = {r[1] for r in con.execute("PRAGMA table_info(reports)")}
    for name in ("sleep", "energy"):
        if name not in columns:
            con.execute(f"ALTER TABLE reports ADD COLUMN {name} INTEGER")
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS wellbeing_activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL REFERENCES users(id),
            activity_key TEXT NOT NULL, kind TEXT NOT NULL,
            title TEXT NOT NULL, duration_seconds INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_wellbeing_patient
            ON wellbeing_activities(patient_id, id DESC);
        CREATE TABLE IF NOT EXISTS care_trees (
            patient_id INTEGER PRIMARY KEY REFERENCES users(id),
            blossoms INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS activity_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL REFERENCES users(id),
            activity_key TEXT NOT NULL, day TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'planned',
            completed_at TEXT, created_at TEXT NOT NULL,
            UNIQUE(patient_id, activity_key, day)
        );
    """
    )
    con.commit()


def register_wellbeing(app, patient, require_role, payload, write_once):
    @app.get("/api/patients/<int:ident>/wellbeing")
    def wellbeing(ident):
        patient(ident)
        activities = rows(
            "SELECT * FROM wellbeing_activities WHERE patient_id=? ORDER BY id DESC LIMIT 300",
            (ident,),
        )
        # Lesson completion stays available even after the recent-activity window.
        lessons = [
            r[0]
            for r in db().execute(
                "SELECT DISTINCT activity_key FROM wellbeing_activities WHERE patient_id=? AND kind='lesson'",
                (ident,),
            )
        ]
        tree = rows("SELECT blossoms FROM care_trees WHERE patient_id=?", (ident,))
        plans = rows(
            "SELECT * FROM activity_plans WHERE patient_id=? ORDER BY day,id",
            (ident,),
        )
        return jsonify(
            activities=activities,
            lessons=lessons,
            tree_blossoms=tree[0]["blossoms"] if tree else 0,
            plans=plans,
        )

    @app.post("/api/patients/<int:ident>/tree")
    def blossom(ident):
        patient(ident)
        require_role("patient")
        data = payload()

        def save():
            db().execute(
                "INSERT INTO care_trees VALUES(?,1) ON CONFLICT(patient_id) "
                "DO UPDATE SET blossoms=MIN(blossoms+1,120)",
                (ident,),
            )
            count = rows(
                "SELECT blossoms FROM care_trees WHERE patient_id=?", (ident,)
            )[0]["blossoms"]
            return {"blossoms": count}, 200

        return write_once(data, save)

    @app.post("/api/patients/<int:ident>/activity-plans")
    def plan_activity(ident):
        patient(ident)
        require_role("patient")
        data = payload()
        key, day = data.get("activity"), data.get("day")
        if not isinstance(key, str) or key not in (
            "morning",
            "desk",
            "walk",
            "evening",
        ):
            raise ValueError("Выберите упражнение из списка движения")
        try:
            chosen = date.fromisoformat(day)
            today = datetime.now(ZoneInfo("Europe/Moscow")).date()
            if chosen.isoformat() != day or abs((chosen - today).days) > 366:
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError("Выберите дату в пределах года") from None

        def save():
            db().execute(
                "INSERT INTO activity_plans(patient_id,activity_key,day,created_at) VALUES(?,?,?,?) "
                "ON CONFLICT(patient_id,activity_key,day) DO UPDATE SET "
                "status=CASE WHEN status='cancelled' THEN 'planned' ELSE status END",
                (ident, key, day, now()),
            )
            record = rows(
                "SELECT id FROM activity_plans WHERE patient_id=? AND activity_key=? AND day=?",
                (ident, key, day),
            )[0]
            return record, 200

        return write_once(data, save)

    @app.post("/api/patients/<int:ident>/activity-plans/<int:plan_id>/<action>")
    def update_activity_plan(ident, plan_id, action):
        patient(ident)
        require_role("patient")
        if action not in ("complete", "cancel"):
            abort(404)
        data = payload()

        def save():
            records = rows(
                "SELECT * FROM activity_plans WHERE id=? AND patient_id=?",
                (plan_id, ident),
            )
            if not records:
                abort(404)
            record = records[0]
            if record["status"] == "done":
                if action == "cancel":
                    raise ValueError("Выполненное занятие уже сохранено")
                return {"ok": True}, 200
            stamp = now()
            if action == "complete":
                if (
                    record["status"] != "planned"
                    or record["day"]
                    > datetime.now(ZoneInfo("Europe/Moscow")).date().isoformat()
                ):
                    raise ValueError(
                        "Можно отметить только запланированное занятие за сегодня или прошедший день"
                    )
                kind, title, seconds = ACTIVITIES[record["activity_key"]]
                db().execute(
                    "INSERT INTO wellbeing_activities(patient_id,activity_key,kind,title,duration_seconds,created_at) VALUES(?,?,?,?,?,?)",
                    (ident, record["activity_key"], kind, title, seconds, stamp),
                )
                audit(
                    g.user["id"], ident, "wellbeing.completed", "Самоотметка: " + title
                )
            db().execute(
                "UPDATE activity_plans SET status=?,completed_at=? WHERE id=?",
                (
                    "done" if action == "complete" else "cancelled",
                    stamp if action == "complete" else None,
                    plan_id,
                ),
            )
            return {"ok": True}, 200

        return write_once(data, save)

    @app.post("/api/patients/<int:ident>/wellbeing")
    def complete(ident):
        patient(ident)
        require_role("patient")
        data = payload()
        key = data.get("activity")
        if not isinstance(key, str) or key not in ACTIVITIES:
            raise ValueError("Выберите занятие из списка")
        kind, title, seconds = ACTIVITIES[key]

        def save():
            if kind == "lesson":
                existing = (
                    db()
                    .execute(
                        "SELECT id FROM wellbeing_activities WHERE patient_id=? AND activity_key=?",
                        (ident, key),
                    )
                    .fetchone()
                )
                if existing:
                    return {"id": existing[0]}, 200
            cur = db().execute(
                "INSERT INTO wellbeing_activities(patient_id,activity_key,kind,title,duration_seconds,created_at) VALUES(?,?,?,?,?,?)",
                (ident, key, kind, title, seconds, now()),
            )
            audit(g.user["id"], ident, "wellbeing.completed", "Самоотметка: " + title)
            return {"id": cur.lastrowid}, 201

        return write_once(data, save)
