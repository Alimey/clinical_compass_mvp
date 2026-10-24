"use strict";

// Small, local interactions keep sub-sections on their current page.
const groundingSteps = [
  [
    "5 вещей, которые вы видите",
    "Оглянитесь вокруг и отметьте глазами любые 5 предметов.",
  ],
  [
    "4 вещи, которые вы можете потрогать",
    "Ощутите физический контакт с четырьмя разными поверхностями или предметами.",
  ],
  ["3 звука, которые вы слышите", "Прислушайтесь к шумам вокруг вас."],
  ["2 запаха, которые вы чувствуете", "Уловите ароматы в воздухе."],
  [
    "1 вкус, который вы ощущаете",
    "Сконцентрируйтесь на вкусе во рту или сделайте глоток воды.",
  ],
];
const dayLabel = (day) =>
  new Date(day + "T12:00:00+03:00").toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "Europe/Moscow",
  });
let guidedExercise = null,
  guidedTicker = null,
  streakTicker = null,
  flowerBusy = false;

// These are explicitly invented scenario rules, not drug reference data.
const compatibilityOptions = [
  ["aviandr", "АВИАНДР · пример названия"],
  ["demo-alpha", "ДЕМО-Альфа · вымышленный"],
  ["demo-beta", "ДЕМО-Бета · вымышленный"],
];
let compatibilityRequest = 0;
function compatibilityProfileNote(profile) {
  const option = (state.detail?.catalog || []).find(
    (item) => item.id === profile?.intolerance,
  );
  return option
    ? `Учебная несовместимость: ${option.name}.`
    : "Остальные факторы укажите ниже; отсутствие отметки не означает отсутствие риска.";
}
function compatibilityCalculator() {
  const selected = state.patients.find(
    (p) => p.id === (state.compatibilityPatient || state.selected),
  );
  const profile =
    state.detail?.patient.id === selected?.id && selected
      ? state.detail.profile
      : selected && state.compatibilityProfile?.id === selected.id
        ? state.compatibilityProfile.profile
        : null;
  state.compatibilityProfile =
    selected && profile ? { id: selected.id, profile } : null;
  return `<div class="compatibility-layout"><section class="card"><form id="compatibility-form"><label>Пациент или свой сценарий<select name="patient" id="compatibility-patient"><option value="manual">Задать характеристики вручную</option>${state.patients.map((p) => `<option value="${p.id}" ${p.id === selected?.id ? "selected" : ""}>${e(p.name)}</option>`).join("")}</select></label><p id="compatibility-profile" class="caption">${selected ? `Пациент: ${e(selected.name)}. ${e(compatibilityProfileNote(profile))}` : "Укажите характеристики учебного случая."}</p><label>Основной препарат<select name="choice">${compatibilityOptions.map(([key, title]) => `<option value="${key}">${title}</option>`).join("")}</select></label><div class="form-grid"><label>Возраст<input name="age" type="number" min="0" max="120" value="${selected?.age || 40}" required></label><label>СКФ · учебное поле<input name="egfr" type="number" min="0" max="200" value="90" required></label></div><label>Печень · учебное поле<select name="liver"><option>Нет ограничений</option><option>Есть ограничение</option></select></label><fieldset class="compatibility-factors"><legend>Характеристики и противопоказания</legend>${[
    ["pregnancy", "Беременность / лактация"],
    ["epilepsy", "Эпилепсия"],
    ["cardio", "Сердечно-сосудистые заболевания"],
    ["diabetes", "Диабет"],
    ["allergy", "Аллергия на выбранный препарат · сценарий"],
  ]
    .map(
      ([key, label]) =>
        `<label class="consent-switch"><input name="${key}" type="checkbox"><span>${label}</span></label>`,
    )
    .join(
      "",
    )}</fieldset><label>Другой препарат в сценарии<select name="other"><option value="none">Не выбран</option><option value="demo-beta">ДЕМО-Бета · вымышленный</option><option value="demo-gamma">ДЕМО-Гамма · вымышленный</option></select></label><button class="button primary full" type="submit">Проверить сценарий</button></form></section><section class="card compatibility-status"><p class="eyebrow">РЕЗУЛЬТАТ ПРОВЕРКИ</p><div id="compatibility-result" role="status"><h2>Какие факторы требуют внимания?</h2><p>Выберите пациента, препарат и характеристики. Здесь появятся причины ограничений в учебном сценарии.</p></div></section></div>`;
}
function showCompatibility(form) {
  const data = Object.fromEntries(new FormData(form)),
    blocks = [],
    cautions = [];
  const primary = compatibilityOptions
    .find(([key]) => key === data.choice)?.[1]
    .split(" · ")[0];
  if (form.elements.allergy.checked)
    blocks.push("В сценарии указана аллергия на выбранный препарат.");
  const known =
    Number(data.patient) === state.compatibilityProfile?.id
      ? state.compatibilityProfile.profile.intolerance
      : Number(data.patient) === state.detail?.patient.id
        ? state.detail.profile.intolerance
        : "";
  if (known === data.choice)
    blocks.push(
      "В синтетической карточке указана несовместимость с выбранным вариантом.",
    );
  if (Number(data.age) < 18)
    (data.choice === "demo-beta" ? cautions : blocks).push(
      "Возраст младше 18: сработало придуманное возрастное правило.",
    );
  if (Number(data.egfr) < 30)
    (data.choice === "demo-alpha" ? blocks : cautions).push(
      "Снижена учебная СКФ: пример проверки функции почек.",
    );
  const factors = [
    ["pregnancy", "беременность / лактация"],
    ["epilepsy", "эпилепсия"],
    ["cardio", "сердечно-сосудистые заболевания"],
    ["diabetes", "диабет"],
  ]
    .filter(([key]) => form.elements[key].checked)
    .map(([, label]) => label);
  if (data.liver !== "Нет ограничений")
    factors.push("ограничение со стороны печени");
  if (factors.length)
    cautions.push(
      "Указаны факторы для отдельной проверки: " + factors.join(", ") + ".",
    );
  if (data.other === "demo-gamma")
    (data.choice === "demo-beta" ? cautions : blocks).push(
      `${primary} + ДЕМО-Гамма: придуманное ${data.choice === "demo-beta" ? "предупреждение" : "несовместимое сочетание"}.`,
    );
  else if (data.other === "demo-beta")
    cautions.push(
      data.choice === "demo-beta"
        ? "Повтор выбранного варианта в учебном списке."
        : `${primary} + ДЕМО-Бета: пример предупреждения о сочетании.`,
    );
  const status = blocks.length
    ? "Есть опасности в демо-сценарии"
    : cautions.length
      ? "Нужна дополнительная проверка"
      : "Учебные ограничения не отмечены";
  $("#compatibility-result").innerHTML =
    `<span class="chip ${blocks.length ? "red" : cautions.length ? "amber" : "green"}">${blocks.length ? "Ограничение" : cautions.length ? "Внимание" : "Демо-проверка завершена"}</span><h2>${status}</h2><p><strong>${e(primary)}</strong> · ${e(form.elements.patient.selectedOptions[0].textContent)} · возраст ${e(data.age)}</p>${[...blocks, ...cautions].length ? `<ul>${[...blocks, ...cautions].map((text) => `<li>${e(text)}</li>`).join("")}</ul>` : "<p>В заданном учебном случае правила не нашли отмеченных ограничений.</p>"}`;
}
document.addEventListener("change", async (event) => {
  if (event.target.id !== "compatibility-patient") return;
  const select = event.target,
    form = select.form,
    version = ++compatibilityRequest;
  const patient = state.patients.find((p) => p.id === Number(select.value));
  for (const input of form.querySelectorAll('input[type="checkbox"]'))
    input.checked = false;
  form.elements.age.value = patient?.age || 40;
  form.elements.egfr.value = 90;
  form.elements.liver.selectedIndex = 0;
  form.elements.other.value = "none";
  $("#compatibility-profile").textContent = patient
    ? "Загружаю синтетическую карточку…"
    : "Свой сценарий: задайте характеристики вручную.";
  form.querySelector('[type="submit"]').disabled = false;
  if (!patient) return;
  form.querySelector('[type="submit"]').disabled = true;
  try {
    const record = await api(`/api/patients/${patient.id}`);
    if (version !== compatibilityRequest || !document.contains(form)) return;
    state.compatibilityPatient = patient.id;
    state.compatibilityProfile = { id: patient.id, profile: record.profile };
    $("#compatibility-profile").textContent =
      `Пациент: ${patient.name}. ${compatibilityProfileNote(record.profile)}`;
  } catch (error) {
    if (version === compatibilityRequest && document.contains(form))
      $("#compatibility-profile").textContent = error.message;
  } finally {
    if (version === compatibilityRequest && document.contains(form))
      form.querySelector('[type="submit"]').disabled = false;
  }
});
for (const eventName of ["input", "change"])
  document.addEventListener(eventName, (event) => {
    if (
      event.target.closest("#compatibility-form") &&
      $("#compatibility-result")
    )
      $("#compatibility-result").innerHTML =
        "<p>Параметры изменены. Нажмите «Проверить сценарий».</p>";
  });

