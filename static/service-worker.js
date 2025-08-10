const CACHE_NAME = "v3";
const ASSETS = [
  "/",
  "/static/styles.css",
  "/static/manifest.json",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png"
];

// --- Install: Precache
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS))
  );
});

// --- Activate: Cleanup old caches
self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)));
    await initDB();
    self.clients.claim();
  })());
});

// --- Simple cache-first for GET
self.addEventListener("fetch", (event) => {
  const req = event.request;

  // Only handle same-origin
  const sameOrigin = new URL(req.url).origin === self.location.origin;

  // Intercept failed POST /add -> queue
  if (sameOrigin && req.method === "POST" && new URL(req.url).pathname === "/add") {
    event.respondWith(
      fetch(req.clone()).catch(async () => {
        await queueRequest(req);
        // Try to register background sync
        if ("sync" in self.registration) {
          try { await self.registration.sync.register("sync-entries"); } catch (e) {}
        }
        return new Response(
          JSON.stringify({ queued: true, message: "Eintrag wird synchronisiert, sobald du wieder online bist." }),
          { status: 202, headers: { "Content-Type": "application/json" } }
        );
      })
    );
    return;
  }

  if (req.method === "GET" && sameOrigin) {
    event.respondWith(
      caches.match(req).then((res) => res || fetch(req))
    );
  }
});

// --- Background Sync: replay queued POSTs
self.addEventListener("sync", (event) => {
  if (event.tag === "sync-entries") {
    event.waitUntil(flushQueue());
  }
});

/* ===== IndexedDB minimal helpers ===== */
let dbPromise;
function initDB(){
  if (dbPromise) return dbPromise;
  dbPromise = new Promise((resolve, reject) => {
    const open = indexedDB.open("hb-sync", 1);
    open.onupgradeneeded = () => {
      const db = open.result;
      if (!db.objectStoreNames.contains("outbox")) {
        db.createObjectStore("outbox", { keyPath: "id", autoIncrement: true });
      }
    };
    open.onsuccess = () => resolve(open.result);
    open.onerror = () => reject(open.error);
  });
  return dbPromise;
}

async function queueRequest(request){
  const db = await initDB();
  const body = await request.clone().formData();
  const pairs = {};
  for (const [k,v] of body.entries()) pairs[k] = v;
  return new Promise((resolve, reject) => {
    const tx = db.transaction("outbox", "readwrite");
    tx.objectStore("outbox").add({ created: Date.now(), path: "/add", data: pairs });
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

async function flushQueue(){
  const db = await initDB();
  const tx = db.transaction("outbox", "readwrite");
  const store = tx.objectStore("outbox");
  const items = await new Promise((resolve, reject) => {
    const all = [];
    const req = store.openCursor();
    req.onsuccess = (e) => {
      const cur = e.target.result;
      if (!cur) return resolve(all);
      all.push({ key: cur.key, value: cur.value });
      cur.continue();
    };
    req.onerror = () => reject(req.error);
  });

  for (const item of items) {
    const form = new FormData();
    Object.entries(item.value.data).forEach(([k,v]) => form.append(k, v));
    try{
      const res = await fetch(item.value.path, { method: "POST", body: form, credentials: "include" });
      if (res.ok || res.status === 302) {
        await new Promise((resolve, reject) => {
          const dtx = db.transaction("outbox", "readwrite");
          dtx.objectStore("outbox").delete(item.key);
          dtx.oncomplete = () => resolve();
          dtx.onerror = () => reject(dtx.error);
        });
      }
    }catch(e){ /* still offline -> leave in queue */ }
  }
}
