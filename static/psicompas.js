"use strict";

// The uploaded prototype supplies the visual language. Account rights and all
// shared care records continue to come from the authenticated server.
const practiceCatalog = {
  breathing: {
    title: "Спокойная пауза",
    seconds: 60,
    glyph: "sun",
    text: "Устройтесь удобно. Дышите в привычном ритме, без усилия и задержек. Можно просто наблюдать за кругом. Если некомфортно, остановитесь.",
    steps: [
      "Заметьте опору под ногами",
      "Расслабьте плечи, если удобно",
      "Дышите так, как вам комфортно",
    ],
  },
  grounding: {
    title: "Пять вещей вокруг",
    seconds: 60,
    glyph: "heart",
    text: "Мягко переведите внимание на то, что вас окружает. Ничего не нужно делать идеально.",
    steps: [
      "Найдите пять предметов, которые видите",
      "Заметьте три звука вокруг",
      "Почувствуйте опору под ногами",
    ],
  },
  stretch: {
    title: "Размяться без спешки",
    seconds: 120,
    glyph: "leaf",
    text: "Выберите удобное положение. Двигайтесь в комфортном диапазоне. При боли или головокружении остановитесь.",
    steps: [
      "Расположите стопы на опоре",
      "Мягко расправьте плечи",
      "Переведите взгляд от экрана и потянитесь, если удобно",
    ],
  },
};
const lessons = [
  {
    key: "diary",
    title: "Зачем вести дневник",
    subtitle: "2 минуты · наблюдение за собой",
    paragraphs: [
      "Короткая запись помогает вспомнить, как менялось самочувствие между встречами. Оценки отражают ваше ощущение в момент записи: это не диагноз и не экзамен.",
      "Можно отметить настроение, тревогу, сон и энергию, а затем добавить пару слов о дне. Пишите столько, сколько удобно. Если пропустили день, достаточно продолжить со следующей записи.",
      "Ваш специалист увидит сохранённые записи. Обсудите с ним, какие изменения стоит отмечать именно вам.",
    ],
    page: "diary",
    action: "Перейти в дневник",
  },
  {
    key: "consultation",
    title: "Как подготовиться к встрече",
    subtitle: "2 минуты · разговор со специалистом",
    paragraphs: [
      "Перед встречей можно записать, что изменилось, какие вопросы появились и что было трудно выполнять. Выберите один-два вопроса, с которых хочется начать.",
      "Посмотрите свои записи и отметьте примеры, которые хотите обсудить. При желании подготовьте список назначений и документов.",
      "Если непонятен согласованный план, попросите объяснить его простыми словами. Изменения в назначениях обсудите со специалистом.",
    ],
    page: "schedule",
    action: "Посмотреть встречи",
  },
  {
    key: "routine",
    title: "Маленькие шаги в течение дня",
    subtitle: "2 минуты · повседневная забота",
    paragraphs: [
      "Выберите небольшое действие, которое подходит вам сегодня: сделать паузу, выпить воды, выйти на короткую прогулку или написать близкому.",
      "Не обязательно выполнять всё сразу. Можно начать с одного посильного шага и заметить, как вы себя чувствуете после него.",
      "Эти материалы помогают ориентироваться в приложении и не заменяют личные рекомендации специалиста.",
    ],
    page: "move",
    action: "Выбрать паузу",
  },
];
let practiceSession = null;
let practiceTicker = null;
let homeTreePaused = false;

function treeArt(points = 0, animated = false) {
  let seed = 17;
  const random = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  const flowers = Array.from({ length: 54 }, (_, i) => {
    const angle = random() * Math.PI * 2;
    const radius = Math.sqrt(random());
    const x = 150 + Math.cos(angle) * radius * 103;
    const y = 111 + Math.sin(angle) * radius * 76;
    return `<g class="tree-blossom" opacity="${i < Math.min(54, 9 + points * 3) ? 1 : 0.14}"><circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${(5 + random() * 5).toFixed(1)}" fill="${["#f2a3b9", "#fbd3de", "#e77f9e"][i % 3]}"/><circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="2" fill="#e77f9e"/></g>`;
  }).join("");
  return `<svg class="care-tree${animated ? " animated-tree" : ""}" viewBox="0 0 300 300" role="img" aria-label="Цветущее дерево заботы"><ellipse cx="150" cy="283" rx="72" ry="7" fill="var(--line)"/><g class="tree-crown">${animated ? '<ellipse cx="150" cy="115" rx="109" ry="85" fill="#f2a3b9" opacity=".1"/>' : ""}<g fill="none" stroke="var(--trunk)" stroke-linecap="round"><path stroke-width="12" d="M150 278Q155 230 148 186Q138 140 153 92"/><path stroke-width="7" d="M150 216Q108 184 89 144M148 188Q183 165 211 123M147 161Q115 135 110 89M150 142Q174 123 183 76"/><path stroke-width="4" d="M122 193L76 177M102 167L106 124M176 171L222 165M186 151L181 111M140 147L152 112M120 125L87 110"/></g>${flowers}</g>${animated ? '<g class="tree-petal"><ellipse cx="218" cy="102" rx="4" ry="7" fill="#e77f9e"/></g><g class="tree-petal"><ellipse cx="83" cy="125" rx="4" ry="6" fill="#f2a3b9"/></g><g class="tree-petal"><ellipse cx="175" cy="83" rx="3" ry="6" fill="#e77f9e"/></g>' : ""}</svg>`;
}

