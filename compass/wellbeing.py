"""Self-reported wellbeing activities; no clinical scoring or device measurements."""

from flask import g, jsonify
from compass.db import audit, db, now, rows

ACTIVITIES = {
    "breathing": ("practice", "Спокойная пауза", 60),
    "grounding": ("practice", "Пять вещей вокруг", 60),
    "stretch": ("practice", "Размяться без спешки", 120),
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
        return jsonify(activities=activities, lessons=lessons)

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
