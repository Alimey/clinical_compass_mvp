"use strict";
const CACHE = "compass-shell-v16";
const SHELL = [
  "/",
  "/static/style.css",
  "/static/app.js",
  "/static/care.js",
  "/static/psicompas.js",
  "/static/psicompas.css",
  "/static/experience.js",
  "/static/experience.css",
  "/static/patient-ui.js",
  "/static/patient-ui.css",
  "/static/games.js",
  "/static/games.css",
  "/static/shell.css",
  "/static/registration.js",
  "/static/revision8.js",
  "/static/sections.js",
  "/static/prototype-content.js",
  "/static/fonts/montserrat-cyrillic-400-normal.woff2",
  "/static/fonts/montserrat-cyrillic-600-normal.woff2",
  "/static/fonts/montserrat-latin-400-normal.woff2",
  "/static/fonts/montserrat-latin-600-normal.woff2",
  "/static/fonts/montserrat-latin-700-normal.woff2",
  "/static/fonts/montserrat-latin-500-normal.woff2",
  "/static/fonts/montserrat-cyrillic-700-normal.woff2",
  "/static/fonts/montserrat-cyrillic-500-normal.woff2",
  "/static/offline.js",
  "/static/manifest.webmanifest",
  "/static/icon.svg",
  "/static/icon-192.png",
  "/static/icon-512.png",
  "/static/icon-maskable.png",
];
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(SHELL))
      .then(() => self.skipWaiting()),
  );
});
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => key.startsWith("compass-shell-") && key !== CACHE)
            .map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  // Never cache patient data, API responses or writes. No background submissions.
  if (
    event.request.method !== "GET" ||
    url.origin !== self.location.origin ||
    !SHELL.includes(url.pathname)
  )
    return;
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response.ok) {
          const copy = response.clone();
          event.waitUntil(
            caches.open(CACHE).then((cache) => cache.put(event.request, copy)),
          );
        }
        return response;
      })
      .catch(() => caches.match(event.request)),
  );
});

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data?.json() || {};
  } catch {}
  event.waitUntil(
    self.registration.showNotification("ПсиКомпас", {
      body: "В приложении новое событие. Откройте его для просмотра.",
      icon: "/static/icon-192.png",
      badge: "/static/icon-192.png",
      tag: typeof data.tag === "string" ? data.tag : "compass-event",
      data: { url: "/" },
    }),
  );
});
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(
    clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then((windows) => {
        const target = windows.find(
          (w) => new URL(w.url).origin === self.location.origin,
        );
        return target ? target.focus() : clients.openWindow("/");
      }),
  );
});
