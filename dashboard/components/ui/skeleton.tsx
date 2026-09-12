import { cn } from "@/lib/utils";

export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-md bg-gradient-to-r from-skeleton via-skeleton-shine to-skeleton bg-[length:200%_100%] [animation:shimmer_1.6s_ease-in-out_infinite]",
        className
      )}
      {...props}
    />
  );
}
