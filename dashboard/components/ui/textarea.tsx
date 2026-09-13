import { forwardRef } from "react";
import { cn } from "@/lib/utils";

export const Textarea = forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => (
    <textarea
      ref={ref}
      className={cn(
        // text-base on mobile — see input.tsx for why (iOS Safari zoom-on-focus).
        "flex min-h-[80px] w-full rounded-md border border-border bg-background px-2.5 py-2 text-base text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-background disabled:opacity-50 sm:text-sm",
        className
      )}
      {...props}
    />
  )
);
Textarea.displayName = "Textarea";
