import {
    $, $$, api, clearSession, durationMarkup, errorMessage, escapeHtml, formatDate,
    hasSession, icon, leftOpenMarkup, relativeTime, setBusy, statusMeta, updateDurationCounters,
} from "/common.js";
import { historyRange, eventInRange } from "/history.js";
import { disableBrowserAlerts, initializeBrowserAlerts } from "/browser-push.js";

const DOOR_STATUS_EVENT = "door.status.changed";
const DOOR_HEALTH_EVENT = "door.health.changed";
const DOOR_DEVICE_EVENT = "door.device.changed";

if (!hasSession()) location.replace("/login?next=%2Fapp%2Fdoors");

const state = {
    user: null,
    doors: [],
    activeDoor: null,
    sharingDoor: null,
    pendingInvitations: [],
    eventCursor: null,
    historyRange: {},
    historyRequest: 0,
    events: [],
    hasMoreEvents: false,
    confirmAction: null,
    toastTimer: null,
    realtime: null,
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
const sharingDialog = $("#sharing-dialog");

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
    const opened = state.doors.filter(door => door.is_online && door.last_status === "opened").length;
    const closed = state.doors.filter(door => door.is_online && door.last_status === "closed").length;
    const offline = state.doors.filter(door => door.last_seen_at && !door.is_online).length;
    const waiting = state.doors.filter(door => !door.last_seen_at).length;
    $("#summary").innerHTML = `
        <div class="door-overview__total"><span>Monitored entrances</span><strong>${state.doors.length}</strong></div>
        <div class="door-overview__states${waiting ? " door-overview__states--waiting" : ""}">
            <div><i class="state-dot state-dot--open"></i><strong>${opened}</strong><span>Open now</span></div>
            <div><i class="state-dot state-dot--closed"></i><strong>${closed}</strong><span>Closed now</span></div>
            <div><i class="state-dot state-dot--offline"></i><strong>${offline}</strong><span>Offline</span></div>
            ${waiting ? `<div><i class="state-dot state-dot--waiting"></i><strong>${waiting}</strong><span>Waiting</span></div>` : ""}
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
        const hasReported = Boolean(door.last_seen_at);
        const status = statusMeta(door.last_status, door.is_online, hasReported);
        const location = door.location ? `${icon("pin")}${escapeHtml(door.location)}` : "No location set";
        const sensorLabel = !hasReported ? "Waiting for first report" : door.is_online ? "Sensor online" : `Last seen ${escapeHtml(relativeTime(door.last_seen_at))}`;
        const sharedBadge = door.access_role === "member"
            ? `<span class="door-shared-badge">${icon("users")}Shared with you</span>`
            : door.member_count > 0 ? `<span class="door-shared-badge">${icon("users")}Shared</span>` : "";
        const pinnedBadge = door.is_pinned ? `<span class="door-pin">${icon("pin")}Pinned</span>` : "";
        const actions = door.access_role === "owner" ? `<button class="icon-button" data-action="edit" type="button" aria-label="Edit ${escapeHtml(door.name)}" title="Edit">${icon("edit")}</button>
                <button class="icon-button icon-button--danger" data-action="delete" type="button" aria-label="Delete ${escapeHtml(door.name)}" title="Delete">${icon("trash")}</button>` : "";
        return `<article class="door-card" data-door-id="${door.id}">
            <button class="door-card__main" type="button" data-action="view" aria-label="View ${escapeHtml(door.name)} details">
                <div class="door-card__top"><span class="status-pill ${status.className}">${status.label}</span><span class="door-card__top-meta">${durationMarkup(door)}</span></div>${leftOpenMarkup(door)}
                <h2>${escapeHtml(door.name)}</h2><p class="door-location">${location} ${pinnedBadge} ${sharedBadge}</p>
                <p class="door-seen">${icon(!hasReported ? "clock" : door.is_online ? "wifi" : "offline")}<span>${sensorLabel}</span></p>
                <span class="door-arrow">${icon("chevron")}</span>
            </button>
            <div class="door-card__actions">
                ${actions}
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

function renderPendingInvitations() {
    const section = $("#pending-invitations");
    const list = $("#pending-invitation-list");
    section.classList.toggle("hidden", state.pendingInvitations.length === 0);
    list.innerHTML = state.pendingInvitations.map(invitation => `
        <article class="invite-inbox__item" data-invitation-id="${invitation.id}">
            <div class="invite-inbox__icon">${icon("users")}</div>
            <div class="invite-inbox__copy"><strong>${escapeHtml(invitation.door_name)}</strong><span>${escapeHtml(invitation.inviter_name)} invited you to monitor this door${invitation.door_location ? ` · ${escapeHtml(invitation.door_location)}` : ""}</span></div>
            <div class="invite-inbox__actions"><button class="button button--forest button--small" data-invitation-action="accept" type="button">Accept</button><button class="icon-button" data-invitation-action="decline" type="button" aria-label="Dismiss invitation" title="Dismiss">${icon("close")}</button></div>
        </article>`).join("");
}

async function loadPendingInvitations() {
    try {
        const payload = await api("/invitations/pending");
        state.pendingInvitations = payload.invitations;
        renderPendingInvitations();
    } catch (error) {
        if (error.status !== 401) console.warn("Could not load door invitations:", errorMessage(error));
    }
}

async function handlePendingInvitation(event) {
    const button = event.target.closest("[data-invitation-action]");
    const item = event.target.closest("[data-invitation-id]");
    if (!button || !item) return;
    const invitationId = Number(item.dataset.invitationId);
    button.disabled = true;
    try {
        if (button.dataset.invitationAction === "accept") {
            await api(`/invitations/${invitationId}/accept`, { method: "POST" });
            toast("Door added to your account.");
            await loadDoors(true);
        } else {
            await api(`/invitations/${invitationId}/decline`, { method: "POST" });
        }
        state.pendingInvitations = state.pendingInvitations.filter(invitation => invitation.id !== invitationId);
        renderPendingInvitations();
    } catch (error) {
        button.disabled = false;
        toast(errorMessage(error));
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
    const hasReported = Boolean(door.last_seen_at);
    const status = statusMeta(door.last_status, door.is_online, hasReported);
    const reportLabel = !hasReported ? "Waiting for the first sensor report" : `${door.is_online ? "Last report" : "Last sensor contact"}: ${escapeHtml(formatDate(door.last_seen_at))}`;
    $("#detail-status").innerHTML = `<div><span class="status-pill ${status.className}">${status.label}</span>${durationMarkup(door)}${leftOpenMarkup(door)}<p>${reportLabel}</p></div><div><strong>${escapeHtml(door.device_name || "Sensor not connected")}</strong></div>`;
    const offlineAlert = $("#detail-offline-alert");
    const isOffline = hasReported && !door.is_online;
    offlineAlert.classList.toggle("hidden", !isOffline);
    offlineAlert.innerHTML = isOffline ? `${icon("offline")}<div><strong>Sensor offline</strong><span>Check its power cable and Wi-Fi connection.</span></div>` : "";
    $("#detail-firmware-version").textContent = door.firmware_version ? `Version ${door.firmware_version}` : "Version will appear after the next heartbeat";
    const queue = $("#detail-firmware-queue");
    queue.classList.toggle("hidden", !door.firmware_update_requested_at);
    queue.textContent = door.firmware_update_requested_at ? `Version ${door.firmware_update_target_version} queued` : "";
    const isOwner = door.access_role === "owner";
    $("#detail-share").classList.toggle("hidden", !isOwner);
    $("#detail-leave").classList.toggle("hidden", isOwner);
    $("#detail-edit").classList.toggle("hidden", !isOwner);
    $("#detail-delete").classList.toggle("hidden", !isOwner);
    $("#detail-firmware-panel").classList.toggle("hidden", !isOwner);
    $("#regenerate-token").classList.toggle("hidden", !isOwner);
    $("#detail-pin").checked = Boolean(door.is_pinned);
    $("#detail-notifications").checked = Boolean(door.notifications_enabled);
    $("#detail-left-open").value = String(door.left_open_minutes || 0);
    updateDurationCounters();
}

async function updateDoorPreference(field, value) {
    const door = state.activeDoor;
    if (!door) return;
    const control = $(field === "is_pinned" ? "#detail-pin" : field === "left_open_minutes" ? "#detail-left-open" : "#detail-notifications");
    if (control.disabled) return;
    control.disabled = true;
    const previous = door[field];
    state.activeDoor = { ...door, [field]: value };
    state.doors = state.doors.map(item => item.id === door.id ? { ...item, [field]: value } : item);
    renderDoors();
    try {
        const result = await api(`/doors/${door.id}`, {
            method: "PATCH",
            body: JSON.stringify({ [field]: value }),
        });
        state.activeDoor = { ...state.activeDoor, ...result.door };
        state.doors = state.doors.map(item => item.id === door.id ? { ...item, ...result.door } : item);
        renderDoors();
    } catch (error) {
        state.activeDoor = { ...state.activeDoor, [field]: previous };
        state.doors = state.doors.map(item => item.id === door.id ? { ...item, [field]: previous } : item);
        if (field === "left_open_minutes") $("#detail-left-open").value = String(previous || 0);
        else $(field === "is_pinned" ? "#detail-pin" : "#detail-notifications").checked = previous;
        renderDoors();
        toast(errorMessage(error));
    } finally {
        control.disabled = false;
    }
}

function renderHistory() {
    const list = $("#history-list");
    if (!state.events.length) {
        list.innerHTML = '<div class="history-empty">No activity in this date range.</div>';
    } else {
        list.innerHTML = state.events.map(event => {
            const status = statusMeta(event.status);
            return `<div class="history-item ${status.className}"><span class="history-dot"></span><strong>Door ${status.label.toLowerCase()}</strong><time datetime="${escapeHtml(event.received_at)}">${escapeHtml(formatDate(event.received_at))}</time></div>`;
        }).join("");
    }
    $("#load-more-events").classList.toggle("hidden", !state.hasMoreEvents);
}

async function loadHistory(append = false) {
    const doorId = state.activeDoor?.id;
    if (!doorId) return;
    const requestId = ++state.historyRequest;
    const query = new URLSearchParams({ per_page: "30", ...state.historyRange });
    if (append && state.eventCursor) query.set("cursor", state.eventCursor);
    const button = $("#load-more-events");
    button.disabled = true;
    if (!append) {
        state.events = [];
        state.hasMoreEvents = false;
        button.classList.add("hidden");
        $("#history-list").innerHTML = '<div class="history-empty">Loading activity…</div>';
    }
    try {
        const payload = await api(`/doors/${doorId}/events?${query}`);
        if (requestId !== state.historyRequest || state.activeDoor?.id !== doorId) return;
        const combined = [...state.events, ...payload.events];
        state.events = [...new Map(combined.map(event => [event.id, event])).values()]
            .sort((a, b) => new Date(b.received_at) - new Date(a.received_at) || b.id - a.id);
        state.eventCursor = payload.pagination.next_cursor;
        state.hasMoreEvents = payload.pagination.has_more;
        renderHistory();
    } catch (error) {
        if (requestId !== state.historyRequest || state.activeDoor?.id !== doorId) return;
        if (append) toast(errorMessage(error));
        else $("#history-list").innerHTML = `<div class="history-empty">${escapeHtml(errorMessage(error))}</div>`;
    } finally {
        if (requestId === state.historyRequest) button.disabled = false;
    }
}

async function applyHistoryFilter() {
    try {
        state.historyRange = historyRange($("#history-preset").value, $("#history-from").value, $("#history-through").value);
        await loadHistory();
    } catch (error) {
        toast(error.message);
    }
}

async function openDoorDetail(door) {
    state.activeDoor = door;
    state.eventCursor = null;
    state.historyRange = {};
    $("#history-preset").value = "all";
    $("#history-custom-range").classList.add("hidden");
    $("#detail-name").textContent = door.name;
    $("#detail-location").textContent = door.location || "No location set";
    renderDetailStatus(door);
    openDialog(detailDialog);
    await Promise.all([refreshActiveDoor(false), loadHistory()]);
}

async function loadMoreEvents() {
    if (state.hasMoreEvents && !$("#load-more-events").disabled) await loadHistory(true);
}

async function refreshActiveDoor(refreshHistory = true) {
    const doorId = state.activeDoor?.id;
    if (!doorId) return;
    try {
        const { door } = await api(`/doors/${doorId}?include_events=false`);
        if (state.activeDoor?.id !== doorId) return;
        state.activeDoor = door;
        $("#detail-name").textContent = door.name;
        $("#detail-location").textContent = door.location || "No location set";
        renderDetailStatus(door);
        if (refreshHistory) await loadHistory();
    } catch (error) {
        if (error.status !== 401) toast("Live state could not be refreshed.");
    }
}

function applyRealtimeDoorUpdate(payload) {
    const door = payload?.version === 1 ? payload.door : null;
    if (!door || !Number.isInteger(door.id)) return;

    const index = state.doors.findIndex(item => item.id === door.id);
    if (index >= 0) state.doors[index] = { ...state.doors[index], ...door };
    else state.doors.push(door);
    renderDoors();

    if (state.activeDoor?.id !== door.id) return;
    state.activeDoor = { ...state.activeDoor, ...door };
    renderDetailStatus(state.activeDoor);

    const doorEvent = payload.event;
    if (doorEvent && eventInRange(doorEvent, state.historyRange) && !state.events.some(item => item.id === doorEvent.id)) {
        state.events.unshift(doorEvent);
        renderHistory();
    }
}

async function resyncRealtimeState() {
    await Promise.all([loadDoors(true), refreshActiveDoor()]);
}

function stopRealtime() {
    const realtime = state.realtime;
    if (!realtime) return;
    realtime.channel.unsubscribe(DOOR_STATUS_EVENT, realtime.onMessage);
    realtime.channel.unsubscribe(DOOR_HEALTH_EVENT, realtime.onMessage);
    realtime.channel.unsubscribe(DOOR_DEVICE_EVENT, realtime.onMessage);
    realtime.channel.off("attached", realtime.onAttached);
    realtime.channel.off("update", realtime.onUpdate);
    realtime.client.connection.off("failed", realtime.onFailed);
    realtime.channel.detach().catch(() => undefined);
    realtime.client.close();
    state.realtime = null;
}

async function startRealtime() {
    if (!window.AblyPubSub?.createClient) throw new Error("The realtime client did not load.");
    const credentials = await api("/realtime/token", { method: "POST" });
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
                const refreshed = await api("/realtime/token", { method: "POST" });
                callback(null, refreshed.token);
            } catch (error) {
                callback(errorMessage(error), null);
            }
        },
    });
    const channel = client.channels.get(credentials.channel);
    const realtime = {
        client,
        channel,
        attachedOnce: false,
        onMessage: message => applyRealtimeDoorUpdate(message.data),
        onAttached: change => {
            if (realtime.attachedOnce && !change.resumed) resyncRealtimeState();
            realtime.attachedOnce = true;
        },
        onUpdate: change => {
            if (!change.resumed) resyncRealtimeState();
        },
        onFailed: change => {
            console.error("Realtime connection failed:", change.reason?.message || change.reason || "Unknown error");
        },
    };
    state.realtime = realtime;

    // Install continuity handlers before subscribing so no gap can be missed
    // during the initial channel attachment.
    channel.on("attached", realtime.onAttached);
    channel.on("update", realtime.onUpdate);
    client.connection.on("failed", realtime.onFailed);
    await Promise.all([
        channel.subscribe(DOOR_STATUS_EVENT, realtime.onMessage),
        channel.subscribe(DOOR_HEALTH_EVENT, realtime.onMessage),
        channel.subscribe(DOOR_DEVICE_EVENT, realtime.onMessage),
    ]);
}

