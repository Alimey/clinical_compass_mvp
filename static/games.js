"use strict";

// Local play: no accounts, health records or network requests are created here.
const compassGames = (() => {
  const W = 720,
    H = 500;
  const definitions = {
    meadow: [
      "Полянка",
      "🌼",
      "Ведите корзинкой по полянке: собирайте цветы и грибы, обходя камни.",
    ],
    balls: [
      "Шарики",
      "🫧",
      "Коснитесь пустого места, чтобы добавить шарик. Старые шарики можно перетаскивать.",
    ],
    salon: [
      "Салон",
      "🎀",
      "Подстригайте волосы касаниями или кнопками, выбирайте цвет и помаду. Бантик можно передвигать.",
    ],
    cake: [
      "Торт",
      "🍰",
      "Выберите украшение и коснитесь торта. Крем и посыпку можно наносить движением пальца.",
    ],
    lava: [
      "Лавовая лампа",
      "🪔",
      "Выберите цвет и наблюдайте, как лава медленно поднимается и опускается.",
    ],
    sand: [
      "Сад камней",
      "🪨",
      "Рисуйте на песке граблями или палочкой. Последний штрих можно отменить.",
    ],
    jam: [
      "Варенье",
      "🍓",
      "Наполните банку и поставьте на полку кнопкой или перетаскиванием.",
    ],
    bubbles: ["Пузырьки", "🫧", "Касайтесь пузырьков."],
  };
  const colors = {
    brown: "#725043",
    black: "#343240",
    blond: "#dcb65e",
    rose: "#d97c9e",
    purple: "#9279bc",
    coral: "#e27e73",
    red: "#b94c64",
    mint: "#76bfa9",
    blue: "#669eb9",
    gold: "#dfbe78",
    cream: "#fff0da",
    white: "#fffaf4",
    orange: "#e9a058",
  };
  const colorNames = {
    brown: "каштановый",
    black: "тёмный",
    blond: "светлый",
    rose: "розовый",
    purple: "сиреневый",
    coral: "коралловый",
    red: "ягодный",
    mint: "мятный",
    blue: "голубой",
    gold: "золотистый",
    cream: "сливочный",
    white: "белый",
    orange: "абрикосовый",
  };
  const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));
  const random = (a, b) => a + Math.random() * (b - a);
  const distance = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
  const motion = matchMedia("(prefers-reduced-motion: reduce)");
  let owner = null,
    selected = "meadow",
    models = new Map(),
    stop = null,
    scrollToStage = false;
  const button = (action, title, extra = "") =>
    `<button type="button" class="button" data-game-action="${action}" ${extra}>${title}</button>`;
  function palette(action, keys, value, title) {
    return `<fieldset class="game-palette"><legend>${title}</legend>${keys.map((key) => `<button type="button" class="game-swatch" data-game-action="${action}" data-color="${key}" aria-label="${title}: ${colorNames[key]}" aria-pressed="${key === value}"><span data-game-tone="${key}" aria-hidden="true"></span></button>`).join("")}</fieldset>`;
  }
  function create(key) {
    const m = {
      t: 0,
      paused: motion.matches,
      pointer: null,
      cursor: { x: W / 2, y: H / 2 },
      keyboard: false,
    };
    if (key === "meadow") {
      Object.assign(m, {
        basket: { x: 360, y: 415 },
        path: [],
        collected: 0,
        rocks: [
          { x: 145, y: 150, r: 40 },
          { x: 505, y: 160, r: 46 },
          { x: 560, y: 355, r: 31 },
        ],
        items: [],
        regrow: [],
      });
      m.items.push({ x: 250, y: 320, kind: "flower", color: "rose" });
      while (m.items.length < 13) m.items.push(growItem(m));
    } else if (key === "balls") {
      Object.assign(m, { balls: [], gravity: true, nextId: 0, dragging: null });
      for (let i = 0; i < 17; i++)
        addBall(m, { x: 100 + (i % 6) * 103, y: 320 - Math.floor(i / 6) * 78 });
    } else if (key === "salon")
      Object.assign(m, {
        lengths: Array(25).fill(155),
        hair: "brown",
        lips: "rose",
        bow: null,
        dragging: false,
      });
    else if (key === "cake")
      Object.assign(m, {
        decorations: [],
        tool: "berry",
        color: "white",
        frosting: "rose",
        stroke: null,
      });
    else if (key === "lava") Object.assign(m, { color: "mint" });
    else if (key === "sand")
      Object.assign(m, { strokes: [], stroke: null, tool: "rake", width: 30 });
    else if (key === "jam")
      Object.assign(m, {
        color: "red",
        fill: 0,
        pouring: false,
        shelf: [],
        transfer: null,
        jar: { x: 360, y: 365 },
        dragging: false,
      });
    return m;
  }
  function model() {
    if (!models.has(selected)) models.set(selected, create(selected));
    return models.get(selected);
  }
  function controls(key, m) {
    if (key === "balls")
      return (
        button("add-ball", "Добавить шарик") +
        button(
          "gravity",
          `Невесомость: ${m.gravity ? "выкл" : "вкл"}`,
          `aria-pressed="${!m.gravity}"`,
        ) +
        button(
          "pause",
          m.paused ? "Запустить" : "Пауза",
          `aria-pressed="${m.paused}"`,
        ) +
        button("clear-balls", "Убрать все")
      );
    if (key === "salon")
      return (
        button("trim", "Подстричь") +
        button("grow", "Отрастить") +
        button(
          "bow",
          m.bow ? "Убрать бантик" : "Добавить бантик",
          `aria-pressed="${!!m.bow}"`,
        ) +
        palette(
          "hair",
          ["brown", "black", "blond", "rose", "purple"],
          m.hair,
          "Волосы",
        ) +
        palette("lips", ["rose", "coral", "red", "purple"], m.lips, "Помада")
      );
    if (key === "cake")
      return (
        `<div class="game-tools">${[
          ["berry", "Ягоды"],
          ["flower", "Цветы"],
          ["sprinkles", "Посыпка"],
          ["candle", "Свечи"],
          ["icing", "Крем"],
        ]
          .map(([key, title]) =>
            button(
              "tool",
              title,
              `data-tool="${key}" aria-pressed="${m.tool === key}"`,
            ),
          )
          .join("")}</div>` +
        palette(
          "color",
          ["rose", "white", "purple", "mint", "gold"],
          m.color,
          "Крем",
        ) +
        button("undo", "Отменить украшение")
      );
    if (key === "lava")
      return (
        palette(
          "color",
          ["mint", "rose", "purple", "blue", "orange"],
          m.color,
          "Цвет лавы",
        ) +
        button(
          "pause",
          m.paused ? "Запустить" : "Пауза",
          `aria-pressed="${m.paused}"`,
        )
      );
    if (key === "sand")
      return (
        button(
          "tool",
          "Грабли",
          `data-tool="rake" aria-pressed="${m.tool === "rake"}"`,
        ) +
        button(
          "tool",
          "Палочка",
          `data-tool="stick" aria-pressed="${m.tool === "stick"}"`,
        ) +
        `<label class="game-range">Ширина грабель<input type="range" min="15" max="55" value="${m.width}" data-game-range="width"></label>` +
        button("undo", "Отменить штрих")
      );
    if (key === "jam")
      return (
        palette(
          "color",
          ["red", "purple", "orange", "rose"],
          m.color,
          "Варенье",
        ) +
        button(
          "pour",
          m.pouring ? "Остановить" : "Наливать",
          `aria-pressed="${m.pouring}"`,
        ) +
        button(
          "shelf",
          "На полку",
          m.fill < 0.05 || m.shelf.length >= 6 || m.transfer ? "disabled" : "",
        ) +
        button("clear-shelf", "Освободить полку")
      );
    return "";
  }
  function page() {
    if (owner !== state.user?.id) reset();
    owner = state.user?.id;
    const m = model();
    const picker = `<div class="game-picker" id="game-picker" aria-label="Выбор игры">${Object.entries(
      definitions,
    )
      .map(
        ([key, [title, glyph]]) =>
          `<button type="button" class="game-choice" data-game-select="${key}" aria-pressed="${selected === key}"><span aria-hidden="true">${glyph}</span><strong>${title}</strong></button>`,
      )
      .join("")}</div>`;
    if (selected === "bubbles")
      return (
        picker +
        `<section class="card mini-game"><h2>Пузырьки</h2><div class="bubble-field">${Array.from({ length: 20 }, (_, i) => `<button class="bubble ${i % 3 === 0 ? "big" : ""}" data-ext="bubble" aria-label="Пузырёк ${i + 1}"></button>`).join("")}</div><p id="bubble-count" class="caption">Касаний: ${state.bubbles || 0}</p></section>`
      );
    return (
      picker +
      `<section class="card mini-game" id="mini-game-stage" data-mini-game="${selected}"><div class="card-heading"><h2>${definitions[selected][0]}</h2><div class="game-heading-actions">${button("choose", "Все игры")}${button("reset", "Начать заново")}</div></div><p id="game-instruction">${definitions[selected][2]}</p><div class="game-controls">${controls(selected, m)}</div><canvas id="game-canvas" width="1440" height="1000" tabindex="0" role="application" aria-label="${definitions[selected][0]}: игровое поле" aria-describedby="game-instruction game-keyboard"></canvas><div class="game-readout"><output id="game-status" aria-live="off"></output>${selected === "jam" ? '<progress id="jam-fill" max="100" value="0" aria-label="Наполнение банки"></progress>' : ""}</div><span id="game-announcement" class="visually-hidden" role="status"></span><details class="game-keyboard"><summary>Управление с клавиатуры</summary><p id="game-keyboard">Стрелки перемещают указатель. Enter или пробел — действие. Кнопки над полем доступны клавишей Tab.</p></details></section>`
    );
  }
  function reset() {
    stop?.();
    stop = null;
    models = new Map();
    owner = null;
    selected = "meadow";
    scrollToStage = false;
  }
  function round(c, x, y, w, h, r, fill, stroke) {
    c.beginPath();
    c.moveTo(x + r, y);
    c.arcTo(x + w, y, x + w, y + h, r);
    c.arcTo(x + w, y + h, x, y + h, r);
    c.arcTo(x, y + h, x, y, r);
    c.arcTo(x, y, x + w, y, r);
    c.closePath();
    if (fill) {
      c.fillStyle = fill;
      c.fill();
    }
    if (stroke) {
      c.strokeStyle = stroke;
      c.stroke();
    }
  }
  function ellipse(c, x, y, rx, ry, fill) {
    c.beginPath();
    c.ellipse(x, y, Math.max(0.1, rx), Math.max(0.1, ry), 0, 0, Math.PI * 2);
    c.fillStyle = fill;
    c.fill();
  }
  function line(c, points, color, width = 2) {
    if (!points.length) return;
    c.beginPath();
    points.forEach((p, i) => (i ? c.lineTo(p.x, p.y) : c.moveTo(p.x, p.y)));
    if (points.length === 1) c.lineTo(points[0].x + 0.1, points[0].y);
    c.strokeStyle = color;
    c.lineWidth = width;
    c.lineJoin = "round";
    c.lineCap = "round";
    c.stroke();
  }
  function stone(c, r) {
    ellipse(c, r.x + 3, r.y + r.r * 0.65, r.r, 9, "#40544820");
    c.beginPath();
    c.moveTo(r.x - r.r, r.y + r.r * 0.4);
    c.lineTo(r.x - r.r * 0.7, r.y - r.r * 0.55);
    c.lineTo(r.x + r.r * 0.05, r.y - r.r);
    c.lineTo(r.x + r.r * 0.8, r.y - r.r * 0.5);
    c.lineTo(r.x + r.r, r.y + r.r * 0.4);
    c.lineTo(r.x + r.r * 0.2, r.y + r.r * 0.8);
    c.closePath();
    c.fillStyle = "#b7bdbe";
    c.fill();
    c.beginPath();
    c.moveTo(r.x - r.r * 0.7, r.y - r.r * 0.55);
    c.lineTo(r.x, r.y - r.r * 0.1);
    c.lineTo(r.x + r.r * 0.05, r.y - r.r);
    c.closePath();
    c.fillStyle = "#dce0df";
    c.fill();
    c.beginPath();
    c.moveTo(r.x, r.y - r.r * 0.1);
    c.lineTo(r.x + r.r * 0.8, r.y - r.r * 0.5);
    c.lineTo(r.x + r.r, r.y + r.r * 0.4);
    c.lineTo(r.x - r.r * 0.1, r.y + r.r * 0.5);
    c.closePath();
    c.fillStyle = "#cbd0d0";
    c.fill();
  }
  function blossom(c, x, y, r, color) {
    for (let i = 0; i < 5; i++) {
      const a = (i * Math.PI * 2) / 5;
      c.save();
      c.translate(x + Math.cos(a) * r * 0.53, y + Math.sin(a) * r * 0.53);
      c.rotate(a);
      ellipse(c, 0, 0, r * 0.7, r * 0.45, color);
      c.restore();
    }
    ellipse(c, x, y, r * 0.27, r * 0.27, "#f9d882");
  }
  function basket(c, x, y) {
    ellipse(c, x, y + 22, 35, 8, "#72875925");
    c.beginPath();
    c.arc(x, y - 14, 23, Math.PI, 0);
    c.strokeStyle = "#be8b50";
    c.lineWidth = 7;
    c.stroke();
    c.beginPath();
    c.moveTo(x - 35, y - 10);
    c.lineTo(x + 35, y - 10);
    c.lineTo(x + 25, y + 29);
    c.lineTo(x - 25, y + 29);
    c.closePath();
    c.fillStyle = "#c99759";
    c.fill();
    for (let i = -2; i <= 2; i++)
      line(
        c,
        [
          { x: x + i * 10, y: y - 6 },
          { x: x + i * 8, y: y + 25 },
        ],
        "#ae7b43",
        2,
      );
    for (let i = 0; i < 4; i++)
      line(
        c,
        [
          { x: x - 30 + i * 2, y: y + i * 8 },
          { x: x + 30 - i * 2, y: y + i * 8 },
        ],
        "#e9c38b",
        3,
      );
  }
  function growItem(m) {
    for (let n = 0; n < 100; n++) {
      const p = {
        x: random(45, 675),
        y: random(60, 430),
        kind: Math.random() < 0.38 ? "mushroom" : "flower",
        color: ["rose", "gold", "purple"][Math.floor(Math.random() * 3)],
      };
      if (
        m.rocks.every((r) => distance(p, r) > r.r + 38) &&
        m.items.every((r) => distance(p, r) > 48)
      )
        return p;
    }
    return { x: 250, y: 320, kind: "flower", color: "rose" };
  }
  function free(m, p) {
    return (
      p.x >= 28 &&
      p.x <= W - 28 &&
      p.y >= 32 &&
      p.y <= H - 30 &&
      m.rocks.every((r) => distance(p, r) > r.r + 27)
    );
  }
  function clearSegment(m, a, b) {
    const steps = Math.max(1, Math.ceil(distance(a, b) / 10));
    for (let i = 1; i <= steps; i++)
      if (
        !free(m, {
          x: a.x + ((b.x - a.x) * i) / steps,
          y: a.y + ((b.y - a.y) * i) / steps,
        })
      )
        return false;
    return true;
  }
  function route(m, target) {
    target = { x: clamp(target.x, 30, 690), y: clamp(target.y, 34, 468) };
    if (clearSegment(m, m.basket, target)) {
      m.path = [target];
      return;
    }
    const step = 24,
      nx = 29,
      ny = 20,
      point = (id) => ({
        x: 24 + (id % nx) * step,
        y: 24 + Math.floor(id / nx) * step,
      });
    const grid = Array.from({ length: nx * ny }, (_, i) => free(m, point(i)));
    const nearest = (p) => {
      let best = -1,
        d = Infinity;
      grid.forEach((ok, i) => {
        const v = distance(p, point(i));
        if (ok && v < d) {
          d = v;
          best = i;
        }
      });
      return best;
    };
    const start = nearest(m.basket),
      end = nearest(target),
      queue = [start],
      prev = new Map([[start, null]]);
    for (let i = 0; i < queue.length && !prev.has(end); i++)
      for (const [dx, dy] of [
        [1, 0],
        [-1, 0],
        [0, 1],
        [0, -1],
        [1, 1],
        [-1, 1],
        [1, -1],
        [-1, -1],
      ]) {
        const x = (queue[i] % nx) + dx,
          y = Math.floor(queue[i] / nx) + dy,
          id = y * nx + x;
        if (
          x < 0 ||
          x >= nx ||
          y < 0 ||
          y >= ny ||
          !grid[id] ||
          prev.has(id) ||
          !clearSegment(m, point(queue[i]), point(id))
        )
          continue;
        prev.set(id, queue[i]);
        queue.push(id);
      }
    if (!prev.has(end)) return;
    const path = [];
    for (let id = end; id !== null; id = prev.get(id)) path.unshift(point(id));
    if (free(m, target)) path.push(target);
    const smooth = [];
    let from = m.basket;
    for (let i = 0; i < path.length; ) {
      let j = path.length - 1;
      while (j > i && !clearSegment(m, from, path[j])) j--;
      smooth.push(path[j]);
      from = path[j];
      i = j + 1;
    }
    m.path = smooth;
  }
  function addBall(m, p) {
    if (m.balls.length >= 48) return false;
    const r = random(20, 42);
    m.balls.push({
      id: ++m.nextId,
      x: clamp(p.x, r + 12, W - r - 12),
      y: clamp(p.y, r + 12, H - r - 12),
      r,
      vx: random(-30, 30),
      vy: 0,
      color: ["#a8c5b8", "#d6a5a0", "#d9c68f", "#6596ab"][m.nextId % 4],
    });
    return true;
  }
  function updateBalls(m, dt) {
    const steps = Math.ceil(dt / 0.008),
      step = dt / steps;
    for (let n = 0; n < steps; n++) {
      for (const b of m.balls) {
        if (b.id === m.dragging) continue;
        b.vy += (m.gravity ? 650 : 0) * step;
        b.vx *= Math.exp(-0.12 * step);
        b.vy *= Math.exp(-0.12 * step);
        b.x += b.vx * step;
        b.y += b.vy * step;
      }
      for (let pass = 0; pass < 2; pass++) {
        for (let i = 0; i < m.balls.length; i++)
          for (let j = i + 1; j < m.balls.length; j++) {
            const a = m.balls[i],
              b = m.balls[j],
              dx = b.x - a.x,
              dy = b.y - a.y,
              d = Math.hypot(dx, dy),
              overlap = a.r + b.r - d;
            if (overlap <= 0) continue;
            const nx = d ? dx / d : 1,
              ny = d ? dy / d : 0,
              ia = a.id === m.dragging ? 0 : 1 / (a.r * a.r),
              ib = b.id === m.dragging ? 0 : 1 / (b.r * b.r),
              sum = ia + ib;
            if (!sum) continue;
            a.x -= (nx * overlap * ia) / sum;
            a.y -= (ny * overlap * ia) / sum;
            b.x += (nx * overlap * ib) / sum;
            b.y += (ny * overlap * ib) / sum;
            const velocity = (b.vx - a.vx) * nx + (b.vy - a.vy) * ny;
            if (velocity < 0) {
              const impulse = (-1.65 * velocity) / sum;
              a.vx -= impulse * ia * nx;
              a.vy -= impulse * ia * ny;
              b.vx += impulse * ib * nx;
              b.vy += impulse * ib * ny;
            }
          }
        for (const b of m.balls) {
          if (b.x < 12 + b.r) {
            b.x = 12 + b.r;
            b.vx = Math.abs(b.vx) * 0.7;
          }
          if (b.x > W - 12 - b.r) {
            b.x = W - 12 - b.r;
            b.vx = -Math.abs(b.vx) * 0.7;
          }
          if (b.y < 12 + b.r) {
            b.y = 12 + b.r;
            b.vy = Math.abs(b.vy) * 0.7;
          }
          if (b.y > H - 12 - b.r) {
            b.y = H - 12 - b.r;
            b.vy = -Math.abs(b.vy) * 0.55;
            b.vx *= 0.98;
            if (Math.abs(b.vy) < 12) b.vy = 0;
          }
        }
      }
    }
  }
  function shelfJar(m) {
    if (m.transfer || m.fill < 0.05 || m.shelf.length >= 6) return false;
    m.pouring = false;
    m.dragging = false;
    m.transfer = {
      t: 0,
      from: { ...m.jar },
      to: { x: 135 + m.shelf.length * 90, y: 116 },
      fill: m.fill,
      color: m.color,
    };
    return true;
  }
  function tick(key, m, dt) {
    m.t += dt;
    if (key === "meadow") {
      if (m.path.length) {
        const goal = m.path[0],
          d = distance(m.basket, goal),
          step = Math.min(d, 235 * dt);
        if (d < 2) m.path.shift();
        else {
          m.basket.x += ((goal.x - m.basket.x) / d) * step;
          m.basket.y += ((goal.y - m.basket.y) / d) * step;
        }
      }
      for (let i = m.items.length - 1; i >= 0; i--)
        if (distance(m.items[i], m.basket) < 33) {
          m.items.splice(i, 1);
          m.collected++;
          m.regrow.push(m.t + 0.8);
        }
      while (m.regrow.length && m.regrow[0] <= m.t) {
        m.regrow.shift();
        m.items.push(growItem(m));
      }
    } else if (key === "balls" && !m.paused) updateBalls(m, dt);
    else if (key === "jam") {
      if (m.pouring && !m.transfer && !m.dragging)
        m.fill = Math.min(1, m.fill + dt * 0.28);
      if (m.fill >= 1) m.pouring = false;
      if (m.transfer) {
        m.transfer.t += dt;
        const progress = clamp(m.transfer.t / 0.6, 0, 1),
          ease = 1 - (1 - progress) ** 3;
        m.jar = {
          x: m.transfer.from.x + (m.transfer.to.x - m.transfer.from.x) * ease,
          y: m.transfer.from.y + (m.transfer.to.y - m.transfer.from.y) * ease,
        };
        if (progress >= 1) {
          m.shelf.push({ fill: m.transfer.fill, color: m.transfer.color });
          m.transfer = null;
          m.fill = 0;
          m.jar = { x: 360, y: 365 };
        }
      }
    }
  }
  function drawMeadow(c, m) {
    c.fillStyle = "#d6e5c5";
    c.fillRect(0, 0, W, H);
    for (let i = 0; i < 100; i++) {
      const x = (i * 137) % W,
        y = (i * 71) % H;
      line(
        c,
        [
          { x, y },
          { x: x - 3, y: y - 8 },
          { x: x + 3, y: y - 3 },
        ],
        "#b4ce9e",
        2,
      );
    }
    m.rocks.forEach((r) => stone(c, r));
    for (const p of m.items) {
      line(
        c,
        [
          { x: p.x, y: p.y + 18 },
          { x: p.x, y: p.y },
        ],
        "#6b9b62",
        4,
      );
      ellipse(c, p.x + 7, p.y + 12, 8, 3, "#86ad72");
      if (p.kind === "flower") blossom(c, p.x, p.y, 15, colors[p.color]);
      else {
        round(c, p.x - 5, p.y, 10, 19, 4, "#fff2d9");
        c.beginPath();
        c.ellipse(p.x, p.y, 21, 17, 0, Math.PI, 0);
        c.closePath();
        c.fillStyle = "#dd7e82";
        c.fill();
        ellipse(c, p.x - 8, p.y - 8, 4, 4, "#fff5e4");
        ellipse(c, p.x + 9, p.y - 6, 3, 3, "#fff5e4");
      }
    }
    basket(c, m.basket.x, m.basket.y);
  }
  function drawBalls(c, m) {
    const g = c.createLinearGradient(0, 0, 0, H);
    g.addColorStop(0, "#edf4f4");
    g.addColorStop(1, "#e3edeb");
    round(c, 6, 6, W - 12, H - 12, 28, g, "#bdcecc");
    for (const b of m.balls) {
      ellipse(c, b.x + 2, b.y + 4, b.r, b.r, "#445b6010");
      ellipse(c, b.x, b.y, b.r, b.r, b.color);
      ellipse(
        c,
        b.x - b.r * 0.3,
        b.y - b.r * 0.33,
        b.r * 0.28,
        b.r * 0.28,
        "#ffffff55",
      );
    }
  }
  function hairRoot(i) {
    const a = Math.PI + (i / 24) * Math.PI;
    return { x: 360 + Math.cos(a) * 100, y: 210 + Math.sin(a) * 100 };
  }
  function drawSalon(c, m) {
    c.fillStyle = "#eee6ef";
    c.fillRect(0, 0, W, H);
    round(c, 180, 30, 360, 430, 150, "#fff9f4", "#d6c4d3");
    ellipse(c, 360, 460, 155, 24, "#ddd0dc");
    round(c, 240, 370, 240, 115, 65, "#79a7ba");
    round(c, 334, 297, 52, 93, 20, "#e8bda4");
    m.lengths.forEach((len, i) => {
      const r = hairRoot(i),
        side = (i - 12) / 12;
      c.beginPath();
      c.moveTo(r.x, r.y);
      c.bezierCurveTo(
        r.x + side * 12,
        r.y + 50,
        r.x + side * 17,
        r.y + len * 0.7,
        r.x + side * 20,
        r.y + len,
      );
      c.strokeStyle = colors[m.hair];
      c.lineWidth = 17;
      c.lineCap = "round";
      c.stroke();
    });
    ellipse(c, 277, 235, 13, 23, "#f2cbb5");
    ellipse(c, 443, 235, 13, 23, "#f2cbb5");
    ellipse(c, 360, 229, 80, 102, "#f6d6c0");
    c.beginPath();
    c.moveTo(278, 194);
    c.bezierCurveTo(285, 70, 444, 77, 445, 196);
    c.bezierCurveTo(410, 174, 388, 157, 375, 137);
    c.bezierCurveTo(345, 182, 307, 193, 278, 194);
    c.fillStyle = colors[m.hair];
    c.fill();
    for (const x of [329, 391]) {
      c.beginPath();
      c.arc(x, 229, 10, 0.1, Math.PI - 0.1);
      c.strokeStyle = "#66534f";
      c.lineWidth = 4;
      c.stroke();
    }
    ellipse(c, 316, 257, 13, 7, "#e8a89955");
    ellipse(c, 404, 257, 13, 7, "#e8a89955");
    line(
      c,
      [
        { x: 357, y: 242 },
        { x: 352, y: 261 },
        { x: 362, y: 262 },
      ],
      "#d4a58f",
      2,
    );
    c.beginPath();
    c.moveTo(341, 283);
    c.quadraticCurveTo(353, 275, 360, 281);
    c.quadraticCurveTo(367, 275, 379, 283);
    c.quadraticCurveTo(360, 304, 341, 283);
    c.fillStyle = colors[m.lips];
    c.fill();
    if (m.bow) {
      c.save();
      c.translate(m.bow.x, m.bow.y);
      c.beginPath();
      c.moveTo(0, 0);
      c.bezierCurveTo(-52, -48, -53, 32, 0, 0);
      c.bezierCurveTo(52, -48, 53, 32, 0, 0);
      c.fillStyle = "#df86a5";
      c.fill();
      ellipse(c, 0, 0, 9, 10, "#c7678c");
      c.restore();
    }
  }
  function cakeContains(p) {
    return p.x > 145 && p.x < 575 && p.y > 195 && p.y < 425;
  }
  function drawCake(c, m) {
    c.fillStyle = "#edf2f5";
    c.fillRect(0, 0, W, H);
    ellipse(c, 360, 440, 260, 29, "#b8d1df");
    ellipse(c, 360, 432, 250, 24, "#fff9f2");
    round(c, 155, 288, 410, 128, 28, "#e6bea4");
    round(c, 155, 284, 410, 82, 28, colors[m.frosting]);
    ellipse(c, 360, 285, 205, 34, "#fff4e6");
    round(c, 218, 205, 284, 96, 22, "#edcab4");
    round(c, 218, 201, 284, 63, 22, colors[m.frosting]);
    ellipse(c, 360, 204, 142, 27, "#fff4e6");
    for (let x = 175; x < 560; x += 28)
      ellipse(c, x, 353 + Math.sin(x) * 5, 12, 13, colors[m.frosting]);
    for (const d of m.decorations) {
      if (d.tool === "icing") {
        line(c, d.points, d.color, 12);
        continue;
      }
      if (d.tool === "sprinkles") {
        for (const p of d.points)
          line(
            c,
            [
              { x: p.x - 3, y: p.y - 3 },
              { x: p.x + 4, y: p.y + 4 },
            ],
            p.color,
            4,
          );
        continue;
      }
      if (d.tool === "berry") {
        ellipse(c, d.x, d.y, 11, 14, "#cc637e");
        for (let i = 0; i < 5; i++)
          ellipse(c, d.x + (i % 2 ? 4 : -4), d.y - 7 + i * 3, 1, 1, "#ffe6a3");
        line(
          c,
          [
            { x: d.x - 7, y: d.y - 13 },
            { x: d.x, y: d.y - 18 },
            { x: d.x + 7, y: d.y - 13 },
          ],
          "#78a87d",
          4,
        );
      }
      if (d.tool === "flower") blossom(c, d.x, d.y, 16, d.color);
      if (d.tool === "candle") {
        round(c, d.x - 6, d.y - 42, 12, 44, 4, d.color);
        ellipse(c, d.x, d.y - 52, 5, 10, "#efbc61");
      }
    }
  }
  function drawLava(c, m) {
    const bg = c.createRadialGradient(360, 250, 40, 360, 250, 480);
    bg.addColorStop(0, "#27465a");
    bg.addColorStop(1, "#122331");
    c.fillStyle = bg;
    c.fillRect(0, 0, W, H);
    const base = c.createLinearGradient(220, 0, 500, 0);
    base.addColorStop(0, "#8192a3");
    base.addColorStop(0.5, "#d1dae0");
    base.addColorStop(1, "#697b8e");
    round(c, 232, 426, 256, 55, 17, base);
    round(c, 258, 22, 204, 37, 15, base);
    c.save();
    round(c, 222, 55, 276, 378, 80, "#193241");
    c.clip();
    c.shadowBlur = 25;
    c.shadowColor = colors[m.color];
    ellipse(c, 360, 436, 130, 38, colors[m.color]);
    ellipse(c, 360, 52, 100, 24, colors[m.color]);
    for (let i = 0; i < 7; i++) {
      const t = m.t * 0.16 + i * 1.9,
        x = 360 + 70 * Math.sin(t * 0.71 + i),
        y = 245 + 146 * Math.sin(t),
        r = 26 + (i % 3) * 10;
      c.save();
      c.translate(x, y);
      c.rotate(Math.sin(t) * 0.24);
      ellipse(
        c,
        0,
        0,
        r * (1 + Math.sin(t) * 0.12),
        r * (1.2 - Math.sin(t) * 0.15),
        colors[m.color],
      );
      c.restore();
    }
    c.shadowBlur = 0;
    const shine = c.createLinearGradient(240, 0, 465, 0);
    shine.addColorStop(0, "#ffffff00");
    shine.addColorStop(0.15, "#ffffff2b");
    shine.addColorStop(0.35, "#ffffff00");
    shine.addColorStop(1, "#ffffff0d");
    c.fillStyle = shine;
    c.fillRect(222, 55, 276, 378);
    c.restore();
  }
  function drawSand(c, m) {
    const g = c.createLinearGradient(0, 0, W, H);
    g.addColorStop(0, "#ecddba");
    g.addColorStop(1, "#d8c197");
    c.fillStyle = g;
    c.fillRect(0, 0, W, H);
    c.fillStyle = "#a9906c22";
    for (let i = 0; i < 950; i++)
      c.fillRect((i * 137.7) % W, (i * 89.3) % H, 1.5, 1.5);
    for (const stroke of m.strokes) {
      const teeth = stroke.tool === "rake" ? 5 : 1;
      for (let k = 0; k < teeth; k++) {
        const offset = ((k - (teeth - 1) / 2) * stroke.width) / 4,
          pts = stroke.points.map((p, i, arr) => {
            const a = arr[Math.max(0, i - 1)],
              b = arr[Math.min(arr.length - 1, i + 1)],
              d = Math.hypot(b.x - a.x, b.y - a.y) || 1;
            return {
              x: p.x - ((b.y - a.y) / d) * offset,
              y: p.y + ((b.x - a.x) / d) * offset,
            };
          });
        line(c, pts, "#b69a7377", stroke.tool === "rake" ? 3 : 4);
        line(
          c,
          pts.map((p) => ({ x: p.x + 1, y: p.y + 2 })),
          "#fff3d080",
          1.5,
        );
      }
    }
    [
      { x: 100, y: 395, r: 43 },
      { x: 155, y: 421, r: 24 },
      { x: 609, y: 103, r: 37 },
    ].forEach((r) => stone(c, r));
  }
  function jar(c, x, y, fill, color, scale = 1, lid = false) {
    c.save();
    c.translate(x, y);
    c.scale(scale, scale);
    round(c, -42, -58, 84, 112, 13, "#ffffff70", "#a2bdc7");
    c.save();
    round(c, -37, -52, 74, 100, 9);
    c.clip();
    round(c, -37, 48 - fill * 100, 74, fill * 100 + 3, 6, colors[color]);
    c.fillStyle = "#ffffff25";
    c.fillRect(-29, -48, 7, 94);
    c.restore();
    round(c, -43, -64, 86, 13, 4, lid ? "#b6ab83" : "#c7d5d7");
    round(c, -25, -3, 50, 31, 7, "#fff6e9cc");
    blossom(c, 0, 12, 9, colors[color]);
    c.restore();
  }
  function drawJam(c, m) {
    c.fillStyle = "#f5eee6";
    c.fillRect(0, 0, W, H);
    round(c, 65, 151, 590, 14, 6, "#c39e75");
    line(
      c,
      [
        { x: 95, y: 165 },
        { x: 95, y: 193 },
      ],
      "#b68f67",
      8,
    );
    line(
      c,
      [
        { x: 625, y: 165 },
        { x: 625, y: 193 },
      ],
      "#b68f67",
      8,
    );
    m.shelf.forEach((j, i) =>
      jar(c, 135 + i * 90, 116, j.fill, j.color, 0.58, true),
    );
    c.fillStyle = "#ead6be";
    c.fillRect(0, 428, W, 72);
    line(
      c,
      [
        { x: 0, y: 428 },
        { x: W, y: 428 },
      ],
      "#cfb390",
      4,
    );
    ellipse(c, 360, 192, 73, 15, "#c1d4d9");
    round(c, 295, 185, 130, 57, 20, "#9db8c4");
    ellipse(c, 360, 187, 59, 10, colors[m.color]);
    if (m.pouring && !m.dragging && !m.transfer)
      line(
        c,
        [
          { x: 360, y: 240 },
          { x: 360 + Math.sin(m.t * 12) * 2, y: m.jar.y - 54 },
        ],
        colors[m.color],
        9,
      );
    jar(
      c,
      m.jar.x,
      m.jar.y,
      m.fill,
      m.transfer?.color || m.color,
      m.transfer ? 1 - 0.42 * clamp(m.transfer.t / 0.6, 0, 1) : 1,
      !!m.transfer,
    );
    ellipse(c, 132, 423, 60, 11, "#cfbda4");
    for (let i = 0; i < 9; i++)
      ellipse(
        c,
        100 + (i % 4) * 20,
        403 - Math.floor(i / 4) * 14,
        13,
        15,
        colors[m.color],
      );
  }
  const drawFunctions = {
    meadow: drawMeadow,
    balls: drawBalls,
    salon: drawSalon,
    cake: drawCake,
    lava: drawLava,
    sand: drawSand,
    jam: drawJam,
  };
  function readout(key, m) {
    if (key === "meadow") return `Собрано: ${m.collected}`;
    if (key === "balls") return `Шариков: ${m.balls.length} из 48`;
    if (key === "salon")
      return `Длина волос: ${Math.round(m.lengths.reduce((a, b) => a + b, 0) / m.lengths.length)}`;
    if (key === "cake") return `Украшений: ${m.decorations.length}`;
    if (key === "lava")
      return m.paused ? "Лампа на паузе" : "Лава движется медленно";
    if (key === "sand") return `Штрихов: ${m.strokes.length}`;
    if (key === "jam")
      return `Банка: ${Math.round(m.fill * 100)}% · На полке: ${m.shelf.length} из 6`;
    return "";
  }
  function mount() {
    stop?.();
    stop = null;
    const root = document.querySelector("#mini-game-stage"),
      canvas = root?.querySelector("canvas");
    if (!canvas || state.user?.role !== "patient") return;
    const key = selected,
      m = model(),
      c = canvas.getContext("2d"),
      controller = new AbortController(),
      signal = controller.signal;
    if (!c) return;
    c.setTransform(2, 0, 0, 2, 0, 0);
    let frame = 0,
      last = 0,
      activePointer = null,
      previousPoint = null;
    const announce = (text) => {
      root.querySelector("#game-announcement").textContent = text;
    };
    function refresh() {
      const output = root.querySelector("#game-status"),
        text = readout(key, m);
      if (output.textContent !== text) output.textContent = text;
      if (key === "jam") {
        root.querySelector("#jam-fill").value = Math.round(m.fill * 100);
        const p = root.querySelector('[data-game-action="pour"]'),
          s = root.querySelector('[data-game-action="shelf"]');
        p.textContent = m.pouring ? "Остановить" : "Наливать";
        p.setAttribute("aria-pressed", m.pouring);
        p.disabled = !!m.transfer || m.fill >= 1;
        s.disabled = m.fill < 0.05 || m.shelf.length >= 6 || !!m.transfer;
      }
    }
    function draw() {
      c.clearRect(0, 0, W, H);
      drawFunctions[key](c, m);
      if (m.keyboard) {
        c.beginPath();
        c.arc(m.cursor.x, m.cursor.y, 12, 0, Math.PI * 2);
        c.setLineDash([3, 4]);
        c.lineWidth = 2;
        c.strokeStyle = "#195f83";
        c.stroke();
        c.setLineDash([]);
      }
      refresh();
    }
    function wantsMotion() {
      if (key === "balls" || key === "lava") return !m.paused;
      if (key === "meadow") return m.path.length > 0 || m.regrow.length > 0;
      if (key === "jam") return m.pouring || !!m.transfer;
      return false;
    }
    function run(now) {
      frame = 0;
      if (!canvas.isConnected || document.hidden) {
        frame = 0;
        last = 0;
        return;
      }
      const dt = last ? Math.min(0.04, (now - last) / 1000) : 0;
      last = now;
      if (!(key === "lava" && m.paused)) tick(key, m, dt);
      draw();
      if (wantsMotion()) frame = requestAnimationFrame(run);
      else last = 0;
    }
    function start() {
      if (wantsMotion() && !frame && !document.hidden) {
        last = 0;
        frame = requestAnimationFrame(run);
      }
    }
    function point(event) {
      const r = canvas.getBoundingClientRect();
      return {
        x: clamp(((event.clientX - r.left) / r.width) * W, 0, W),
        y: clamp(((event.clientY - r.top) / r.height) * H, 0, H),
      };
    }
    function trimAt(p) {
      for (let i = 0; i < 25; i++) {
        const r = hairRoot(i);
        if (
          Math.abs(p.x - r.x) < 30 &&
          p.y >= r.y &&
          (Math.abs(p.x - 360) > 58 || p.y < 178)
        )
          m.lengths[i] = clamp(p.y - r.y, 20, m.lengths[i]);
      }
    }
    function decorate(p, begin = false) {
      if (!cakeContains(p)) return;
      if (begin) {
        const d = {
          tool: m.tool,
          x: p.x,
          y: p.y,
          color: colors[m.color],
          points: [],
        };
        m.decorations.push(d);
        if (m.decorations.length > 180) m.decorations.shift();
        m.stroke = d;
      }
      if (!m.stroke) return;
      if (m.stroke.tool === "icing" && m.stroke.points.length < 700)
        m.stroke.points.push({ ...p });
      if (m.stroke.tool === "sprinkles" && m.stroke.points.length < 700)
        for (let i = 0; i < 3; i++)
          m.stroke.points.push({
            x: p.x + random(-10, 10),
            y: p.y + random(-10, 10),
            color: ["#e099a7", "#82b9ae", "#e1bd6b", "#ad92c5"][
              Math.floor(Math.random() * 4)
            ],
          });
    }
    function begin(p) {
      m.cursor = p;
      if (key === "meadow") route(m, p);
      if (key === "balls") {
        let b = [...m.balls].reverse().find((b) => distance(b, p) <= b.r + 4);
        if (!b && addBall(m, p)) b = m.balls.at(-1);
        if (b) {
          m.dragging = b.id;
          b.vx = 0;
          b.vy = 0;
        }
      }
      if (key === "salon") {
        if (m.bow && distance(m.bow, p) < 40) m.dragging = true;
        else trimAt(p);
      }
      if (key === "cake") decorate(p, true);
      if (key === "sand") {
        m.stroke = { tool: m.tool, width: m.width, points: [{ ...p }] };
        m.strokes.push(m.stroke);
        if (m.strokes.length > 60) m.strokes.shift();
      }
      if (key === "jam" && !m.transfer) {
        if (
          m.fill > 0.05 &&
          Math.abs(p.x - m.jar.x) < 65 &&
          Math.abs(p.y - m.jar.y) < 75
        ) {
          m.dragging = true;
          m.pouring = false;
        } else if (Math.abs(p.x - 360) < 90 && p.y > 200)
          m.pouring = !m.pouring && m.fill < 1;
      }
      draw();
      start();
    }
    function move(p, pressed) {
      m.cursor = p;
      if (
        key === "meadow" &&
        (!previousPoint || distance(previousPoint, p) > 10)
      )
        route(m, p);
      if (key === "balls" && m.dragging) {
        const b = m.balls.find((b) => b.id === m.dragging);
        if (b) {
          if (previousPoint) {
            b.vx = clamp((p.x - previousPoint.x) * 30, -700, 700);
            b.vy = clamp((p.y - previousPoint.y) * 30, -700, 700);
          }
          b.x = clamp(p.x, b.r + 12, W - b.r - 12);
          b.y = clamp(p.y, b.r + 12, H - b.r - 12);
        }
      }
      if (pressed && key === "salon") {
        if (m.dragging)
          m.bow = { x: clamp(p.x, 230, 490), y: clamp(p.y, 80, 370) };
        else trimAt(p);
      }
      if (
        pressed &&
        key === "cake" &&
        (!previousPoint || distance(previousPoint, p) > 5)
      )
        decorate(p);
      if (
        pressed &&
        key === "sand" &&
        m.stroke &&
        m.stroke.points.length < 1200 &&
        (!previousPoint || distance(previousPoint, p) > 2)
      )
        m.stroke.points.push({ ...p });
      if (key === "jam" && m.dragging)
        m.jar = { x: clamp(p.x, 80, 640), y: clamp(p.y, 65, 410) };
      previousPoint = p;
      draw();
      start();
    }
    function end() {
      if (key === "jam" && m.dragging) {
        if (m.jar.y < 205 && !shelfJar(m)) m.jar = { x: 360, y: 365 };
        else if (m.jar.y >= 205) m.jar = { x: 360, y: 365 };
      }
      m.dragging = key === "balls" ? null : false;
      m.stroke = null;
      activePointer = null;
      previousPoint = null;
      draw();
      start();
    }
    canvas.addEventListener(
      "pointerdown",
      (event) => {
        if (activePointer !== null || event.button > 0) return;
        event.preventDefault();
        canvas.focus({ preventScroll: true });
        activePointer = event.pointerId;
        canvas.setPointerCapture(event.pointerId);
        m.keyboard = false;
        begin(point(event));
        previousPoint = point(event);
      },
      { signal },
    );
    canvas.addEventListener(
      "pointermove",
      (event) => {
        if (activePointer !== null && activePointer !== event.pointerId) return;
        if (activePointer !== null || key === "meadow") {
          event.preventDefault();
          move(point(event), activePointer !== null);
        }
      },
      { signal },
    );
    for (const event of ["pointerup", "pointercancel", "lostpointercapture"])
      canvas.addEventListener(
        event,
        (event) => {
          if (event.pointerId !== activePointer) return;
          if (
            event.type === "lostpointercapture" &&
            canvas.hasPointerCapture(event.pointerId)
          )
            return;
          end();
        },
        { signal },
      );
    canvas.addEventListener(
      "keydown",
      (event) => {
        if (
          ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(
            event.key,
          )
        ) {
          event.preventDefault();
          m.keyboard = true;
          const x =
              event.key === "ArrowLeft"
                ? -25
                : event.key === "ArrowRight"
                  ? 25
                  : 0,
            y =
              event.key === "ArrowUp"
                ? -25
                : event.key === "ArrowDown"
                  ? 25
                  : 0;
          m.cursor = {
            x: clamp(m.cursor.x + x, 20, 700),
            y: clamp(m.cursor.y + y, 20, 480),
          };
          if (key === "meadow") route(m, m.cursor);
          draw();
          start();
        }
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          begin({ ...m.cursor });
          end();
        }
      },
      { signal },
    );
    root.addEventListener(
      "click",
      (event) => {
        const b = event.target.closest("[data-game-action]");
        if (!b || b.disabled) return;
        const action = b.dataset.gameAction;
        if (action === "choose") {
          document
            .querySelector("#game-picker")
            .scrollIntoView({ block: "start" });
          return;
        }
        if (action === "reset") {
          models.set(key, create(key));
          render();
          return;
        }
        if (action === "add-ball") addBall(m, { x: random(100, 620), y: 80 });
        if (action === "clear-balls") {
          m.balls = [];
          m.dragging = null;
        }
        if (action === "gravity") {
          m.gravity = !m.gravity;
          if (!m.gravity)
            for (const ball of m.balls) {
              ball.vx = random(-80, 80);
              ball.vy = random(-90, 50);
            }
          b.textContent = `Невесомость: ${m.gravity ? "выкл" : "вкл"}`;
          b.setAttribute("aria-pressed", !m.gravity);
        }
        if (action === "pause") {
          m.paused = !m.paused;
          if (m.paused) {
            cancelAnimationFrame(frame);
            frame = 0;
            last = 0;
          }
          b.textContent = m.paused ? "Продолжить" : "Пауза";
          b.setAttribute("aria-pressed", m.paused);
        }
        if (action === "trim")
          m.lengths = m.lengths.map((v) => Math.max(20, v - 20));
        if (action === "grow")
          m.lengths = m.lengths.map((v) => Math.min(225, v + 22));
        if (action === "bow") {
          m.bow = m.bow ? null : { x: 422, y: 148 };
          b.textContent = m.bow ? "Убрать бантик" : "Добавить бантик";
          b.setAttribute("aria-pressed", !!m.bow);
        }
        if (
          ["hair", "lips", "color"].includes(action) &&
          Object.hasOwn(colors, b.dataset.color)
        ) {
          m[action] = b.dataset.color;
          root
            .querySelectorAll(`[data-game-action="${action}"]`)
            .forEach((node) => node.setAttribute("aria-pressed", node === b));
        }
        if (action === "tool") {
          m.tool = b.dataset.tool;
          root
            .querySelectorAll('[data-game-action="tool"]')
            .forEach((node) => node.setAttribute("aria-pressed", node === b));
        }
        if (action === "undo") {
          (key === "sand" ? m.strokes : m.decorations).pop();
        }
        if (action === "pour" && !m.transfer) {
          m.pouring = !m.pouring && m.fill < 1;
        }
        if (action === "shelf") shelfJar(m);
        if (action === "clear-shelf") {
          m.shelf = [];
          m.transfer = null;
          m.jar = { x: 360, y: 365 };
        }
        announce(readout(key, m));
        draw();
        start();
      },
      { signal },
    );
    root.addEventListener(
      "input",
      (event) => {
        if (event.target.dataset.gameRange === "width") {
          m.width = clamp(Number(event.target.value), 15, 55);
          draw();
        }
      },
      { signal },
    );
    document.addEventListener(
      "visibilitychange",
      () => {
        if (document.hidden) {
          cancelAnimationFrame(frame);
          frame = 0;
          last = 0;
        } else start();
      },
      { signal },
    );
    const preference = () => {
      if (motion.matches && ["lava", "balls"].includes(key)) {
        m.paused = true;
        cancelAnimationFrame(frame);
        frame = 0;
        last = 0;
        const b = root.querySelector('[data-game-action="pause"]');
        b.textContent = "Запустить";
        b.setAttribute("aria-pressed", "true");
        draw();
      }
    };
    motion.addEventListener("change", preference, { signal });
    preference();
    stop = () => {
      controller.abort();
      cancelAnimationFrame(frame);
      m.dragging = null;
      m.stroke = null;
      m.pointer = null;
      if (key === "jam") m.pouring = false;
    };
    draw();
    start();
    if (scrollToStage) {
      canvas.scrollIntoView({ block: "center" });
      scrollToStage = false;
    }
  }
  document.addEventListener("click", (event) => {
    const choice = event.target.closest("[data-game-select]");
    if (
      !choice ||
      state.user?.role !== "patient" ||
      !Object.hasOwn(definitions, choice.dataset.gameSelect)
    )
      return;
    selected = choice.dataset.gameSelect;
    scrollToStage = true;
    render();
  });
  return { page, mount, reset };
})();
