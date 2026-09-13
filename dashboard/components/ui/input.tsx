import { forwardRef } from "react";
import { cn } from "@/lib/utils";

export const Input = forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        // text-base (16px) on mobile, not text-sm (14px): iOS Safari auto-zooms
        // the whole page on focus for any input below 16px, which is jarring.
        "flex h-9 w-full rounded-md border border-border bg-background px-2.5 py-1 text-base text-foreground transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-background disabled:opacity-50 sm:h-8 sm:text-sm",
        className
      )}
      {...props}
    />
  )
);
Input.displayName = "Input";
