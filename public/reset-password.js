import { $, api, errorMessage, setBusy } from "/common.js";

const form = $("#reset-form");
const errorNode = $("#reset-error");
const token = new URLSearchParams(location.search).get("token");

if (!token) {
    errorNode.textContent = "This reset link is missing its security token. Request a new password reset email.";
    form.querySelector("button[type='submit']").disabled = true;
}

form.addEventListener("submit", async event => {
    event.preventDefault();
    errorNode.textContent = "";
    setBusy(form, true, "Saving…");
    try {
        await api("/auth/reset-password", {
            method: "POST",
            body: JSON.stringify({ token, password: form.elements.password.value }),
            redirectOnUnauthorized: false,
        });
        form.innerHTML = '<div class="success-mark"><svg aria-hidden="true"><use href="#icon-shield"></use></svg></div><p class="eyebrow">Password updated</p><h1>You are ready to return.</h1><p>Your new password is active. You can now log in to your account.</p><a class="button button--forest button--full" href="/login">Continue to log in</a>';
    } catch (error) {
        errorNode.textContent = errorMessage(error);
    } finally {
        setBusy(form, false);
    }
});
