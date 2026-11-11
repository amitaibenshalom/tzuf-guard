let installPrompt = null;
if ("serviceWorker" in navigator) {
    navigator.serviceWorker.getRegistrations().then(async registrations => {
        for (const registration of registrations) {
            const worker = registration.active || registration.waiting || registration.installing;
            if (!worker || new URL(worker.scriptURL).pathname !== "/notifications-sw.js") continue;
            try {
                const subscription = await registration.pushManager?.getSubscription();
                if (subscription) await subscription.unsubscribe();
            } finally {
                await registration.unregister();
            }
        }
    }).catch(() => undefined);
}
const installButtons = [...document.querySelectorAll("[data-install-app]")];
const isStandalone = window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
const isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent)
    || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
const isMobile = window.matchMedia("(pointer: coarse)").matches;

if (!isStandalone && isMobile) installButtons.forEach(button => { button.hidden = false; });
if (isStandalone) installButtons.forEach(button => { button.hidden = true; });

window.addEventListener("beforeinstallprompt", event => {
    event.preventDefault();
    installPrompt = event;
    installButtons.forEach(button => { button.hidden = false; });
});

function showManualInstallHelp() {
    let dialog = document.querySelector("#pwa-install-help");
    if (!dialog) {
        dialog = document.createElement("dialog");
        dialog.id = "pwa-install-help";
        dialog.className = "modal modal--narrow pwa-install-dialog";
        const instructions = isIOS
            ? ["Open this page in Safari.", "Tap the Share button.", "Choose Add to Home Screen, then tap Add."]
            : ["Open your browser menu.", "Choose Install app or Add to Home screen.", "Confirm the installation."];
        dialog.innerHTML = `<section class="modal-card"><div class="modal-head"><div><p class="eyebrow">TzufGuard app</p><h2>Install TzufGuard</h2></div><button class="icon-button" type="button" aria-label="Close" data-install-help-close>×</button></div><p>Add TzufGuard to your home screen for quick access in its own app window.</p><ol>${instructions.map(item => `<li>${item}</li>`).join("")}</ol><button class="button button--forest button--full" type="button" data-install-help-close>Got it</button></section>`;
        document.body.append(dialog);
        dialog.querySelectorAll("[data-install-help-close]").forEach(button => {
            button.addEventListener("click", () => dialog.close());
        });
        dialog.addEventListener("click", event => {
            if (event.target === dialog) dialog.close();
        });
    }
    if (!dialog.open) dialog.showModal();
}

installButtons.forEach(button => {
    button.addEventListener("click", async () => {
        if (!installPrompt) {
            showManualInstallHelp();
            return;
        }
        installPrompt.prompt();
        const choice = await installPrompt.userChoice;
        if (choice.outcome === "accepted") installButtons.forEach(item => { item.hidden = true; });
        installPrompt = null;
    });
});

window.addEventListener("appinstalled", () => {
    installPrompt = null;
    installButtons.forEach(button => { button.hidden = true; });
});
