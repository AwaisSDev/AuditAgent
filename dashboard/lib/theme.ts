"use client";

export type Theme = "system" | "light" | "dark";

export const THEME_STORAGE_KEY = "tracyn-theme";

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

// Public/marketing pages are always light, regardless of stored preference
// or OS setting -- theming is a dashboard (post-login) feature only.
const ALWAYS_LIGHT_PATHS = ["/", "/docs"];

function isAlwaysLightPath(pathname: string): boolean {
  return ALWAYS_LIGHT_PATHS.some((p) => (p === "/" ? pathname === "/" : pathname === p || pathname.startsWith(`${p}/`)));
}

/** The script string inlined into <head> (see app/layout.tsx) so the right
 * class is set before first paint — no flash of the wrong theme. Kept as a
 * plain string (not a bundled function) since it must run standalone,
 * before any of the app's JS has loaded. */
export const THEME_INIT_SCRIPT = `
(function () {
  try {
    var alwaysLight = ${JSON.stringify(ALWAYS_LIGHT_PATHS)}.some(function (p) {
      return p === "/" ? location.pathname === "/" : location.pathname === p || location.pathname.indexOf(p + "/") === 0;
    });
    if (alwaysLight) return;
    var stored = localStorage.getItem("${THEME_STORAGE_KEY}");
    var dark = stored === "dark" || (stored !== "light" && window.matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.classList.toggle("dark", dark);
  } catch (e) {}
})();
`;

/** Client-side navigation between routes (next/link) never re-runs the
 * inline script above, so a page reached that way (e.g. clicking from an
 * authenticated dark-mode page to the public landing/docs pages) would
 * otherwise keep whatever `dark` class was already on <html>. Call this
 * from those pages so they're always light no matter how they were
 * reached, and restore the user's actual preference again on the way out
 * (see app-shell.tsx). */
export function forceLightTheme(): void {
  document.documentElement.classList.remove("dark");
}

export function restoreStoredTheme(): void {
  if (typeof window === "undefined") return;
  if (!isAlwaysLightPath(window.location.pathname)) applyTheme(getStoredTheme());
}
