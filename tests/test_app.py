import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from app import create_app


class CompassTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'test.db'
        self.app = create_app(self.path)
        self.client = self.app.test_client()
        self.report = dict(mood=7, anxiety=3, adherence='Да', adverse_effects='', note='Вымышленный пример', safety_signal=False)

    def tearDown(self):
        self.temp.cleanup()

    def test_complete_patient_doctor_workflow(self):
        self.assertEqual(len(self.client.get('/api/patients').json), 2)
        result = self.client.post('/api/patients/2/reports', json={**self.report, 'safety_signal': True})
        self.assertEqual(result.status_code, 201)
        detail = self.client.get('/api/patients/2').json
        self.assertEqual(detail['reports'][0]['note'], self.report['note'])
        self.assertEqual(detail['alerts'][0]['report_id'], result.json['id'])
        self.assertEqual(self.client.get('/api/patients').json[0]['unread'], 1)
        alert_id = detail['alerts'][0]['id']
        self.assertEqual(self.client.post(f'/api/alerts/{alert_id}/review', json={}).status_code, 200)
        self.assertEqual(self.client.get('/api/patients').json[0]['unread'], 0)
        decision = self.client.post('/api/patients/2/decisions', json={'decision': 'Продолжить наблюдение', 'note': 'Демо'})
        self.assertEqual(decision.status_code, 201)
        # New application instance sees durable data; patient B remains isolated.
        other = create_app(self.path).test_client()
        self.assertEqual(other.get('/api/patients/2').json['decisions'][0]['note'], 'Демо')
        self.assertEqual(other.get('/api/patients/3').json, {'reports': [], 'alerts': [], 'decisions': []})

    def test_report_without_safety_does_not_create_alert(self):
        self.assertEqual(self.client.post('/api/patients/2/reports', json=self.report).status_code, 201)
        self.assertEqual(self.client.get('/api/patients/2').json['alerts'], [])

    def test_invalid_input_never_writes(self):
        for changes in ({'mood': -1}, {'anxiety': 11}, {'mood': True}, {'mood': 2.5}, {'safety_signal': 'false'}, {'adherence': 'unknown'}, {'note': 'x'*501}, {'adverse_effects': None}):
            with self.subTest(changes=changes):
                self.assertEqual(self.client.post('/api/patients/2/reports', json={**self.report, **changes}).status_code, 400)
        for data in ([], None, 'text'):
            self.assertEqual(self.client.post('/api/patients/2/reports', data=json.dumps(data), content_type='application/json').status_code, 400)
        self.assertEqual(self.client.post('/api/patients/1/reports', json=self.report).status_code, 400)
        self.assertEqual(self.client.get('/api/patients/2').json['reports'], [])

    def test_bad_decisions_and_unknown_alerts(self):
        self.assertEqual(self.client.post('/api/patients/2/decisions', json={'decision':'Назначить лекарство'}).status_code, 400)
        self.assertEqual(self.client.post('/api/alerts/999/review', json={}).status_code, 400)

    def test_cross_origin_and_non_json_writes_rejected(self):
        self.assertEqual(self.client.post('/api/patients/2/reports', json=self.report, headers={'Origin':'https://other.example'}).status_code, 403)
        self.assertEqual(self.client.post('/api/patients/2/reports', data='text').status_code, 415)
        self.assertEqual(self.client.get('/api/patients/2').headers['Cache-Control'], 'no-store')

    def test_https_proxy_origin_with_preserved_host(self):
        response = self.client.post('/api/patients/2/reports', json=self.report,
                                    headers={'Host': 'compass.example', 'Origin': 'https://compass.example'})
        self.assertEqual(response.status_code, 201)

    def test_pwa_assets_and_health(self):
        self.assertEqual(self.client.get('/api/health').json['status'], 'ok')
        for url in ('/', '/sw.js', '/static/app.js', '/static/style.css', '/static/icon-192.png', '/static/icon-512.png', '/static/icon-maskable.png'):
            with self.client.get(url) as response:
                self.assertEqual(response.status_code, 200, url)
        with self.client.get('/static/manifest.webmanifest') as response:
            manifest = json.loads(response.data)
        self.assertEqual(manifest['display'], 'standalone')
        with self.client.get('/') as response:
            self.assertIn("frame-ancestors 'none'", response.headers['Content-Security-Policy'])

    def test_existing_streamlit_schema_compatible(self):
        # Original tracked demo database remains untouched. Use a copy for compatibility check.
        original = Path(__file__).resolve().parents[1] / 'demo.db'
        with sqlite3.connect(original) as source, sqlite3.connect(self.path) as target:
            source.backup(target)
        legacy = create_app(self.path).test_client()
        self.assertEqual(legacy.get('/api/patients').status_code, 200)
        self.assertEqual(legacy.post('/api/patients/2/reports', json=self.report).status_code, 201)


if __name__ == '__main__':
    unittest.main()
