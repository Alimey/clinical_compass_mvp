"use strict";
const $ = (q) => document.querySelector(q);
const e = (v) =>
  String(v ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const paths = {
  home: "M3 10 12 3l9 7M5 9v12h5v-7h4v7h5V9",
  users:
    "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M16 3a4 4 0 0 1 0 8M22 21v-2a4 4 0 0 0-3-3.87M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0",
  chat: "M21 11a8 8 0 0 1-8 8H7l-5 3 2-6a8 8 0 1 1 17-5ZM8 9h8M8 13h5",
  bell: "M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4",
  arrow: "m9 5 7 7-7 7",
  back: "m15 5-7 7 7 7",
  check: "m5 12 4 4L19 6",
  book: "M4 3h13a3 3 0 0 1 3 3v15H7a3 3 0 0 1-3-3V3ZM4 17h16M8 7h8M8 11h5",
  shield: "m12 2 9 4v6c0 5-9 10-9 10S3 17 3 12V6l9-4ZM8 12l3 3 5-6",
  heart:
    "M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z",
  chart: "M3 3v18h18M7 14l4-4 4 2 5-7",
  clock: "M12 8v5l3 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0",
  refresh: "M20 11a8 8 0 1 0-2 7M20 4v7h-7",
  exit: "M9 21H4V3h5M9 12h12m-5-5 5 5-5 5",
  search: "M21 21l-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0",
  send: "m22 2-7 20-4-9L2 9 22 2ZM22 2 11 13",
  plus: "M12 5v14M5 12h14",
  leaf: "M20 3C8 2 2 9 5 16s15 6 15-13ZM5 19 15 9",
  run: "M15 4h.01M17 4a2 2 0 1 1-4 0 2 2 0 0 1 4 0ZM4 11l4-3 4 2 3-3 4 3h3M12 10l-3 5-5 5M10 14l5 2-1 6M3 15h3",
  gear: "M9 3h6l1 3 3 1 2 5-2 5-3 1-1 3H9l-1-3-3-1-2-5 2-5 3-1 1-3ZM16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0",
  info: "M12 11v6M12 7h.01M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0",
  alert: "m12 3 10 18H2L12 3ZM12 9v5M12 17h.01",
  sun: "M12 3v2M12 19v2M3 12h2M19 12h2M5 5l2 2M17 17l2 2M5 19l2-2M17 7l2-2M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0",
};
const icon = (name) =>
  `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="${paths[name] || paths.info}"/></svg>`;
const initials = (name) =>
  name
    .split(" ")
    .slice(0, 2)
    .map((v) => v[0])
    .join("");
const date = (v) =>
  v
    ? new Date(v).toLocaleString("ru-RU", {
        dateStyle: "medium",
        timeStyle: "short",
      })
    : "Пока нет записей";
const shortDate = (v) =>
  new Date(v).toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
const patientNavigation = [
  ["overview", "home", "Мой день"],
  ["diary", "book", "Дневник"],
  ["move", "run", "Движение"],
  ["learn", "leaf", "Знания"],
  ["help", "heart", "Помощь"],
  ["messages", "chat", "Врач"],
  ["schedule", "clock", "Консультации"],
];
const patientTools = [["settings", "gear", "Настройки"]];
function observationLabel(patient) {
  return patient?.observed_since
    ? "Наблюдается с " +
        new Date(patient.observed_since).toLocaleDateString("ru-RU", {
          day: "numeric",
          month: "long",
          year: "numeric",
          timeZone: "Europe/Moscow",
        })
    : "Дата начала наблюдения не указана";
}
let state = {
  user: null,
  csrf: null,
  page: "overview",
  selected: null,
  patients: [],
  detail: null,
  messages: [],
  audit: [],
  notifications: [],
  filter: "all",
  search: "",
  tab: "overview",
  diary: "form",
};
let pendingInstall,
  pollBusy = false,
  busy = false,
  toastTimer,
  selectionVersion = 0,
  resolution;
const retryKeys = new Map();
function toast(message, error = false) {
  clearTimeout(toastTimer);
  $("#toast").textContent = message;
  $("#toast").className = error ? "error" : "";
  $("#toast").hidden = false;
  toastTimer = setTimeout(
    () => {
      $("#toast").hidden = true;
    },
    error ? 12000 : 6500,
  );
}
async function api(path, data, extra = {}) {
  const response = await fetch(path, {
    cache: "no-store",
    credentials: "same-origin",
    ...(data === undefined
      ? {}
      : {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": state.csrf || "",
            ...extra,
          },
          body: JSON.stringify(data),
        }),
  });
  const body = await response.json();
  if (!response.ok) {
    if (response.status === 401 && path !== "/api/auth/login") {
      clearSession();
      renderLogin();
    }
    throw new Error(body.error || "Не удалось выполнить запрос");
  }
  return body;
}
async function write(path, data) {
  const fingerprint = path + JSON.stringify(data);
  if (!retryKeys.has(fingerprint))
    retryKeys.set(
      fingerprint,
      globalThis.crypto?.randomUUID?.() ||
        Date.now() + "-" + Math.random().toString(36).slice(2),
    );
  const result = await api(path, data, {
    "Idempotency-Key": retryKeys.get(fingerprint),
  });
  retryKeys.delete(fingerprint);
  return result;
}
function clearSession() {
  ++selectionVersion;
  state = {
    ...state,
    user: null,
    csrf: null,
    detail: null,
    patients: [],
    messages: [],
    audit: [],
    notifications: [],
    selected: null,
  };
  retryKeys.clear();
  notificationReads.clear();
  state.notificationSource = [];
  state.notificationTotal = 0;
  $("#app-shell").hidden = true;
  $("#content").replaceChildren();
  $("#notifications-panel").hidden = true;
  $("#notification-list").replaceChildren();
  $("#decision-dialog").close();
}
function chart(reports, compact = false) {
  const values = reports.slice(0, 14).reverse();
  if (!values.length)
    return (
      '<div class="empty">' +
      icon("chart") +
      "Динамика появится после первого самоотчёта</div>"
    );
  const x = (i) =>
      values.length === 1 ? 250 : 40 + (i * 440) / (values.length - 1),
    y = (n) => 165 - Math.max(0, Math.min(10, Number(n) || 0)) * 13;
  const graphs = [
    ["mood", "#0b8cc4"],
    ["anxiety", "#d06a2b"],
  ]
    .map(
      ([field, color]) =>
        `<polyline fill="none" stroke="${color}" stroke-width="2.5" stroke-linejoin="round" points="${values.map((r, i) => `${x(i)},${y(r[field])}`).join(" ")}"/>${values.map((r, i) => `<circle cx="${x(i)}" cy="${y(r[field])}" r="3.5" fill="white" stroke="${color}" stroke-width="2"/>`).join("")}`,
    )
    .join("");
  return `<div class="legend"><span><i></i>Настроение</span><span><i></i>Тревога</span></div><svg class="trend" viewBox="0 0 520 202" role="img" aria-label="Динамика настроения и тревоги от 0 до 10. Даты и значения доступны в истории самоотчётов."><g stroke="#eff3f0" stroke-dasharray="4 4"><path d="M40 35H480M40 100H480M40 165H480"/></g><g fill="#a8b5ac" font-size="18"><text x="12" y="39">10</text><text x="18" y="104">5</text><text x="18" y="169">0</text><text x="40" y="195">${e(shortDate(values[0].created_at))}</text><text x="438" y="195">${e(shortDate(values.at(-1).created_at))}</text></g>${graphs}</svg>${compact ? "" : `<div class="chart-foot"><span>Последние ${values.length} записей · собственные оценки</span></div>`}`;
}
function heading(eyebrow, title, description, action = "") {
  return `<div class="page-heading"><div><h1>${title}</h1>${description ? `<p class="muted">${description}</p>` : ""}</div>${action ? '<div class="heading-actions">' + action + "</div>" : ""}</div>`;
}
const refreshButton = () =>
  `<button class="button" data-action="refresh" aria-label="Обновить данные">${icon("refresh")}Обновить</button>`;