async function requestFirmwareUpdate() {
    if (!state.activeDoor) return;
    const button = $("#firmware-update-button");
    button.disabled = true;
    const label = $("span", button);
    const previousLabel = label.textContent;
    label.textContent = "Checking…";
    try {
        const payload = await api(`/doors/${state.activeDoor.id}/firmware-update`, { method: "POST" });
        state.activeDoor = { ...state.activeDoor, ...payload.door };
        const index = state.doors.findIndex(door => door.id === state.activeDoor.id);
        if (index >= 0) state.doors[index] = { ...state.doors[index], ...payload.door };
        renderDoors();
        renderDetailStatus(state.activeDoor);
        toast(payload.firmware_update.status === "queued"
            ? `Version ${payload.firmware_update.target_version} queued for the next heartbeat.`
            : `Firmware ${payload.firmware_update.target_version} is already installed.`);
    } catch (error) {
        toast(errorMessage(error));
    } finally {
        button.disabled = false;
        label.textContent = previousLabel;
    }
}

function showConfirm(title, copy, buttonText, action) {
    $("h2", confirmDialog).textContent = title;
    $("p:not(.eyebrow)", confirmDialog).textContent = copy;
    $("#confirm-delete-button").textContent = buttonText;
    state.confirmAction = action;
    openDialog(confirmDialog);
}

