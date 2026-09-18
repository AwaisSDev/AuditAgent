"use client";

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
  if (!open) return null;
  return (
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
    </div>
  );
}
