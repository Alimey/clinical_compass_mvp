"""Демонстрационные правила формирования предложений для специалиста."""

from compass.db import db, now

VERSION = "synthetic-3.0"
CATALOG = [
    {
        "id": "demo-alpha",
        "name": "ДЕМО-Альфа",
        "color": "mint",
        "tag": "Базовый сценарий",
        "description": "Вымышленный вариант сопровождения для демонстрации согласования плана.",
        "checks": ["Обсудить цель наблюдения", "Согласовать дневник самочувствия"],
        "restriction": "",
    },
    {
        "id": "demo-beta",
        "name": "ДЕМО-Бета",
        "color": "lilac",
        "tag": "Альтернативный сценарий",
        "description": "Вымышленная альтернатива. Показывает проверку несовместимости в профиле.",
        "checks": ["Проверить учебные ограничения профиля", "Подтвердить выбор врачом"],
        "restriction": "demo-beta",
    },
    {
        "id": "demo-gamma",
        "name": "ДЕМО-Гамма",
        "color": "peach",
        "tag": "Сценарий с наблюдением",
        "description": "Вымышленный вариант для демонстрации повторного контакта и контроля самочувствия.",
        "checks": ["Согласовать повторный контакт", "Проверить записи о самочувствии"],
        "restriction": "",
    },
]


def evaluate(report):
    """Return explainable demo proposals; never diagnose or change a plan."""
    result = []
    if report["safety_signal"]:
        result.append(
            (
                "referral",
                "mandatory",
                "Проверить безопасность и обсудить маршрутизацию",
                "Пациент сообщил об опасениях за свою безопасность. Основание: запись в дневнике и план безопасности.",
            )
        )
    elif report["anxiety"] >= 8 or report["mood"] <= 2:
        result.append(
            (
                "referral",
                "desirable",
                "Обсудить дополнительную консультацию",
                "Тревога ≥ 8 или настроение ≤ 2. Условные пороги демо-правила S-02, не клинический триаж.",
            )
        )
    if report["adverse_effects"].strip():
        result.append(
            (
                "tolerability",
                "mandatory",
                "Уточнить переносимость плана",
                "Пациент отметил нежелательные явления. Уточните симптомы и переносимость лечения.",
            )
        )
    if report["adherence"] in ("Нет", "Частично"):
        result.append(
            (
                "adherence",
                "desirable",
                "Обсудить трудности соблюдения плана",
                "Соблюдение плана ниже ожидаемого. Основание: дневник пациента.",
            )
        )
    return result


def add_proposals(patient_id, report_id, report):
    for kind, tier, title, reason in evaluate(report):
        db().execute(
            """INSERT OR IGNORE INTO proposals
            (patient_id,report_id,kind,tier,title,reason,rule_version,created_at)
            VALUES(?,?,?,?,?,?,?,?)""",
            (patient_id, report_id, kind, tier, title, reason, VERSION, now()),
        )
