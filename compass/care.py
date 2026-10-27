"""Расписание, опросы, назначения и отметки приёма."""

import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import abort, g, jsonify
from compass.db import db, rows, now, audit, notify
from compass.rules import CATALOG

CLINIC_TZ = ZoneInfo("Europe/Moscow")


def local_today():
    return datetime.now(CLINIC_TZ).date()


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("Укажите дату и время")
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if date.tzinfo is None:
            raise ValueError()
        return date.astimezone(timezone.utc)
    except ValueError:
        raise ValueError("Укажите дату и время с часовым поясом") from None


def calendar_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise ValueError("Укажите дату в формате ГГГГ-ММ-ДД") from None


def questions(value):
    if not isinstance(value, list) or not 1 <= len(value) <= 20:
        raise ValueError("В опросе должно быть от 1 до 20 вопросов")
    result = []
    for i, q in enumerate(value):
        if not isinstance(q, dict) or q.get("type") not in ("scale", "text", "yes_no"):
            raise ValueError(
                "Допустимы вопросы с оценкой 0–10, текстом или ответом да/нет"
            )
        label = q.get("label")
        if not isinstance(label, str) or not label.strip() or len(label) > 200:
            raise ValueError("Текст вопроса: от 1 до 200 символов")
        result.append({"id": str(i + 1), "label": label.strip(), "type": q["type"]})
    return result


