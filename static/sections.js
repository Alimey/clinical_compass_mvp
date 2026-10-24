"use strict";
// Full section map from the supplied prototype. Shared records use the API;
// unsupported device/organization connections are labelled as demo examples.
const ws = () =>
  state.workspace || {
    preferences: {},
    entries: [],
    assessments: [],
    events: [],
    letters: [],
    progress: [],
  };
const pref = () => ws().preferences;
const sub = (group, fallback) => state.sectionTabs?.[group] || fallback;
const planLabels = [
  ["signs", "Мои предупреждающие сигналы"],
  ["self", "Что я могу сделать сам(а)"],
  ["distract", "Люди и места, которые помогают отвлечься"],
  ["people", "Кому я могу сказать, что мне плохо"],
  ["pros", "Специалисты и экстренная помощь"],
  ["safe", "Как сделать обстановку безопаснее"],
];
function sectionTabs(group, options, fallback) {
  return `<div class="tabs section-tabs" aria-label="Разделы">${options.map(([key, title]) => `<button data-ext="sub" data-group="${group}" data-key="${key}" class="${sub(group, fallback) === key ? "active" : ""}" aria-pressed="${sub(group, fallback) === key}">${title}</button>`).join("")}</div>`;
}
const demoNote = (text) => `<p class="source-note">${text}</p>`;
function entriesList(kind) {
  const items = ws().entries.filter((n) => n.kind === kind);
  return items.length
    ? items
        .map(
          (n) =>
            `<article class="report-item"><p class="caption">${e(clinicDate(n.created_at))} · ${n.shared ? "Видно специалисту" : "Только мне"}</p>${Object.entries(
              n.data,
            )
              .filter(([, v]) => v)
              .map(
                ([k, v]) =>
                  `<p class="report-text"><b>${e({ text: "Заметка", time: "Время", meal: "Приём пищи", what: "Что ели", appetite: "Аппетит", feeling: "Состояние", situation: "Ситуация", thought: "Мысль", emotion: "Эмоция", alternative: "Другой взгляд", after: "Эмоция после", name: "Название", note: "Комментарий" }[k] || k)}:</b> ${e(v)}</p>`,
              )
              .join("")}</article>`,
        )
        .join("")
    : '<p class="muted">Записей пока нет.</p>';
}
function entryForm(kind, fields, shared = true) {
  return `<form class="entry-form" data-kind="${kind}">${fields.map(([name, label, type = "text"]) => `<label>${label}${type === "textarea" ? `<textarea name="${name}" maxlength="1000" rows="3" ${name === fields[0][0] ? "required" : ""}></textarea>` : `<input name="${name}" type="${type}" maxlength="1000" ${name === fields[0][0] ? "required" : ""}>`}</label>`).join("")}<label class="consent-switch"><input name="shared" type="checkbox" ${shared ? "checked" : ""}><span>Показать специалисту</span></label><button class="button primary" type="submit">Сохранить запись</button></form>`;
}
function extendedDiaryPage() {
  return patientDiaryScreen();
}
const sectionPatientHome = patientOverview;
patientOverview = function () {
  return sectionPatientHome().replace(
    '<section class="welcome-garden">',
    `<div class="home-shortcuts"><button class="button" data-action="nav" data-page="consents">${icon("shield")}Мои согласия</button></div><section class="welcome-garden">`,
  );
};
const sectionDiary = diaryPage;
diaryPage = function () {
  const html = sectionDiary();
  return state.diary === "form"
    ? html.replace(
        '<label for="adverse">',
        `<div class="symptom-picker"><h3>Жалобы сегодня</h3><div class="filter-group">${["Плохой сон", "Сонливость", "Головная боль", "Головокружение", "Напряжение", "Тошнота"].map((s) => `<button type="button" data-ext="symptom" data-key="${s}" aria-pressed="false">${s}</button>`).join("")}</div></div><label for="adverse">`,
      )
    : html;
};
const sectionPoints = carePoints;
carePoints = function () {
  return (
    sectionPoints() +
    (ws().progress || []).filter((r) => r.resource.startsWith("course-")).length
  );
};
function additionalChart() {
  const reports = state.detail.reports
    .filter((r) => r.sleep != null && r.energy != null)
    .slice(0, 21)
    .reverse();
  if (!reports.length)
    return '<p class="muted">График появится после записи сна и энергии.</p>';
  const x = (i) =>
    reports.length === 1 ? 170 : 20 + (300 * i) / (reports.length - 1);
  return `<svg class="trend" viewBox="0 0 340 150" role="img" aria-label="Сон и энергия от 0 до 10"><path d="M20 15H320M20 70H320M20 125H320" stroke="var(--line)"/>${[
    ["sleep", "#22a3db"],
    ["energy", "#1f7a55"],
  ]
    .map(
      ([k, c]) =>
        `<polyline fill="none" stroke="${c}" stroke-width="3" points="${reports.map((r, i) => `${x(i)},${125 - r[k] * 11}`).join(" ")}"/>`,
    )
    .join(
      "",
    )}</svg><p class="caption">Голубой — сон · зелёный — энергия. Последние ${reports.length} записей.</p><details><summary>Посмотреть значения</summary>${reports.map((r) => `<p class="caption">${e(clinicDate(r.created_at))} · сон ${r.sleep}/10 · энергия ${r.energy}/10</p>`).join("")}</details>`;
}
function assessmentPage(doctor = false) {
  let chosen = state.assessmentKind;
  if (
    !doctor &&
    !ws().assessment_assignments?.some(
      (a) =>
        a.id === state.assessmentAssignment &&
        a.kind === chosen &&
        a.status === "assigned",
    )
  )
    chosen = null;
  const available = doctor ? ["hama"] : ["gad7", "phq9"];
  if (extraAssessments[chosen] || ["schulte", "serial7"].includes(chosen))
    return extendedAssessment(chosen);
  if (chosen && available.includes(chosen)) {
    const items = prototypeContent[chosen];
    const maximum = chosen === "hama" ? 4 : 3;
    return `<section class="card"><h2>${{ gad7: "GAD-7", phq9: "PHQ-9", hama: "HAM-A" }[chosen]}</h2><form id="assessment-form" data-kind="${chosen}">${items.map((q, i) => `<label>${i + 1}. ${e(q)}<select name="q${i}" required><option value="">Выберите ответ</option>${Array.from({ length: maximum + 1 }, (_, v) => `<option value="${v}">${v} · ${maximum === 3 ? ["Ни разу", "Несколько дней", "Больше половины дней", "Почти каждый день"][v] : ["Нет", "Легко", "Умеренно", "Выраженно", "Очень выраженно"][v]}</option>`).join("")}</select></label>`).join("")}<p class="urgent">При непосредственной опасности обратитесь за срочной помощью. Запись в приложении не вызывает экстренную службу.</p><button class="button primary" type="submit">${doctor ? "Сохранить оценку" : "Отправить ответы специалисту"}</button><button class="button quiet" type="button" data-ext="assessment-cancel">Отмена</button></form></section>`;
  }
  const past = ws().assessments;
  return `<section class="card"><h2>${doctor ? "Шкала специалиста" : "Шкалы самочувствия"}</h2>${assessmentAssignmentPanel(doctor)}${(doctor ? available : []).map((k) => `<button class="button full" data-ext="assessment" data-key="${k}">${{ gad7: "GAD-7 · 7 вопросов", phq9: "PHQ-9 · 9 вопросов", hama: "HAM-A · 14 пунктов" }[k]} ${icon("arrow")}</button>`).join("")}</section><section class="card"><h2>Сохранённые результаты</h2>${past.length ? past.map((s) => `<div class="report-item"><strong>${e(extraAssessments[s.kind]?.title || { schulte: "Таблицы Шульте", serial7: "Вычитание по 7 из 100" }[s.kind] || s.kind.toUpperCase())}</strong><p class="caption">${e(clinicDate(s.created_at))}</p>${doctor ? `${extraAssessments[s.kind] ? "<p>Учебные ответы без диагностического балла</p>" : `<p>${s.kind === "schulte" ? "Время, сек." : s.kind === "serial7" ? "Верных ответов" : "Сумма"}: <strong>${s.score}</strong></p>`}<details><summary>Ответы по пунктам</summary><p>${s.answers.map((v, i) => `${i + 1}: ${v}`).join(" · ")}</p></details>` : `<p>${e(s.interpretation)}</p>`}</div>`).join("") : '<p class="muted">Шкалы пока не заполнены.</p>'}</section>`;
}

