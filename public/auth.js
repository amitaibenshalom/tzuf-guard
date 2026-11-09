import { $, $$, api, errorMessage, hasSession, safeNextPath, saveSession, setBusy } from "/common.js";

if (hasSession()) location.replace(safeNextPath());

const form = $("#auth-form");
const errorNode = $("#auth-error");
const mode = document.body.dataset.authMode;
const LOGIN_EMAIL_KEY = "tzufguard_login_email";

function showAuthError(error) {
    errorNode.replaceChildren(document.createTextNode(errorMessage(error)));
    if (error.code === "duplicate_email" && mode === "register") {
        sessionStorage.setItem(LOGIN_EMAIL_KEY, form.elements.email.value.trim());
        const loginLink = document.createElement("a");
        loginLink.href = "/login";
        loginLink.textContent = " Log in instead.";
        errorNode.append(loginLink);
    } else if (error.code === "google_link_requires_password") {
        const loginLink = document.createElement("a");
        const email = form.elements.email?.value.trim();
        if (email) sessionStorage.setItem(LOGIN_EMAIL_KEY, email);
        loginLink.href = "/login";
        loginLink.textContent = " Go to email login.";
        errorNode.append(loginLink);
    }
}

function toast(message) {
    const element = $("#toast");
    element.textContent = message;
    element.classList.add("visible");
    setTimeout(() => element.classList.remove("visible"), 3200);
}

function openDialog(dialog) {
    if (dialog && !dialog.open) dialog.showModal();
}

function closeDialog(dialog) {
    if (dialog?.open) dialog.close();
}

async function completeAuthentication(payload) {
    saveSession(payload);
    location.assign(safeNextPath());
}

form.addEventListener("submit", async event => {
    event.preventDefault();
    errorNode.textContent = "";
    setBusy(form, true, mode === "register" ? "Creating account…" : "Logging in…");
    try {
        const payload = await api(form.dataset.endpoint, {
            method: "POST",
            body: JSON.stringify(Object.fromEntries(new FormData(form))),
            redirectOnUnauthorized: false,
        });
        await completeAuthentication(payload);
    } catch (error) {
        showAuthError(error);
    } finally {
        setBusy(form, false);
    }
});

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
            errorNode.textContent = "";
            try {
                const payload = await api("/auth/google", {
                    method: "POST",
                    body: JSON.stringify({ id_token: credential }),
                    redirectOnUnauthorized: false,
                });
                await completeAuthentication(payload);
            } catch (error) {
                showAuthError(error);
            }
        },
    });
    renderGoogleButton();
}

function renderGoogleButton() {
    if (!window.google?.accounts?.id || !$("#google-button")) return;
    const width = Math.min(400, Math.floor($(".auth-card").clientWidth));
    $("#google-button").replaceChildren();
    window.google.accounts.id.renderButton($("#google-button"), {
        theme: document.documentElement.dataset.theme === "dark" ? "filled_black" : "outline",
        size: "large", shape: "pill", width,
    });
}

window.addEventListener("tzufguard:themechange", renderGoogleButton);

const forgotButton = $("#forgot-password-button");
const forgotForm = $("#forgot-form");
if (forgotButton && forgotForm) {
    forgotButton.addEventListener("click", () => openDialog($("#forgot-dialog")));
    forgotForm.addEventListener("submit", async event => {
        event.preventDefault();
        const formError = $("[data-form-error]", forgotForm);
        formError.textContent = "";
        setBusy(forgotForm, true, "Sending…");
        try {
            const payload = await api("/auth/forgot-password", {
                method: "POST",
                body: JSON.stringify(Object.fromEntries(new FormData(forgotForm))),
                redirectOnUnauthorized: false,
            });
            closeDialog($("#forgot-dialog"));
            forgotForm.reset();
            toast(payload.message);
        } catch (error) {
            formError.textContent = errorMessage(error);
        } finally {
            setBusy(forgotForm, false);
        }
    });
}

$$('[data-close]').forEach(button => button.addEventListener("click", () => closeDialog(button.closest("dialog"))));
if (new URLSearchParams(location.search).has("expired")) errorNode.textContent = "Your session expired. Log in again to continue.";
initGoogle();
const invitationEmail = sessionStorage.getItem(LOGIN_EMAIL_KEY);
if (invitationEmail && form.elements.email) {
    form.elements.email.value = invitationEmail;
    sessionStorage.removeItem(LOGIN_EMAIL_KEY);
}