def init_care(seed_demo=True):
    db().executescript(
        """
    CREATE TABLE IF NOT EXISTS contacts(user_id INTEGER PRIMARY KEY REFERENCES users(id), phone TEXT NOT NULL DEFAULT '', profession TEXT NOT NULL DEFAULT '', organization TEXT NOT NULL DEFAULT '');
    CREATE TABLE IF NOT EXISTS demographics(patient_id INTEGER PRIMARY KEY REFERENCES users(id), sex TEXT NOT NULL DEFAULT 'Не указан', height REAL, weight REAL, phone TEXT NOT NULL DEFAULT '');
    CREATE TABLE IF NOT EXISTS appointments(id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL REFERENCES users(id), doctor_id INTEGER NOT NULL REFERENCES users(id), starts_at TEXT NOT NULL, ends_at TEXT NOT NULL, kind TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'booked', note TEXT NOT NULL DEFAULT '');
    CREATE INDEX IF NOT EXISTS ix_appointments_doctor ON appointments(doctor_id,starts_at,status);
    CREATE INDEX IF NOT EXISTS ix_appointments_patient ON appointments(patient_id,starts_at);
    CREATE TABLE IF NOT EXISTS encounters(id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL REFERENCES users(id), doctor_id INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL, title TEXT NOT NULL, summary TEXT NOT NULL, plan TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS labs(id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL REFERENCES users(id), title TEXT NOT NULL, created_at TEXT NOT NULL, result TEXT NOT NULL, note TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS survey_templates(id INTEGER PRIMARY KEY AUTOINCREMENT, doctor_id INTEGER REFERENCES users(id), title TEXT NOT NULL, description TEXT NOT NULL, schema_json TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS survey_assignments(id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL REFERENCES users(id), doctor_id INTEGER NOT NULL REFERENCES users(id), template_id INTEGER NOT NULL REFERENCES survey_templates(id), title TEXT NOT NULL, schema_json TEXT NOT NULL, due_at TEXT NOT NULL, repeat_days INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'assigned', created_at TEXT NOT NULL, parent_id INTEGER UNIQUE REFERENCES survey_assignments(id));
    CREATE INDEX IF NOT EXISTS ix_assignments_patient ON survey_assignments(patient_id,status,due_at);
    CREATE TABLE IF NOT EXISTS survey_responses(id INTEGER PRIMARY KEY AUTOINCREMENT, assignment_id INTEGER NOT NULL UNIQUE REFERENCES survey_assignments(id), patient_id INTEGER NOT NULL REFERENCES users(id), answers_json TEXT NOT NULL, submitted_at TEXT NOT NULL, interpretation TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS prescriptions(id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL REFERENCES users(id), doctor_id INTEGER NOT NULL REFERENCES users(id), choice TEXT NOT NULL, title TEXT NOT NULL, times_json TEXT NOT NULL, starts_on TEXT NOT NULL, ends_on TEXT NOT NULL, note TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS medication_marks(id INTEGER PRIMARY KEY AUTOINCREMENT, prescription_id INTEGER NOT NULL REFERENCES prescriptions(id), patient_id INTEGER NOT NULL REFERENCES users(id), day TEXT NOT NULL, scheduled_time TEXT NOT NULL, status TEXT NOT NULL, marked_at TEXT NOT NULL, UNIQUE(prescription_id,day,scheduled_time));
    CREATE TABLE IF NOT EXISTS reminder_events(key TEXT PRIMARY KEY, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS escalations(id INTEGER PRIMARY KEY AUTOINCREMENT, alert_id INTEGER NOT NULL UNIQUE REFERENCES alerts(id), doctor_id INTEGER NOT NULL REFERENCES users(id), patient_id INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'protocol_pending', note TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS assistant_runs(id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL REFERENCES users(id), doctor_id INTEGER NOT NULL REFERENCES users(id), provider TEXT NOT NULL, model TEXT NOT NULL, question TEXT NOT NULL, answer TEXT NOT NULL, created_at TEXT NOT NULL);
    """
    )
    with db() as con:
        for ident, phone, profession in [(1, "", "Психотерапевт"), (4, "", "Психолог")]:
            con.execute(
                "INSERT OR IGNORE INTO contacts VALUES(?,?,?,'Центр заботы · демо')",
                (ident, phone, profession),
            )
        for ident, sex, height, weight, phone in [
            (2, "Женский", 168, 62, "+70000000002"),
            (3, "Мужской", 181, 80, "+70000000003"),
            (5, "Женский", 172, 67, "+70000000005"),
        ]:
            con.execute(
                "INSERT OR IGNORE INTO demographics VALUES(?,?,?,?,?)",
                (ident, sex, height, weight, phone),
            )
        if not con.execute(
            "SELECT 1 FROM demo_state WHERE key='care-v3-templates'"
        ).fetchone():
            con.execute("INSERT INTO demo_state VALUES('care-v3-templates')")
            for title, description, schema in [
                (
                    "Ежедневное самочувствие",
                    "Учебные вопросы, не клиническая шкала.",
                    [
                        {
                            "label": "Как вы оцениваете своё самочувствие?",
                            "type": "scale",
                        },
                        {"label": "Удалось ли отдохнуть?", "type": "yes_no"},
                        {"label": "Что хотелось бы обсудить?", "type": "text"},
                    ],
                ),
                (
                    "Сон и ритм дня",
                    "Синтетический шаблон для обсуждения со специалистом.",
                    [
                        {"label": "Насколько вы довольны своим сном?", "type": "scale"},
                        {"label": "Что мешало отдыху?", "type": "text"},
                    ],
                ),
                (
                    "Соблюдение плана",
                    "Обсуждение трудностей, без медицинской интерпретации.",
                    [
                        {
                            "label": "Получалось следовать согласованному плану?",
                            "type": "yes_no",
                        },
                        {"label": "Какие трудности возникли?", "type": "text"},
                    ],
                ),
            ]:
                con.execute(
                    "INSERT INTO survey_templates(doctor_id,title,description,schema_json,created_at) VALUES(NULL,?,?,?,?)",
                    (
                        title,
                        description,
                        json.dumps(questions(schema), ensure_ascii=False),
                        now(),
                    ),
                )
        if con.execute(
            "SELECT 1 FROM demo_state WHERE key='care-v3-showcase'"
        ).fetchone():
            return
        con.execute("INSERT INTO demo_state VALUES('care-v3-showcase')")
        if not seed_demo:
            return
        for patient, doctor in [(2, 1), (3, 1), (5, 4)]:
            tomorrow = datetime.combine(
                local_today() + timedelta(days=1), datetime.min.time(), CLINIC_TZ
            ).replace(hour=11 if patient != 3 else 14)
            start = tomorrow.astimezone(timezone.utc)
            con.execute(
                "INSERT INTO appointments(patient_id,doctor_id,starts_at,ends_at,kind) VALUES(?,?,?,?,?)",
                (
                    patient,
                    doctor,
                    start.isoformat(timespec="milliseconds"),
                    (start + timedelta(minutes=50)).isoformat(timespec="milliseconds"),
                    "Онлайн-консультация",
                ),
            )
            con.execute(
                "INSERT INTO encounters(patient_id,doctor_id,created_at,title,summary,plan) VALUES(?,?,?,?,?,?)",
                (
                    patient,
                    doctor,
                    (start - timedelta(days=7)).isoformat(timespec="milliseconds"),
                    "Первичная консультация · синтетический пример",
                    "Обсудили самочувствие, ожидания и удобный формат наблюдения. Все сведения вымышлены.",
                    "Вести дневник и обсудить изменения на следующей встрече.",
                ),
            )
            con.execute(
                "INSERT INTO labs(patient_id,title,created_at,result,note) VALUES(?,?,?,?,?)",
                (
                    patient,
                    "Учебный лабораторный отчёт",
                    now(),
                    "ДЕМО-маркер A: 12 усл. ед.\nДЕМО-маркер B: 7 усл. ед.",
                    "Показатели и единицы вымышлены. Не являются результатами реальных анализов.",
                ),
            )
            template = con.execute(
                "SELECT * FROM survey_templates ORDER BY id LIMIT 1"
            ).fetchone()
            con.execute(
                "INSERT INTO survey_assignments(patient_id,doctor_id,template_id,title,schema_json,due_at,repeat_days,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (
                    patient,
                    doctor,
                    template["id"],
                    template["title"],
                    template["schema_json"],
                    (datetime.now(timezone.utc) + timedelta(hours=20)).isoformat(
                        timespec="milliseconds"
                    ),
                    1,
                    now(),
                ),
            )
            con.execute(
                "INSERT INTO prescriptions(patient_id,doctor_id,choice,title,times_json,starts_on,ends_on,note,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    patient,
                    doctor,
                    "demo-alpha",
                    "ДЕМО-Альфа · учебная отметка",
                    json.dumps(["09:00", "20:00"]),
                    local_today().isoformat(),
                    (local_today() + timedelta(days=13)).isoformat(),
                    "Вымышленное назначение для показа таблетницы. Не лекарство, без дозировки.",
                    now(),
                ),
            )


