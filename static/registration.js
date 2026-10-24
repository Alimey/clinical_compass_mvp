"use strict";

function decoratePublicEntry() {
  const root = $("#login-screen .login-layout, #login-screen .intake-layout");
  if (!root) return;
  if (!root.querySelector("[data-theme-toggle]"))
    root.insertAdjacentHTML(
      "afterbegin",
      '<button type="button" class="entry-theme-toggle icon-button" data-theme-toggle aria-label="Сменить цветовую тему"></button>',
    );
  updateThemeControl();
}
function publicScreen(title, body) {
  $("#app-shell").hidden = true;
  $("#login-screen").hidden = false;
  $("#login-screen").innerHTML =
    `<div class="intake-layout registration-layout"><div class="brand"><img src="/static/icon.svg" alt="" width="36" height="36"><span>ПсиКомпас<small>Пространство заботы</small></span></div><button class="text-button registration-back" type="button" data-registration="login">${icon("back")}Ко входу</button><h1>${e(title)}</h1>${body}<p id="registration-error" class="login-error" role="alert" hidden></p></div>`;
  decoratePublicEntry();
}
const accountInputs = () =>
  '<label>Имя и фамилия<input name="name" required minlength="2" maxlength="100" autocomplete="name"></label><label>Телефон<input name="phone" type="tel" required maxlength="30" placeholder="+70000000999" autocomplete="tel"></label>';
const passwordInputs = () =>
  '<label>Пароль<input name="password" type="password" required minlength="8" maxlength="200" autocomplete="new-password" aria-describedby="password-hint"></label><p id="password-hint" class="caption">От 8 символов</p><label>Повторите пароль<input name="confirm" type="password" required minlength="8" maxlength="200" autocomplete="new-password"></label>';
