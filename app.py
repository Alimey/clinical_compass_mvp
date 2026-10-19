"""Clinical Compass mobile demo. Synthetic data only."""
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from flask import Flask, g, jsonify, request
from werkzeug.exceptions import HTTPException


def create_app(database=None):
    app = Flask(__name__, static_folder='static')
    app.config.update(DATABASE=str(database or os.environ.get('COMPASS_DB', Path(__file__).with_name('instance') / 'compass.db')), MAX_CONTENT_LENGTH=16384)
    Path(app.config['DATABASE']).parent.mkdir(parents=True, exist_ok=True)

    def db():
        if 'db' not in g:
            g.db = sqlite3.connect(app.config['DATABASE'], timeout=10)
            g.db.row_factory = sqlite3.Row
        return g.db

    @app.teardown_appcontext
    def close_db(error):
        con = g.pop('db', None)
        if con is not None:
            con.close()

    with app.app_context():
        db().executescript('''
        CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, role TEXT NOT NULL, name TEXT NOT NULL, doctor_id INTEGER);
        CREATE TABLE IF NOT EXISTS reports (id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL, created_at TEXT NOT NULL, mood INTEGER NOT NULL, anxiety INTEGER NOT NULL, adherence TEXT NOT NULL, adverse_effects TEXT NOT NULL, safety_signal INTEGER NOT NULL, note TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS alerts (id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL, report_id INTEGER NOT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'new', explanation TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS decisions (id INTEGER PRIMARY KEY AUTOINCREMENT, doctor_id INTEGER NOT NULL, patient_id INTEGER NOT NULL, created_at TEXT NOT NULL, decision TEXT NOT NULL, note TEXT NOT NULL);
        INSERT OR IGNORE INTO users VALUES(1,'doctor','Врач (демо)',NULL);
        INSERT OR IGNORE INTO users VALUES(2,'patient','Пациент А (вымышленный)',1);
        INSERT OR IGNORE INTO users VALUES(3,'patient','Пациент Б (вымышленный)',1);
        ''')
        db().commit()

    def rows(sql, args=()):
        return [dict(row) for row in db().execute(sql, args).fetchall()]

    def patient(ident):
        if not rows("SELECT id FROM users WHERE id=? AND role='patient' AND doctor_id=1", (ident,)):
            raise ValueError('Демо-пациент не найден')

    def payload():
        data = request.get_json()
        if not isinstance(data, dict):
            raise ValueError('Ожидается JSON-объект')
        return data

    def text(data, key, limit=500):
        value = data.get(key, '')
        if not isinstance(value, str) or len(value) > limit:
            raise ValueError(f'Поле {key}: допустимо до {limit} символов')
        return value.strip()

    def now():
        return datetime.now(timezone.utc).isoformat(timespec='seconds')

    @app.before_request
    def same_origin():
        if request.method == 'POST':
            origin = request.headers.get('Origin')
            if request.headers.get('Sec-Fetch-Site') == 'cross-site' or (origin and (urlsplit(origin).scheme not in ('http', 'https') or urlsplit(origin).netloc != request.host)):
                return jsonify(error='Запрос с другого сайта запрещён'), 403

    @app.after_request
    def headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        return response

    @app.errorhandler(ValueError)
    def invalid(error):
        return jsonify(error=str(error)), 400

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error=error.description), error.code

    @app.get('/')
    def index():
        return app.send_static_file('index.html')

    @app.get('/sw.js')
    def worker():
        return app.send_static_file('sw.js')

    @app.get('/api/health')
    def health():
        db().execute('SELECT 1').fetchone()
        return jsonify(status='ok', mode='synthetic-demo')

    @app.get('/api/patients')
    def patients():
        return jsonify(rows("SELECT u.id, u.name, (SELECT COUNT(*) FROM alerts a WHERE a.patient_id=u.id AND a.status='new') AS unread FROM users u WHERE role='patient' AND doctor_id=1 ORDER BY id"))

    @app.get('/api/patients/<int:ident>')
    def detail(ident):
        patient(ident)
        return jsonify(**{table: rows(f'SELECT * FROM {table} WHERE patient_id=? ORDER BY id DESC', (ident,)) for table in ('reports', 'alerts', 'decisions')})

    @app.post('/api/patients/<int:ident>/reports')
    def report(ident):
        patient(ident)
        data = payload()
        for key in ('mood', 'anxiety'):
            if type(data.get(key)) is not int or not 0 <= data[key] <= 10:
                raise ValueError('Настроение и тревога: целые числа от 0 до 10')
        if type(data.get('safety_signal')) is not bool:
            raise ValueError('Укажите сигнал безопасности')
        if data.get('adherence') not in ('Да', 'Частично', 'Нет', 'Не применимо'):
            raise ValueError('Выберите соблюдение рекомендаций')
        adverse, note, stamp = text(data, 'adverse_effects'), text(data, 'note'), now()
        with db() as con:
            cur = con.execute('INSERT INTO reports(patient_id,created_at,mood,anxiety,adherence,adverse_effects,safety_signal,note) VALUES(?,?,?,?,?,?,?,?)', (ident, stamp, data['mood'], data['anxiety'], data['adherence'], adverse, int(data['safety_signal']), note))
            report_id = cur.lastrowid
            if data['safety_signal']:
                con.execute('INSERT INTO alerts(patient_id,report_id,created_at,explanation) VALUES(?,?,?,?)', (ident, report_id, stamp, 'В самоотчёте отмечены опасения за безопасность. Требуется проверка врачом.'))
        return jsonify(id=report_id, safety_signal=data['safety_signal']), 201

    @app.post('/api/alerts/<int:ident>/review')
    def review(ident):
        payload()
        with db() as con:
            cur = con.execute("UPDATE alerts SET status='reviewed' WHERE id=? AND patient_id IN (SELECT id FROM users WHERE doctor_id=1 AND role='patient')", (ident,))
            if not cur.rowcount:
                raise ValueError('Сигнал не найден')
        return jsonify(status='reviewed')

    @app.post('/api/patients/<int:ident>/decisions')
    def decision(ident):
        patient(ident)
        data = payload()
        action, note = text(data, 'decision', 100), text(data, 'note')
        if action not in ('Продолжить наблюдение', 'Назначить очную консультацию', 'Рассмотреть направление к специалисту', 'Другое'):
            raise ValueError('Выберите действие врача')
        with db() as con:
            cur = con.execute('INSERT INTO decisions(doctor_id,patient_id,created_at,decision,note) VALUES(1,?,?,?,?)', (ident, now(), action, note))
        return jsonify(id=cur.lastrowid), 201

    return app


if __name__ == '__main__':
    create_app().run(host=os.environ.get('COMPASS_HOST', '127.0.0.1'), port=int(os.environ.get('PORT', '8000')), debug=False)