function invitationLinkPreview(url) {
    const tokenMarker = url.indexOf("?token=");
    if (tokenMarker >= 0) return `${url.slice(0, tokenMarker)}?token=...`;
    const maxLength = 44;
    return url.length > maxLength ? `${url.slice(0, maxLength - 3)}...` : url;
}

function renderSharing(payload) {
    const owner = payload.owner;
    const members = payload.members;
    const invitations = payload.invitations;
    $("#sharing-members").innerHTML = [
        `<div class="sharing-person"><span class="sharing-avatar">${escapeHtml((owner.name || owner.email || "O").charAt(0).toUpperCase())}</span><div><strong>${escapeHtml(owner.name || owner.email)}</strong><span>${escapeHtml(owner.email)} · Owner</span></div></div>`,
        ...members.map(member => `<div class="sharing-person" data-sharing-member="${member.user_id}"><span class="sharing-avatar">${escapeHtml((member.name || member.email || "M").charAt(0).toUpperCase())}</span><div><strong>${escapeHtml(member.name || member.email)}</strong><span>${escapeHtml(member.email)} · Member</span></div><button class="icon-button icon-button--danger" data-sharing-action="remove-member" data-user-id="${member.user_id}" type="button" aria-label="Remove ${escapeHtml(member.email)}" title="Remove access">${icon("trash")}</button></div>`),
    ].join("");
    $("#sharing-invitations").innerHTML = invitations.length
        ? invitations.map(invitation => `<div class="sharing-person" data-sharing-invitation="${invitation.id}"><span class="sharing-avatar sharing-avatar--pending">${icon("clock")}</span><div><strong>${escapeHtml(invitation.email)}</strong><span>Invited by ${escapeHtml(invitation.inviter_name)} · Expires ${escapeHtml(formatDate(invitation.expires_at))}</span></div><button class="icon-button" data-sharing-action="revoke-invitation" data-invitation-id="${invitation.id}" type="button" aria-label="Cancel invitation to ${escapeHtml(invitation.email)}" title="Cancel invitation">${icon("close")}</button></div>`).join("")
        : '<p class="sharing-empty">No pending invitations.</p>';
}

