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
            page.get_by_role("button", name="Войти как Александра").click()
            expect(page.locator(".patient-dashboard")).to_be_visible()
            page.locator(".home-tree-link").click()
            page.locator(".earned-tree .tree-touch").click()
            page.evaluate("()=>flowerQueue")
            page.locator("#navigation [data-page=move]").click()
            expect(page.locator(".simple-tree")).to_have_count(0)
            assert page.evaluate("state.wellbeing.tree_flowers.length") == 1
            form = page.locator(".activity-plan-form[data-key=walk]")
            form.get_by_role("button", name="В календарь").click()
            page.locator(".planned-exercise").get_by_role(
                "button", name="Выполнено", exact=True
            ).click()
            expect(page.locator(".planned-exercise")).to_contain_text("✓ Выполнено")
            page.locator("#navigation [data-page=help]").click()
            panic = page.locator(".emotion-accordion").first
            panic.locator("summary").click()
            initial = panic.locator(".emotion-current").inner_text()
            panic.get_by_role("button", name="Дальше").click()
            assert panic.locator(".emotion-current").inner_text() != initial
            page.locator("[data-ext=sub][data-group=help][data-key=calm]").click()
            expect(page.locator(".practice-accordion")).to_have_count(6)
            page.locator("[data-ext=sub][data-group=help][data-key=streak]").click()
            page.get_by_role("button", name="Начать отсчёт").click()
            expect(page.locator("#streak-display")).to_be_visible()
            page.locator("[data-ext=sub][data-group=help][data-key=plan]").click()
            expect(page.locator(".safety-plan-steps li")).to_have_count(6)
            page.locator("[data-ext=sub][data-group=help][data-key=sos]").click()
            expect(page.locator(".hold-sos:visible")).to_have_count(1)
            sos = page.locator(".sos-large")
            sos.scroll_into_view_if_needed()
            box = sos.bounding_box()
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            before_events = page.evaluate("state.workspace.events.length")
            page.mouse.down()
            page.wait_for_timeout(300)
            page.mouse.up()
            assert page.evaluate("state.workspace.events.length") == before_events
            page.mouse.down()
            page.wait_for_timeout(1700)
            page.mouse.up()
            expect(page.locator("#content")).to_contain_text("Запрос сохранён")
            assert page.evaluate("state.workspace.events.length") == before_events + 1
            dc = browser.new_context(
                viewport={"width": 1440, "height": 1000}, reduced_motion="reduce"
            )
            doc = dc.new_page()
            doc.on("pageerror", lambda e: errors.append(str(e)))
            doc.goto(url)
            doc.get_by_role("button", name="Войти как врач").click()
            expect(doc.locator(".doctor-calendar-card")).to_be_visible()
            appointment = doc.evaluate(
                "state.appointments.find(a=>a.status==='booked')"
            )
            day = appointment["starts_at"][:10]
            doc.locator(f'.activity-day[data-day="{day}"]').click()
            expect(doc.locator(".calendar-appointment")).not_to_have_count(0)
            doc.screenshot(
                path=str(ART / "revisions-doctor-calendar.png"), full_page=True
            )
            doc.locator(".calendar-appointment").first.click()
            expect(doc.locator(".profile-banner")).to_contain_text("Наблюдается с")
            expect(doc.locator("#content")).to_contain_text(
                "Мне сейчас нужна поддержка"
            )
            doc.locator("#navigation [data-page=reference]").click()
            expect(doc.locator("#compatibility-form")).to_be_visible()
            doc.locator("#compatibility-form [type=submit]").click()
            expect(doc.locator("#compatibility-result")).to_contain_text(
                "Учебные ограничения не отмечены"
            )
            doc.locator("#compatibility-form [name=allergy]").check()
            expect(doc.locator("#compatibility-result")).to_contain_text(
                "Параметры изменены"
            )
            doc.locator("#compatibility-form [type=submit]").click()
            expect(doc.locator("#compatibility-result")).to_contain_text(
                "Назначать нельзя"
            )
            expect(doc.locator("#compatibility-result")).to_have_attribute(
                "data-level", "blocked"
            )
            doc.locator("#compatibility-form [name=allergy]").uncheck()
            doc.locator("#compatibility-form [name=contraindication]").check()
            doc.locator("#compatibility-form [name=cardio]").check()
            doc.locator("#compatibility-form [type=submit]").click()
            expect(doc.locator("#compatibility-result h2")).to_have_text(
                "Назначать нельзя"
            )
            expect(doc.locator("#compatibility-result")).to_contain_text(
                "Противопоказание"
            )
            expect(doc.locator("#compatibility-result")).to_contain_text(
                "Причины запрета"
            )
            expect(doc.locator("#compatibility-result")).to_contain_text(
                "Дополнительно проверить"
            )
            doc.locator("#compatibility-form [name=contraindication]").uncheck()
            expect(doc.locator("#compatibility-result")).to_have_attribute(
                "data-level", "unverified"
            )
            doc.locator("#compatibility-form [type=submit]").click()
            expect(doc.locator("#compatibility-result")).to_have_attribute(
                "data-level", "caution"
            )
            doc.locator("#compatibility-form [name=cardio]").uncheck()
            doc.locator("#compatibility-form [name=other]").select_option("demo-gamma")
            doc.locator("#compatibility-form [type=submit]").click()
            expect(doc.locator("#compatibility-result")).to_contain_text(
                "несовместимое сочетание"
            )
            doc.locator("#compatibility-form [name=choice]").select_option("demo-beta")
            doc.locator("#compatibility-form [type=submit]").click()
            expect(doc.locator("#compatibility-result")).to_contain_text(
                "В синтетической карточке указана несовместимость"
            )
            doc.locator("#compatibility-patient").select_option("3")
            expect(doc.locator("#compatibility-profile")).to_contain_text("Михаил")
            expect(doc.locator("#compatibility-form [name=age]")).to_have_value("37")
            doc.locator("#compatibility-form [name=other]").select_option("demo-gamma")
            doc.locator("#compatibility-form [type=submit]").click()
            expect(doc.locator("#compatibility-result")).to_contain_text(
                "Нужна дополнительная проверка"
            )
            doc.locator("#compatibility-form [name=choice]").select_option("aviandr")
            doc.locator("#compatibility-form [type=submit]").click()
            doc.evaluate("scrollTo(0,0)")
            doc.screenshot(path=str(ART / "revisions-calculator.png"), full_page=True)
            rc = browser.new_context()
            rel = rc.new_page()
            rel.goto(url)
            rel.get_by_role("button", name="Войти как близкий").click()
            expect(rel.get_by_role("heading", name="Запрос поддержки")).to_be_visible()
            expect(rel.locator("#navigation")).to_contain_text("Полезные контакты")
            for width in (320, 390, 768, 1440):
                page.set_viewport_size({"width": width, "height": 900})
                for name in (
                    "overview",
                    "diary",
                    "move",
                    "learn",
                    "help",
                    "messages",
                    "schedule",
                    "settings",
                ):
                    page.evaluate("name=>navigate(name)", name)
                    expect(page.locator(".hold-sos:visible")).to_have_count(1)
                    if name != "overview":
                        expect(page.locator(".page-back")).to_be_visible()
                    assert page.evaluate(
                        "document.documentElement.scrollWidth<=innerWidth"
                    ), (width, name)
                doc.set_viewport_size({"width": width, "height": 900})
                assert doc.evaluate(
                    "document.documentElement.scrollWidth<=innerWidth"
                ), (width, "calculator")
            page.evaluate("name=>navigate(name)", "overview")
            page.evaluate("name=>navigate(name)", "diary")
            page.locator(".page-back").click()
            expect(page.locator(".patient-dashboard")).to_be_visible()
            assert not errors, errors
            browser.close()
            print(
                "PASS: persistent tap-to-bloom tree, activity plans/calendar, inline crisis/practice accordions and readiness, grounding 5-4-3-2-1, exercise timer, live stopwatch, SOS hold/cancel and cross-role messages, doctor calendar, scenario calculator, matching navigation, Back and 4 viewport sizes"
            )
    finally:
        server.terminate()
        server.wait(timeout=10)
