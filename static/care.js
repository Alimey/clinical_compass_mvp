/* Product workflows: real local operations, optional external integrations. */
const care = () =>
  state.detail?.care || {
    appointments: [],
    surveys: [],
    prescriptions: [],
    medication_marks: [],
    encounters: [],
    labs: [],
    today: new Date().toISOString().slice(0, 10),
  };
const clinicDate = (v) =>
  new Date(v).toLocaleString("ru-RU", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Europe/Moscow",
  });
const isDoctor = () => state.user?.role === "doctor";
const timeLabel = (v) =>
  new Date(v).toLocaleTimeString("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Moscow",
  });
function appointmentStrip() {
  const upcoming = (state.appointments || [])
    .filter((a) => a.status === "booked" && new Date(a.starts_at) > new Date())
    .slice(0, 6);
  return `<section class="appointment-section"><div class="section-heading"><h2>Ближайшие консультации</h2><button class="button quiet small" data-action="nav" data-page="schedule">${isDoctor() ? "Расписание" : "Записаться"} ${icon("arrow")}</button></div><div class="appointment-strip">${upcoming.length ? upcoming.map((a) => `<button class="appointment-tile" data-action="nav" data-page="schedule"><div class="appointment-date"><strong>${new Date(a.starts_at).toLocaleDateString("ru-RU", { day: "numeric", timeZone: "Europe/Moscow" })}</strong><span>${new Date(a.starts_at).toLocaleDateString("ru-RU", { month: "short", timeZone: "Europe/Moscow" })}</span></div><div><strong>${e(timeLabel(a.starts_at))} <small>МСК</small></strong><p>${e(isDoctor() ? a.patient_name : a.doctor_name)}</p><small>${e(a.kind)}</small></div>${icon("arrow")}</button>`).join("") : '<div class="empty">Пока нет ближайших записей. Выберите время в расписании.</div>'}</div></section>`;
}
const originalOverview = overview;
overview = function () {
  const html = originalOverview();
  return isDoctor()
    ? html.replace(
        '<div class="stats-grid">',
        appointmentStrip() + '<div class="stats-grid">',
      )
    : html;
};
const originalPatientOverview = patientOverview;
patientOverview = function () {
  const d = state.detail,
    c = care();
  const links = [
    [
      "surveys",
      "book",
      "Назначенные опросы",
      c.surveys.filter((a) => a.status === "assigned").length +
        " ожидают ответа",
    ],
    ["medications", "leaf", "Таблетница", "Отметки по вашему плану"],
    [
      "records",
      "chart",
      "Анализы и посещения",
      c.labs.length + " результатов · " + c.encounters.length + " посещений",
    ],
    ["diary", "heart", "Самочувствие", "Записать изменения в любой момент"],
  ];
  const contact = (d.doctor.phone || "").replace(/[\s()\-]/g, "");
  const call = /^\+\d{10,15}$/.test(contact)
    ? `<a class="button full" href="tel:${e(contact)}">${icon("heart")}Позвонить специалисту</a>`
    : '<button class="button full" disabled>Позвонить · телефон не указан</button>';
  return originalPatientOverview()
    .replace(
      '<button class="button full" data-action="nav" data-page="messages">',
      call +
        '<button class="button full" data-action="nav" data-page="messages">',
    )
    .replace(
      '<div class="intro-card">',
      appointmentStrip() +
        `<div class="quick-grid">${links.map(([page, glyph, title, sub]) => `<button class="quick-card" data-action="nav" data-page="${page}"><span class="routine-icon">${icon(glyph)}</span><strong>${title}</strong><small>${e(sub)}</small></button>`).join("")}</div>` +
        '<div class="intro-card">',
    );
};
const originalPlan = planPage;
planPage = function (doctor = false) {
  return (
    originalPlan(doctor) +
    `<div class="section-heading"><h2>Таблетница</h2><button class="button" data-action="nav" data-page="medications">${doctor ? "Управлять назначениями" : "Открыть таблетницу"} ${icon("arrow")}</button></div><p class="caption">${care().prescriptions.filter((p) => p.active).length} активных учебных назначений. Только вымышленные варианты, без реальных дозировок.</p>`
  );
};
function schedulePage() {
  const all = state.appointments || [],
    upcoming = all.filter((a) => a.status === "booked"),
    past = all.filter((a) => a.status !== "booked");
  return (
    heading(
      "ВСТРЕЧИ СО СПЕЦИАЛИСТОМ",
      "Расписание консультаций",
      "Время записей указано по Москве (UTC+3). Данные синтетические.",
      refreshButton(),
    ) +
    appointmentStrip() +
    `<div class="two-columns"><div class="card"><h2>Записаться на консультацию</h2><form id="appointment-form">${isDoctor() ? `<label for="booking-patient">Пациент</label><select name="patient_id" id="booking-patient">${state.patients.map((p) => `<option value="${p.id}" ${p.id === state.selected ? "selected" : ""}>${e(p.name)}</option>`).join("")}</select>` : ""}<label for="booking-slot">Свободное время · Москва</label><select id="booking-slot" name="starts_at" required><option value="">Выберите время</option>${(state.slots || []).map((s) => `<option value="${s}">${e(new Date(s).toLocaleString("ru-RU", { dateStyle: "medium", timeStyle: "short", timeZone: "Europe/Moscow" }))}</option>`).join("")}</select><label for="booking-kind">Формат</label><select name="kind" id="booking-kind"><option>Онлайн-консультация</option><option>Очная консультация</option></select><div class="form-footer"><small>Запись появится у пациента и специалиста. Длительность — 50 минут.</small><button class="button primary" type="submit">Подтвердить запись</button></div></form></div><div class="card"><h2>Ваши записи</h2>${upcoming.length ? upcoming.map((a) => `<article class="report-item"><div class="report-meta"><time>${e(clinicDate(a.starts_at))}</time><span class="chip green">Запланировано</span></div><h3>${e(isDoctor() ? a.patient_name : a.doctor_name)}</h3><p class="caption">${e(a.kind)}</p><div class="proposal-actions">${new Date(a.starts_at) > new Date() ? `<button class="button small" data-care="appointment-cancel" data-id="${a.id}">Отменить запись</button>` : isDoctor() ? `<button class="button small primary" data-care="appointment-complete" data-id="${a.id}">Завершить консультацию</button>` : ""}</div></article>`).join("") : '<p class="empty">Предстоящих консультаций нет</p>'}${past.length ? `<details><summary>История записей</summary>${past.map((a) => `<p class="caption">${e(clinicDate(a.starts_at))} · ${a.status === "completed" ? "Завершена" : "Отменена"} · ${e(isDoctor() ? a.patient_name : a.doctor_name)}</p>`).join("")}</details>` : ""}</div></div>`
  );
}
function demographicCard() {
  const p = state.detail.profile;
  return `<div class="card"><div class="profile-banner">${avatar(state.detail.patient.name, "mint", "large")}<div><p class="eyebrow">ОСНОВНЫЕ ДАННЫЕ</p><h2>${e(state.detail.patient.name)}</h2><p>${e(p.sex || "Пол не указан")} · ${e(p.age || "—")} лет</p></div></div><div class="profile-measures"><span>Рост<strong>${e(p.height || "—")} <small>см</small></strong></span><span>Вес<strong>${e(p.weight || "—")} <small>кг</small></strong></span><span>Телефон<strong class="phone-text">${e(p.phone || "Не указан")}</strong></span></div><p class="caption">${e(p.context || "Первичная анкета пока не заполнена")}</p>${isDoctor() ? `<details><summary>Изменить основные данные</summary><form id="profile-form"><div class="form-grid"><div><label>Пол<select name="sex">${["Женский", "Мужской", "Не указан"].map((v) => `<option ${v === p.sex ? "selected" : ""}>${v}</option>`).join("")}</select></label><label>Рост, см<input name="height" type="number" min="30" max="250" step="0.1" value="${e(p.height || "")}"></label></div><div><label>Вес, кг<input name="weight" type="number" min="1" max="350" step="0.1" value="${e(p.weight || "")}"></label><label>Телефон<input name="phone" maxlength="30" value="${e(p.phone || "")}"></label></div></div><button class="button primary" type="submit">Сохранить данные</button></form></details>` : ""}</div>`;
}
function recordsPage() {
  const c = care(),
    doctor = isDoctor(),
    d = state.detail;
  const phone = (d.doctor.phone || "").replace(/[\s()\-]/g, "");
  return `${state.page === "card" ? "" : heading("МОЯ КАРТА", "Посещения и анализы", "История контактов и результаты в одном месте.", refreshButton())}${demographicCard()}<div class="record-shortcuts"><button class="button" data-care="record-plan">${icon("leaf")}План и назначения</button><button class="button" data-care="record-chat">${icon("chat")}Открыть чат</button><button class="button" data-care="record-diary">${icon("book")}Дневник пациента</button>${!doctor && /^\+\d{10,15}$/.test(phone) ? `<a class="button" href="tel:${e(phone)}">${icon("heart")}Позвонить специалисту</a>` : !doctor ? '<button class="button" disabled>Телефон специалиста не указан</button>' : ""}</div><div class="two-columns"><div class="card"><h2>История посещений</h2>${c.encounters.length ? c.encounters.map((v) => `<article class="report-item"><time class="caption">${e(date(v.created_at))} · ${e(v.doctor_name)}</time><h3>${e(v.title)}</h3><p class="report-text">${e(v.summary)}</p><h3>Согласованный план</h3><p class="report-text">${e(v.plan)}</p></article>`).join("") : '<p class="empty">Отчётов о посещениях пока нет</p>'}${doctor ? `<details><summary>Добавить отчёт о посещении</summary><form id="encounter-form"><label>Название<input name="title" required maxlength="160" placeholder="Повторная консультация"></label><label>Что обсудили<textarea name="summary" required maxlength="3000" rows="4"></textarea></label><label>План после встречи<textarea name="plan" required maxlength="1000" rows="3"></textarea></label><button class="button primary" type="submit">Сохранить отчёт</button></form></details>` : ""}</div><div class="card"><h2>Результаты анализов</h2>${c.labs.length ? c.labs.map((l) => `<article class="report-item"><span class="chip neutral">Синтетический документ</span><h3>${e(l.title)}</h3><p class="caption">${e(shortDate(l.created_at))}</p><pre class="lab-result">${e(l.result)}</pre><p class="caption">${e(l.note)}</p><a class="button small" href="/api/labs/${l.id}/download" download>Скачать результат</a></article>`).join("") : '<p class="empty">Результатов пока нет</p>'}${doctor ? `<details><summary>Добавить синтетический результат</summary><form id="lab-form"><label>Название<input name="title" required maxlength="160"></label><label>Результат<textarea name="result" required maxlength="3000" rows="4"></textarea></label><label>Комментарий<textarea name="note" maxlength="500" rows="2"></textarea></label><button class="button primary" type="submit">Добавить результат</button></form></details>` : ""}</div></div>`;
}
function surveyResponses(item) {
  return item.questions
    .map(
      (q) =>
        `<tr><td>${e(q.label)}</td><td>${typeof item.answers[q.id] === "boolean" ? (item.answers[q.id] ? "Да" : "Нет") : e(item.answers[q.id])}${q.type === "scale" ? " / 10" : ""}</td></tr>`,
    )
    .join("");
}
function surveysPage() {
  const c = care(),
    doctor = isDoctor(),
    selected = c.surveys.find(
      (s) => s.id === state.surveyId && s.status === "assigned",
    );
  if (selected && !doctor)
    return (
      heading(
        "НАЗНАЧЕННЫЙ ОПРОС",
        e(selected.title),
        "Ответы увидит ваш специалист. Это учебный опрос, не диагностическая шкала.",
      ) +
      `<div class="card"><p class="caption">Дедлайн: ${e(date(selected.due_at))}</p><form id="survey-answer-form" data-id="${selected.id}">${selected.questions.map((q) => `<label for="survey-q-${q.id}">${e(q.label)}</label>${q.type === "scale" ? `<select name="q-${q.id}" id="survey-q-${q.id}" required><option value="">Выберите оценку</option>${Array.from({ length: 11 }, (_, i) => `<option value="${i}">${i} / 10</option>`).join("")}</select>` : q.type === "yes_no" ? `<select name="q-${q.id}" id="survey-q-${q.id}" required><option value="">Выберите ответ</option><option value="yes">Да</option><option value="no">Нет</option></select>` : `<textarea name="q-${q.id}" id="survey-q-${q.id}" maxlength="1000" rows="3"></textarea>`}`).join("")}<div class="form-footer"><button class="button quiet" type="button" data-care="survey-back">Назад к опросам</button><button class="button primary" type="submit">Отправить ответы</button></div></form></div>`
    );
  return `${state.page === "card" ? "" : heading("МОИ ЗАДАНИЯ", "Опросы от специалиста", "Периодичность и дедлайны определяет ваш специалист.", refreshButton())}${doctor ? `<div class="card"><div class="card-heading"><h2>Назначить опрос</h2><button class="button quiet small" data-action="nav" data-page="builder">Конструктор опросов ${icon("arrow")}</button></div><form id="assign-survey-form"><label>Шаблон<select name="template_id" required>${(state.templates || []).map((t) => `<option value="${t.id}">${e(t.title)}</option>`).join("")}</select></label><div class="form-grid"><label>Дедлайн · время устройства<input name="due_at" type="datetime-local" required></label><label>Повторение<select name="repeat_days"><option value="0">Без повторения</option><option value="1">Ежедневно</option><option value="7">Раз в неделю</option><option value="14">Раз в две недели</option><option value="30">Раз в 30 дней</option></select></label></div><button class="button primary" type="submit">Назначить пациенту</button></form></div>` : ""}<div class="section-heading"><h2>${doctor ? "Назначенные опросы" : "Ваши опросы"}</h2></div>${c.surveys.length ? c.surveys.map((s) => `<article class="card survey-card"><div class="card-heading"><h2>${e(s.title)}</h2><span class="chip ${s.status === "completed" ? "green" : s.overdue ? "red" : "amber"}">${s.status === "completed" ? "Завершён" : s.status === "cancelled" ? "Отменён специалистом" : s.overdue ? "Дедлайн прошёл" : "Ожидает ответа"}</span></div><p class="caption">${s.status === "completed" ? "Заполнен " + e(date(s.submitted_at)) : "До " + e(date(s.due_at))}${s.repeat_days ? " · повтор каждые " + s.repeat_days + " дн." : ""}</p>${!doctor && s.status === "assigned" ? `<button class="button primary" data-care="answer-survey" data-id="${s.id}">Пройти опрос ${icon("arrow")}</button>` : doctor && s.status === "completed" ? `<table class="rule-table"><tbody>${surveyResponses(s)}</tbody></table>` : s.status === "completed" ? `<p class="source-note">${e(s.interpretation)}</p>` : `<p class="caption">${s.questions.length} вопросов · учебный шаблон</p>`}${doctor && s.status === "assigned" ? `<button class="button small quiet" data-care="cancel-survey" data-id="${s.id}">Отменить задание</button>` : ""}</article>`).join("") : '<div class="empty">Опросы пока не назначены</div>'}`;
}
function questionRow(question = { label: "", type: "scale" }) {
  return `<div class="question-row"><input class="question-label" aria-label="Текст вопроса" required maxlength="200" value="${e(question.label)}" placeholder="Например: как вы оцениваете свой сон?"><select class="question-type" aria-label="Тип ответа">${[
    ["scale", "Оценка 0–10"],
    ["yes_no", "Да / нет"],
    ["text", "Свободный текст"],
  ]
    .map(
      ([v, t]) =>
        `<option value="${v}" ${v === question.type ? "selected" : ""}>${t}</option>`,
    )
    .join(
      "",
    )}</select><button class="icon-button" type="button" data-care="remove-question" aria-label="Удалить вопрос">×</button></div>`;
}
function builderPage() {
  return (
    heading(
      "ИНСТРУМЕНТЫ СПЕЦИАЛИСТА",
      "Конструктор опросов",
      "Создайте свой опрос, измените шаблон или запросите черновик у ИИ.",
    ) +
    `<div class="two-columns"><div class="card"><form id="template-form"><label>Название<input name="title" required maxlength="160" placeholder="Короткий опрос перед встречей"></label><label>Описание<textarea name="description" maxlength="500" rows="2" placeholder="Для чего этот опрос"></textarea></label><div class="section-heading"><h2>Вопросы</h2><button class="button small" type="button" data-care="add-question">${icon("plus")}Вопрос</button></div><div id="question-rows">${questionRow()}${questionRow({ label: "", type: "text" })}</div><p class="caption">Опросы не являются валидированными шкалами. Любой ИИ-черновик нужно проверить перед сохранением.</p><button class="button primary full" type="submit">Сохранить шаблон</button></form></div><div><div class="card"><h2>Начать с шаблона</h2><label for="copy-template">Доступные шаблоны</label><select id="copy-template">${(state.templates || []).map((t) => `<option value="${t.id}">${e(t.title)}</option>`).join("")}</select><button class="button full" data-care="copy-template">Создать свою версию</button></div><div class="card"><h2>Составить с ИИ</h2><p class="caption">${state.integrations?.ai?.configured ? "Будет отправлен запрос настроенной внешней модели." : "Внешний ИИ API ещё не подключён. Настройка — в разделе «Ещё»."}</p><form id="generate-survey-form"><label>Задача опроса<textarea name="prompt" required maxlength="1000" rows="4" placeholder="Составь 4 учебных вопроса о сне и трудностях соблюдения плана"></textarea></label><button class="button" type="submit">Получить ИИ-черновик</button></form></div></div></div>`
  );
}
function medicationsPage() {
  const c = care(),
    doctor = isDoctor(),
    day = state.medicationDay || c.today;
  const entries = c.prescriptions.filter(
    (p) => p.active && p.starts_on <= day && p.ends_on >= day,
  );
  return (
    heading(
      "СОГЛАСОВАННЫЙ ПЛАН",
      "Таблетница",
      "Только вымышленные ДЕМО-варианты. Отметки не являются назначениями реальных лекарств.",
      refreshButton(),
    ) +
    `<div class="card"><label for="medication-day">День отметок · Москва</label><input id="medication-day" type="date" value="${e(day)}" max="${c.today}"></div>${
      entries.length
        ? entries
            .map(
              (p) =>
                `<article class="card"><div class="card-heading"><h2>${e(p.title)}</h2><span class="chip neutral">Вымышленный вариант</span></div><p class="caption">${e(p.note)}</p><p class="caption">${e(p.starts_on)} — ${e(p.ends_on)} · время по Москве</p><div class="dose-list">${p.times
                  .map((t) => {
                    const mark = c.medication_marks.find(
                        (m) =>
                          m.prescription_id === p.id &&
                          m.day === day &&
                          m.scheduled_time === t,
                      ),
                      future =
                        new Date(day + "T" + t + ":00+03:00") > new Date();
                    return `<div class="dose-row"><span class="dose-time">${e(t)}</span><span class="chip ${mark?.status === "taken" ? "green" : mark?.status === "skipped" ? "amber" : "neutral"}">${mark?.status === "taken" ? "Отмечено: принято" : mark?.status === "skipped" ? "Отмечено: пропущено" : future ? "Предстоит" : "Без отметки"}</span>${!doctor ? `<div class="dose-actions"><button class="button small ${mark?.status === "taken" ? "primary" : ""}" data-care="medication-mark" data-id="${p.id}" data-time="${t}" data-status="taken" ${future ? "disabled" : ""}>Принято</button><button class="button small" data-care="medication-mark" data-id="${p.id}" data-time="${t}" data-status="skipped" ${future ? "disabled" : ""}>Пропущено</button></div>` : ""}</div>`;
                  })
                  .join(
                    "",
                  )}</div>${doctor ? `<details><summary>Отменить учебное назначение</summary><form class="stop-prescription-form" data-id="${p.id}"><label>Обоснование<textarea name="note" required maxlength="500" rows="2"></textarea></label><button class="button danger" type="submit">Подтвердить отмену</button></form></details>` : ""}</article>`,
            )
            .join("")
        : '<div class="empty">На выбранный день нет активных назначений</div>'
    }${doctor ? `<div class="card"><h2>Подтвердить учебное назначение</h2><form id="prescription-form"><label>Вымышленный вариант<select name="choice">${state.detail.catalog.map((c) => `<option value="${c.id}">${e(c.name)}</option>`).join("")}</select></label><div class="form-grid"><label>Первое время · Москва<input name="time1" type="time" required value="09:00"></label><label>Второе время · необязательно<input name="time2" type="time" value="20:00"></label><label>С даты<input name="starts_on" type="date" required min="${c.today}" value="${c.today}"></label><label>По дату<input name="ends_on" type="date" required min="${c.today}"></label></div><label>Указание для синтетического сценария<textarea name="note" required maxlength="500" rows="3" placeholder="Не указывайте настоящие препараты или дозировки"></textarea></label><button class="button primary" type="submit">Подтвердить назначение</button></form></div>` : ""}`
  );
}
function assistantPage() {
  const configured = state.integrations?.ai?.configured;
  return `<div class="source-note">${configured ? "Подключена внешняя модель " + e(state.integrations.ai.model) + "." : "Внешний ИИ API пока не подключён."} ИИ видит только синтетический контекст выбранного пациента. Ответ — черновик для специалиста, без автоматического изменения плана.</div><div class="card"><h2>ИИ-помощник специалиста</h2><form id="assistant-form"><label>Что проанализировать?<textarea name="question" required maxlength="1000" rows="3" placeholder="Составь сводку динамики и предложи вопросы для следующей консультации"></textarea></label><button class="button primary" type="submit">Спросить ИИ</button></form></div><div id="assistant-results">${(state.aiRuns || []).map((r) => `<article class="card"><span class="chip purple">ИИ-черновик · ${e(r.model)}</span><p class="caption">${e(date(r.created_at))}</p><h3>${e(r.question)}</h3><p class="assistant-answer">${e(r.answer)}</p></article>`).join("")}</div>`;
}
function settingsPage() {
  const i = state.integrations || {},
    contact = i.contact?.[0] || {},
    doctor = isDoctor();
  return (
    heading(
      "МОЁ ПРОСТРАНСТВО",
      "Настройки и инструменты",
      "Подключения показывают фактическую настройку, а не имитируют результат.",
    ) +
    `<div class="quick-grid">${(doctor
      ? [
          ["builder", "book", "Конструктор опросов"],
          ["scenarios", "chart", "Сценарии показа"],
          ["schedule", "clock", "Расписание"],
        ]
      : [
          ["surveys", "book", "Опросы"],
          ["medications", "leaf", "Таблетница"],
          ["records", "chart", "Моя карта"],
          ["plan", "leaf", "Мой план"],
          ["schedule", "clock", "Расписание"],
        ]
    )
      .map(
        ([page, glyph, title]) =>
          `<button class="quick-card" data-action="nav" data-page="${page}"><span class="routine-icon">${icon(glyph)}</span><strong>${title}</strong></button>`,
      )
      .join(
        "",
      )}</div>${doctor ? `<div class="card"><h2>Пригласить пациента</h2><p class="caption">Пациент заполняет анкету сам. Карточка автоматически привязывается к вам. Приглашение одноразовое и действует 72 часа.</p><button class="button primary" data-care="invite">Создать приглашение</button><div id="invite-result"></div></div><div class="card"><h2>Контакты специалиста</h2><form id="contact-form"><label>Телефон для кнопки вызова<input name="phone" maxlength="30" value="${e(contact.phone || "")}" placeholder="+70000000001"></label><label>Специализация<input name="profession" maxlength="100" value="${e(contact.profession || "")}"></label><label>Организация<input name="organization" maxlength="100" value="${e(contact.organization || "")}"></label><button class="button primary" type="submit">Сохранить контакты</button></form></div>` : ""}<div class="card"><h2>Напоминания и push</h2><p class="caption">Уведомления внутри приложения работают при открытой вкладке. Push требует разрешения браузера, HTTPS или localhost и работающего фонового обработчика. На iPhone — установленной PWA.</p><p><span class="chip ${i.push?.subscriptions ? "green" : "neutral"}">${i.push?.subscriptions ? "Подписка браузера сохранена" : "Этот браузер ещё не подключён"}</span></p><div class="proposal-actions"><button class="button primary" data-care="enable-push">Подключить push в браузере</button><button class="button" data-care="disable-push">Отключить</button></div><p class="caption">Последний сигнал обработчика: ${i.worker_last_seen ? e(date(i.worker_last_seen)) : "ещё не запускался"}. Успешная подписка не подтверждает доставку конкретного push.</p></div>${!doctor ? `<div class="card"><h2>Назначения и записи без интернета</h2><p class="caption">По вашему выбору сохраним зашифрованную копию назначений, консультаций, посещений и результатов. Без чата и сессионных токенов. Для открытия нужен PIN. Копия может устареть; отправка изменений офлайн недоступна.</p><form id="offline-save-form"><div class="form-grid"><label>PIN из 6 цифр<input name="pin" type="password" inputmode="numeric" pattern="[0-9]{6}" required maxlength="6" autocomplete="new-password"></label><label>Повторите PIN<input name="confirm" type="password" inputmode="numeric" pattern="[0-9]{6}" required maxlength="6" autocomplete="new-password"></label></div><div class="proposal-actions"><button class="button primary" type="submit">Сохранить офлайн-копию</button><button class="button quiet" data-care="clear-offline" type="button">Удалить копию</button></div></form><p class="caption">Выход из аккаунта удаляет копию. После перезагрузки для обновления сохраните её заново с PIN.</p></div>` : `<div class="card"><h2>Внешний ИИ API</h2><p><span class="chip ${i.ai?.configured ? "green" : "amber"}">${i.ai?.configured ? "Настроена модель " + e(i.ai.model) : "Не подключён"}</span></p><p class="caption">Подключение модели выполняет администратор по инструкции в README. Ключ не передаётся в браузер. Без модели приложение не выдаёт заготовки за ответы ИИ.</p><h2>Регистрация через Telegram</h2><p><span class="chip ${i.telegram?.configured ? "green" : "amber"}">${i.telegram?.configured ? "Настройки бота заданы" : "Бот ещё не подключён"}</span></p><p class="caption">Понадобятся бот, созданный через BotFather, его токен, username и адрес приложения. На локальном компьютере используется long polling — публичный webhook не нужен. До подключения работает та же регистрация по веб-приглашению.</p><h2>Очередь эскалации</h2>${(state.escalations || []).map((v) => `<article class="report-item"><span class="chip ${v.status === "resolved" ? "green" : "amber"}">${v.status === "resolved" ? "Сигнал просмотрен" : "Протокол ожидает настройки"}</span><p class="caption">Сигнал #${v.alert_id} · ${e(date(v.created_at))}</p><p class="caption">${e(v.note)}</p></article>`).join("") || '<p class="caption">Очередь пуста</p>'}<h2>Если сигнал не просмотрен</h2><p class="caption">Через 15 минут событие попадёт во внутреннюю очередь эскалации. Внешний протокол и адресат организации ещё не определены: отправка в медорганизацию не имитируется.</p></div>`}<button class="button quiet" data-action="nav" data-page="about">Подробнее о проекте ${icon("arrow")}</button>`
  );
}
function fillBuilder(draft) {
  const form = $("#template-form");
  form.title.value = draft.title;
  form.description.value = draft.description || "";
  $("#question-rows").innerHTML = draft.questions.map(questionRow).join("");
}
const originalPatients = patientsPage;
patientsPage = function () {
  return originalPatients().replace(
    '<div class="list-toolbar">',
    `<div class="invite-toolbar"><button class="button primary" data-care="invite">${icon("plus")}Пригласить пациента</button><div id="invite-result"></div></div><div class="list-toolbar">`,
  );
};
const originalRenderLogin = renderLogin;
renderLogin = function (error = "") {
  originalRenderLogin(error);
  const form = $("#login-form"),
    details = form?.closest("details"),
    first = $(".demo-login");
  if (form && details && first) {
    details.removeChild(form);
    first.before(form);
    details.remove();
    form.querySelector("label[for=username]").textContent =
      "Имя пользователя или телефон";
    form.querySelector("#username").placeholder = "patient-a или +70000000002";
    const line = document.createElement("p");
    line.className = "caption";
    line.textContent = "Или быстрый вход в синтетический сценарий:";
    first.before(line);
  }
  OfflineVault.exists().then((exists) => {
    if (!exists || !$("#login-screen") || $("#login-screen").hidden) return;
    const host = $(".login-form-side");
    if (!host) return;
    const block = document.createElement("div");
    block.className = "offline-unlock";
    block.innerHTML =
      '<h2>Сохранённая офлайн-копия</h2><p class="caption">Только просмотр назначений и записей. Для доступа введите свой PIN.</p><form id="offline-unlock-form"><label>PIN из 6 цифр<input name="pin" type="password" inputmode="numeric" pattern="[0-9]{6}" required maxlength="6"></label><button class="button" type="submit">Открыть офлайн-копию</button></form>';
    host.append(block);
  });
};
function renderOffline(snapshot) {
  const c = snapshot.care,
    plan = snapshot.catalog.find((p) => p.id === snapshot.profile.plan);
  $("#app-shell").hidden = true;
  $("#login-screen").hidden = false;
  $("#login-screen").innerHTML =
    `<div class="offline-layout"><div class="page-heading"><div><p class="eyebrow">ОФЛАЙН · ТОЛЬКО ПРОСМОТР</p><h1>${e(snapshot.user.name)}</h1><p class="caption">Копия от ${e(date(snapshot.saved_at))}. Данные могли измениться на сервере.</p></div><button class="button" data-care="return-online">Войти онлайн</button></div><div class="source-note">Это зашифрованная копия на этом устройстве, а не действующая серверная сессия. Чат и отправка данных недоступны.</div><div class="card"><h2>Записи на консультации</h2>${c.appointments.length ? c.appointments.map((a) => `<p>${e(clinicDate(a.starts_at))} · ${e(a.kind)} · ${a.status === "cancelled" ? "Отменена" : a.status === "completed" ? "Завершена" : "Запланирована"}</p>`).join("") : "<p>Записей пока нет</p>"}</div><div class="card"><h2>Назначения</h2><p>${plan ? e(plan.name) : "План ещё не подтверждён"}</p><p class="caption">${e(snapshot.profile.plan_note)}</p>${c.prescriptions.map((p) => `<article class="report-item"><h3>${e(p.title)}</h3><p class="caption">${e(p.starts_on)} — ${e(p.ends_on)} · ${p.times.map(e).join(", ")} МСК · ${p.active ? "Активно в сохранённой копии" : "Отменено"}</p><p>${e(p.note)}</p></article>`).join("")}</div><div class="card"><h2>История посещений</h2>${c.encounters.map((v) => `<article class="report-item"><time class="caption">${e(date(v.created_at))}</time><h3>${e(v.title)}</h3><p>${e(v.summary)}</p><p>${e(v.plan)}</p></article>`).join("") || "<p>Пока нет посещений</p>"}</div><div class="card"><h2>Результаты в сохранённой копии</h2>${c.labs.map((l) => `<h3>${e(l.title)}</h3><pre class="lab-result">${e(l.result)}</pre>`).join("") || "<p>Пока нет результатов</p>"}</div></div>`;
}
async function enableDevicePush() {
  if (
    !("serviceWorker" in navigator) ||
    !("PushManager" in window) ||
    !window.isSecureContext
  )
    throw new Error(
      "Push требует поддерживаемого браузера и HTTPS или localhost",
    );
  if ((await Notification.requestPermission()) !== "granted")
    throw new Error(
      "Разрешение на уведомления не получено. Его можно изменить в настройках браузера.",
    );
  const registration = await navigator.serviceWorker.ready;
  const key = await api("/api/push/key");
  const raw = atob(key.public_key.replace(/-/g, "+").replace(/_/g, "/"));
  const applicationServerKey = Uint8Array.from(raw, (c) => c.charCodeAt(0));
  const subscription =
    (await registration.pushManager.getSubscription()) ||
    (await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey,
    }));
  await api("/api/push/subscribe", { subscription: subscription.toJSON() });
}
async function disableDevicePush() {
  if (!("serviceWorker" in navigator)) return;
  const registration = await navigator.serviceWorker.getRegistration();
  const sub = await registration?.pushManager?.getSubscription();
  if (sub) {
    try {
      await api("/api/push/unsubscribe", { endpoint: sub.endpoint });
    } finally {
      await sub.unsubscribe();
    }
  }
}
async function showIntake() {
  const activation = location.hash.startsWith("#activate=");
  const token = decodeURIComponent(location.hash.split("=").slice(1).join("="));
  $("#app-shell").hidden = true;
  $("#login-screen").hidden = false;
  try {
    const data = activation ? null : await api("/api/intake/info", { token });
    $("#login-screen").innerHTML =
      `<div class="intake-layout"><div class="brand"><span class="brand-mark">✦</span><span>Клинический компас<small>Первое знакомство</small></span></div><p class="eyebrow">${activation ? "ЗАВЕРШЕНИЕ РЕГИСТРАЦИИ" : "ПРИГЛАШЕНИЕ СПЕЦИАЛИСТА"}</p><h1>${activation ? "Задайте пароль" : "Давайте познакомимся"}</h1>${data ? `<p class="caption">Специалист: ${e(data.doctor.name)} · ${e(data.doctor.profession || "Специалист")}. Карточка будет создана автоматически и закреплена за ним.</p>` : ""}<p class="source-note">Используйте только вымышленные сведения. Анкета не является диагностикой.</p><form id="intake-form" data-token="${e(token)}" data-activation="${activation}">${activation ? "" : `<label>Имя и фамилия<input name="name" required minlength="2" maxlength="100" autocomplete="off"></label><div class="form-grid"><label>Пол<select name="sex"><option>Женский</option><option>Мужской</option><option>Не указан</option></select></label><label>Возраст<input name="age" type="number" required min="18" max="100"></label><label>Рост, см<input name="height" type="number" required min="100" max="250" step="0.1"></label><label>Вес, кг<input name="weight" type="number" required min="30" max="350" step="0.1"></label></div><label>Синтетический телефон<input name="phone" type="tel" required maxlength="30" placeholder="+70000000999" autocomplete="off"></label><label>Что хотите обсудить на первой встрече?<textarea name="context" maxlength="1000" rows="3"></textarea></label>`}<label>Пароль<input name="password" type="password" required minlength="8" maxlength="200" autocomplete="new-password"></label><label>Повторите пароль<input name="confirm" type="password" required minlength="8" maxlength="200" autocomplete="new-password"></label><button class="button primary full" type="submit">${activation ? "Сохранить пароль" : "Создать карточку и войти"}</button></form><p id="intake-error" class="login-error" hidden role="alert"></p></div>`;
  } catch (error) {
    renderLogin(error.message);
    history.replaceState(null, "", location.pathname);
  }
}
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-care]");
  if (!button || button.disabled) return;
  const action = button.dataset.care,
    id = Number(button.dataset.id);
  try {
    if (action === "return-online") {
      location.reload();
      return;
    }
    if (!state.user || busy) return;
    if (action === "answer-survey") {
      state.surveyId = id;
      return navigate("surveys");
    }
    if (action === "survey-back") {
      state.surveyId = null;
      render();
      return;
    }
    if (action === "add-question") {
      if ($("#question-rows").children.length >= 20)
        throw new Error("Не более 20 вопросов");
      $("#question-rows").insertAdjacentHTML("beforeend", questionRow());
      return;
    }
    if (action === "remove-question") {
      if ($("#question-rows").children.length <= 1)
        throw new Error("Оставьте хотя бы один вопрос");
      button.closest(".question-row").remove();
      return;
    }
    if (action === "copy-template") {
      const template = state.templates.find(
        (t) => t.id === Number($("#copy-template").value),
      );
      fillBuilder({ ...template, title: template.title + " · моя версия" });
      return;
    }
    if (action === "record-plan") {
      if (isDoctor()) {
        state.tab = "plan";
        return navigate("card");
      }
      return navigate("plan");
    }
    if (action === "record-chat") {
      if (isDoctor()) {
        state.tab = "chat";
        return navigate("card");
      }
      return navigate("messages");
    }
    if (action === "record-diary") {
      if (isDoctor()) {
        state.tab = "overview";
        return navigate("card");
      }
      state.diary = "history";
      return navigate("diary");
    }
    if (action === "clear-offline") {
      await OfflineVault.clear();
      toast("Офлайн-копия удалена");
      return;
    }
    button.disabled = true;
    busy = true;
    try {
      if (action === "invite") {
        const invite = await api("/api/invites", {});
        const url =
          location.origin +
          location.pathname +
          "#join=" +
          encodeURIComponent(invite.token);
        const target = $("#invite-result");
        target.innerHTML = `<div class="source-note"><p>Ссылка для регистрации · одноразовая, 72 часа</p><input class="invite-url" aria-label="Ссылка приглашения" readonly value="${e(url)}"><button class="button small" data-care="copy-invite">Копировать ссылку</button>${invite.telegram_url ? `<p><a class="button" href="${e(invite.telegram_url)}" target="_blank" rel="noopener noreferrer">Открыть Telegram-бота</a></p>` : '<p class="caption">Telegram-бот пока не подключён. Веб-регистрация по этой ссылке уже работает.</p>'}</div>`;
      }
      if (action === "copy-invite") {
        await navigator.clipboard.writeText($(".invite-url").value);
        toast("Ссылка скопирована");
      }
      if (
        action === "appointment-cancel" ||
        action === "appointment-complete"
      ) {
        await write("/api/appointments/" + id + "/status", {
          status: action === "appointment-cancel" ? "cancelled" : "completed",
        });
        await load();
        toast("Статус консультации обновлён");
      }
      if (action === "cancel-survey") {
        await write("/api/surveys/" + id + "/cancel", {});
        await load();
        toast("Опрос отменён");
      }
      if (action === "medication-mark") {
        await write("/api/prescriptions/" + id + "/mark", {
          day: state.medicationDay || care().today,
          time: button.dataset.time,
          status: button.dataset.status,
        });
        await load();
        toast("Отметка сохранена");
      }
      if (action === "enable-push") {
        await enableDevicePush();
        await load();
        toast(
          "Подписка сохранена. Для фоновой доставки должен работать обработчик.",
        );
      }
      if (action === "disable-push") {
        await disableDevicePush();
        await load();
        toast("Push для этого браузера отключён");
      }
    } finally {
      busy = false;
      button.disabled = false;
    }
  } catch (error) {
    toast(error.message, true);
  }
});
document.addEventListener("change", (event) => {
  if (event.target.id === "medication-day") {
    state.medicationDay = event.target.value;
    render();
  }
});
document.addEventListener("submit", (event) => {
  const form = event.target;
  const fields = () => Object.fromEntries(new FormData(form));
  if (form.id === "intake-form") {
    const data = fields();
    if (data.password !== data.confirm) {
      $("#intake-error").hidden = false;
      $("#intake-error").textContent = "Пароли не совпадают";
      return;
    }
    if (form.dataset.activation === "false")
      Object.assign(data, {
        age: Number(data.age),
        height: Number(data.height),
        weight: Number(data.weight),
      });
    data.token = form.dataset.token;
    delete data.confirm;
    return run(form, async () => {
      const result = await api(
        "/api/intake/" +
          (form.dataset.activation === "true" ? "activate" : "register"),
        data,
      );
      history.replaceState(null, "", location.pathname);
      await OfflineVault.clear();
      if (form.dataset.activation === "true") {
        renderLogin();
        toast("Пароль сохранён. Войдите по телефону и новому паролю.");
      } else {
        busy = false;
        await login(result.username, data.password);
      }
    });
  }
  if (form.id === "offline-unlock-form")
    return run(form, async () =>
      renderOffline(await OfflineVault.unlock(form.pin.value)),
    );
  if (!state.user) return;
  if (form.id === "offline-save-form") {
    const pin = form.pin.value;
    if (pin !== form.confirm.value) {
      toast("PIN не совпадают", true);
      return;
    }
    return run(form, async () => {
      await OfflineVault.save(state, pin);
      form.reset();
      toast("Зашифрованная копия сохранена на устройстве");
    });
  }
  if (form.id === "appointment-form") {
    const data = fields();
    if (isDoctor()) data.patient_id = Number(data.patient_id);
    return run(form, async () => {
      await write("/api/appointments", data);
      await load();
      toast("Консультация добавлена в расписание");
    });
  }
  if (form.id === "profile-form") {
    const data = fields();
    data.height = data.height ? Number(data.height) : null;
    data.weight = data.weight ? Number(data.weight) : null;
    return run(form, async () => {
      await write("/api/patients/" + state.selected + "/profile", data);
      await load();
      toast("Основные данные сохранены");
    });
  }
  if (form.id === "contact-form") {
    const data = fields();
    return run(form, async () => {
      await api("/api/contact", data);
      await load();
      toast("Контакты обновлены");
    });
  }
  if (form.id === "encounter-form" || form.id === "lab-form") {
    const data = fields();
    return run(form, async () => {
      await write(
        "/api/patients/" +
          state.selected +
          (form.id === "encounter-form" ? "/encounters" : "/labs"),
        data,
      );
      await load();
      toast("Запись добавлена в карточку");
    });
  }
  if (form.id === "assign-survey-form") {
    const data = fields();
    data.template_id = Number(data.template_id);
    data.repeat_days = Number(data.repeat_days);
    data.due_at = new Date(data.due_at).toISOString();
    return run(form, async () => {
      await write("/api/patients/" + state.selected + "/surveys", data);
      await load();
      toast("Опрос назначен пациенту");
    });
  }
  if (form.id === "survey-answer-form") {
    const item = care().surveys.find((s) => s.id === Number(form.dataset.id));
    const answers = {};
    for (const q of item.questions) {
      const value = form.elements["q-" + q.id].value;
      answers[q.id] =
        q.type === "scale"
          ? Number(value)
          : q.type === "yes_no"
            ? value === "yes"
            : value;
    }
    return run(form, async () => {
      await write("/api/surveys/" + item.id + "/submit", { answers });
      state.surveyId = null;
      await load();
      toast("Ответы сохранены и доступны специалисту");
    });
  }
  if (form.id === "template-form") {
    const data = {
      title: form.title.value,
      description: form.description.value,
      questions: [...$("#question-rows").children].map((r) => ({
        label: r.querySelector(".question-label").value,
        type: r.querySelector(".question-type").value,
      })),
    };
    return run(form, async () => {
      await write("/api/surveys/templates", data);
      await load();
      toast("Шаблон сохранён. Теперь его можно назначить пациенту.");
    });
  }
  if (form.id === "generate-survey-form") {
    const data = fields();
    return run(form, async () => {
      const draft = await api("/api/surveys/generate", data);
      fillBuilder(draft);
      toast("ИИ-черновик готов. Проверьте вопросы и сохраните шаблон.");
    });
  }
  if (form.id === "assistant-form") {
    const data = fields();
    return run(form, async () => {
      await api("/api/patients/" + state.selected + "/assistant", data);
      await load();
      toast("ИИ подготовил черновик. План пациента не изменён.");
    });
  }
  if (form.id === "prescription-form") {
    const data = fields();
    data.times = [data.time1, data.time2].filter(Boolean);
    delete data.time1;
    delete data.time2;
    return run(form, async () => {
      await write("/api/patients/" + state.selected + "/prescriptions", data);
      await load();
      toast("Учебное назначение подтверждено");
    });
  }
  if (form.classList.contains("stop-prescription-form")) {
    const data = fields();
    return run(form, async () => {
      await write("/api/prescriptions/" + form.dataset.id + "/stop", data);
      await load();
      toast("Учебное назначение отменено");
    });
  }
});
