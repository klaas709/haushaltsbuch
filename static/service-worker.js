self.addEventListener("install", event => {
  event.waitUntil(
    caches.open("v2").then(cache => {
      return cache.addAll([
        "/",
        "/static/styles.css",
        "/static/manifest.json",
        "/static/icons/icon-192.png",
        "/static/icons/icon-512.png"
      ]);
    })
  );
});

self.addEventListener("fetch", event => {
  event.respondWith(
    caches.match(event.request).then(response => {
      return response || fetch(event.request);
    })
  );
});
