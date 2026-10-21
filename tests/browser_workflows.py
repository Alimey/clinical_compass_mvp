"""Product workflow test. Temporary DB, independent sessions, no external keys."""

import os, socket, subprocess, tempfile, time, urllib.request, shutil
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
ART = Path(tempfile.gettempdir()) / "compass-artifacts"
ART.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory() as temp:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {
        **os.environ,
        "COMPASS_DB": str(Path(temp) / "browser.db"),
        "PORT": str(port),
        "COMPASS_DISABLE_WORKER": "1",
        "COMPASS_AI_API_KEY": "",
        "COMPASS_TELEGRAM_BOT_TOKEN": "",
    }
    python = (
        ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    )
    server = subprocess.Popen(
        [str(python), "app.py"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                with urllib.request.urlopen(url + "/api/health", timeout=1) as r:
                    assert r.status == 200
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
            dc = browser.new_context(
                viewport={"width": 1440, "height": 1000}, timezone_id="Europe/Moscow"
            )
            pc = browser.new_context(
                viewport={"width": 390, "height": 844},
                is_mobile=True,
                has_touch=True,
                timezone_id="Europe/Moscow",
            )
            doc = dc.new_page()
            pat = pc.new_page()
            errors = []
            for page in (doc, pat):
                page.on("pageerror", lambda error: errors.append(str(error)))

            def signin(page, username):
                page.goto(url)
                page.locator("#username").fill(username)
                page.locator("#password").fill("compass-demo")
                page.locator("#login-form").get_by_role(
                    "button", name="Войти", exact=True
                ).click()

            def nav(page, name):
                if name == "Ещё" and page.locator("#more-button").is_visible():
                    page.locator("#more-button").click()
                    return
                page.locator("#navigation").get_by_role(
                    "button", name=name, exact=True
                ).click()

            def tab(name):
                doc.locator("#content .tabs").get_by_role(
                    "button", name=name, exact=True
                ).click()

            signin(doc, "doctor")
            expect(doc.get_by_role("heading", name="Добрый день, Анна")).to_be_visible()
            expect(doc.locator(".appointment-tile")).to_have_count(2)
            doc.screenshot(path=str(ART / "overview-v3.png"), full_page=True)
            nav(doc, "Ещё")
            doc.get_by_role("button", name="Конструктор опросов", exact=True).click()
            form = doc.locator("#template-form")
            form.locator("[name=title]").fill("Перед встречей E2E")
            form.locator("[name=description]").fill("Синтетический опрос")
            doc.locator(".question-label").nth(0).fill("Как прошёл день?")
            doc.locator(".question-label").nth(1).fill("Что обсудим?")
            form.get_by_role("button", name="Сохранить шаблон").click()
            expect(doc.locator("#copy-template")).to_contain_text("Перед встречей E2E")
            nav(doc, "Пациенты")
            doc.locator(".patient-card").filter(has_text="Александра").get_by_role(
                "button", name="Открыть карточку"
            ).click()
            tab("Опросы")
            form = doc.locator("#assign-survey-form")
            form.locator("[name=template_id]").select_option(label="Перед встречей E2E")
            form.locator("[name=due_at]").fill(
                (datetime.now(ZoneInfo("Europe/Moscow")) + timedelta(hours=3)).strftime(
                    "%Y-%m-%dT%H:%M"
                )
            )
            form.locator("[name=repeat_days]").select_option("1")
            form.get_by_role("button", name="Назначить пациенту").click()
            expect(
                doc.locator(".survey-card").filter(has_text="Перед встречей E2E")
            ).to_have_count(1)
            signin(pat, "+7 (000) 000-00-02")
            expect(
                pat.get_by_role("heading", name="Здравствуйте, Александра")
            ).to_be_visible()
            expect(pat.locator(".appointment-tile")).to_have_count(1)
            pat.screenshot(path=str(ART / "home-v3-mobile.png"), full_page=True)
            pat.get_by_role("button", name="Назначенные опросы", exact=False).click()
            pat.locator(".survey-card").filter(
                has_text="Перед встречей E2E"
            ).get_by_role("button", name="Пройти опрос").click()
            pat.locator("#survey-q-1").select_option("6")
            pat.locator("#survey-q-2").fill("Вымышленный ответ E2E")
            pat.get_by_role("button", name="Отправить ответы", exact=True).click()
            expect(
                pat.locator(".survey-card")
                .filter(has_text="Завершён")
                .filter(has_text="Перед встречей E2E")
            ).to_have_count(1)
            tab("Опросы")
            expect(doc.locator("#content")).to_contain_text("Вымышленный ответ E2E")
            tab("Карточка")
            expect(doc.locator(".profile-measures")).to_contain_text("168")
            with doc.expect_download() as download:
                doc.get_by_role("link", name="Скачать результат").first.click()
            assert download.value.suggested_filename.startswith("demo-lab-")
            doc.get_by_text("Добавить отчёт о посещении", exact=True).click()
            form = doc.locator("#encounter-form")
            for name, value in [
                ("title", "Встреча E2E"),
                ("summary", "Обсудили синтетический дневник"),
                ("plan", "Продолжить учебное наблюдение"),
            ]:
                form.locator(f"[name={name}]").fill(value)
            form.get_by_role("button", name="Сохранить отчёт").click()
            expect(doc.locator("#content")).to_contain_text("Встреча E2E")
            tab("План и варианты")
            doc.get_by_role("button", name="Управлять назначениями").click()
            form = doc.locator("#prescription-form")
            today = doc.locator("#medication-day").input_value()
            for name, value in [
                ("time1", "00:00"),
                ("time2", ""),
                ("ends_on", today),
                ("note", "Таблетница E2E · вымышленное назначение"),
            ]:
                form.locator(f"[name={name}]").fill(value)
            form.get_by_role(
                "button", name="Подтвердить назначение", exact=True
            ).click()
            expect(
                doc.locator(".card").filter(has_text="Таблетница E2E")
            ).to_have_count(1)
            nav(pat, "Ещё")
            pat.get_by_role("button", name="Таблетница", exact=True).click()
            dose = pat.locator(".card").filter(has_text="Таблетница E2E")
            dose.get_by_role("button", name="Принято", exact=True).click()
            expect(dose).to_contain_text("Отмечено: принято")
            nav(pat, "Ещё")
            pat.get_by_role("button", name="Расписание", exact=True).click()
            slot = pat.locator("#booking-slot option").nth(1).get_attribute("value")
            pat.locator("#booking-slot").select_option(slot)
            with pat.expect_response(
                lambda r: r.request.method == "POST"
                and r.url.endswith("/api/appointments")
            ) as booking:
                pat.get_by_role("button", name="Подтвердить запись", exact=True).click()
            ident = booking.value.json()["id"]
            cancel = pat.locator(f'[data-care=appointment-cancel][data-id="{ident}"]')
            expect(cancel).to_be_visible()
            cancel.click()
            expect(pat.locator("#content")).to_contain_text("Отменена")
            nav(pat, "Ещё")
            form = pat.locator("#offline-save-form")
            form.locator("[name=pin]").fill("123456")
            form.locator("[name=confirm]").fill("123456")
            form.get_by_role("button", name="Сохранить офлайн-копию").click()
            expect(pat.locator("#toast")).to_contain_text(
                "Зашифрованная копия сохранена"
            )
            meta = pat.evaluate(
                """async()=>{const d=await new Promise(r=>{const q=indexedDB.open('compass-offline-v1');q.onsuccess=()=>r(q.result)});return new Promise(r=>{const q=d.transaction('vault').objectStore('vault').get('patient');q.onsuccess=()=>{const v=q.result;r({keys:Object.keys(v),encrypted:v.ciphertext instanceof ArrayBuffer});d.close();}})}"""
            )
            assert meta["encrypted"] and set(meta["keys"]) == {
                "salt",
                "iv",
                "ciphertext",
            }, meta
            pc.set_offline(True)
            pat.reload()
            expect(pat.locator("#offline-unlock-form")).to_be_visible()
            form = pat.locator("#offline-unlock-form")
            form.locator("[name=pin]").fill("000000")
            form.get_by_role("button", name="Открыть офлайн-копию").click()
            expect(pat.locator("#toast")).to_contain_text("Неверный PIN")
            form.locator("[name=pin]").fill("123456")
            form.get_by_role("button", name="Открыть офлайн-копию").click()
            expect(pat.locator(".offline-layout")).to_contain_text("Встреча E2E")
            expect(pat.locator(".offline-layout")).to_contain_text("Таблетница E2E")
            assert pat.locator("#message-form").count() == 0
            pc.set_offline(False)
            pat.get_by_role("button", name="Войти онлайн", exact=True).click()
            expect(
                pat.get_by_role("heading", name="Здравствуйте, Александра")
            ).to_be_visible()
            pat.get_by_role("button", name="Выйти", exact=True).click()
            expect(pat.locator("#login-form")).to_be_visible()
            pat.reload()
            expect(pat.locator("#offline-unlock-form")).to_have_count(0)
            nav(doc, "Ещё")
            doc.get_by_role("button", name="Создать приглашение", exact=True).click()
            invite = doc.locator(".invite-url").input_value()
            nc = browser.new_context(viewport={"width": 390, "height": 844})
            new = nc.new_page()
            new.on("pageerror", lambda error: errors.append(str(error)))
            new.goto(invite)
            expect(new.locator("#intake-form")).to_be_visible()
            form = new.locator("#intake-form")
            for name, value in [
                ("name", "Новая Анкета"),
                ("age", "32"),
                ("height", "170"),
                ("weight", "65"),
                ("phone", "+70000000111"),
                ("context", "Синтетический профиль"),
                ("password", "new-patient-demo"),
                ("confirm", "new-patient-demo"),
            ]:
                form.locator(f"[name={name}]").fill(value)
            form.get_by_role("button", name="Создать карточку и войти").click()
            expect(
                new.get_by_role("heading", name="Здравствуйте, Новая")
            ).to_be_visible(timeout=10000)
            nav(doc, "Пациенты")
            expect(doc.locator(".patient-card")).to_have_count(3)
            doc.locator(".patient-card").filter(has_text="Новая Анкета").get_by_role(
                "button", name="Открыть карточку"
            ).click()
            tab("ИИ-помощник")
            doc.locator("#assistant-form [name=question]").fill(
                "Сводка синтетического профиля"
            )
            doc.get_by_role("button", name="Спросить ИИ").click()
            expect(doc.locator("#toast")).to_contain_text("ИИ не подключён")
            for width in (320, 390, 430, 1280):
                doc.set_viewport_size({"width": width, "height": 844})
                assert doc.evaluate(
                    "document.documentElement.scrollWidth<=innerWidth"
                ), width
                nav(doc, "Ещё")
                doc.get_by_role(
                    "button", name="Конструктор опросов", exact=True
                ).click()
                assert doc.evaluate(
                    "document.documentElement.scrollWidth<=innerWidth"
                ), ("builder", width)
            assert not errors, errors
            nc.close()
            dc.close()
            pc.close()
            browser.close()
            print(
                "PASS: phone login, appointment ribbon, questionnaires, visit reports/downloads, tablet tracking, booking/cancellation, PIN-encrypted offline view and purge, automatic registration, explicit AI status, mobile forms"
            )
    finally:
        server.terminate()
        server.wait(timeout=10)