async function openSharing(door) {
    if (!door || door.access_role !== "owner") return;
    state.sharingDoor = door;
    $("#sharing-door-name").textContent = door.name;
    $("#sharing-form").reset();
    $("[data-form-error]", $("#sharing-form")).textContent = "";
    $("#invite-link-fallback").classList.add("hidden");
    openDialog(sharingDialog);
    try {
        const payload = await api(`/doors/${door.id}/sharing`);
        renderSharing(payload);
    } catch (error) {
        toast(errorMessage(error));
    }
}

async function sendDoorInvitation(event) {
    event.preventDefault();
    if (!state.sharingDoor) return;
    const form = $("#sharing-form");
    const errorNode = $("[data-form-error]", form);
    errorNode.textContent = "";
    setBusy(form, true, "Sending…");
    try {
        const payload = await api(`/doors/${state.sharingDoor.id}/invitations`, {
            method: "POST",
            body: JSON.stringify({ email: form.elements.email.value.trim() }),
        });
        form.reset();
        const inviteLinkValue = $("#invite-link-value");
        inviteLinkValue.textContent = invitationLinkPreview(payload.invitation_url);
        inviteLinkValue.title = payload.invitation_url;
        inviteLinkValue.dataset.url = payload.invitation_url;
        $("#invite-link-message").textContent = payload.email_sent
            ? `Invitation email sent to ${payload.invitation.email}. You can also share the link directly.`
            : payload.email_delivery === "queued"
                ? `Invitation email is queued for ${payload.invitation.email}. You can also share the link directly.`
                : `Email could not be sent to ${payload.invitation.email}. You can still share the link directly.`;
        $("#invite-link-fallback").classList.remove("hidden");
        toast(payload.email_sent
            ? `Invitation email sent to ${payload.invitation.email}.`
            : payload.email_delivery === "queued" ? "Invitation email queued. The link is ready to share." : "Email could not be sent. The invite link is ready to share.");
        renderSharing(await api(`/doors/${state.sharingDoor.id}/sharing`));
    } catch (error) {
        errorNode.textContent = errorMessage(error);
    } finally {
        setBusy(form, false);
    }
}

