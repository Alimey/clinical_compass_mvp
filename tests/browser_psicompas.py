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
            page.screenshot(path=str(ART / "psicompas-login.png"), full_page=True)
            page.get_by_role("button", name="Войти как Александра").click()
            expect(
                page.get_by_role("heading", name="Здравствуйте, Александра")
            ).to_be_visible()
            page.screenshot(path=str(ART / "psicompas-home.png"), full_page=True)
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
            page.get_by_role("button", name="Календарь", exact=True).click()
            expect(page.locator(".calendar-grid")).to_be_visible()
            today = page.evaluate("care().today")
            page.locator(f'[data-ui="calendar-day"][data-day="{today}"]').click()
            expect(page.locator("#content")).to_contain_text("Сон: 7/10")
            page.screenshot(path=str(ART / "psicompas-calendar.png"), full_page=True)
            page.locator("#navigation [data-page=learn]").click()
            page.locator(".lesson-option").first.click()
            page.get_by_role("button", name="Отметить прочитанным").click()
            expect(page.get_by_role("button", name="✓ Прочитано")).to_be_disabled()
            page.get_by_role("button", name="Все материалы").click()
            expect(page.locator(".notice")).to_contain_text("1 из 3")
            page.locator("#navigation [data-page=help]").click()
            page.locator(".emotion-accordion").last.locator("summary").click()
            expect(page.get_by_role("link", name="Позвонить 112")).to_have_attribute(
                "href", "tel:112"
            )
            assert "Сигнал отправлен" not in page.locator("#content").inner_text()
            page.locator("[data-ext=sub][data-group=help][data-key=calm]").click()
            practice = page.locator("[data-practice=breathing]")
            practice.locator("summary").click()
            practice.get_by_role("button", name="Да, начать").click()
            expect(practice.locator(".guided-clock")).to_contain_text("1:00")
            practice.get_by_role("button", name="Пауза", exact=True).click()
            expect(
                page.get_by_role("button", name="Продолжить", exact=True)
            ).to_be_visible()
            # Advance the browser clock instead of waiting a real minute.
            page.clock.install()
            page.get_by_role("button", name="Продолжить", exact=True).click()
            page.clock.fast_forward(61000)
            expect(practice.locator("[data-experience=practice-save]")).to_be_visible()
            practice.locator("[data-experience=practice-save]").click()
            expect(page.locator(".activity-row")).to_contain_text("Спокойная пауза")
            page.clock.resume()
            page.reload()
            expect(
                page.get_by_role("heading", name="Здравствуйте, Александра")
            ).to_be_visible()
            page.locator("#navigation [data-page=help]").click()
            page.locator("[data-ext=sub][data-group=help][data-key=calm]").click()
            expect(page.locator(".activity-row")).to_contain_text("Спокойная пауза")
            page.locator("#navigation [data-page=learn]").click()
            expect(page.locator(".notice")).to_contain_text("1 из 3")
            page.go_back()
            expect(
                page.get_by_role("heading", name="Дыхание и заземление")
            ).to_be_visible()
            page.get_by_role("button", name="Включить тёмную тему").click()
            expect(page.locator("html")).to_have_attribute("data-theme", "dark")
            page.locator("#navigation [data-page=overview]").click()
            page.screenshot(path=str(ART / "psicompas-dark.png"), full_page=True)
            page.reload()
            expect(page.locator("html")).to_have_attribute("data-theme", "dark")
            page.get_by_role("button", name="Включить светлую тему").click()
            for width in (320, 390, 430, 1280):
                page.set_viewport_size({"width": width, "height": 844})
                for name in ("overview", "diary", "move", "learn", "help", "messages"):
                    page.locator(f'#navigation [data-page="{name}"]').click()
                    expect(
                        page.locator(f'#navigation [data-page="{name}"]')
                    ).to_have_attribute("aria-current", "page")
                    assert page.evaluate(
                        "document.documentElement.scrollWidth <= innerWidth"
                    ), (width, name)
                assert page.locator("#navigation").bounding_box()["width"] <= width
            page.evaluate("navigator.serviceWorker.ready")
            cached = page.evaluate(
                """async()=>{const c=await caches.open('compass-shell-v7');return (await c.keys()).map(r=>new URL(r.url).pathname)}"""
            )
            assert (
                "/static/psicompas.js" in cached and "/static/psicompas.css" in cached
            )
            assert len([p for p in cached if p.endswith(".woff2")]) == 4
            assert not any(p.startswith("/api/") for p in cached)
            assert not errors, errors
            assert not external, external
            assert not csp, csp
            context.close()
            browser.close()
            print(
                "PASS: home tablet tracking, mood/sleep/energy, calendar, lessons, help contacts, practice timer and persistence, browser Back, themes, 4 widths, fully local PWA assets"
            )
    finally:
        server.terminate()
        server.wait(timeout=10)
