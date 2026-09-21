import { useState } from "react";
import { applyTheme, resolveInitialTheme, setStoredTheme, type Theme } from "../lib/theme";

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(() => resolveInitialTheme());

  const toggle = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    applyTheme(next);
    setStoredTheme(next);
  };

  return (
    <button
      className="theme-toggle"
      data-testid="theme-toggle"
      aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
      onClick={toggle}
    >
      {theme === "dark" ? "🌙" : "☀️"}
    </button>
  );
}