async function handleSharingAction(event) {
    const button = event.target.closest("[data-sharing-action]");
    if (!button || !state.sharingDoor) return;
    const action = button.dataset.sharingAction;
    const memberId = Number(button.dataset.userId);
    const invitationId = Number(button.dataset.invitationId);
    const isMember = action === "remove-member";
    const email = button.closest(".sharing-person").querySelector("strong")?.textContent || "this person";
    showConfirm(
        isMember ? `Remove ${email}?` : `Cancel invitation to ${email}?`,
        isMember ? "They will immediately lose access to this door and its history." : "The invitation link will stop working.",
        isMember ? "Remove access" : "Cancel invitation",
        async () => {
            await api(
                isMember
                    ? `/doors/${state.sharingDoor.id}/members/${memberId}`
                    : `/doors/${state.sharingDoor.id}/invitations/${invitationId}`,
                { method: "DELETE" },
            );
            renderSharing(await api(`/doors/${state.sharingDoor.id}/sharing`));
            toast(isMember ? `${email} no longer has access.` : `Invitation to ${email} cancelled.`);
        },
    );
}

async function leaveSharedDoor() {
    const door = state.activeDoor;
    if (!door || door.access_role !== "member") return;
    showConfirm(
        `Leave ${door.name}?`,
        "This door will be removed from your account. The owner can invite you again later.",
        "Leave door",
        async () => {
            await api(`/doors/${door.id}/membership`, { method: "DELETE" });
            state.activeDoor = null;
            closeDialog(detailDialog);
            state.doors = state.doors.filter(item => item.id !== door.id);
            renderDoors();
            toast("Door removed from your account.");
        },
    );
}