function homeTree() {
  return `<figure class="home-tree-scene${homeTreePaused ? " is-paused" : ""}">${treeArt(carePoints(), true)}<button type="button" class="tree-motion-toggle" data-ui="tree-motion" aria-pressed="${homeTreePaused}" aria-label="Приостановить анимацию дерева">${homeTreePaused ? "Продолжить" : "Пауза"}</button></figure>`;
}
function careIllustration() {
  return `<svg class="care-illustration" viewBox="0 0 300 240" aria-hidden="true"><ellipse cx="168" cy="214" rx="108" ry="12" fill="var(--accent)" opacity=".06"/><path d="M51 120c-6-61 54-92 110-91 64 1 119 47 106 106-13 58-101 79-153 61-31-10-59-36-63-76Z" fill="var(--accent)" opacity=".07"/><rect x="189" y="30" width="78" height="46" rx="16" fill="var(--surface)"/><path d="m204 65-5 15 24-9" fill="var(--surface)"/><path d="M206 53h10l5-10 7 22 8-14h14" fill="none" stroke="var(--accent)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M85 205c-7-21-11-45-2-67 4-12 12-20 25-24l26-2c21 7 34 28 36 50l3 43Z" fill="var(--accent)"/><path d="m112 115-17 25 21 43 26-48-13-22" fill="var(--surface)"/><path d="M114 98v21c1 11 16 11 18 0V98" fill="#dfb99e"/><ellipse cx="122" cy="78" rx="25" ry="31" fill="#ebcbb4"/><path d="M97 84c-15-29 0-56 24-55 28 1 37 20 30 50-10-1-14-16-15-22-8 10-22 14-38 13Z" fill="#244653"/><path d="M111 85h1m20 0h1" stroke="#244653" stroke-width="3" stroke-linecap="round"/><path d="M117 98q7 5 13-1" fill="none" stroke="#ad7662" stroke-width="2" stroke-linecap="round"/><path d="m100 170 33-5 28 22-34 12-30-14" fill="#ebcbb4"/><rect x="128" y="153" width="54" height="66" rx="5" transform="rotate(-14 128 153)" fill="var(--surface)"/><path d="m143 169 24-6m-21 17 24-6m-21 17 18-5" stroke="var(--accent)" opacity=".35" stroke-width="3" stroke-linecap="round"/><path d="M69 213h115" stroke="var(--accent)" stroke-width="7" stroke-linecap="round"/><path d="M230 209v-49m0 24c-21-4-29-16-27-26 17-2 28 11 27 26Zm0-12c2-21 13-30 26-28 1 16-11 27-26 28Z" fill="var(--accent)" opacity=".45"/><path d="M211 202h37l-6 17h-25Z" fill="var(--accent)" opacity=".6"/><circle cx="62" cy="80" r="17" fill="var(--surface)"/><path d="M55 80h14m-7-7v14" stroke="var(--accent)" stroke-width="2" stroke-linecap="round"/></svg>`;
}
function carePoints() {
  const days = new Set(
    (state.detail?.reports || []).map((r) => clinicDay(r.created_at)),
  );
  return days.size + (state.wellbeing?.activities.length || 0);
}
function clinicDay(value) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Moscow",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(value));
}
function moodFaces(selected = -1, quick = false) {
  return `<div class="mood-faces" role="group" aria-label="Выберите настроение">${[0, 2, 5, 8, 10].map((value, i) => `<button type="button" class="mood-face" data-ui="${quick ? "quick-mood" : "mood"}" data-value="${value}" aria-label="${["Очень плохо", "Плохо", "Так себе", "Неплохо", "Хорошо"][i]} · ${value} из 10" aria-pressed="${selected === value}"><svg viewBox="0 0 44 44" aria-hidden="true"><circle cx="22" cy="22" r="20" fill="${["#e0796b", "#eba06a", "#e9cb72", "#a9cf8a", "#6fbf9a"][i]}"/><g fill="none" stroke="#1b2430" stroke-width="2" stroke-linecap="round"><path d="M14 17h1M29 17h1"/><path d="M14 29Q22 ${[17, 22, 29, 35, 40][i]} 30 29"/></g></svg><span>${["Очень плохо", "Плохо", "Так себе", "Неплохо", "Хорошо"][i]}</span></button>`).join("")}</div>`;
}
function medicationPreview() {
  const c = care();
  const active = c.prescriptions.filter(
    (p) => p.active && p.starts_on <= c.today && p.ends_on >= c.today,
  );
  return `<section class="card medication-card"><div class="card-heading"><h2>Мои препараты</h2><button class="text-button" data-action="nav" data-page="medications">График приёма</button></div><p class="caption">Вымышленные ДЕМО-варианты</p>${
    active.length
      ? active
          .slice(0, 2)
          .map(
            (p) =>
              `<div class="medication-preview"><h3>${e(p.title)}</h3><p class="caption">${e(p.note)}</p><div class="dose-preview">${p.times
                .map((time) => {
                  const taken = c.medication_marks.find(
                    (m) =>
                      m.prescription_id === p.id &&
                      m.day === c.today &&
                      m.scheduled_time === time,
                  );
                  const future =
                    new Date(c.today + "T" + time + ":00+03:00") > new Date();
                  return `<button class="dose-tile ${taken?.status === "taken" ? "taken" : ""}" data-care="medication-mark" data-id="${p.id}" data-time="${time}" data-status="taken" aria-pressed="${taken?.status === "taken"}" ${future ? "disabled" : ""}><strong>${e(time)} · МСК</strong><span>${taken?.status === "taken" ? "✓ Принято" : taken?.status === "skipped" ? "Пропущено · изменить" : future ? "Предстоит" : "Отметить приём"}</span></button>`;
                })
                .join("")}</div></div>`,
          )
          .join("")
      : '<p class="muted">Пока нет активных назначений.</p><button class="button" data-action="nav" data-page="plan">Мой план</button>'
  }</section>`;
}

