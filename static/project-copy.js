"use strict";
const licensedAssessments = new Set([
  "mmpi",
  "beck_hopelessness",
  "beck_depression",
]);
const letterTopics = [
  "Приём препарата: доза, время, пропуск",
  "Побочный эффект",
  "Самочувствие ухудшилось",
  "Сочетание с другими лекарствами",
  "Рецепт на препарат",
  "Анализы и обследования",
  "Запись, перенос или отмена приёма",
  "Справки и документы",
  "Дневник и опросники",
  "Другое",
];
function messageCount(value) {
  const n = Number(value),
    tail = n % 100;
  return `${n} ${tail >= 11 && tail <= 14 ? "сообщений" : n % 10 === 1 ? "сообщение" : n % 10 >= 2 && n % 10 <= 4 ? "сообщения" : "сообщений"}`;
}
function licensedAssessmentNotice(kind) {
  return `<section class="card"><h2>${e(extraAssessments[kind].title)}</h2><p>Проводится на приёме по лицензии.</p><p>Бланк и ключи в приложении не публикуются. Проведение и результат обсуждаются со специалистом.</p><button class="button" data-ext="assessment-cancel">Назад к заданиям</button></section>`;
}
function applyProjectCopy() {
  prototypeContent.course.forEach((item) => (item.min = 3));
  prototypeContent.relativeCourse = prototypeContent.relativeCourse.slice(0, 3);
  prototypeContent.relativeCourse.forEach((item) => (item.min = 3));
  const oldPlanPage = planPage;
  planPage = function (doctor = false) {
    const prescribed = care().prescriptions.filter(
      (p) => p.title === "Авиандр 20 мг",
    );
    return (
      (prescribed.length
        ? `<section class="card"><h2>Назначения врача</h2>${prescribed.map((p) => `<h3>${e(p.title)}</h3><p>${e(p.note)}</p>`).join("")}</section>`
        : "") + oldPlanPage(doctor)
    );
  };
  for (const kind of licensedAssessments) extraAssessments[kind].questions = [];
  const oldAssessment = assessmentAssignmentPanel;
  assessmentAssignmentPanel = function (doctor) {
    let html = oldAssessment(doctor);
    if (doctor)
      html += `<section class="card"><h2>Методики на приёме</h2>${[...licensedAssessments].map((k) => `<h3>${e(extraAssessments[k].title)}</h3><p>Проводится на приёме по лицензии.</p>`).join("")}</section>`;
    return html;
  };
  const oldLetters = lettersPage;
  lettersPage = function () {
    let html = oldLetters();
    if (!isDoctor())
      html =
        '<section class="notice info"><p>Врач отвечает на письма в течение 1–2 рабочих дней. Если нужна срочная помощь, нажмите SOS или позвоните 112.</p></section>' +
        html;
    else {
      const items = state.letters || [],
        filter = state.letterFilter || "all";
      const filtered = items.filter(
        (l) => filter === "all" || (filter === "new" ? !l.reply : !!l.reply),
      );
      state.letters = filtered;
      html = oldLetters();
      state.letters = items;
      html =
        `<div class="filter-group">${[
          ["new", `Новые (${items.filter((l) => !l.reply).length})`],
          ["answered", "Отвеченные"],
          ["all", "Все"],
        ]
          .map(
            ([k, t]) =>
              `<button data-copy-filter="${k}" aria-pressed="${filter === k}">${t}</button>`,
          )
          .join("")}</div>` + html;
    }
    return html;
  };
  // Names and descriptions only; do not invent or replace disputed phone numbers.
  prototypeContent.categories = prototypeContent.categories.map(
    ([key, title]) => [
      key,
      key === "urgent"
        ? "Угроза жизни и острое состояние"
        : key === "adult"
          ? "Психологическая помощь"
          : title,
    ],
  );
  prototypeContent.helplines = prototypeContent.helplines.filter(
    (h) => !(h.c === "adult" && h.url?.includes("msph.ru")),
  );
  for (const h of prototypeContent.helplines) {
    if (h.n.includes("ПКБ № 1")) h.url = "https://pkb1.ru/";
    if (
      h.n.includes("ПКБ № 1") ||
      h.n.includes("Без паники") ||
      h.n === "Кризисный центр помощи женщинам и детям" ||
      h.n.includes("телефон доверия для женщин")
    ) {
      h.ph = [];
      h.d =
        "Телефон и часы работы требуют сверки. Уточните контакты на официальном сайте. При угрозе жизни звоните 112.";
    }
    if (h.n.includes("Московская служба психологической помощи"))
      h.d += " · Есть бесплатные консультации психолога — msph.ru";
    if (h.ph.includes("103"))
      h.d += " · Экстренную психиатрическую помощь вызывают через скорую";
  }
  prototypeContent.news = [
    {
      cat: "Мероприятия",
      date: "Пример",
      title: "Встреча специалистов: дневник между приёмами",
      text: "Пример новости компании: обсуждение наблюдения за самочувствием и подготовки к повторной консультации.",
    },
    {
      cat: "Разработки",
      date: "Пример",
      title: "ПсиКомпас: новые задания и напоминания",
      text: "Пример новости компании: врач назначает формы, пациент видит сроки, а результаты обсуждаются на приёме.",
    },
    {
      cat: "Статьи",
      date: "Пример",
      title: "Как близкие могут поддержать человека",
      text: "Пример материала компании о согласии пациента, границах общения и плане безопасности.",
    },
  ];
  const oldDecorate = decoratePsicompas;
  decoratePsicompas = function () {
    oldDecorate();
    const root = $("#content");
    if (state.page === "card" && state.selected === 2)
      root.querySelector(".profile-banner .eyebrow").textContent =
        "КАРТОЧКА ПАЦИЕНТА · МОО97-26";
    root.querySelectorAll("dt").forEach((dt) => {
      if (
        ["Учебное ограничение", "Источник сведений"].includes(dt.textContent)
      ) {
        dt.nextElementSibling?.remove();
        dt.remove();
      }
    });
    root.querySelectorAll(".chip").forEach((chip) => {
      if (chip.textContent.startsWith("Правила synthetic-")) chip.remove();
    });
  };
  const oldChat = chatPage;
  chatPage = function () {
    return oldChat().replace(" · синтетический диалог", "");
  };
}
document.addEventListener("click", (event) => {
  const b = event.target.closest("[data-copy-filter]");
  if (b && !busy && isDoctor()) {
    state.letterFilter = b.dataset.copyFilter;
    render();
  }
});
