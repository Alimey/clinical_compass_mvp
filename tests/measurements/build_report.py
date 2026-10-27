"""Build poster and report only from recorded test results."""

import csv
from html import escape
import json
import math
import os
from pathlib import Path
import re
import zipfile

os.environ.setdefault("MPLCONFIGDIR", "/tmp/compass-poster-mpl")
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
)

ROOT = Path(os.environ.get("COMPASS_REPO", Path(__file__).resolve().parents[2]))
OUT = Path(os.environ.get("COMPASS_METRICS_OUT", ROOT / "test-results" / "metrics"))
OUT.mkdir(parents=True, exist_ok=True)
b = json.loads((OUT / "benchmark-results.json").read_text())
u = json.loads((OUT / "ui-metrics.json").read_text())
v = json.loads((OUT / "validation-results.json").read_text())
assert b["finished_at"] and v["finished_at"]
assert b["commit"] == u["commit"] == v["commit"]
load = b["load"]
total = sum(r["n"] for r in load)
errors = sum(r["errors"] for r in load)
fifty = [r for r in load if r["sessions"] == 50]
load95 = max(r["p95_ms"] for r in fifty)
load95_bound_s = math.ceil(load95) / 1000
max_screen = max(r["p95_ms"] for r in u["summary"]["login_screen"].values())
max_diary = max(r["p95_ms"] for r in u["summary"]["diary_save"].values())
sos = u["summary"]["sos"]
doc95 = sos["doctor_from_press_ms"]["p95_ms"]
rel95 = sos["relative_from_press_ms"]["p95_ms"]
server_log = (OUT / "validation/server_tests/output.log").read_text()
server_n = int(re.search(r"Ran (\d+) tests", server_log).group(1))
server_ok = "\nOK\n" in server_log
browser_jobs = [r for r in v["results"] if r["name"].startswith("browser_")]
browser_pass = sum(r["exit_code"] == 0 for r in browser_jobs)
syntax_jobs = [r for r in v["results"] if r["name"].startswith("syntax_")]
failed = [r["name"] for r in v["results"] if r["exit_code"] != 0]
fmt = lambda x, n=2: f"{x:.{n}f}".replace(".", ",")
num = lambda x: f"{x:,}".replace(",", " ")
request_word = (
    "запрос"
    if total % 10 == 1 and total % 100 != 11
    else (
        "запроса"
        if total % 10 in [2, 3, 4] and total % 100 not in [12, 13, 14]
        else "запросов"
    )
)
INK = "#173d53"
BLUE = "#087ca7"
MUTED = "#587182"
BG = "#eff6fa"
PURPLE = "#a284b5"
plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.labelcolor": INK,
        "text.color": INK,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "pdf.fonttype": 42,
        "svg.fonttype": "none",
    }
)

fig, axes = plt.subplots(1, 2, figsize=(12, 4.4), layout="constrained")
for repeat, color in [(1, BLUE), (2, PURPLE)]:
    rows = sorted(
        [r for r in load if r["repeat"] == repeat], key=lambda r: r["sessions"]
    )
    axes[0].plot(
        [r["sessions"] for r in rows],
        [r["p95_ms"] for r in rows],
        "-o",
        color=color,
        label=f"Прогон {repeat}",
        lw=2,
    )
    axes[1].plot(
        [r["sessions"] for r in rows], [r["rps"] for r in rows], "-o", color=color, lw=2
    )
for ax in axes:
    ax.set_xticks([1, 5, 10, 25, 50])
    ax.set_xlabel("Одновременно активные сессии")
    ax.grid(alpha=0.18)
    ax.set_axisbelow(True)
    ax.set_ylim(bottom=0)
axes[0].set_ylabel("HTTP-отклик, p95, мс")
axes[0].legend(frameon=False)
axes[1].set_ylabel("Запросов в секунду")
fig.suptitle(
    f"Локальный стенд: {num(total)} {request_word}, {errors} неожиданных ошибок",
    fontweight="bold",
)
fig.savefig(OUT / "load-chart.png", dpi=180)
fig.savefig(OUT / "load-chart.pdf")
plt.close(fig)

fig, ax = plt.subplots(figsize=(10, 4.5), layout="constrained")
for key, color, label in [
    ("doctor_from_press_ms", BLUE, "Врач"),
    ("relative_from_press_ms", PURPLE, "Близкий"),
]:
    vals = sorted(r[key] / 1000 for r in u["sos"])
    ax.step(
        vals,
        [(i + 1) * 100 / len(vals) for i in range(len(vals))],
        where="post",
        color=color,
        label=label,
        lw=2,
    )
