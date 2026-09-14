"use client";

import { useEffect } from "react";
import { forceLightTheme } from "@/lib/theme";

/** Drop into any public/marketing page that must always render light,
 * regardless of the visitor's stored preference or OS setting -- theming
 * is a dashboard (post-login) feature only. Needed because a server
 * component (like a page with its own `metadata` export) can't itself
 * hold the client-side effect this requires. */
export function ForceLightTheme() {
  useEffect(() => {
    forceLightTheme();
  }, []);

  return null;
}