function monthGrid(month, selected, items, group) {
  const [year, m] = month.split("-").map(Number);
  const offset = (new Date(Date.UTC(year, m - 1, 1)).getUTCDay() + 6) % 7;
  const length = new Date(Date.UTC(year, m, 0)).getUTCDate();
  const label = new Date(Date.UTC(year, m - 1, 1)).toLocaleDateString("ru-RU", {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
  return `<div class="month-panel"><div class="month-toolbar"><button class="icon-button" data-experience="month" data-group="${group}" data-offset="-1" aria-label="Предыдущий месяц">${icon("back")}</button><h3>${e(label)}</h3><button class="icon-button" data-experience="month" data-group="${group}" data-offset="1" aria-label="Следующий месяц">${icon("arrow")}</button></div><div class="activity-calendar" role="group" aria-label="${e(label)}">${["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"].map((d) => `<span class="weekday">${d}</span>`).join("")}${"<span></span>".repeat(offset)}${Array.from(
    { length },
    (_, i) => {
      const day = `${month}-${String(i + 1).padStart(2, "0")}`;
      const events = items.filter((a) => a.day === day);
      return `<button class="activity-day ${day === care().today ? "today" : ""}" data-experience="calendar-day" data-group="${group}" data-day="${day}" aria-pressed="${day === selected}" aria-label="${e(dayLabel(day))}: ${events.length} ${group === "doctor" ? "консультаций" : "занятий"}"><span>${i + 1}</span><span class="calendar-marks">${events.length ? `<i class="${events.some((a) => a.status === "done") ? "done" : ""}"></i><small>${events.length}</small>` : ""}</span></button>`;
    },
  ).join("")}</div></div>`;
}
function activityCalendar() {
  const today = care().today,
    selected = state.activityDay || today;
  const plans = (state.wellbeing?.plans || []).filter(
    (p) => p.status !== "cancelled",
  );
  const completed = (state.wellbeing?.activities || []).filter((a) =>
    ["morning", "desk", "walk", "evening"].includes(a.activity_key),
  );
  const marks = [
    ...plans,
    ...completed
      .filter((a) => !plans.some((p) => p.completed_at === a.created_at))
      .map((a) => ({ ...a, day: clinicDay(a.created_at), status: "done" })),
  ];
  return `<div class="calendar-and-agenda">${monthGrid(state.activityMonth || selected.slice(0, 7), selected, marks, "activity")}<div class="day-agenda"><p class="eyebrow">ВЫБРАННЫЙ ДЕНЬ</p><h3>${e(dayLabel(selected))}</h3>${
    plans
      .filter((p) => p.day === selected)
      .map((p) => {
        const item = prototypeContent.exercises.find(
          (i) => i.id === p.activity_key,
        );
        return `<article class="planned-exercise"><div><strong>${e(item.name)}</strong><p class="caption">${p.status === "done" ? "✓ Выполнено" : "Запланировано"} · ${item.min} мин</p></div>${p.status === "planned" ? `<div class="proposal-actions"><button class="button small primary" data-experience="activity-complete" data-id="${p.id}" ${p.day > today ? "disabled" : ""}>Выполнено</button><button class="button small quiet" data-experience="activity-cancel" data-id="${p.id}">Убрать</button></div>` : ""}</article>`;
      })
      .join("") ||
    '<p class="muted">Пока нет запланированных занятий. Добавьте упражнение из списка ниже.</p>'
  }${completed
    .filter(
      (a) =>
        clinicDay(a.created_at) === selected &&
        !plans.some((p) => p.completed_at === a.created_at),
    )
    .map((a) => `<p class="caption">✓ ${e(a.title)} · самоотметка</p>`)
    .join("")}</div></div>`;
}
function movementExperience() {
  const selected = state.activityDay || care().today;
  return `<div id="weekly-activity">${weeklyActivity()}</div><section class="card"><div class="card-heading"><h2>Календарь активности</h2><span class="chip neutral">МСК</span></div><p class="caption">Точка — запланированное занятие, зелёная — есть отметка о выполнении.</p><div id="activity-calendar-panel">${activityCalendar()}</div></section>
    <section class="card"><h2>Добавить упражнение</h2><div class="movement-exercise-list">${prototypeContent.exercises.map((item) => `<article class="movement-exercise"><div class="routine-icon">${icon("run")}</div><div><h3>${e(item.name)}</h3><p class="caption">${item.min} мин · ${e(item.desc)}</p><details><summary>Как выполнять</summary><ol>${item.steps.map((s) => `<li><strong>${e(s[0])}.</strong> ${e(s[1])}</li>`).join("")}</ol></details><form class="activity-plan-form" data-key="${item.id}"><label>Дата<input type="date" name="day" required value="${selected}"></label><button class="button primary" type="submit">В календарь</button></form></div></article>`).join("")}</div></section>${wearableCard()}`;
}
function doctorCalendar() {
  const items = (state.appointments || [])
    .filter((a) => a.status !== "cancelled")
    .map((a) => ({ ...a, day: clinicDay(a.starts_at) }));
  const selected = state.doctorDay || care().today;
  return `<section class="card doctor-calendar-card"><div class="card-heading"><div><p class="eyebrow">ПРИЁМЫ ПАЦИЕНТОВ</p><h2>Календарь консультаций</h2></div><button class="button" data-action="nav" data-page="schedule">Расписание ${icon("arrow")}</button></div><div id="doctor-calendar-panel">${doctorCalendarPanel(items, selected)}</div></section>`;
}
function doctorCalendarPanel(
  items = (state.appointments || [])
    .filter((a) => a.status !== "cancelled")
    .map((a) => ({ ...a, day: clinicDay(a.starts_at) })),
  selected = state.doctorDay || care().today,
) {
  return `<div class="calendar-and-agenda">${monthGrid(state.doctorMonth || selected.slice(0, 7), selected, items, "doctor")}<div class="day-agenda"><p class="eyebrow">ВЫБРАННЫЙ ДЕНЬ</p><h3>${e(dayLabel(selected))}</h3>${
    items
      .filter((a) => a.day === selected)
      .map(
        (a) =>
          `<button class="calendar-appointment" data-action="patient" data-id="${a.patient_id}"><span class="appointment-time">${e(timeLabel(a.starts_at))}</span><span><strong>${e(a.patient_name)}</strong><small>${e(a.kind)} · ${a.status === "completed" ? "Завершена" : "Запланирована"}</small></span>${icon("arrow")}</button>`,
      )
      .join("") || '<p class="muted">На этот день приёмов нет.</p>'
  }</div></div>`;
}

function practiceHistory() {
  return (
    (state.wellbeing?.activities || [])
      .filter((a) => a.kind === "practice")
      .slice(0, 8)
      .map(
        (a) =>
          `<div class="activity-row">${icon("check")}<div><strong>${e(a.title)}</strong><small>${e(clinicDate(a.created_at))} · самоотметка</small></div></div>`,
      )
      .join("") || '<p class="muted">Здесь появятся выполненные упражнения.</p>'
  );
}
function calmPractices() {
  const choices = [
    {
      key: "rhythm",
      title: "Дыхание 4 · 2 · 6",
      desc: "Мягкий ритм с необязательной паузой",
      glyph: "sun",
    },
    {
      key: "grounding",
      title: "Пять вещей вокруг",
      desc: "Заземление 5–4–3–2–1",
      glyph: "leaf",
    },

    ...prototypeContent.exercises.map((i) => ({
      key: i.id,
      title: i.name,
      desc: `${i.min} мин · ${i.desc}`,
      glyph: "run",
    })),
  ];
  return `<div class="practice-list">${choices.map((item) => `<details class="card practice-accordion" data-practice="${item.key}"><summary><span class="routine-icon">${icon(item.glyph)}</span><span><strong>${e(item.title)}</strong><small>${e(item.desc)}</small></span>${icon("plus")}</summary><div class="practice-expansion"><div class="practice-ready"><div class="ready-halo" aria-hidden="true">${icon(item.glyph)}</div><h3>Вы готовы приступить к упражнению?</h3><p class="caption">Устройтесь удобно. Можно остановиться в любой момент.</p><button class="button primary" data-experience="practice-begin" data-key="${item.key}">Да, начать</button></div><div class="practice-workspace" hidden>${practiceWorkspace(item.key)}</div></div></details>`).join("")}</div><section class="card"><h2>Выполнено упражнений: <output id="practice-count">${state.wellbeing?.practice_count || 0}</output></h2><div id="practice-history">${practiceHistory()}</div></section>`;
}
function practiceWorkspace(key) {
  if (key === "rhythm")
    return `<label class="consent-switch"><input type="checkbox" id="breath-voice" ${breathingVoice ? "checked" : ""}><span>Озвучивать дыхание</span></label><div class="breath-space"><div class="breathing-orb"><span id="breath-phase">Готовы?</span></div></div><p class="caption">Вдох 4, необязательная пауза 2, выдох 6. Можно пропустить задержку и дышать привычно. При дискомфорте остановитесь.</p><button class="button" data-experience="breath-control">Остановить</button>`;
  if (key === "grounding")
    return `<ol class="grounding-steps">${groundingSteps.map(([title, text], i) => `<li ${i ? "hidden" : 'aria-current="step"'}><h3>${title}</h3><p>${text}</p></li>`).join("")}</ol><button class="button primary" data-experience="ground-step">Далее</button>`;
  return `<div class="guided-step"></div><p class="exercise-clock guided-clock" aria-live="off"></p><div class="proposal-actions"><button class="button" data-experience="guided-pause">Пауза</button><button class="button" data-experience="guided-next">Дальше</button></div><p class="caption">Двигайтесь в комфортном диапазоне; остановитесь при боли или дискомфорте.</p>`;
}
function stopGuidedExercise() {
  clearInterval(guidedTicker);
  guidedTicker = null;
  guidedExercise = null;
}
function updateGuidedExercise() {
  const session = guidedExercise;
  if (!session || !document.contains(session.root)) {
    stopGuidedExercise();
    return;
  }
  const item = prototypeContent.exercises.find((i) => i.id === session.key);
  const step = item?.steps[session.step];
  const left = session.paused
    ? session.left
    : Math.max(0, Math.ceil((session.end - Date.now()) / 1000));
  session.root.querySelector(".guided-clock").textContent =
    `${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`;
  session.root.querySelector(".guided-step").innerHTML = step
    ? `<p class="eyebrow">ШАГ ${session.step + 1} ИЗ ${item.steps.length}</p><h3>${e(step[0])}</h3><p>${e(step[1])}</p>`
    : "<h3>Минута для себя</h3><p>Дышите в привычном ритме, без усилия и задержек. Можно просто наблюдать за кругом.</p>";
  const last = !item || session.step === item.steps.length - 1;
  const next = session.root.querySelector('[data-experience="guided-next"]');
  if (next) next.hidden = last;
  if (last && left === 0) {
    stopGuidedExercise();
    completePractice(session.root, session.key);
  }
}
function beginGuidedExercise(key, root) {
  stopGuidedExercise();
  const item = prototypeContent.exercises.find((i) => i.id === key);
  guidedExercise = {
    key,
    root,
    step: 0,
    paused: false,
    end: Date.now() + (item ? item.steps[0][2] : 60) * 1000,
  };
  updateGuidedExercise();
  guidedTicker = setInterval(updateGuidedExercise, 500);
}
function stopwatchValue() {
  let seconds = Math.max(
    0,
    Math.floor(
      (Date.now() -
        (state.counterClockOffset || 0) -
        new Date(pref().streak_start).getTime()) /
        1000,
    ),
  );
  const days = Math.floor(seconds / 86400);
  seconds %= 86400;
  return `${days} дн. ${String(Math.floor(seconds / 3600)).padStart(2, "0")}:${String(Math.floor((seconds % 3600) / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}
function decorateExperience() {
  updatePatientScreen();
  $("#patient-safety-bar").hidden =
    state.user.role !== "patient" ||
    (state.page === "help" && sub("help", "now") === "sos");
  if (state.page !== "overview")
    $("#content").insertAdjacentHTML(
      "afterbegin",
      `<button class="button back-link page-back" data-experience="back" aria-label="Назад">${icon("back")}Назад</button>`,
    );
  if (state.page !== "help" || sub("help", "now") !== "calm") {
    stopGuidedExercise();
    stopBreathing();
  }
  clearInterval(streakTicker);
  if ($("#streak-display") && pref().streak_on)
    streakTicker = setInterval(() => {
      const el = $("#streak-display");
      if (el) el.textContent = stopwatchValue();
    }, 1000);
}
async function refreshActivities() {
  const owner = state.user?.id,
    selected = state.selected;
  const result = await api(`/api/patients/${selected}/wellbeing`);
  if (state.user?.id !== owner || state.selected !== selected) return;
  state.wellbeing = result;
  if ($("#activity-calendar-panel"))
    $("#activity-calendar-panel").innerHTML = activityCalendar();
  if ($("#practice-history"))
    $("#practice-history").innerHTML = practiceHistory();
  if ($("#practice-count"))
    $("#practice-count").textContent = String(
      state.wellbeing.practice_count || 0,
    );
  if ($("#weekly-activity")) $("#weekly-activity").innerHTML = weeklyActivity();
}

document.addEventListener(
  "toggle",
  (event) => {
    const item = event.target;
    if (!item.matches?.("details[data-practice]")) return;
    if (item.open) {
      document
        .querySelectorAll("details[data-practice][open]")
        .forEach((other) => {
          if (other !== item) other.open = false;
        });
    } else {
      if (item.dataset.practice === "rhythm") stopBreathing();
      if (guidedExercise?.root === item) stopGuidedExercise();
      item.querySelector(".practice-ready").hidden = false;
      item.querySelector(".practice-workspace").hidden = true;
      item
        .querySelectorAll('[data-experience="practice-save"]')
        .forEach((b) => {
          b.disabled = false;
          b.textContent = "Отметить выполненным";
        });
    }
  },
  true,
);

document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-experience]");
  if (!button || button.disabled || !state.user || busy) return;
  const action = button.dataset.experience,
    key = button.dataset.key;
  try {
    if (action === "back") {
      await goBack();
    } else if (action === "tree-bloom") {
      plantFlower(event, button);
    } else if (action === "month" || action === "calendar-day") {
      const group = button.dataset.group,
        prefix =
          group === "doctor"
            ? "doctor"
            : group === "diary"
              ? "calendar"
              : "activity";
      if (action === "month") {
        const [year, month] = (
          state[prefix + "Month"] ||
          (state[prefix + "Day"] || care().today).slice(0, 7)
        )
          .split("-")
          .map(Number);
        state[prefix + "Month"] = new Date(
          Date.UTC(year, month - 1 + Number(button.dataset.offset), 1),
        )
          .toISOString()
          .slice(0, 7);
      } else state[prefix + "Day"] = button.dataset.day;
      if (group === "diary") {
        $("#daily-calendar").innerHTML = patientDailyCalendar();
        return;
      }
      $(
        group === "doctor"
          ? "#doctor-calendar-panel"
          : "#activity-calendar-panel",
      ).innerHTML =
        group === "doctor" ? doctorCalendarPanel() : activityCalendar();
      if (group === "activity" && action === "calendar-day")
        document
          .querySelectorAll('.activity-plan-form [name="day"]')
          .forEach((i) => (i.value = button.dataset.day));
    } else if (action === "activity-complete" || action === "activity-cancel") {
      button.disabled = true;
      try {
        await write(
          `/api/patients/${state.selected}/activity-plans/${button.dataset.id}/${action === "activity-complete" ? "complete" : "cancel"}`,
          {},
        );
        await refreshActivities();
      } finally {
        button.disabled = false;
      }
    } else if (action === "practice-begin") {
      const root = button.closest("[data-practice]");
      delete root.dataset.completion;
      root.dataset.session = newPracticeId();
      root.querySelector(".practice-workspace").innerHTML =
        practiceWorkspace(key);
      root.querySelector(".practice-ready").hidden = true;
      root.querySelector(".practice-workspace").hidden = false;
      if (key === "rhythm") {
        breathingStarted = Date.now();
        lastBreathPhase = -1;
        stopBreathing();
        breathingTicker = setInterval(tickBreathing, 250);
        tickBreathing();
        root.querySelector(".breathing-orb").classList.add("running");
      } else if (key === "grounding") {
        root.dataset.step = "0";
        root.querySelectorAll(".grounding-steps li").forEach((li, i) => {
          li.hidden = i !== 0;
          if (i === 0) li.setAttribute("aria-current", "step");
          else li.removeAttribute("aria-current");
        });
        root.querySelector('[data-experience="ground-step"]').hidden = false;
      } else beginGuidedExercise(key, root);
    } else if (action === "breath-control") {
      const root = button.closest("[data-practice]");
      if (breathingTicker) {
        stopBreathing();
        button.textContent = "Продолжить";
      } else {
        breathingStarted = Date.now();
        lastBreathPhase = -1;
        breathingTicker = setInterval(tickBreathing, 250);
        tickBreathing();
        button.textContent = "Остановить";
      }
      root
        .querySelector(".breathing-orb")
        .classList.toggle("running", !!breathingTicker);
    } else if (action === "ground-step") {
      const root = button.closest("[data-practice]"),
        step = Math.min(5, Number(root.dataset.step) + 1);
      root.dataset.step = String(step);
      if (step === 5) {
        await completePractice(root, "grounding");
      } else {
        root.querySelectorAll(".grounding-steps li").forEach((li, i) => {
          li.hidden = i !== step;
        });
      }
    } else if (action === "guided-pause" && guidedExercise) {
      if (guidedExercise.paused) {
        guidedExercise.end = Date.now() + guidedExercise.left * 1000;
        guidedExercise.paused = false;
        button.textContent = "Пауза";
      } else {
        guidedExercise.left = Math.max(
          0,
          Math.ceil((guidedExercise.end - Date.now()) / 1000),
        );
        guidedExercise.paused = true;
        button.textContent = "Продолжить";
      }
      updateGuidedExercise();
    } else if (action === "guided-next" && guidedExercise) {
      const item = prototypeContent.exercises.find(
        (i) => i.id === guidedExercise.key,
      );
      guidedExercise.step = Math.min(
        item.steps.length - 1,
        guidedExercise.step + 1,
      );
      guidedExercise.end =
        Date.now() + item.steps[guidedExercise.step][2] * 1000;
      guidedExercise.paused = false;
      guidedExercise.root.querySelector(
        '[data-experience="guided-pause"]',
      ).textContent = "Пауза";
      updateGuidedExercise();
    } else if (action === "practice-save") {
      button.disabled = true;
      try {
        await write(`/api/patients/${state.selected}/wellbeing`, {
          activity: key,
        });
        stopGuidedExercise();
        await refreshActivities();
        button.textContent = "✓ Сохранено";
        toast("Занятие отмечено выполненным");
      } catch (error) {
        button.disabled = false;
        throw error;
      }
    } else if (action === "streak-start") {
      button.disabled = true;
      try {
        await write(`/api/patients/${state.selected}/counter/start`, {});
        await load();
      } finally {
        button.disabled = false;
      }
    }
  } catch (error) {
    toast(error.message, true);
  }
});
document.addEventListener("submit", (event) => {
  const form = event.target;
  if (!form.matches(".activity-plan-form")) return;
  return run(form, async () => {
    const day = form.elements.day.value;
    await write(`/api/patients/${state.selected}/activity-plans`, {
      activity: form.dataset.key,
      day,
    });
    state.activityDay = day;
    state.activityMonth = day.slice(0, 7);
    await refreshActivities();
    toast("Упражнение добавлено в календарь");
  });
});