const badge = (p) =>
  p.unread > 0
    ? '<span class="chip red">Обязательно</span>'
    : '<span class="chip green">На наблюдении</span>';
const avatar = (name, color = "mint", size = "") =>
  `<div class="avatar ${color} ${size}">${e(initials(name))}</div>`;
function stat(label, value, foot, glyph, color = "mint") {
  return `<div class="stat-card"><div><div class="stat-label">${label}</div><div class="stat-number">${value}</div></div><div class="stat-icon ${color}">${icon(glyph)}</div></div>`;
}
function patientRows(list) {
  return list
    .map(
      (p, i) =>
        `<div class="patient-row">${avatar(p.name, i % 2 ? "lilac" : "mint")}<div class="patient-info"><strong>${e(p.name)}</strong><small>${p.age ? e(p.age) + " лет · " : ""}${p.last_report ? e(shortDate(p.last_report)) : "Нет отчётов"}</small></div>${badge(p)}<button class="icon-button" data-action="patient" data-id="${p.id}" aria-label="Открыть ${e(p.name)}">${icon("arrow")}</button></div>`,
    )
    .join("");
}
function overview() {
  const d = state.detail,
    doctor = state.user.role === "doctor",
    last = d?.reports[0];
  if (!d)
    return (
      heading(
        "КАБИНЕТ ВРАЧА",
        `Добрый день, ${e(state.user.name.split(" ")[0])}`,
        "",
      ) +
      '<section class="card welcome-doctor"><h2>Пригласите первого пациента</h2><p>Создайте ссылку: после регистрации карточка пациента появится в вашем кабинете.</p><button class="button primary" data-care="invite">Пригласить пациента</button><div id="invite-result"></div></section>'
    );
  if (!doctor) return patientOverview();
  const alerts = state.patients.reduce((n, p) => n + p.unread, 0),
    messages = state.patients.reduce((n, p) => n + p.unread_messages, 0);
  return (
    heading(
      "КАБИНЕТ ВРАЧА",
      `Добрый день, ${e(state.user.name.split(" ")[0])}`,
      "",
      refreshButton(),
    ) +
    `<div class="stats-grid">${stat("Пациентов на наблюдении", state.patients.length, "Ваши закреплённые пациенты", "users")}${stat("Новых сигналов", alerts, alerts ? "Есть записи для просмотра" : "Все сигналы просмотрены", "shield", "peach")}${stat("Непрочитанных сообщений", messages, "Диалоги с пациентами", "chat", "lilac")}</div>
    <div class="two-columns"><div class="card"><div class="card-heading"><h2>Динамика самочувствия</h2><select id="chart-patient" aria-label="Пациент для графика">${state.patients.map((p) => `<option value="${p.id}" ${p.id === state.selected ? "selected" : ""}>${e(p.name)}</option>`).join("")}</select></div>${chart(d.reports)}</div><div class="card"><div class="card-heading"><h2>Обратить внимание</h2><span class="chip amber">${alerts} сигналов</span></div>${
      state.patients
        .filter((p) => p.unread)
        .map(
          (p) =>
            `<div class="attention-item"><span class="chip red">Сигнал безопасности</span><p><b>${e(p.name)}</b><br>Есть непросмотренные сигналы в карточке.</p><button class="button quiet small" data-action="patient" data-id="${p.id}">Открыть карточку ${icon("arrow")}</button></div>`,
        )
        .join("") ||
      '<div class="empty">' + icon("check") + "Новых сигналов нет</div>"
    }</div></div>
    <div class="section-heading"><h2>Ваши пациенты</h2><button class="button quiet small" data-action="nav" data-page="patients">Все пациенты ${icon("arrow")}</button></div><div class="card">${patientRows(state.patients)}</div>`
  );
}
function patientOverview() {
  const d = state.detail,
    last = d.reports[0],
    today = new Date().toDateString(),
    sent = last && new Date(last.created_at).toDateString() === today;
  return (
    heading(
      "МОЙ ДЕНЬ",
      `Здравствуйте, ${e(state.user.name.split(" ")[0])}`,
      "Небольшие шаги помогают замечать изменения.",
      refreshButton(),
    ) +
    `<div class="intro-card"><div><p class="eyebrow">ВРЕМЯ ДЛЯ СЕБЯ</p><h2>${sent ? "Спасибо, что ведёте дневник" : "Как вы чувствуете себя сегодня?"}</h2><p>${sent ? "Ваш последний самоотчёт сохранён. Можно посмотреть историю или добавить новую запись." : "Отметьте настроение, тревогу и самочувствие. Записи увидит ваш ведущий врач."}</p><button class="button primary" data-action="nav" data-page="diary">${icon("plus")}Заполнить дневник</button></div><div class="intro-graphic" aria-hidden="true"><span>✦</span></div></div>
    <div class="stats-grid">${stat("Настроение", last ? `${last.mood}<small> / 10</small>` : "—", "Из последнего самоотчёта", "sun")}${stat("Тревога", last ? `${last.anxiety}<small> / 10</small>` : "—", "Субъективная оценка", "heart", "lilac")}${stat("Соблюдение плана", d.adherence === null ? "—" : `${d.adherence}<small>%</small>`, "Условный индекс, 7 записей", "check", "peach")}</div>
    <div class="two-columns"><div class="card"><div class="card-heading"><h2>Моя динамика</h2><button class="button quiet small" data-action="history">История ${icon("arrow")}</button></div>${chart(d.reports)}</div><div><div class="card"><h2>На сегодня</h2><div class="routine-item"><div class="routine-icon">${icon(sent ? "check" : "book")}</div><div><h3>Заполнить дневник</h3><p>${sent ? "Сегодня уже есть запись" : "Пара минут внимания к себе"}</p></div></div><div class="routine-item"><div class="routine-icon">${icon("chat")}</div><div><h3>Оставаться на связи</h3><p>Вопросы можно обсудить с врачом</p></div></div><div class="routine-item"><div class="routine-icon">${icon("leaf")}</div><div><h3>Следовать согласованному плану</h3><p>Изменения подтверждает только врач</p></div></div></div><div class="card"><div class="patient-row">${avatar(d.doctor.name, "lilac")}<div class="patient-info"><strong>${e(d.doctor.name)}</strong><small>Ваш ведущий врач</small></div></div><button class="button full" data-action="nav" data-page="messages">${icon("chat")}Написать врачу</button></div></div></div>`
  );
}
function filteredPatients() {
  return state.patients.filter(
    (p) =>
      (state.filter !== "attention" || p.unread > 0) &&
      p.name
        .toLocaleLowerCase("ru")
        .includes(state.search.toLocaleLowerCase("ru")),
  );
}
function patientCards() {
  const list = filteredPatients();
  return list.length
    ? list
        .map(
          (p, i) =>
            `<article class="card patient-card"><div class="profile-top">${avatar(p.name, i % 2 ? "lilac" : "mint")}<div><h3>${e(p.name)}</h3><p class="caption">${e(p.age || "—")} лет · ${p.observed_since ? "Наблюдается с " + e(shortDate(p.observed_since)) + " " + new Date(p.observed_since).getFullYear() : "Дата начала наблюдения не указана"}</p></div></div>${badge(p)}<div class="mini-metrics"><div><small>Настроение</small><strong>${p.mood ?? "—"}<span> / 10</span></strong></div><div><small>Тревога</small><strong>${p.anxiety ?? "—"}<span> / 10</span></strong></div></div><p class="caption">Последняя запись: ${e(date(p.last_report))}</p><button class="button full" data-action="patient" data-id="${p.id}">Открыть карточку ${icon("arrow")}</button></article>`,
        )
        .join("")
    : '<div class="empty">Пациенты не найдены. Измените поиск или фильтр.</div>';
}
function patientsPage() {
  return (
    heading(
      "НАБЛЮДЕНИЕ",
      "Ваши пациенты",
      "Карточки, дневники и решения по каждому случаю.",
      refreshButton(),
    ) +
    `<div class="list-toolbar"><div class="search-field">${icon("search")}<input id="patient-search" type="search" aria-label="Найти пациента" placeholder="Найти пациента" value="${e(state.search)}"></div><div class="filter-group"><button data-action="filter" data-filter="all" class="${state.filter === "all" ? "active" : ""}">Все пациенты</button><button data-action="filter" data-filter="attention" class="${state.filter === "attention" ? "active" : ""}">Требуют внимания</button></div></div><div id="patient-cards" class="patient-grid">${patientCards()}</div>`
  );
}
function reportList(reports) {
  if (!reports.length)
    return '<div class="empty">' + icon("book") + "Самоотчётов пока нет</div>";
  return reports
    .map(
      (r) =>
        `<article class="report-item"><div class="report-meta"><time>${e(date(r.created_at))}</time><span class="chip ${r.safety_signal ? "red" : "neutral"}">${r.safety_signal ? "Сигнал безопасности" : "Самоотчёт"}</span></div><div class="report-values">Настроение <strong>${e(r.mood)}/10</strong> Тревога <strong>${e(r.anxiety)}/10</strong></div>${r.sleep != null || r.energy != null ? `<p class="caption">Сон: ${r.sleep == null ? "—" : e(r.sleep) + "/10"} · Энергия: ${r.energy == null ? "—" : e(r.energy) + "/10"}</p>` : ""}<p class="report-text">Соблюдение плана: ${e(r.adherence)}</p>${r.adverse_effects || r.note ? `<details><summary>Подробнее о записи</summary><p class="report-text">${r.adverse_effects ? "Самочувствие: " + e(r.adverse_effects) + "<br>" : ""}${r.note ? "Комментарий: " + e(r.note) : ""}</p></details>` : ""}</article>`,
    )
    .join("");
}
function proposals() {
  const list = state.detail.proposals.filter((p) => p.status === "pending");
  return list.length
    ? list
        .map(
          (p) =>
            `<article class="proposal ${p.tier}"><span class="chip ${p.tier === "mandatory" ? "red" : "amber"}">${p.tier === "mandatory" ? "Обязательно" : "Желательно"}</span><h3>${e(p.title)}</h3><p>${e(p.reason)}</p><small class="caption">Основание: запись от ${e(date(p.created_at))}</small><div class="proposal-actions"><button class="button small primary" data-action="resolve" data-id="${p.id}" data-status="accepted">Подтвердить</button><button class="button quiet small" data-action="resolve" data-id="${p.id}" data-status="rejected">Отклонить</button></div></article>`,
        )
        .join("")
    : '<div class="empty">' +
        icon("check") +
        "Все предложения рассмотрены</div>";
}
function alerts() {
  const list = state.detail.alerts;
  return list.length
    ? list
        .map(
          (a) =>
            `<article class="alert-card ${a.status === "reviewed" ? "reviewed" : ""}"><span class="chip ${a.status === "new" ? "red" : "green"}">${a.status === "new" ? "Новый сигнал" : "Просмотрен врачом"}</span><p>${e(a.explanation)}</p><p class="caption">${e(date(a.created_at))} · отчёт #${a.report_id}</p>${a.status === "new" ? `<button class="button small" data-action="review" data-id="${a.id}">${icon("check")}Отметить просмотренным</button>` : ""}</article>`,
        )
        .join("")
    : '<div class="empty">Сигналов безопасности нет</div>';
}
function doctorCard() {
  const d = state.detail,
    p = d.patient;
  const tabs = [
    ["overview", "Обзор"],
    ["plan", "План и варианты"],
    ["record", "Карточка"],
    ["surveys", "Опросы"],
    ["assistant", "ИИ-помощник"],
    ["chat", "Сообщения"],
    ["audit", "Журнал"],
  ];
  let content = "";
  if (state.tab === "overview")
    content = `<div class="stats-grid">${stat("Настроение", d.reports[0]?.mood ?? "—", "Последняя запись", "sun")}${stat("Тревога", d.reports[0]?.anxiety ?? "—", "Последняя запись", "heart", "lilac")}${stat("Соблюдение плана", d.adherence === null ? "—" : d.adherence + "<small>%</small>", "Условный индекс, 7 записей", "check", "peach")}</div><div class="two-columns"><div><div class="card"><div class="card-heading"><h2>Динамика состояния</h2><span class="chip neutral">0–10</span></div>${chart(d.reports)}</div><div class="card"><h2>Самоотчёты <span class="muted">· ${d.reports_total}</span></h2>${reportList(d.reports)}</div></div><div><div class="card"><div class="card-heading"><h2>Сигналы безопасности</h2>${icon("shield")}</div>${alerts()}</div><div class="card"><h2>Контекст пациента</h2><p class="profile-context">${e(d.profile.context || "Профиль не заполнен")}</p><dl class="profile-context"><dt>Цель наблюдения</dt><dd>${e(d.profile.goal)}</dd><dt>Учебное ограничение</dt><dd>${d.profile.intolerance ? "Несовместимость с " + e(d.catalog.find((c) => c.id === d.profile.intolerance)?.name || d.profile.intolerance) : "Не указано"}</dd><dt>Источник сведений</dt><dd>Вымышленный сценарий, не клинические данные</dd></dl></div></div></div>`;
  if (state.tab === "plan") content = planPage(true);
  if (state.tab === "record") content = recordsPage(true);
  if (state.tab === "surveys") content = surveysPage(true);
  if (state.tab === "assistant") content = assistantPage();
  if (state.tab === "chat") content = chatPage();
  if (state.tab === "audit")
    content = `<div class="card"><h2>Журнал действий</h2>${state.audit.length ? state.audit.map((a) => `<div class="journal-item"><time>${e(date(a.created_at))}</time><h3>${e(a.detail)}</h3><p>${e(a.actor_name)} · ${e(a.action)}</p></div>`).join("") : '<div class="empty">События появятся после действий в приложении</div>'}</div>`;
  if (state.tab === "overview") content += wellbeingSummary();
  return `<button class="back-link" data-action="nav" data-page="patients">${icon("back")}Все пациенты</button><div class="profile-banner">${avatar(p.name, "mint", "large")}<div><p class="eyebrow">КАРТОЧКА ПАЦИЕНТА · #${p.id}</p><h1>${e(p.name)}</h1><p>${e(d.profile.age || "—")} лет · ${e(observationLabel(state.patients.find((x) => x.id === p.id)))}</p></div>${badge(state.patients.find((x) => x.id === p.id) || {})}</div><div class="tabs" aria-label="Разделы карточки">${tabs.map(([id, title]) => `<button data-action="tab" data-tab="${id}" class="${state.tab === id ? "active" : ""}" aria-pressed="${state.tab === id}">${title}</button>`).join("")}</div>${content}`;
}
function planPage(doctor = false) {
  const d = state.detail,
    choice = d.catalog.find((c) => c.id === d.profile.plan);
  return `${doctor ? "" : heading("ПОДТВЕРЖДЁННЫЕ РЕШЕНИЯ", "Мой план", "Изменения появляются здесь после решения ведущего врача.", refreshButton())}
  <div class="plan-current"><span class="chip green">${choice ? "Подтверждено врачом" : "План ещё не согласован"}</span><h3>${choice ? e(choice.name) : "Решение остаётся за врачом"}</h3><p>${choice ? e(d.profile.plan_note) : "Система формирует только предложения. Выбор не применяется автоматически."}</p></div>
  ${
    doctor
      ? `<div class="section-heading"><h2>Предложения к рассмотрению</h2><span class="chip neutral">Правила ${e(d.rule_version)}</span></div><div class="two-columns"><div class="card">${proposals()}</div><div class="card"><h2>Как работает согласование</h2><div class="routine-item"><div class="routine-icon">1</div><div><h3>Проверить основание</h3><p>Посмотрите запись пациента и причину предложения</p></div></div><div class="routine-item"><div class="routine-icon">2</div><div><h3>Принять решение</h3><p>Подтвердить или отклонить с обоснованием</p></div></div><div class="routine-item"><div class="routine-icon">3</div><div><h3>Сохранить результат</h3><p>Решение записывается в журнал, пациент получает уведомление</p></div></div></div></div>
  <div class="section-heading"><h2>Вымышленные варианты сопровождения</h2></div><div class="catalog-grid">${d.catalog
    .map((c) => {
      const blocked = d.profile.intolerance === c.id,
        pending = d.proposals.some(
          (p) => p.choice === c.id && p.status === "pending",
        );
      return `<article class="option-card ${blocked ? "blocked" : ""}"><div class="option-symbol ${c.color}">${icon("leaf")}</div><span class="chip neutral">${e(c.tag)}</span><h3>${e(c.name)}</h3><p>${e(c.description)}</p><ul>${c.checks.map((x) => "<li>" + e(x) + "</li>").join("")}</ul><button class="button small" data-action="propose" data-choice="${c.id}" ${blocked || pending ? "disabled" : ""}>${blocked ? "Учебная несовместимость" : pending ? "Ожидает решения" : "Добавить к рассмотрению"}</button></article>`;
    })
    .join("")}</div>
  <div class="card"><h2>Зафиксировать отдельное решение</h2><form id="decision-form"><label for="decision">Действие</label><select id="decision" name="decision"><option>Продолжить наблюдение</option><option>Назначить очную консультацию</option><option>Рассмотреть направление к специалисту</option><option>Другое</option></select><label for="decision-note">Обоснование / заметки</label><textarea id="decision-note" name="note" required maxlength="500" rows="3" placeholder="Только вымышленный сценарий"></textarea><div class="form-footer"><small>Запись появится в истории пациента. Реальных назначений приложение не делает.</small><button class="button primary" type="submit">Сохранить решение</button></div></form></div>`
      : ""
  }
  <div class="section-heading"><h2>История решений</h2></div><div class="card">${d.decisions.length ? d.decisions.map((v) => `<div class="journal-item"><time>${e(date(v.created_at))}</time><h3>${e(v.decision)}</h3><p>${e(v.note)}</p></div>`).join("") : '<div class="empty">Подтверждённых решений пока нет</div>'}</div>`;
}
function diaryPage() {
  return (
    heading("МОЙ ДНЕВНИК", "Минута внимания к себе", "", refreshButton()) +
    `<div class="tabs"><button data-action="diary" data-mode="form" class="${state.diary === "form" ? "active" : ""}">Самоотчёт</button><button data-action="diary" data-mode="history" class="${state.diary === "history" ? "active" : ""}">История записей</button></div>` +
    (state.diary === "history"
      ? `<div class="card"><h2>Как менялось самочувствие</h2>${chart(state.detail.reports)}</div><div class="card" id="report-history"><h2>История · ${state.detail.reports_total} записей</h2><p class="caption">Показаны последние 100 записей.</p>${reportList(state.detail.reports)}</div>`
      : `<div class="two-columns"><form id="report-form" class="card"><div class="card-heading"><h2>Как вы сегодня?</h2><span class="chip green">Сегодня</span></div><label class="range-label" for="mood">Настроение <output id="mood-value" for="mood">5 / 10</output></label><input id="mood" name="mood" type="range" min="0" max="10" value="5"><div class="scale"><span>Очень плохое</span><span>Отличное</span></div><label class="range-label" for="anxiety">Тревога <output id="anxiety-value" for="anxiety">5 / 10</output></label><input id="anxiety" name="anxiety" type="range" min="0" max="10" value="5"><div class="scale"><span>Нет тревоги</span><span>Очень сильная</span></div><label for="adherence">Следовали согласованным рекомендациям?</label><select id="adherence" name="adherence"><option>Да</option><option>Частично</option><option>Нет</option><option>Не применимо</option></select><label for="adverse">Самочувствие / нежелательные явления</label><textarea id="adverse" name="adverse_effects" maxlength="500" rows="2" placeholder="Что хотелось бы обсудить с врачом?"></textarea><label for="note">Комментарий</label><textarea id="note" name="note" maxlength="500" rows="2" placeholder="Только вымышленные сведения"></textarea><label class="safety"><input id="safety" name="safety_signal" type="checkbox"><span>Есть опасения за свою безопасность или мысли о причинении себе вреда</span></label><p id="urgent" class="urgent" role="alert" hidden>При непосредственной опасности обратитесь в местные экстренные службы или за срочной медицинской помощью. Не ждите ответа в приложении: оно не обеспечивает экстренную связь.</p><div class="form-footer"><small>Запись сохранится на сервере и станет доступна вашему врачу.</small><button class="button primary" type="submit">Сохранить самоотчёт ${icon("arrow")}</button></div></form><div><div class="card"><h2>Дневник, а не диагноз</h2><div class="divider"></div><div class="routine-item"><div class="routine-icon">${icon("shield")}</div><div><h3>Ваши записи — вашему врачу</h3><p>Доступ ограничен закреплённым врачом и вашим демо-аккаунтом</p></div></div><div class="routine-item"><div class="routine-icon">${icon("clock")}</div><div><h3>Без ожидания в опасной ситуации</h3><p>Не используйте дневник для получения экстренной помощи</p></div></div></div><div class="card"><h2>Без интернета</h2><p class="caption">Для сохранения дневника нужно подключение к интернету.</p></div></div></div>`)
  );
}
function chatThread() {
  return state.messages.length
    ? state.messages
        .map(
          (m) =>
            `<div class="message ${m.sender_id === state.user.id ? "own" : ""}"><div class="message-bubble">${e(m.body)}</div><div class="message-meta">${e(m.sender_name)} · ${e(date(m.created_at))}${m.sender_id === state.user.id ? " · " + (m.read_at ? "Прочитано" : "Отправлено") : ""}</div></div>`,
        )
        .join("")
    : '<div class="empty">Начните диалог. Не используйте чат для экстренной помощи.</div>';
}
function chatPage() {
  const d = state.detail,
    partner = state.user.role === "doctor" ? d.patient : d.doctor;
  return `<div class="card chat-card"><div class="chat-heading">${avatar(partner.name, "lilac")}<div><h3>${e(partner.name)}</h3><p>${state.user.role === "doctor" ? "Пациент" : "Ведущий врач"} · синтетический диалог</p></div></div><div class="chat-thread" id="chat-thread" aria-label="Переписка">${chatThread()}</div><form class="chat-compose" id="message-form"><label class="visually-hidden" for="message-body">Сообщение</label><textarea id="message-body" name="body" required maxlength="1000" rows="2" placeholder="Написать сообщение…"></textarea><button class="button primary" type="submit" aria-label="Отправить сообщение">${icon("send")}<span>Отправить</span></button></form></div><p class="caption">Чат с врачом. Для срочной помощи звоните 112.</p>`;
}
function messagesPage() {
  if (state.user.role === "patient")
    return (
      heading(
        "НА СВЯЗИ",
        "Сообщения врачу",
        "Обсудите записи и согласованный план.",
        refreshButton(),
      ) + chatPage()
    );
  return (
    heading(
      "НА СВЯЗИ",
      "Сообщения",
      "Диалоги с вашими пациентами.",
      refreshButton(),
    ) +
    state.patients
      .map(
        (p, i) =>
          `<button class="message-list-card" data-action="open-chat" data-id="${p.id}">${avatar(p.name, i % 2 ? "lilac" : "mint")}<div><strong>${e(p.name)}</strong><small>${p.unread_messages ? "Непрочитанных: " + p.unread_messages : "Открыть переписку"}</small></div>${icon("arrow")}</button>`,
      )
      .join("")
  );
}
function scenariosPage() {
  return (
    heading(
      "ДЕМОНСТРАЦИЯ",
      "От сценария — к решению",
      "Все пациенты, правила и варианты сопровождения вымышлены.",
    ) +
    `<div class="scenario-grid"><article class="scenario-card"><span class="chip red">Сценарий 01 · внимание к безопасности</span><h2>Заметить изменение вовремя</h2><p>Александра, 29 лет. В дневнике отмечены тревога, трудности соблюдения плана и опасения за безопасность.</p><ol class="scenario-steps"><li>Открыть сигнал и проверить записи</li><li>Различить обязательные и желательные действия</li><li>Рассмотреть ДЕМО-Альфа; увидеть ограничение ДЕМО-Бета</li><li>Подтвердить или отклонить предложение с обоснованием</li></ol><button class="button" data-action="patient" data-id="2">Открыть сценарий ${icon("arrow")}</button></article><article class="scenario-card"><span class="chip green">Сценарий 02 · плановое наблюдение</span><h2>Поддержать положительную динамику</h2><p>Михаил, 37 лет. Синтетические записи показывают более высокую оценку настроения и меньшую тревогу.</p><ol class="scenario-steps"><li>Посмотреть динамику и соблюдение плана</li><li>Обсудить состояние в переписке</li><li>Добавить вымышленный вариант к рассмотрению</li><li>Зафиксировать решение и проверить журнал</li></ol><button class="button" data-action="patient" data-id="3">Открыть сценарий ${icon("arrow")}</button></article></div><div class="card"><h2>Прозрачные учебные правила</h2><div class="source-note">Версия synthetic-2.0. Придумано для демонстрации взаимодействия интерфейса и сервера. Не клинические рекомендации, не валидированные шкалы, не медицинский триаж.</div><table class="rule-table"><thead><tr><th>ПРАВИЛО</th><th>УСЛОВИЕ</th><th>ПРЕДЛОЖЕНИЕ</th></tr></thead><tbody><tr><td>S-01</td><td>Отмечены опасения за безопасность</td><td>Обязательная проверка в демо + сигнал врачу</td></tr><tr><td>S-02</td><td>Тревога ≥ 8 или настроение ≤ 2, без S-01</td><td>Желательное обсуждение консультации в демо</td></tr><tr><td>S-03</td><td>Поле самочувствия не пустое</td><td>Обязательное уточнение в демо; смысл текста не анализируется</td></tr><tr><td>S-04</td><td>Соблюдение плана: «Нет» или «Частично»</td><td>Желательное обсуждение трудностей в демо</td></tr></tbody></table><p class="caption">Индекс соблюдения: «Да» = 1, «Частично» = 0,5, «Нет» = 0; среднее по последним 7 записям, «Не применимо» исключается. Это условная визуализация, не клиническая оценка.</p></div>`
  );
}
function aboutPage() {
  return (
    heading(
      "О ПРОЕКТЕ",
      "Клинический компас",
      "Мобильное пространство для демонстрации сопровождения пациента.",
    ) +
    `<div class="card"><h2>Установка на телефон</h2><p class="caption">Нужен HTTPS-адрес сервера. Android: Chrome → меню → «Установить приложение». iPhone: Safari → «Поделиться» → «На экран Домой». По локальному HTTP можно проверить интерфейс, установка требует HTTPS.</p><div class="divider"></div><h2>Что здесь вымышлено</h2><p class="caption">Все профили и истории, правила S-01–S-04, условные индексы и варианты ДЕМО-Альфа / Бета / Гамма. Это не настоящие препараты, не шкалы и не рекомендации по лечению.</p><h2>Границы демо</h2><p class="caption">Раздельные аккаунты и серверные права демонстрируют разграничение доступа. Демо-пароль публичный, поэтому приложение не подходит для реальных персональных или медицинских данных. Push подключается отдельно и не гарантирует экстренную доставку. Нет клинической валидации или подтверждения соответствия требованиям к медицинским системам.</p><h2>Без сети</h2><p class="caption">По вашему выбору можно сохранить зашифрованную PIN-кодом копию назначений и записей в разделе «Ещё». Без чата и токенов сессии, только для просмотра. Без сохранённой копии доступна лишь оболочка.</p><p class="urgent">При непосредственной опасности обратитесь в местные экстренные службы. Не ждите ответа в приложении.</p></div>`
  );
}
function render() {
  if (!state.user) return;
  const doctor = state.user.role === "doctor";
  const nav = doctor
    ? [
        ["overview", "home", "Главное"],
        ["patients", "users", "Пациенты"],
        ["letters", "chat", "Письма"],
        ["reference", "book", "Справочник"],
        ["news", "info", "Новости"],
        ["forum", "users", "Форум"],
        ["schedule", "clock", "Мои встречи"],
      ]
    : patientNavigation;
  const roleNav =
    state.user.role === "relative"
      ? [
          ["overview", "heart", "Сигналы"],
          ["learn", "book", "Как помочь"],
          ["contacts", "chat", "Полезные контакты"],
        ]
      : nav;
  $("#navigation").innerHTML = roleNav
    .map(
      ([page, glyph, title]) =>
        `<button class="nav-item ${state.page === page || (state.page === "card" && page === "patients") ? "active" : ""}" data-action="nav" data-page="${page}" ${state.page === page ? 'aria-current="page"' : ""}>${icon(glyph)}<span>${title}</span></button>`,
    )
    .join("");
  $("#breadcrumb").textContent =
    state.page === "card"
      ? "Карточка пациента"
      : [...roleNav, ...patientTools].find((n) => n[0] === state.page)?.[2] ||
        "Обзор";
  $("#account-avatar").textContent = initials(state.user.name);
  $("#account-avatar").title = state.user.name;
  const views = {
    overview: state.user.role === "relative" ? relativePage : overview,
    patients: patientsPage,
    card: doctorCard,
    diary: extendedDiaryPage,
    plan: planPage,
    messages: extendedMessagesPage,
    scenarios: scenariosPage,
    about: aboutPage,
    schedule: schedulePage,
    settings: settingsPage,
    surveys: surveysPage,
    medications: medicationsPage,
    records: recordsPage,
    builder: builderPage,
    move: extendedMovementPage,
    learn:
      state.user.role === "relative"
        ? relativeLearningPage
        : extendedLearningPage,
    help: extendedHelpPage,
    tree: treePage,
    consents: consentsPage,
    letters: lettersPage,
    reference: referencePage,
    news: newsPage,
    forum: forumPage,
    research: researchPage,
    contacts: contactsPage,
    tour: tourPage,
  };
  const markup = (views[state.page] || overview)();
  $("#content").innerHTML =
    state.user.role === "patient"
      ? `<div class="patient-page">${markup}</div>`
      : markup;
  decoratePsicompas();
  if ($("#chat-thread"))
    $("#chat-thread").scrollTop = $("#chat-thread").scrollHeight;
}
async function load() {
  const version = ++selectionVersion;
  if (state.user?.role === "relative") {
    const data = await api("/api/relative");
    if (version === selectionVersion && state.user?.role === "relative") {
      state.relative = data;
      render();
    }
    return;
  }
  const patients = await api("/api/patients");
  if (!state.user || version !== selectionVersion) return;
  state.patients = patients;
  if (!patients.some((p) => p.id === state.selected))
    state.selected = patients[0]?.id;
  if (!state.selected) {
    const endpoints = {
      appointments: "/api/appointments",
      templates: "/api/surveys/templates",
      integrations: "/api/integrations",
      letters: "/api/letters",
      forum: "/api/forum",
      research: "/api/research",
    };
    const values = await Promise.all(
      Object.values(endpoints).map((path) => api(path)),
    );
    if (!state.user || version !== selectionVersion) return;
    Object.assign(
      state,
      Object.fromEntries(
        Object.keys(endpoints).map((key, i) => [key, values[i]]),
      ),
      {
        detail: null,
        workspace: null,
        wellbeing: null,
        messages: [],
        audit: [],
        aiRuns: [],
        escalations: [],
        slots: [],
      },
    );
    render();
    return;
  }
  const selected = state.selected;
  const [
    detail,
    messages,
    journal,
    appointments,
    slots,
    templates,
    integrations,
    aiRuns,
    escalations,
    wellbeing,
    workspace,
    letters,
    forum,
    research,
  ] = await Promise.all([
    api("/api/patients/" + selected),
    api("/api/patients/" + selected + "/messages"),
    state.user.role === "doctor"
      ? api("/api/patients/" + selected + "/audit")
      : Promise.resolve([]),
    api("/api/appointments"),
    api("/api/appointments/slots"),
    state.user.role === "doctor"
      ? api("/api/surveys/templates")
      : Promise.resolve([]),
    api("/api/integrations"),
    state.user.role === "doctor"
      ? api("/api/patients/" + selected + "/assistant")
      : Promise.resolve([]),
    state.user.role === "doctor"
      ? api("/api/escalations")
      : Promise.resolve([]),
    api("/api/patients/" + selected + "/wellbeing"),
    api("/api/patients/" + selected + "/workspace"),
    state.user.role === "doctor" ? api("/api/letters") : Promise.resolve([]),
    state.user.role === "doctor" ? api("/api/forum") : Promise.resolve([]),
    state.user.role === "doctor" ? api("/api/research") : Promise.resolve([]),
  ]);
  if (
    !state.user ||
    version !== selectionVersion ||
    selected !== state.selected
  )
    return;
  state.appointments = appointments;
  state.slots = slots.slots;
  state.templates = templates;
  state.integrations = integrations;
  state.aiRuns = aiRuns;
  state.escalations = escalations;
  state.wellbeing = wellbeing;
  state.workspace = workspace;
  state.counterClockOffset = workspace.server_now
    ? Date.now() - Date.parse(workspace.server_now)
    : 0;
  state.letters = letters;
  state.forum = forum;
  state.research = research;
  state.detail = detail;
  state.messages = messages;
  state.audit = journal;
  render();
  OfflineVault.refresh(state).catch(() => {});
  if ($("#chat-thread")) await acknowledgeMessages(selected);
}
function renderLogin(error = "") {
  $("#app-shell").hidden = true;
  $("#login-screen").hidden = false;
  const artReports = [
    { mood: 4, anxiety: 7 },
    { mood: 5, anxiety: 6 },
    { mood: 5, anxiety: 6 },
    { mood: 6, anxiety: 5 },
    { mood: 5, anxiety: 4 },
    { mood: 7, anxiety: 4 },
    { mood: 8, anxiety: 3 },
  ]
    .reverse()
    .map((r, i) => ({
      ...r,
      created_at: new Date(Date.now() - i * 86400000).toISOString(),
    }));
  $("#login-screen").innerHTML =
    `<div class="login-layout"><div class="login-form-side"><div class="brand"><span class="brand-mark">✦</span><span>Клинический компас<small>Пространство заботы</small></span></div><h1>Внимание к человеку.<br>Ясность в решениях.</h1><p>Дневник самочувствия, связь с врачом и прозрачный путь от наблюдения к решению.</p><button class="demo-login" data-action="login" data-account="doctor">${avatar("Анна Соколова", "mint")}<span><strong>Войти как врач</strong><small>Анна Соколова · кабинет и пациенты</small></span>${icon("arrow")}</button><button class="demo-login" data-action="login" data-account="patient-a">${avatar("Александра Морозова", "lilac")}<span><strong>Войти как Александра</strong><small>Пациент · дневник и личный план</small></span>${icon("arrow")}</button><button class="demo-login" data-action="login" data-account="patient-b">${avatar("Михаил Волков", "peach")}<span><strong>Войти как Михаил</strong><small>Пациент · сценарий наблюдения</small></span>${icon("arrow")}</button><p class="login-note">Все сведения и варианты сопровождения вымышлены. Демо-аккаунты общедоступны: не вводите реальные персональные или медицинские данные.</p><details><summary>Войти по логину и паролю</summary><form id="login-form"><label for="username">Логин</label><input id="username" name="username" autocomplete="username" required maxlength="80"><label for="password">Пароль</label><input id="password" name="password" type="password" autocomplete="current-password" required maxlength="200"><button class="button primary full" type="submit">Войти</button></form><p class="caption">Логины: doctor, patient-a, patient-b. Демо-пароль: compass-demo.</p></details><div id="login-error" class="login-error" role="alert" ${error ? "" : "hidden"}>${e(error)}</div></div><div class="login-art" aria-hidden="true"><div class="art-card"><div class="patient-row">${avatar("Михаил Волков", "lilac")}<div class="patient-info"><strong>Самочувствие в динамике</strong><small>Дневник · последние 7 записей</small></div></div>${chart(artReports, true)}<div class="art-stats"><div><strong>8 <small>/ 10</small></strong><small>Настроение</small></div><div><strong>3 <small>/ 10</small></strong><small>Тревога</small></div></div></div><div class="art-pill">${icon("check")}<div>Решение подтверждено врачом<small>Понятный план. Совместное движение.</small></div></div><div class="art-caption"><h2>Забота, в которой<br>есть место диалогу</h2><p>Инструмент поддерживает.<br>Человек принимает решение.</p></div></div></div>`;
}
async function login(username, password) {
  if (busy) return;
  busy = true;
  document
    .querySelectorAll("#login-screen button")
    .forEach((b) => (b.disabled = true));
  try {
    const result = await api("/api/auth/login", { username, password });
    state = {
      ...state,
      user: result.user,
      csrf: result.csrf,
      selected: null,
      page: "overview",
      tab: "overview",
      search: "",
      filter: "all",
      diary: "form",
    };
    beginNavigationSession();
    sendPresence();
    $("#login-screen").hidden = true;
    $("#login-screen").replaceChildren();
    $("#app-shell").hidden = false;
    await load();
    await pollNotifications(true);
  } catch (error) {
    if (state.user) {
      toast("Вход выполнен, но данные не загрузились: " + error.message, true);
      $("#content").innerHTML =
        '<div class="empty">Не удалось загрузить данные. <button class="button" data-action="refresh">Повторить</button></div>';
    } else renderLogin(error.message);
  } finally {
    busy = false;
    document
      .querySelectorAll("#login-screen button")
      .forEach((b) => (b.disabled = false));
  }
}
async function run(form, task) {
  if (busy) return;
  busy = true;
  const controls = [...form.elements];
  controls.forEach((c) => (c.disabled = true));
  try {
    await task();
  } catch (error) {
    toast(
      error.message +
        " Неотправленный текст остаётся в форме; повторную отправку можно выполнить после восстановления связи.",
      true,
    );
  } finally {
    busy = false;
    controls.forEach((c) => (c.disabled = false));
  }
}
async function navigate(page, id) {
  if (busy) return;
  if (state.user?.role === "patient") {
    const alias = {
      tree: ["tree"],
      surveys: ["diary", "diary", "scales"],
      medications: ["diary", "diary", "meds"],
      plan: ["diary", "diary", "meds"],
      records: ["messages", "doctor", "chat"],
      consents: ["settings", "settings", "consents"],
      about: ["settings", "settings", "about"],
      tour: ["settings", "settings", "general"],
    }[page];
    if (alias) {
      page = alias[0];
      if (alias[1])
        state.sectionTabs = { ...state.sectionTabs, [alias[1]]: alias[2] };
    }
  }
  if (prepareNavigation(page, id)) return;
  $("#notifications-panel").hidden = true;
  $("#notifications-button").setAttribute("aria-expanded", "false");
  state.page = page;
  if (id) state.selected = Number(id);
  try {
    await load();
    window.scrollTo({ top: 0, behavior: "instant" });
  } catch (error) {
    toast(error.message, true);
  }
}
function showResolution(id, status) {
  resolution = { id: Number(id), status };
  const p = state.detail.proposals.find((p) => p.id === resolution.id);
  $("#resolution-title").textContent =
    (status === "accepted" ? "Подтвердить: " : "Отклонить: ") + p.title;
  $("#resolution-description").textContent = p.reason;
  $("#resolution-note").value = "";
  $("#resolve-submit").textContent =
    status === "accepted" ? "Подтвердить решение" : "Отклонить предложение";
  $("#decision-dialog").showModal();
}
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-action]");
  if (!button || button.disabled) return;
  if (button.tagName === "A") event.preventDefault();
  const { action, id, page, tab, status, choice, account, filter, mode } =
    button.dataset;
  try {
    if (action === "login") return login(account, "compass-demo");
    if (!state.user || busy) return;
    if (action === "nav") return navigate(page);
    if (action === "patient") {
      state.tab = "overview";
      return navigate("card", id);
    }
    if (action === "open-chat") {
      state.tab = "chat";
      return navigate("card", id);
    }
    if (action === "tab") {
      state.tab = tab;
      return navigate("card");
    }
    if (action === "diary") {
      state.diary = mode;
      render();
      return;
    }
    if (action === "history") {
      state.diary = "history";
      return navigate("diary");
    }
    if (action === "filter") {
      state.filter = filter;
      render();
      return;
    }
    if (action === "refresh") {
      busy = true;
      button.disabled = true;
      try {
        await load();
        await pollNotifications();
        $("#update-banner").hidden = true;
        toast("Данные обновлены");
      } finally {
        busy = false;
        button.disabled = false;
      }
      return;
    }
    if (action === "resolve") {
      showResolution(id, status);
      return;
    }
    if (action === "review" || action === "propose") {
      busy = true;
      button.disabled = true;
      try {
        if (action === "review") {
          await api("/api/alerts/" + id + "/review", {});
          toast("Сигнал отмечен просмотренным");
        } else {
          await write("/api/patients/" + state.selected + "/proposals", {
            choice,
          });
          toast("Вариант добавлен к рассмотрению. План пока не изменён.");
        }
        await load();
        await pollNotifications();
      } finally {
        busy = false;
        button.disabled = false;
      }
    }
    if (action === "notification") await readNotification(Number(id));
  } catch (error) {
    toast(error.message, true);
  }
});
document.addEventListener("input", (event) => {
  const { id, value } = event.target;
  if (["mood", "anxiety", "sleep", "energy"].includes(id))
    $("#" + id + "-value").textContent = value + " / 10";
  if (id === "patient-search") {
    state.search = value;
    $("#patient-cards").innerHTML = patientCards();
  }
});
document.addEventListener("change", async (event) => {
  if (event.target.id === "safety") $("#urgent").hidden = !event.target.checked;
  if (event.target.id === "chart-patient") {
    state.selected = Number(event.target.value);
    try {
      await load();
    } catch (error) {
      toast(error.message, true);
    }
  }
});
document.addEventListener("submit", (event) => {
  const form = event.target;
  event.preventDefault();
  if (form.id === "login-form")
    return login(form.username.value, form.password.value);
  if (form.id === "report-form") {
    const data = {
      mood: Number(form.mood.value),
      anxiety: Number(form.anxiety.value),
      adherence: form.adherence.value,
      adverse_effects: form.adverse_effects.value,
      note: form.note.value,
      safety_signal: form.safety_signal.checked,
      sleep: Number(form.sleep.value),
      energy: Number(form.energy.value),
    };
    return run(form, async () => {
      await write("/api/patients/" + state.selected + "/reports", data);
      state.diary = "history";
      state.calendarDay = care().today;
      state.calendarMonth = care().today.slice(0, 7);
      await load();
      toast(
        data.safety_signal
          ? "Самоотчёт сохранён. При непосредственной опасности обратитесь за экстренной помощью; не ждите ответа в приложении."
          : "Самоотчёт сохранён и доступен вашему врачу",
      );
    });
  }
  if (form.id === "decision-form") {
    const data = { decision: form.decision.value, note: form.note.value };
    return run(form, async () => {
      await write("/api/patients/" + state.selected + "/decisions", data);
      await load();
      toast(
        "Решение сохранено. Пациент получит уведомление внутри приложения.",
      );
    });
  }
  if (form.id === "resolution-form") {
    const data = {
      status: resolution.status,
      note: $("#resolution-note").value,
    };
    return run(form, async () => {
      await write("/api/proposals/" + resolution.id + "/resolve", data);
      $("#decision-dialog").close();
      await load();
      toast(
        data.status === "accepted"
          ? "Решение подтверждено и записано в журнал"
          : "Предложение отклонено. Основание сохранено.",
      );
    });
  }
  if (form.id === "message-form") {
    const data = { body: form.body.value };
    return run(form, async () => {
      await write("/api/patients/" + state.selected + "/messages", data);
      form.reset();
      await refreshChat();
      toast("Сообщение отправлено");
    });
  }
});
async function acknowledgeMessages(selected) {
  const ids = state.messages
    .filter((m) => m.sender_id !== state.user.id && !m.read_at)
    .map((m) => m.id);
  if (ids.length)
    await api("/api/patients/" + selected + "/messages/read", { ids });
}
async function refreshChat() {
  if (!state.user || !$("#chat-thread")) return;
  const selected = state.selected,
    user = state.user.id;
  const messages = await api("/api/patients/" + selected + "/messages");
  if (
    !state.user ||
    state.user.id !== user ||
    selected !== state.selected ||
    !$("#chat-thread")
  )
    return;
  const old = JSON.stringify(state.messages);
  state.messages = messages;
  if (old !== JSON.stringify(messages)) {
    const thread = $("#chat-thread"),
      nearBottom =
        thread.scrollHeight - thread.scrollTop - thread.clientHeight < 70;
    thread.innerHTML = chatThread();
    if (nearBottom) thread.scrollTop = thread.scrollHeight;
  }
  await acknowledgeMessages(selected);
}
const notificationReads = new Map();
function renderNotifications(patchOnly = false) {
  const source = state.notificationSource || [],
    owner = state.user?.id;
  state.notifications = source.map((n) =>
    notificationReads.get(n.id)?.owner === owner
      ? { ...n, read_at: notificationReads.get(n.id).stamp }
      : n,
  );
  const locallyRead = source.filter(
    (n) => !n.read_at && notificationReads.get(n.id)?.owner === owner,
  ).length;
  const unread = Math.max(0, (state.notificationTotal || 0) - locallyRead);
  $("#notification-count").textContent = unread > 99 ? "99+" : String(unread);
  $("#notification-count").hidden = !unread;
  if (!patchOnly)
    $("#notification-list").innerHTML = state.notifications.length
      ? state.notifications
          .map(
            (n) =>
              `<button class="notification-item ${n.read_at ? "" : "unread"}" data-action="notification" data-id="${n.id}"><span class="notification-heading"><strong>${e(n.title)}</strong><span class="notification-state">${n.read_at ? "Прочитано" : "Новое"}</span></span><p>${e(n.body)}</p><time datetime="${e(n.created_at)}">${e(date(n.created_at))}</time></button>`,
          )
          .join("")
      : '<div class="empty">Уведомлений пока нет</div>';
  else
    for (const n of state.notifications) {
      const button = $(`#notification-list [data-id="${n.id}"]`);
      if (button) {
        button.classList.toggle("unread", !n.read_at);
        button.querySelector(".notification-state").textContent = n.read_at
          ? "Прочитано"
          : "Новое";
      }
    }
}
async function readNotification(id) {
  const item = state.notifications.find((n) => n.id === id),
    owner = state.user?.id;
  if (!item || item.read_at || !owner) return;
  const optimistic = { owner, stamp: new Date().toISOString() };
  notificationReads.set(id, optimistic);
  renderNotifications(true);
  try {
    await api("/api/notifications/read", { id });
  } catch (error) {
    if (state.user?.id === owner && notificationReads.get(id) === optimistic) {
      notificationReads.delete(id);
      renderNotifications(true);
    }
    throw error;
  }
}
async function pollNotifications(initial = false) {
  if (!state.user || pollBusy || !navigator.onLine) return;
  pollBusy = true;
  const user = state.user.id;
  try {
    const result = await api("/api/notifications");
    if (!state.user || user !== state.user.id) return;
    const previous = state.notifications[0]?.id;
    const undelivered = result.items
      .filter((n) => !n.delivered_at)
      .map((n) => n.id);
    if (undelivered.length) {
      const ack = await api("/api/notifications/delivered", {
        ids: undelivered,
      });
      if (!state.user || user !== state.user.id) return;
      result.items.forEach((n) => {
        if (!n.delivered_at) n.delivered_at = ack.delivered_at;
      });
    }
    state.notificationSource = result.items;
    state.notificationTotal = result.unread;
    renderNotifications();
    if (!initial && result.items[0]?.id && previous !== result.items[0].id) {
      if (
        !busy &&
        ["overview", "patients"].includes(state.page) &&
        !["INPUT", "TEXTAREA", "SELECT"].includes(
          document.activeElement?.tagName,
        )
      ) {
        await load();
        $("#update-banner").hidden = true;
      } else $("#update-banner").hidden = false;
    }
    $("#sync-label").textContent = "На связи";
  } catch (error) {
    if (state.user) $("#sync-label").textContent = "Нет связи с сервером";
  } finally {
    pollBusy = false;
  }
}
$("#bell-icon").innerHTML = icon("bell");
$("#logout").innerHTML = icon("exit");
$("#notifications-button").onclick = () => {
  const panel = $("#notifications-panel");
  panel.hidden = !panel.hidden;
  $("#notifications-button").setAttribute(
    "aria-expanded",
    String(!panel.hidden),
  );
  if (!panel.hidden) pollNotifications();
};
$("#close-notifications").onclick = () => {
  $("#notifications-panel").hidden = true;
  $("#notifications-button").setAttribute("aria-expanded", "false");
};
$("#cancel-resolution").onclick = () => {
  if (!busy) $("#decision-dialog").close();
};
$("#logout").onclick = async () => {
  if (busy) return;
  try {
    await disableDevicePush();
    await api("/api/auth/logout", {});
    await OfflineVault.clear();
    clearSession();
    renderLogin();
    toast("Вы вышли из аккаунта");
  } catch (error) {
    toast(error.message, true);
  }
};
document.querySelector(".brand").onclick = (event) => {
  event.preventDefault();
  if (state.user) navigate("overview");
};
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    $("#notifications-panel").hidden = true;
    $("#notifications-button").setAttribute("aria-expanded", "false");
  }
});
function connectivity() {
  $("#connection").hidden = navigator.onLine;
}
window.addEventListener("offline", connectivity);
window.addEventListener("online", () => {
  connectivity();
  if (state.user) pollNotifications();
});
window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  pendingInstall = event;
  $("#install").hidden = false;
});
$("#install").onclick = async () => {
  if (pendingInstall) {
    await pendingInstall.prompt();
    pendingInstall = null;
    $("#install").hidden = true;
  }
};
window.addEventListener("appinstalled", () => {
  $("#install").hidden = true;
});
document.addEventListener("visibilitychange", () => {
  if (!document.hidden && state.user) {
    pollNotifications();
    refreshChat().catch(() => {});
  }
});
setInterval(() => {
  if (!document.hidden && state.user) {
    pollNotifications();
    if (!busy) refreshChat().catch(() => {});
  }
}, 5000);
async function boot() {
  connectivity();
  try {
    const result = await api("/api/auth/me");
    if (!result.user) {
      renderLogin();
      return;
    }
    state.user = result.user;
    state.csrf = result.csrf;
    beginNavigationSession();
    sendPresence();
    $("#login-screen").hidden = true;
    $("#app-shell").hidden = false;
    await load();
    await pollNotifications(true);
  } catch (error) {
    if (state.user) {
      $("#app-shell").hidden = false;
      $("#content").innerHTML =
        '<div class="empty">Не удалось загрузить данные. <button class="button" data-action="refresh">Повторить</button></div>';
      toast(error.message, true);
    } else renderLogin("Сервер недоступен. Для входа требуется соединение.");
  }
}
// care.js selects the authenticated or public intake entry point.
if ("serviceWorker" in navigator)
  navigator.serviceWorker.register("/sw.js").catch(() => {});
