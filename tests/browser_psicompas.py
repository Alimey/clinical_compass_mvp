"""New prototype flows in a real browser, with a temporary synthetic database."""

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
ART = Path(tempfile.gettempdir()) / "compass-artifacts"
ART.mkdir(exist_ok=True)

with tempfile.TemporaryDirectory() as temp:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {
        **os.environ,
        "COMPASS_DB": str(Path(temp) / "browser.db"),
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
        else:
            raise RuntimeError("Server not ready")
        with sync_playwright() as p:
            browser = p.chromium.launch(
                executable_path=os.environ.get("CHROMIUM_PATH")
                or shutil.which("chromium"),
                args=["--no-sandbox"],
            )
            context = browser.new_context(
                viewport={"width": 390, "height": 844},
                is_mobile=True,
                has_touch=True,
                timezone_id="Europe/Moscow",
                reduced_motion="reduce",
            )
            page = context.new_page()
            errors, external, csp = [], [], []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on(
                "request",
                lambda r: external.append(r.url) if not r.url.startswith(url) else None,
            )
            page.on(
                "console",
                lambda m: (
                    csp.append(m.text) if "Content Security Policy" in m.text else None
                ),
            )
            page.goto(url)
            page.get_by_role("button", name="Войти как Александра").click()
            expect(page.locator(".patient-dashboard")).to_be_visible()
            expect(page.locator(".dose-tile").first).to_be_enabled()
            page.locator(".dose-tile").first.click()
            expect(page.locator(".dose-tile").first).to_contain_text("Принято")
            page.get_by_role("button", name="Хорошо · 10 из 10", exact=True).click()
            expect(page.locator("#mood")).to_have_value("10")
            for key, value in (("sleep", 7), ("energy", 4)):
                page.locator("#" + key).evaluate(
                    "(el,value)=>{el.value=value;el.dispatchEvent(new Event('input',{bubbles:true}));}",
                    value,
                )
            page.locator("#note").fill("Новая запись из ПсиКомпаса")
            page.get_by_role("button", name="Сохранить самоотчёт").click()
            expect(page.locator("#report-history")).to_contain_text(
                "Сон: 7/10 · Энергия: 4/10"
            )
            expect(page.locator("#daily-calendar .activity-calendar")).to_be_visible()
            today = page.evaluate("care().today")
            page.locator(
                f'[data-experience=calendar-day][data-group=diary][data-day="{today}"]'
            ).click()
            expect(page.locator("#report-history")).to_contain_text("Сон: 7/10")
            page.locator("#navigation [data-page=learn]").click()
            page.locator(".course-item summary").first.click()
            expect(page.locator(".video-placeholder").first).to_be_visible()
            expect(page.locator(".lesson-option")).to_have_count(0)
            page.locator("#navigation [data-page=help]").click()
            page.locator(".emotion-accordion").last.locator("summary").click()
            expect(page.get_by_role("link", name="Позвонить 112")).to_have_attribute(
                "href", "tel:112"
            )
            page.locator("[data-ext=sub][data-group=help][data-key=calm]").click()
            ground = page.locator("[data-practice=grounding]")
            ground.locator("summary").click()
            ground.get_by_role("button", name="Да, начать").click()
            for _ in range(5):
                ground.get_by_role("button", name="Далее").click()
            expect(page.locator(".activity-row")).to_contain_text("Пять вещей вокруг")
            page.reload()
            expect(page.locator(".patient-dashboard")).to_be_visible()
            page.locator("#navigation [data-page=help]").click()
            page.locator("[data-ext=sub][data-group=help][data-key=calm]").click()
            expect(page.locator(".activity-row")).to_contain_text("Пять вещей вокруг")
            page.locator("#navigation [data-page=learn]").click()
            page.go_back()
            expect(page.locator(".practice-list")).to_be_visible()
            page.get_by_role("button", name="Включить тёмную тему").click()
            expect(page.locator("html")).to_have_attribute("data-theme", "dark")
            page.reload()
            expect(page.locator("html")).to_have_attribute("data-theme", "dark")
            expect(page.locator(".patient-dashboard")).to_be_visible()
            page.get_by_role("button", name="Включить светлую тему").click()
            for width in (320, 390, 430, 1280):
                page.set_viewport_size({"width": width, "height": 844})
                for name in (
                    "overview",
                    "diary",
                    "move",
                    "learn",
                    "help",
                    "messages",
                    "schedule",
                ):
                    page.locator(f'#navigation [data-page="{name}"]').click()
                    expect(
                        page.locator(f'#navigation [data-page="{name}"]')
                    ).to_have_attribute("aria-current", "page")
                    assert page.evaluate(
                        "document.documentElement.scrollWidth<=innerWidth"
                    ), (width, name)
            page.evaluate("navigator.serviceWorker.ready")
            cached = page.evaluate(
                """async()=>{const c=await caches.open('compass-shell-v8');return (await c.keys()).map(r=>new URL(r.url).pathname)}"""
            )
            assert (
                "/static/patient-ui.js" in cached and "/static/patient-ui.css" in cached
            )
            assert len([p for p in cached if p.endswith(".woff2")]) == 4
            assert not any(p.startswith("/api/") for p in cached)
            assert not errors, errors
            assert not external, external
            assert not csp, csp
            browser.close()
            print(
                "PASS: home medication tracking, combined diary/calendar, mood/sleep/energy, school placeholders, sequential grounding and automatic persistence, Back, themes, 4 widths and fully local PWA assets"
            )
    finally:
        server.terminate()
        server.wait(timeout=10)
