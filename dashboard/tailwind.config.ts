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
        subtle: "0 1px 2px 0 rgb(55 53 47 / 0.06)",
        popover: "0 4px 12px 0 rgb(55 53 47 / 0.1), 0 0 0 1px rgb(55 53 47 / 0.06)",
      },
    },
  },
  plugins: [],
};

export default config;
