"""Home, entry, notification acknowledgement and real browser history flows."""

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
        "COMPASS_DB": str(Path(temp) / "revision6.db"),
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
                viewport={"width": 390, "height": 1000},
                reduced_motion="reduce",
                timezone_id="Europe/Moscow",
            )
            page = context.new_page()
            errors = []
            csp = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on(
                "console",
                lambda m: (
                    csp.append(m.text) if "Content Security Policy" in m.text else None
                ),
            )
            page.goto(url)
            expect(page.locator(".entry-garden .care-tree")).to_be_visible()
            expect(page.locator("#entry-quote")).to_be_visible()
            quote = page.locator("#entry-quote").inner_text()
            page.locator("[data-entry-quote]").click()
            assert page.locator("#entry-quote").inner_text() != quote
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
            page.screenshot(
                path=str(ART / "revision6-entry-mobile.png"), full_page=True
            )
            page.get_by_role("button", name="Войти как Александра").click()
            page.wait_for_function("()=>state.user&&!busy")
            expect(page.locator(".home-tree-link")).to_be_visible()
            expect(
                page.get_by_role("button", name="Моё дерево", exact=True)
            ).to_have_count(0)
            expect(page.locator(".home-trend")).to_have_count(0)
            expect(page.locator(".home-counter")).to_be_visible()
            expect(page.locator(".home-season")).to_be_visible()
            for width in (320, 390, 430):
                page.set_viewport_size({"width": width, "height": 1000})
                boxes = page.locator(".home-actions .quick-card").evaluate_all(
                    "els=>els.map(el=>{const r=el.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y}})"
                )
                grid = page.locator(".home-actions").bounding_box()
                assert (
                    abs(
                        (boxes[-1]["x"] + boxes[-2]["x"]) / 2
                        - (grid["x"] + grid["width"] / 2)
                    )
                    < 2
                ), (width, boxes)
                assert abs(boxes[-1]["y"] - boxes[-2]["y"]) < 1
            page.set_viewport_size({"width": 390, "height": 1000})
            page.locator(".home-counter [data-experience=streak-start]").click()
            expect(page.locator(".home-counter #streak-display")).to_be_visible()
            stamp = page.evaluate("pref().streak_start")
            first = page.locator("#streak-display").inner_text()
            page.wait_for_timeout(1200)
            assert page.locator("#streak-display").inner_text() != first
            page.locator("#navigation [data-page=move]").click()
            expect(page.locator(".care-tree")).to_have_count(0)
            expect(page.locator("#weekly-activity")).to_be_visible()
            page.locator("#navigation [data-page=help]").click()
            page.locator("[data-group=help][data-key=streak]").click()
            expect(page.locator("#streak-display")).to_be_visible()
            assert page.evaluate("pref().streak_start") == stamp
            page.locator(".app-brand").click()
            expect(page.locator(".home-counter #streak-display")).to_be_visible()
            expect(page.locator("#nav-scroll-next")).to_be_enabled()
            current = page.url
            page.locator("#nav-scroll-next").click()
            page.wait_for_function(
                "()=>document.querySelector('#navigation').scrollLeft>10"
            )
            expect(page.locator("#nav-scroll-prev")).to_be_enabled()
            assert page.url == current
            page.locator("#nav-scroll-prev").click()
            page.wait_for_function(
                "()=>document.querySelector('#navigation').scrollLeft<2"
            )
            page.evaluate("scrollTo(0,0)")
            page.screenshot(path=str(ART / "revision6-home-mobile.png"), full_page=True)
            page.set_viewport_size({"width": 1440, "height": 1000})
            page.screenshot(
                path=str(ART / "revision6-home-desktop.png"), full_page=True
            )

            doctorContext = browser.new_context(
                viewport={"width": 1440, "height": 1000},
                reduced_motion="reduce",
                timezone_id="Europe/Moscow",
            )
            auth = doctorContext.request.post(
                url + "/api/auth/login",
                data={"username": "doctor", "password": "compass-demo"},
            ).json()
            for body in ("Уведомление для проверки чтения", "Второе уведомление"):
                response = doctorContext.request.post(
                    url + "/api/patients/2/messages",
                    data={"body": body},
                    headers={"X-CSRF-Token": auth["csrf"]},
                )
                assert response.ok
            page.wait_for_function("()=>!pollBusy")
            page.evaluate("()=>pollNotifications(true)")
            page.locator("#notifications-button").click()
            expect(page.locator(".notification-item.unread")).to_have_count(2)
            before = int(page.locator("#notification-count").inner_text())
            location = page.url
            pending = []
            page.route("**/api/notifications/read", lambda route: pending.append(route))
            item = page.locator(".notification-item.unread").first
            ident = item.get_attribute("data-id")
            item.click()
            expect(
                page.locator(f'.notification-item[data-id="{ident}"]')
            ).not_to_have_class("notification-item unread")
            expect(page.locator("#notification-count")).to_have_text(str(before - 1))
            assert page.url == location and len(pending) == 1
            expect(page.locator("#notifications-panel")).to_be_visible()
            page.wait_for_function("()=>!pollBusy")
            page.evaluate("()=>pollNotifications(true)")
            expect(
                page.locator(
                    f'.notification-item[data-id="{ident}"] .notification-state'
                )
            ).to_have_text("Прочитано")
            with page.expect_response("**/api/notifications/read") as read:
                pending[0].continue_()
            assert read.value.ok
            result = context.request.get(url + "/api/notifications").json()
            assert next(n for n in result["items"] if n["id"] == int(ident))["read_at"]
            page.unroute("**/api/notifications/read")
            page.route(
                "**/api/notifications/read",
                lambda route: route.fulfill(
                    status=503, json={"error": "Тестовый отказ сохранения"}
                ),
            )
            other = page.locator(".notification-item.unread").first
            otherId = other.get_attribute("data-id")
            other.click()
            expect(page.locator("#toast")).to_contain_text("Тестовый отказ")
            expect(
                page.locator(f'.notification-item[data-id="{otherId}"]')
            ).to_have_class("notification-item unread")
            expect(page.locator("#notification-count")).to_have_text(str(before - 1))
            page.unroute("**/api/notifications/read")
            page.locator(f'.notification-item[data-id="{otherId}"]').click()
            expect(page.locator(".notification-item.unread")).to_have_count(0)
            expect(page.locator("#toast")).not_to_be_visible(timeout=18000)
            page.set_viewport_size({"width": 390, "height": 1000})
            page.screenshot(path=str(ART / "revision6-notifications.png"))
            page.locator("#close-notifications").click()

            doc = doctorContext.new_page()
            doc.on("pageerror", lambda e: errors.append(str(e)))
            doc.goto(url)
            doc.wait_for_function("()=>state.user&&!busy")

            def patients():
                doc.locator("#navigation [data-page=patients]").click()
                expect(doc.locator("#patient-cards")).to_be_visible()

            def card():
                doc.locator('[data-action=patient][data-id="2"]').first.click()
                expect(doc.locator(".tabs [data-tab=plan]")).to_be_visible()
                expect(
                    doc.get_by_role("heading", name="Александра Морозова", exact=True)
                ).to_be_visible()

            def home():
                expect(
                    doc.get_by_role("heading", name="Добрый день, Анна", exact=True)
                ).to_be_visible()

            patients()
            card()
            expect(doc.locator(".page-back")).to_be_visible()
            assert doc.locator(".page-back").bounding_box()["height"] >= 44
            doc.get_by_role("button", name="Все пациенты", exact=True).click()
            expect(doc.locator("#patient-cards")).to_be_visible()
            doc.locator(".page-back").click()
            home()
            patients()
            card()
            doc.get_by_role("button", name="Все пациенты", exact=True).click()
            expect(doc.locator("#patient-cards")).to_be_visible()
            doc.go_back()
            home()
            doc.go_forward()
            expect(doc.locator("#patient-cards")).to_be_visible()
            doc.go_back()
            home()
            card()
            doc.get_by_role("button", name="Все пациенты", exact=True).click()
            expect(doc.locator("#patient-cards")).to_be_visible()
            doc.locator(".page-back").click()
            home()
            for width in (320, 390, 768, 1024, 1440):
                page.set_viewport_size({"width": width, "height": 1000})
                assert page.evaluate(
                    "document.documentElement.scrollWidth<=innerWidth"
                ), (width, "home")
                patients()
                doc.set_viewport_size({"width": width, "height": 1000})
                assert doc.evaluate(
                    "document.documentElement.scrollWidth<=innerWidth"
                ), (width, "patients")
                doc.locator(".page-back").click()
                home()
            assert not errors, errors
            assert not csp, csp
            browser.close()
            print(
                "PASS: entry tree/quotes, home-only tree, centered mobile actions, shared live counter and seasonal card, navigation arrows, immediate notification read/poll-race/rollback without routing, real Back/Forward and parent navigation, 5 widths"
            )
    finally:
        server.terminate()
        server.wait(timeout=10)
