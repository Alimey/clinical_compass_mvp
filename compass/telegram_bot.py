"""Первичная анкета пациента через Telegram long polling."""

import json
import os
import time
from urllib.request import Request, urlopen
from flask import current_app
from compass.db import db, now
from compass.onboarding import digest, invite_record, provision
from compass.assistants import ai_settings, complete, SYSTEM, AssistantUnavailable
from compass.name_crypto import seal, unseal

STEPS = [
    ("name", "Как вас зовут? Используйте вымышленное имя."),
    ("sex", "Пол: Женский, Мужской или Не указан."),
    ("age", "Ваш возраст? Демо рассчитано на взрослых 18–100 лет."),
    ("height", "Рост в сантиметрах (100–250)?"),
    ("weight", "Вес в килограммах (30–350)?"),
    ("phone", "Синтетический телефон: + и от 10 до 15 цифр. Например +70000000999."),
    (
        "context",
        "Что хотите обсудить со специалистом? Только вымышленные сведения, до 1000 символов.",
    ),
]


def telegram_api(method, data):
    token = os.environ.get("COMPASS_TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("Telegram token missing")
    request = Request(
        "https://api.telegram.org/bot" + token + "/" + method,
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=40) as response:
        result = json.load(response)
    if not result.get("ok"):
        raise RuntimeError("Telegram API rejected request")
    return result["result"]


def enqueue(chat, body):
    db().execute(
        "INSERT INTO telegram_outbox(chat_id,body) VALUES(?,?)",
        (chat, seal(body[:4000], "outbox")),
    )


def handle_update(update):
    """Transactional update deduplication. No outbound network in this transaction."""
    message = update.get("message", {})
    chat = message.get("chat", {})
    chat_id = chat.get("id")
    value = message.get("text", "").strip()
    update_id = update.get("update_id")
    if (
        type(update_id) is not int
        or type(chat_id) is not int
        or chat.get("type") != "private"
    ):
        return
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        if con.execute(
            "SELECT 1 FROM telegram_updates WHERE update_id=?", (update_id,)
        ).fetchone():
            return
        con.execute("INSERT INTO telegram_updates VALUES(?,?)", (update_id, now()))
        if value.startswith("/start "):
            token = value.split(" ", 1)[1][:100]
            try:
                item = invite_record(token, chat_id)
            except Exception:
                enqueue(
                    chat_id,
                    "Приглашение недоступно. Попросите специалиста создать новую ссылку.",
                )
                return
            con.execute(
                "UPDATE invites SET telegram_chat=? WHERE token_hash=?",
                (chat_id, item["token_hash"]),
            )
            con.execute(
                "INSERT OR REPLACE INTO telegram_sessions VALUES(?,?,?,?)",
                (
                    chat_id,
                    item["token_hash"],
                    "name",
                    seal(json.dumps({"_token": token}), "intake"),
                ),
            )
            enqueue(
                chat_id,
                "Клинический компас · синтетическое демо. Анкета создаст карточку у пригласившего специалиста. Не используйте реальные данные.\n"
                + STEPS[0][1],
            )
            return
        session = con.execute(
            "SELECT * FROM telegram_sessions WHERE chat_id=?", (chat_id,)
        ).fetchone()
        if not session:
            enqueue(
                chat_id,
                "Откройте персональную ссылку от специалиста, чтобы начать анкету.",
            )
            return
        data = json.loads(unseal(session["data_json"], "intake"))
        stage = session["stage"]
        if stage == "done":
            enqueue(
                chat_id,
                "Карточка уже создана. Для нового приглашения обратитесь к специалисту.",
            )
            return
        if stage == "confirm":
            if value.casefold() != "подтверждаю":
                enqueue(
                    chat_id,
                    "Чтобы создать карточку, напишите «Подтверждаю». Для новой анкеты нужен новый /start по ссылке специалиста.",
                )
                return
            # A savepoint rolls back partial account creation on bad data.
            con.execute("SAVEPOINT intake")
            try:
                user, activation = provision(data["_token"], data, chat_id=chat_id)
                con.execute("RELEASE intake")
            except Exception:
                con.execute("ROLLBACK TO intake")
                con.execute("RELEASE intake")
                enqueue(
                    chat_id,
                    "Не удалось создать карточку. Проверьте анкету или начните заново по ссылке. Возможна повторная регистрация телефона.",
                )
                return
            public = os.environ.get("COMPASS_PUBLIC_URL", "").rstrip("/")
            enqueue(
                chat_id,
                "Карточка создана. Задайте пароль по одноразовой ссылке (24 часа): "
                + public
                + "/#activate="
                + activation
                + "\nЛогин: "
                + data["phone"],
            )
            con.execute(
                "UPDATE telegram_sessions SET stage='done',data_json=? WHERE chat_id=?",
                (seal("{}", "intake"), chat_id),
            )
            return
        index = next((i for i, s in enumerate(STEPS) if s[0] == stage), None)
        if index is None:
            return
        try:
            if stage == "age":
                parsed = int(value)
                if not 18 <= parsed <= 100:
                    raise ValueError()
            elif stage in ("height", "weight"):
                parsed = float(value.replace(",", "."))
                lo, hi = (100, 250) if stage == "height" else (30, 350)
                if not lo <= parsed <= hi:
                    raise ValueError()
            elif stage == "phone":
                from compass.onboarding import phone_number

                parsed = phone_number(value)
            elif stage == "sex":
                parsed = next(
                    v
                    for v in ("Женский", "Мужской", "Не указан")
                    if v.casefold() == value.casefold()
                )
            else:
                if not value or len(value) > (100 if stage == "name" else 1000):
                    raise ValueError()
                parsed = value
        except (ValueError, StopIteration):
            enqueue(chat_id, "Проверьте ответ. " + STEPS[index][1])
            return
        data[stage] = parsed
        if index + 1 < len(STEPS):
            next_stage, prompt = STEPS[index + 1]
        else:
            next_stage = "confirm"
            prompt = (
                "Проверьте анкету:\n"
                + "\n".join(f"{key}: {data[key]}" for key, _ in STEPS)
                + "\n\nНапишите «Подтверждаю», чтобы создать карточку. Диагноз и лечение автоматически не определяются."
            )
        con.execute(
            "UPDATE telegram_sessions SET stage=?,data_json=? WHERE chat_id=?",
            (next_stage, seal(json.dumps(data, ensure_ascii=False), "intake"), chat_id),
        )
        enqueue(chat_id, prompt)


def enrich_intake(chat_id):
    if not all(ai_settings()):
        return
    session = (
        db()
        .execute(
            "SELECT * FROM telegram_sessions WHERE chat_id=? AND stage='confirm'",
            (chat_id,),
        )
        .fetchone()
    )
    if not session:
        return
    data = json.loads(unseal(session["data_json"], "intake"))
    if data.get("_ai_done"):
        return
    facts = {key: data[key] for key in ("age", "sex", "context") if key in data}
    try:
        answer = complete(
            SYSTEM
            + " Составь нейтральную сводку первичной анкеты и 2 уточняющих вопроса. Не добавляй фактов, не устанавливай диагноз и не назначай лечение.",
            json.dumps(facts, ensure_ascii=False),
        )
    except AssistantUnavailable:
        return
    with db() as con:
        current = con.execute(
            "SELECT * FROM telegram_sessions WHERE chat_id=? AND stage='confirm'",
            (chat_id,),
        ).fetchone()
        if not current or current["invite_hash"] != session["invite_hash"]:
            return
        latest = json.loads(unseal(current["data_json"], "intake"))
        latest["_ai_done"] = True
        latest["_ai_summary"] = answer
        latest["_ai_model"] = ai_settings()[1]
        con.execute(
            "UPDATE telegram_sessions SET data_json=? WHERE chat_id=?",
            (seal(json.dumps(latest, ensure_ascii=False), "intake"), chat_id),
        )
        enqueue(
            chat_id,
            "ИИ-черновик для проверки, а не диагноз:\n"
            + answer[:2800]
            + "\n\nИсходные ответы не изменены. Для создания карточки напишите «Подтверждаю».",
        )


def tick_telegram():
    if not os.environ.get("COMPASS_TELEGRAM_BOT_TOKEN") or not os.environ.get(
        "COMPASS_PUBLIC_URL"
    ):
        return
    offset = (
        db()
        .execute("SELECT value FROM service_state WHERE key='telegram_offset'")
        .fetchone()
    )
    updates = telegram_api(
        "getUpdates",
        {
            "offset": int(offset["value"]) if offset else 0,
            "timeout": 0,
            "allowed_updates": ["message"],
        },
    )
    for update in updates:
        handle_update(update)
        enrich_intake(update.get("message", {}).get("chat", {}).get("id"))
        with db() as con:
            con.execute(
                "INSERT OR REPLACE INTO service_state VALUES('telegram_offset',?)",
                (str(update["update_id"] + 1),),
            )
    for record in (
        db()
        .execute(
            "SELECT * FROM telegram_outbox WHERE sent_at IS NULL AND next_attempt<=? AND attempts<6 ORDER BY id LIMIT 20",
            (time.time(),),
        )
        .fetchall()
    ):
        try:
            telegram_api(
                "sendMessage",
                {
                    "chat_id": record["chat_id"],
                    "text": unseal(record["body"], "outbox"),
                    "protect_content": True,
                },
            )
            with db() as con:
                con.execute(
                    "UPDATE telegram_outbox SET sent_at=? WHERE id=?",
                    (now(), record["id"]),
                )
        except Exception:
            with db() as con:
                con.execute(
                    "UPDATE telegram_outbox SET attempts=attempts+1,next_attempt=? WHERE id=?",
                    (
                        time.time() + min(300, 2 ** (record["attempts"] + 1) * 5),
                        record["id"],
                    ),
                )
    with db() as con:
        con.execute(
            "INSERT OR REPLACE INTO service_state VALUES('telegram_heartbeat',?)",
            (now(),),
        )
