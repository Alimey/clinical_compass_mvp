"""Optional browser smoke test: pip install playwright; playwright install chromium.
Uses installed system Chromium when available. Run from repository root.
"""
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as temp:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    env = {**os.environ, 'COMPASS_DB': str(Path(temp)/'browser.db'), 'PORT': str(port)}
    python = ROOT / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    server = subprocess.Popen([str(python), 'app.py'], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f'http://127.0.0.1:{port}'
    try:
        for _ in range(100):
            try:
                with urllib.request.urlopen(url+'/api/health', timeout=1) as response:
                    assert response.status == 200
                break
            except OSError:
                if server.poll() is not None:
                    raise RuntimeError('Test server exited')
                time.sleep(.1)
        else:
            raise RuntimeError('Test server did not start')
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or shutil.which('chromium'), args=['--no-sandbox'])
            context = browser.new_context(viewport={'width':390,'height':844}, is_mobile=True, has_touch=True)
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(url)
            expect(page.locator('#patient option')).to_have_count(2)
            page.locator('#note').fill('<script>window.injected=true</script> Вымышленный пример')
            page.locator('#safety').check()
            expect(page.locator('#urgent')).to_be_visible()
            page.get_by_role('button', name='Сохранить самоотчёт', exact=True).click()
            expect(page.locator('#status')).to_contain_text('Самоотчёт сохранён')
            page.get_by_role('button', name='История', exact=True).click()
            expect(page.locator('#patient-history')).to_contain_text('<script>window.injected=true</script>')
            assert page.evaluate('window.injected') is None
            page.get_by_role('button', name='Я врач', exact=True).click()
            expect(page.locator('#unread')).to_contain_text('1 у пациента')
            page.get_by_role('button', name='Отметить просмотренным').click()
            expect(page.locator('#unread')).to_contain_text('0 у пациента')
            page.locator('#decision-note').fill('Вымышленное решение')
            page.get_by_role('button', name='Сохранить решение', exact=True).click()
            expect(page.locator('#decisions')).to_contain_text('Вымышленное решение')
            page.locator('#patient').select_option('3')
            expect(page.locator('#doctor-history')).to_contain_text('Пока нет самоотчётов')
            page.locator('#patient').select_option('2')
            expect(page.locator('#doctor-history')).to_contain_text('Вымышленный пример')
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            Path('/tmp/compass-artifacts').mkdir(exist_ok=True)
            page.screenshot(path='/tmp/compass-artifacts/doctor-mobile.png', full_page=True)
            page.get_by_role('button', name='Я пациент', exact=True).click()
            page.screenshot(path='/tmp/compass-artifacts/patient-mobile.png', full_page=True)
            # Wait for active worker before testing a genuine offline navigation.
            page.evaluate('navigator.serviceWorker.ready')
            page.reload()
            page.wait_for_function('navigator.serviceWorker.controller !== null')
            caches = page.evaluate('''async()=>{const out=[];for(const key of await caches.keys()){const c=await caches.open(key);out.push(...(await c.keys()).map(r=>new URL(r.url).pathname));}return out;}''')
            assert '/' in caches and not any(path.startswith('/api/') for path in caches), caches
            context.set_offline(True)
            page.reload()
            expect(page.locator('#connection')).to_be_visible()
            page.locator('#note').fill('Офлайн-черновик')
            page.get_by_role('button', name='Сохранить самоотчёт', exact=True).click()
            expect(page.locator('#status')).to_contain_text('Не удалось сохранить')
            expect(page.locator('#note')).to_have_value('Офлайн-черновик')
            context.set_offline(False)
            page.reload()
            expect(page.locator('#patient option')).to_have_count(2)
            # Narrow Android size and larger iPhone size: layout only, same Chromium engine.
            for width, height in [(320,740),(430,932),(1280,800)]:
                page.set_viewport_size({'width':width,'height':height})
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), width
            assert not errors, errors
            context.close()
            browser.close()
            print('PASS: mobile patient/doctor workflow, isolation, XSS escaping, offline shell, no API cache, 4 viewport sizes; no JS errors')
    finally:
        server.terminate()
        server.wait(timeout=10)
