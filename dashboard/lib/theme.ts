"use client";

export type Theme = "system" | "light" | "dark";

export const THEME_STORAGE_KEY = "auditagent-theme";

export function getStoredTheme(): Theme {
  if (typeof window === "undefined") return "system";
  const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
  return stored === "light" || stored === "dark" ? stored : "system";
}

function prefersDark(): boolean {
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

/** Applies (or removes) the `dark` class on <html> for the given theme —
 * "system" resolves against the OS/browser preference at call time. */
export function applyTheme(theme: Theme): void {
  const dark = theme === "dark" || (theme === "system" && prefersDark());
  document.documentElement.classList.toggle("dark", dark);
}

export function setTheme(theme: Theme): void {
  if (theme === "system") {
    window.localStorage.removeItem(THEME_STORAGE_KEY);
  } else {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  }
  applyTheme(theme);
}

/** The script string inlined into <head> (see app/layout.tsx) so the right
 * class is set before first paint — no flash of the wrong theme. Kept as a
 * plain string (not a bundled function) since it must run standalone,
 * before any of the app's JS has loaded. */
export const THEME_INIT_SCRIPT = `
(function () {
  try {
    var stored = localStorage.getItem("${THEME_STORAGE_KEY}");
    var dark = stored === "dark" || (stored !== "light" && window.matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.classList.toggle("dark", dark);
  } catch (e) {}
})();
`;
