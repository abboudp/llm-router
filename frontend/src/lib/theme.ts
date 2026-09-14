export type Theme = "light" | "dark";

const STORAGE_KEY = "llm-router-theme";

/** Reads the user's explicitly-chosen theme, if any was ever saved. */
export function getStoredTheme(): Theme | null {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    // Storage can be unavailable (private browsing, disabled cookies, quota).
    return null;
  }
}

/** Persists an explicit theme choice. Silently no-ops if storage fails. */
export function setStoredTheme(theme: Theme): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    /* the theme just won't be remembered next visit */
  }
}

/**
 * The theme to render on load: the user's saved choice if there is one,
 * otherwise the OS/browser's light/dark preference, otherwise light.
 */
export function resolveInitialTheme(): Theme {
  const stored = getStoredTheme();
  if (stored) return stored;
  try {
    if (window.matchMedia?.("(prefers-color-scheme: dark)").matches) return "dark";
  } catch {
    /* matchMedia unavailable in this environment */
  }
  return "light";
}

/** Applies a theme by setting the attribute app.css keys its variables off of. */
export function applyTheme(theme: Theme): void {
  document.documentElement.setAttribute("data-theme", theme);
}
