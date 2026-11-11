// Retire browser notification registrations created by the previous release.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", event => {
    event.waitUntil((async () => {
        try {
            const subscription = await self.registration.pushManager?.getSubscription();
            if (subscription) await subscription.unsubscribe();
        } finally {
            await self.registration.unregister();
        }
    })());
});
