import { api, toast } from "/common.js";

const supported = () => "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;

export async function disableBrowserAlerts() {
    if (!supported()) return;
    const registration = await navigator.serviceWorker.getRegistration("/notifications-sw.js");
    const subscription = await registration?.pushManager.getSubscription();
    if (!subscription) return;
    try {
        await api("/web-push/subscriptions", { method: "DELETE", body: JSON.stringify({ endpoint: subscription.endpoint }) });
    } finally {
        await subscription.unsubscribe();
    }
}

export async function initializeBrowserAlerts() {
    const button = document.querySelector("#browser-alerts-toggle");
    const testButton = document.querySelector("#test-notification");
    if (!button || !supported()) return;
    const config = await api("/web-push/config");
    if (!config.enabled) return;
    button.classList.remove("hidden");
    const registration = await navigator.serviceWorker.register("/notifications-sw.js");
    await navigator.serviceWorker.ready;
    let subscription = await registration.pushManager.getSubscription();
    const update = () => {
        button.textContent = subscription ? "Disable browser alerts" : "Enable browser alerts";
        testButton?.classList.toggle("hidden", !subscription);
    };
    if (subscription && Notification.permission === "granted") {
        await api("/web-push/subscriptions", { method: "POST", body: JSON.stringify(subscription.toJSON()) });
    }
    update();
    button.addEventListener("click", async () => {
        button.disabled = true;
        try {
            if (subscription) {
                await disableBrowserAlerts();
                subscription = null;
            } else {
                const permission = await Notification.requestPermission();
                if (permission !== "granted") {
                    toast("Allow notifications in your browser’s site settings to enable alerts.");
                    return;
                }
                const base64 = config.public_key.replace(/-/g, "+").replace(/_/g, "/");
                const publicKey = Uint8Array.from(atob(base64 + "=".repeat((4 - base64.length % 4) % 4)), value => value.charCodeAt(0));
                subscription = await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: publicKey });
                await api("/web-push/subscriptions", { method: "POST", body: JSON.stringify(subscription.toJSON()) });
            }
            update();
        } catch {
            toast("Could not update browser alerts. Please try again.");
        } finally {
            button.disabled = false;
        }
    });
    testButton?.addEventListener("click", async () => {
        testButton.disabled = true;
        try {
            await api("/notifications/test", { method: "POST", body: "{}" });
            toast("Test alert queued.");
        } catch {
            toast("Could not send the test alert.");
        } finally {
            testButton.disabled = false;
        }
    });
}
