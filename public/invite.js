import { $, api, clearSession, hasSession } from "/common.js";

const token = new URLSearchParams(location.search).get("token") || "";
const nextPath = `${location.pathname}${location.search}`;
const actions = $("#invite-actions");
const errorNode = $("#invite-error");
let invitation = null;

function button(label, className, onClick) {
    const element = document.createElement("button");
    element.className = className;
    element.type = "button";
    element.textContent = label;
    element.addEventListener("click", onClick);
    return element;
}

function authLink(path, label, primary = false) {
    const link = document.createElement("a");
    link.className = `button ${primary ? "button--forest" : "button--quiet"} button--full`;
    link.href = `${path}?next=${encodeURIComponent(nextPath)}`;
    link.textContent = label;
    link.addEventListener("click", () => {
        try { sessionStorage.setItem("tzufguard_login_email", invitation.email); } catch { /* Optional form prefill. */ }
    });
    return link;
}

function renderAuthenticatedActions() {
    actions.replaceChildren(button("Accept invitation", "button button--forest button--full", acceptInvitation));
    actions.append(button("Switch account", "link-button invite-switch", () => {
        clearSession();
        location.assign(`/login?next=${encodeURIComponent(nextPath)}`);
    }));
}

function renderUnauthenticatedActions() {
    actions.replaceChildren(
        authLink("/login", "Log in", true),
        authLink("/register", "Create an account"),
    );
}

async function acceptInvitation() {
    const acceptButton = actions.querySelector("button");
    acceptButton.disabled = true;
    acceptButton.textContent = "Joining…";
    errorNode.textContent = "";
    try {
        await api("/invitations/accept", {
            method: "POST",
            body: JSON.stringify({ token }),
        });
        $("#invite-title").textContent = "Door added";
        $("#invite-copy").textContent = `${invitation.door_name} is now in your doors list.`;
        $("#invite-email").classList.add("hidden");
        actions.replaceChildren(authLink("/app/doors", "Open your doors", true));
    } catch (error) {
        errorNode.textContent = error.message || "Could not accept this invitation.";
        acceptButton.disabled = false;
        acceptButton.textContent = "Accept invitation";
    }
}

async function initialize() {
    if (!token) {
        $("#invite-title").textContent = "Invitation unavailable";
        $("#invite-copy").textContent = "This invitation link is missing its code.";
        return;
    }
    try {
        const response = await api(`/invitations/preview?token=${encodeURIComponent(token)}`, { redirectOnUnauthorized: false });
        invitation = response.invitation;
        $("#invite-title").textContent = `Monitor ${invitation.door_name}`;
        $("#invite-copy").textContent = `${invitation.inviter_name} invited you to view this door’s status and activity history.`;
        $("#invite-email").textContent = `This invitation is for ${invitation.email}`;
        $("#invite-email").classList.remove("hidden");
        if (hasSession()) renderAuthenticatedActions();
        else renderUnauthenticatedActions();
    } catch (error) {
        $("#invite-title").textContent = "Invitation expired";
        $("#invite-copy").textContent = error.message || "This invitation is no longer active.";
    }
}

initialize();
