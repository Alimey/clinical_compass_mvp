"""Clinical Compass: educational, synthetic-data-only prototype.

Run: streamlit run app.py
Never use this code for real patient care.
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

DB = Path(__file__).with_name("demo.db")


def connect():
    con = sqlite3.connect(DB, timeout=10)
    con.row_factory = sqlite3.Row
    return con


def setup():
    with connect() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY, role TEXT NOT NULL,
            name TEXT NOT NULL, doctor_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL, created_at TEXT NOT NULL,
            mood INTEGER NOT NULL, anxiety INTEGER NOT NULL,
            adherence TEXT NOT NULL, adverse_effects TEXT NOT NULL,
            safety_signal INTEGER NOT NULL, note TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL, report_id INTEGER NOT NULL,
            created_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'new',
            explanation TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doctor_id INTEGER NOT NULL, patient_id INTEGER NOT NULL,
            created_at TEXT NOT NULL, decision TEXT NOT NULL, note TEXT NOT NULL
        );
        """)
        con.execute("INSERT OR IGNORE INTO users(id,role,name,doctor_id) VALUES(1,'doctor','Врач (демо)',NULL)")
        con.execute("INSERT OR IGNORE INTO users(id,role,name,doctor_id) VALUES(2,'patient','Пациент А (вымышленный)',1)")
        con.execute("INSERT OR IGNORE INTO users(id,role,name,doctor_id) VALUES(3,'patient','Пациент Б (вымышленный)',1)")


def query(sql, parameters=()):
    with connect() as con:
        return pd.read_sql_query(sql, con, params=parameters)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def submit_report(patient_id, mood, anxiety, adherence, adverse_effects, safety_signal, note):
    with connect() as con:
        cur = con.execute("""INSERT INTO reports
        (patient_id,created_at,mood,anxiety,adherence,adverse_effects,safety_signal,note)
        VALUES(?,?,?,?,?,?,?,?)""", (patient_id, now(), mood, anxiety, adherence,
                                        adverse_effects, int(safety_signal), note))
        report_id = cur.lastrowid
        # Demonstration rule only, NOT a clinical screening/triage protocol.
        if safety_signal:
            con.execute("""INSERT INTO alerts(patient_id,report_id,created_at,explanation)
                           VALUES(?,?,?,?)""", (patient_id, report_id, now(),
                           "Самоотчёт содержит ответ о возможном риске безопасности. Требуется проверка врачом."))
    return bool(safety_signal)


def patient_screen(patient_id, patient_name):
    st.header("Самоотчёт пациента")
    st.caption(f"{patient_name} · демонстрационные вопросы, НЕ валидированная шкала")
    with st.form("report", clear_on_submit=True):
        mood = st.slider("Настроение сегодня (0 — очень плохое, 10 — отличное)", 0, 10, 5)
        anxiety = st.slider("Субъективная тревога (0 — нет, 10 — очень сильная)", 0, 10, 5)
        adherence = st.selectbox("Следовал(а) ли рекомендациям врача?", ["Да", "Частично", "Нет", "Не применимо"])
        adverse = st.text_area("Нежелательные явления / самочувствие", max_chars=500)
        safety = st.checkbox("Есть опасения за свою безопасность или мысли о причинении себе вреда")
        note = st.text_area("Комментарий", max_chars=500)
        sent = st.form_submit_button("Отправить врачу", type="primary")
    if sent:
        flagged = submit_report(patient_id, mood, anxiety, adherence, adverse, safety, note)
        st.success("Самоотчёт записан и доступен врачу в демонстрационной системе.")
        if flagged:
            st.error("Зафиксирован сигнал безопасности. Приложение не является службой экстренной помощи. При непосредственной опасности обратитесь в местные экстренные службы или за срочной медицинской помощью. Не ждите ответа в приложении.")
    st.subheader("История самоотчётов")
    history = query("SELECT created_at, mood, anxiety FROM reports WHERE patient_id=? ORDER BY id", (patient_id,))
    if history.empty:
        st.info("Отчётов пока нет.")
    else:
        st.line_chart(history.set_index("created_at")[["mood", "anxiety"]])


