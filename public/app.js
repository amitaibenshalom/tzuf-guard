"use strict";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const state = {
    token: localStorage.getItem("tzufguard_access_token"),
    user: null,
    doors: [],
    activeDoor: null,
    eventPage: 1,
    events: [],
    hasMoreEvents: false,
    confirmAction: null,
    toastTimer: null,
};

const authView = $("#auth-view");
const dashboardView = $("#dashboard-view");
const doorGrid = $("#door-grid");
const doorLoading = $("#door-loading");
const emptyState = $("#empty-state");
const doorFormDialog = $("#door-form-dialog");
const doorForm = $("#door-form");
const tokenDialog = $("#token-dialog");
const detailDialog = $("#door-detail-dialog");
const confirmDialog = $("#confirm-dialog");
const publicDemo = $("#public-demo");

function icon(name) {
    return `<svg aria-hidden="true"><use href="#icon-${name}"></use></svg>`;
}

function escapeHtml(value = "") {
    const node = document.createElement("div");
    node.textContent = String(value);
    return node.innerHTML;
}

function errorMessage(error) {
    return error?.message || "Something went wrong. Please try again.";
}

async function api(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
    if (state.token) headers.set("Authorization", `Bearer ${state.token}`);

    const response = await fetch(`/api${path}`, { ...options, headers });
    const text = await response.text();
    let payload = {};
    if (text) {
        try { payload = JSON.parse(text); } catch { payload = {}; }
    }
    if (!response.ok) {
        if (response.status === 401 && options.handleAuth !== false && !path.startsWith("/auth/")) logout(false);
        const error = new Error(payload?.error?.message || "Request failed.");
        error.code = payload?.error?.code;
        error.status = response.status;
        throw error;
    }
    return payload;
}

function saveSession(payload) {
    state.token = payload.access_token;
    state.user = payload.user;
    localStorage.setItem("tzufguard_access_token", state.token);
}

function logout(showMessage = true) {
    localStorage.removeItem("tzufguard_access_token");
    state.token = null;
    state.user = null;
    state.doors = [];
    authView.classList.remove("hidden");
    dashboardView.classList.add("hidden");
    if (window.google?.accounts?.id) window.google.accounts.id.disableAutoSelect();
    if (showMessage) toast("You have been logged out.");
}

function toast(message) {
    const element = $("#toast");
    element.textContent = message;
    element.classList.add("visible");
    clearTimeout(state.toastTimer);
    state.toastTimer = setTimeout(() => element.classList.remove("visible"), 2800);
}

function setBusy(form, busy, busyText = "Please wait…") {
    const button = form.querySelector("button[type='submit']");
    if (!button) return;
    if (!button.dataset.label) button.dataset.label = button.textContent;
    button.disabled = busy;
    button.textContent = busy ? busyText : button.dataset.label;
}

function openDialog(dialog) {
    if (!dialog.open) dialog.showModal();
}

function closeDialog(dialog) {
    if (dialog.open) dialog.close();
}

function setAuthMode(mode) {
    const registering = mode === "register";
    $("#login-tab").classList.toggle("active", !registering);
    $("#register-tab").classList.toggle("active", registering);
    $("#login-form").classList.toggle("hidden", registering);
    $("#register-form").classList.toggle("hidden", !registering);
    $("#auth-title").textContent = registering ? "Create your account" : "Log in to your account";
    $("#auth-subtitle").textContent = registering ? "Start with your first connected door." : "Your doors are waiting.";
    $("#auth-error").textContent = "";
}

async function handleAuthForm(event, endpoint) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form));
    setBusy(form, true, endpoint === "/auth/register" ? "Creating account…" : "Logging in…");
    $("#auth-error").textContent = "";
    try {
        const payload = await api(endpoint, { method: "POST", body: JSON.stringify(data), handleAuth: false });
        saveSession(payload);
        form.reset();
        await showDashboard();
    } catch (error) {
        $("#auth-error").textContent = errorMessage(error);
    } finally {
        setBusy(form, false);
    }
}

function initGoogle(attempt = 0) {
    const clientId = document.body.dataset.googleClientId;
    if (!clientId) return;
    if (!window.google?.accounts?.id) {
        if (attempt < 40) setTimeout(() => initGoogle(attempt + 1), 150);
        return;
    }
    window.google.accounts.id.initialize({
        client_id: clientId,
        callback: async ({ credential }) => {
            try {
                const payload = await api("/auth/google", { method: "POST", body: JSON.stringify({ id_token: credential }), handleAuth: false });
                saveSession(payload);
                await showDashboard();
            } catch (error) {
                $("#auth-error").textContent = errorMessage(error);
            }
        },
    });
    const buttonWidth = Math.min(360, Math.floor($(".auth-card").clientWidth));
    window.google.accounts.id.renderButton($("#google-button"), {
        theme: "outline", size: "large", shape: "pill", width: buttonWidth,
    });
}

