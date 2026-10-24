"""Public themes, registration of three linked roles and fresh doctor workspace."""

import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ART = Path(tempfile.gettempdir()) / "compass-artifacts"
ART.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory() as temp:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {
        **os.environ,
        "COMPASS_DB": str(Path(temp) / "revision7.db"),
        "PORT": str(port),
        "COMPASS_DISABLE_WORKER": "1",
        "COMPASS_AI_API_KEY": "",
        "COMPASS_TELEGRAM_BOT_TOKEN": "",
    }
    server = subprocess.Popen(
        [str(ROOT / ".venv/bin/python"), "app.py"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        url = f"http://127.0.0.1:{port}"
        for _ in range(100):
            try:
                urllib.request.urlopen(url + "/api/health", timeout=1).close()
                break
            except OSError:
                if server.poll() is not None:
                    raise RuntimeError("Server exited")
                time.sleep(0.1)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                executable_path=shutil.which("chromium"), args=["--no-sandbox"]
            )
            context = browser.new_context(
                viewport={"width": 1440, "height": 1000}, reduced_motion="reduce"
            )
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(url)
            page.get_by_role("button", name="Войти как врач").click()
            page.wait_for_function("()=>state.user&&!busy")
            page.locator("#navigation [data-page=letters]").click()
            expect(page.locator("[data-copy-filter=new]")).to_have_text("Новые (2)")
            page.locator("[data-copy-filter=new]").click()
            expect(page.locator(".letter-reply-form")).to_have_count(2)
            page.locator("[data-copy-filter=answered]").click()
            expect(page.locator(".letter-reply-form")).to_have_count(2)
            page.screenshot(path=str(ART / "project-copy-letters.png"), full_page=True)
            page.locator("#navigation [data-page=forum]").click()
            expect(page.locator("#content")).to_contain_text(
                "Как правильно вовлечь родственников"
            )
            assert "1 сообщений" not in page.locator("#content").inner_text()
            page.locator("#navigation [data-page=patients]").click()
            page.locator('[data-action=patient][data-id="2"]').first.click()
            expect(page.locator(".profile-banner .eyebrow")).to_contain_text("МОО97-26")
            page.locator("[data-tab=therapy]").click()
            expect(page.locator("#content")).to_contain_text("Авиандр 20 мг")
            expect(page.locator("#content")).to_contain_text("за 30 минут до еды")
            page.locator("[data-tab=scales]").click()
            expect(page.locator("#content")).to_contain_text(
                "Проводится на приёме по лицензии"
            )
            options = page.locator("#assign-assessment-form option").evaluate_all(
                "els=>els.map(e=>e.value)"
            )
            assert not any(
                k in options for k in ["mmpi", "beck_depression", "beck_hopelessness"]
            )
            page.screenshot(path=str(ART / "project-copy-scales.png"), full_page=True)
            pc = browser.new_context(
                viewport={"width": 390, "height": 1000}, reduced_motion="reduce"
            )
            patient = pc.new_page()
            patient.on("pageerror", lambda e: errors.append(str(e)))
            patient.goto(url)
            patient.get_by_role("button", name="Войти как Александра").click()
            patient.wait_for_function("()=>state.user&&!busy")
            patient.locator("#navigation [data-page=messages]").click()
            patient.locator("[data-group=doctor][data-key=mail]").click()
            expect(patient.locator("#letter-form option")).to_have_count(10)
            expect(patient.locator("#content")).to_contain_text("1–2 рабочих дней")
            expect(patient.locator(".demo-data-footer")).to_have_text("Демо-данные")
            assert not errors, errors
            browser.close()
            print(
                "PASS: physician letter filters, filled forum and plural forms, patient code, licensed-method notices without online forms, patient topics and response timing, shared demo footer"
            )
    finally:
        server.terminate()
        server.wait(timeout=10)
