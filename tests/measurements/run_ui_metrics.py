"""Measure UI and real SOS on an isolated localhost WSGI instance."""

import json
import math
import os
from pathlib import Path
import random
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from contextlib import closing

from playwright.sync_api import sync_playwright, expect
from runtime import revision, server_command, server_label, stop_server

ROOT = Path(os.environ.get("COMPASS_REPO", Path(__file__).resolve().parents[2]))
OUT = Path(os.environ.get("COMPASS_METRICS_OUT", ROOT / "test-results" / "metrics"))
OUT.mkdir(parents=True, exist_ok=True)


def summary(rows, key):
    values = sorted(r[key] for r in rows)
    return {
        "n": len(values),
        "p50_ms": round(values[math.ceil(0.5 * len(values)) - 1], 3),
        "p95_ms": round(values[math.ceil(0.95 * len(values)) - 1], 3),
        "max_ms": round(max(values), 3),
    }


def main(base, database):
    result = {
        "commit": revision(ROOT),
        "network": "HTTP localhost; no TLS, WAN or CPU/network throttling",
        "server": server_label()
        + "; separate temporary SQLite database; reminder worker disabled",
        "browser": "Chromium desktop and mobile viewport, not physical Safari/iPhone/Android",
        "errors": [],
        "http_5xx": [],
        "requests_failed": [],
        "login_screen": [],
        "diary_save": [],
        "sos": [],
    }
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=os.environ.get("CHROMIUM_PATH") or shutil.which("chromium"),
            args=["--no-sandbox"] if sys.platform.startswith("linux") else [],
        )

        def attach(page):
            page.on("pageerror", lambda error: result["errors"].append(str(error)))
            page.on(
                "response",
                lambda r: (
                    result["http_5xx"].append({"status": r.status, "url": r.url})
                    if r.status >= 500
                    else None
                ),
            )
            page.on(
                "requestfailed",
                lambda r: result["requests_failed"].append(
                    {"url": r.url, "failure": r.failure}
                ),
            )

        prior = None
        if "--sos-only" in sys.argv:
            prior = json.loads((OUT / "ui-metrics.json").read_text())
            result["login_screen"] = prior["login_screen"]
            result["diary_save"] = prior["diary_save"]
            result["errors"] = prior["errors"]
            result["http_5xx"] = prior["http_5xx"]
            result["requests_failed"] = prior["requests_failed"]
            result["screen_diary_source"] = (
                "Previous completed UI run on the same application commit; SOS repeated with an independent sender schedule."
            )
        for width in [] if prior else [1440, 390]:
            for index in range(10):
                # Fresh browser context: no existing service worker or HTTP cache.
                context = browser.new_context(
                    viewport={"width": width, "height": 1000},
                    timezone_id="Europe/Moscow",
                )
                page = context.new_page()
                attach(page)
                started = time.perf_counter()
                page.goto(base, wait_until="domcontentloaded")
                expect(
                    page.get_by_role("button", name="Войти как Александра")
                ).to_be_visible()
                elapsed = (time.perf_counter() - started) * 1000
                result["login_screen"].append(
                    {"width": width, "sample": index + 1, "ms": round(elapsed, 3)}
                )
                context.close()
            print(
                "LOGIN SCREEN",
                width,
                summary(
                    [r for r in result["login_screen"] if r["width"] == width], "ms"
                ),
                flush=True,
            )

        context = browser.new_context(
            viewport={"width": 390, "height": 1000}, timezone_id="Europe/Moscow"
        )
        patient = context.new_page()
        attach(patient)
        patient.goto(base)
        patient.get_by_role("button", name="Войти как Александра").click()
        patient.wait_for_function("()=>state.user&&!busy")
        for width in [] if prior else [1440, 390]:
            patient.set_viewport_size({"width": width, "height": 1000})
            for index in range(10):
                patient.wait_for_function("()=>!busy&&!pollBusy")
                patient.locator("#navigation [data-page=overview]").click()
                patient.get_by_role("button", name="Заполнить дневник").click()
                note = f"Измерение сохранения {width}-{index}"
                patient.locator("#note").fill(note)
                save = patient.get_by_role("button", name="Сохранить самоотчёт")
                save.scroll_into_view_if_needed()
                started = time.perf_counter()
                with patient.expect_response(
                    lambda r: r.request.method == "POST" and r.url.endswith("/reports")
                ) as response:
                    save.click()
                status = response.value.status
                assert status == 201, status
                patient.wait_for_function(
                    "note=>!busy&&state.detail.reports.some(r=>r.note===note)", arg=note
                )
                # Saved-history details are closed by design; text is present in history.
                expect(patient.locator("#report-history")).to_contain_text(note)
                elapsed = (time.perf_counter() - started) * 1000
                result["diary_save"].append(
                    {
                        "width": width,
                        "sample": index + 1,
                        "ms": round(elapsed, 3),
                        "status": status,
                    }
                )
            patient.screenshot(path=str(OUT / f"diary-{width}.png"), full_page=True)
            print(
                "DIARY SAVE",
                width,
                summary([r for r in result["diary_save"] if r["width"] == width], "ms"),
                flush=True,
            )

        recipients = []
        for role, label, width in [
            ("doctor", "Войти как врач", 1440),
            ("relative", "Войти как близкий", 390),
        ]:
            ctx = browser.new_context(
                viewport={"width": width, "height": 1000}, timezone_id="Europe/Moscow"
            )
            page = ctx.new_page()
            attach(page)
            page.goto(base)
            page.get_by_role("button", name=label).click()
            page.wait_for_function("()=>state.user&&!busy")
            page.locator("#notifications-button").click()
            page.wait_for_function("()=>!pollBusy")
            page.evaluate(
                """() => {
                window.metricSeen = {};
                const record = () => document.querySelectorAll('#notification-list [data-id]').forEach(el=>{
                    if (!document.querySelector('#notifications-panel').hidden && el.getClientRects().length && !window.metricSeen[el.dataset.id])
                        window.metricSeen[el.dataset.id] = performance.timeOrigin+performance.now();
                });
                new MutationObserver(record).observe(document.querySelector('#notification-list'),{childList:true,subtree:true});
                record();
            }"""
            )
            recipients.append((role, page, page.evaluate("state.user.id")))

        patient.set_viewport_size({"width": 390, "height": 1000})
        patient.locator("#navigation [data-page=help]").click()
        patient.locator("[data-ext=sub][data-group=help][data-key=sos]").click()
        patient.evaluate(
            """() => {
            document.addEventListener('pointerdown',e=>{
                if(e.target.closest('[data-ext=sos]')) window.metricSosPressed=performance.timeOrigin+performance.now();
            },true);
            const original=window.fetch;
            window.fetch=function(...args){
                if(String(args[0]).endsWith('/sos')) window.metricSosSent=performance.timeOrigin+performance.now();
                return original.apply(this,args);
            };
        }"""
        )
        with closing(sqlite3.connect(database)) as con, con:
            prefs = json.loads(
                con.execute(
                    "SELECT settings_json FROM patient_preferences WHERE patient_id=2"
                ).fetchone()[0]
            )
            assert prefs["relative_sos"] is True, prefs
        rng = random.Random(26102026)
        for index in range(20):
            patient.wait_for_function("()=>!busy&&!pollBusy")
            patient.wait_for_timeout(rng.uniform(100, 5100))
            button = patient.locator(".sos-large")
            button.scroll_into_view_if_needed()
            box = button.bounding_box()
            patient.mouse.move(
                box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            )
            with patient.expect_response(
                lambda r: r.request.method == "POST" and r.url.endswith("/sos")
            ) as response:
                patient.mouse.down()
                patient.wait_for_timeout(1600)
                patient.mouse.up()
            resp = response.value
            payload = resp.json()
            assert resp.status == 201, (resp.status, payload)
            timing = patient.evaluate(
                "({pressed:window.metricSosPressed,sent:window.metricSosSent})"
            )
            record = {
                "sample": index + 1,
                "event_id": payload["id"],
                "status": resp.status,
                "hold_to_send_ms": round(timing["sent"] - timing["pressed"], 3),
            }
            with closing(sqlite3.connect(database)) as con, con:
                ids = {
                    uid: con.execute(
                        "SELECT MAX(id) FROM notifications WHERE patient_id=2 AND user_id=? AND title=?",
                        (uid, "Запрос поддержки"),
                    ).fetchone()[0]
                    for _, _, uid in recipients
                }
            for role, page, uid in recipients:
                ident = ids[uid]
                assert ident is not None, (role, ids)
                record[f"{role}_notification_id"] = ident
            record["pressed_epoch_ms"] = timing["pressed"]
            record["sent_epoch_ms"] = timing["sent"]
            result["sos"].append(record)
            (OUT / "ui-metrics-progress.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2)
            )
            print("SOS SENT", json.dumps(record), flush=True)
        # Observe deliveries after the sender schedule, so receipt latency cannot
        # determine the phase of the next press relative to the polling timer.
        for record in result["sos"]:
            for role, page, uid in recipients:
                ident = record[f"{role}_notification_id"]
                page.wait_for_function(
                    "id=>!!window.metricSeen[id]", arg=str(ident), timeout=15000
                )
                visible = page.evaluate("id=>window.metricSeen[id]", str(ident))
                record[f"{role}_from_press_ms"] = round(
                    visible - record["pressed_epoch_ms"], 3
                )
                record[f"{role}_from_send_ms"] = round(
                    visible - record["sent_epoch_ms"], 3
                )
            print("SOS DELIVERED", json.dumps(record), flush=True)
        for role, page, _ in recipients:
            page.screenshot(path=str(OUT / f"sos-{role}.png"), full_page=True)
        patient.screenshot(path=str(OUT / "sos-patient.png"), full_page=True)
        with closing(sqlite3.connect(database)) as con, con:
            ids = [r["event_id"] for r in result["sos"]]
            result["sos_saved"] = con.execute(
                "SELECT COUNT(*) FROM support_events WHERE id IN ("
                + ",".join("?" * len(ids))
                + ")",
                ids,
            ).fetchone()[0]
            result["sqlite_integrity"] = con.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
        result["summary"] = {}
        for key in ["login_screen", "diary_save"]:
            result["summary"][key] = {
                str(w): summary([r for r in result[key] if r["width"] == w], "ms")
                for w in [1440, 390]
            }
        result["summary"]["sos"] = {
            key: summary(result["sos"], key)
            for key in [
                "hold_to_send_ms",
                "doctor_from_press_ms",
                "relative_from_press_ms",
                "doctor_from_send_ms",
                "relative_from_send_ms",
            ]
        }
        (OUT / "ui-metrics.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2)
        )
        print("SUMMARY", json.dumps(result["summary"], ensure_ascii=False), flush=True)
        assert not result["errors"], result["errors"]
        assert not result["http_5xx"], result["http_5xx"]
        assert result["sos_saved"] == 20, result["sos_saved"]
        browser.close()


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="cc-poster-") as directory:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        database = Path(directory) / "ui.db"
        env = {
            **os.environ,
            "PORT": str(port),
            "COMPASS_DB": str(database),
            "COMPASS_AI_API_KEY": "",
            "COMPASS_AI_BASE_URL": "",
            "COMPASS_AI_MODEL": "",
            "COMPASS_TELEGRAM_BOT_TOKEN": "",
            "COMPASS_PUBLIC_URL": "",
            "COMPASS_DISABLE_WORKER": "1",
            "COMPASS_SECURE_COOKIES": "0",
        }
        with (OUT / "ui-server.log").open("w") as log:
            process = subprocess.Popen(
                server_command(ROOT, port),
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
            try:
                base = f"http://127.0.0.1:{port}"
                for _ in range(200):
                    try:
                        urllib.request.urlopen(base + "/api/health", timeout=1).close()
                        break
                    except OSError:
                        if process.poll() is not None:
                            raise RuntimeError("Server exited")
                        time.sleep(0.05)
                main(base, database)
            finally:
                stop_server(process)
