"use client";

import { useState } from "react";
import { Menu } from "lucide-react";
import { useWorkspace } from "@/lib/workspace-context";
import { Sidebar } from "@/components/nav/sidebar";
import { CreateWorkspace } from "@/components/onboarding/create-workspace";
import { Skeleton } from "@/components/ui/skeleton";

function AppShellSkeleton() {
  return (
    <div className="flex">
      <aside className="hidden h-screen w-[288px] shrink-0 flex-col bg-sidebar md:flex">
        <div className="flex items-center gap-2.5 px-4 pb-4 pt-5">
          <Skeleton className="h-[26px] w-[26px] rounded" />
          <Skeleton className="h-4 w-24" />
        </div>
        <div className="px-3 pb-3">
          <Skeleton className="h-[42px] w-full rounded-md" />
        </div>
        <div className="flex-1 space-y-1 px-3 pt-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-9 w-full rounded-md" />
          ))}
        </div>
      </aside>
      <main className="h-screen flex-1 overflow-y-auto">
        <div className="mx-auto max-w-4xl space-y-5 px-4 py-8 sm:px-10">
          <Skeleton className="h-7 w-40" />
          <Skeleton className="h-64 w-full rounded-lg" />
        </div>
      </main>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { workspaces, isLoading } = useWorkspace();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  if (isLoading) return <AppShellSkeleton />;
  if (workspaces.length === 0) return <CreateWorkspace />;

  return (
    <div className="md:flex">
      <Sidebar open={mobileNavOpen} onClose={() => setMobileNavOpen(false)} />

      <div className="flex min-h-screen w-full min-w-0 flex-col md:ml-[288px] md:w-auto md:flex-1">
        <div className="sticky top-0 z-30 flex items-center gap-3 border-b border-border bg-background px-4 py-3 md:hidden">
          <button
            onClick={() => setMobileNavOpen(true)}
            className="-m-1 rounded-md p-2.5 text-foreground hover:bg-muted"
            aria-label="Open menu"
          >
            <Menu className="h-5 w-5" />
          </button>
          {/* eslint-disable-next-line @next/next/no-img-element -- next/image's optimizer (sharp) fails on this PNG */}
          <img src="/logo.png" alt="" width={20} height={20} />
          <span className="text-sm font-semibold">AuditAgent</span>
        </div>

        <main className="flex-1 overflow-y-auto md:h-screen">
          <div className="mx-auto max-w-4xl px-4 py-6 sm:px-10 sm:py-8">{children}</div>
        </main>
      </div>
    </div>
  );
}
