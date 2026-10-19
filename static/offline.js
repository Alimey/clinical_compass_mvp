/* Explicit, encrypted, read-only patient snapshots. No sessions or chat storage. */
const OfflineVault = (() => {
  let epoch = 0;
  let activeKey = null,
    activeSalt = null,
    owner = null;
  function open() {
    return new Promise((resolve, reject) => {
      const r = indexedDB.open("compass-offline-v1", 1);
      r.onupgradeneeded = () => r.result.createObjectStore("vault");
      r.onsuccess = () => resolve(r.result);
      r.onerror = () => reject(new Error("Офлайн-хранилище недоступно"));
    });
  }
  async function access(mode, fn) {
    const db = await open();
    return new Promise((resolve, reject) => {
      const t = db.transaction("vault", mode),
        r = fn(t.objectStore("vault"));
      let result;
      r.onsuccess = () => (result = r.result);
      t.oncomplete = () => {
        db.close();
        resolve(result);
      };
      t.onerror = () => {
        db.close();
        reject(new Error("Ошибка офлайн-хранилища"));
      };
    });
  }
  async function derive(pin, salt) {
    if (!/^\d{6}$/.test(pin)) throw new Error("PIN должен состоять из 6 цифр");
    const material = await crypto.subtle.importKey(
      "raw",
      new TextEncoder().encode(pin),
      "PBKDF2",
      false,
      ["deriveKey"],
    );
    return crypto.subtle.deriveKey(
      { name: "PBKDF2", salt, iterations: 210000, hash: "SHA-256" },
      material,
      { name: "AES-GCM", length: 256 },
      false,
      ["encrypt", "decrypt"],
    );
  }
  function snapshot(state) {
    const d = state.detail;
    return {
      user: { id: state.user.id, name: state.user.name },
      saved_at: new Date().toISOString(),
      doctor: d.doctor,
      profile: {
        age: d.profile.age,
        plan: d.profile.plan,
        plan_note: d.profile.plan_note,
      },
      care: {
        appointments: d.care.appointments,
        encounters: d.care.encounters,
        labs: d.care.labs,
        prescriptions: d.care.prescriptions,
      },
      catalog: d.catalog,
    };
  }
  async function refresh(state) {
    if (!activeKey || owner !== state.user?.id || state.user.role !== "patient")
      return;
    const generation = epoch;
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const ciphertext = await crypto.subtle.encrypt(
      { name: "AES-GCM", iv },
      activeKey,
      new TextEncoder().encode(JSON.stringify(snapshot(state))),
    );
    if (generation !== epoch) return;
    await access("readwrite", (store) =>
      store.put({ salt: activeSalt, iv, ciphertext }, "patient"),
    );
  }
  async function save(state, pin) {
    if (!crypto.subtle)
      throw new Error("Офлайн-копия требует HTTPS или localhost");
    if (state.user.role !== "patient")
      throw new Error("Офлайн-копия доступна только пациенту");
    activeSalt = crypto.getRandomValues(new Uint8Array(16));
    activeKey = await derive(pin, activeSalt);
    owner = state.user.id;
    await refresh(state);
  }
  async function unlock(pin) {
    const entry = await access("readonly", (store) => store.get("patient"));
    if (!entry) throw new Error("Офлайн-копии нет");
    try {
      const key = await derive(pin, entry.salt);
      const plain = await crypto.subtle.decrypt(
        { name: "AES-GCM", iv: entry.iv },
        key,
        entry.ciphertext,
      );
      return JSON.parse(new TextDecoder().decode(plain));
    } catch {
      throw new Error("Неверный PIN или повреждённая копия");
    }
  }
  async function exists() {
    try {
      return Boolean(await access("readonly", (store) => store.get("patient")));
    } catch {
      return false;
    }
  }
  async function clear() {
    epoch++;
    activeKey = null;
    activeSalt = null;
    owner = null;
    await access("readwrite", (store) => store.delete("patient"));
  }
  return { save, refresh, unlock, exists, clear };
})();
