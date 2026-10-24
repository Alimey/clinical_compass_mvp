"use strict";

// Original demo prompts, not reproductions or scoring keys of clinical instruments.
const extraAssessments = Object.fromEntries(
  [
    ["mmpi", "MMPI", []],
    [
      "leonhard",
      "Опросник Леонгарда–Шмишека",
      [
        "Я быстро увлекаюсь новым",
        "Мне важен привычный порядок",
        "Я долго обдумываю события",
        "Мне легко проявлять чувства",
        "Я замечаю настроение окружающих",
        "Мне комфортно менять планы",
      ],
    ],
    ["beck_hopelessness", "Тест безнадёжности Бека", []],
    ["beck_depression", "Тест депрессии Бека", []],
    [
      "spielberger",
      "Тревожность Спилбергера: ситуативная и личностная",
      [
        "Сейчас я чувствую напряжение",
        "Сейчас мне трудно расслабиться",
        "Сейчас я беспокоюсь о будущем",
        "Обычно я заранее переживаю",
        "Обычно мне трудно отвлечься от тревоги",
        "Обычно мне нужна помощь, чтобы успокоиться",
      ],
    ],
    [
      "hcl33",
      "Шкала HCL-33",
      [
        "Бывали периоды необычного прилива сил",
        "В такие дни я больше общался",
        "Я замечал ускорение мыслей",
        "Я брался за много дел",
        "Мой привычный сон менялся",
        "Окружающие замечали перемены",
      ],
    ],
    [
      "mdq",
      "Шкала MDQ",
      [
        "Я замечал необычно активные периоды",
        "Моё настроение менялось",
        "Мне хотелось говорить больше обычного",
        "Мне было трудно остановить поток идей",
        "Это влияло на повседневные дела",
        "Мне хотелось обсудить это со специалистом",
      ],
    ],
    [
      "dembo",
      "Самооценка Дембо–Рубинштейн",
      [
        "Я доволен своими возможностями",
        "Я чувствую уверенность в общении",
        "Я замечаю свои сильные стороны",
        "Мне удаётся справляться с задачами",
        "Я могу принимать поддержку",
        "Я понимаю свои ближайшие цели",
      ],
    ],
    [
      "cope",
      "COPE",
      [
        "Я составляю план действий",
        "Я прошу поддержки",
        "Я делаю паузу",
        "Я ищу информацию",
        "Я обсуждаю чувства",
        "Я переключаюсь на посильное занятие",
      ],
    ],
  ].map(([key, title, questions]) => [key, { title, questions }]),
);
const patientVideoTitles = [
  "Синапс под дождем: как нейромедиаторы управляют настроением",
  "Четыре ключа к мозгу: как на самом деле работают лекарства в психиатрии",
  "У кабинета: что нужно знать перед визитом к психиатру",
  "Психолог, психотерапевт, психиатр: в чем разница",
  "Три техники против тревоги: дыхание, чувства, ТРУД",
];
const relativeVideoTitles = [
  "Это может случиться в любой семье: как принять болезнь близкого",
  "Бесплатная помощь в Москве: куда звонить и куда идти",
  "Мифы и правда о суициде: что нужно знать близким",
];
prototypeContent.course.forEach(
  (item, i) => (item.t = patientVideoTitles[i] || item.t),
);
prototypeContent.relativeCourse.forEach(
  (item, i) => (item.t = relativeVideoTitles[i] || item.t),
);
let schulteRun = null;
function assessmentTitle(kind) {
  return (
    extraAssessments[kind]?.title ||
    {
      gad7: "GAD-7",
      phq9: "PHQ-9",
      schulte: "Таблицы Шульте",
      serial7: "Вычитание по 7 из 100",
    }[kind] ||
    kind
  );
}
function completeLocalAssignment(id) {
  const item = ws().assessment_assignments?.find((a) => a.id === id);
  if (item) item.status = "completed";
}
function assessmentAssignmentPanel(doctor) {
  const assignments = ws().assessment_assignments || [];
  const kinds = [
    "gad7",
    "phq9",
    ...Object.keys(extraAssessments).filter((k) => !licensedAssessments.has(k)),
    "schulte",
    "serial7",
  ];
  return `${doctor ? `<section class="card"><h2>Назначить шкалу или упражнение</h2><form id="assign-assessment-form"><label>Форма<select name="kind">${kinds.map((k) => `<option value="${k}">${e(assessmentTitle(k))}</option>`).join("")}</select></label><label>Срок выполнения · время устройства<input type="datetime-local" name="due_at" required></label><button class="button primary">Назначить пациенту</button></form></section>` : ""}<section class="assessment-assignments"><h2>${doctor ? "Задания пациенту" : "Назначено специалистом"}</h2>${assignments.length ? assignments.map((a) => `<article class="card"><h3>${e(assessmentTitle(a.kind))}</h3>${licensedAssessments.has(a.kind) ? "<p>Проводится на приёме по лицензии.</p>" : ""}<p>До ${e(clinicDate(a.due_at))}</p><p class="chip">${a.status === "completed" ? "Выполнено" : a.status === "cancelled" ? "Отменено" : Date.parse(a.due_at) < Date.now() ? "Срок прошёл · можно заполнить" : "Ожидает выполнения"}</p>${a.status === "assigned" && (doctor || !licensedAssessments.has(a.kind)) ? (doctor ? `<button class="button" data-cancel-assessment="${a.id}">Отменить задание</button>` : `<button class="button primary" data-ext="assessment" data-key="${a.kind}" data-assessment-assignment="${a.id}">Пройти ${e(assessmentTitle(a.kind))}</button>`) : ""}</article>`).join("") : '<p class="empty">Шкалы и упражнения пока не назначены.</p>'}</section>`;
}
const unassignedSurveysPage = surveysPage;
surveysPage = function () {
  return (
    (isDoctor() ? assessmentAssignmentPanel(true) : "") +
    unassignedSurveysPage()
  );
};
document.addEventListener("click", async (event) => {
  const assignment = event.target.closest("[data-assessment-assignment]");
  if (assignment && !busy)
    state.assessmentAssignment = Number(
      assignment.dataset.assessmentAssignment,
    );
  const cancel = event.target.closest("[data-cancel-assessment]");
  if (!cancel || busy) return;
  cancel.disabled = true;
  try {
    await write(
      `/api/patients/${state.selected}/assessment-assignments/${Number(cancel.dataset.cancelAssessment)}/cancel`,
      {},
    );
    await load();
  } catch (error) {
    toast(error.message, true);
  } finally {
    cancel.disabled = false;
  }
});
document.addEventListener("submit", (event) => {
  const form = event.target;
  if (form.id !== "assign-assessment-form") return;
  event.preventDefault();
  run(form, async () => {
    await write(`/api/patients/${state.selected}/assessment-assignments`, {
      kind: form.elements.kind.value,
      due_at: new Date(form.elements.due_at.value).toISOString(),
    });
    await load();
    toast("Задание назначено");
  });
});
function extendedAssessment(key) {
  if (licensedAssessments.has(key)) return licensedAssessmentNotice(key);
  if (key === "schulte") {
    const numbers = Array.from({ length: 25 }, (_, i) => i + 1);
    for (let i = numbers.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [numbers[i], numbers[j]] = [numbers[j], numbers[i]];
    }
    schulteRun = {
      next: 1,
      started: null,
      saving: false,
      assignment: state.assessmentAssignment,
    };
    return `<section class="card"><h2>Таблицы Шульте</h2><p>Нажимайте числа от 1 до 25 по порядку. Время начнётся с первого верного нажатия.</p><div class="schulte-grid">${numbers.map((n) => `<button class="button" data-schulte="${n}">${n}</button>`).join("")}</div><p id="schulte-status" role="status">Найдите 1</p><button class="button" data-ext="assessment-cancel">Закрыть</button></section>`;
  }
  if (key === "serial7")
    return `<section class="card"><h2>Вычитание по 7 из 100</h2><p>Начните со 100. Каждый раз вычитайте 7 из предыдущего ответа.</p><form id="serial7-form">${Array.from({ length: 13 }, (_, i) => `<label>Шаг ${i + 1}<input name="q${i}" type="number" min="0" max="100" required></label>`).join("")}<button class="button primary">Проверить и сохранить</button><button type="button" class="button" data-ext="assessment-cancel">Отмена</button></form><p id="serial7-result" role="status"></p></section>`;
  const item = extraAssessments[key];
  return `<section class="card"><h2>${e(item.title)} · учебная форма</h2><p>Демонстрация прохождения и сохранения ответов, без интерпретации по ключам методики.</p><form class="extra-assessment-form" data-kind="${key}">${item.questions.map((q, i) => `<label>${i + 1}. ${e(q)}<select name="q${i}" required><option value="">Выберите ответ</option>${["Нет", "Иногда", "Часто", "Почти всегда"].map((t, v) => `<option value="${v}">${t}</option>`).join("")}</select></label>`).join("")}<button class="button primary">Сохранить ответы</button><button class="button" type="button" data-ext="assessment-cancel">Отмена</button></form></section>`;
}
document.addEventListener("submit", (event) => {
  const form = event.target;
  if (form.matches(".counter-label-form")) {
    event.preventDefault();
    return run(form, async () => {
      await savePreference({
        streak_label: form.elements.label.value.trim() || "Мой отсчёт",
      });
    });
  }
  if (!form.matches(".extra-assessment-form, #serial7-form")) return;
  event.preventDefault();
  const serial = form.id === "serial7-form",
    kind = serial ? "serial7" : form.dataset.kind;
  const answers = Array.from({ length: serial ? 13 : 6 }, (_, i) =>
    Number(form.elements["q" + i].value),
  );
  run(form, async () => {
    await write(`/api/patients/${state.selected}/assessments`, {
      kind,
      answers,
      assignment_id: state.assessmentAssignment,
    });
    completeLocalAssignment(state.assessmentAssignment);
    if (serial) {
      const correct = answers.filter((v, i) => v === 100 - 7 * (i + 1)).length;
      $("#serial7-result").textContent =
        `Верных ответов: ${correct} из 13. Ответы сохранены.`;
    } else {
      state.assessmentKind = null;
      await load();
      toast("Ответы сохранены");
    }
  });
});
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-schulte]");
  if (!button || busy || !schulteRun || schulteRun.saving) return;
  if (Number(button.dataset.schulte) !== schulteRun.next) {
    $("#schulte-status").textContent = `Найдите ${schulteRun.next}`;
    return;
  }
  schulteRun.started ??= performance.now();
  button.disabled = true;
  schulteRun.next++;
  if (schulteRun.next <= 25) {
    $("#schulte-status").textContent = `Найдите ${schulteRun.next}`;
    return;
  }
  const seconds = Math.max(
    1,
    Math.round((performance.now() - schulteRun.started) / 1000),
  );
  schulteRun.saving = true;
  const status = $("#schulte-status"),
    session = schulteRun;
  try {
    await write(`/api/patients/${state.selected}/assessments`, {
      kind: "schulte",
      assignment_id: session.assignment,
      answers: [seconds],
    });
    completeLocalAssignment(session.assignment);
    if (status.isConnected)
      status.textContent = `Готово за ${seconds} сек. Результат сохранён.`;
  } catch (error) {
    session.next = 25;
    session.saving = false;
    button.disabled = false;
    if (status.isConnected) toast(error.message, true);
  }
});
treePage = function () {
  return (
    heading("МОЁ ДЕРЕВО", "Мои цветы заботы", "") +
    `<section class="card earned-tree"><button class="tree-touch" data-experience="tree-bloom" aria-label="Добавить маленький розовый цветок">${treeArt(carePoints(), true)}</button><ul class="tree-legend">${[
      ["#e4b83f", "Жёлтые — отмеченный приём лекарства"],
      ["#5199dc", "Синие — завершённая консультация"],
      ["#a786c9", "Сиреневые — запись в дневнике"],
      ["#6bad81", "Зелёные — завершённое упражнение"],
      ["#f2a3b9", "Маленькие розовые — касание дерева"],
    ]
      .map(
        ([color, label]) =>
          `<li><span class="legend-flower" data-color="${color}"></span>${label}</li>`,
      )
      .join("")}</ul></section>`
  );
};
const labMaze = (() => {
  // One vector mark is shared by the game picker, heading and canvas.
  const brandColor = "#087d9c";
  const brandPetal =
    "M40 13C29 7 15 14 13 26C11 37 21 44 31 40L39 33L29 24L22 30L31 37C24 39 18 35 18 29C18 20 29 14 40 13Z";
  const brandIcon = () =>
    `<svg class="maze-brand-mark" viewBox="0 0 64 64" aria-hidden="true" focusable="false"><circle cx="32" cy="32" r="28" fill="white" stroke="${brandColor}" stroke-width="3"/><g fill="${brandColor}"><path d="${brandPetal}"/><path d="${brandPetal}" transform="rotate(180 32 32)"/></g></svg>`;
  const petal = new Path2D(brandPetal);
  function drawBrand(c, x, y, size) {
    c.save();
    c.translate(x, y);
    c.scale(size / 64, size / 64);
    c.fillStyle = "#ffffff";
    c.strokeStyle = brandColor;
    c.lineWidth = 3;
    c.beginPath();
    c.arc(32, 32, 28, 0, Math.PI * 2);
    c.fill();
    c.stroke();
    c.fillStyle = brandColor;
    c.fill(petal);
    c.translate(32, 32);
    c.rotate(Math.PI);
    c.translate(-32, -32);
    c.fill(petal);
    c.restore();
  }
  function drawCarton(c, x, y, cells) {
    const w = cells * 36 - 4,
      h = 32,
      compact = cells === 1;
    c.save();
    c.translate(x + 2, y + 2);
    c.fillStyle = "#ded7e6";
    c.beginPath();
    c.roundRect(1, 2, w, h, 3);
    c.fill();
    const paper = c.createLinearGradient(0, 0, w, h);
    paper.addColorStop(0, "#ffffff");
    paper.addColorStop(1, "#eeeef0");
    c.fillStyle = paper;
    c.strokeStyle = "#9385a2";
    c.lineWidth = 1;
    c.beginPath();
    c.roundRect(0.5, 0.5, w - 1, h - 1, 2.5);
    c.fill();
    c.stroke();
    c.save();
    c.clip();
    c.fillStyle = "#b6a0c5";
    c.fillRect(0, 0, compact ? 5 : 7, h);
    c.fillStyle = "#d2c2dc";
    c.fillRect(0, 0, w, 3);
    c.fillStyle = "#b6a0c5";
    c.fillRect(0, 0, compact ? 7 : 11, 5);
    c.fillRect(w - 9, 0, 9, 3);
    c.restore();
    c.fillStyle = "#292c30";
    c.font = `700 ${compact ? 5.2 : 9}px sans-serif`;
    c.fillText(
      "АВИАНДР",
      compact ? 7 : 11,
      compact ? 12 : 15,
      w - (compact ? 9 : 15),
    );
    c.fillStyle = "#88b99c";
    c.beginPath();
    c.roundRect(w - (compact ? 17 : 24), 23, compact ? 14 : 21, 6, 2);
    c.fill();
    c.fillStyle = "#ffffff";
    c.font = `700 ${compact ? 4.5 : 5}px sans-serif`;
    c.fillText("20 мг", w - (compact ? 15 : 20), 27.5);
    if (!compact) {
      c.fillStyle = "#9c91a8";
      for (let i = 0; i < 4; i++) c.fillRect(11, 20 + i * 2, 2, 1);
      drawBrand(c, w - 11, 5, 7);
    }
    c.restore();
  }
  const maze = [
    "###############",
    "#.............#",
    "#.###.###.###.#",
    "#...#.....#...#",
    "###.#.###.#.###",
    "#.....#.#.....#",
    "#.###.#.#.###.#",
    "#.............#",
    "#.###.###.###.#",
    "#.............#",
    "###############",
  ];
  const open = (x, y) => maze[y]?.[x] === ".";
  function create() {
    return {
      player: { x: 1, y: 1 },
      pills: new Set(
        maze.flatMap((row, y) =>
          [...row].flatMap((c, x) =>
            c === "." && !(x === 1 && y === 1) ? [`${x},${y}`] : [],
          ),
        ),
      ),
      collected: 0,
      ghost: { x: 13, y: 9 },
      turns: 0,
      over: false,
    };
  }
  function step(m, dx, dy) {
    if (m.over || !open(m.player.x + dx, m.player.y + dy)) return;
    m.player = { x: m.player.x + dx, y: m.player.y + dy };
    if (m.pills.delete(`${m.player.x},${m.player.y}`)) m.collected++;
    m.turns++;
    if (m.turns % 3 === 0) {
      const choices = [
        [1, 0],
        [-1, 0],
        [0, 1],
        [0, -1],
      ].filter(([x, y]) => open(m.ghost.x + x, m.ghost.y + y));
      choices.sort(
        (a, b) =>
          Math.abs(m.ghost.x + a[0] - m.player.x) +
          Math.abs(m.ghost.y + a[1] - m.player.y) -
          Math.abs(m.ghost.x + b[0] - m.player.x) -
          Math.abs(m.ghost.y + b[1] - m.player.y),
      );
      const d = choices[0];
      if (d) m.ghost = { x: m.ghost.x + d[0], y: m.ghost.y + d[1] };
    }
    m.over =
      m.pills.size === 0 ||
      (m.player.x === m.ghost.x && m.player.y === m.ghost.y);
  }
  function draw(c, m) {
    c.fillStyle = "#faf6ef";
    c.fillRect(0, 0, 720, 500);
    c.fillStyle = "#086c94";
    c.font = "bold 24px sans-serif";
    drawBrand(c, 30, 10, 34);
    c.fillText("ХИМРАР · Лабиринт", 76, 37);
    const size = 36,
      ox = 90,
      oy = 58;
    // Join adjacent wall cells into cartons while preserving the collision grid.
    maze.forEach((row, y) => {
      for (let x = 0; x < row.length; ) {
        if (row[x] !== "#") {
          x++;
          continue;
        }
        const cells = row[x + 1] === "#" ? 2 : 1;
        drawCarton(c, ox + x * size, oy + y * size, cells);
        x += cells;
      }
    });
    maze.forEach((row, y) =>
      [...row].forEach((cell, x) => {
        if (cell !== "#" && m.pills.has(`${x},${y}`)) {
          c.save();
          c.translate(ox + x * size + 18, oy + y * size + 18);
          c.lineWidth = 2;
          if ((x + y) % 3 === 0) {
            c.fillStyle = "#31958f";
            c.strokeStyle = "#1d6867";
            c.beginPath();
            c.arc(0, 0, 7.5, 0, Math.PI * 2);
            c.fill();
            c.stroke();
            c.strokeStyle = "#d6f3e7";
            c.beginPath();
            c.moveTo(-4, 0);
            c.lineTo(4, 0);
            c.stroke();
          } else {
            c.rotate((x % 2 ? -1 : 1) * 0.55);
            c.beginPath();
            c.roundRect(-11, -5.5, 22, 11, 5.5);
            c.fillStyle = "#e5ad48";
            c.fill();
            c.save();
            c.clip();
            c.fillStyle = "#bc5377";
            c.fillRect(-11, -6, 11, 12);
            c.restore();
            c.strokeStyle = "#733d5b";
            c.stroke();
            c.beginPath();
            c.moveTo(0, -5);
            c.lineTo(0, 5);
            c.stroke();
          }
          c.restore();
        }
      }),
    );
    c.fillStyle = "#248bd0";
    c.beginPath();
    c.arc(
      ox + m.player.x * size + 18,
      oy + m.player.y * size + 18,
      13,
      0.35,
      Math.PI * 2 - 0.35,
    );
    c.lineTo(ox + m.player.x * size + 18, oy + m.player.y * size + 18);
    c.fill();
    c.fillStyle = "#d687a5";
    c.beginPath();
    c.arc(
      ox + m.ghost.x * size + 18,
      oy + m.ghost.y * size + 18,
      12,
      0,
      Math.PI * 2,
    );
    c.fill();
    c.fillStyle = "#163d53";
    c.font = "18px sans-serif";
    c.fillText(
      m.over
        ? m.pills.size
          ? "Попробуйте ещё раз"
          : "Все пилюли собраны!"
        : "Собирайте пилюли и избегайте розового шарика",
      55,
      480,
    );
  }
  const controls = () =>
    `<div class="maze-controls">${[
      [0, -1, "Вверх"],
      [-1, 0, "Влево"],
      [0, 1, "Вниз"],
      [1, 0, "Вправо"],
    ]
      .map(
        ([x, y, t]) =>
          `<button class="button" data-game-action="lab-step" data-dx="${x}" data-dy="${y}">${t}</button>`,
      )
      .join("")}</div>`;
  return { create, step, draw, controls, brandIcon };
})();