function thoughtJournal() {
  return `<section class="card"><h2>Дневник мыслей</h2><p class="caption">Ситуация → мысль → эмоция → другой взгляд. Запись можно оставить личной.</p>${entryForm(
    "thought",
    [
      ["situation", "Что произошло"],
      ["thought", "Автоматическая мысль"],
      ["emotion", "Эмоция и её сила"],
      ["alternative", "Другой взгляд на ситуацию", "textarea"],
      ["after", "Эмоция после"],
    ],
  )}${entriesList("thought")}</section>`;
}
function literature(who) {
  return `<section class="card"><h2>Литература</h2>${prototypeContent.literature[
    who
  ]
    .filter(([t]) => !t.includes("Инструкция ДЕМО"))
    .map(
      ([t, d, link]) =>
        `<article class="report-item"><h3>${e(t)}</h3><p class="caption">${e(d)}</p>${typeof link === "string" && /^https:\/\//.test(link) ? `<a class="text-button" target="_blank" rel="noopener noreferrer" href="${e(link)}">Открыть источник ↗</a>` : ""}</article>`,
    )
    .join("")}</section>`;
}
function coursePage(items, prefix) {
  if (
    (state.user.role === "patient" && prefix === "course") ||
    (state.user.role === "relative" && prefix === "relative")
  )
    return schoolVideos(items);
  const progress =
    state.user.role === "relative"
      ? state.relative?.progress || []
      : ws().progress;
  const read = new Set(progress.map((p) => p.resource));
  return `<section class="card"><h2>${prefix === "relative" ? "Как поддержать близкого" : "Школа пациента"}</h2><p class="caption">${items.filter((l) => read.has(prefix + "-" + l.id)).length} из ${items.length} занятий пройдено</p>${items.map((l) => `<details class="course-item"><summary>${read.has(prefix + "-" + l.id) ? "✓ " : ""}${e(l.t)} · ${l.min} мин</summary>${l.pts.map((p) => `<p>${e(p)}</p>`).join("")}<button class="button" data-ext="resource-read" data-key="${prefix + "-" + l.id}" ${read.has(prefix + "-" + l.id) ? "disabled" : ""}>Отметить прочитанным</button></details>`).join("")}</section>`;
}
function extendedLearningPage() {
  return stripHeading(learningContent());
}
function extendedHelpPage() {
  return stripHeading(helpContent());
}
function extendedMessagesPage() {
  return isDoctor() ? messagesContent() : stripHeading(messagesContent());
}
function learningContent() {
  const active = sub("learn", "course");
  const tabs = sectionTabs(
    "learn",
    [
      ["course", "Школа"],
      ["articles", "Статьи"],
      ["thought", "Дневник мыслей"],
      ["books", "Книги"],
    ],
    "course",
  );
  if (active === "books")
    return (
      heading("ЗНАНИЯ", "Книги и материалы", "") + tabs + literature("patient")
    );
  if (active === "thought")
    return (
      heading(
        "ЗНАНИЯ",
        "Разобрать ситуацию",
        "Запись доступна только вам, пока вы не разрешите доступ.",
      ) +
      tabs +
      thoughtJournal()
    );
  if (active === "articles")
    return (
      heading("ЗНАНИЯ", "Понять себя", "") +
      tabs +
      `<section class="card">${[
        [
          "Что со мной происходит",
          "Тревога может сопровождаться напряжением, усталостью и изменениями сна. По одной записи нельзя установить причину; обсудите свои ощущения со специалистом.",
        ],
        [
          "Как работает сопровождение",
          "Врач и пациент согласовывают план. В приложении можно отмечать состояние, задавать вопросы и возвращаться к результатам встреч.",
        ],
        [
          "Круг тревоги",
          "Ситуация → мысль → чувство → действие. Попробуйте заметить эти звенья в дневнике мыслей.",
        ],
        [
          "Ловушки мышления",
          "Можно спросить себя: какие у меня есть факты? Есть ли другой взгляд? Что я сказал(а) бы другу?",
        ],
        [
          "Время для беспокойства",
          "Если вам подходит такой подход, можно записать волнующий вопрос и обсудить его в удобное время. Подберите технику со специалистом.",
        ],
        [
          "Сон при тревоге",
          "Отмечайте качество сна и условия, которые могли на него повлиять. Если трудности повторяются, расскажите специалисту.",
        ],
      ]
        .map(
          ([t, p]) =>
            `<details class="course-item"><summary>${t}</summary><p>${p}</p></details>`,
        )
        .join("")}</section>`
    );
  return (
    heading(
      "ЗНАНИЯ",
      "Школа пациента",
      "Пять занятий из макета и короткие практические материалы.",
    ) +
    tabs +
    coursePage(prototypeContent.course, "course")
  );
}

let breathingTicker = null;
let breathingStarted = 0,
  breathingVoice = false,
  lastBreathPhase = -1;
function extendedMovementPage() {
  return movementExperience();
}
function wearableCard() {
  return `<section class="card"><h2>Часы и фитнес-браслеты</h2><span class="chip neutral">${pref().wear ? "Синтетический пример включён" : "Устройство не подключено"}</span>${pref().wear ? `<div class="demo-measures">${pref().wear_steps ? "<span>Шаги<strong>6 420</strong>Активность: 24 мин</span>" : ""}${pref().wear_sleep ? "<span>Сон<strong>7,2 ч</strong>Синтетический пример</span>" : ""}${pref().wear_hr ? "<span>Пульс<strong>72</strong>Синтетический пример</span>" : ""}</div>` : ""}<p class="caption">Экран Health / Health Connect из макета сохранён как демонстрация. PWA не читает Apple Health или Health Connect напрямую.</p><button class="button" data-action="nav" data-page="consents">Управлять примером и согласиями</button></section>`;
}

function safetyPlanPage(doctor = false) {
  const plan = ws().plan,
    agreement = ws().agreement;
  let html = `<section class="card"><h2>План безопасности</h2><p class="caption">Ваш план поддержки в сложной ситуации.</p>${plan ? `<p class="caption">Сохранён специалистом ${e(clinicDate(plan.updated_at))}</p>` : '<p class="muted">План ещё не составлен. Обсудите его на встрече.</p>'}</section>`;
  if (doctor)
    html += `<section class="card"><form id="safety-plan-form">${planLabels.map(([k, t]) => `<label>${t}<textarea name="${k}" rows="3" required maxlength="1500">${e(plan?.body[k] || "")}</textarea></label>`).join("")}<button class="button primary" type="submit">Сохранить план безопасности</button></form></section>`;
  else if (plan)
    html += `<section class="card"><ol class="safety-plan-steps">${planLabels.map(([k, t]) => `<li><h3>${t}</h3><p class="report-text">${e(plan.body[k])}</p></li>`).join("")}</ol></section>`;
  html += `<section class="card"><h2>Соглашение о сопровождении</h2>${agreement ? `<p class="report-text">${e(agreement.body)}</p><p class="caption">До ${e(clinicDate(agreement.ends_on))} · специалист ознакомил ${e(clinicDate(agreement.created_at))}</p><span class="chip ${agreement.patient_signed_at ? "green" : "amber"}">${agreement.patient_signed_at ? "Пациент ознакомился " + e(clinicDate(agreement.patient_signed_at)) : "Ожидает ознакомления пациента"}</span>${!doctor && !agreement.patient_signed_at && new Date(agreement.ends_on) > new Date() ? '<button class="button primary full" data-ext="agreement-accept">Ознакомился(ась) с условиями</button>' : ""}` : '<p class="muted">Договорённостей пока нет.</p>'}${doctor ? `<details><summary>Предложить новое соглашение</summary><form id="agreement-form"><label>Что согласовано<textarea name="body" required maxlength="3000" rows="6">Врач и пациент обсуждают записи на встречах. Ответы в чате — в согласованное рабочее время. При непосредственной опасности пациент обращается за экстренной помощью.</textarea></label><label>Срок, дней<input name="days" type="number" min="1" max="365" value="28" required></label><button class="button primary" type="submit">Сохранить соглашение</button></form></details>` : ""}</section>`;
  return html;
}
const emotionSteps = {
  panic: [
    "Накатывает паника",
    "Почувствуйте опору под ногами. Можно сесть в удобном месте.",
    "Назовите про себя, что чувствуете, без необходимости это менять.",
    "Дышите в комфортном ритме, посмотрите на знакомые предметы.",
    "Если становится хуже или непонятна причина физических симптомов, обратитесь за медицинской помощью.",
  ],
  anger: [
    "Злюсь",
    "Остановитесь на короткую паузу, если это безопасно.",
    "Отойдите от ситуации, не принимая резких решений.",
    "Заметьте ощущения и выберите одно посильное действие.",
  ],
  numb: [
    "Ничего не чувствую",
    "Оглядитесь и назовите пять предметов вокруг.",
    "Почувствуйте поверхность, на которой сидите, или опору под ногами.",
    "Можно написать человеку, которому доверяете.",
  ],
  harm: [
    "Хочу навредить себе",
    "Если есть непосредственная опасность, звоните 112 или в местную экстренную службу сейчас.",
    "По возможности перейдите в более безопасное место и свяжитесь с человеком, которому доверяете.",
    "Откройте согласованный план безопасности. Не оставайтесь с этим в одиночку.",
  ],
};
function helpContent() {
  const active = sub("help", "now");
  const tabs = sectionTabs(
    "help",
    [
      ["now", "Сейчас"],
      ["calm", "Дыхание"],
      ["games", "Игры"],
      ["plan", "План"],
      ["sos", "SOS"],
      ["streak", "Счётчик"],
    ],
    "now",
  );
  if (active === "plan") return tabs + safetyPlanPage();
  if (active === "calm")
    return (
      heading(
        "САМОПОМОЩЬ",
        "Дыхание и заземление",
        "Остановитесь, если некомфортно.",
      ) +
      tabs +
      calmPractices()
    );
  if (active === "games")
    return (
      heading(
        "САМОПОМОЩЬ",
        "Немного переключиться",
        "Без оценок и соревнования.",
      ) +
      tabs +
      gamesPage()
    );
  if (active === "streak")
    return (
      heading(
        "ЛИЧНОЕ",
        "Счётчик дней",
        "Виден только вам; использование добровольное.",
      ) +
      tabs +
      streakPage()
    );
  if (active === "sos")
    return tabs + sosPage() + trustedForm() + contactsPage();
  return (
    heading("САМОПОМОЩЬ", "Как вы сейчас?", "") +
    tabs +
    `<div class="emotion-list">${Object.entries(emotionSteps)
      .map(([key, steps]) => crisisSteps(key, steps))
      .join("")}</div>`
  );
}
function sosPage() {
  return `<section class="card sos-focus"><h2>Тревожная кнопка</h2><button class="button danger hold-sos sos-large" data-ext="sos" aria-label="Отправить SOS: удерживайте полторы секунды">Удерживайте 1,5 секунды</button><p class="caption">Сообщение врачу и разрешённому близкому внутри приложения. При непосредственной опасности звоните 112.</p>${(
    ws().events || []
  )
    .filter((v) => v.kind === "sos")
    .slice(0, 3)
    .map(
      (v) =>
        `<p class="caption">Запрос сохранён ${e(clinicDate(v.created_at))} · ${v.doctor_read_at ? "специалист отметил просмотр" : "просмотр специалистом пока не подтверждён"}</p>`,
    )
    .join("")}</section>`;
}
function trustedForm() {
  return `<section class="card"><h2>Доверенный человек</h2><form id="trusted-form">${[
    ["relative_name", "Имя"],
    ["relative_relation", "Кто это"],
    ["relative_phone", "Телефон"],
  ]
    .map(
      ([k, l]) =>
        `<label>${l}<input name="${k}" maxlength="150" value="${e(pref()[k] || "")}"></label>`,
    )
    .join(
      "",
    )}<button class="button primary" type="submit">Сохранить контакт</button></form><button class="button quiet full" data-action="nav" data-page="consents">Что разрешено близкому</button></section>`;
}
function streakPage(compact = false) {
  const p = pref();
  return `<section class="card stopwatch-card${compact ? " home-counter" : ""}">${compact ? `<h2>${e(p.streak_label || "Мой отсчёт")}</h2>` : "<p>Личный отсчёт времени с выбранного вами момента — например, начала периода без самоповреждения. Пользуйтесь им, если это помогает; он не оценивает успешность лечения.</p>"}<form class="counter-label-form"><label>Что отсчитываем?<input name="label" maxlength="80" required value="${e(p.streak_label || "Мой отсчёт")}" placeholder="Например, дни заботы о себе"></label><button type="submit" class="button">Сохранить название</button></form>${p.streak_on && p.streak_start ? `<output id="streak-display" class="stopwatch" aria-label="Прошло времени">${stopwatchValue()}</output><div class="proposal-actions"><button class="button" data-ext="streak-restart">Начать заново</button><button class="button quiet" data-ext="streak-off">Остановить отсчёт</button></div>` : '<button class="button primary" data-experience="streak-start">Начать отсчёт</button>'}</section>`;
}
function gamesPage() {
  return compassGames.page();
}
function consentsPage() {
  const p = pref();
  const toggle = (key, title, description) =>
    `<label class="consent-switch"><input type="checkbox" data-pref="${key}" ${p[key] ? "checked" : ""}><span><strong>${title}</strong><small>${description}</small></span></label>`;
  return (
    heading(
      "ПРОФИЛЬ",
      "Мои согласия",
      "Изменения сохраняются на сервере. Их можно отозвать.",
    ) +
    `<section class="card"><h2>Дневник и исследования</h2>${toggle("share_mood", "Показывать специалисту дневник и графики", "После отзыва новые запросы специалиста не возвращают записи дневника. Уже просмотренное невозможно удалить из памяти получателя.")}${toggle("research", "Разрешить демонстрационную выгрузку для исследований", "Только агрегаты под случайным кодом, без имени, телефона, текстов заметок и чата. Это псевдонимизация, не юридическое согласие на реальные исследования.")}${toggle("trials", "Можно предлагать участие в исследованиях", "Сохраняется предпочтение. Приглашения и отдельные юридические согласия пока не оформляются.")}</section><section class="card"><h2>Доверенный человек</h2>${toggle("relative_sos", "Разрешить близкому получать SOS", "Для близких, зарегистрированных по вашему приглашению. Эти разрешения действуют для всех связанных близких; шкалы, дневник и переписка им недоступны.")}${toggle("relative_adherence", "Показывать отметки приёма", "Только время и статус, без названий препаратов.")}${toggle("relative_wellbeing", "Общая сводка самочувствия", "Только нейтральное сообщение о наличии записей, без баллов.")}${toggle("relative_away", "Показывать дату последней записи", "Близкий может заметить длительное отсутствие записей. Это не гарантия доставки фонового уведомления.")}</section>${trustedForm()}<section class="card"><h2>Часы и «Здоровье»</h2>${toggle("wear", "Показать синтетический пример импорта", "Устройство не подключается. Нативные Health / Health Connect не доступны напрямую через обычную PWA.")}${toggle("wear_steps", "Шаги и активные минуты", "Поля в демонстрационном наборе.")}${toggle("wear_sleep", "Сон", "Поле в демонстрационном наборе.")}${toggle("wear_hr", "Пульс в покое", "Поле в демонстрационном наборе.")}</section><section class="card"><h2>ЕМИАС</h2>${toggle("emias", "Предпочтение синхронизации", "Интеграция с медицинской организацией не подключена. Согласие сохраняется, данные в ЕМИАС не передаются.")}${toggle("emias_from", "Получать документы", "Предпочтение для будущего подключения.")}${toggle("emias_to", "Передавать результаты", "Предпочтение для будущего подключения.")}</section><section class="card"><h2>История согласий</h2><p class="caption">Изменения разрешений фиксируются в журнале приложения. Личные заметки в журнал не копируются.</p>${(ws().consent_history || []).map((r) => `<p class="caption">${e(clinicDate(r.created_at))} · ${e(r.detail)}</p>`).join("") || '<p class="muted">Изменений пока нет.</p>'}</section>`
  );
}

function messagesContent() {
  if (isDoctor()) return messagesPage();
  const active = sub("doctor", "chat");
  const tabs = sectionTabs(
    "doctor",
    [
      ["chat", "Чат"],
      ["mail", "Письма"],
      ["ai", "Помощник"],
    ],
    "chat",
  );
  if (active === "chat") return tabs + messagesPage();

  if (active === "mail")
    return (
      heading(
        "ЛЕЧАЩИЙ СПЕЦИАЛИСТ",
        "Письма врачу",
        "Для развёрнутого обращения; срок ответа согласуйте лично.",
      ) +
      tabs +
      lettersPage()
    );
  return (
    heading(
      "ЛЕЧАЩИЙ СПЕЦИАЛИСТ",
      "ИИ-помощник",
      "Настоящий запрос к настроенной внешней модели.",
    ) +
    tabs +
    `<section class="card"><p class="caption">${state.integrations?.ai?.configured ? "Внешний API настроен" : "ИИ ещё не подключён"}. Помощник не ставит диагноз и не меняет назначения.</p>${(state.patientAi || []).map((m) => `<article class="report-item"><strong>${e(m.question)}</strong><p class="assistant-answer">${e(m.answer)}</p></article>`).join("")}<form id="patient-ai-form"><label>Ваш вопрос<textarea name="question" required maxlength="1000" rows="3"></textarea></label><button class="button primary" type="submit">Спросить помощника</button></form><p class="caption">Ответы этой беседы не сохраняются после выхода. Вопрос отправляется внешнему API, если он подключён.</p></section>`
  );
}
function lettersPage() {
  const doctor = isDoctor(),
    items = doctor ? state.letters || [] : ws().letters;
  return `${doctor ? heading("ОБРАЩЕНИЯ", "Письма пациентов", "Развёрнутые вопросы и ответы.") + `<button class="button full" data-action="nav" data-page="messages">Чаты с пациентами ${icon("chat")}</button>` : `<section class="card"><h2>Новое письмо</h2><form id="letter-form"><label>Тема обращения<select name="category">${["Вопрос о лечении", "Побочный эффект", "Запись на приём", "Документы", "Другое"].map((v) => `<option>${v}</option>`).join("")}</select></label><label>Заголовок<input name="subject" required maxlength="160"></label><label>Текст<textarea name="body" required maxlength="3000" rows="5"></textarea></label><button class="button primary" type="submit">Отправить письмо</button></form></section>`}${items.length ? items.map((l) => `<section class="card"><div class="card-heading"><h2>${e(l.subject)}</h2><span class="chip ${l.reply ? "green" : l.read_at ? "neutral" : "amber"}">${l.reply ? "Есть ответ" : l.read_at ? "Прочитано" : "Новое"}</span></div><p class="caption">${e(l.patient_name || l.category)} · ${e(clinicDate(l.created_at))}</p><p class="report-text">${e(l.body)}</p>${l.reply ? `<div class="source-note"><strong>Ответ специалиста</strong><p class="report-text">${e(l.reply)}</p></div>` : ""}${doctor ? `<form class="letter-reply-form" data-id="${l.id}"><label>Ответ<textarea name="body" required maxlength="3000" rows="3">${e(l.reply)}</textarea></label><button class="button primary" type="submit">Отправить ответ</button></form>` : ""}</section>`).join("") : '<section class="card"><p class="muted">Писем пока нет.</p></section>'}`;
}

const scaleGuideDefinitions = {
  gad7: {
    title: "GAD-7",
    max: 21,
    starts: [0, 5, 10, 15],
    tones: ["mint", "green", "yellow", "red"],
  },
  phq9: {
    title: "PHQ-9",
    max: 27,
    starts: [0, 5, 10, 15, 20],
    tones: ["mint", "green", "yellow", "orange", "red"],
  },
  hama: {
    title: "HAM-A",
    max: 56,
    starts: [0, 18, 25, 31],
    tones: ["green", "yellow", "orange", "red"],
  },
};
function scaleGuideRange(definition, index) {
  return `${definition.starts[index]}–${index + 1 < definition.starts.length ? definition.starts[index + 1] - 1 : definition.max}`;
}
function scaleGuideResult(key, value) {
  const definition = scaleGuideDefinitions[key],
    score = Number(value);
  if (
    String(value).trim() === "" ||
    !Number.isInteger(score) ||
    score < 0 ||
    score > definition.max
  )
    return `<p class="caption scale-zone-empty" role="status">Введите целое число от 0 до ${definition.max}.</p>`;
  const index = definition.starts.reduce(
      (current, start, i) => (score >= start ? i : current),
      0,
    ),
    range = scaleGuideRange(definition, index);
  return `<div class="scale-zone-meter" role="meter" aria-label="${definition.title}: положение балла" aria-valuemin="0" aria-valuemax="${definition.max}" aria-valuenow="${score}" aria-valuetext="${score} из ${definition.max}; диапазон ${range}"><svg class="scale-zone-track" viewBox="0 0 560 36" preserveAspectRatio="none" aria-hidden="true"><defs><clipPath id="${key}-zone-clip"><rect x="0" y="9" width="560" height="18" rx="9"/></clipPath></defs><g clip-path="url(#${key}-zone-clip)">${definition.starts.map((start, i) => `<rect data-tone="${definition.tones[i]}" x="${(start / definition.max) * 560}" y="9" width="${(((definition.starts[i + 1] ?? definition.max) - start) / definition.max) * 560}" height="18" stroke="var(--surface)" stroke-width="2" vector-effect="non-scaling-stroke"/>`).join("")}</g><rect class="scale-zone-marker" x="${(score / definition.max) * 560 - 2}" y="3" width="4" height="30" rx="2"/></svg></div><div class="scale-zone-axis" aria-hidden="true"><span>0</span><span>${definition.max}</span></div><div class="scale-zone-current" data-tone="${definition.tones[index]}" role="status"><span>Текущая зона</span><strong>${range} баллов</strong></div>`;
}
function scaleGuide() {
  return `<form id="scale-guide-form" class="scale-guide-grid">${Object.entries(
    scaleGuideDefinitions,
  )
    .map(([key, definition]) => {
      const value = state.scaleGuideScores?.[key] ?? "0";
      return `<section class="card scale-guide-card" data-scale="${key}"><div class="scale-zone-heading"><h2>${definition.title}</h2><label>Баллы<input name="${key}" type="number" min="0" max="${definition.max}" step="1" value="${e(value)}" required inputmode="numeric" aria-label="${definition.title}: баллы" ></label></div><div class="scale-guide-result">${scaleGuideResult(key, value)}</div><details class="scale-zone-ranges"><summary>Все диапазоны</summary><ul>${definition.starts.map((start, i) => `<li><span class="scale-zone-swatch" data-tone="${definition.tones[i]}" aria-hidden="true"></span><span>${scaleGuideRange(definition, i)} баллов</span></li>`).join("")}</ul></details></section>`;
    })
    .join("")}</form>`;
}
function updateScaleGuide(input) {
  const key = input.name;
  if (!Object.hasOwn(scaleGuideDefinitions, key)) return;
  (state.scaleGuideScores ||= {})[key] = input.value;
  input
    .closest(".scale-guide-card")
    .querySelector(".scale-guide-result").innerHTML = scaleGuideResult(
    key,
    input.value,
  );
}
function referencePage() {
  const active = sub("reference", "calc");
  const tabs = sectionTabs(
    "reference",
    [
      ["calc", "Калькулятор"],
      ["scales", "Шкалы"],
      ["rules", "Правила"],
      ["literature", "Литература"],
    ],
    "calc",
  );
  if (active === "literature")
    return (
      heading("ИНСТРУМЕНТЫ ВРАЧА", "Справочник", "") +
      tabs +
      literature("doctor")
    );
  if (active === "rules")
    return (
      heading("ИНСТРУМЕНТЫ ВРАЧА", "Правила и источники", "") +
      tabs +
      aboutPage()
    );
  if (active === "scales")
    return (
      heading("ИНСТРУМЕНТЫ ВРАЧА", "Шкалы и маршрутизация", "") +
      tabs +
      scaleGuide() +
      `<section class="card"><h2>Маршрутизация</h2><p>Сигнал безопасности → просмотр специалистом → согласованный следующий шаг. Приложение не оформляет реальное направление автоматически.</p><p class="caption">При непосредственной угрозе жизни нужна срочная помощь независимо от суммы шкалы.</p></section>`
    );
  return (
    heading("ИНСТРУМЕНТЫ ВРАЧА", "Калькулятор совместимости", "") +
    tabs +
    compatibilityCalculator()
  );
}
function newsPage() {
  const category = state.newsCategory || "Все";
  const cats = ["Все", "Препараты", "Мероприятия", "Статьи", "Разработки"];
  return (
    heading("ДЛЯ СПЕЦИАЛИСТОВ", "Новости", "") +
    `<div class="filter-group">${cats.map((c) => `<button data-ext="news-category" data-key="${c}" class="${category === c ? "active" : ""}">${c}</button>`).join("")}</div>${prototypeContent.news
      .filter((n) => category === "Все" || n.cat === category)
      .map(
        (n, i) =>
          `<article class="card"><div class="card-heading"><span class="chip neutral">${e(n.cat)}</span><span class="caption">${e(n.date)}</span></div><h2>${e(n.title)}</h2><p>${e(n.text)}</p><button class="button quiet" data-ext="resource-read" data-key="news-${prototypeContent.news.indexOf(n)}">Отметить прочитанным</button></article>`,
      )
      .join("")}`
  );
}
function forumPage() {
  const item = state.forumThread;
  if (item)
    return (
      heading("ОБРАТНАЯ СВЯЗЬ", "Форум врачей", item.thread.title) +
      `<div class="proposal-actions"><button class="button" data-ext="forum-back">Все темы</button><button class="button" data-ext="forum-refresh" data-id="${item.thread.id}">Обновить тему</button></div><section class="card">${item.posts.map((p) => `<article class="report-item"><h3>${e(p.author)}</h3><time class="caption">${e(clinicDate(p.created_at))}</time><p class="report-text">${e(p.body)}</p></article>`).join("")}<form id="forum-reply-form" data-id="${item.thread.id}"><label>Ответ<textarea name="body" required maxlength="3000" rows="4"></textarea></label><button class="button primary" type="submit">Опубликовать ответ</button></form></section>`
    );
  return (
    heading("ОБРАТНАЯ СВЯЗЬ", "Форум врачей", "") +
    `<section class="card"><details><summary>Новая тема</summary><form id="forum-form"><label>Раздел<select name="category">${["Опыт применения", "Безопасность", "Взаимодействия", "Вопрос коллегам"].map((v) => `<option>${v}</option>`).join("")}</select></label><label>Заголовок<input name="title" maxlength="160" required></label><label>Сообщение<textarea name="body" rows="5" maxlength="3000" required></textarea></label><button class="button primary" type="submit">Опубликовать тему</button></form></details></section>${(state.forum || []).map((t) => `<button class="card lesson-option" data-ext="forum-open" data-id="${t.id}"><span><small>${e(t.category)} · ${t.replies} сообщений</small><strong>${e(t.title)}</strong><small>${e(t.author)} · ${e(clinicDate(t.created_at))}</small></span>${icon("arrow")}</button>`).join("")}`
  );
}
function researchPage() {
  const data = state.research || [];
  return (
    heading(
      "ДАННЫЕ",
      "Исследовательская выгрузка",
      "Только ваши пациенты с включённым разрешением.",
    ) +
    demoNote("Пациенты обозначены кодами; имена и контакты не выгружаются.") +
    `<section class="card"><h2>${data.length} записей с разрешением</h2><a class="button" href="/api/research.csv" download>Скачать CSV</a><div class="table-scroll"><table class="rule-table"><thead><tr><th>Код</th><th>Возрастная группа</th><th>Записей</th><th>Настроение / тревога</th></tr></thead><tbody>${data.map((r) => `<tr><td>${e(r.code)}</td><td>${e(r.age_band)}</td><td>${r.reports}</td><td>${r.mood_mean ?? "—"} / ${r.anxiety_mean ?? "—"}</td></tr>`).join("")}</tbody></table></div><p class="caption">Без имён, телефонов, чата и свободных текстов. Отзыв разрешения исключает пациента из следующих выгрузок.</p></section>`
  );
}
function contactsPage() {
  const category = state.contactCategory || "urgent";
  const q = (state.contactSearch || "").toLocaleLowerCase("ru");
  const list = prototypeContent.helplines.filter((h) =>
    q
      ? (h.n + " " + h.d).toLocaleLowerCase("ru").includes(q)
      : h.c === category,
  );
  return `<section class="card"><h2>Телефоны доверия и помощь</h2><label>Поиск<input id="contacts-search" value="${e(state.contactSearch || "")}" placeholder="Название или аудитория"></label><div class="filter-group">${prototypeContent.categories.map(([k, t]) => `<button data-ext="contact-category" data-key="${k}" class="${category === k ? "active" : ""}">${e(t)}</button>`).join("")}</div><div id="contact-results">${list.map(contactRow).join("") || '<p class="muted">Ничего не найдено.</p>'}</div></section>`;
}
function contactRow(h) {
  return `<article class="report-item"><h3>${e(h.n)}</h3><p class="caption">${e(h.d)}</p><div class="proposal-actions">${h.ph.map((phone) => `<a class="button" href="tel:${e(phone.replace(/[^+0-9]/g, ""))}">${e(phone)}</a>`).join("")}</div>${h.url ? `<a class="text-button" href="${e(h.url)}" target="_blank" rel="noopener noreferrer">Открыть сайт ↗</a>` : ""}</article>`;
}
function relativePage() {
  const people = state.relative?.patients || [];
  return (
    heading(
      "КАБИНЕТ БЛИЗКОГО",
      `Здравствуйте, ${e(state.user.name.split(" ")[0])}`,
      "Только сведения, разрешённые пациентом.",
    ) +
    (people.length
      ? people
          .map(
            (p) =>
              `<section class="card"><h2>${e(p.name)}</h2>${p.phone ? `<a class="button" href="tel:${e(p.phone.replace(/[^+0-9]/g, ""))}">Позвонить</a>` : ""}${p.last_active ? `<p class="caption">Последняя запись: ${e(clinicDate(p.last_active))}</p>` : ""}${p.wellbeing ? `<p>${e(p.wellbeing)}</p>` : ""}${p.adherence ? `<details><summary>Разрешённые отметки приёма</summary>${p.adherence.map((a) => `<p class="caption">${e(a.day)} ${e(a.scheduled_time)} · ${a.status === "taken" ? "принято" : "пропущено"}</p>`).join("")}</details>` : ""}</section>${p.events.length ? p.events.map((v) => `<section class="notice urgent-help"><h2>Запрос поддержки</h2><p>${e(p.name)} попросил(а) связаться через SOS.</p><p class="caption">${e(clinicDate(v.created_at))} · ${v.relative_read_at ? "вы отметили просмотр" : "новый запрос"}</p>${!v.relative_read_at ? `<button class="button" data-ext="support-read" data-id="${v.id}">Отметить просмотренным</button>` : ""}<a class="button danger" href="tel:112">Экстренная помощь · 112</a></section>`).join("") : '<section class="card"><p>Сохранённых запросов SOS нет.</p></section>'}`,
          )
          .join("")
      : '<section class="card"><p>Пациент пока не разрешил доступ или отозвал его. Сведения не отображаются.</p></section>')
  );
}
function relativeLearningPage() {
  return (
    heading("ДЛЯ БЛИЗКИХ", "Как помочь", "") +
    coursePage(prototypeContent.relativeCourse, "relative")
  );
}

const sectionSettings = settingsPage;
settingsPage = function () {
  if (state.user.role === "patient") {
    const tabs = sectionTabs(
      "settings",
      [
        ["general", "Настройки"],
        ["consents", "Мои согласия"],
        ["about", "О проекте"],
      ],
      "general",
    );
    return (
      tabs +
      (
        { consents: patientConsentScreen, about: aboutPage }[
          sub("settings", "general")
        ] || patientSettingsGeneral
      )()
    );
  }
  if (state.user.role === "relative")
    return (
      heading("ПСИКОМПАС", "Ваше пространство", "") +
      demoNote(
        "Доступ к данным определяет ваш близкий в разделе «Мои согласия».",
      )
    );
  const links = isDoctor()
    ? [
        ["overview", "Обзор"],
        ["messages", "Чаты"],
        ["schedule", "Расписание"],
        ["research", "Данные для исследований"],
        ["tour", "Сценарий для защиты"],
      ]
    : [
        ["consents", "Мои согласия"],
        ["tour", "Сценарий для защиты"],
      ];
  return (
    `<div class="quick-grid">${links.map(([page, title]) => `<button class="quick-card" data-action="nav" data-page="${page}">${icon("arrow")}<strong>${title}</strong></button>`).join("")}</div>` +
    sectionSettings()
  );
};
const sectionDoctorCard = doctorCard;
doctorCard = function () {
  let html = sectionDoctorCard();
  const additions = `<button data-action="tab" data-tab="therapy" class="${state.tab === "therapy" ? "active" : ""}">Терапия</button><button data-action="tab" data-tab="scales" class="${state.tab === "scales" ? "active" : ""}">Шкалы</button><button data-action="tab" data-tab="safetyplan" class="${state.tab === "safetyplan" ? "active" : ""}">План безопасности</button>`;
  const marker = '<div class="tabs" aria-label="Разделы карточки">';
  html = html.replace(marker, marker + additions);
  if (state.tab === "scales") html += assessmentPage(true);
  if (state.tab === "safetyplan") html += safetyPlanPage(true);
  if (state.tab === "therapy")
    html +=
      planPage(true) +
      `<section class="card"><h2>Проверка ограничений</h2><p>Контекст: ${e(state.detail.profile.context)}</p><button class="button" data-action="nav" data-page="reference">Калькулятор совместимости</button></section>`;
  if (state.tab === "overview")
    html +=
      supportSummary() +
      `<section class="card"><h2>Общие записи пациента</h2>${entriesList("food")}${entriesList("thought")}${entriesList("note")}</section>`;
  return html;
};
function supportSummary() {
  return `<section class="card"><h2>Запросы поддержки</h2>${
    ws().events.length
      ? ws()
          .events.map(
            (v) =>
              `<article class="report-item"><span class="chip ${v.doctor_read_at ? "neutral" : "red"}">${v.doctor_read_at ? "Просмотрено" : "Требует внимания"}</span><p>${e(v.body)}</p><p class="caption">${e(clinicDate(v.created_at))}</p>${!v.doctor_read_at ? `<button class="button" data-ext="support-read" data-id="${v.id}">Отметить просмотренным</button>` : ""}</article>`,
          )
          .join("")
      : '<p class="muted">Запросов пока нет.</p>'
  }</section>`;
}
const sectionLogin = renderLogin;
renderLogin = function (error = "") {
  sectionLogin(error);
  const first = $(".demo-login");
  if (first) {
    const b = document.createElement("button");
    b.className = "demo-login";
    b.dataset.action = "login";
    b.dataset.account = "relative";
    b.innerHTML = `${avatar("Екатерина Морозова", "blue")}<span><strong>Войти как близкий</strong><small>Екатерина · разрешённые сигналы и поддержка</small></span>${icon("arrow")}`;
    first.parentNode.insertBefore(b, $(".login-note"));
  }
};

function tourPage() {
  const steps = [
    [
      "Первый приём",
      "Врач знакомится с карточкой и первичными сведениями.",
      "patients",
    ],
    [
      "План и соглашение",
      "Специалист сохраняет договорённости и план безопасности.",
      "patients",
    ],
    ["Первый день", "Пациент отмечает приём и самочувствие.", "overview"],
    [
      "Школа и помощник",
      "Материалы и внешний ИИ отвечают за разные задачи.",
      "learn",
    ],
    ["Перед экзаменом", "Техники переключения внимания и дыхание.", "help"],
    [
      "Трудный вечер",
      "План безопасности, экстренные контакты и запрос SOS.",
      "help",
    ],
    [
      "Поддержка близкого",
      "Отдельный аккаунт видит только разрешённые сведения.",
      "overview",
    ],
    [
      "Сигнал специалисту",
      "Просмотр запроса и согласование следующего шага.",
      "patients",
    ],
    ["Контроль динамики", "Дневник, шкалы, результаты встреч.", "patients"],
    [
      "Давно нет записей",
      "Близкий видит дату последней записи, если это разрешено.",
      "overview",
    ],
    [
      "Исследовательская таблица",
      "Выгрузка только разрешённых агрегатов.",
      "research",
    ],
  ];
  return (
    heading(
      "ДЕМОНСТРАЦИЯ",
      "Сценарий для защиты",
      "11 эпизодов макета. Данные не сбрасываются и даты не подменяются.",
    ) +
    steps
      .map(
        ([t, p, page], i) =>
          `<section class="card"><p class="eyebrow">ШАГ ${i + 1} ИЗ ${steps.length}</p><h2>${t}</h2><p>${p}</p><button class="button" data-action="nav" data-page="${state.user.role === "doctor" ? page : state.user.role === "relative" ? "overview" : ["patients", "research"].includes(page) ? "messages" : page}">Открыть экран</button></section>`,
      )
      .join("")
  );
}

for (const p of ["consents", "tour"]) pageSets.patient.add(p);
for (const p of ["letters", "reference", "news", "forum", "research", "tour"])
  pageSets.doctor.add(p);
pageSets.relative = new Set([
  "overview",
  "learn",
  "contacts",
  "settings",
  "tour",
]);
const sectionDecorate = decoratePsicompas;
decoratePsicompas = function () {
  sectionDecorate();
  if (state.user.role === "relative")
    $("#session-role").textContent = "Близкий";
  if (isDoctor() && state.page === "card") {
    const item = $('#navigation [data-page="patients"]');
    if (item) {
      item.classList.add("active");
      item.setAttribute("aria-current", "page");
    }
  }
  if (state.page !== "help" || sub("help", "now") !== "calm") stopBreathing();
  decorateExperience();
  compassGames.mount();
};
const sectionClear = clearSession;
clearSession = function () {
  compassGames.reset();
  pendingFlowers.clear();
  ++insightRequest;
  stopGuidedExercise();
  clearInterval(streakTicker);
  flowerBusy = false;
  $("#patient-safety-bar").hidden = true;
  stopBreathing();
  sectionClear();
  for (const key of [
    "workspace",
    "relative",
    "forumThread",
    "forum",
    "letters",
    "research",
    "patientAi",
    "sectionTabs",
    "assessmentKind",
    "scaleGuideScores",
    "emotion",
    "memoryCards",
    "bubbles",
    "memoryOpen",
    "memoryMatched",
    "activityDay",
    "activityMonth",
    "doctorDay",
    "doctorMonth",
    "compatibilityPatient",
    "compatibilityProfile",
    "counterClockOffset",
    "graphInsight",
  ])
    delete state[key];
};

function stopBreathing() {
  clearInterval(breathingTicker);
  breathingTicker = null;
  try {
    speechSynthesis.cancel();
  } catch {}
}
function tickBreathing() {
  const total = (Date.now() - breathingStarted) / 1000;
  if (total >= 60) {
    stopBreathing();
    const root = $('[data-practice="rhythm"]');
    if (root && !root.querySelector(".practice-workspace").hidden)
      completePractice(root, "breathing-rhythm");
    return;
  }
  const elapsed = total % 12;
  const phase = elapsed < 4 ? 0 : elapsed < 6 ? 1 : 2;
  const text = ["Вдох", "Пауза", "Выдох"][phase];
  if ($("#breath-phase")) $("#breath-phase").textContent = text;
  if (
    breathingVoice &&
    phase !== lastBreathPhase &&
    "speechSynthesis" in window
  ) {
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "ru-RU";
    speechSynthesis.speak(utterance);
  }
  lastBreathPhase = phase;
}
async function savePreference(data) {
  await write("/api/patients/" + state.selected + "/preferences", data);
  await load();
}
function formData(form) {
  return Object.fromEntries(new FormData(form));
}

let sosTimer = null,
  sosHeld = false;
document.addEventListener("pointerdown", (event) => {
  const b = event.target.closest('[data-ext="sos"]');
  if (
    !b ||
    b.disabled ||
    event.button !== 0 ||
    state.user?.role !== "patient" ||
    busy
  )
    return;
  clearTimeout(sosTimer);
  sosHeld = false;
  b.classList.add("holding");
  sosTimer = setTimeout(() => {
    if (
      !document.contains(b) ||
      document.hidden ||
      state.user?.role !== "patient"
    )
      return;
    sosHeld = true;
    b.classList.remove("holding");
    sendSos(b);
  }, 1500);
});
for (const name of ["pointerup", "pointercancel"])
  document.addEventListener(name, () => {
    clearTimeout(sosTimer);
    document
      .querySelectorAll(".hold-sos")
      .forEach((b) => b.classList.remove("holding"));
  });
document.addEventListener("pointerout", (event) => {
  if (
    event.target.closest?.('[data-ext="sos"]') &&
    !event.target.closest('[data-ext="sos"]').contains(event.relatedTarget)
  ) {
    clearTimeout(sosTimer);
    event.target.closest('[data-ext="sos"]').classList.remove("holding");
  }
});
async function sendSos(button) {
  if (busy || state.user?.role !== "patient") return;
  busy = true;
  button.disabled = true;
  try {
    await write("/api/patients/" + state.selected + "/sos", {});
    await load();
    toast(
      "Запрос сохранён. Уведомление создано; немедленный ответ не гарантируется. При опасности звоните 112.",
    );
  } catch (error) {
    toast(error.message, true);
  } finally {
    busy = false;
    button.disabled = false;
  }
}
document.addEventListener("click", async (event) => {
  const b = event.target.closest("[data-ext]");
  if (!b || b.disabled || !state.user || busy) return;
  const a = b.dataset.ext,
    k = b.dataset.key,
    id = b.dataset.id;
  try {
    if (a === "sub") {
      state.sectionTabs = { ...state.sectionTabs, [b.dataset.group]: k };
      state.assessmentKind = null;
      render();
    } else if (a === "symptom") {
      const checked = b.getAttribute("aria-pressed") === "true";
      b.setAttribute("aria-pressed", !checked);
      const values = $("#adverse")
        .value.split(", ")
        .filter(Boolean)
        .filter((v) => v !== k);
      if (!checked) values.push(k);
      $("#adverse").value = values.join(", ").slice(0, 500);
    } else if (a === "assessment") {
      state.assessmentKind = k;
      render();
    } else if (a === "assessment-cancel") {
      state.assessmentKind = null;
      render();
    } else if (a === "thought-open") {
      state.sectionTabs = { ...state.sectionTabs, learn: "thought" };
      await navigate("learn");
    } else if (a === "news-category") {
      state.newsCategory = k;
      render();
    } else if (a === "contact-category") {
      state.contactCategory = k;
      state.contactSearch = "";
      render();
    } else if (a === "forum-open" || a === "forum-refresh") {
      state.forumThread = await api("/api/forum/" + id);
      render();
    } else if (a === "forum-back") {
      state.forumThread = null;
      await load();
    } else if (a === "resource-read") {
      await api("/api/resources/read", { resource: k });
      await load();
      toast("Отметка сохранена");
    } else if (a === "support-read") {
      await api("/api/support-events/" + id + "/read", {});
      await load();
      toast("Запрос отмечен просмотренным");
    } else if (a === "agreement-accept") {
      await write("/api/patients/" + state.selected + "/agreement", {
        accepted: true,
      });
      await load();
      toast("Ознакомление сохранено");
    } else if (a === "emotion") {
      state.emotion = k;
      state.emotionStep = 0;
      render();
    } else if (a === "emotion-next") {
      state.emotionStep = Math.min(
        (state.emotionStep || 0) + 1,
        emotionSteps[state.emotion].length - 2,
      );
      render();
    } else if (a === "emotion-close") {
      state.emotion = null;
      render();
    } else if (a === "ground-next") {
      state.groundStep = ((state.groundStep || 0) + 1) % 6;
      render();
    } else if (a === "breath-toggle") {
      if (breathingTicker) stopBreathing();
      else {
        breathingStarted = Date.now();
        lastBreathPhase = -1;
        breathingTicker = setInterval(tickBreathing, 250);
      }
      render();
      tickBreathing();
    } else if (a === "bubble") {
      state.bubbles = (state.bubbles || 0) + 1;
      b.classList.toggle("popped");
      $("#bubble-count").textContent = "Касаний: " + state.bubbles;
    } else if (a === "streak-off") await savePreference({ streak_on: false });
    else if (a === "streak-restart") {
      await write(`/api/patients/${state.selected}/counter/start`, {});
      await load();
      toast("Начат новый отсчёт. Предыдущий опыт остаётся важным.");
    } else if (a === "sos" && event.detail === 0) {
      if (
        confirm(
          "Сохранить запрос SOS и уведомить специалиста и разрешённого близкого? Это не вызов экстренной службы.",
        )
      )
        await sendSos(b);
    }
  } catch (error) {
    toast(error.message, true);
  }
});
document.addEventListener("change", async (event) => {
  if (event.target.id === "breath-voice") {
    breathingVoice = event.target.checked;
    return;
  }
  const k = event.target.dataset.pref;
  if (!k || !state.user || busy) return;
  const b = event.target;
  busy = true;
  b.disabled = true;
  try {
    await savePreference({ [k]: b.checked });
    toast("Настройка сохранена");
  } catch (error) {
    b.checked = !b.checked;
    toast(error.message, true);
  } finally {
    busy = false;
    b.disabled = false;
  }
});
document.addEventListener("input", (event) => {
  if (event.target.matches("#scale-guide-form input"))
    updateScaleGuide(event.target);
  if (event.target.id === "contacts-search") {
    state.contactSearch = event.target.value;
    const q = event.target.value.toLowerCase();
    $("#contact-results").innerHTML =
      prototypeContent.helplines
        .filter((h) => (h.n + " " + h.d).toLowerCase().includes(q))
        .map(contactRow)
        .join("") || '<p class="muted">Ничего не найдено.</p>';
  }
});
document.addEventListener("submit", (event) => {
  const f = event.target;
  const data = formData(f);
  if (f.classList.contains("entry-form"))
    return run(f, async () => {
      await write("/api/patients/" + state.selected + "/entries", {
        ...data,
        kind: f.dataset.kind,
        shared: f.elements.shared.checked,
      });
      await load();
      toast("Запись сохранена");
    });
  if (f.id === "assessment-form")
    return run(f, async () => {
      const kind = f.dataset.kind;
      await write("/api/patients/" + state.selected + "/assessments", {
        kind,
        assignment_id: state.assessmentAssignment,
        answers: prototypeContent[kind].map((_, i) => Number(data["q" + i])),
      });
      state.assessmentKind = null;
      await load();
      toast("Ответы сохранены. Обсудите результат со специалистом.");
    });
  if (f.id === "safety-plan-form" || f.id === "agreement-form")
    return run(f, async () => {
      if (f.id === "agreement-form") data.days = Number(data.days);
      await write(
        "/api/patients/" +
          state.selected +
          (f.id === "agreement-form" ? "/agreement" : "/safety-plan"),
        data,
      );
      await load();
      toast("Сохранено");
    });
  if (f.id === "trusted-form")
    return run(f, async () => {
      await savePreference(data);
      toast("Контакт сохранён");
    });
  if (f.id === "streak-form")
    return run(f, async () => {
      const days = Number(data.days);
      await savePreference({
        streak_on: true,
        streak_start: new Date(Date.now() - days * 86400000).toISOString(),
        streak_best: days,
      });
      toast("Личный счётчик включён");
    });
  if (f.id === "letter-form")
    return run(f, async () => {
      await write("/api/patients/" + state.selected + "/letters", data);
      await load();
      toast("Письмо сохранено и доступно специалисту");
    });
  if (f.classList.contains("letter-reply-form"))
    return run(f, async () => {
      await write("/api/letters/" + f.dataset.id + "/reply", data);
      await load();
      toast("Ответ сохранён");
    });
  if (f.id === "patient-ai-form")
    return run(f, async () => {
      const r = await api(
        "/api/patients/" + state.selected + "/patient-assistant",
        data,
      );
      state.patientAi = [
        ...(state.patientAi || []),
        { question: data.question, answer: r.answer },
      ];
      render();
    });
  if (f.id === "forum-form")
    return run(f, async () => {
      const r = await write("/api/forum", data);
      state.forumThread = await api("/api/forum/" + r.id);
      await load();
      toast("Тема опубликована в демо-форуме");
    });
  if (f.id === "forum-reply-form")
    return run(f, async () => {
      await write("/api/forum/" + f.dataset.id + "/posts", data);
      state.forumThread = await api("/api/forum/" + f.dataset.id);
      render();
      toast("Ответ опубликован");
    });
  if (f.id === "compatibility-form") showCompatibility(f);
  if (f.id === "scale-guide-form") {
    f.querySelectorAll("input").forEach(updateScaleGuide);
  }
});

if (
  location.hash.startsWith("#join=") ||
  location.hash.startsWith("#support=") ||
  location.hash.startsWith("#activate=")
)
  showIntake();
else boot();
