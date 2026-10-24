"""Geometry and interaction checks for real desktop, tablet and phone layouts."""

import os
from pathlib import Path
import shutil
import socket
import sqlite3
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
        # The intake checks should also work before the first morning dose.
        with sqlite3.connect(env["COMPASS_DB"]) as db:
            db.execute(
                "UPDATE prescriptions SET times_json=? WHERE patient_id=2",
                ('["00:00", "20:00"]',),
            )
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
            expect(page.locator(".tree-motion-toggle")).to_have_count(0)
            expect(page.locator("#navigation [data-page=messages]")).to_have_text(
                "Врач"
            )
            expect(page.locator("#navigation [data-page=schedule]")).to_have_text(
                "Консультации"
            )
            expect(page.locator("#workspace-tools [data-page]")).to_have_count(1)
            assert (
                page.locator("#workspace-tools [data-page]").get_attribute("data-page")
                == "settings"
            )
            assert page.locator(".home-actions [data-page]").evaluate_all(
                "els=>els.map(e=>e.dataset.page).sort()"
            ) == page.locator(
                "#navigation [data-page],#workspace-tools [data-page]"
            ).evaluate_all(
                "els=>els.map(e=>e.dataset.page).sort()"
            )
            page.evaluate(
                """()=>{window.originalFetch=window.fetch;window.treeSaves=[];window.fetch=(url,...args)=>String(url).endsWith('/tree')?new Promise((resolve,reject)=>window.treeSaves.push(()=>window.originalFetch(url,...args).then(resolve,reject))):window.originalFetch(url,...args)}"""
            )
            page.evaluate(
                "window.beforeTree=document.querySelector('.home-tree-link svg')"
            )
            tree = page.locator(".home-tree-link")
            # The click now opens a detail page; exercise the animation helper
            # separately here. Real click navigation is covered by revision8.
            page.evaluate("state.wellbeing.tree_rewards=[];syncTreeFlowers()")

            def tap_tree(x, y):
                tree.evaluate(
                    "(el,p)=>{const r=el.getBoundingClientRect();plantFlower({detail:1,clientX:r.left+p.x,clientY:r.top+p.y},el)}",
                    {"x": x, "y": y},
                )

            page.evaluate(
                "window.originalRandom=Math.random;window.testFlowerSizes=[.05,.95,.45];Math.random=()=>window.testFlowerSizes.shift()??.5"
            )
            tap_tree(110, 90)
            expect(tree.locator(".tree-flowers circle")).to_have_count(2)
            assert (
                tree.locator(".tree-tap").evaluate("el=>el.getAnimations().length") == 0
            )
            page.evaluate(
                "window.firstFlower=document.querySelector('.tree-flowers [data-flower]')"
            )
            page.emulate_media(reduced_motion="no-preference")
            tap_tree(140, 110)
            expect(tree.locator(".tree-flowers circle")).to_have_count(4)
            page.evaluate(
                "window.previousTap=document.querySelector('.tree-tap').getAnimations()[0];window.windAnimation=document.querySelector('.tree-crown').getAnimations()[0]"
            )
            tap_tree(120, 100)
            expect(tree.locator(".tree-flowers circle")).to_have_count(6)
            assert page.evaluate("window.previousTap.playState") == "idle"
            assert (
                tree.locator(".tree-tap").evaluate("el=>el.getAnimations().length") == 1
            )
            assert page.evaluate(
                "window.windAnimation===document.querySelector('.tree-crown').getAnimations()[0]"
            )
            assert page.evaluate(
                "window.firstFlower===document.querySelector('.tree-flowers [data-flower]')"
            )
            page.evaluate(
                "Math.random=window.originalRandom;window.lastFlower=document.querySelector('.tree-flowers [data-flower]:last-child');document.querySelector('.tree-tap').getAnimations()[0].currentTime=160"
            )
            assert (
                tree.locator(".tree-tap").evaluate(
                    "el=>Math.abs(new DOMMatrix(getComputedStyle(el).transform).b)"
                )
                > 0.01
            )
            assert (
                page.locator(
                    ".tree-flowers [data-flower]:last-child .flower-bloom"
                ).evaluate("el=>el.getAnimations().length")
                == 1
            )
            radii = tree.locator(".flower-bloom > circle:first-child").evaluate_all(
                "els=>els.map(el=>Number(el.getAttribute('r')))"
            )
            assert len(set(radii)) == 3 and all(4.5 <= r <= 9 for r in radii), radii
            assert page.url.endswith("#page=overview")
            page.evaluate(
                "()=>{window.fetch=window.originalFetch;window.treeSaves.forEach(release=>release())}"
            )
            page.evaluate("()=>flowerQueue")
            assert page.evaluate("state.wellbeing.tree_flowers.length") == 3
            assert page.evaluate(
                "window.lastFlower===document.querySelector('.tree-flowers [data-flower]:last-child')"
            )
            assert (
                tree.locator(".flower-bloom > circle:first-child").evaluate_all(
                    "els=>els.map(el=>Number(el.getAttribute('r')))"
                )
                == radii
            )
            page.emulate_media(reduced_motion="reduce")
            assert (
                tree.locator(".tree-tap").evaluate("el=>el.getAnimations().length") == 0
            )
            assert page.evaluate(
                "window.beforeTree===document.querySelector('.home-tree-link svg')"
            )
            page.locator("#navigation [data-page=move]").click()
            expect(page.locator(".simple-tree")).to_have_count(0)
            expect(page.locator("#tree-bloom-status")).to_have_count(0)
            expect(page.locator(".care-tree")).to_have_count(0)
            page.locator(".activity-plan-form[data-key=walk] button").click()
            expect(page.locator(".weekly-activity progress")).to_have_attribute(
                "max", "1200"
            )
            page.locator(".planned-exercise").get_by_role(
                "button", name="Выполнено", exact=True
            ).click()
            expect(page.locator(".weekly-activity progress")).to_have_attribute(
                "value", "1200"
            )
            page.locator("#navigation [data-page=diary]").click()
            expect(page.locator("#daily-calendar")).to_be_visible()
            expect(page.locator("#report-form")).to_be_visible()
            expect(page.locator("[data-action=diary]")).to_have_count(0)
            expect(page.locator("#content .page-heading")).to_have_count(0)
            page.locator("#note").fill("Запись revision2")
            today = page.evaluate("care().today")
            yesterday = page.evaluate("dayOffset(care().today,-1)")
            page.locator(
                f'[data-experience=calendar-day][data-group=diary][data-day="{yesterday}"]'
            ).click()
            expect(page.locator("#note")).to_have_value("Запись revision2")
            page.get_by_role("button", name="Сохранить самоотчёт", exact=False).click()
            expect(page.locator("#report-history")).to_contain_text("Запись revision2")
            page.set_viewport_size({"width": 390, "height": 844})
            page.evaluate("scrollTo(0,0)")
            expect(page.locator("#toast")).to_be_hidden(timeout=15000)
            page.screenshot(path=str(ART / "revision2-diary.png"))
            page.locator("[data-ext=sub][data-group=diary][data-key=charts]").click()
            expect(page.locator("#graph-insight")).to_contain_text(
                "ИИ ещё не подключён"
            )
            expect(page.locator(".patient-page > .card")).to_have_count(5)
            expect(
                page.get_by_role(
                    "img", name="Тревога, качество сна и энергия от 0 до 10"
                )
            ).to_be_visible()
            expect(page.locator(".complaint-day")).to_have_count(42)
            calls = []

            def summary(route):
                calls.append(route.request.url)
                route.fulfill(
                    json={
                        "status": "ready",
                        "items": [
                            "Проверка интерфейса: данные переданы модели.",
                            "<script>window.bad=true</script>",
                        ],
                        "created_at": "2026-10-23T12:00:00+00:00",
                    }
                )

            page.route("**/chart-summary", summary)
            page.evaluate("()=>{state.integrations.ai.configured=true;render()}")
            expect(page.locator("#graph-insight")).to_contain_text(
                "данные переданы модели"
            )
            assert len(calls) == 1 and page.evaluate("window.bad") is None
            page.locator("[data-ext=sub][data-group=diary][data-key=notes]").click()
            expect(page.locator(".entry-form")).to_have_count(2)
            assert "Дневник мыслей" not in page.locator("#content").inner_text()
            page.locator("[data-ext=sub][data-group=diary][data-key=charts]").click()
            expect(page.locator("#graph-insight")).to_contain_text(
                "данные переданы модели"
            )
            assert len(calls) == 1
            page.locator("[data-ext=sub][data-group=diary][data-key=meds]").click()
            expect(page.locator(".medication-schedule tbody tr")).to_have_count(14)
            expect(page.locator(".patient-page > .card")).to_have_count(1)
            dose = page.locator(".dose-check:not([disabled])").first
            ident = dose.get_attribute("data-id")
            day = dose.get_attribute("data-day")
            time_value = dose.get_attribute("data-time")
            dose.click()
            expect(
                page.locator(
                    f'.dose-check[data-id="{ident}"][data-day="{day}"][data-time="{time_value}"]'
                )
            ).to_have_attribute("aria-pressed", "true")
            page.evaluate("scrollTo(0,0)")
            pair = (
                page.locator(".medication-schedule tbody tr")
                .first.locator(".dose-check")
                .all()
            )
            assert abs(pair[0].bounding_box()["y"] - pair[1].bounding_box()["y"]) < 1
            expect(page.locator("#toast")).to_be_hidden(timeout=15000)
            page.screenshot(path=str(ART / "revision2-medications.png"))
            page.locator("#navigation [data-page=learn]").click()
            expect(page.locator(".school-videos .course-item")).to_have_count(5)
            page.locator(".school-videos summary").first.click()
            expect(page.locator(".video-placeholder").first).to_be_visible()
            assert "Понятно о повседневном" not in page.locator("#content").inner_text()
            expect(page.locator("#content .page-heading")).to_have_count(0)
            page.locator("#navigation [data-page=help]").click()
            panic = page.locator(".emotion-accordion").first
            panic.locator("summary").click()
            first = panic.locator(".emotion-current").inner_text()
            panic.get_by_role("button", name="Дальше").click()
            assert panic.locator(".emotion-current").inner_text() != first
            expect(panic.locator("ol")).to_have_count(0)
            page.locator("[data-ext=sub][data-group=help][data-key=calm]").click()
            expect(page.locator(".practice-accordion")).to_have_count(6)
            assert "Спокойная пауза" not in page.locator("#content").inner_text()
            page.emulate_media(reduced_motion="no-preference")
            page.evaluate("crypto.randomUUID=undefined")
            rhythm = page.locator("[data-practice=rhythm]")
            rhythm.locator("summary").click()
            rhythm.get_by_role("button", name="Да, начать").click()
            expect(page.locator("#breath-phase")).to_have_text("Вдох")
            assert (
                rhythm.locator(".breathing-orb").evaluate(
                    "el=>getComputedStyle(el).animationDuration"
                )
                == "12s"
            )
            offsets = rhythm.locator(".breathing-orb").evaluate(
                "el=>el.getAnimations()[0].effect.getKeyframes().map(k=>k.offset)"
            )
            assert abs(offsets[1] - 1 / 3) < 0.001 and offsets[2] == 0.5
            page.clock.install()
            page.clock.fast_forward(4100)
            expect(page.locator("#breath-phase")).to_have_text("Пауза")
            page.clock.fast_forward(2100)
            expect(page.locator("#breath-phase")).to_have_text("Выдох")
            page.clock.fast_forward(55000)
            expect(rhythm.locator(".practice-success")).to_contain_text(
                "счётчик обновлён"
            )
            expect(page.locator("#practice-count")).to_have_text("2")
            # One planned walk and one completed breathing session.
            assert page.evaluate("state.wellbeing.practice_count") == 2
            ground = page.locator("[data-practice=grounding]")
            ground.locator("summary").click()
            ground.get_by_role("button", name="Да, начать").click()
            for count in range(5):
                expect(ground.locator(".grounding-steps li:visible")).to_have_count(1)
                ground.get_by_role("button", name="Далее").click()
            expect(ground.locator(".practice-success")).to_contain_text("Вы молодец")
            expect(page.locator("#practice-count")).to_have_text("3")
            exercise = page.locator("[data-practice=desk]")
            exercise.locator("summary").click()
            exercise.get_by_role("button", name="Да, начать").click()
            for _ in range(3):
                exercise.get_by_role("button", name="Дальше").click()
            page.clock.fast_forward(61000)
            expect(exercise.locator(".practice-success")).to_contain_text(
                "счётчик обновлён"
            )
            expect(page.locator("#practice-count")).to_have_text("4")
            page.clock.fast_forward(3000)
            assert page.evaluate("state.wellbeing.practice_count") == 4
            assert (
                page.evaluate(
                    "()=>{const node=document.createElement('div');node.innerHTML=weeklyActivity();return node.querySelector('progress').getAttribute('value')}"
                )
                == "1380"
            )
            page.clock.resume()
            page.set_viewport_size({"width": 1440, "height": 1000})
            page.locator("[data-ext=sub][data-group=help][data-key=plan]").click()
            cards = page.locator(".patient-page > .card").all()
            for before, after in zip(cards, cards[1:]):
                a, b = before.bounding_box(), after.bounding_box()
                assert b["y"] >= a["y"] + a["height"], (a, b)
            page.evaluate("scrollTo(0,0)")
            page.screenshot(path=str(ART / "revision2-safety-plan.png"), full_page=True)
            page.locator("[data-ext=sub][data-group=help][data-key=sos]").click()
            cards = page.locator(".patient-page > .card").all()
            for before, after in zip(cards, cards[1:]):
                a, b = before.bounding_box(), after.bounding_box()
                assert b["y"] >= a["y"] + a["height"]
            page.locator("#more-button").click()
            expect(page.locator(".patient-page > .card")).to_have_count(1)
            expect(page.locator(".patient-page > .card")).to_contain_text(
                "Уведомления и установка PWA"
            )
            assert "Сценарий" not in page.locator("#content").inner_text()
            tabs = page.locator(".patient-page > .section-tabs").bounding_box()
            panel = page.locator(".patient-page > .card").bounding_box()
            assert (
                panel["y"] >= tabs["y"] + tabs["height"]
                and abs(panel["x"] - tabs["x"]) < 2
            )
            page.evaluate("scrollTo(0,0)")
            page.screenshot(path=str(ART / "revision2-settings.png"), full_page=True)
            for width in (320, 390, 768, 1024, 1440):
                page.set_viewport_size({"width": width, "height": 900})
                for group, sections in (
                    ("diary", ("daily", "charts", "meds", "notes")),
                    ("learn", ("course", "articles", "books")),
                    ("help", ("now", "calm", "plan", "sos")),
                    ("doctor", ("chat", "mail", "ai")),
                    ("settings", ("general", "consents", "about")),
                ):
                    name = {"doctor": "messages"}.get(group, group)
                    page.evaluate("name=>navigate(name)", name)
                    for section in sections:
                        page.locator(
                            f'[data-ext=sub][data-group="{group}"][data-key="{section}"]'
                        ).click()
                        assert page.evaluate(
                            "document.documentElement.scrollWidth<=innerWidth"
                        ), (width, group, section)
                        expect(page.locator(".patient-page > .tabs")).to_have_count(1)
                        if group != "settings" or section != "about":
                            expect(
                                page.locator(".patient-page .page-heading")
                            ).to_have_count(0)
            assert not errors, errors
            browser.close()
            print(
                "PASS: instant positioned home flowers, tree removed from movement, uninterrupted tree animation, weekly activity, combined diary and draft retention, automatic AI UI states/cache, medication table/marks, school video placeholders, sequential crisis/grounding, synchronized 12s breathing, automatic exercise counts and congratulations, full-width Plan/SOS/settings, renamed navigation and 5 widths"
            )
    finally:
        server.terminate()
        server.wait(timeout=10)
