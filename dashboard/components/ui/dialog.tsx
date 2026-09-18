"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/utils";

export function Dialog({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}) {
  // Portal to document.body rather than rendering inline: this component
  // gets mounted from deep inside AppShell's layout (sidebar flex wrapper,
  // a scrolling `main`, a max-w content column, ...) -- if any ancestor
  // ever picks up a transform/filter/perspective (including ones added
  // later, e.g. a page-transition wrapper), that ancestor becomes the
  // containing block for this "fixed" overlay per the CSS spec instead of
  // the actual viewport, which is exactly what produced the reported bug
  // (the backdrop clipped/offset instead of covering the full page).
  // Portaling out to <body> makes that class of bug structurally
  // impossible instead of depending on no ancestor ever doing that.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  if (!open || !mounted) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/20 p-4"
      onClick={onClose}
    >
      <div
        className={cn("max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-lg border border-border bg-card p-5 shadow-popover")}
        onClick={(e) => e.stopPropagation()}
      >
        {title && <h2 className="mb-4 text-sm font-medium">{title}</h2>}
        {children}
      </div>
    </div>,
    document.body
  );
}