patientOverview = function () {
  const c = care();
  const pending = c.surveys.filter((s) => s.status === "assigned");
  const day = new Date().toLocaleDateString("ru-RU", {
    weekday: "long",
    day: "numeric",
    month: "long",
    timeZone: "Europe/Moscow",
  });
  const name = state.user.name.split(" ")[0];
  const actions = [
    ["schedule", "clock", "Встречи"],
    ["surveys", "book", "Опросы"],
    ["diary", "sun", "Дневник"],
    ["medications", "leaf", "Таблетница"],
    ["records", "chart", "Моя карта"],
    ["messages", "chat", "Чат"],
  ];
  return `<div class="patient-dashboard"><div class="today-heading"><div><p class="eyebrow">${e(day)}</p><h1>Здравствуйте, ${e(name)}</h1><p class="muted">Небольшие шаги. Каждый день.</p></div><button class="help-pill" data-action="nav" data-page="help">Помощь</button></div>
    <div class="quick-grid home-actions" aria-label="Быстрые действия">${actions.map(([page, glyph, label]) => `<button class="quick-card" data-action="nav" data-page="${page}"><span class="action-circle">${icon(glyph)}</span><strong>${label}</strong></button>`).join("")}</div>
    <section class="welcome-garden"><div><span class="eyebrow">ВРЕМЯ ДЛЯ СЕБЯ</span><h2>Забота рядом.<br>В вашем ритме.</h2><p>Замечайте своё состояние и оставайтесь на связи со специалистом.</p><button class="button primary" data-action="nav" data-page="tree">Моё дерево ${icon("arrow")}</button></div>${homeTree()}</section>
    ${appointmentStrip()}
    ${pending.length ? `<section class="notice info survey-reminder"><div><span class="eyebrow">ОТ СПЕЦИАЛИСТА</span><h2>${pending.length === 1 ? "Вас ждёт опрос" : "Вас ждут опросы"}</h2><p>${e(pending[0].title)} · до ${e(clinicDate(pending[0].due_at))}</p></div><button class="button primary" data-action="nav" data-page="surveys">Назначенные опросы · ${pending.length} ${icon("arrow")}</button></section>` : ""}
    ${medicationPreview()}
    <section class="card mood-card"><h2>Как настроение?</h2><p class="caption">Минута внимания к себе</p>${moodFaces(-1, true)}<button class="button primary full" data-ui="open-diary">Заполнить дневник ${icon("arrow")}</button></section>
    <section class="card specialist-card">${specialistContact()}<p class="caption">Вопросы и наблюдения можно обсудить в переписке.</p><button class="button full" data-action="nav" data-page="messages">${icon("chat")}Написать врачу</button></section>
    <section class="card home-trend"><div class="card-heading"><h2>Моя динамика</h2><button class="text-button" data-action="history">История</button></div>${chart(state.detail.reports)}</section></div>`;
};
function specialistContact() {
  const doctor = state.detail.doctor;
  const phone = (doctor.phone || "").replace(/[\s()\-]/g, "");
  return `<div class="patient-row">${avatar(doctor.name, "blue")}<div class="patient-info"><strong>${e(doctor.name)}</strong><small>Ваш ведущий специалист</small></div></div>${/^\+\d{10,15}$/.test(phone) ? `<a class="button full" href="tel:${e(phone)}">${icon("heart")}Позвонить специалисту</a>` : '<p class="caption">Телефон специалиста пока не указан</p>'}`;
}