def care_bundle(patient_id):
    assignments = rows(
        """SELECT a.*,r.answers_json,r.submitted_at,r.interpretation FROM survey_assignments a
        LEFT JOIN survey_responses r ON r.assignment_id=a.id WHERE a.patient_id=? ORDER BY a.due_at DESC LIMIT 100""",
        (patient_id,),
    )
    for item in assignments:
        item["questions"] = json.loads(item.pop("schema_json"))
        item["answers"] = json.loads(item.pop("answers_json") or "{}")
        item["overdue"] = item["status"] == "assigned" and timestamp(
            item["due_at"]
        ) < datetime.now(timezone.utc)
    prescriptions = rows(
        "SELECT * FROM prescriptions WHERE patient_id=? ORDER BY id DESC LIMIT 100",
        (patient_id,),
    )
    for item in prescriptions:
        item["times"] = json.loads(item.pop("times_json"))
    return dict(
        appointments=rows(
            "SELECT * FROM appointments WHERE patient_id=? ORDER BY starts_at DESC LIMIT 100",
            (patient_id,),
        ),
        encounters=rows(
            "SELECT e.*,u.name AS doctor_name FROM encounters e JOIN users u ON u.id=e.doctor_id WHERE patient_id=? ORDER BY e.id DESC LIMIT 100",
            (patient_id,),
        ),
        labs=rows(
            "SELECT * FROM labs WHERE patient_id=? ORDER BY id DESC LIMIT 100",
            (patient_id,),
        ),
        surveys=assignments,
        prescriptions=prescriptions,
        medication_marks=rows(
            "SELECT * FROM medication_marks WHERE patient_id=? AND day>=? ORDER BY day DESC LIMIT 500",
            (patient_id, (local_today() - timedelta(days=30)).isoformat()),
        ),
        today=local_today().isoformat(),
        timezone=str(CLINIC_TZ),
    )


