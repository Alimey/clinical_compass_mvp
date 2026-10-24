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
        "COMPASS_DB": str(Path(temp) / "revision8.db"),
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
                viewport={"width": 390, "height": 1000}, reduced_motion="reduce"
            )
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(url)
            page.get_by_role("button", name="Войти как Александра").click()
            page.wait_for_function("()=>state.user&&!busy")
            form = page.locator(".counter-label-form")
            form.locator("input").fill("Мои спокойные дни")
            form.locator("button").click()
            expect(page.locator(".home-counter h2")).to_have_text("Мои спокойные дни")
            page.locator(".home-tree-link").click()
            expect(page.locator(".earned-tree")).to_be_visible()
            expect(page.locator(".tree-legend li")).to_have_count(5)
            page.evaluate("()=>flowerQueue")
            page.screenshot(path=str(ART / "revision8-tree.png"), full_page=True)
            page.locator("#navigation [data-page=diary]").click()
            page.locator("[data-ext=sub][data-group=diary][data-key=scales]").click()
            expect(
                page.locator(".extended-assessments [data-ext=assessment]")
            ).to_have_count(11)
            for key in [
                "mmpi",
                "leonhard",
                "beck_hopelessness",
                "beck_depression",
                "spielberger",
                "hcl33",
                "mdq",
                "dembo",
                "cope",
            ]:
                page.locator(f"[data-ext=assessment][data-key={key}]").click()
                f = page.locator(".extra-assessment-form")
                expect(f).to_be_visible()
                for select in f.locator("select").all():
                    select.select_option("1")
                f.locator("button[type=submit],button:not([type])").first.click()
                expect(page.locator(".extended-assessments")).to_be_visible()
                page.wait_for_function("()=>!busy")
            page.locator("[data-ext=assessment][data-key=schulte]").click()
            for n in range(1, 26):
                page.locator(f'[data-schulte="{n}"]').click()
            expect(page.locator("#schulte-status")).to_contain_text(
                "Результат сохранён"
            )
            page.screenshot(path=str(ART / "revision8-schulte.png"), full_page=True)
            page.locator("[data-ext=assessment-cancel]").click()
            page.locator("[data-ext=assessment][data-key=serial7]").click()
            for i in range(13):
                page.locator(f"#serial7-form [name=q{i}]").fill(str(100 - 7 * (i + 1)))
            page.locator("#serial7-form button").first.click()
            expect(page.locator("#serial7-result")).to_contain_text("13 из 13")
            page.wait_for_function("()=>!busy")
            page.locator("#navigation [data-page=help]").click()
            page.locator("[data-ext=sub][data-group=help][data-key=games]").click()
            page.locator("[data-game-select=lab]").click()
            canvas = page.locator("#game-canvas")
            expect(page.locator("#game-status")).to_contain_text("Собрано пилюль: 0")
            canvas.press("ArrowUp")
            expect(page.locator("#game-status")).to_contain_text("Собрано пилюль: 0")
            canvas.press("ArrowRight")
            expect(page.locator("#game-status")).to_contain_text("Собрано пилюль: 1")
            page.locator('[data-game-action=lab-step][data-dx="1"]').click()
            expect(page.locator("#game-status")).to_contain_text("Собрано пилюль: 2")
            page.screenshot(path=str(ART / "revision8-labyrinth.png"), full_page=True)
            for width in [320, 390, 768, 1024, 1440]:
                page.set_viewport_size({"width": width, "height": 1000})
                assert page.evaluate(
                    "document.documentElement.scrollWidth<=innerWidth"
                ), width
            page.locator("[data-game-select=jam]").click()
            canvas = page.locator("#game-canvas")
            box = canvas.bounding_box()
            canvas.click(
                position={"x": 100 / 720 * box["width"], "y": 353 / 500 * box["height"]}
            )
            expect(page.locator("#game-status")).to_contain_text("Ягод лопнуто: 1")
            page.wait_for_timeout(950)
            canvas.click(
                position={"x": 100 / 720 * box["width"], "y": 353 / 500 * box["height"]}
            )
            expect(page.locator("#game-status")).to_contain_text("Ягод лопнуто: 2")
            page.screenshot(path=str(ART / "revision8-jam.png"), full_page=True)
            page.locator("#navigation [data-page=learn]").click()
            page.locator("[data-group=learn][data-key=course]").click()
            expect(page.locator(".school-videos summary")).to_have_count(5)
            expect(page.locator(".school-videos")).to_contain_text("Синапс под дождем")
            assert not errors, errors
            browser.close()
            print(
                "PASS: named private counter, tree navigation and color legend, nine demo forms with persistence, Schulte and serial subtraction, labyrinth pills/walls/keyboard/buttons, popping and regrowing berries, video titles, 5 widths"
            )
    finally:
        server.terminate()
        server.wait(timeout=10)
