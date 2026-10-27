"""Patient graph observations from a real external model and a dated data snapshot."""

import hashlib
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from flask import jsonify
from compass.assistants import AssistantUnavailable, ai_settings, complete
from compass.care import care_bundle
from compass.db import db, now, rows


def init_insights():
    db().execute(
        "CREATE TABLE IF NOT EXISTS graph_insights(patient_id INTEGER PRIMARY KEY REFERENCES users(id),fingerprint TEXT NOT NULL,body_json TEXT NOT NULL,created_at TEXT NOT NULL)"
    )
    db().commit()


def graph_facts(ident):
    today = datetime.now(ZoneInfo("Europe/Moscow")).date()
    start = today - timedelta(days=27)
    records = rows(
        "SELECT created_at,anxiety,sleep,energy,adverse_effects,safety_signal FROM reports WHERE patient_id=? ORDER BY id DESC LIMIT 100",
        (ident,),
    )
    records = [
        {
            **r,
            "day": datetime.fromisoformat(r["created_at"])
            .astimezone(ZoneInfo("Europe/Moscow"))
            .date()
            .isoformat(),
        }
        for r in records
    ]
    records = [r for r in records if str(start) <= r["day"] <= str(today)]

    def week(first, last):
        selected = [r for r in records if str(first) <= r["day"] <= str(last)]
        return {
            "from": str(first),
            "to": str(last),
            "records": len(selected),
            "mean": {
                key: (
                    round(
                        sum(r[key] for r in selected if r[key] is not None)
                        / sum(r[key] is not None for r in selected),
                        1,
                    )
                    if any(r[key] is not None for r in selected)
                    else None
                )
                for key in ("anxiety", "sleep", "energy")
            },
        }

    c = care_bundle(ident)
    marks = [m for m in c["medication_marks"] if str(start) <= m["day"] <= str(today)]
    return {
        "period": {"from": str(start), "to": str(today)},
        "report_count": len(records),
        "last_week": week(today - timedelta(days=6), today),
        "previous_week": week(today - timedelta(days=13), today - timedelta(days=7)),
        "complaint_days": sorted({r["day"] for r in records if r["adverse_effects"]}),
        "urgent_days": sorted({r["day"] for r in records if r["safety_signal"]}),
        "medication_marks": {
            "taken": sum(m["status"] == "taken" for m in marks),
            "skipped": sum(m["status"] == "skipped" for m in marks),
        },
        "scales": rows(
            "SELECT kind,score,created_at FROM assessments WHERE patient_id=? ORDER BY id DESC LIMIT 30",
            (ident,),
        ),
    }


def register_insights(app, patient, require_role, payload):
    @app.post("/api/patients/<int:ident>/chart-summary")
    def summary(ident):
        patient(ident)
        require_role("patient")
        payload()
        facts = graph_facts(ident)
        if (
            not facts["report_count"]
            and not facts["scales"]
            and not any(facts["medication_marks"].values())
        ):
            return jsonify(status="empty", items=[])
        base, model, _ = ai_settings()
        fingerprint = hashlib.sha256(
            json.dumps(
                [facts, base, model], sort_keys=True, ensure_ascii=False
            ).encode()
        ).hexdigest()
        cached = rows(
            "SELECT * FROM graph_insights WHERE patient_id=? AND fingerprint=?",
            (ident, fingerprint),
        )
        if cached:
            return jsonify(
                status="ready",
                items=json.loads(cached[0]["body_json"]),
                created_at=cached[0]["created_at"],
                cached=True,
            )
        answer = complete(
            'Ты описываешь графики собственных синтетических записей пациента. Ответ по-русски в JSON: {"items":[2–5 коротких наблюдений]}. Используй ТОЛЬКО переданные факты и рассчитанные средние. Если данных мало, скажи это. Нельзя выдумывать значения, проценты соблюдения, причины, диагнозы, прогнозы, дозировки, советы о лекарствах или оценивать успешность лечения. Не делай выводов о причинно-следственной связи сна и тревоги. Баллы шкал — наблюдаемые учебные значения, без клинической интерпретации. Ничего не назначай. Даты и пропуски обозначай явно. Не упоминай отсутствующие данные как нормальные. Ответ — наблюдения для обсуждения со специалистом.',
            json.dumps(facts, ensure_ascii=False),
            True,
        )
        try:
            items = json.loads(answer)["items"]
            if (
                not isinstance(items, list)
                or not 1 <= len(items) <= 5
                or any(
                    not isinstance(item, str) or not item.strip() or len(item) > 700
                    for item in items
                )
            ):
                raise ValueError()
        except (ValueError, TypeError, KeyError):
            raise AssistantUnavailable(
                "Не удалось получить краткую расшифровку графиков. Попробуйте позже."
            ) from None
        stamp = now()
        with db() as con:
            con.execute(
                "INSERT INTO graph_insights VALUES(?,?,?,?) ON CONFLICT(patient_id) DO UPDATE SET fingerprint=excluded.fingerprint,body_json=excluded.body_json,created_at=excluded.created_at",
                (ident, fingerprint, json.dumps(items, ensure_ascii=False), stamp),
            )
        return jsonify(status="ready", items=items, created_at=stamp, cached=False)