def validated_phone(value, user_id):
    if not value:
        return ""
    from compass.onboarding import phone_number

    phone = phone_number(value)
    if (
        db()
        .execute(
            "SELECT 1 FROM demographics WHERE phone=? AND patient_id!=?",
            (phone, user_id),
        )
        .fetchone()
        or db()
        .execute(
            "SELECT 1 FROM contacts WHERE phone=? AND user_id!=?", (phone, user_id)
        )
        .fetchone()
        or db()
        .execute(
            "SELECT 1 FROM credentials WHERE username=? AND user_id!=?",
            (phone, user_id),
        )
        .fetchone()
    ):
        abort(409, "Телефон уже связан с другим аккаунтом")
    return phone


def register_care(app, patient, require_role, payload, text, write_once):
    @app.get("/api/appointments")
    def appointments():
        field = "doctor_id" if g.user["role"] == "doctor" else "patient_id"
        return jsonify(
            rows(
                f"""SELECT a.*,p.name AS patient_name,d.name AS doctor_name FROM appointments a
            JOIN users p ON p.id=a.patient_id JOIN users d ON d.id=a.doctor_id
            WHERE a.{field}=? ORDER BY a.starts_at LIMIT 200""",
                (g.user["id"],),
            )
        )

    @app.get("/api/appointments/slots")
    def available_slots():
        doctor = g.user["id"] if g.user["role"] == "doctor" else g.user["doctor_id"]
        slots = []
        booked = rows(
            "SELECT starts_at,ends_at FROM appointments WHERE doctor_id=? AND status='booked'",
            (doctor,),
        )
        for day in range(14):
            for hour in (9, 11, 14, 16):
                local = datetime.combine(
                    local_today() + timedelta(days=day), datetime.min.time(), CLINIC_TZ
                ).replace(hour=hour)
                start = local.astimezone(timezone.utc)
                end = start + timedelta(minutes=50)
                if start < datetime.now(timezone.utc) + timedelta(minutes=30):
                    continue
                if any(
                    timestamp(r["starts_at"]) < end and timestamp(r["ends_at"]) > start
                    for r in booked
                ):
                    continue
                slots.append(start.isoformat(timespec="milliseconds"))
        return jsonify(slots=slots, timezone=str(CLINIC_TZ))

    @app.post("/api/appointments")
    def book_appointment():
        data = payload()
        ident = data.get("patient_id") if g.user["role"] == "doctor" else g.user["id"]
        if type(ident) is not int:
            raise ValueError("Укажите пациента")
        account = patient(ident)
        start = timestamp(data.get("starts_at"))
        end = start + timedelta(minutes=50)
        kind = data.get("kind", "Онлайн-консультация")
        if kind not in ("Онлайн-консультация", "Очная консультация"):
            raise ValueError("Выберите формат консультации")
        local = start.astimezone(CLINIC_TZ)
        if (
            not datetime.now(timezone.utc) + timedelta(minutes=30)
            <= start
            <= datetime.now(timezone.utc) + timedelta(days=14)
            or local.hour not in (9, 11, 14, 16)
            or local.minute
            or local.second
            or local.microsecond
        ):
            raise ValueError(
                "Выберите свободное время из расписания на ближайшие 14 дней"
            )

        def action():
            if (
                db()
                .execute(
                    "SELECT 1 FROM appointments WHERE doctor_id=? AND status='booked' AND starts_at<? AND ends_at>?",
                    (
                        account["doctor_id"],
                        end.isoformat(timespec="milliseconds"),
                        start.isoformat(timespec="milliseconds"),
                    ),
                )
                .fetchone()
            ):
                abort(409, "Это время уже занято. Обновите расписание")
            cur = db().execute(
                "INSERT INTO appointments(patient_id,doctor_id,starts_at,ends_at,kind) VALUES(?,?,?,?,?)",
                (
                    ident,
                    account["doctor_id"],
                    start.isoformat(timespec="milliseconds"),
                    end.isoformat(timespec="milliseconds"),
                    kind,
                ),
            )
            notify(
                ident if g.user["role"] == "doctor" else account["doctor_id"],
                ident,
                "Новая запись",
                "Консультация добавлена в расписание.",
            )
            audit(
                g.user["id"],
                ident,
                "appointment.booked",
                "Запись #" + str(cur.lastrowid),
            )
            return {"id": cur.lastrowid}, 201

        return write_once(data, action)

    @app.post("/api/appointments/<int:ident>/status")
    def appointment_status(ident):
        data = payload()
        status = data.get("status")
        if status not in ("cancelled", "completed"):
            raise ValueError("Неизвестный статус записи")
        if status == "completed":
            require_role("doctor")

        def action():
            record = (
                db()
                .execute("SELECT * FROM appointments WHERE id=?", (ident,))
                .fetchone()
            )
            if not record:
                abort(404, "Запись не найдена")
            account = patient(record["patient_id"])
            if record["status"] != "booked":
                abort(409, "Статус записи уже изменён")
            if status == "completed" and timestamp(record["starts_at"]) > datetime.now(
                timezone.utc
            ):
                abort(409, "Будущую консультацию нельзя завершить")
            if status == "cancelled" and timestamp(record["starts_at"]) < datetime.now(
                timezone.utc
            ):
                abort(409, "Прошедшую консультацию нельзя отменить")
            db().execute("UPDATE appointments SET status=? WHERE id=?", (status, ident))
            audit(
                g.user["id"],
                record["patient_id"],
                "appointment." + status,
                "Запись #" + str(ident),
            )
            notify(
                (
                    account["doctor_id"]
                    if g.user["role"] == "patient"
                    else record["patient_id"]
                ),
                record["patient_id"],
                "Статус консультации изменён",
                "Откройте расписание.",
            )
            return {"status": status}, 200

        return write_once(data, action)

    @app.post("/api/patients/<int:ident>/profile")
    def update_profile(ident):
        patient(ident)
        require_role("doctor")
        data = payload()
        sex = data.get("sex", "Не указан")
        if sex not in ("Женский", "Мужской", "Не указан"):
            raise ValueError("Выберите пол")
        numbers = {}
        for key, low, high in [("height", 30, 250), ("weight", 1, 350)]:
            value = data.get(key)
            if value is not None and (
                type(value) not in (int, float) or not low <= value <= high
            ):
                raise ValueError("Проверьте рост и вес")
            numbers[key] = value

        def save():
            db().execute(
                "INSERT INTO demographics(patient_id,sex,height,weight,phone) VALUES(?,?,?,?,?) ON CONFLICT(patient_id) DO UPDATE SET sex=excluded.sex,height=excluded.height,weight=excluded.weight,phone=excluded.phone",
                (
                    ident,
                    sex,
                    numbers["height"],
                    numbers["weight"],
                    validated_phone(text(data, "phone", 30), ident),
                ),
            )
            audit(g.user["id"], ident, "profile.updated", "Основные данные обновлены")
            return {"ok": True}, 200

        return write_once(data, save)

    @app.post("/api/contact")
    def update_contact():
        require_role("doctor")
        data = payload()
        with db() as con:
            con.execute("BEGIN IMMEDIATE")
            con.execute(
                "INSERT INTO contacts(user_id,phone,profession,organization) VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET phone=excluded.phone,profession=excluded.profession,organization=excluded.organization",
                (
                    g.user["id"],
                    validated_phone(text(data, "phone", 30), g.user["id"]),
                    text(data, "profession", 100),
                    text(data, "organization", 100),
                ),
            )
        return jsonify(ok=True)

    @app.post("/api/patients/<int:ident>/encounters")
    def save_encounter(ident):
        patient(ident)
        require_role("doctor")
        data = payload()
        title, summary, plan = (
            text(data, "title", 160, True),
            text(data, "summary", 3000, True),
            text(data, "plan", 1000, True),
        )

        def save():
            cur = db().execute(
                "INSERT INTO encounters(patient_id,doctor_id,created_at,title,summary,plan) VALUES(?,?,?,?,?,?)",
                (ident, g.user["id"], now(), title, summary, plan),
            )
            audit(g.user["id"], ident, "encounter.created", title)
            notify(
                ident,
                ident,
                "Отчёт о посещении",
                "Специалист добавил отчёт о консультации.",
            )
            return {"id": cur.lastrowid}, 201

        return write_once(data, save)

    @app.post("/api/patients/<int:ident>/labs")
    def save_lab(ident):
        patient(ident)
        require_role("doctor")
        data = payload()
        title, result, note = (
            text(data, "title", 160, True),
            text(data, "result", 3000, True),
            text(data, "note", 500),
        )

        def save():
            cur = db().execute(
                "INSERT INTO labs(patient_id,title,created_at,result,note) VALUES(?,?,?,?,?)",
                (ident, title, now(), result, note),
            )
            audit(g.user["id"], ident, "lab.created", title)
            notify(
                ident,
                ident,
                "Новый результат",
                "В карточку добавлен синтетический результат анализа.",
            )
            return {"id": cur.lastrowid}, 201

        return write_once(data, save)

    @app.get("/api/labs/<int:ident>/download")
    def download_lab(ident):
        item = rows("SELECT * FROM labs WHERE id=?", (ident,))
        if not item:
            abort(404, "Результат не найден")
        item = item[0]
        patient(item["patient_id"])
        body = f"СИНТЕТИЧЕСКИЙ ДОКУМЕНТ · НЕ ДЛЯ МЕДИЦИНСКИХ РЕШЕНИЙ\n{item['title']}\n{item['created_at']}\n\n{item['result']}\n\n{item['note']}"
        return app.response_class(
            body,
            content_type="text/plain; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="demo-lab-{ident}.txt"'
            },
        )

    @app.get("/api/surveys/templates")
    def templates():
        require_role("doctor")
        result = rows(
            "SELECT * FROM survey_templates WHERE doctor_id IS NULL OR doctor_id=? ORDER BY id",
            (g.user["id"],),
        )
        for item in result:
            item["questions"] = json.loads(item.pop("schema_json"))
        return jsonify(result)

    @app.post("/api/surveys/templates")
    def create_template():
        require_role("doctor")
        data = payload()
        schema = questions(data.get("questions"))
        title = text(data, "title", 160, True)
        description = text(data, "description", 500)

        def save():
            cur = db().execute(
                "INSERT INTO survey_templates(doctor_id,title,description,schema_json,created_at) VALUES(?,?,?,?,?)",
                (
                    g.user["id"],
                    title,
                    description,
                    json.dumps(schema, ensure_ascii=False),
                    now(),
                ),
            )
            return {"id": cur.lastrowid}, 201

        return write_once(data, save)

    @app.post("/api/patients/<int:ident>/surveys")
    def assign_survey(ident):
        patient(ident)
        require_role("doctor")
        data = payload()
        template = data.get("template_id")
        deadline = timestamp(data.get("due_at"))
        repeat = data.get("repeat_days", 0)
        if deadline <= datetime.now(timezone.utc) or deadline > datetime.now(
            timezone.utc
        ) + timedelta(days=365):
            raise ValueError("Дедлайн должен быть в пределах следующего года")
        if type(repeat) is not int or repeat not in (0, 1, 7, 14, 30):
            raise ValueError("Выберите периодичность")

        def save():
            source = (
                db()
                .execute(
                    "SELECT * FROM survey_templates WHERE id=? AND (doctor_id IS NULL OR doctor_id=?)",
                    (template, g.user["id"]),
                )
                .fetchone()
            )
            if not source:
                abort(404, "Шаблон не найден")
            cur = db().execute(
                "INSERT INTO survey_assignments(patient_id,doctor_id,template_id,title,schema_json,due_at,repeat_days,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (
                    ident,
                    g.user["id"],
                    source["id"],
                    source["title"],
                    source["schema_json"],
                    deadline.isoformat(timespec="milliseconds"),
                    repeat,
                    now(),
                ),
            )
            notify(ident, ident, "Назначен опрос", source["title"])
            audit(g.user["id"], ident, "survey.assigned", source["title"])
            return {"id": cur.lastrowid}, 201

        return write_once(data, save)

    @app.post("/api/surveys/<int:ident>/cancel")
    def cancel_survey(ident):
        require_role("doctor")
        data = payload()

        def save():
            item = (
                db()
                .execute("SELECT * FROM survey_assignments WHERE id=?", (ident,))
                .fetchone()
            )
            if not item:
                abort(404, "Опрос не найден")
            patient(item["patient_id"])
            if item["status"] != "assigned":
                abort(409, "Опрос уже завершён или отменён")
            db().execute(
                "UPDATE survey_assignments SET status='cancelled' WHERE id=?", (ident,)
            )
            audit(g.user["id"], item["patient_id"], "survey.cancelled", item["title"])
            notify(
                item["patient_id"],
                item["patient_id"],
                "Опрос отменён",
                "Специалист отменил задание. Заполнять его не требуется.",
            )
            return {"status": "cancelled"}, 200

        return write_once(data, save)

    @app.post("/api/surveys/<int:ident>/submit")
    def submit_survey(ident):
        require_role("patient")
        data = payload()
        answers = data.get("answers")
        if not isinstance(answers, dict):
            raise ValueError("Заполните ответы")

        def save():
            item = (
                db()
                .execute("SELECT * FROM survey_assignments WHERE id=?", (ident,))
                .fetchone()
            )
            if not item:
                abort(404, "Опрос не найден")
            account = patient(item["patient_id"])
            if item["status"] != "assigned":
                abort(409, "Опрос уже заполнен")
            schema = json.loads(item["schema_json"])
            if set(answers) != {q["id"] for q in schema}:
                raise ValueError("Ответьте на все вопросы")
            for q in schema:
                value = answers[q["id"]]
                if q["type"] == "scale" and (
                    type(value) is not int or not 0 <= value <= 10
                ):
                    raise ValueError("Оценки должны быть от 0 до 10")
                if q["type"] == "yes_no" and type(value) is not bool:
                    raise ValueError("Выберите да или нет")
                if q["type"] == "text" and (
                    not isinstance(value, str) or len(value) > 1000
                ):
                    raise ValueError("Текст ответа: до 1000 символов")
            explanation = "Ответы сохранены и доступны вашему специалисту. Учебный опрос не ставит диагноз. Обсудите отмеченные изменения на встрече."
            stamp = now()
            db().execute(
                "INSERT INTO survey_responses(assignment_id,patient_id,answers_json,submitted_at,interpretation) VALUES(?,?,?,?,?)",
                (
                    ident,
                    account["id"],
                    json.dumps(answers, ensure_ascii=False),
                    stamp,
                    explanation,
                ),
            )
            db().execute(
                "UPDATE survey_assignments SET status='completed' WHERE id=?", (ident,)
            )
            if item["repeat_days"]:
                deadline = max(
                    timestamp(item["due_at"]), datetime.now(timezone.utc)
                ) + timedelta(days=item["repeat_days"])
                db().execute(
                    "INSERT INTO survey_assignments(patient_id,doctor_id,template_id,title,schema_json,due_at,repeat_days,created_at,parent_id) VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        account["id"],
                        item["doctor_id"],
                        item["template_id"],
                        item["title"],
                        item["schema_json"],
                        deadline.isoformat(timespec="milliseconds"),
                        item["repeat_days"],
                        stamp,
                        ident,
                    ),
                )
            notify(account["doctor_id"], account["id"], "Опрос заполнен", item["title"])
            audit(g.user["id"], account["id"], "survey.completed", item["title"])
            return {"interpretation": explanation}, 201

        return write_once(data, save)

    @app.post("/api/patients/<int:ident>/prescriptions")
    def prescribe(ident):
        patient(ident)
        require_role("doctor")
        data = payload()
        choice = data.get("choice")
        times = data.get("times")
        option = next((c for c in CATALOG if c["id"] == choice), None)
        if not option:
            raise ValueError("Выберите вымышленный ДЕМО-вариант")
        if (
            not isinstance(times, list)
            or not 1 <= len(times) <= 6
            or any(not isinstance(t, str) or len(t) != 5 for t in times)
        ):
            raise ValueError("Укажите от 1 до 6 времён приёма")
        try:
            for t in times:
                datetime.strptime(t, "%H:%M")
        except ValueError:
            raise ValueError("Время должно быть в формате ЧЧ:ММ") from None
        if len(set(times)) != len(times):
            raise ValueError("Время приёма не должно повторяться")
        start, end = calendar_date(data.get("starts_on")), calendar_date(
            data.get("ends_on")
        )
        note = text(data, "note", 500, True)
        if not local_today() <= start <= end <= local_today() + timedelta(days=90):
            raise ValueError("Учебное назначение: от сегодня, не более 90 дней")

        def save():
            profile = (
                db()
                .execute(
                    "SELECT intolerance FROM profiles WHERE patient_id=?", (ident,)
                )
                .fetchone()
            )
            if profile and profile["intolerance"] == choice:
                abort(409, "Учебная несовместимость в профиле")
            cur = db().execute(
                "INSERT INTO prescriptions(patient_id,doctor_id,choice,title,times_json,starts_on,ends_on,note,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    ident,
                    g.user["id"],
                    choice,
                    option["name"] + " · учебная отметка",
                    json.dumps(sorted(times)),
                    start.isoformat(),
                    end.isoformat(),
                    note,
                    now(),
                ),
            )
            audit(g.user["id"], ident, "prescription.confirmed", option["name"])
            notify(
                ident,
                ident,
                "Обновлена таблетница",
                "Специалист подтвердил вымышленное назначение.",
            )
            return {"id": cur.lastrowid}, 201

        return write_once(data, save)

    @app.post("/api/prescriptions/<int:ident>/stop")
    def stop_prescription(ident):
        require_role("doctor")
        data = payload()
        note = text(data, "note", 500, True)

        def save():
            item = (
                db()
                .execute("SELECT * FROM prescriptions WHERE id=?", (ident,))
                .fetchone()
            )
            if not item:
                abort(404, "Назначение не найдено")
            patient(item["patient_id"])
            if not item["active"]:
                abort(409, "Назначение уже отменено")
            db().execute("UPDATE prescriptions SET active=0 WHERE id=?", (ident,))
            audit(g.user["id"], item["patient_id"], "prescription.stopped", note)
            notify(
                item["patient_id"],
                item["patient_id"],
                "Изменение таблетницы",
                "Специалист отменил учебное назначение.",
            )
            return {"ok": True}, 200

        return write_once(data, save)

    @app.post("/api/prescriptions/<int:ident>/mark")
    def medication_mark(ident):
        require_role("patient")
        data = payload()
        day = calendar_date(data.get("day"))
        scheduled = data.get("time")
        status = data.get("status")
        if status not in ("taken", "skipped"):
            raise ValueError("Выберите принято или пропущено")

        def save():
            item = (
                db()
                .execute("SELECT * FROM prescriptions WHERE id=?", (ident,))
                .fetchone()
            )
            if not item:
                abort(404, "Назначение не найдено")
            patient(item["patient_id"])
            if (
                not item["active"]
                or not item["starts_on"] <= day.isoformat() <= item["ends_on"]
                or scheduled not in json.loads(item["times_json"])
            ):
                abort(409, "Эта отметка не предусмотрена назначением")
            due = datetime.combine(
                day, datetime.strptime(scheduled, "%H:%M").time(), CLINIC_TZ
            )
            if due > datetime.now(CLINIC_TZ) or day < local_today() - timedelta(
                days=30
            ):
                raise ValueError(
                    "Нельзя отмечать будущие приёмы или записи старше 30 дней"
                )
            db().execute(
                "INSERT INTO medication_marks(prescription_id,patient_id,day,scheduled_time,status,marked_at) VALUES(?,?,?,?,?,?) ON CONFLICT(prescription_id,day,scheduled_time) DO UPDATE SET status=excluded.status,marked_at=excluded.marked_at",
                (ident, item["patient_id"], day.isoformat(), scheduled, status, now()),
            )
            audit(
                g.user["id"],
                item["patient_id"],
                "medication." + status,
                "Учебная отметка #" + str(ident),
            )
            return {"status": status}, 200

        return write_once(data, save)
