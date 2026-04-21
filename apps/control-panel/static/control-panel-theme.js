(() => {
  const storageKey = "prism-theme-mode";
  const root = document.documentElement;
  const mediaQuery =
    typeof window.matchMedia === "function"
      ? window.matchMedia("(prefers-color-scheme: light)")
      : null;

  function normalizeMode(mode) {
    return ["light", "dark", "system"].includes(mode) ? mode : "system";
  }

  function readMode() {
    try {
      return normalizeMode(window.localStorage.getItem(storageKey));
    } catch (error) {
      return normalizeMode(root.dataset.themeMode);
    }
  }

  function resolvedTheme(mode) {
    if (mode === "system") {
      return mediaQuery && mediaQuery.matches ? "light" : "dark";
    }
    return mode;
  }

  function persistMode(mode) {
    try {
      window.localStorage.setItem(storageKey, mode);
    } catch (error) {
      return;
    }
  }

  function updateButtons(mode) {
    document.querySelectorAll("[data-theme-option]").forEach((button) => {
      const active = button.dataset.themeOption === mode;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }

  function applyTheme(mode, options = {}) {
    const nextMode = normalizeMode(mode);
    const appliedTheme = resolvedTheme(nextMode);
    root.dataset.themeMode = nextMode;
    root.dataset.themeApplied = appliedTheme;
    root.style.colorScheme = appliedTheme;
    updateButtons(nextMode);
    if (options.persist) {
      persistMode(nextMode);
    }
  }

  function handleThemeClick(event) {
    const mode = event.currentTarget?.dataset.themeOption;
    if (!mode) {
      return;
    }
    applyTheme(mode, { persist: true });
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-theme-option]").forEach((button) => {
      button.addEventListener("click", handleThemeClick);
    });
    applyTheme(readMode());
  });

  if (mediaQuery) {
    const handleSystemThemeChange = () => {
      if (normalizeMode(root.dataset.themeMode) === "system") {
        applyTheme("system");
      }
    };
    if (typeof mediaQuery.addEventListener === "function") {
      mediaQuery.addEventListener("change", handleSystemThemeChange);
    } else if (typeof mediaQuery.addListener === "function") {
      mediaQuery.addListener(handleSystemThemeChange);
    }
  }
})();
