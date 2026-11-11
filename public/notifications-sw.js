self.addEventListener("push", event => {
    event.waitUntil((async () => {
        const payload = event.data?.json() || {};
        const doorId = Number(payload.data?.door_id);
        const url = Number.isSafeInteger(doorId) && doorId > 0 ? `/app/doors?door=${doorId}` : "/app/doors";
        await self.registration.showNotification(payload.title || "TzufGuard", {
            body: payload.body || "", icon: "/icons/icon-192.png", badge: "/icons/icon-192.png",
            tag: payload.tag, data: { url },
        });
    })());
});

self.addEventListener("notificationclick", event => {
    event.notification.close();
    const target = new URL(event.notification.data?.url || "/app/doors", self.location.origin);
    if (target.origin !== self.location.origin) return;
    event.waitUntil((async () => {
        const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
        if (windows.length) {
            await windows[0].navigate(target.href);
            await windows[0].focus();
        } else {
            await self.clients.openWindow(target.href);
        }
    })());
});
