"""Geometry and interaction checks for real desktop, tablet and phone layouts."""

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
        "COMPASS_DB": str(Path(temp) / "layout.db"),
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
                executable_path=os.environ.get("CHROMIUM_PATH")
                or shutil.which("chromium"),
                args=["--no-sandbox"],
            )
            context = browser.new_context(
                viewport={"width": 1440, "height": 1000},
                reduced_motion="reduce",
                timezone_id="Europe/Moscow",
            )
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(url)
            expect(page.locator(".login-layout")).to_be_visible()
            assert page.locator(".login-layout").bounding_box()["width"] >= 1438
            page.screenshot(
                path=str(ART / "responsive-login-desktop.png"), full_page=True
            )
            page.get_by_role("button", name="Войти как Александра").click()
            expect(
                page.get_by_role("heading", name="Здравствуйте, Александра")
            ).to_be_visible()
            crown = page.locator(".animated-tree .tree-crown")
            expect(page.locator(".animated-tree")).to_be_visible()
            expect(page.locator(".tree-motion-toggle")).to_have_count(0)
            assert crown.evaluate("el=>getComputedStyle(el).animationName") == "none"
            page.emulate_media(reduced_motion="no-preference")
            assert (
                crown.evaluate("el=>getComputedStyle(el).animationName") == "tree-sway"
            )
            context.set_offline(True)
            assert (
                crown.evaluate("el=>getComputedStyle(el).animationPlayState")
                == "running"
            )
            context.set_offline(False)
            page.emulate_media(reduced_motion="reduce")
            for width in (320, 390, 430, 768, 1024, 1280, 1440, 1920):
                page.set_viewport_size({"width": width, "height": 900})
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= innerWidth"
                ), (width, "home overflow")
                shell = page.locator("#app-shell").bounding_box()
                assert shell["width"] >= width - 2, (width, shell)
                nav = page.locator("#navigation").bounding_box()
                if width >= 1024:
                    sidebar = page.locator(".sidebar").bounding_box()
                    content = page.locator("#content").bounding_box()
                    assert content["width"] >= width - sidebar["width"] - 2, (
                        width,
                        content,
                    )
                    assert nav["width"] < 300 and nav["height"] > 200
                    hero = page.locator(".welcome-garden").bounding_box()
                    appointments = page.locator(
                        ".patient-dashboard > .appointment-section"
                    ).bounding_box()
                    assert abs(hero["y"] - appointments["y"]) < 2, (
                        width,
                        hero,
                        appointments,
                    )
                    assert appointments["x"] > hero["x"] + hero["width"] - 1
                    page.locator("#workspace-tools [data-page=settings]").click()
                    expect(
                        page.get_by_role("heading", name="Уведомления и установка PWA")
                    ).to_be_visible()
                    page.locator(".app-brand[data-page=overview]").click()
                    expect(
                        page.get_by_role("heading", name="Здравствуйте, Александра")
                    ).to_be_visible()
                else:
                    assert nav["y"] > 750 and nav["y"] + nav["height"] <= 901, (
                        width,
                        nav,
                    )
                    first = page.locator(
                        ".home-actions .quick-card"
                    ).first.bounding_box()
                    assert first["width"] >= 44, (width, first)
                if width in (390, 1440):
                    page.evaluate("scrollTo(0,0)")
                    page.screenshot(
                        path=str(ART / f"responsive-home-{width}.png"), full_page=True
                    )
                    page.emulate_media(reduced_motion="no-preference")
                    tree_box = page.locator(
                        ".home-tree-scene .care-tree"
                    ).bounding_box()
                    garden_box = page.locator(".welcome-garden").bounding_box()
                    assert tree_box["y"] >= garden_box["y"], (
                        width,
                        tree_box,
                        garden_box,
                    )
                    page.locator(".welcome-garden").screenshot(
                        path=str(ART / f"tree-home-{width}.png"), animations="disabled"
                    )
                    page.emulate_media(reduced_motion="reduce")
            page.set_viewport_size({"width": 1440, "height": 1000})
            page.locator("#navigation [data-page=messages]").click()
            expect(page.locator("#message-form")).to_be_visible()
            assert page.locator(".chat-card").bounding_box()["width"] > 900
            page.locator("#message-body").fill(
                "Синтетическое сообщение: широкий интерфейс"
            )
            page.get_by_role("button", name="Отправить сообщение").click()
            expect(page.locator("#chat-thread")).to_contain_text("широкий интерфейс")
            expect(page.locator("#toast")).to_be_hidden(timeout=15000)
            page.screenshot(
                path=str(ART / "responsive-chat-desktop.png"), full_page=True
            )
            page.set_viewport_size({"width": 390, "height": 844})
            page.evaluate("scrollTo(0,0)")
            mobile_nav = page.locator(".navigation-dock").bounding_box()
            assert abs(mobile_nav["y"] + mobile_nav["height"] - 844) < 2
            assert abs(page.locator(".topbar").bounding_box()["y"]) < 2
            page.screenshot(
                path=str(ART / "responsive-chat-mobile.png"), full_page=True
            )
            page.screenshot(path=str(ART / "responsive-chat-mobile-viewport.png"))
            page.get_by_role("button", name="Включить тёмную тему").click()
            expect(page.locator("html")).to_have_attribute("data-theme", "dark")
            page.set_viewport_size({"width": 1440, "height": 1000})
            page.locator(".app-brand[data-page=overview]").click()
            page.screenshot(
                path=str(ART / "responsive-dark-desktop.png"), full_page=True
            )
            page.get_by_role("button", name="Включить светлую тему").click()
            page.get_by_role("button", name="Выйти", exact=True).click()
            page.get_by_role("button", name="Войти как врач").click()
            expect(
                page.get_by_role("heading", name="Добрый день, Анна")
            ).to_be_visible()
            expect(page.locator("#toast")).to_be_hidden(timeout=15000)
            expect(page.locator(".sidebar [aria-current=page]")).to_have_count(1)
            page.screenshot(
                path=str(ART / "responsive-doctor-desktop.png"), full_page=True
            )
            columns = page.locator(".two-columns > .card").all()
            assert columns[1].bounding_box()["x"] > columns[0].bounding_box()["x"]
            assert not errors, errors
            browser.close()
            print(
                "PASS: animated home tree offline, reduced motion, full-width shell, desktop columns and sidebar, tablet/phone navigation, 8 widths, login/chat, theme switching and desktop messaging"
            )
    finally:
        server.terminate()
        server.wait(timeout=10)
