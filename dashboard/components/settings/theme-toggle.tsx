"use client";

import { useEffect, useState } from "react";
import { Monitor, Moon, Sun } from "lucide-react";
import { cn } from "@/lib/utils";
import { getStoredTheme, setTheme, type Theme } from "@/lib/theme";

const OPTIONS: { value: Theme; label: string; icon: typeof Sun }[] = [
  { value: "system", label: "System", icon: Monitor },
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
];

export function ThemeToggle() {
  // Starts on "system" (matches the server-rendered markup) and syncs to
  // the real stored value after mount, to avoid a hydration mismatch.
  const [theme, setThemeState] = useState<Theme>("system");

  useEffect(() => {
    setThemeState(getStoredTheme());
  }, []);

  function choose(value: Theme) {
    setThemeState(value);
    setTheme(value);
  }

  return (
    <div className="inline-flex rounded-md border border-border p-0.5">
      {OPTIONS.map(({ value, label, icon: Icon }) => (
        <button
          key={value}
          type="button"
          onClick={() => choose(value)}
          aria-pressed={theme === value}
          className={cn(
            "flex items-center gap-1.5 rounded px-2.5 py-1.5 text-[13px] font-medium transition-colors",
            theme === value ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground"
          )}
        >
          <Icon className="h-3.5 w-3.5" strokeWidth={1.75} />
          {label}
        </button>
      ))}
    </div>
  );
}
