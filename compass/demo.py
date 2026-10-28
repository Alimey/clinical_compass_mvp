"""Начальные демонстрационные аккаунты и записи."""

from datetime import datetime, timedelta, timezone
from werkzeug.security import generate_password_hash
from compass.db import db, notify
from compass.rules import add_proposals, VERSION
from compass.name_crypto import seal

# These credentials are deliberately public demo fixtures, never real accounts.
DEMO_PASSWORD = "compass-demo"
ACCOUNTS = [
    (1, "doctor", "Анна Соколова", None, "doctor"),
    (2, "patient", "Александра Морозова", 1, "patient-a"),
    (3, "patient", "Михаил Волков", 1, "patient-b"),
    (4, "doctor", "Илья Крылов", None, "doctor-other"),
    (5, "patient", "Виктория Орлова", 4, "patient-c"),
]


def seed(history=True):
    con = db()
    with con:
        for ident, role, name, doctor, username in ACCOUNTS:
            con.execute(
                "INSERT OR IGNORE INTO users VALUES(?,?,?,?)",
                (ident, role, seal(name), doctor),
            )
            con.execute(
                "UPDATE users SET name=? WHERE id=? AND name IN ('Врач (демо)','Пациент А (вымышленный)','Пациент Б (вымышленный)')",
                (seal(name), ident),
            )
            if not con.execute(
                "SELECT 1 FROM credentials WHERE user_id=?", (ident,)
            ).fetchone():
                con.execute(
                    "INSERT INTO credentials VALUES(?,?,?)",
                    (ident, username, generate_password_hash(DEMO_PASSWORD)),
                )
        profiles = [
            (
                2,
                29,
                "Дизайнер",
                "Учебный кейс: напряжённый рабочий период, нерегулярный сон.",
                "Отслеживать самочувствие и восстановить ритм дня",
                "demo-beta",
            ),
            (
                3,
                37,
                "Преподаватель",
                "Учебный кейс: постепенное улучшение самочувствия на фоне наблюдения.",
                "Сохранить привычку вести дневник",
                "",
            ),
            (
                5,
                31,
                "Инженер",
                "Учебный кейс другого врача: проверка разделения доступа.",
                "Регулярный контакт с ведущим врачом",
                "",
            ),
        ]
        for profile in profiles:
            con.execute(
                "INSERT OR IGNORE INTO profiles(patient_id,age,occupation,context,goal,intolerance) VALUES(?,?,?,?,?,?)",
                profile,
            )
        if con.execute("SELECT 1 FROM demo_state WHERE key='showcase-v2'").fetchone():
            return
        con.execute("INSERT INTO demo_state VALUES('showcase-v2')")
        if not history:
            return
        for patient in (2, 3, 5):
            if con.execute(
                "SELECT 1 FROM reports WHERE patient_id=?", (patient,)
            ).fetchone():
                continue  # Never overwrite or mix sample history into existing user records.
            for i in range(7):
                stamp = (datetime.now(timezone.utc) - timedelta(days=6 - i)).isoformat(
                    timespec="milliseconds"
                )
                concern = patient == 2
                mood = [6, 5, 6, 4, 5, 4, 3][i] if concern else [5, 6, 6, 7, 6, 7, 8][i]
                anxiety = (
                    [4, 5, 4, 6, 5, 7, 8][i] if concern else [6, 5, 5, 4, 4, 3, 2][i]
                )
                safety = concern and i == 6
                report = dict(
                    mood=mood,
                    anxiety=anxiety,
                    adherence="Частично" if concern and i > 4 else "Да",
                    adverse_effects=(
                        "Усталость к вечеру (вымышленный пример)"
                        if concern and i == 6
                        else ""
                    ),
                    safety_signal=safety,
                )
                cur = con.execute(
                    "INSERT INTO reports(patient_id,created_at,mood,anxiety,adherence,adverse_effects,safety_signal,note) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        patient,
                        stamp,
                        mood,
                        anxiety,
                        report["adherence"],
                        report["adverse_effects"],
                        int(safety),
                        "Синтетическая запись для демонстрации",
                    ),
                )
                if i == 6:
                    add_proposals(patient, cur.lastrowid, report)
                    if safety:
                        alert = con.execute(
                            "INSERT INTO alerts(patient_id,report_id,created_at,explanation) VALUES(?,?,?,?)",
                            (
                                patient,
                                cur.lastrowid,
                                stamp,
                                "Отмечены опасения за безопасность · синтетический сценарий S-01",
                            ),
                        ).lastrowid
                        notify(
                            1,
                            patient,
                            "Новый сигнал безопасности",
                            "Александра отметила опасения за безопасность. Откройте карточку.",
                            alert,
                        )
            con.execute(
                "INSERT INTO messages(patient_id,sender_id,body,created_at) VALUES(?,?,?,?)",
                (
                    patient,
                    patient,
                    "Здравствуйте! Это вымышленный диалог. Хочу обсудить записи дневника.",
                    stamp,
                ),
            )
        if not con.execute(
            "SELECT 1 FROM proposals WHERE patient_id=2 AND kind='therapy'"
        ).fetchone():
            con.execute(
                """INSERT INTO proposals(patient_id,kind,tier,title,reason,choice,rule_version,created_at)
                VALUES(2,'therapy','desirable','Рассмотреть ДЕМО-Альфа','Вымышленный сценарий согласования. Это не лекарство и не рекомендация лечения.','demo-alpha',?,?)""",
                (
                    VERSION,
                    datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                ),
            )