function statusMeta(status) {
    if (status === "opened") return { label: "Open", className: "status--opened" };
    if (status === "closed") return { label: "Closed", className: "status--closed" };
    return { label: "Not connected", className: "status--unknown" };
}

function renderPublicDemo(payload) {
    const available = payload?.available === true;
    const status = available ? payload.status : null;
    publicDemo.classList.remove("is-loading", "is-open", "is-closed", "is-unavailable");
    $("#demo-door-label").textContent = payload?.label || "Amitai's door";

    if (status === "opened") {
        publicDemo.classList.add("is-open");
        $("#demo-door-status").textContent = "Open";
        $("#demo-door-detail").textContent = "The sensor reports that the door is open";
        return;
    }
    if (status === "closed") {
        publicDemo.classList.add("is-closed");
        $("#demo-door-status").textContent = "Closed";
        $("#demo-door-detail").textContent = "The sensor reports that the door is closed";
        return;
    }

    publicDemo.classList.add("is-unavailable");
    $("#demo-door-status").textContent = available ? "Waiting" : "Coming online";
    $("#demo-door-detail").textContent = available
        ? "Waiting for the sensor's first report"
        : "The live sensor demo is being configured";
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

function formatDate(value) {
    if (!value) return "Never reported";
    return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function relativeTime(value) {
    if (!value) return "Waiting for first report";
    const seconds = Math.round((new Date(value).getTime() - Date.now()) / 1000);
    const ranges = [[31536000, "year"], [2592000, "month"], [86400, "day"], [3600, "hour"], [60, "minute"]];
    const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
    for (const [unitSeconds, unit] of ranges) {
        if (Math.abs(seconds) >= unitSeconds) return formatter.format(Math.round(seconds / unitSeconds), unit);
    }
    return formatter.format(seconds, "second");
}

async function showDashboard() {
    authView.classList.add("hidden");
    dashboardView.classList.remove("hidden");
    $("#user-greeting").textContent = state.user?.name ? `Hi, ${state.user.name}` : state.user?.email || "";
    await loadDoors();
}

async function loadDoors(silent = false) {
    if (!silent) {
        doorLoading.classList.remove("hidden");
        doorGrid.classList.add("hidden");
        emptyState.classList.add("hidden");
    }
    try {
        const payload = await api("/doors");
        state.doors = payload.doors;
        renderDoors();
    } catch (error) {
        if (state.token) toast(errorMessage(error));
    } finally {
        doorLoading.classList.add("hidden");
    }
}

function renderSummary() {
    const opened = state.doors.filter(door => door.last_status === "opened").length;
    const closed = state.doors.filter(door => door.last_status === "closed").length;
    $("#summary").innerHTML = [
        [state.doors.length, "Total doors"], [opened, "Open now"], [closed, "Closed now"],
    ].map(([value, label]) => `<div class="summary-item"><strong>${value}</strong><span>${label}</span></div>`).join("");
}

function renderDoors() {
    renderSummary();
    if (!state.doors.length) {
        doorGrid.classList.add("hidden");
        emptyState.classList.remove("hidden");
        return;
    }
    emptyState.classList.add("hidden");
    doorGrid.classList.remove("hidden");
    doorGrid.innerHTML = state.doors.map(door => {
        const status = statusMeta(door.last_status);
        const location = door.location ? `${icon("pin")}${escapeHtml(door.location)}` : "No location set";
        return `<article class="door-card" data-door-id="${door.id}">
            <button class="door-card__main" type="button" data-action="view" aria-label="View ${escapeHtml(door.name)} details">
                <div class="door-card__top"><span class="status-pill ${status.className}">${status.label}</span></div>
                <h2>${escapeHtml(door.name)}</h2><p class="door-location">${location}</p>
                <p class="door-seen">${icon("clock")}<span>${escapeHtml(relativeTime(door.last_seen_at))}</span></p>
                <span class="door-arrow">${icon("chevron")}</span>
            </button>
            <div class="door-card__actions">
                <button class="icon-button" data-action="edit" type="button" aria-label="Edit ${escapeHtml(door.name)}" title="Edit">${icon("edit")}</button>
                <button class="icon-button icon-button--danger" data-action="delete" type="button" aria-label="Delete ${escapeHtml(door.name)}" title="Delete">${icon("trash")}</button>
            </div>
        </article>`;
    }).join("");
}

function findDoor(id) {
    return state.doors.find(door => door.id === Number(id));
}

function openDoorForm(door = null) {
    doorForm.reset();
    $("[data-form-error]", doorForm).textContent = "";
    doorForm.elements.door_id.value = door?.id || "";
    doorForm.elements.name.value = door?.name || "";
    doorForm.elements.location.value = door?.location || "";
    $("#door-form-title").textContent = door ? "Edit door" : "Add a door";
    $("#door-form-eyebrow").textContent = door ? "Door settings" : "New monitor";
    openDialog(doorFormDialog);
    setTimeout(() => doorForm.elements.name.focus(), 50);
}

async function saveDoor(event) {
    event.preventDefault();
    const id = doorForm.elements.door_id.value;
    const payload = { name: doorForm.elements.name.value, location: doorForm.elements.location.value };
    const errorNode = $("[data-form-error]", doorForm);
    errorNode.textContent = "";
    setBusy(doorForm, true, "Saving…");
    try {
        const result = await api(id ? `/doors/${id}` : "/doors", { method: id ? "PATCH" : "POST", body: JSON.stringify(payload) });
        closeDialog(doorFormDialog);
        await loadDoors(true);
        if (!id) {
            $("#provisioning-token").textContent = result.provisioning_token;
            openDialog(tokenDialog);
        } else {
            toast("Door updated.");
        }
    } catch (error) {
        errorNode.textContent = errorMessage(error);
    } finally {
        setBusy(doorForm, false);
    }
}

async function openDoorDetail(door) {
    state.activeDoor = door;
    state.eventPage = 1;
    state.events = [];
    $("#detail-name").textContent = door.name;
    $("#detail-location").textContent = door.location || "No location set";
    $("#history-list").innerHTML = '<div class="history-empty">Loading activity…</div>';
    renderDetailStatus(door);
    openDialog(detailDialog);
    try {
        const [doorPayload, eventsPayload] = await Promise.all([
            api(`/doors/${door.id}`), api(`/doors/${door.id}/events?page=1&per_page=30`),
        ]);
        state.activeDoor = doorPayload.door;
        state.events = eventsPayload.events;
        state.hasMoreEvents = eventsPayload.pagination.has_more;
        $("#detail-name").textContent = state.activeDoor.name;
        $("#detail-location").textContent = state.activeDoor.location || "No location set";
        renderDetailStatus(state.activeDoor);
        renderHistory();
    } catch (error) {
        $("#history-list").innerHTML = `<div class="history-empty">${escapeHtml(errorMessage(error))}</div>`;
    }
}

function renderDetailStatus(door) {
    const status = statusMeta(door.last_status);
    $("#detail-status").innerHTML = `<div><span class="status-pill ${status.className}">${status.label}</span><p>Last report: ${escapeHtml(formatDate(door.last_seen_at))}</p></div><div><strong>${escapeHtml(door.device_name || "Sensor not connected")}</strong></div>`;
}

function renderHistory() {
    const list = $("#history-list");
    if (!state.events.length) {
        list.innerHTML = '<div class="history-empty">No activity yet. Events will appear after the sensor reports a change.</div>';
    } else {
        list.innerHTML = state.events.map(event => {
            const status = statusMeta(event.status);
            return `<div class="history-item ${status.className}"><span class="history-dot"></span><strong>Door ${status.label.toLowerCase()}</strong><time datetime="${escapeHtml(event.received_at)}">${escapeHtml(formatDate(event.received_at))}</time></div>`;
        }).join("");
    }
    $("#load-more-events").classList.toggle("hidden", !state.hasMoreEvents);
}

async function loadMoreEvents() {
    if (!state.activeDoor || !state.hasMoreEvents) return;
    const button = $("#load-more-events");
    button.disabled = true;
    try {
        const nextPage = state.eventPage + 1;
        const payload = await api(`/doors/${state.activeDoor.id}/events?page=${nextPage}&per_page=30`);
        state.eventPage = nextPage;
        state.events.push(...payload.events);
        state.hasMoreEvents = payload.pagination.has_more;
        renderHistory();
    } catch (error) { toast(errorMessage(error)); }
    finally { button.disabled = false; }
}

function showConfirm(title, copy, buttonText, action) {
    $("h2", confirmDialog).textContent = title;
    $("p:not(.eyebrow)", confirmDialog).textContent = copy;
    $("#confirm-delete-button").textContent = buttonText;
    state.confirmAction = action;
    openDialog(confirmDialog);
}

function confirmDelete(door) {
    showConfirm(
        `Delete ${door.name}?`,
        "Its status and complete activity history will be permanently removed.",
        "Delete door",
        async () => {
            await api(`/doors/${door.id}`, { method: "DELETE" });
            closeDialog(detailDialog);
            await loadDoors(true);
            toast("Door deleted.");
        },
    );
}

function confirmRegenerateToken() {
    if (!state.activeDoor) return;
    showConfirm(
        "Generate a new setup phrase?",
        "The current sensor will stop authenticating until you enter the new phrase on its setup page.",
        "Generate phrase",
        async () => {
            const payload = await api(`/doors/${state.activeDoor.id}/setup-token`, { method: "POST" });
            closeDialog(detailDialog);
            $("#provisioning-token").textContent = payload.provisioning_token;
            openDialog(tokenDialog);
        },
    );
}

async function runConfirmAction() {
    const button = $("#confirm-delete-button");
    const action = state.confirmAction;
    if (!action) return;
    button.disabled = true;
    try {
        await action();
        closeDialog(confirmDialog);
    } catch (error) { toast(errorMessage(error)); }
    finally { button.disabled = false; state.confirmAction = null; }
}

async function copyToken() {
    const token = $("#provisioning-token").textContent;
    try {
        await navigator.clipboard.writeText(token);
        toast("Setup phrase copied.");
    } catch {
        const range = document.createRange();
        range.selectNodeContents($("#provisioning-token"));
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        toast("Setup phrase selected. Copy it now.");
    }
}

async function submitForgotPassword(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const errorNode = $("[data-form-error]", form);
    errorNode.textContent = "";
    setBusy(form, true, "Sending…");
    try {
        const payload = await api("/auth/forgot-password", { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(form))), handleAuth: false });
        closeDialog($("#forgot-dialog"));
        form.reset();
        toast(payload.message);
    } catch (error) { errorNode.textContent = errorMessage(error); }
    finally { setBusy(form, false); }
}