const baseDiaryPage = diaryPage;
const diaryTabs = () =>
  `<div class="tabs"><button data-action="diary" data-mode="form" class="${state.diary === "form" ? "active" : ""}">Самоотчёт</button><button data-action="diary" data-mode="calendar" class="${state.diary === "calendar" ? "active" : ""}">Календарь</button><button data-action="diary" data-mode="history" class="${state.diary === "history" ? "active" : ""}">История записей</button></div>`;
diaryPage = function () {
  if (state.diary === "calendar")
    return (
      heading(
        "МОЙ ДНЕВНИК",
        "Каждый день имеет значение",
        "Выберите день, чтобы посмотреть сохранённые записи.",
      ) +
      diaryTabs() +
      calendarView()
    );
  let html = baseDiaryPage();
  html = html.replace(/<div class="tabs">.*?<\/div>/s, diaryTabs());
  if (state.diary !== "history") {
    html = html.replace(
      '<label class="range-label" for="mood">',
      moodFaces(5) + '<label class="range-label" for="mood">',
    );
    html = html.replace(
      '<label for="adherence">',
      [
        ["sleep", "Качество сна", "Очень плохо", "Отлично"],
        ["energy", "Энергия", "Нет сил", "Много сил"],
      ]
        .map(
          ([id, title, low, high]) =>
            `<label class="range-label" for="${id}">${title}<output id="${id}-value" for="${id}">5 / 10</output></label><input id="${id}" name="${id}" type="range" min="0" max="10" value="5"><div class="scale"><span>${low}</span><span>${high}</span></div>`,
        )
        .join("") + '<label for="adherence">',
    );
  }
  return html;
};
function calendarView() {
  const today = care().today;
  const month = state.calendarMonth || today.slice(0, 7);
  const [year, m] = month.split("-").map(Number);
  const start = new Date(Date.UTC(year, m - 1, 1));
  const offset = (start.getUTCDay() + 6) % 7;
  const count = new Date(Date.UTC(year, m, 0)).getUTCDate();
  const reports = state.detail.reports;
  const chosen = state.calendarDay || today;
  const monthLabel = start.toLocaleDateString("ru-RU", {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
  const cells =
    Array.from(
      { length: offset },
      () => '<span class="calendar-empty"></span>',
    ).join("") +
    Array.from({ length: count }, (_, i) => {
      const day = `${month}-${String(i + 1).padStart(2, "0")}`;
      const records = reports.filter((r) => clinicDay(r.created_at) === day);
      return `<button class="calendar-day ${day === today ? "today" : ""}" data-ui="calendar-day" data-day="${day}" aria-label="${e(day)} · ${records.length} записей" aria-pressed="${day === chosen}" ${day > today ? "disabled" : ""}><span>${i + 1}</span><i class="mood-dot ${records.length ? "filled" : ""}"></i></button>`;
    }).join("");
  const chosenReports = reports.filter(
    (r) => clinicDay(r.created_at) === chosen,
  );
  return `<section class="card"><div class="card-heading"><button class="icon-button" data-ui="month" data-offset="-1" aria-label="Предыдущий месяц">‹</button><h2>${e(monthLabel)}</h2><button class="icon-button" data-ui="month" data-offset="1" aria-label="Следующий месяц" ${month >= today.slice(0, 7) ? "disabled" : ""}>›</button></div><div class="calendar-grid">${["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"].map((v) => `<span class="weekday">${v}</span>`).join("")}${cells}</div><p class="caption">Точка — есть запись. Доступны последние 100 самоотчётов.</p></section><section class="card"><h2>${e(chosen.split("-").reverse().join("."))}</h2>${chosenReports.length ? reportList(chosenReports) : '<p class="muted">За этот день нет записей в загруженной истории.</p>'}</section>`;
}

function treePage() {
  const points = carePoints();
  return (
    heading(
      "МОЁ ДЕРЕВО",
      "Забота складывается из мелочей",
      "Дерево расцветает от записей и завершённых занятий.",
    ) +
    `<section class="card tree-card">${treeArt(points)}<h2>${points} ${points === 1 ? "отметка" : "отметок"} заботы</h2><p class="muted">Дни с записями и занятия в доступной истории. Это визуальный символ участия, а не оценка здоровья.</p><button class="button primary" data-ui="open-diary">Заполнить дневник</button><button class="button" data-action="nav" data-page="move">Выбрать небольшую паузу</button></section>`
  );
}
function wellbeingSummary() {
  const activities = state.wellbeing?.activities || [];
  return `<section class="card"><h2>Занятия и материалы</h2><p class="caption">Самоотметки пациента, без измерения нагрузки и клинических выводов.</p>${
    activities.length
      ? activities
          .slice(0, 6)
          .map(
            (a) =>
              `<div class="activity-row">${icon("check")}<div><strong>${e(a.title)}</strong><small>${e(clinicDate(a.created_at))} · ${a.kind === "lesson" ? "прочитано" : "выполнено"}</small></div></div>`,
          )
          .join("")
      : '<p class="muted">Пациент пока не отмечал занятия.</p>'
  }</section>`;
}
function practiceView() {
  const session = practiceSession;
  const item = practiceCatalog[session.key];
  return `<section class="card practice-card"><p class="eyebrow">В СВОЁМ РИТМЕ</p><h2>${item.title}</h2><p>${item.text}</p><div class="breath-space"><div class="breathing-orb ${session.key === "breathing" && session.running ? "running" : ""}"><span id="practice-time">${practiceRemaining()}</span></div></div><ol class="practice-steps">${item.steps.map((s) => `<li>${s}</li>`).join("")}</ol><p class="caption">Таймер помогает выделить время. Приложение не измеряет дыхание или нагрузку.</p><div class="practice-actions"><button class="button primary" data-ui="practice-toggle">${session.running ? "Пауза" : "Продолжить"}</button><button class="button" data-ui="practice-close">Завершить без отметки</button></div><button class="button primary full" id="practice-save" data-ui="practice-save" ${practiceSecondsLeft() > 0 ? "hidden" : ""}>Отметить выполненным</button></section>`;
}
function movementPage() {
  const activities = (state.wellbeing?.activities || []).filter(
    (a) => a.kind === "practice",
  );
  return (
    heading(
      "В СВОЁМ РИТМЕ",
      "Пауза для себя",
      "Небольшое занятие по вашему желанию.",
    ) +
    (practiceSession
      ? practiceView()
      : `<section class="notice info"><h2>Без спешки и нормативов</h2><p>Выберите то, что подходит вам сейчас. Любое занятие можно остановить.</p></section>${Object.entries(
          practiceCatalog,
        )
          .map(
            ([key, item]) =>
              `<section class="card practice-option"><div class="routine-icon">${icon(item.glyph)}</div><div><p class="eyebrow">${item.seconds / 60} МИН</p><h2>${item.title}</h2><p class="caption">${item.steps[0]}</p></div><button class="button" data-ui="practice-start" data-key="${key}">Начать ${icon("arrow")}</button></section>`,
          )
          .join("")}`) +
    `<section class="card"><h2>Мои занятия</h2>${
      activities.length
        ? activities
            .slice(0, 8)
            .map(
              (a) =>
                `<div class="activity-row"><span>${icon("check")}</span><div><strong>${e(a.title)}</strong><small>${e(clinicDate(a.created_at))} · самоотметка</small></div></div>`,
            )
            .join("")
        : '<p class="muted">Здесь появятся занятия, которые вы отметите выполненными.</p>'
    }</section>`
  );
}
function learningPage() {
  const done = state.wellbeing?.lessons || [];
  const selected = lessons.find((l) => l.key === state.lesson);
  if (selected)
    return (
      heading("ЗНАНИЯ", selected.title, selected.subtitle) +
      `<button class="back-link" data-ui="lesson-back">${icon("back")}Все материалы</button><article class="card lesson-body">${selected.paragraphs.map((p) => `<p>${p}</p>`).join("")}<button class="button primary" data-ui="lesson-complete" data-key="${selected.key}" ${done.includes(selected.key) ? "disabled" : ""}>${done.includes(selected.key) ? "✓ Прочитано" : "Отметить прочитанным"}</button><button class="button" data-action="nav" data-page="${selected.page}">${selected.action} ${icon("arrow")}</button></article>`
    );
  return (
    heading(
      "ШКОЛА ПАЦИЕНТА",
      "Понятно о повседневном",
      "Короткие материалы для знакомства с заботой о себе.",
    ) +
    `<section class="notice info"><h2>${done.length} из ${lessons.length} материалов прочитано</h2><progress max="${lessons.length}" value="${done.length}" aria-label="Прочитанные материалы"></progress><p>Общие информационные заметки. Программу обучения с медкомандой можно добавить позже.</p></section>${lessons.map((l, i) => `<button class="card lesson-option" data-ui="lesson" data-key="${l.key}"><span class="lesson-number">${done.includes(l.key) ? "✓" : String(i + 1).padStart(2, "0")}</span><span><strong>${l.title}</strong><small>${l.subtitle}</small></span>${icon("arrow")}</button>`).join("")}`
  );
}
function helpPage() {
  return (
    heading(
      "ПОМОЩЬ РЯДОМ",
      "Как вы сейчас?",
      "Выберите удобный следующий шаг.",
    ) +
    `<section class="notice urgent-help"><p class="eyebrow">ЕСЛИ ОПАСНОСТЬ НЕПОСРЕДСТВЕННАЯ</p><h2>Обратитесь за срочной помощью</h2><p>В России можно позвонить 112. В другой стране используйте местный экстренный номер. Не ждите ответа в приложении.</p><a class="button danger" href="tel:112">Позвонить 112</a><p class="caption">Приложение не вызывает помощь автоматически.</p></section><section class="card"><h2>Хочется немного опоры</h2><p class="muted">Можно переключить внимание на окружающее или сделать спокойную паузу.</p><button class="button" data-ui="help-practice" data-key="grounding">Пять вещей вокруг ${icon("arrow")}</button><button class="button" data-ui="help-practice" data-key="breathing">Спокойная пауза ${icon("arrow")}</button></section><section class="card"><h2>Связаться со специалистом</h2>${specialistContact()}<button class="button primary full" data-action="nav" data-page="messages">Написать врачу ${icon("chat")}</button><p class="caption">Чат не экстренный. Срок ответа нужно согласовать со специалистом.</p></section><section class="card"><h2>Рассказать о своём состоянии</h2><p class="muted">Сохраните запись в дневнике. Отметка об опасениях за безопасность создаст сигнал в кабинете специалиста.</p><button class="button full" data-ui="open-diary">Открыть дневник</button><p class="caption">Отправка записи не подтверждает, что специалист уже прочитал её.</p></section>`
  );
}

const careLogin = renderLogin;
const careSettings = settingsPage;
settingsPage = function () {
  return (
    heading(
      "ПСИКОМПАС С СОБОЙ",
      "Установить приложение",
      "Открывайте его с главного экрана телефона.",
    ) +
    `<section class="card"><button class="button primary full" data-ui="install">${icon("plus")}Установить PWA</button><p class="caption">Android / Chrome: «Установить приложение» в меню браузера. iPhone / Safari: «Поделиться» → «На экран Домой». На телефоне нужен адрес с HTTPS.</p><p class="caption">Офлайн-копию назначений можно сохранить ниже с PIN-кодом.</p></section>` +
    careSettings()
  );
};
renderLogin = function (error = "") {
  careLogin(error);
  const brand = $(".login-form-side .brand");
  if (brand)
    brand.innerHTML =
      '<img class="compass-logo" src="/static/icon.svg" alt="" width="30" height="30"><span class="visually-hidden">ПсиКомпас</span><span>ПсиКомпас<small>Пространство заботы</small></span>';
  const title = $(".login-form-side h1");
  if (title) title.innerHTML = "Забота рядом.<br>Каждый день.";
  const art = $(".login-art");
  if (art)
    art.innerHTML = `${careIllustration()}<p class="eyebrow">ПРОСТРАНСТВО ЗАБОТЫ</p><h2>Рядом. Даже между встречами.</h2><p>Замечать изменения.<br>Оставаться на связи.</p>`;
};
function decoratePsicompas() {
  const doctor = isDoctor();
  $("#session-role").textContent =
    `${doctor ? "Специалист" : "Пациент"} · демо`;
  $("#more-button").hidden = false;
  document.body.dataset.role = state.user.role;
  document.body.dataset.page = state.page;
  $("#content").dataset.view = state.page;
  $("#header-user").textContent = state.user.name;
  $("#sidebar-account").innerHTML =
    `${avatar(state.user.name, "blue")}<span><strong>${e(state.user.name)}</strong><small>${doctor ? "Специалист" : state.user.role === "relative" ? "Близкий" : "Пациент"}</small></span>`;
  $("#workspace-tools").innerHTML = (
    state.user.role === "relative"
      ? [["settings", "info", "Настройки"]]
      : [
          ...(doctor ? [["overview", "home", "Главная"]] : []),
          ["schedule", "clock", "Мои встречи"],
          ["settings", "info", "Настройки"],
        ]
  )
    .map(
      ([page, glyph, label]) =>
        `<button class="nav-item ${state.page === page ? "active" : ""}" data-action="nav" data-page="${page}" ${state.page === page ? 'aria-current="page"' : ""}>${icon(glyph)}<span>${label}</span></button>`,
    )
    .join("");
  const parent = {
    surveys: "diary",
    records: "messages",
    medications: "overview",
    plan: "overview",
    tree: "overview",
    card: "patients",
    builder: "settings",
    about: "settings",
    scenarios: "settings",
  }[state.page];
  if (parent) {
    const item = $(`#navigation [data-page="${parent}"]`);
    if (item) {
      item.classList.add("active");
      item.setAttribute("aria-current", "page");
    }
  }
  if (state.page !== "move" && practiceSession?.running) pausePractice();
  updateThemeControl();
  rememberRoute();
}
const pageSets = {
  patient: new Set([
    "overview",
    "diary",
    "move",
    "learn",
    "help",
    "messages",
    "settings",
    "plan",
    "surveys",
    "medications",
    "records",
    "schedule",
    "tree",
    "about",
  ]),
  doctor: new Set([
    "overview",
    "patients",
    "messages",
    "settings",
    "schedule",
    "card",
    "builder",
    "scenarios",
    "about",
    "medications",
  ]),
};
let restoringRoute = false;
function rememberRoute() {
  if (restoringRoute || !state.user) return;
  const route = {
    page: state.page,
    selected: state.selected,
    tab: state.tab,
    user: state.user.id,
  };
  const old = history.state?.compass;
  if (old && JSON.stringify(old) === JSON.stringify(route)) return;
  const method = old?.user === route.user ? "pushState" : "replaceState";
  history[method](
    { compass: route },
    "",
    "#page=" + encodeURIComponent(state.page),
  );
}
window.addEventListener("popstate", async (event) => {
  if (!state.user) return;
  const route = event.state?.compass;
  if (
    !route ||
    route.user !== state.user.id ||
    !pageSets[state.user.role]?.has(route.page)
  )
    return;
  if (busy) {
    history.replaceState(
      {
        compass: {
          page: state.page,
          selected: state.selected,
          tab: state.tab,
          user: state.user.id,
        },
      },
      "",
      "#page=" + state.page,
    );
    return;
  }
  restoringRoute = true;
  try {
    state.tab = route.tab;
    await navigate(route.page, route.selected);
  } finally {
    restoringRoute = false;
  }
});
function updateThemeControl() {
  const dark =
    document.documentElement.dataset.theme === "dark" ||
    (!document.documentElement.dataset.theme &&
      matchMedia("(prefers-color-scheme: dark)").matches);
  $("#theme-toggle").setAttribute(
    "aria-label",
    dark ? "Включить светлую тему" : "Включить тёмную тему",
  );
  $("meta[name=theme-color]").content = dark ? "#08405e" : "#0b6390";
}
try {
  const theme = localStorage.getItem("psicompas-theme");
  if (["light", "dark"].includes(theme))
    document.documentElement.dataset.theme = theme;
} catch {}
$("#theme-toggle").onclick = () => {
  const current =
    document.documentElement.dataset.theme ||
    (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  const theme = current === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = theme;
  try {
    localStorage.setItem("psicompas-theme", theme);
  } catch {}
  updateThemeControl();
};
function practiceSecondsLeft() {
  if (!practiceSession) return 0;
  return Math.max(
    0,
    Math.ceil(
      (practiceSession.remaining -
        (practiceSession.running ? Date.now() - practiceSession.started : 0)) /
        1000,
    ),
  );
}
function practiceRemaining() {
  const seconds = practiceSecondsLeft();
  return seconds
    ? `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`
    : "Готово";
}
function pausePractice() {
  if (practiceSession?.running) {
    practiceSession.remaining = Math.max(
      0,
      practiceSession.remaining - (Date.now() - practiceSession.started),
    );
    practiceSession.running = false;
  }
  clearInterval(practiceTicker);
}
function tickPractice() {
  clearInterval(practiceTicker);
  practiceTicker = setInterval(() => {
    if (!state.user || state.page !== "move") {
      pausePractice();
      return;
    }
    const time = $("#practice-time");
    if (time) time.textContent = practiceRemaining();
    if (practiceSecondsLeft() === 0) {
      pausePractice();
      if ($("#practice-save")) $("#practice-save").hidden = false;
      $(".breathing-orb")?.classList.remove("running");
      const toggle = $('[data-ui="practice-toggle"]');
      if (toggle) toggle.hidden = true;
    }
  }, 250);
}
async function startPractice(key) {
  if (!practiceCatalog[key]) return;
  pausePractice();
  practiceSession = {
    key,
    remaining: practiceCatalog[key].seconds * 1000,
    started: Date.now(),
    running: true,
  };
  await navigate("move");
  tickPractice();
}
document.addEventListener("visibilitychange", () => {
  if (document.hidden && practiceSession?.running) {
    pausePractice();
    if (state.user && state.page === "move") render();
  }
});
const baseClearSession = clearSession;
clearSession = function () {
  pausePractice();
  practiceSession = null;
  baseClearSession();
  $("#sidebar-account").replaceChildren();
  $("#header-user").textContent = "";
  state.wellbeing = null;
  state.lesson = null;
  state.calendarMonth = null;
  state.calendarDay = null;
  if (location.hash.startsWith("#page="))
    history.replaceState(null, "", location.pathname);
};

document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-ui]");
  if (!button || button.disabled || !state.user || busy) return;
  const action = button.dataset.ui;
  const key = button.dataset.key;
  try {
    if (action === "tree-motion") {
      homeTreePaused = !homeTreePaused;
      button
        .closest(".home-tree-scene")
        .classList.toggle("is-paused", homeTreePaused);
      button.setAttribute("aria-pressed", String(homeTreePaused));
      button.textContent = homeTreePaused ? "Продолжить" : "Пауза";
    } else if (action === "install") {
      if (pendingInstall) await $("#install").onclick();
      else
        toast(
          "Откройте меню браузера: «Установить приложение» или «На экран Домой».",
        );
    } else if (["open-diary", "quick-mood"].includes(action)) {
      state.diary = "form";
      await navigate("diary");
      if (action === "quick-mood" && $("#mood"))
        setMood(Number(button.dataset.value));
    } else if (action === "mood") setMood(Number(button.dataset.value));
    else if (action === "calendar-day") {
      state.calendarDay = button.dataset.day;
      render();
    } else if (action === "month") {
      const [y, m] = (state.calendarMonth || care().today.slice(0, 7))
        .split("-")
        .map(Number);
      state.calendarMonth = new Date(
        Date.UTC(y, m - 1 + Number(button.dataset.offset), 1),
      )
        .toISOString()
        .slice(0, 7);
      render();
    } else if (action === "lesson") {
      state.lesson = key;
      render();
      window.scrollTo(0, 0);
    } else if (action === "lesson-back") {
      state.lesson = null;
      render();
    } else if (action === "practice-start" || action === "help-practice")
      await startPractice(key);
    else if (action === "practice-toggle") {
      if (practiceSession.running) pausePractice();
      else {
        practiceSession.started = Date.now();
        practiceSession.running = true;
        tickPractice();
      }
      render();
    } else if (action === "practice-close") {
      pausePractice();
      practiceSession = null;
      render();
    } else if (action === "practice-save" || action === "lesson-complete") {
      if (
        action === "practice-save" &&
        (!practiceSession || practiceSecondsLeft() > 0)
      )
        return;
      busy = true;
      button.disabled = true;
      try {
        await write("/api/patients/" + state.selected + "/wellbeing", {
          activity: action === "lesson-complete" ? key : practiceSession.key,
        });
        if (action === "practice-save") {
          pausePractice();
          practiceSession = null;
        }
        await load();
        toast(
          action === "lesson-complete"
            ? "Прочитано. Отметка сохранена."
            : "Занятие отмечено. Спасибо за время для себя.",
        );
      } finally {
        busy = false;
        button.disabled = false;
      }
    }
  } catch (error) {
    toast(error.message, true);
  }
});
function setMood(value) {
  $("#mood").value = value;
  $("#mood").dispatchEvent(new Event("input", { bubbles: true }));
}
document.addEventListener("input", (event) => {
  if (event.target.id === "mood")
    document
      .querySelectorAll('[data-ui="mood"]')
      .forEach((b) =>
        b.setAttribute(
          "aria-pressed",
          Number(b.dataset.value) === Number(event.target.value),
        ),
      );
});

updateThemeControl();
