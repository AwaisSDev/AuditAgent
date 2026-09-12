import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

// Notion-style flat tag colors: muted, low-saturation fills rather than
// Tailwind's default 100/800 pairs, which read as louder "alert" colors.
const badgeVariants = cva("inline-flex items-center rounded px-2 py-1 text-[13px] font-medium leading-none", {
  variants: {
    variant: {
      default: "bg-primary text-primary-foreground",
      secondary: "bg-muted text-muted-foreground",
      success: "bg-[#DBEDDB] text-[#2F5D3A] dark:bg-[#1F3D2B] dark:text-[#8FCBA3]",
      warning: "bg-[#FBF3DB] text-[#8A6116] dark:bg-[#4A3C1B] dark:text-[#E3C878]",
      destructive: "bg-[#FBE4E4] text-[#AF4C4C] dark:bg-[#4B2426] dark:text-[#E8A5A0]",
      outline: "border border-border text-foreground",
    },
  },
  defaultVariants: { variant: "default" },
});

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

const STATUS_VARIANTS: Record<string, BadgeProps["variant"]> = {
  completed: "success",
  approved: "success",
  pending: "warning",
  rejected: "destructive",
  denied_timeout: "destructive",
  error: "destructive",
};

export function StatusBadge({ status }: { status: string }) {
  return <Badge variant={STATUS_VARIANTS[status] ?? "secondary"}>{status.replace(/_/g, " ")}</Badge>;
}
