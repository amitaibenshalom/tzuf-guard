// Run before styles load so a saved dark preference never flashes a light page.
(() => {
    const storageKey = "tzufguard_theme";
    const systemTheme = window.matchMedia("(prefers-color-scheme: dark)");
    const validPreference = value => ["light", "dark", "system"].includes(value) ? value : "light";
    const forceLight = location.pathname === "/" || /^\/(login|register)\/?$/.test(location.pathname);
    let preference = "light";
    try {
        preference = validPreference(localStorage.getItem(storageKey));
    } catch {
        // The selector still works for this page when browser storage is blocked.
    }

    function applyTheme() {
        const theme = forceLight ? "light" : preference === "system" ? (systemTheme.matches ? "dark" : "light") : preference;
        const changed = document.documentElement.dataset.theme !== theme;
        document.documentElement.dataset.theme = theme;
        document.querySelectorAll("[data-theme-preference]").forEach(control => {
            control.value = preference;
        });
        const themeColor = document.querySelector('meta[name="theme-color"]');
        if (themeColor) themeColor.content = theme === "dark" ? "#091712" : location.pathname === "/" ? "#102f27" : "#f7f8f4";
        if (changed) window.dispatchEvent(new CustomEvent("tzufguard:themechange", { detail: { theme } }));
    }

    applyTheme();
    document.addEventListener("DOMContentLoaded", () => {
        applyTheme();
        document.querySelectorAll("[data-theme-preference]").forEach(control => {
            control.addEventListener("change", () => {
                preference = validPreference(control.value);
                try {
                    localStorage.setItem(storageKey, preference);
                } catch {
                    // Preserve the in-memory choice for this visit.
                }
                applyTheme();
            });
        });
    });
    systemTheme.addEventListener("change", applyTheme);
    window.addEventListener("storage", event => {
        if (event.key === storageKey || event.key === null) {
            preference = validPreference(event.newValue);
            applyTheme();
        }
    });
})();
