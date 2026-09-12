"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { History, CircleCheck, FileText, ShieldCheck, BadgeCheck, Settings, LogOut, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { createSupabaseBrowserClient } from "@/lib/supabase-browser";
import { WorkspaceSwitcher } from "@/components/nav/workspace-switcher";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Timeline", icon: History },
  { href: "/approvals", label: "Approvals", icon: CircleCheck },
  { href: "/questionnaires", label: "Evidence Packs", icon: FileText },
  { href: "/policy", label: "Policy", icon: ShieldCheck },
  { href: "/soc2", label: "SOC 2 Mapping", icon: BadgeCheck },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar({ open, onClose }: { open?: boolean; onClose?: () => void }) {
  const pathname = usePathname();
  const router = useRouter();
  const supabase = createSupabaseBrowserClient();

  async function signOut() {
    await supabase.auth.signOut();
    router.push("/login");
  }

  return (
    <>
      {/* mobile backdrop */}
      {open && <div className="fixed inset-0 z-40 bg-foreground/20 md:hidden" onClick={onClose} />}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex h-screen w-[288px] shrink-0 -translate-x-full flex-col border-r border-border bg-sidebar transition-transform duration-200 md:translate-x-0",
          open && "translate-x-0"
        )}
      >
        <div className="flex items-center gap-2.5 px-4 pb-4 pt-5">
          {/* eslint-disable-next-line @next/next/no-img-element -- next/image's optimizer (sharp) fails on this PNG */}
          <img src="/logo.png" alt="" width={26} height={26} className="shrink-0" />
          <span className="flex-1 text-base font-semibold tracking-tight text-foreground">AuditAgent</span>
          <button onClick={onClose} className="rounded-md p-1 text-muted-foreground hover:bg-muted md:hidden">
            <X className="h-5 w-5" />
          </button>
        </div>

        <WorkspaceSwitcher />

        <nav className="flex-1 space-y-1 px-3 pt-2">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const active = pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={onClose}
                className={cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  active ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground"
                )}
              >
                <Icon className="h-[18px] w-[18px] shrink-0" strokeWidth={1.75} />
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="border-t border-border px-3 py-3">
          <button
            onClick={signOut}
            className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <LogOut className="h-[18px] w-[18px]" strokeWidth={1.75} />
            Sign out
          </button>
        </div>
      </aside>
    </>
  );
}