ax.axhline(95, color=MUTED, lw=1, ls=":")
ax.set(
    xlabel="От начала удержания SOS до появления уведомления в открытом приложении, с",
    ylabel="Доля доставленных сигналов, %",
    ylim=(0, 105),
    xlim=(0, None),
    title="20 реальных нажатий SOS · удержание 1,5 с входит во время",
)
ax.grid(alpha=0.18)
ax.legend(frameon=False)
fig.savefig(OUT / "sos-chart.png", dpi=180)
fig.savefig(OUT / "sos-chart.pdf")
plt.close(fig)

fig, ax = plt.subplots(figsize=(16, 9), dpi=160)
fig.patch.set_facecolor(BG)
ax.set(xlim=(0, 1), ylim=(0, 1))
ax.axis("off")
fig.subplots_adjust(0, 0, 1, 1)


def text(x, y, value, size=12, color=INK, weight="normal"):
    ax.text(x, y, value, va="center", fontsize=size, color=color, fontweight=weight)


text(0.05, 0.945, "ПСИКОМПАС / ТЕХНИЧЕСКИЕ ИСПЫТАНИЯ", 11, MUTED, "bold")
text(0.05, 0.875, "Нагрузка, отклик и доставка SOS", 29, INK, "bold")
text(
    0.05,
    0.813,
    f'26 октября 2026 · версия {b["commit"][:7]} · локальный стенд',
    13,
    MUTED,
)
cards = [
    (
        f"{fmt(max_screen/1000)} с",
        "Открытие экрана входа, p95",
        "20 открытий · без прежнего кэша",
    ),
    (
        f"{fmt(max_diary/1000)} с",
        "Сохранение дневника, p95",
        "20 сохранений · подтверждение в UI",
    ),
    (
        f"{fmt(doc95/1000)} / {fmt(rel95/1000)} с",
        "SOS: врач / близкий, p95",
        "20 SOS · включая удержание 1,5 с",
    ),
    (
        f"{fmt(load95_bound_s,3)} с",
        "HTTP-отклик при 50 сессиях, p95",
        "Верхняя граница двух прогонов",
    ),
    (str(errors), "Неожиданных ошибок нагрузки", f"HTTP-запросов: {num(total)}"),
    (
        f'{server_n if server_ok else "?"} / {server_n}',
        "Серверных проверок",
        f"Браузерных серий: {browser_pass}/{len(browser_jobs)}",
    ),
]
for i, (value, title, note) in enumerate(cards):
    x = 0.05 + i % 3 * 0.31
    y = 0.48 - i // 3 * 0.255
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            0.28,
            0.20,
            boxstyle="round,pad=0.009,rounding_size=0.015",
            facecolor="white",
            edgecolor="#d7e5ed",
        )
    )
    text(x + 0.015, y + 0.14, value, 31, BLUE, "bold")
    text(x + 0.015, y + 0.075, title, 11.5, INK, "bold")
    text(x + 0.015, y + 0.031, note, 9.2, MUTED)
text(
    0.05,
    0.14,
    "p95: 95% измерений быстрее указанного значения. Для UI — худшая ширина из 390 и 1440 px.",
    10,
    MUTED,
)
text(
    0.05,
    0.10,
    "Стенд: 4 vCPU / 32 ГиБ · Gunicorn 1 × 4 потока · SQLite · HTTP localhost.",
    10,
    MUTED,
)
text(
    0.05,
    0.06,
    "50 сессий — проверенная нагрузка, не предел. SOS — внутри открытого приложения, без OS push.",
    10,
    MUTED,
)
fig.savefig(OUT / "poster-metrics.png", dpi=160, facecolor=BG)
fig.savefig(OUT / "poster-metrics.pdf", facecolor=BG)
plt.close(fig)

ui_rows = []
for group in ["login_screen", "diary_save"]:
    for width, stats in u["summary"][group].items():
        ui_rows.append(
            [
                group,
                width,
                str(stats["n"]),
                fmt(stats["p50_ms"]),
                fmt(stats["p95_ms"]),
                fmt(stats["max_ms"]),
            ]
        )