async function submitResetPassword(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const resetToken = new URLSearchParams(location.search).get("token");
    const errorNode = $("[data-form-error]", form);
    errorNode.textContent = "";
    setBusy(form, true, "Saving…");
    try {
        await api("/auth/reset-password", { method: "POST", body: JSON.stringify({ token: resetToken, password: form.elements.password.value }), handleAuth: false });
        closeDialog($("#reset-dialog"));
        history.replaceState({}, "", location.pathname);
        form.reset();
        toast("Password updated. You can log in now.");
    } catch (error) { errorNode.textContent = errorMessage(error); }
    finally { setBusy(form, false); }
}

function bindEvents() {
    $("#login-tab").addEventListener("click", () => setAuthMode("login"));
    $("#register-tab").addEventListener("click", () => setAuthMode("register"));
    $("#login-form").addEventListener("submit", event => handleAuthForm(event, "/auth/login"));
    $("#register-form").addEventListener("submit", event => handleAuthForm(event, "/auth/register"));
    $("#logout-button").addEventListener("click", () => logout());
    $("#add-door-button").addEventListener("click", () => openDoorForm());
    $("[data-action='add-door']").addEventListener("click", () => openDoorForm());
    doorForm.addEventListener("submit", saveDoor);
    $("#copy-token-button").addEventListener("click", copyToken);
    $("#token-done-button").addEventListener("click", () => closeDialog(tokenDialog));
    $("#load-more-events").addEventListener("click", loadMoreEvents);
    $("#confirm-delete-button").addEventListener("click", runConfirmAction);
    $("#regenerate-token").addEventListener("click", confirmRegenerateToken);
    $("#forgot-password-button").addEventListener("click", () => openDialog($("#forgot-dialog")));
    $("#forgot-form").addEventListener("submit", submitForgotPassword);
    $("#reset-form").addEventListener("submit", submitResetPassword);
    $$("[data-close]").forEach(button => button.addEventListener("click", () => closeDialog(button.closest("dialog"))));

    doorGrid.addEventListener("click", event => {
        const actionButton = event.target.closest("[data-action]");
        const card = event.target.closest("[data-door-id]");
        if (!actionButton || !card) return;
        const door = findDoor(card.dataset.doorId);
        if (!door) return;
        if (actionButton.dataset.action === "view") openDoorDetail(door);
        if (actionButton.dataset.action === "edit") openDoorForm(door);
        if (actionButton.dataset.action === "delete") confirmDelete(door);
    });

    $("#detail-edit").addEventListener("click", () => {
        if (!state.activeDoor) return;
        closeDialog(detailDialog);
        openDoorForm(state.activeDoor);
    });
    $("#detail-delete").addEventListener("click", () => {
        if (state.activeDoor) confirmDelete(state.activeDoor);
    });
}

async function initialize() {
    bindEvents();
    initGoogle();
    loadPublicDemo();
    if (new URLSearchParams(location.search).get("token")) openDialog($("#reset-dialog"));
    if (!state.token) return;
    try {
        const payload = await api("/me");
        state.user = payload.user;
        await showDashboard();
    } catch {
        logout(false);
    }
}

initialize();
setInterval(() => {
    if (state.token && !dashboardView.classList.contains("hidden")) loadDoors(true);
}, 30000);
setInterval(() => {
    if (!authView.classList.contains("hidden")) loadPublicDemo();
}, 10000);
