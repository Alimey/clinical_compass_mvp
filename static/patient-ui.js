"use strict";

// Patient screens from the team's second revision: one page per menu entry.
const stripHeading = (html) => {
  const doc = new DOMParser().parseFromString(html, "text/html");
  doc.querySelectorAll(".page-heading").forEach((node) => node.remove());
  return doc.body.innerHTML;
};
const dayOffset = (day, offset) =>
  new Date(Date.parse(day + "T12:00:00Z") + offset * 86400000)
    .toISOString()
    .slice(0, 10);
let flowerQueue = Promise.resolve(),
  flowerSerial = 0,
  insightRequest = 0;
const pendingFlowers = new Map();
const treeTapAnimations = new WeakMap();
const treeMotionPreference = matchMedia("(prefers-reduced-motion: reduce)");
treeMotionPreference.addEventListener("change", () => {
  if (treeMotionPreference.matches)
    document
      .querySelectorAll(".tree-tap, .flower-bloom")
      .forEach((node) =>
        node.getAnimations().forEach((animation) => animation.cancel()),
      );
});
const newPracticeId = () =>
  globalThis.crypto?.randomUUID?.() ||
  Date.now() + "-" + Math.random().toString(36).slice(2);
function flowerDots(flower) {
  const radius = flower.kind
    ? Math.max(8, Number(flower.radius) || 8)
    : Math.min(4.5, Math.max(3, Number(flower.radius) || 3.75));
  const color = {
    medication: "#e4b83f",
    visit: "#5199dc",
    diary: "#a786c9",
    activity: "#6bad81",
  }[flower.kind];
  return `<g data-flower="${e(flower.id)}" transform="translate(${Number(flower.x).toFixed(2)} ${Number(flower.y).toFixed(2)})"><g class="flower-bloom"><circle cx="0" cy="0" r="${radius.toFixed(2)}" fill="${color || "#f2a3b9"}"/><circle cx="${(radius * 1.16).toFixed(2)}" cy="${(-radius * 0.83).toFixed(2)}" r="${(radius * 0.66).toFixed(2)}" fill="${color || "#e77f9e"}"/></g></g>`;
}
function visibleTreeFlowers() {
  return [
    ...(state.wellbeing?.tree_flowers || []),
    ...(state.wellbeing?.tree_rewards || []),
    ...Array.from(pendingFlowers.values()).filter(
      (f) => f.owner === state.user?.id,
    ),
  ];
}
function treeFlowerMarkup() {
  return visibleTreeFlowers().map(flowerDots).join("");
}
function syncTreeFlowers() {
  const flowers = visibleTreeFlowers(),
    wanted = new Set(flowers.map((f) => String(f.id)));
  document.querySelectorAll(".tree-flowers").forEach((group) => {
    const existing = new Set();
    for (const node of [...group.children]) {
      if (!wanted.has(node.dataset.flower)) node.remove();
      else existing.add(node.dataset.flower);
    }
    for (const flower of flowers)
      if (!existing.has(String(flower.id)))
        group.insertAdjacentHTML("beforeend", flowerDots(flower));
  });
}
function animateTreeTap(button, flower) {
  if (treeMotionPreference.matches) return;
  const tree = button.querySelector(".tree-tap");
  if (!tree?.animate) return;
  const previous = treeTapAnimations.get(tree),
    start = getComputedStyle(tree).transform;
  previous?.cancel();
  const direction = flower.x < 150 ? 1 : -1;
  treeTapAnimations.set(
    tree,
    tree.animate(
      [
        { transform: start },
        { transform: `rotate(${direction * 2.5}deg)`, offset: 0.16 },
        { transform: `rotate(${direction * -1.7}deg)`, offset: 0.4 },
        { transform: `rotate(${direction * 0.9}deg)`, offset: 0.64 },
        { transform: `rotate(${direction * -0.35}deg)`, offset: 0.83 },
        { transform: "rotate(0deg)" },
      ],
      { duration: 950, easing: "ease-in-out" },
    ),
  );
  document
    .querySelectorAll(
      `.tree-flowers [data-flower="${flower.id}"] .flower-bloom`,
    )
    .forEach((node) =>
      node.animate(
        [
          { transform: "scale(.12)", opacity: 0 },
          { transform: "scale(1.22)", opacity: 1, offset: 0.55 },
          { transform: "scale(.94)", offset: 0.8 },
          { transform: "scale(1)", opacity: 1 },
        ],
        { duration: 620, easing: "ease-out" },
      ),
    );
}
function plantFlower(event, button) {
  const owner = state.user.id,
    patient = state.selected;
  const crown = button.querySelector(".tree-crown");
  let point = { x: 150, y: 110 };
  if (event.detail && crown?.getScreenCTM())
    point = new DOMPoint(event.clientX, event.clientY).matrixTransform(
      crown.getScreenCTM().inverse(),
    );
  const flower = {
    id: `local-${++flowerSerial}`,
    owner,
    x: Math.max(7, Math.min(290, point.x)),
    y: Math.max(7, Math.min(290, point.y)),
    radius: Number((3 + Math.random() * 1.5).toFixed(2)),
  };
  pendingFlowers.set(flower.id, flower);
  syncTreeFlowers();
  animateTreeTap(button, flower);
  flowerQueue = flowerQueue
    .catch(() => {})
    .then(async () => {
      if (state.user?.id !== owner || state.user.role !== "patient") {
        pendingFlowers.delete(flower.id);
        return;
      }
      try {
        const result = await api(
          `/api/patients/${patient}/tree`,
          { x: flower.x, y: flower.y, radius: flower.radius },
          { "Idempotency-Key": flower.id + "-" + owner + "-" + Date.now() },
        );
        if (state.user?.id !== owner) return;
        state.wellbeing.tree_blossoms = result.blossoms;
        const flowers = state.wellbeing.tree_flowers || [];
        if (!flowers.some((f) => f.id === result.flower.id))
          flowers.push(result.flower);
        state.wellbeing.tree_flowers = flowers.slice(-120);
        document
          .querySelectorAll(`.tree-flowers [data-flower="${flower.id}"]`)
          .forEach((node) => (node.dataset.flower = String(result.flower.id)));
      } catch (error) {
        if (state.user?.id === owner)
          toast("Не удалось сохранить цветок. " + error.message, true);
      } finally {
        pendingFlowers.delete(flower.id);
        if (state.user?.id === owner) syncTreeFlowers();
      }
    });
}
function weeklyActivity() {
  const today = care().today;
  const weekday = (new Date(today + "T12:00:00Z").getUTCDay() + 6) % 7;
  const monday = dayOffset(today, -weekday),
    sunday = dayOffset(monday, 6);
  const plans = (state.wellbeing?.plans || []).filter(
    (p) => p.status !== "cancelled" && p.day >= monday && p.day <= sunday,
  );
  const seconds = (key) =>
    prototypeContent.exercises.find((i) => i.id === key)?.min * 60 || 0;
  const planned = plans.reduce((sum, p) => sum + seconds(p.activity_key), 0);
  const plannedCompleted = plans
    .filter((p) => p.status === "done")
    .reduce((sum, p) => sum + seconds(p.activity_key), 0);
  const extraCompleted = (state.wellbeing?.activities || [])
    .filter(
      (a) =>
        seconds(a.activity_key) > 0 &&
        clinicDay(a.created_at) >= monday &&
        clinicDay(a.created_at) <= sunday &&
        !(state.wellbeing?.plans || []).some(
          (p) => p.completed_at === a.created_at,
        ),
    )
    .reduce((sum, a) => sum + a.duration_seconds, 0);
  const completed = plannedCompleted + extraCompleted;
  const value = (n) =>
    (n / 3600).toLocaleString("ru-RU", { maximumFractionDigits: 1 });
  return `<section class="card weekly-activity"><div class="card-heading"><h2>Активность за неделю</h2><strong>${value(completed)} ч / ${value(planned)} ч</strong></div><progress max="${planned || completed || 1}" value="${completed}" aria-label="Выполнено из запланированных часов"></progress>${!planned ? '<p class="caption">Добавьте упражнения в календарь.</p>' : ""}</section>`;
}
function patientDailyCalendar() {
  const selected = state.calendarDay || care().today,
    reports = state.detail.reports;
  return `${monthGrid(
    state.calendarMonth || selected.slice(0, 7),
    selected,
    reports.map((r) => ({ ...r, day: clinicDay(r.created_at) })),
    "diary",
  )}<div id="report-history" class="daily-saved">${
    reports
      .filter((r) => clinicDay(r.created_at) === selected)
      .map(
        (r) =>
          `<details class="saved-day"><summary>${e(timeLabel(r.created_at))} · настроение ${r.mood}/10 · тревога ${r.anxiety}/10</summary>${reportList([r])}</details>`,
      )
      .join("") || '<p class="caption">За выбранный день записей пока нет.</p>'
  }</div>`;
}
function patientDaily() {
  const previous = state.diary;
  state.diary = "form";
  const doc = new DOMParser().parseFromString(sectionDiary(), "text/html");
  state.diary = previous;
  const form = doc.querySelector("#report-form");
  form.querySelector(".card-heading").innerHTML =
    `<h2>Запись состояния · ${e(dayLabel(care().today))}</h2>`;
  return `<section class="card" id="daily-calendar">${patientDailyCalendar()}</section>${form.outerHTML}`;
}
function chartSeries(items, series, label) {
  if (!items.length) return '<p class="muted">Пока нет данных.</p>';
  const x = (i) =>
    items.length === 1 ? 320 : 38 + (564 * i) / (items.length - 1);
  return `<div class="chart-legend">${series.map(([key, title, color]) => `<span><svg width="10" height="10" aria-hidden="true"><circle cx="5" cy="5" r="4" fill="${color}"/></svg>${title}</span>`).join("")}</div><svg class="patient-trend" viewBox="0 0 640 220" role="img" aria-label="${label}">${[0, 5, 10].map((v) => `<path d="M38 ${180 - v * 15}H610" stroke="var(--line)"/><text x="8" y="${184 - v * 15}" fill="var(--muted)" font-size="18">${v}</text>`).join("")}${series
    .map(([key, title, color]) => {
      // Split at missing observations, rather than filling gaps with zeroes.
      const segments = [];
      let segment = [];
      items.forEach((item, i) => {
        if (item[key] == null) {
          if (segment.length) segments.push(segment);
          segment = [];
        } else segment.push([x(i), 180 - item[key] * 15]);
      });
      if (segment.length) segments.push(segment);
      return segments
        .map(
          (points) =>
            `<polyline points="${points.map((p) => p.join(",")).join(" ")}" fill="none" stroke="${color}" stroke-width="3"/>${points.map(([cx, cy]) => `<circle cx="${cx}" cy="${cy}" r="4" fill="${color}"/>`).join("")}`,
        )
        .join("");
    })
    .join(
      "",
    )}<text x="38" y="211" fill="var(--muted)" font-size="18">${e(shortDate(items[0].created_at))}</text><text x="610" y="211" text-anchor="end" fill="var(--muted)" font-size="18">${e(shortDate(items[items.length - 1].created_at))}</text></svg>`;
}
function complaintsCalendar() {
  const today = care().today,
    days = Array.from({ length: 14 }, (_, i) => dayOffset(today, i - 13));
  const reports = state.detail.reports;
  const categories = [
    ["adverse", "Побочные эффекты"],
    ["body", "Тело и сон"],
    ["urgent", "Срочные"],
  ];
  return `<div class="complaints-calendar">${categories
    .map(
      ([key, title]) =>
        `<div class="complaint-week"><span>${title}</span><div>${days
          .map((day) => {
            const entries = reports.filter(
              (r) => clinicDay(r.created_at) === day,
            );
            const texts = entries
              .map((r) => r.adverse_effects || "")
              .filter(Boolean);
            const marked =
              key === "urgent"
                ? entries.some((r) => r.safety_signal)
                : key === "body"
                  ? texts.some((t) => /сон|тел|бол|голов|устал|напряж/i.test(t))
                  : texts.length > 0;
            return `<button class="complaint-day ${marked ? key : ""}" data-patient="complaint-day" data-day="${day}" aria-label="${e(dayLabel(day))}, ${title}: ${marked ? "есть запись" : "нет отметки"}" title="${e(dayLabel(day))}">${day.slice(-2)}</button>`;
          })
          .join("")}</div></div>`,
    )
    .join("")}</div><div id="complaint-day-details" role="status"></div>`;
}
function scaleChart() {
  const scales = [...(ws().scale_series || [])].reverse();
  const labels = { gad7: "GAD-7", phq9: "PHQ-9", hama: "HAM-A" };
  if (!scales.length)
    return '<p class="muted">График появится после заполнения шкал.</p>';
  const series = Object.keys(labels).filter((key) =>
    scales.some((s) => s.kind === key),
  );
  return series
    .map((key) => {
      const values = scales.filter((s) => s.kind === key),
        max = { gad7: 21, phq9: 27, hama: 56 }[key];
      const x = (i) =>
        values.length === 1 ? 320 : 38 + (564 * i) / (values.length - 1);
      return `<div class="scale-series"><h3>${labels[key]}</h3><svg class="patient-trend" viewBox="0 0 640 150" role="img" aria-label="${labels[key]}: сохранённые баллы"><path d="M38 112H610" stroke="var(--line)"/><polyline points="${values.map((s, i) => `${x(i)},${112 - (s.score / max) * 85}`).join(" ")}" stroke="var(--accent)" stroke-width="3" fill="none"/>${values.map((s, i) => `<circle cx="${x(i)}" cy="${112 - (s.score / max) * 85}" r="4" fill="var(--accent)"/><text x="${x(i)}" y="${100 - (s.score / max) * 85}" text-anchor="middle" fill="var(--ink)" font-size="20">${s.score}</text>`).join("")}<text x="38" y="140" fill="var(--muted)" font-size="18">${e(shortDate(values[0].created_at))}</text><text x="610" y="140" text-anchor="end" fill="var(--muted)" font-size="18">${e(shortDate(values[values.length - 1].created_at))}</text></svg></div>`;
    })
    .join("");
}
function patientGraphs() {
  const series = [...state.detail.reports]
    .filter(
      (r) =>
        clinicDay(r.created_at) >= dayOffset(care().today, -27) &&
        clinicDay(r.created_at) <= care().today,
    )
    .reverse();
  return `<section class="card"><p class="caption">Доступ специалиста к дневнику: ${pref().share_mood ? "разрешён" : "отозван"}</p><button class="button" data-action="nav" data-page="consents">Мои согласия</button></section><section class="card graph-insight"><div class="card-heading"><h2>Что видно на графиках</h2><span class="chip neutral">ИИ</span></div><div id="graph-insight" role="status">Готовлю расшифровку…</div></section><section class="card"><h2>Тревога, качество сна и энергия</h2>${chartSeries(
    series,
    [
      ["anxiety", "Тревога", "#dc9265"],
      ["sleep", "Качество сна", "#22a3db"],
      ["energy", "Энергия", "#3c9877"],
    ],
    "Тревога, качество сна и энергия от 0 до 10",
  )}</section><section class="card"><h2>Календарь жалоб</h2>${complaintsCalendar()}</section><section class="card"><h2>Шкалы</h2>${scaleChart()}</section>`;
}
async function loadGraphInsight() {
  const node = $("#graph-insight");
  if (!node) return;
  const request = ++insightRequest,
    owner = state.user.id;
  const signature = JSON.stringify([
    care().today,
    state.detail.reports.map((r) => r.id),
    ws().scale_series,
    care().medication_marks,
  ]);
  if (state.graphInsight?.signature === signature) {
    node.innerHTML = state.graphInsight.html;
    return;
  }
  if (!state.integrations?.ai?.configured) {
    node.textContent =
      "ИИ ещё не подключён. Для автоматической расшифровки нужны настройки внешней модели на сервере.";
    return;
  }
  try {
    const result = await api(
      `/api/patients/${state.selected}/chart-summary`,
      {},
    );
    if (
      request !== insightRequest ||
      state.user?.id !== owner ||
      !document.contains(node)
    )
      return;
    const html =
      result.status === "empty"
        ? "<p>Пока недостаточно записей для расшифровки.</p>"
        : `<ul>${result.items.map((text) => `<li>${e(text)}</li>`).join("")}</ul><p class="caption">Обновлено ${e(clinicDate(result.created_at))}</p>`;
    state.graphInsight = { signature, html };
    node.innerHTML = html;
  } catch (error) {
    if (
      request === insightRequest &&
      state.user?.id === owner &&
      document.contains(node)
    )
      node.textContent = "Расшифровка временно недоступна. " + error.message;
  }
}
function medicationSchedule() {
  const c = care(),
    days = Array.from({ length: 14 }, (_, i) => dayOffset(c.today, -i));
  const prescriptions = c.prescriptions.filter(
    (p) => p.starts_on <= c.today && p.ends_on >= days[13],
  );
  const marks = c.medication_marks;
  return `<section class="card medication-schedule"><h2>График приёма препаратов</h2><div class="table-scroll"><table><thead><tr><th>Дата</th>${prescriptions.map((p) => `<th>${e(p.title.split(" · ")[0])}<small>${p.times.map(e).join(" / ")} · МСК</small></th>`).join("")}<th>Другие препараты</th><th>Жалобы</th></tr></thead><tbody>${days
    .map(
      (day) =>
        `<tr><th scope="row">${day.slice(8)}.${day.slice(5, 7)}</th>${prescriptions
          .map(
            (p) =>
              `<td>${
                day < p.starts_on || day > p.ends_on
                  ? "—"
                  : p.times
                      .map((time) => {
                        const mark = marks.find(
                          (m) =>
                            m.prescription_id === p.id &&
                            m.day === day &&
                            m.scheduled_time === time,
                        );
                        const future =
                          new Date(`${day}T${time}:00+03:00`) > new Date();
                        const status = mark?.status;
                        return `<button class="dose-check ${status || ""}" data-care="medication-mark" data-id="${p.id}" data-day="${day}" data-time="${time}" data-status="${status === "taken" ? "skipped" : "taken"}" aria-label="${e(prescriptionTitle(p))} · ${day} ${time} · ${status === "taken" ? "Принято, отметить пропуск" : status === "skipped" ? "Пропущено, отметить приём" : "Отметить приём"}" aria-pressed="${status === "taken"}" ${future || !p.active ? "disabled" : ""}>${status === "taken" ? "✓" : status === "skipped" ? "×" : "—"}</button>`;
                      })
                      .join('<span class="dose-divider"> / </span>')
              }</td>`,
          )
          .join("")}<td>${
          ws()
            .entries.filter(
              (entry) =>
                entry.kind === "other_med" &&
                clinicDay(entry.created_at) === day,
            )
            .map((entry) => e(entry.data.name))
            .join(", ") || "—"
        }</td><td>${
          state.detail.reports
            .filter(
              (r) =>
                clinicDay(r.created_at) === day &&
                (r.adverse_effects || r.safety_signal),
            )
            .map(
              (r) =>
                `${e(r.adverse_effects)}${r.safety_signal ? '<span class="chip red">Срочная отметка</span>' : ""}`,
            )
            .join("<br>") || "—"
        }</td></tr>`,
    )
    .join(
      "",
    )}</tbody></table></div>${!prescriptions.length ? '<p class="caption">На этот период нет назначений.</p>' : ""}</section>`;
}
function patientDiaryScreen() {
  const active = sub("diary", "daily");
  const tabs = sectionTabs(
    "diary",
    [
      ["daily", "Дневник"],
      ["charts", "Графики"],
      ["meds", "Препараты"],
      ["scales", "Шкалы"],
      ["notes", "Записи"],
    ],
    "daily",
  );
  if (active === "daily") return tabs + patientDaily();
  if (active === "charts") return tabs + patientGraphs();
  if (active === "meds") return tabs + medicationSchedule();
  if (active === "scales")
    return tabs + assessmentPage(false) + stripHeading(surveysPage());
  return (
    tabs +
    `<section class="card"><h2>Дневник питания</h2>${entryForm("food", [
      ["time", "Время", "time"],
      ["meal", "Приём пищи"],
      ["what", "Что ели"],
      ["appetite", "Аппетит"],
      ["feeling", "В каком состоянии"],
    ])}${entriesList("food")}</section><section class="card"><h2>Заметки</h2>${entryForm("note", [["text", "Что хочется записать", "textarea"]], false)}${entriesList("note")}</section>`
  );
}
function schoolVideos(items) {
  return `<section class="card school-videos">${items.map((item) => `<details class="course-item"><summary>${e(item.t)} · ${item.min} мин</summary><div class="video-placeholder" role="img" aria-label="Место для видеоурока"><span aria-hidden="true">▷</span><strong>Видео появится здесь</strong></div></details>`).join("")}</section>`;
}
function patientSettingsGeneral() {
  const push = state.integrations?.push?.subscriptions;
  return `<section class="card"><h2>Уведомления и установка PWA</h2><div class="proposal-actions"><button class="button primary" data-ui="install">Установить PWA</button><button class="button" data-care="enable-push">Подключить push в браузере</button><button class="button quiet" data-care="disable-push">Отключить push</button></div><p class="caption">${push ? "Подписка браузера сохранена." : "Push ещё не подключены."} Для доставки нужны разрешение браузера, HTTPS и работающий сервер.</p><p class="caption">На iPhone: Safari → «Поделиться» → «На экран Домой». На Android: меню браузера → «Установить приложение».</p></section>`;
}
function patientConsentScreen() {
  const doc = new DOMParser().parseFromString(sectionSettings(), "text/html");
  const offline = doc.querySelector("#offline-save-form")?.closest(".card");
  return (
    stripHeading(consentsPage()) +
    '<section class="card"><h2>Пригласить близкого</h2><p>Близкий создаст свой аккаунт по ссылке. Доступ к сигналам включается вами в согласиях выше.</p><button class="button primary" data-registration="invite-relative">Создать приглашение</button><div id="relative-invite-result"></div></section>' +
    (offline?.outerHTML || "")
  );
}
function crisisSteps(key, steps) {
  return `<details class="card emotion-accordion" data-emotion="${key}"><summary>${steps[0]}${icon("plus")}</summary><div class="emotion-step" data-step="0"><p class="caption step-label">Шаг 1 из ${steps.length - 1}</p><p class="emotion-current">${e(steps[1])}</p><button class="button primary" data-patient="emotion-next" data-key="${key}">Дальше</button></div>${key === "harm" ? '<a class="button danger" href="tel:112">Позвонить 112</a>' : ""}</details>`;
}
function updatePatientScreen() {
  if (state.user?.role !== "patient") return;
  if ($("#graph-insight")) loadGraphInsight();
  const weekly = $("#weekly-activity");
  if (weekly) weekly.innerHTML = weeklyActivity();
}
async function completePractice(root, key) {
  if (root.dataset.completion) return;
  const owner = state.user.id,
    patient = state.selected;
  root.dataset.completion = "saving";
  const session =
    root.dataset.session || (root.dataset.session = newPracticeId());
  const workspace = root.querySelector(".practice-workspace");
  workspace.innerHTML =
    '<div class="practice-success" role="status"><strong>Упражнение завершено!</strong><p>Сохраняю отметку…</p></div>';
  try {
    await api(
      `/api/patients/${patient}/wellbeing`,
      { activity: key },
      { "Idempotency-Key": session },
    );
    if (state.user?.id !== owner) return;
    root.dataset.completion = "saved";
    await refreshActivities();
    if (document.contains(root))
      workspace.innerHTML =
        '<div class="practice-success" role="status"><span aria-hidden="true">✓</span><h3>Вы молодец!</h3><p>Упражнение завершено, счётчик обновлён.</p></div>';
  } catch (error) {
    if (state.user?.id !== owner) return;
    root.dataset.completion = "error";
    workspace.innerHTML = `<div class="practice-success" role="status"><h3>Упражнение завершено</h3><p>Отметка пока не сохранена.</p><button class="button" data-patient="retry-practice" data-key="${key}">Повторить сохранение</button></div>`;
  }
}
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-patient]");
  if (!button || !state.user || button.disabled) return;
  const action = button.dataset.patient;
  if (action === "emotion-next") {
    const panel = button.closest(".emotion-step"),
      steps = emotionSteps[button.dataset.key].slice(1);
    const next = Number(panel.dataset.step) + 1;
    panel.dataset.step = String(next);
    if (next >= steps.length) {
      panel.innerHTML =
        '<p>Можно повторить упражнение, если вам это подходит.</p><button class="button" data-patient="emotion-restart">Начать снова</button>';
      return;
    }
    panel.querySelector(".emotion-current").textContent = steps[next];
    panel.querySelector(".step-label").textContent =
      `Шаг ${next + 1} из ${steps.length}`;
  } else if (action === "emotion-restart") {
    const details = button.closest("[data-emotion]");
    const doc = new DOMParser().parseFromString(
      crisisSteps(
        details.dataset.emotion,
        emotionSteps[details.dataset.emotion],
      ),
      "text/html",
    );
    details
      .querySelector(".emotion-step")
      .replaceWith(doc.querySelector(".emotion-step"));
  } else if (action === "complaint-day") {
    const records = state.detail.reports.filter(
      (r) => clinicDay(r.created_at) === button.dataset.day,
    );
    $("#complaint-day-details").innerHTML =
      `<p class="caption">${e(dayLabel(button.dataset.day))}</p>${
        records
          .filter((r) => r.adverse_effects || r.safety_signal)
          .map(
            (r) =>
              `<p>${e(r.adverse_effects || "")} ${r.safety_signal ? "Отмечен срочный сигнал." : ""}</p>`,
          )
          .join("") || '<p class="caption">Жалоб не отмечено.</p>'
      }`;
  } else if (action === "retry-practice") {
    const root = button.closest("[data-practice]");
    delete root.dataset.completion;
    await completePractice(root, button.dataset.key);
  }
});
