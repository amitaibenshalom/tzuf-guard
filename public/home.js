import { $, api, clearSession, hasSession, setDurationCounter, updateDurationCounters } from "/common.js";

const publicDemo = $("#public-demo");
const PUBLIC_DEMO_EVENT = "demo.status.changed";
const DEMO_CLIENT_STORAGE_KEY = "tzufguard_demo_client_id";
let realtime = null;
let transientDemoClientId = null;

function demoClientId() {
    try {
        const existing = localStorage.getItem(DEMO_CLIENT_STORAGE_KEY);
        if (/^demo-[a-f0-9]{32}$/.test(existing || "")) return existing;
    } catch {
        // Storage can be unavailable in restrictive privacy modes. Keeping the
        // ID in memory still makes token renewal stable for this page session.
    }
    if (transientDemoClientId) return transientDemoClientId;

    const bytes = new Uint8Array(16);
    crypto.getRandomValues(bytes);
    const clientId = `demo-${Array.from(bytes, byte => byte.toString(16).padStart(2, "0")).join("")}`;
    transientDemoClientId = clientId;
    try {
        localStorage.setItem(DEMO_CLIENT_STORAGE_KEY, clientId);
    } catch {
        // The in-memory ID above is sufficient when persistent storage is blocked.
    }
    return clientId;
}

function durationStartedAt(duration) {
    if (duration === null || duration === undefined || !Number.isFinite(Number(duration))) return null;
    return new Date(Date.now() - Math.max(0, Number(duration)) * 1000).toISOString();
}

function renderPublicDemo(payload) {
    const available = payload?.available === true;
    const status = available ? payload.status : null;
    const detail = $("#demo-door-detail");
    publicDemo.classList.remove("is-loading", "is-open", "is-closed", "is-offline", "is-unavailable");
    $("#demo-door-label").textContent = payload?.label || "Amitai's door";

    if (available && payload.online === false && payload.last_seen_seconds !== null && payload.last_seen_seconds !== undefined) {
        publicDemo.classList.add("is-offline");
        $("#demo-door-status").textContent = "Offline";
        delete detail.dataset.durationStatus;
        delete detail.dataset.durationStartedAt;
        const minutes = Math.max(10, Math.floor(Number(payload.last_seen_seconds || 600) / 60));
        detail.textContent = `No sensor signal for ${minutes} minutes`;
        return;
    }

    if (payload?.last_seen_seconds !== null && payload?.last_seen_seconds !== undefined && ["opened", "closed"].includes(status)) {
        publicDemo.classList.add(status === "opened" ? "is-open" : "is-closed");
        $("#demo-door-status").textContent = status === "opened" ? "Open" : "Closed";
        setDurationCounter(detail, status, durationStartedAt(payload.duration_seconds));
        return;
    }

    publicDemo.classList.add("is-unavailable");
    $("#demo-door-status").textContent = available ? "Waiting" : "Coming online";
    delete detail.dataset.durationStatus;
    delete detail.dataset.durationStartedAt;
    detail.textContent = available ? "Waiting for the sensor's first report" : "The live sensor demo is being configured";
}

async function loadPublicDemo() {
    try {
        const response = await fetch("/api/public/demo-door", { headers: { Accept: "application/json" } });
        if (!response.ok) throw new Error("Demo request failed");
        renderPublicDemo(await response.json());
    } catch {
        renderPublicDemo({ available: false });
    }
}

async function getRealtimeCredentials() {
    const response = await fetch("/api/public/demo-door/realtime-token", {
        method: "POST",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        body: JSON.stringify({ client_id: demoClientId() }),
    });
    if (!response.ok) throw new Error("Demo realtime authentication failed");
    return response.json();
}

function stopRealtime() {
    if (!realtime) return;
    realtime.channel.unsubscribe(PUBLIC_DEMO_EVENT, realtime.onMessage);
    realtime.channel.off("attached", realtime.onAttached);
    realtime.channel.off("update", realtime.onUpdate);
    realtime.channel.detach().catch(() => undefined);
    realtime.client.close();
    realtime = null;
}

async function startRealtime() {
    if (!window.AblyPubSub?.createClient) throw new Error("The realtime client did not load");
    const credentials = await getRealtimeCredentials();
    let initialToken = credentials.token;
    const client = window.AblyPubSub.createClient({
        echoMessages: false,
        authCallback: async (_tokenParams, callback) => {
            try {
                if (initialToken) {
                    const token = initialToken;
                    initialToken = null;
                    callback(null, token);
                    return;
                }
                const refreshed = await getRealtimeCredentials();
                callback(null, refreshed.token);
            } catch (error) {
                callback(error instanceof Error ? error.message : "Realtime authentication failed", null);
            }
        },
    });
    const channel = client.channels.get(credentials.channel);
    const connection = {
        client,
        channel,
        attachedOnce: false,
        onMessage: message => renderPublicDemo(message.data),
        onAttached: change => {
            if (connection.attachedOnce && !change.resumed) loadPublicDemo();
            connection.attachedOnce = true;
        },
        onUpdate: change => {
            if (!change.resumed) loadPublicDemo();
        },
    };
    realtime = connection;
    channel.on("attached", connection.onAttached);
    channel.on("update", connection.onUpdate);
    await channel.subscribe(PUBLIC_DEMO_EVENT, connection.onMessage);
}

const logoutButton = $("#home-logout-button");
logoutButton.addEventListener("click", () => {
    clearSession();
    location.assign("/");
});

if (hasSession()) {
    $("#home-login-link").classList.add("hidden");
    logoutButton.classList.remove("hidden");
    $("#hero-title").textContent = "Welcome back";
    $("#home-primary-cta").innerHTML = 'Open your doors <svg aria-hidden="true"><use href="#icon-arrow"></use></svg>';
    $("#home-primary-cta").href = "/app/doors";
    api("/me").then(({ user }) => {
        const name = user?.name?.trim();
        if (name) $("#hero-title").textContent = `Welcome back, ${name}`;
    }).catch(error => {
        if (error.status !== 401) console.error("Could not load the signed-in user's name:", error);
    });
}

loadPublicDemo();
startRealtime().catch(error => console.error("Live demo realtime is unavailable:", error));
setInterval(updateDurationCounters, 1000);
document.addEventListener("visibilitychange", () => {
    if (!document.hidden) loadPublicDemo();
});
window.addEventListener("pagehide", stopRealtime);
