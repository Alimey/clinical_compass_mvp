"""Run local measurements on Windows, macOS or Linux and create an HTML report."""

import argparse
from datetime import datetime, timezone
from html import escape
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import webbrowser

from runtime import revision, server_kind, server_label, system_info

ROOT = Path(__file__).resolve().parents[2]


def save_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def preflight():
    missing = [
        name
        for name in ["flask", "cryptography", "playwright", server_kind()]
        if importlib.util.find_spec(name) is None
    ]
    if missing:
        raise RuntimeError(
            "Missing packages: "
            + ", ".join(missing)
            + ". Install application requirements and tests/measurements/requirements-local.txt with this Python."
        )
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        executable = (
            os.environ.get("CHROMIUM_PATH")
            or shutil.which("chromium")
            or pw.chromium.executable_path
        )
        if not Path(executable).is_file():
            raise RuntimeError(
                "Chromium not found. Run: python -m playwright install chromium"
            )


def run_stage(out, environment, name, arguments):
    print("\n=== " + name + " ===", flush=True)
    with (out / (name + ".log")).open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [sys.executable, "-X", "utf8", *arguments],
            cwd=ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        try:
            for line in process.stdout:
                print(line, end="", flush=True)
                log.write(line)
                log.flush()
            return process.wait()
        except KeyboardInterrupt:
            process.terminate()
            process.wait(timeout=20)
            raise


