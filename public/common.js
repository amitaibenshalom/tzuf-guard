export const TOKEN_KEY = "tzufguard_access_token";

export const $ = (selector, root = document) => root.querySelector(selector);
export const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

export function hasSession() {
    return Boolean(localStorage.getItem(TOKEN_KEY));
}

export function saveSession(payload) {
    localStorage.setItem(TOKEN_KEY, payload.access_token);
}

export function clearSession() {
    localStorage.removeItem(TOKEN_KEY);
}

export function safeNextPath(fallback = "/app/doors") {
    const next = new URLSearchParams(location.search).get("next");
    return next && next.startsWith("/") && !next.startsWith("//") ? next : fallback;
}

export async function api(path, options = {}) {
    const { redirectOnUnauthorized = true, ...fetchOptions } = options;
    const headers = new Headers(fetchOptions.headers || {});
    if (fetchOptions.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
    const token = localStorage.getItem(TOKEN_KEY);
    if (token) headers.set("Authorization", `Bearer ${token}`);

    const response = await fetch(`/api${path}`, { ...fetchOptions, headers });
    const text = await response.text();
    let payload = {};
    if (text) {
        try { payload = JSON.parse(text); } catch { payload = {}; }
    }
    if (!response.ok) {
        if (response.status === 401 && redirectOnUnauthorized && !path.startsWith("/auth/")) {
            clearSession();
            location.replace(`/login?expired=1&next=${encodeURIComponent(location.pathname)}`);
        }
        const error = new Error(payload?.error?.message || "Request failed.");
        error.code = payload?.error?.code;
        error.status = response.status;
        throw error;
    }
    return payload;
}

export function escapeHtml(value = "") {
    const node = document.createElement("div");
    node.textContent = String(value);
    return node.innerHTML;
}

export function errorMessage(error) {
    return error?.message || "Something went wrong. Please try again.";
}

export function icon(name) {
    return `<svg aria-hidden="true"><use href="#icon-${name}"></use></svg>`;
}

export function setBusy(form, busy, busyText = "Please wait…") {
    const button = form.querySelector("button[type='submit']");
    if (!button) return;
    if (!button.dataset.label) button.dataset.label = button.textContent;
    button.disabled = busy;
    button.textContent = busy ? busyText : button.dataset.label;
}

export function statusMeta(status, online = true, hasReported = true) {
    if (!hasReported) return { label: "Waiting for first report", className: "status--unknown" };
    if (!online) return { label: "Offline", className: "status--offline" };
    if (status === "opened") return { label: "Open", className: "status--opened" };
    if (status === "closed") return { label: "Closed", className: "status--closed" };
    return { label: "Not connected", className: "status--unknown" };
}

export function formatElapsed(totalSeconds) {
    const total = Math.max(0, Math.floor(Number(totalSeconds) || 0));
    const days = Math.floor(total / 86400);
    const hours = Math.floor((total % 86400) / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const seconds = total % 60;
    if (days > 0) return `${days}d ${hours}h`;
    if (hours > 0) return `${hours}h ${minutes}m`;
    if (minutes > 0) return `${minutes}m ${seconds}s`;
    return `${seconds}s`;
}

export function durationText(status, startedAt) {
    const started = new Date(startedAt).getTime();
    if (!Number.isFinite(started)) return "Duration starts with the next change";
    return `${statusMeta(status).label} for ${formatElapsed((Date.now() - started) / 1000)}`;
}

export function statusStartedText(status, startedAt, now = Date.now()) {
    const date = new Date(startedAt);
    if (!Number.isFinite(date.getTime()) || !["opened", "closed"].includes(status)) return "";

    const current = new Date(now);
    const localDay = value => Date.UTC(value.getFullYear(), value.getMonth(), value.getDate());
    const daysAgo = Math.floor((localDay(current) - localDay(date)) / 86400000);
    let relative;
    if (daysAgo <= 0) relative = "today";
    else if (daysAgo === 1) relative = "yesterday";
    else if (daysAgo < 7) relative = `${daysAgo} days ago`;
    else if (daysAgo < 30) {
        const weeks = Math.floor(daysAgo / 7);
        relative = `${weeks} ${weeks === 1 ? "week" : "weeks"} ago`;
    } else if (daysAgo < 365) {
        const months = Math.floor(daysAgo / 30);
        relative = `${months} ${months === 1 ? "month" : "months"} ago`;
    } else {
        const years = Math.floor(daysAgo / 365);
        relative = `${years} ${years === 1 ? "year" : "years"} ago`;
    }

    const time = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(date);
    const fullDate = new Intl.DateTimeFormat(undefined, {
        month: "short",
        day: "numeric",
        ...(date.getFullYear() !== current.getFullYear() ? { year: "numeric" } : {}),
    }).format(date);
    const timestamp = daysAgo <= 1 ? `${relative} at ${time}` : `${relative} · ${fullDate} at ${time}`;
    const state = status === "opened" ? "Opened" : "Closed";
    return `${state} since ${timestamp}`;
}

export function setDurationCounter(element, status, startedAt) {
    if (!element) return;
    if (!startedAt || !["opened", "closed"].includes(status)) {
        delete element.dataset.durationStatus;
        delete element.dataset.durationStartedAt;
        element.textContent = status ? "Duration starts with the next change" : "Waiting for the first sensor report";
        return;
    }
    element.dataset.durationStatus = status;
    element.dataset.durationStartedAt = startedAt;
    element.textContent = durationText(status, startedAt);
}

export function updateDurationCounters() {
    $$('[data-duration-started-at]').forEach(element => {
        element.textContent = durationText(element.dataset.durationStatus, element.dataset.durationStartedAt);
    });
    $$('[data-state-started-at]').forEach(element => {
        element.textContent = statusStartedText(element.dataset.stateStatus, element.dataset.stateStartedAt);
    });
    $$('[data-relative-time]').forEach(element => {
        element.textContent = `Last seen ${relativeTime(element.dataset.relativeTime)}`;
    });
}

export function durationMarkup(door) {
    if (!door.last_seen_at) return "";
    if (!door.is_online) {
        const lastKnown = door.last_status === "opened" ? "Open" : door.last_status === "closed" ? "Closed" : "Unknown";
        return `<span class="state-duration">Last known: ${lastKnown}</span>`;
    }
    if (!["opened", "closed"].includes(door.last_status)) return "";
    if (!door.status_changed_at) return '<span class="state-duration">Duration starts with the next change</span>';
    const startedAt = escapeHtml(door.status_changed_at);
    return `<span class="state-timing"><span class="state-duration" data-duration-status="${door.last_status}" data-duration-started-at="${startedAt}">${escapeHtml(durationText(door.last_status, door.status_changed_at))}</span><span class="state-started-at" data-state-status="${door.last_status}" data-state-started-at="${startedAt}">${escapeHtml(statusStartedText(door.last_status, door.status_changed_at))}</span></span>`;
}

export function formatDate(value) {
    if (!value) return "Never reported";
    const date = new Date(value);
    if (!Number.isFinite(date.getTime())) return "Report time unavailable";
    return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}

export function relativeTime(value) {
    if (!value) return "Waiting for first report";
    const timestamp = new Date(value).getTime();
    if (!Number.isFinite(timestamp)) return "Report time unavailable";
    const seconds = Math.round((timestamp - Date.now()) / 1000);
    const ranges = [[31536000, "year"], [2592000, "month"], [86400, "day"], [3600, "hour"], [60, "minute"]];
    if (typeof Intl.RelativeTimeFormat === "function") {
        const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
        for (const [unitSeconds, unit] of ranges) {
            if (Math.abs(seconds) >= unitSeconds) return formatter.format(Math.round(seconds / unitSeconds), unit);
        }
        return formatter.format(seconds, "second");
    }
    const [unitSeconds, unit] = ranges.find(([size]) => Math.abs(seconds) >= size) || [1, "second"];
    const amount = Math.max(1, Math.round(Math.abs(seconds) / unitSeconds));
    const label = `${unit}${amount === 1 ? "" : "s"}`;
    return seconds < 0 ? `${amount} ${label} ago` : `In ${amount} ${label}`;
}
