"""Проверка активности пользователя и настроек уведомлений."""

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
            import sqlite3

            browser = pw.chromium.launch(
                executable_path=shutil.which("chromium"), args=["--no-sandbox"]
            )
            context = browser.new_context(
                viewport={"width": 390, "height": 1000}, reduced_motion="reduce"
            )
            page = context.new_page()
            errors = []
            beats = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on(
                "request",
                lambda r: (
                    beats.append(r.url)
                    if r.url.endswith("/api/activity/heartbeat")
                    else None
                ),
            )
            page.goto(url)
            page.get_by_role("button", name="Войти как Александра").click()
            page.wait_for_function("()=>state.user&&!busy&&!presencePending")
            assert len(beats) >= 1
            before = len(beats)
            page.evaluate(
                "async()=>{presenceSent=0;Object.defineProperty(document,'hidden',{value:true,configurable:true});await sendPresence();}"
            )
            assert len(beats) == before
            page.evaluate(
                "async()=>{Object.defineProperty(document,'hidden',{value:false,configurable:true});await sendPresence();}"
            )
            assert len(beats) == before + 1
            current_beats = len(beats)
            page.evaluate(
                "async()=>{presenceSent=0;presenceInteractionAt=Date.now()-600000;await sendPresence();}"
            )
            assert len(beats) == current_beats
            page.evaluate("presenceInteractionAt=Date.now()")
            page.locator("#more-button").click()
            expect(page.locator("[data-test-push]")).to_be_visible()
            page.locator("[data-test-push]").click()
            expect(page.locator("#toast")).to_contain_text("Сначала подключите push")
            page.locator("[data-group=settings][data-key=consents]").click()
            expect(
                page.locator("[data-pref=relative_away]").locator("..")
            ).to_contain_text("3 суток")
            relative_context = browser.new_context(
                viewport={"width": 390, "height": 1000}, reduced_motion="reduce"
            )
            relative = relative_context.new_page()
            relative.on("pageerror", lambda e: errors.append(str(e)))
            relative.goto(url)
            relative.get_by_role("button", name="Войти как близкий").click()
            relative.wait_for_function("()=>state.user&&!busy")
            data = relative_context.request.get(url + "/api/relative").json()
            with sqlite3.connect(env["COMPASS_DB"]) as con:
                stamp = con.execute(
                    "SELECT last_seen FROM user_presence WHERE user_id=2"
                ).fetchone()[0]
            assert data["patients"][0]["last_active"] == stamp
            relative.locator("#more-button").click()
            expect(relative.locator("[data-care=enable-push]")).to_be_visible()
            expect(relative.locator("[data-test-push]")).to_be_visible()
            relative.screenshot(
                path=str(ART / "push-relative-settings.png"), full_page=True
            )
            assert not errors, errors
            browser.close()
            print(
                "PASS: visible-only presence heartbeat, real visit timestamp, consent wording, patient and relative push/test controls, no fabricated subscription success"
            )
    finally:
        server.terminate()
        server.wait(timeout=10)
