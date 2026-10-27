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
            browser = pw.chromium.launch(
                executable_path=os.environ.get("CHROMIUM_PATH")
                or shutil.which("chromium"),
                args=["--no-sandbox"],
            )
            doctor_context = browser.new_context(
                viewport={"width": 390, "height": 1000},
                reduced_motion="reduce",
                color_scheme="light",
            )
            page = doctor_context.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(url)
            theme = page.locator("#login-screen [data-theme-toggle]")
            expect(theme).to_be_visible()
            theme.click()
            expect(page.locator("html")).to_have_attribute("data-theme", "dark")
            page.reload()
            expect(page.locator("#entry-quote")).to_be_visible()
            expect(page.locator("html")).to_have_attribute("data-theme", "dark")
            page.locator("#login-screen [data-theme-toggle]").click()
            page.screenshot(
                path=str(ART / "revision7-entry-mobile.png"), full_page=True
            )
            for width in (320, 390, 768, 1024, 1440):
                page.set_viewport_size({"width": width, "height": 1000})
                assert page.locator(".entry-garden").bounding_box()["width"] >= 180
                assert page.evaluate(
                    "document.documentElement.scrollWidth<=innerWidth"
                ), width
            page.screenshot(
                path=str(ART / "revision7-entry-desktop.png"), full_page=True
            )
            page.locator("#login-screen [data-theme-toggle]").click()
            page.screenshot(path=str(ART / "revision7-entry-dark.png"), full_page=True)
            page.locator("[data-registration=open]").click()
            page.locator("[data-registration=doctor]").click()
            form = page.locator("#doctor-registration-form")
            form.locator("[name=name]").fill("Мария Тестовая")
            form.locator("[name=phone]").fill("+70000000002")
            form.locator("[name=profession]").fill("Психолог")
            form.locator("[name=password]").fill("new-test-password")
            form.locator("[name=confirm]").fill("different-password")
            form.locator("[type=submit]").click()
            expect(page.locator("#registration-error")).to_have_text(
                "Пароли не совпадают"
            )
            form.locator("[name=confirm]").fill("new-test-password")
            form.locator("[type=submit]").click()
            expect(page.locator("#registration-error")).to_contain_text(
                "уже зарегистрирован"
            )
            expect(form.locator("[name=name]")).to_have_value("Мария Тестовая")
            form.locator("[name=phone]").fill("+70000000981")
            form.locator("[type=submit]").click()
            expect(page.locator(".welcome-doctor")).to_be_visible()
            page.wait_for_function("()=>!busy")
            expect(page.locator("#theme-toggle")).to_have_attribute(
                "aria-label", "Включить светлую тему"
            )
            for route in (
                "patients",
                "settings",
                "reference",
                "news",
                "forum",
                "letters",
                "schedule",
                "overview",
            ):
                if route == "settings":
                    page.locator("#more-button").click()
                else:
                    page.locator(f'#navigation [data-page="{route}"]').click()
                try:
                    page.wait_for_function(
                        "p=>state.page===p&&document.querySelector('#content').dataset.view===p",
                        arg=route,
                        timeout=10000,
                    )
                except Exception:
                    print(
                        "FAILED ROUTE",
                        route,
                        page.evaluate(
                            "({page:state.page,view:document.querySelector('#content').dataset.view,toast:document.querySelector('#toast').textContent})"
                        ),
                        errors,
                        flush=True,
                    )
                    raise
                if route == "reference":
                    page.locator("#compatibility-form [type=submit]").click()
                    expect(page.locator("#compatibility-result")).to_contain_text(
                        "Учебные ограничения не отмечены"
                    )
            page.locator(".welcome-doctor [data-care=invite]").click()
            invite = page.locator(".invite-url")
            expect(invite).to_be_visible()
            invitation = invite.input_value()
            patient_context = browser.new_context(
                viewport={"width": 390, "height": 1000}, reduced_motion="reduce"
            )
            patient = patient_context.new_page()
            patient.on("pageerror", lambda e: errors.append(str(e)))
            patient.goto(url)
            patient.locator("[data-registration=invitation]").click()
            patient.locator("#invitation-link-form input").fill("invalid")
            patient.locator("#invitation-link-form [type=submit]").click()
            expect(patient.locator("#registration-error")).to_contain_text(
                "Проверьте приглашение"
            )
            patient.locator("#invitation-link-form input").fill(invitation)
            patient.locator("#invitation-link-form [type=submit]").click()
            intake = patient.locator("#intake-form")
            expect(intake).to_be_visible()
            expect(patient.locator("[data-theme-toggle]")).to_be_visible()
            for name, value in {
                "name": "Ольга Тестовая",
                "age": "29",
                "height": "168",
                "weight": "62",
                "phone": "+70000000982",
                "password": "new-patient-test",
                "confirm": "new-patient-test",
            }.items():
                intake.locator(f'[name="{name}"]').fill(value)
            intake.locator("[type=submit]").click()
            expect(patient.locator(".patient-dashboard")).to_be_visible()
            patient.wait_for_function("()=>!busy")
            patient.locator("[data-page=consents]").click()
            patient.locator("[data-registration=invite-relative]").click()
            relative_link = patient.locator("#relative-invite-result input")
            expect(relative_link).to_be_visible()
            link = relative_link.input_value()
            patient.screenshot(path=str(ART / "revision7-relative-invite.png"))
            relative_context = browser.new_context(
                viewport={"width": 390, "height": 1000}, reduced_motion="reduce"
            )
            relative = relative_context.new_page()
            relative.on("pageerror", lambda e: errors.append(str(e)))
            relative.goto(link)
            rf = relative.locator("#relative-registration-form")
            expect(rf).to_be_visible()
            expect(relative.locator("[data-theme-toggle]")).to_be_visible()
            relative.screenshot(
                path=str(ART / "revision7-relative-registration.png"), full_page=True
            )
            for name, value in {
                "name": "Ирина Тестовая",
                "phone": "+70000000983",
                "password": "new-relative-test",
                "confirm": "new-relative-test",
            }.items():
                rf.locator(f'[name="{name}"]').fill(value)
            rf.locator("[type=submit]").click()
            relative.wait_for_function("()=>state.user?.role==='relative'&&!busy")
            assert (
                relative_context.request.get(url + "/api/relative").json()["patients"]
                == []
            )
            patient.locator("[data-pref=relative_sos]").check()
            patient.wait_for_function("()=>!busy&&pref().relative_sos")
            assert (
                len(
                    relative_context.request.get(url + "/api/relative").json()[
                        "patients"
                    ]
                )
                == 1
            )
            patient.locator("[data-pref=relative_sos]").uncheck()
            patient.wait_for_function("()=>!busy&&!pref().relative_sos")
            assert (
                relative_context.request.get(url + "/api/relative").json()["patients"]
                == []
            )
            page.locator("#navigation [data-page=patients]").click()
            expect(page.locator("#patient-cards")).to_contain_text("Ольга Тестовая")
            reused = browser.new_page()
            reused.goto(link)
            expect(
                reused.get_by_role("heading", name="Приглашение недоступно")
            ).to_be_visible()
            assert not errors, errors
            browser.close()
            print(
                "PASS: entry theme persistence and accessibility, larger tree and 5 widths, doctor registration validation/duplicate phone/empty workspace, patient invite registration, relative single-use invite/registration and consent revocation, independent role sessions"
            )
    finally:
        server.terminate()
        server.wait(timeout=10)