function showRegistration(invitation = false) {
  publicScreen(
    "Создать аккаунт",
    `<p>Выберите, как вы будете пользоваться приложением.</p><div class="registration-roles"><button class="button" type="button" data-registration="doctor">${icon("users")}Я специалист</button><button class="button" type="button" data-registration="patient">${icon("heart")}Я пациент</button><button class="button" type="button" data-registration="relative">${icon("users")}Я близкий</button></div><div id="registration-choice"></div>`,
  );
  if (invitation) chooseRegistration("patient");
}
function chooseRegistration(role) {
  for (const b of document.querySelectorAll(".registration-roles button"))
    b.setAttribute("aria-pressed", String(b.dataset.registration === role));
  $("#registration-error").hidden = true;
  $("#registration-choice").innerHTML =
    role === "doctor"
      ? `<form id="doctor-registration-form"><h2>Кабинет специалиста</h2>${accountInputs()}<label>Специализация<input name="profession" maxlength="100" autocomplete="organization-title" placeholder="Психолог, психотерапевт"></label><label>Организация, необязательно<input name="organization" maxlength="100" autocomplete="organization"></label>${passwordInputs()}<button type="submit" class="button primary full">Зарегистрироваться</button></form>`
      : `<form id="invitation-link-form" data-kind="${role}"><h2>${role === "patient" ? "Приглашение врача" : "Приглашение пациента"}</h2><p>${role === "patient" ? "Попросите врача создать приглашение в разделе «Пациенты». Оно свяжет вашу карточку с его кабинетом." : "Попросите пациента создать приглашение в разделе «Мои согласия». Доступ к сигналам он настраивает сам."}</p><label>Ссылка или код приглашения<input name="invitation" required maxlength="500" autocomplete="off" placeholder="Вставьте приглашение"></label><button type="submit" class="button primary full">Продолжить</button></form>`;
}
const firstShowIntake = showIntake;
showIntake = async function () {
  if (!location.hash.startsWith("#support=")) {
    await firstShowIntake();
    decoratePublicEntry();
    $("#intake-form")?.insertAdjacentHTML(
      "afterend",
      '<button class="text-button registration-back" type="button" data-registration="login">Ко входу</button>',
    );
    return;
  }
  const token = location.hash.slice("#support=".length);
  publicScreen(
    "Регистрация близкого",
    '<p role="status">Проверяю приглашение…</p>',
  );
  try {
    const data = await api("/api/intake/relative-info", { token });
    publicScreen(
      "Рядом с близким человеком",
      `<p>Вас приглашает ${e(data.patient.name)}. В кабинете будут только сведения, доступ к которым разрешит пациент.</p><form id="relative-registration-form" data-token="${e(token)}">${accountInputs()}${passwordInputs()}<button class="button primary full" type="submit">Создать аккаунт и войти</button></form>`,
    );
  } catch (error) {
    publicScreen(
      "Приглашение недоступно",
      `<p role="alert">${e(error.message)}</p><button type="button" class="button" data-registration="invitation">Ввести другое приглашение</button>`,
    );
  }
};
function registrationError(message) {
  const error = $("#registration-error");
  error.textContent = message;
  error.hidden = false;
}
async function submitAccount(form, endpoint) {
  if (busy) return;
  const data = Object.fromEntries(new FormData(form));
  if (data.password !== data.confirm)
    return registrationError("Пароли не совпадают");
  delete data.confirm;
  if (form.dataset.token) data.token = form.dataset.token;
  busy = true;
  const controls = [...form.elements];
  controls.forEach((el) => (el.disabled = true));
  $("#registration-error").hidden = true;
  try {
    const result = await api(endpoint, data);
    history.replaceState(null, "", location.pathname);
    await OfflineVault.clear();
    busy = false;
    await login(result.username, data.password);
  } catch (error) {
    registrationError(error.message);
  } finally {
    busy = false;
    controls.forEach((el) => (el.disabled = false));
  }
}
document.addEventListener("submit", (event) => {
  const form = event.target;
  if (
    form.id === "doctor-registration-form" ||
    form.id === "relative-registration-form"
  ) {
    event.preventDefault();
    submitAccount(
      form,
      "/api/intake/" +
        (form.id === "doctor-registration-form" ? "doctor" : "relative"),
    );
  } else if (form.id === "invitation-link-form") {
    event.preventDefault();
    const kind = form.dataset.kind === "patient" ? "join" : "support";
    let token = form.elements.invitation.value.trim();
    try {
      if (token.includes("://")) {
        const url = new URL(token);
        if (url.origin !== location.origin) throw new Error();
        token = url.hash;
      }
      if (token.startsWith("#")) {
        if (!token.startsWith("#" + kind + "=")) throw new Error();
        token = token.slice(kind.length + 2);
      }
      if (!/^[A-Za-z0-9_-]{32}$/.test(token)) throw new Error();
      history.replaceState(null, "", "#" + kind + "=" + token);
      showIntake();
    } catch {
      registrationError(
        "Проверьте приглашение и выбранную роль. Нужна ссылка из этого приложения или код из неё.",
      );
    }
  }
});
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-registration]");
  if (!button || button.disabled || busy) return;
  const action = button.dataset.registration;
  if (action === "open" || action === "invitation")
    return showRegistration(action === "invitation");
  if (["doctor", "patient", "relative"].includes(action))
    return chooseRegistration(action);
  if (action === "login") {
    history.replaceState(null, "", location.pathname);
    return renderLogin();
  }
  try {
    if (action === "invite-relative" && state.user?.role === "patient") {
      button.disabled = true;
      const invite = await api("/api/relative-invites", {});
      const url =
        location.origin + location.pathname + "#support=" + invite.token;
      $("#relative-invite-result").innerHTML =
        `<div class="source-note"><p>Одноразовое приглашение · 72 часа</p><input class="invite-url" aria-label="Приглашение близкого" readonly value="${e(url)}"><button type="button" class="button" data-registration="copy-relative">Копировать ссылку</button></div>`;
    } else if (action === "copy-relative") {
      const input = $("#relative-invite-result input");
      try {
        await navigator.clipboard.writeText(input.value);
        toast("Ссылка скопирована");
      } catch {
        input.focus();
        input.select();
        toast("Скопируйте выделенную ссылку");
      }
    }
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
  }
});
