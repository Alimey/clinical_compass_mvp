"""Synthetic end-to-end check. Requires Playwright and Chromium; see README."""

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
ARTIFACTS = Path(tempfile.gettempdir()) / "compass-artifacts"
ARTIFACTS.mkdir(exist_ok=True)
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
                with urllib.request.urlopen(url + "/api/health", timeout=1) as response:
                    assert response.status == 200
                break
            except OSError:
                if server.poll() is not None:
                    raise RuntimeError("Test server exited")
                time.sleep(0.1)
        else:
            raise RuntimeError("Server did not start")
        with sync_playwright() as p:
            browser = p.chromium.launch(
                executable_path=os.environ.get("CHROMIUM_PATH")
                or shutil.which("chromium"),
                args=["--no-sandbox"],
            )
            doctor_context = browser.new_context(
                viewport={"width": 1440, "height": 1000}
            )
            patient_context = browser.new_context(
                viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True
            )
            doctor = doctor_context.new_page()
            patient = patient_context.new_page()
            errors = []
            for page in (doctor, patient):
                page.on("pageerror", lambda error: errors.append(str(error)))
            doctor.goto(url)
            expect(doctor.get_by_role("button", name="Войти как врач")).to_be_visible()
            doctor.screenshot(path=str(ARTIFACTS / "login-desktop.png"), full_page=True)
            doctor.get_by_role("button", name="Войти как врач").click()
            expect(
                doctor.get_by_role("heading", name="Добрый день, Анна")
            ).to_be_visible()
            doctor.screenshot(
                path=str(ARTIFACTS / "dashboard-desktop.png"), full_page=True
            )
            patient.goto(url)
            patient.get_by_role("button", name="Войти как Александра").click()
            expect(
                patient.get_by_role("heading", name="Здравствуйте, Александра")
            ).to_be_visible()
            patient.screenshot(
                path=str(ARTIFACTS / "patient-mobile.png"), full_page=True
            )
            patient.get_by_role("button", name="Заполнить дневник").click()
            patient.locator("#note").fill(
                "<script>window.injected=true</script> Новый синтетический отчёт"
            )
            patient.locator("#safety").check()
            expect(patient.locator("#urgent")).to_be_visible()
            patient.get_by_role("button", name="Сохранить самоотчёт").click()
            expect(patient.locator("#report-history")).to_contain_text("История")
            patient.locator("#report-history details").first.locator("summary").click()
            expect(patient.locator("#report-history")).to_contain_text(
                "<script>window.injected=true</script>"
            )
            assert patient.evaluate("window.injected") is None
            # Poll delivers a durable notification to the independent doctor session.
            doctor.get_by_role("button", name="Уведомления", exact=True).click()
            expect(doctor.locator("#notification-list")).to_contain_text(
                "Сигнал безопасности", timeout=10000
            )
            expect(doctor.locator("#notification-list")).to_contain_text(
                "отметил(а) опасения", timeout=10000
            )
            doctor.locator("#notification-list .notification-item").first.click()
            expect(
                doctor.get_by_role("heading", name="Александра Морозова")
            ).to_be_visible()
            doctor.get_by_role("button", name="Отметить просмотренным").first.click()
            expect(doctor.locator("#toast")).to_contain_text("Сигнал отмечен")
            doctor.get_by_role("button", name="План и варианты", exact=True).click()
            expect(
                doctor.get_by_role("button", name="Учебная несовместимость")
            ).to_be_disabled()
            proposal = doctor.locator(".proposal").filter(
                has_text="Рассмотреть ДЕМО-Альфа"
            )
            proposal.get_by_role("button", name="Подтвердить", exact=True).click()
            doctor.locator("#resolution-note").fill(
                "Согласовали вымышленный план для демонстрации"
            )
            doctor.get_by_role("button", name="Подтвердить решение", exact=True).click()
            expect(doctor.locator(".plan-current")).to_contain_text("ДЕМО-Альфа")
            doctor.get_by_role("button", name="Журнал", exact=True).click()
            expect(doctor.locator("#content")).to_contain_text("proposal.accepted")
            patient.get_by_role("button", name="Ещё", exact=True).click()
            patient.get_by_role("button", name="Мой план", exact=True).click()
            expect(patient.locator(".plan-current")).to_contain_text("ДЕМО-Альфа")
            patient.get_by_role("button", name="Сообщения", exact=True).click()
            patient.locator("#message-body").fill(
                "Привет! Это синтетическое сообщение."
            )
            patient.get_by_role(
                "button", name="Отправить сообщение", exact=True
            ).click()
            expect(patient.locator("#chat-thread")).to_contain_text(
                "Привет! Это синтетическое сообщение."
            )
            doctor.locator("#content .tabs").get_by_role(
                "button", name="Сообщения", exact=True
            ).click()
            expect(doctor.locator("#chat-thread")).to_contain_text(
                "Привет! Это синтетическое сообщение."
            )
            doctor.locator("#message-body").fill("Спасибо, обсудим вымышленный план.")
            doctor.get_by_role("button", name="Отправить сообщение").click()
            expect(patient.locator("#chat-thread")).to_contain_text(
                "Спасибо, обсудим вымышленный план.", timeout=12000
            )
            expect(
                patient.locator("#chat-thread .message.own .message-meta").last
            ).to_contain_text("Прочитано", timeout=12000)
            # Polling must not overwrite a draft.
            patient.locator("#message-body").fill("Черновик ещё не отправлен")
            doctor.locator("#message-body").fill(
                "Второе сообщение для проверки обновления"
            )
            doctor.get_by_role("button", name="Отправить сообщение").click()
            expect(patient.locator("#chat-thread")).to_contain_text(
                "Второе сообщение", timeout=12000
            )
            expect(patient.locator("#message-body")).to_have_value(
                "Черновик ещё не отправлен"
            )
            doctor.get_by_role("button", name="Пациенты", exact=True).click()
            doctor.locator("#patient-search").fill("Михаил")
            expect(doctor.locator(".patient-card")).to_have_count(1)
            doctor.locator(".patient-card").get_by_role(
                "button", name="Открыть карточку"
            ).click()
            expect(doctor.get_by_role("heading", name="Михаил Волков")).to_be_visible()
            assert (
                "Новый синтетический отчёт"
                not in doctor.locator("#content").inner_text()
            )
            # Visit both layouts, including the long plan and chart screens.
            for width, height in [(320, 740), (390, 844), (430, 932), (1280, 900)]:
                doctor.set_viewport_size({"width": width, "height": height})
                assert doctor.evaluate(
                    "document.documentElement.scrollWidth <= innerWidth"
                ), width
                doctor.get_by_role("button", name="План и варианты", exact=True).click()
                assert doctor.evaluate(
                    "document.documentElement.scrollWidth <= innerWidth"
                ), ("plan", width)
                doctor.get_by_role("button", name="Обзор", exact=True).last.click()
            doctor.set_viewport_size({"width": 390, "height": 844})
            doctor.screenshot(path=str(ARTIFACTS / "doctor-mobile.png"), full_page=True)
            # Offline shell contains no cached authenticated/API responses.
            patient.evaluate("navigator.serviceWorker.ready")
            patient.reload()
            patient.wait_for_function("navigator.serviceWorker.controller !== null")
            expect(
                patient.get_by_role("heading", name="Здравствуйте, Александра")
            ).to_be_visible()
            caches = patient.evaluate(
                """async()=>{const out=[];for(const key of await caches.keys()){const c=await caches.open(key);out.push(...(await c.keys()).map(r=>new URL(r.url).pathname));}return out;}"""
            )
            assert "/" in caches and not any(
                v.startswith("/api/") for v in caches
            ), caches
            assert patient.evaluate("localStorage.length") == 0
            patient.get_by_role("button", name="Заполнить дневник").click()
            patient.locator("#note").fill("Офлайн-черновик")
            patient_context.set_offline(True)
            expect(patient.locator("#connection")).to_be_visible()
            patient.get_by_role("button", name="Сохранить самоотчёт").click()
            expect(patient.locator("#toast")).to_contain_text("Неотправленный текст")
            expect(patient.locator("#note")).to_have_value("Офлайн-черновик")
            patient.reload()
            expect(
                patient.get_by_role("button", name="Войти как Александра")
            ).to_be_visible()
            expect(patient.locator("#login-error")).to_contain_text("Сервер недоступен")
            patient_context.set_offline(False)
            patient.reload()
            expect(
                patient.get_by_role("heading", name="Здравствуйте, Александра")
            ).to_be_visible()
            patient.get_by_role("button", name="Выйти", exact=True).click()
            expect(
                patient.get_by_role("button", name="Войти как Александра")
            ).to_be_visible()
            patient.reload()
            expect(
                patient.get_by_role("button", name="Войти как Александра")
            ).to_be_visible()
            assert not errors, errors
            doctor_context.close()
            patient_context.close()
            browser.close()
            print(
                "PASS: separate sessions, report → notification → review → confirmed plan → patient, journal, live chat, receipts, draft preservation, search, 4 widths, offline shell, logout; no JS errors"
            )
    finally:
        server.terminate()
        server.wait(timeout=10)