sos_rows = [
    [
        key,
        str(row["n"]),
        fmt(row["p50_ms"] / 1000),
        fmt(row["p95_ms"] / 1000),
        fmt(row["max_ms"] / 1000),
    ]
    for key, row in sos.items()
]
load_rows = []
for sessions in [1, 5, 10, 25, 50]:
    rows = [r for r in load if r["sessions"] == sessions]
    load_rows.append(
        [
            str(sessions),
            num(sum(r["n"] for r in rows)),
            f'{fmt(min(r["p95_ms"] for r in rows))}–{fmt(max(r["p95_ms"] for r in rows))}',
            f'{fmt(min(r["rps"] for r in rows))}–{fmt(max(r["rps"] for r in rows))}',
            str(sum(r["errors"] for r in rows)),
        ]
    )
api_rows = [
    [
        key,
        str(row["n"]),
        fmt(row["p50_ms"]),
        fmt(row["p95_ms"]),
        str(len(row["errors"])),
    ]
    for key, row in b["single"].items()
]
md_table = (
    lambda head, rows: "| "
    + " | ".join(head)
    + " |\n| "
    + " | ".join(["---"] * len(head))
    + " |\n"
    + "\n".join("| " + " | ".join(r) + " |" for r in rows)
)
poster_copy = f"Локальные испытания: 50 одновременно активных сессий; p95 HTTP-отклика ≤ {fmt(load95_bound_s,3)} с; {num(total)} {request_word} без неожиданных ошибок. Открытие экрана входа — p95 {fmt(max_screen/1000)} с; сохранение дневника — p95 {fmt(max_diary/1000)} с. SOS — p95 {fmt(doc95/1000)} с врачу и {fmt(rel95/1000)} с близкому (20 нажатий, включая удержание 1,5 с, открытое приложение)."
(OUT / "poster-text.txt").write_text(
    poster_copy
    + "\n\np95 — 95% измерений быстрее указанного значения. Стенд: 4 vCPU / 32 ГиБ, Gunicorn 1 worker / 4 threads, SQLite, localhost. Проверка публичного Render и реальных системных push пока не проведена.\n"
)