def write_report(out, run):
    sections = []

    def table(headers, rows):
        return (
            '<div class="scroll"><table><thead><tr>'
            + "".join("<th>" + escape(str(h)) + "</th>" for h in headers)
            + "</tr></thead><tbody>"
            + "".join(
                "<tr>"
                + "".join("<td>" + escape(str(c)) + "</td>" for c in row)
                + "</tr>"
                for row in rows
            )
            + "</tbody></table></div>"
        )

    def read(name):
        path = out / name
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def number(x):
        return f"{x:.2f}".replace(".", ",")

    bench = read("benchmark-results.json")
    ui = read("ui-metrics.json")
    if bench and bench.get("finished_at"):
        stages = bench["load"]
        sections.append(
            "<h2>Нагрузка и отклик сервера</h2>"
            + table(
                [
                    "Прогон",
                    "Активных сессий",
                    "Запросов",
                    "p95, мс",
                    "Запросов/с",
                    "Неожиданных ошибок",
                ],
                [
                    [
                        r["repeat"],
                        r["sessions"],
                        r["n"],
                        number(r["p95_ms"]),
                        number(r["rps"]),
                        r["errors"],
                    ]
                    for r in stages
                ],
            )
        )
        sections.append(
            "<p>Всего запросов под нагрузкой: <b>"
            + str(sum(r["n"] for r in stages))
            + "</b>. Неожиданных ошибок: <b>"
            + str(sum(r["errors"] for r in stages))
            + "</b>.</p>"
        )
        sections.append(
            "<h2>Обычные операции API</h2>"
            + table(
                ["Операция", "Попыток", "p50, мс", "p95, мс", "Ошибок"],
                [
                    [
                        {
                            "patient_card": "Карточка пациента",
                            "doctor_patients": "Список пациентов",
                            "report_save": "Сохранение дневника",
                            "medication_mark": "Отметка приёма лекарства",
                            "doctor_notifications": "Уведомления врача",
                        }.get(name, name),
                        r["n"],
                        number(r["p50_ms"]),
                        number(r["p95_ms"]),
                        len(r["errors"]),
                    ]
                    for name, r in bench["single"].items()
                ],
            )
        )
        crash = bench["recovery"]["process_crash"]
        sections.append(
            "<h2>Восстановление после остановки процесса</h2>"
            + table(
                ["Показатель", "Результат"],
                [
                    ["Подтверждённых записей до остановки", crash["accepted"]],
                    ["Найдено после перезапуска", crash["found"]],
                    ["Потеряно", crash["lost"]],
                    [
                        "Готовность сервера после перезапуска, мс",
                        number(crash["health_ready_ms"]),
                    ],
                    ["Проверка целостности базы", crash["integrity"]],
                ],
            )
        )
        sections.append(
            "<details><summary>Подробные результаты восстановления и снимка базы</summary><pre>"
            + escape(json.dumps(bench["recovery"], ensure_ascii=False, indent=2))
            + "</pre></details>"
        )
    if ui:
        sections.append(
            "<h2>Отклик интерфейса</h2>"
            + table(
                [
                    "Сценарий",
                    "Ширина, px",
                    "Попыток",
                    "p50, с",
                    "p95, с",
                    "Максимум, с",
                ],
                [
                    [
                        label,
                        width,
                        r["n"],
                        number(r["p50_ms"] / 1000),
                        number(r["p95_ms"] / 1000),
                        number(r["max_ms"] / 1000),
                    ]
                    for key, label in [
                        ("login_screen", "Открытие экрана входа"),
                        ("diary_save", "Сохранение дневника"),
                    ]
                    for width, r in ui["summary"][key].items()
                ],
            )
        )
        labels = {
            "doctor_from_press_ms": "От удержания до врача",
            "relative_from_press_ms": "От удержания до близкого",
            "doctor_from_send_ms": "От отправки до врача",
            "relative_from_send_ms": "От отправки до близкого",
        }
        sections.append(
            "<h2>SOS в открытом приложении</h2>"
            + table(
                ["Измерение", "Попыток", "p50, с", "p95, с", "Максимум, с"],
                [
                    [
                        label,
                        r["n"],
                        number(r["p50_ms"] / 1000),
                        number(r["p95_ms"] / 1000),
                        number(r["max_ms"] / 1000),
                    ]
                    for key, label in labels.items()
                    for r in [ui["summary"]["sos"][key]]
                ],
            )
        )
        sections.append(
            "<p>SOS сохранено: "
            + str(ui["sos_saved"])
            + ". Ошибок JS: "
            + str(len(ui["errors"]))
            + ". Ответов HTTP 5xx: "
            + str(len(ui["http_5xx"]))
            + ".</p>"
        )
    log = out / "server-tests.log"
    if log.exists():
        text = log.read_text(encoding="utf-8")
        count = re.search(r"Ran (\d+) tests", text)
        sections.append(
            "<h2>Серверные функциональные тесты</h2><p>Выполнено: "
            + (count.group(1) if count else "см. журнал")
            + ". Результат: "
            + (
                "OK"
                if run["stages"].get("server-tests") == 0
                else "есть ошибка — см. server-tests.log"
            )
            + ".</p>"
        )
    info = run["environment"]
    status = (
        "Завершено"
        if run["status"] == "completed"
        else "Запуск не завершён — проверьте журнал"
    )
    document = """<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ПсиКомпас — локальные замеры</title><style>
    body{margin:0;background:#eff6fa;color:#173d53;font:17px/1.6 system-ui,sans-serif}main{max-width:1100px;margin:auto;padding:28px}h1{font-size:32px}h2{font-size:23px;margin-top:30px}section{background:white;padding:24px;border-radius:18px;margin:20px 0}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:15px}td,th{text-align:left;padding:10px;border-bottom:1px solid #d7e5ed}th{background:#e4f0f6}pre{white-space:pre-wrap;font-size:14px}small{color:#587182}a{color:#087ca7}</style><main>"""
    document += (
        "<h1>ПсиКомпас: локальные технические испытания</h1><p><b>"
        + status
        + "</b></p><p>Начало: "
        + escape(run["started_local"])
        + "<br>Версия: "
        + escape(run["commit"])
        + "<br>Система: "
        + escape(info["platform"])
        + "; Python "
        + escape(info["python"])
        + "<br>Сервер: "
        + escape(run["server"])
        + "<br>Логических процессоров по данным ОС: "
        + str(info["logical_cpu_count"])
        + "</p>"
    )
    if info.get("cpu_max"):
        document += (
            "<p>Квота CPU cgroup: "
            + escape(info["cpu_max"])
            + "; лимит памяти cgroup: "
            + escape(str(info["memory_max"]))
            + ".</p>"
        )
    document += "<section><b>Область измерений</b><p>Клиент и отдельный тестовый сервер работают на этом компьютере через HTTP localhost. Производительность Render, HTTPS и интернет-канала сюда не входят. База временная; основная база приложения не используется.</p><p>p95: 95% попыток укладываются в указанное время. 50 сессий — максимальная проверенная ступень, а не найденный предел. Нагрузка: 2 с прогрева + 12 с измерений, два прогона каждого уровня; автоматические сессии без пауз пользователя.</p><p>Chromium: размеры экрана 390 и 1440 px. SOS измеряется в открытых панелях врача и разрешённого близкого; время от удержания включает 1,5 с защиты от случайного нажатия. Системные push и физические телефоны не проверяются. Основной набор из 13 браузерных серий этим запуском не выполняется; проверяется специальный сценарий измерений и серверные тесты.</p></section>"
    document += (
        "<section>"
        + "".join(sections)
        + "</section><section><h2>Исходные результаты</h2><p>JSON, CSV и журналы находятся в этой же папке. Их можно использовать для повторной проверки расчётов. Через браузер можно сохранить этот отчёт в PDF: Ctrl+P → «Сохранить как PDF».</p>"
    )
    if run.get("error"):
        document += "<pre>" + escape(run["error"]) + "</pre>"
    document += "</section></main></html>"
    (out / "report.html").write_text(document, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="New or empty output directory")
    parser.add_argument(
        "--no-open", action="store_true", help="Do not open the report in a browser"
    )
    args = parser.parse_args()
    out = (
        args.output
        or ROOT
        / "test-results"
        / ("local-" + datetime.now().strftime("%Y-%m-%d_%H-%M-%S"))
    ).resolve()
    if out.exists() and any(out.iterdir()):
        parser.error("Output folder must be empty; previous results are preserved")
    out.mkdir(parents=True, exist_ok=True)
    run = {
        "status": "running",
        "started_local": datetime.now().astimezone().isoformat(timespec="seconds"),
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "commit": revision(ROOT),
        "server": server_label(),
        "environment": system_info(),
        "stages": {},
    }
    env = {
        **os.environ,
        "COMPASS_REPO": str(ROOT),
        "COMPASS_METRICS_OUT": str(out),
        "COMPASS_AI_API_KEY": "",
        "COMPASS_AI_BASE_URL": "",
        "COMPASS_AI_MODEL": "",
        "COMPASS_TELEGRAM_BOT_TOKEN": "",
        "COMPASS_PUBLIC_URL": "",
        "COMPASS_DISABLE_WORKER": "1",
        "COMPASS_SECURE_COOKIES": "0",
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUNBUFFERED": "1",
    }
    print("Results: " + str(out), flush=True)
    try:
        preflight()
        for name, arguments in [
            ("load", ["tests/measurements/run_benchmarks.py"]),
            ("ui", ["tests/measurements/run_ui_metrics.py"]),
            ("server-tests", ["-m", "unittest", "discover", "-s", "tests", "-v"]),
        ]:
            code = run_stage(out, env, name, arguments)
            run["stages"][name] = code
            save_json(out / "local-run.json", run)
            if code != 0:
                raise RuntimeError(name + " failed; see " + str(out / (name + ".log")))
        run["status"] = "completed"
    except (Exception, KeyboardInterrupt) as error:
        run["status"] = "failed"
        run["error"] = str(error) or "Interrupted"
    finally:
        run["finished_utc"] = datetime.now(timezone.utc).isoformat()
        save_json(out / "local-run.json", run)
        write_report(out, run)
        print("\nReport: " + str(out / "report.html"), flush=True)
        if not args.no_open:
            webbrowser.open((out / "report.html").as_uri())
    return 0 if run["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
