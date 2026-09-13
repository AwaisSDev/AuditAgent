"use client";

import { cn } from "@/lib/utils";

export function Switch({
  checked,
  onCheckedChange,
  disabled,
}: {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
}) {
  return (
    // The outer button is a full 44px tap target on touchscreens even though
    // the visible track stays a normal-looking switch size — same technique
    // native iOS/Android switches use rather than just drawing a bigger control.
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onCheckedChange(!checked)}
      className="flex h-11 w-11 shrink-0 items-center justify-center disabled:cursor-not-allowed disabled:opacity-50 sm:h-8 sm:w-9"
    >
      <span
        className={cn(
          "relative h-[22px] w-9 rounded-full border transition-colors duration-150",
          checked ? "border-warning bg-warning" : "border-[#D6D3CE] bg-[#E5E2DC] dark:border-[#4a4844] dark:bg-[#3a3835]"
        )}
      >
        <span
          className={cn(
            "absolute left-[3px] top-[3px] h-4 w-4 rounded-full bg-white shadow-[0_1px_3px_rgb(0,0,0,0.25)] transition-transform duration-150",
            checked ? "translate-x-[14px]" : "translate-x-0"
          )}
        />
      </span>
    </button>
  );
}