def doctor_screen():
    st.header("Панель врача")
    patients = query("SELECT id, name FROM users WHERE role='patient' AND doctor_id=1 ORDER BY id")
    unread = query("SELECT COUNT(*) AS n FROM alerts WHERE status='new'")
    st.metric("Непросмотренные демонстрационные алерты", int(unread.iloc[0]["n"]))
    patient_id = st.selectbox("Пациент", patients["id"].tolist(),
                              format_func=lambda ident: patients.loc[patients.id == ident, "name"].iloc[0])
    st.subheader("Самоотчёты")
    reports = query("""SELECT id, created_at, mood, anxiety, adherence,
                     adverse_effects, safety_signal, note FROM reports
                     WHERE patient_id=? ORDER BY id DESC""", (patient_id,))
    if reports.empty:
        st.info("Пациент ещё не отправлял самоотчёты.")
    else:
        st.dataframe(reports, hide_index=True, use_container_width=True)
        st.line_chart(reports.sort_values("id").set_index("created_at")[["mood", "anxiety"]])
    st.subheader("Сигналы безопасности")
    alerts = query("SELECT id, created_at, status, explanation FROM alerts WHERE patient_id=? ORDER BY id DESC", (patient_id,))
    if alerts.empty:
        st.info("Сигналов нет.")
    else:
        for alert in alerts.itertuples(index=False):
            with st.container(border=True):
                st.error(f"Сигнал #{alert.id} · {alert.status} · {alert.created_at}")
                st.write(alert.explanation)
                if alert.status == "new" and st.button("Отметить как просмотренный", key=f"seen-{alert.id}"):
                    with connect() as con:
                        con.execute("UPDATE alerts SET status='reviewed' WHERE id=?", (alert.id,))
                    st.rerun()
    st.subheader("Фиксация решения врача")
    st.caption("Приложение ничего не назначает автоматически. Решение вводит врач.")
    with st.form("doctor-decision"):
        decision = st.selectbox("Действие", ["Продолжить наблюдение", "Назначить очную консультацию", "Рассмотреть направление к специалисту", "Другое"])
        note = st.text_area("Обоснование / заметки (только синтетические данные)")
        saved = st.form_submit_button("Подтвердить и сохранить")
    if saved:
        with connect() as con:
            con.execute("INSERT INTO decisions(doctor_id,patient_id,created_at,decision,note) VALUES(?,?,?,?,?)",
                        (1, patient_id, now(), decision, note))
        st.success("Действие врача сохранено.")
    previous = query("SELECT created_at, decision, note FROM decisions WHERE patient_id=? ORDER BY id DESC", (patient_id,))
    if not previous.empty:
        st.dataframe(previous, hide_index=True, use_container_width=True)


st.set_page_config(page_title="Клинический компас · демо", page_icon="🧭", layout="wide")
setup()
st.title("Клинический компас")
st.warning("Учебный прототип для кейс-чемпионата. Только вымышленные данные. Не использовать для реальной диагностики, лечения или экстренной помощи.")
role = st.sidebar.radio("Режим просмотра", ["Врач", "Пациент"])
st.sidebar.caption("Переключение ролей — не авторизация; для демонстрации в контролируемой среде.")
if role == "Врач":
    doctor_screen()
else:
    available = query("SELECT id, name FROM users WHERE role='patient' AND doctor_id=1 ORDER BY id")
    pid = st.sidebar.selectbox("Демо-пациент", available.id.tolist(),
                               format_func=lambda ident: available.loc[available.id == ident, "name"].iloc[0])
    patient_screen(pid, available.loc[available.id == pid, "name"].iloc[0])
