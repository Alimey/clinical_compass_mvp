"use strict";
let presenceOwner = null,
  presenceSent = 0,
  presencePending = false,
  presenceInteractionAt = Date.now();
async function sendPresence() {
  if (
    state.user?.role !== "patient" ||
    document.hidden ||
    Date.now() - presenceInteractionAt > 300000 ||
    !navigator.onLine ||
    presencePending
  )
    return;
  const owner = state.user.id;
  if (presenceOwner === owner && Date.now() - presenceSent < 60000) return;
  presencePending = true;
  try {
    await api("/api/activity/heartbeat", {});
    if (state.user?.id === owner) {
      presenceOwner = owner;
      presenceSent = Date.now();
    }
  } catch {
    /* Ordinary actions continue; a later visible heartbeat retries. */
  } finally {
    presencePending = false;
  }
}
setInterval(sendPresence, 60000);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) {
    presenceInteractionAt = Date.now();
    sendPresence();
  }
});
for (const event of ["pointerdown", "keydown"])
  document.addEventListener(
    event,
    () => {
      presenceInteractionAt = Date.now();
      sendPresence();
    },
    { passive: true },
  );
window.addEventListener("online", sendPresence);
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-test-push]");
  if (!button || button.disabled || !state.user || busy) return;
  button.disabled = true;
  try {
    await api("/api/push/test", {});
    toast(
      "Проверка поставлена в очередь для подключённых устройств. Сверните приложение, чтобы увидеть системное уведомление.",
    );
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
  }
});
function notificationSettings() {
  return `<section class="card"><h2>Уведомления на устройствах</h2><p>Разрешите push, чтобы получать сообщения на телефон или компьютер, даже когда вкладка приложения закрыта.</p><div class="proposal-actions"><button class="button primary" data-care="enable-push">Подключить push</button><button class="button" data-test-push>Проверить уведомление</button><button class="button quiet" data-care="disable-push">Отключить</button></div><p>На iPhone сначала добавьте приложение на экран «Домой» через Safari. Напоминания работают, пока сервер запущен.</p></section>`;
}
