import Link from "next/link";
import type { ReactNode } from "react";

// Shared chrome for /privacy and /terms: same header/footer as the landing
// page but without the `.lp` motion system, since these are static
// text pages that don't need the scroll-scrubbed hero.
export function LegalPage({
  title,
  lastUpdated,
  children,
}: {
  title: string;
  lastUpdated: string;
  children: ReactNode;
}) {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border">
        <div className="mx-auto flex h-16 max-w-[760px] items-center justify-between px-6">
          <Link href="/" className="flex items-center gap-2.5">
            {/* eslint-disable-next-line @next/next/no-img-element -- next/image's optimizer (sharp) fails on this PNG */}
            <img src="/logo.png" alt="" width={22} height={22} />
            <span className="text-[15px] font-semibold tracking-[-0.01em]">Tracyn</span>
          </Link>
          <nav className="flex items-center gap-5 text-[13px] text-muted-foreground">
            <Link href="/privacy" className="hover:text-foreground">
              Privacy
            </Link>
            <Link href="/terms" className="hover:text-foreground">
              Terms
            </Link>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-[760px] px-6 py-16">
        <h1 className="text-[28px] font-semibold tracking-[-0.01em]">{title}</h1>
        <p className="mt-2 text-[13px] text-muted-foreground">Last updated: {lastUpdated}</p>
        <div className="legal-prose mt-10 space-y-6 text-[15px] leading-7 text-foreground/90">
          {children}
        </div>
      </main>

      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-[760px] items-center justify-between px-6 py-8 text-[13px] text-muted-foreground">
          <span>Tracyn · compliance infrastructure for AI agent teams</span>
          <a href="mailto:mawais9171@gmail.com" className="hover:text-foreground">
            Contact
          </a>
        </div>
      </footer>
    </div>
  );
}

export function H2({ children }: { children: ReactNode }) {
  return <h2 className="pt-4 text-[19px] font-semibold tracking-[-0.01em]">{children}</h2>;
}

export function P({ children }: { children: ReactNode }) {
  return <p>{children}</p>;
}

export function Ul({ children }: { children: ReactNode }) {
  return <ul className="list-disc space-y-2 pl-5">{children}</ul>;
}
