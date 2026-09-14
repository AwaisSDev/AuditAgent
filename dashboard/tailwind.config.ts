import type { Config } from "tailwindcss";

const config: Config = {
  // Class-based: lib/theme.ts applies/removes `dark` on <html>, defaulting
  // to the OS/browser preference until the user picks Light/Dark explicitly
  // in Settings (see components/settings/theme-toggle.tsx).
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "var(--font-sans)",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      colors: {
        border: "hsl(var(--border))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        ring: "hsl(var(--ring))",
        sidebar: "hsl(var(--sidebar))",
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        card: "hsl(var(--card))",
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        // Distinct from `destructive` (a filled button background paired
        // with white text) — `error` is tuned only for plain text on the
        // page background (e.g. form error messages), which needs a
        // different lightness to hit WCAG AA contrast in each theme.
        error: "hsl(var(--error))",
        warning: {
          DEFAULT: "hsl(var(--warning))",
          foreground: "hsl(var(--warning-foreground))",
        },
        skeleton: {
          DEFAULT: "hsl(var(--skeleton))",
          shine: "hsl(var(--skeleton-shine))",
        },
      },
      borderRadius: {
        lg: "8px",
        md: "6px",
        sm: "4px",
      },
      boxShadow: {
        // Defined as CSS variables (globals.css) rather than fixed values --
        // a dark shadow that reads correctly against a near-white page is
        // invisible against a near-black one, so dark mode needs a
        // different shadow, not just the same one at a different opacity.
        subtle: "var(--shadow-subtle)",
        popover: "var(--shadow-popover)",
      },
    },
  },
  plugins: [],
};

export default config;