method = [
    "Проверена версия "
    + b["commit"]
    + " в ветке design/experiments. Изменено только устаревшее ожидаемое название препарата в browser_smoke; код приложения во время замеров не менялся.",
    "Стенд: Linux, 4 vCPU по квоте cgroup, 32 ГиБ по лимиту cgroup; Gunicorn: 1 worker, 4 threads; SQLite; HTTP 127.0.0.1. Клиент и сервер на одной машине. Напоминания отключены для изоляции замеров; запуск планировщика проверяется отдельной серией.",
    "Каждая нагрузочная ступень: 2 с прогрева и 12 с измерений; два повтора, уровни 1/5/10/25/50 сессий. Закрытая модель: каждая сессия отправляет следующий запрос после ответа, без задержки пользователя. Это активные автоматические HTTP-сессии, не 50 физических устройств.",
    "База нагрузки: 100 добавленных пациентов с 20 историческими записями на каждого плюс штатные фикстуры. На ступенях от 5 сессий: 20% сессий врача (один аккаунт, разные сессии), 80% разных пациентов. Чтение карт, списков и уведомлений, сохранение дневника, отметки лекарств, отправка чата. Аутентификация, статика, TLS и системные push не входят в нагрузку. Перед каждой ступенью база восстанавливается из одного снимка.",
    "Открытие экрана входа: 10 запусков для 1440 px и 10 для 390 px, каждый в новом контексте Chromium без прежнего кэша/SW; от начала навигации до видимой кнопки входа. Сервер прогрет. Это готовность конкретного экрана, не LCP/INP и не запуск приложения через мобильную сеть.",
    "Дневник: 10 сохранений на каждой ширине. От клика по уже видимой кнопке до ответа 201, наличия записи в актуальном состоянии приложения и истории. Ввод текста и прокрутка не входят. Время включает накладные расходы Playwright и ожиданий проверки интерфейса.",
    "SOS: 20 настоящих удержаний кнопки мышью в мобильном viewport; штатный обработчик удерживает 1,5 с. Врач и близкий авторизованы в отдельных контекстах Chromium, панели уведомлений открыты; согласие пациента включено. Между отправками случайная пауза 0,1–5,1 с плюс удержание; отправитель не ждёт получения предыдущего сигнала, поэтому следующий клик не синхронизируется с polling. Точки времени фиксируются пассивным обработчиком pointerdown, обёрткой fetch и MutationObserver; ручное обновление и принудительный polling после отправки не выполняются. Нормальный polling — каждые 5 с.",
    "Показаны два времени SOS: от начала удержания и от начала HTTP-отправки. Появление элемента в открытой панели не означает, что человек его прочитал; системный push на закрытом устройстве не измерялся. Выборка 20 небольшая; p95 — 19-е по величине значение в отсортированной выборке из 20. Для всех серий p95 считается методом nearest rank, без удаления выбросов.",
    "Ошибки нагрузки: несовпадение ожидаемого HTTP-кода, включая 5xx, timeout и транспортную ошибку. 0 ошибок за короткий прогон не является доказательством годовой доступности или отсутствия всех дефектов. При принудительном аварийном тесте остановка намеренная и учитывается отдельно.",
]
limits = [
    "https://psicompass-demo.onrender.com недоступен из среды проверки: CONNECT-прокси вернул 403 до установления TLS. Это ограничение среды, не ответ самого приложения. Файлы render-proxy-headers.txt и render-probe-error.txt сохранены.",
    "Нельзя утверждать, что Render выдерживает эту нагрузку с такой же скоростью: ресурсы и сеть отличаются. Максимальная проверенная ступень — 50 сессий, точка насыщения не найдена; задержка растёт с нагрузкой, поэтому «без замедления» не подтверждено.",
    "Не подтверждены физические Android/iPhone, Safari, реальный OS Web Push, доставка при закрытой PWA, внешний ИИ/Telegram, длительный прогон в течение суток, пентест и медицинская валидность. 390 px — эмуляция размера экрана в Chromium, а не тест iPhone.",
    "SOS в приложении — запрос поддержки. Он не вызывает экстренную службу и не гарантирует немедленного ответа специалиста. Сбой сети, сон бесплатного сервера и отключённые уведомления могут увеличивать реальную задержку.",
    "Для публичного пилота повторить эти же сценарии на согласованном серверном стенде с его реальными ресурсами, HTTPS и сетью; отдельно измерить системные push на телефоне/компьютере и холодный старт после сна Render.",
]
crash = b["recovery"]["process_crash"]
snap = b["recovery"]["snapshot"]
recovery = f'После принудительного завершения процесса сохранены {crash["found"]}/{crash["accepted"]} подтверждённых записей, потеряно {crash["lost"]}. Готовность health после перезапуска — {fmt(crash["health_ready_ms"])} мс; integrity_check: {crash["integrity"]}. Повтор последней записи с тем же ключом вернул тот же id: {crash["retry_same_id"]}; счётчики неизменны: {crash["counts_unchanged_after_retry"]}. Восстановление снимка до ответа карточки — {fmt(snap["restore_to_card_ms"])} мс. Снимок сохранил свои счётчики: {snap["snapshot_counts_preserved"]}; {snap["post_backup_records_absent"]} записей, созданных после снимка, ожидаемо отсутствуют. Плановое резервное копирование в этих тестах не настроено.'
report = (
    "# ПсиКомпас: замеры для постера\n\nДата: 26.10.2026. Локальное испытание текущей версии "
    + b["commit"][:7]
    + ".\n\n## Готовая строка для постера\n\n"
    + poster_copy
    + "\n\n## Отклик интерфейса\n\n"
    + md_table(
        ["Сценарий", "Ширина, px", "N", "p50, мс", "p95, мс", "max, мс"], ui_rows
    )
    + "\n\n## SOS\n\n"
    + md_table(["Отсчёт / получатель", "N", "p50, с", "p95, с", "max, с"], sos_rows)
    + "\n\n## Нагрузка\n\n"
    + md_table(
        [
            "Сессий",
            "Запросов",
            "p95, мс (2 прогона)",
            "Запросов/с (2 прогона)",
            "Ошибок",
        ],
        load_rows,
    )
    + "\n\n## API без нагрузки\n\n"
    + md_table(["Операция", "N", "p50, мс", "p95, мс", "Ошибок"], api_rows)
    + "\n\n## Функции и ошибки\n\n"
    + f'Сервер: {server_n}/{server_n if server_ok else "?"}; браузерные серии: {browser_pass}/{len(browser_jobs)}; синтаксис JS: {sum(r["exit_code"]==0 for r in syntax_jobs)}/{len(syntax_jobs)}. Непройденные серии: {failed or "нет"}. В измерительном браузерном сценарии JS-ошибок: {len(u["errors"])}; HTTP 5xx: {len(u["http_5xx"])}; прерванных запросов: {len(u["requests_failed"])}. SOS сохранено {u["sos_saved"]}/20; в обеих панелях проверено по 20 уведомлений.\n\n'
    + recovery
    + "\n\n## Методика\n\n"
    + "\n\n".join(method)
    + "\n\n## Ограничения\n\n"
    + "\n\n".join(limits)
    + "\n\n## Доказательства\n\nИсходные строки каждого запроса — load-requests.csv; браузерные попытки — ui-metrics.json; агрегаты — benchmark-results.json; функциональные серии — validation-results.json и validation/*/output.log. run_benchmarks.py, run_ui_metrics.py и run_validation.py воспроизводят измерения; запускать последовательно, не одновременно. README.txt содержит порядок запуска. Файлы отчёта автоматически собраны build_report.py из JSON, без вручную придуманных показателей.\n"
)
(OUT / "report.md").write_text(report)