function confirmDelete(door) {
    showConfirm(
        `Delete ${door.name}?`,
        "Its status and complete activity history will be permanently removed. Anyone it is shared with will also lose access.",
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
    $("#logout-button").addEventListener("click", async () => {
        await disableBrowserAlerts().catch(() => undefined);
        stopRealtime();
        clearSession();
        location.assign("/");
    });
    const deleteAccountDialog = $("#delete-account-dialog");
    const deleteAccountForm = $("#delete-account-form");
    $("#delete-account-open").addEventListener("click", () => {
        $("#account-menu").open = false;
        $("#delete-account-email").textContent = state.user?.email || "your account email";
        deleteAccountForm.reset();
        $("[data-form-error]", deleteAccountForm).textContent = "";
        openDialog(deleteAccountDialog);
        setTimeout(() => $("#delete-account-confirmation").focus(), 50);
    });
    deleteAccountForm.addEventListener("submit", async event => {
        event.preventDefault();
        const errorNode = $("[data-form-error]", deleteAccountForm);
        errorNode.textContent = "";
        setBusy(deleteAccountForm, true, "Deleting…");
        try {
            await api("/me", {
                method: "DELETE",
                body: JSON.stringify({ confirmation_email: deleteAccountForm.elements.confirmation_email.value }),
            });
            stopRealtime();
            clearSession();
            location.assign("/");
        } catch (error) {
            errorNode.textContent = errorMessage(error);
        } finally {
            setBusy(deleteAccountForm, false);
        }
    });
    $("#add-door-button").addEventListener("click", () => openDoorForm());
    $("[data-action='add-door']").addEventListener("click", () => openDoorForm());
    $("#retry-doors").addEventListener("click", () => loadDoors());
    doorForm.addEventListener("submit", saveDoor);
    $("#copy-token-button").addEventListener("click", copyToken);
    $("#token-done-button").addEventListener("click", () => closeDialog(tokenDialog));
    $("#load-more-events").addEventListener("click", loadMoreEvents);
    $("#detail-left-open").addEventListener("change", event => updateDoorPreference("left_open_minutes", Number(event.target.value)));
    $("#history-preset").addEventListener("change", () => {
        const custom = $("#history-preset").value === "custom";
        $("#history-custom-range").classList.toggle("hidden", !custom);
        if (!custom) applyHistoryFilter();
    });
    $("#history-apply").addEventListener("click", applyHistoryFilter);
    $("#confirm-delete-button").addEventListener("click", runConfirmAction);
    $("#regenerate-token").addEventListener("click", confirmRegenerateToken);
    $("#firmware-update-button").addEventListener("click", requestFirmwareUpdate);
    $("#detail-share").addEventListener("click", () => openSharing(state.activeDoor));
    $("#detail-leave").addEventListener("click", leaveSharedDoor);
    $("#detail-pin").addEventListener("change", event => updateDoorPreference("is_pinned", event.target.checked));
    $("#detail-notifications").addEventListener("change", event => updateDoorPreference("notifications_enabled", event.target.checked));
    $("#sharing-form").addEventListener("submit", sendDoorInvitation);
    $("#sharing-members").addEventListener("click", handleSharingAction);
    $("#sharing-invitations").addEventListener("click", handleSharingAction);
    $("#pending-invitation-list").addEventListener("click", handlePendingInvitation);
    $("#copy-invite-link").addEventListener("click", async () => {
        const linkNode = $("#invite-link-value");
        const url = linkNode.dataset.url || linkNode.textContent;
        try {
            await navigator.clipboard.writeText(url);
            toast("Invitation link copied.");
        } catch {
            const range = document.createRange();
            range.selectNodeContents(linkNode);
            const selection = window.getSelection();
            selection.removeAllRanges();
            selection.addRange(range);
            toast("Invitation link selected. Copy it now.");
        }
    });
    $("#share-invite-link").addEventListener("click", async () => {
        const url = $("#invite-link-value").dataset.url || $("#invite-link-value").textContent;
        if (navigator.share) {
            try {
                await navigator.share({ title: "TzufGuard door invitation", url });
                return;
            } catch (error) {
                if (error.name === "AbortError") return;
            }
        }
        try {
            await navigator.clipboard.writeText(url);
            toast("Invitation link copied.");
        } catch {
            const linkNode = $("#invite-link-value");
            const range = document.createRange();
            range.selectNodeContents(linkNode);
            const selection = window.getSelection();
            selection.removeAllRanges();
            selection.addRange(range);
            toast("Invitation link selected. Copy it now.");
        }
    });
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
        $("#user-greeting").textContent = state.user?.name || state.user?.email || "Account";
        $("#user-avatar").textContent = (state.user?.name || state.user?.email || "A").charAt(0).toUpperCase();
        await loadDoors();
        const requestedDoor = Number(new URLSearchParams(location.search).get("door"));
        const notificationDoor = state.doors.find(door => door.id === requestedDoor);
        if (notificationDoor) await openDoorDetail(notificationDoor);
        initializeBrowserAlerts().catch(error => console.error("Browser alerts unavailable:", errorMessage(error)));
        await loadPendingInvitations();
        startRealtime().catch(error => {
            console.error("Realtime updates are unavailable:", errorMessage(error));
        });
    } catch (error) {
        if (error.status !== 401) doorError.classList.remove("hidden");
    }
}

initialize();
setInterval(updateDurationCounters, 1000);
document.addEventListener("click", event => {
    const menu = $("#account-menu");
    if (menu.open && !menu.contains(event.target)) menu.open = false;
});
document.addEventListener("keydown", event => {
    if (event.key === "Escape") $("#account-menu").open = false;
});
document.addEventListener("visibilitychange", () => {
    if (!document.hidden && hasSession()) resyncRealtimeState();
});
window.addEventListener("pagehide", stopRealtime);
