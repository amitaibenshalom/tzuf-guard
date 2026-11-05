import { $, hasSession, setDurationCounter, updateDurationCounters } from "/common.js";

const publicDemo = $("#public-demo");

function durationStartedAt(duration) {
    if (duration === null || duration === undefined || !Number.isFinite(Number(duration))) return null;
    return new Date(Date.now() - Math.max(0, Number(duration)) * 1000).toISOString();
}

function renderPublicDemo(payload) {
    const available = payload?.available === true;
    const status = available ? payload.status : null;
    const detail = $("#demo-door-detail");
    publicDemo.classList.remove("is-loading", "is-open", "is-closed", "is-unavailable");
    $("#demo-door-label").textContent = payload?.label || "Amitai's door";

    if (["opened", "closed"].includes(status)) {
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

if (hasSession()) {
    $("#home-login-link").classList.add("hidden");
    $("#home-nav-cta").textContent = "Open dashboard";
    $("#home-nav-cta").href = "/app/doors";
    $("#home-primary-cta").innerHTML = 'Open your doors <svg aria-hidden="true"><use href="#icon-arrow"></use></svg>';
    $("#home-primary-cta").href = "/app/doors";
    $("#home-secondary-login").classList.add("hidden");
}

loadPublicDemo();
setInterval(updateDurationCounters, 1000);
setInterval(() => {
    if (!document.hidden) loadPublicDemo();
}, 10000);