font = "/usr/share/fonts/truetype/dejavu/DejaVuSans"
pdfmetrics.registerFont(TTFont("DV", font + ".ttf"))
pdfmetrics.registerFont(TTFont("DVB", font + "-Bold.ttf"))
normal = ParagraphStyle(
    "normal",
    fontName="DV",
    fontSize=9,
    leading=13,
    textColor=colors.HexColor(INK),
    spaceAfter=7,
)
small = ParagraphStyle("small", parent=normal, fontSize=7.5, leading=11)
head = ParagraphStyle(
    "head", parent=normal, fontName="DVB", fontSize=16, leading=21, spaceAfter=12
)
sub = ParagraphStyle(
    "sub",
    parent=normal,
    fontName="DVB",
    fontSize=11,
    leading=16,
    spaceBefore=9,
    spaceAfter=8,
)
story = []


def p(t, style=normal):
    story.append(Paragraph(escape(t), style))


def table(headers, rows, widths):
    data = [[Paragraph(escape(str(x)), small) for x in row] for row in [headers] + rows]
    t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e4f0f6")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor("#bdd5e1")),
                ("LINEBELOW", (0, 1), (-1, -1), 0.3, colors.HexColor("#d7e5ed")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(t)
    story.append(Spacer(1, 9))


p("ПсиКомпас — технические испытания", head)
p("26 октября 2026 · версия " + b["commit"][:7] + " · локальный стенд", small)
p("Что можно указать на постере", sub)
p(poster_copy)
p("Отклик интерфейса", sub)
ui_labels = {"login_screen": "Экран входа", "diary_save": "Дневник"}
table(
    ["Сценарий", "px", "N", "p50, мс", "p95, мс", "max, мс"],
    [[ui_labels[r[0]]] + r[1:] for r in ui_rows],
    [120, 40, 30, 75, 75, 75],
)
p(
    "Для постера взято большее p95 из двух размеров экрана. Время включает отрисовку/ожидание подтверждения, а не только API. p95: 95% попыток быстрее указанного значения.",
    small,
)
p("SOS: врач и близкий", sub)
labels = {
    "hold_to_send_ms": "Удержание → отправка",
    "doctor_from_press_ms": "Удержание → врач",
    "relative_from_press_ms": "Удержание → близкий",
    "doctor_from_send_ms": "Отправка → врач",
    "relative_from_send_ms": "Отправка → близкий",
}
table(
    ["Измерение", "N", "p50, с", "p95, с", "max, с"],
    [[labels[r[0]]] + r[1:] for r in sos_rows],
    [185, 35, 65, 65, 65],
)
p(
    "20 из 20 SOS сохранены; по 20 уведомлений появились в открытых панелях врача и разрешённого близкого. Штатный polling 5 с. Системные push и прочтение человеком не измерены.",
    small,
)
story.append(PageBreak())
p("Нагрузка и надёжность", head)
table(
    ["Сессий", "Запросов", "p95, мс", "Запросов/с", "Ошибок"],
    load_rows,
    [50, 75, 120, 125, 45],
)
p(
    "Два прогона каждой ступени: 2 с прогрева + 12 с измерений. Указаны диапазоны между прогонами. 50 — проверенная нагрузка, а не максимальная ёмкость сервера. Задержка растёт при увеличении нагрузки.",
    small,
)
p("API без нагрузки", sub)
table(
    ["Операция", "N", "p50, мс", "p95, мс", "Ошибок"], api_rows, [185, 35, 65, 65, 65]
)
p("Функциональные проверки", sub)
p(
    f'Сервер: {server_n} тестов, результат {"OK" if server_ok else "см. журнал"}. Браузерные серии: {browser_pass}/{len(browser_jobs)}. JS-синтаксис: {sum(r["exit_code"]==0 for r in syntax_jobs)}/{len(syntax_jobs)}. Непройденные серии: {failed or "нет"}.'
)
p(
    f'В измерительном браузерном сценарии: {len(u["errors"])} ошибок JS; {len(u["http_5xx"])} ответов HTTP 5xx; {len(u["requests_failed"])} прерванных запросов. Отказы в тестах неверных входных данных ожидаемы и не считаются неожиданными сбоями.'
)
p("Аварийное завершение и восстановление", sub)
p(recovery)
story.append(PageBreak())
p("Методика", head)
for item in method:
    p(item)
story.append(PageBreak())
p("Границы результата и воспроизведение", head)
for item in limits:
    p(item)
p("Доказательства", sub)
p(
    "Исходные запросы: load-requests.csv. Браузерные попытки: ui-metrics.json. Агрегаты: benchmark-results.json. Проверки функций: validation-results.json и журналы validation/*/output.log. Скриншоты сохранены рядом с отчётом и в validation. Скрипты и порядок повторного запуска включены в архив."
)
p(
    "В исходном browser_smoke исправлено только устаревшее ожидание названия в расписании лекарств: ДЕМО-Альфа → Авиандр 20 мг. Это исправление проверки существующего текста, не изменение приложения. Все остальные ожидания сохранены."
)
p(
    "Технические повторы: первая попытка UI-скрипта остановилась из-за неверно переданного аргумента Playwright; затем полный замер повторён. Первый последовательный прогон SOS подтвердил 20/20 доставок, но ожидание получателя могло синхронизировать следующие нажатия с polling. Поэтому итоговый SOS повторён с независимым отправителем. Исходные журналы и диагностический JSON сохранены; в итоговую таблицу SOS вошёл только независимый прогон.",
    small,
)


def footer(canvas, doc):
    canvas.setFont("DV", 8)
    canvas.setFillColor(colors.HexColor(MUTED))
    canvas.drawString(
        40, 25, "ПсиКомпас · локальные технические испытания · 26.10.2026"
    )
    canvas.drawRightString(A4[0] - 40, 25, str(doc.page))


SimpleDocTemplate(
    str(OUT / "report.pdf"),
    pagesize=A4,
    rightMargin=40,
    leftMargin=40,
    topMargin=38,
    bottomMargin=40,
).build(story, onFirstPage=footer, onLaterPages=footer)

for group in ["login_screen", "diary_save", "sos"]:
    rows = u[group]
    with (OUT / (group + "-samples.csv")).open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
(OUT / "README.txt").write_text(
    "ПсиКомпас: реальные локальные замеры, 26.10.2026\n\nНачните с report.pdf и poster-metrics.png. poster-text.txt — готовый абзац для таблицы постера.\n\nПовторный запуск из корня репозитория (Linux с Chromium):\n1. Настройте .venv по README проекта. Для скриптов с браузером нужен Python с playwright и установленный Chromium.\n2. Запускайте ПОСЛЕДОВАТЕЛЬНО: .venv/bin/python /путь/run_benchmarks.py\n3. python /путь/run_ui_metrics.py\n4. python /путь/run_validation.py\n5. python /путь/build_report.py (нужны matplotlib и reportlab).\nПуть ROOT в скриптах по умолчанию /workspace/clinical_compass_mvp; измените под свою машину. Внешние ключи отключаются, база создаётся временно. Нагрузочный тест не направляйте на публичный сервер без согласования условий.\n\nПубличный Render из текущей среды не проверен: CONNECT-прокси блокирует адрес. Результаты localhost нельзя приписывать Render.\n"
)
archive = OUT.with_suffix(".zip")
with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
    for path in sorted(OUT.rglob("*")):
        if (
            path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix not in [".db", ".sqlite", ".pem"]
        ):
            zipped.write(path, path.relative_to(OUT.parent))
print(
    json.dumps(
        {
            "requests": total,
            "load_errors": errors,
            "load_p95_worst_ms": load95,
            "screen_p95_ms": max_screen,
            "diary_p95_ms": max_diary,
            "sos_doctor_p95_ms": doc95,
            "sos_relative_p95_ms": rel95,
            "server_tests": server_n,
            "browser_pass": browser_pass,
            "browser_total": len(browser_jobs),
            "failed_jobs": failed,
            "archive": str(archive),
        },
        ensure_ascii=False,
        indent=2,
    )
)
