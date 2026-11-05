import {
    $, $$, api, clearSession, durationMarkup, errorMessage, escapeHtml, formatDate,
    hasSession, icon, relativeTime, setBusy, statusMeta, updateDurationCounters,
} from "/common.js";

if (!hasSession()) location.replace("/login?next=%2Fapp%2Fdoors");

const state = {
    user: null,
    doors: [],
    activeDoor: null,
    eventPage: 1,
    events: [],
    hasMoreEvents: false,
    confirmAction: null,
    toastTimer: null,
};

const doorGrid = $("#door-grid");
const doorLoading = $("#door-loading");
const emptyState = $("#empty-state");
const doorError = $("#door-error");
const doorFormDialog = $("#door-form-dialog");
const doorForm = $("#door-form");
const tokenDialog = $("#token-dialog");
const detailDialog = $("#door-detail-dialog");
const confirmDialog = $("#confirm-dialog");

function toast(message) {
    const element = $("#toast");
    element.textContent = message;
    element.classList.add("visible");
    clearTimeout(state.toastTimer);
    state.toastTimer = setTimeout(() => element.classList.remove("visible"), 2800);
}

function openDialog(dialog) {
    if (!dialog.open) dialog.showModal();
}

function closeDialog(dialog) {
    if (dialog?.open) dialog.close();
}

function renderSummary() {
    const opened = state.doors.filter(door => door.last_status === "opened").length;
    const closed = state.doors.filter(door => door.last_status === "closed").length;
    const waiting = state.doors.length - opened - closed;
    $("#summary").innerHTML = `
        <div class="door-overview__total"><span>Monitored entrances</span><strong>${state.doors.length}</strong></div>
        <div class="door-overview__states">
            <div><i class="state-dot state-dot--open"></i><strong>${opened}</strong><span>Open now</span></div>
            <div><i class="state-dot state-dot--closed"></i><strong>${closed}</strong><span>Closed now</span></div>
            <div><i class="state-dot state-dot--waiting"></i><strong>${waiting}</strong><span>Waiting</span></div>
        </div>`;
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
                <div class="door-card__top"><span class="status-pill ${status.className}">${status.label}</span>${durationMarkup(door)}</div>
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
    updateDurationCounters();
}

async function loadDoors(silent = false) {
    if (!silent) {
        doorLoading.classList.remove("hidden");
        doorGrid.classList.add("hidden");
        emptyState.classList.add("hidden");
    }
    doorError.classList.add("hidden");
    try {
        const payload = await api("/doors");
        state.doors = payload.doors;
        renderDoors();
    } catch (error) {
        if (error.status !== 401) {
            doorError.classList.remove("hidden");
            if (silent) toast(errorMessage(error));
        }
    } finally {
        doorLoading.classList.add("hidden");
    }
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
        const result = await api(id ? `/doors/${id}` : "/doors", {
            method: id ? "PATCH" : "POST",
            body: JSON.stringify(payload),
        });
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

function renderDetailStatus(door) {
    const status = statusMeta(door.last_status);
    $("#detail-status").innerHTML = `<div><span class="status-pill ${status.className}">${status.label}</span>${durationMarkup(door)}<p>Last report: ${escapeHtml(formatDate(door.last_seen_at))}</p></div><div><strong>${escapeHtml(door.device_name || "Sensor not connected")}</strong></div>`;
    updateDurationCounters();
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
            api(`/doors/${door.id}`),
            api(`/doors/${door.id}/events?page=1&per_page=30`),
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
    } catch (error) {
        toast(errorMessage(error));
    } finally {
        button.disabled = false;
    }
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
    } catch (error) {
        toast(errorMessage(error));
    } finally {
        button.disabled = false;
        state.confirmAction = null;
    }
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

function bindEvents() {
    $("#logout-button").addEventListener("click", () => {
        clearSession();
        location.assign("/");
    });
    $("#add-door-button").addEventListener("click", () => openDoorForm());
    $("[data-action='add-door']").addEventListener("click", () => openDoorForm());
    $("#retry-doors").addEventListener("click", () => loadDoors());
    doorForm.addEventListener("submit", saveDoor);
    $("#copy-token-button").addEventListener("click", copyToken);
    $("#token-done-button").addEventListener("click", () => closeDialog(tokenDialog));
    $("#load-more-events").addEventListener("click", loadMoreEvents);
    $("#confirm-delete-button").addEventListener("click", runConfirmAction);
    $("#regenerate-token").addEventListener("click", confirmRegenerateToken);
    $$('[data-close]').forEach(button => button.addEventListener("click", () => closeDialog(button.closest("dialog"))));

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
    if (!hasSession()) return;
    bindEvents();
    try {
        const payload = await api("/me");
        state.user = payload.user;
        $("#user-greeting").textContent = state.user?.name || state.user?.email || "";
        await loadDoors();
    } catch (error) {
        if (error.status !== 401) doorError.classList.remove("hidden");
    }
}

initialize();
setInterval(updateDurationCounters, 1000);
setInterval(() => {
    if (!document.hidden) loadDoors(true);
}, 30000);
document.addEventListener("visibilitychange", () => {
    if (!document.hidden && hasSession()) loadDoors(true);
});
