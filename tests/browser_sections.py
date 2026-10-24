"""Cross-role checks for every additional section of the supplied mockup."""

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
        "COMPASS_DB": str(Path(temp) / "test.db"),
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
                time.sleep(0.1)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                executable_path=os.environ.get("CHROMIUM_PATH")
                or shutil.which("chromium"),
                args=["--no-sandbox"],
            )
            errors = []

            def user(account):
                c = browser.new_context(
                    viewport={"width": 390, "height": 844},
                    reduced_motion="reduce",
                    timezone_id="Europe/Moscow",
                )
                c.add_init_script(
                    "window.cspViolations=[];addEventListener('securitypolicyviolation',event=>window.cspViolations.push(event.violatedDirective))"
                )
                page = c.new_page()
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.goto(url)
                page.locator("#username").fill(account)
                page.locator("#password").fill("compass-demo")
                page.locator("#login-form button").click()
                expect(page.locator("#app-shell")).to_be_visible()
                page.wait_for_function("() => !busy && state.user !== null")
                return page

            pat, doc, rel = user("patient-a"), user("doctor"), user("relative")

            def nav(page, name):
                page.evaluate("p=>navigate(p)", name)
                page.wait_for_function("() => !busy")

            def tab(page, group, key):
                page.locator(
                    f'[data-ext=sub][data-group="{group}"][data-key="{key}"]'
                ).click()

            def submit(page, form):
                page.locator(form).locator("button[type=submit]").click()
                page.wait_for_function("() => !busy")

            # Revision 3: all main destinations precede the settings separator.
            doc.set_viewport_size({"width": 1440, "height": 1000})
            nav(doc, "overview")
            expect(doc.locator("#navigation [data-page]").first).to_have_text("Главное")
            expect(doc.locator("#navigation [data-page=schedule]")).to_have_text(
                "Мои встречи"
            )
            for page in (pat, doc, rel):
                expect(page.locator("#workspace-tools [data-page]")).to_have_count(1)
                expect(
                    page.locator("#workspace-tools [data-page=settings]")
                ).to_have_count(1)
                assert page.locator(
                    "#workspace-tools [data-page=settings] path"
                ).get_attribute("d") == pat.locator(
                    "#workspace-tools [data-page=settings] path"
                ).get_attribute(
                    "d"
                )
            assert doc.locator("#workspace-tools").evaluate(
                "el=>parseFloat(getComputedStyle(el).borderTopWidth)>0"
            )
            doc.screenshot(path=str(ART / "revision3-doctor-menu.png"), full_page=True)
            nav(doc, "schedule")
            expect(
                doc.get_by_role("heading", name="Записать на консультацию", exact=True)
            ).to_be_visible()
            expect(doc.locator("#booking-patient")).to_be_visible()
            nav(pat, "schedule")
            expect(
                pat.get_by_role(
                    "heading", name="Записаться на консультацию", exact=True
                )
            ).to_be_visible()
            expect(
                rel.get_by_role("link", name="Позвонить", exact=True)
            ).to_have_attribute("href", "tel:+70000000002")
            nav(rel, "learn")
            expect(rel.locator(".course-item")).to_have_count(4)
            for item in rel.locator(".course-item").all():
                item.locator("summary").click()
                expect(item.locator(".video-placeholder")).to_be_visible()
            expect(rel.locator("[data-ext=resource-read]")).to_have_count(0)
            rel.evaluate("scrollTo(0,0)")
            rel.screenshot(
                path=str(ART / "revision3-relative-videos.png"), full_page=True
            )

            nav(pat, "diary")
            tab(pat, "diary", "notes")
            f = pat.locator(".entry-form[data-kind=note]")
            f.locator("[name=text]").fill("private-browser-marker")
            submit(pat, ".entry-form[data-kind=note]")
            expect(pat.locator("#content")).to_contain_text("private-browser-marker")
            nav(pat, "learn")
            tab(pat, "learn", "thought")
            pat.locator("[name=situation]").fill("Синтетическая ситуация E2E")
            submit(pat, ".entry-form[data-kind=thought]")
            tab(pat, "learn", "course")
            pat.locator(".course-item").first.locator("summary").click()
            expect(pat.locator(".video-placeholder").first).to_be_visible()
            tab(pat, "learn", "articles")
            expect(pat.locator(".course-item")).to_have_count(6)
            tab(pat, "learn", "books")
            expect(pat.get_by_role("heading", name="Литература")).to_be_visible()
            nav(pat, "diary")
            tab(pat, "diary", "scales")
            pat.locator("[data-ext=assessment][data-key=gad7]").click()
            for i in range(7):
                pat.locator(f"#assessment-form [name=q{i}]").select_option("1")
            submit(pat, "#assessment-form")
            expect(pat.locator("#content")).to_contain_text(
                "Обсудите результат со специалистом"
            )
            nav(pat, "messages")
            tab(pat, "doctor", "mail")
            pat.locator("#letter-form [name=subject]").fill("Письмо E2E")
            pat.locator("#letter-form [name=body]").fill("Синтетический вопрос")
            submit(pat, "#letter-form")
            nav(doc, "letters")
            expect(doc.locator("#content")).to_contain_text("Письмо E2E")
            doc.locator(".letter-reply-form [name=body]").fill("Ответ E2E")
            submit(doc, ".letter-reply-form")
            nav(pat, "messages")
            expect(pat.locator("#content")).to_contain_text("Ответ E2E")
            nav(doc, "patients")
            doc.locator(".patient-card").filter(has_text="Александра").get_by_role(
                "button", name="Открыть карточку"
            ).click()
            expect(doc.locator("#content")).to_contain_text(
                "Синтетическая ситуация E2E"
            )
            assert "private-browser-marker" not in doc.locator("#content").inner_text()
            doc.locator("[data-action=tab][data-tab=scales]").click()
            expect(doc.locator("#content")).to_contain_text("Сумма: 7")
            doc.locator("[data-ext=assessment][data-key=hama]").click()
            for i in range(14):
                doc.locator(f"#assessment-form [name=q{i}]").select_option("1")
            submit(doc, "#assessment-form")
            expect(doc.locator("#content")).to_contain_text("Сумма: 14")
            doc.locator("[data-action=tab][data-tab=safetyplan]").click()
            for key in ("signs", "self", "distract", "people", "pros", "safe"):
                doc.locator(f"#safety-plan-form [name={key}]").fill("План E2E: " + key)
            submit(doc, "#safety-plan-form")
            doc.get_by_text("Предложить новое соглашение", exact=True).click()
            submit(doc, "#agreement-form")
            nav(pat, "help")
            tab(pat, "help", "plan")
            expect(pat.locator("#content")).to_contain_text("План E2E: signs")
            pat.get_by_role("button", name="Ознакомился(ась) с условиями").click()
            expect(pat.locator("#content")).to_contain_text("Пациент ознакомился")
            tab(pat, "help", "games")
            pat.locator('[data-game-select="bubbles"]').click()
            pat.get_by_role("button", name="Пузырёк 1", exact=True).click()
            expect(pat.locator("#bubble-count")).to_contain_text("1")
            expect(
                pat.get_by_role("button", name="Шарик в лунку", exact=True)
            ).to_have_count(0)
            tab(pat, "help", "calm")
            rhythm = pat.locator("[data-practice=rhythm]")
            rhythm.locator("summary").click()
            rhythm.get_by_role("button", name="Да, начать").click()
            expect(pat.locator("#breath-phase")).to_contain_text("Вдох")
            pat.get_by_role("button", name="Остановить", exact=True).click()
            tab(pat, "help", "streak")
            pat.get_by_role("button", name="Начать отсчёт").click()
            expect(pat.locator("#streak-display")).to_contain_text("0 дн.")
            tab(pat, "help", "sos")
            button = pat.locator("[data-ext=sos]:visible")
            button.scroll_into_view_if_needed()
            box = button.bounding_box()
            pat.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            pat.mouse.down()
            pat.wait_for_timeout(1700)
            pat.mouse.up()
            pat.wait_for_function("() => !busy")
            expect(pat.locator("#content")).to_contain_text("Запрос сохранён")
            rel.reload()
            expect(rel.locator("#content")).to_contain_text("Александра")
            expect(rel.get_by_role("heading", name="Запрос поддержки")).to_be_visible()
            rel.get_by_role("button", name="Отметить просмотренным").click()
            expect(rel.locator("#content")).to_contain_text("вы отметили просмотр")
            nav(pat, "consents")
            pat.locator("[data-pref=research]").check()
            pat.wait_for_function("() => !busy")
            pat.locator("[data-pref=wear]").check()
            pat.wait_for_function("() => !busy")
            pat.locator("[data-pref=emias]").check()
            pat.wait_for_function("() => !busy")
            nav(pat, "move")
            expect(pat.locator("#content")).to_contain_text(
                "Синтетический пример включён"
            )
            plan = pat.locator(".activity-plan-form[data-key=desk]")
            plan.get_by_role("button", name="В календарь").click()
            pat.locator(".planned-exercise").get_by_role(
                "button", name="Выполнено", exact=True
            ).click()
            expect(pat.locator(".planned-exercise")).to_contain_text("✓ Выполнено")
            nav(doc, "research")
            expect(doc.locator("tbody")).to_contain_text("PK-")
            with doc.expect_download() as download:
                doc.get_by_role("link", name="Скачать CSV").click()
            assert download.value.suggested_filename == "synthetic-research.csv"
            nav(doc, "reference")
            doc.locator("#compatibility-form [name=egfr]").fill("20")
            submit(doc, "#compatibility-form")
            expect(doc.locator("#compatibility-result")).to_contain_text(
                "Нужна дополнительная проверка"
            )
            tab(doc, "reference", "scales")
            # Check threshold transitions, invalid scores and pointer geometry.
            for key, maximum, examples in (
                (
                    "gad7",
                    21,
                    (
                        (0, "0–4"),
                        (4, "0–4"),
                        (5, "5–9"),
                        (9, "5–9"),
                        (10, "10–14"),
                        (14, "10–14"),
                        (15, "15–21"),
                        (21, "15–21"),
                    ),
                ),
                (
                    "phq9",
                    27,
                    (
                        (0, "0–4"),
                        (4, "0–4"),
                        (5, "5–9"),
                        (9, "5–9"),
                        (10, "10–14"),
                        (14, "10–14"),
                        (15, "15–19"),
                        (19, "15–19"),
                        (20, "20–27"),
                        (27, "20–27"),
                    ),
                ),
                (
                    "hama",
                    56,
                    (
                        (0, "0–17"),
                        (17, "0–17"),
                        (18, "18–24"),
                        (24, "18–24"),
                        (25, "25–30"),
                        (30, "25–30"),
                        (31, "31–56"),
                        (56, "31–56"),
                    ),
                ),
            ):
                card = doc.locator(f".scale-guide-card[data-scale={key}]")
                for score, band in examples:
                    card.locator("input").fill(str(score))
                    expect(card.get_by_role("meter")).to_have_attribute(
                        "aria-valuenow", str(score)
                    )
                    expect(card.locator(".scale-zone-current")).to_contain_text(band)
                    pointer = card.evaluate(
                        "el=>{const m=el.querySelector('.scale-zone-marker').getBoundingClientRect(),t=el.querySelector('.scale-zone-track').getBoundingClientRect();return {ratio:(m.x+m.width/2-t.x)/t.width,marker:{x:m.x,width:m.width},track:{x:t.x,width:t.width}}}"
                    )
                    assert abs(pointer["ratio"] - score / maximum) < 0.01, (
                        key,
                        score,
                        pointer,
                    )
                for invalid in ("", "-1", str(maximum + 1), "2.5"):
                    card.locator("input").fill(invalid)
                    expect(card.get_by_role("meter")).to_have_count(0)
                    expect(card.locator(".scale-zone-empty")).to_contain_text(
                        f"от 0 до {maximum}"
                    )
                card.locator("input").fill(
                    {"gad7": "11", "phq9": "8", "hama": "20"}[key]
                )
                card.locator("summary").click()
                expect(card.locator(".scale-zone-ranges li")).to_have_count(
                    5 if key == "phq9" else 4
                )
            expect(doc.locator("#toast")).to_be_hidden(timeout=10000)
            for width in (320, 390, 768, 1440):
                doc.set_viewport_size({"width": width, "height": 1000})
                assert doc.evaluate(
                    "document.documentElement.scrollWidth<=innerWidth"
                ), (width, "scale zones")
                if width in (390, 1440):
                    doc.evaluate("scrollTo(0,0)")
                    doc.screenshot(
                        path=str(ART / f"revision3-scales-{width}.png"), full_page=True
                    )
            for key in ("rules", "literature", "scales"):
                tab(doc, "reference", key)
                assert doc.locator("#content").inner_text()
            expect(doc.locator("[data-scale=phq9] input")).to_have_value("8")
            nav(doc, "news")
            doc.get_by_role("button", name="Мероприятия", exact=True).click()
            expect(doc.locator("#content article.card")).to_have_count(1)
            nav(doc, "forum")
            doc.get_by_text("Новая тема", exact=True).click()
            doc.locator("#forum-form [name=title]").fill("Тема E2E")
            doc.locator("#forum-form [name=body]").fill(
                "<script>window.pwned=true</script> Синтетический вопрос"
            )
            submit(doc, "#forum-form")
            doc.locator("#forum-reply-form [name=body]").fill("Обсуждение E2E")
            submit(doc, "#forum-reply-form")
            expect(doc.locator("#content")).to_contain_text("Обсуждение E2E")
            assert doc.evaluate("window.pwned") is None
            nav(pat, "consents")
            pat.locator("[data-pref=relative_sos]").uncheck()
            pat.wait_for_function("() => !busy")
            rel.reload()
            expect(rel.locator("#content")).to_contain_text("отозвал его")
            for width in (320, 390, 430, 1280):
                for page, sections in (
                    (
                        doc,
                        (
                            "overview",
                            "schedule",
                            "reference",
                            "news",
                            "forum",
                            "research",
                            "tour",
                        ),
                    ),
                    (pat, ("consents", "diary", "learn", "move", "help")),
                    (rel, ("overview", "learn", "contacts")),
                ):
                    page.set_viewport_size({"width": width, "height": 844})
                    for section in sections:
                        nav(page, section)
                        assert page.evaluate(
                            "document.documentElement.scrollWidth<=innerWidth"
                        ), (
                            width,
                            section,
                            page.evaluate(
                                "[...document.querySelectorAll('body *')].filter(el=>{const r=el.getBoundingClientRect();return r.width&&r.right>innerWidth+1}).slice(0,15).map(el=>[el.tagName,el.id,el.className.baseVal||el.className,Math.round(el.getBoundingClientRect().right)])"
                            ),
                        )
            doc.set_viewport_size({"width": 390, "height": 844})
            nav(doc, "forum")
            doc.locator("[data-ext=forum-back]").click()
            doc.screenshot(path=str(ART / "psicompas-forum.png"), full_page=True)
            rel.set_viewport_size({"width": 390, "height": 844})
            nav(rel, "learn")
            rel.screenshot(path=str(ART / "psicompas-relative.png"), full_page=True)
            assert not errors, errors
            for page in (pat, doc, rel):
                assert page.evaluate("window.cspViolations") == []
            browser.close()
            print(
                "PASS: all prototype sections, revision 3 doctor navigation/booking, shared settings gear, relative call/video placeholders, live scale zones and boundary/invalid values, 3 separate roles, notes/thoughts/privacy, GAD/PHQ/HAM forms, letters/replies, safety plan/agreement, SOS hold and relative revocation, games/breathing, exercises, consents/research CSV, calculator/news/forum, responsive layouts"
            )
    finally:
        server.terminate()
        server.wait(timeout=10)
