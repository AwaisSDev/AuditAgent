"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { ArrowUpRight, Check, Copy } from "lucide-react";
import { Hero } from "./hero";
import { Reveal } from "./reveal";
import {
  ApprovalsArt,
  DashboardArt,
  EvidenceArt,
  LedgerArt,
  LoggingArt,
  McpArt,
} from "./illustrations";
import "./landing.css";

// Google Sans Flex is published on Google Fonts under the OFL. React hoists
// this <link> into <head> (the `precedence` prop opts in).
const FONT_HREF =
  "https://fonts.googleapis.com/css2?family=Google+Sans+Flex:opsz,wght@6..144,400..700&display=swap";

const DOCS_URL = "https://getauditagent.vercel.app/docs"; // the marketing site (AwaisSDev/AuditAgentWeb)

const SECTIONS = [
  { id: "logging", label: "Logging" },
  { id: "approvals", label: "Approvals" },
  { id: "ledger", label: "Ledger" },
  { id: "evidence", label: "Evidence" },
  { id: "dashboard", label: "Dashboard" },
  { id: "mcp", label: "MCP" },
];

/* ---------- buttons ---------- */

function PillLink({
  href,
  children,
  variant = "primary",
  external,
}: {
  href: string;
  children: ReactNode;
  variant?: "primary" | "secondary" | "outline";
  external?: boolean;
}) {
  const base =
    "inline-flex h-12 items-center justify-center gap-1.5 rounded-full px-6 text-[15px] font-medium tracking-[-0.01em] transition-[background-color,box-shadow,transform] duration-150 active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--lp-fg)] focus-visible:ring-offset-2";
  const styles = {
    primary: "bg-[var(--lp-accent)] text-[#1f1e1b] hover:bg-[#ffb24d]",
    secondary: "bg-[var(--lp-amber)] text-[var(--lp-accent-ink)] hover:bg-[#ffe7bd]",
    outline: "border border-[var(--lp-line)] bg-white text-[var(--lp-fg)] hover:bg-[var(--lp-band)]",
  }[variant];
  const props = external ? { target: "_blank", rel: "noreferrer" } : {};
  return (
    <Link href={href} className={`${base} ${styles}`} {...props}>
      {children}
      {external && <ArrowUpRight className="h-4 w-4" />}
    </Link>
  );
}

/* ---------- header ---------- */

function Header() {
  return (
    <header className="fixed inset-x-0 top-0 z-50 h-[var(--lp-header-h)] border-b border-[var(--lp-line)] bg-white/95 backdrop-blur-[2px]">
      <div className="mx-auto flex h-full max-w-[1200px] items-center justify-between px-6">
        <div className="flex items-center gap-8">
          <Link href="/" className="flex items-center gap-2.5">
            {/* eslint-disable-next-line @next/next/no-img-element -- next/image's optimizer (sharp) fails on this PNG */}
            <img src="/logo.png" alt="" width={26} height={26} />
            <span className="text-[17px] font-semibold tracking-[-0.01em]">AuditAgent</span>
          </Link>
          <nav className="hidden items-center gap-6 text-[14px] text-[var(--lp-fg-2)] md:flex">
            <a href="#logging" className="hover:text-[var(--lp-fg)]">
              How it works
            </a>
            <a
              href={DOCS_URL}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-0.5 hover:text-[var(--lp-fg)]"
            >
              For developers <ArrowUpRight className="h-3.5 w-3.5" />
            </a>
          </nav>
        </div>
        <div className="flex items-center gap-2.5">
          <Link
            href="/login"
            className="hidden h-10 items-center rounded-full border border-[var(--lp-line)] px-5 text-[14px] font-medium transition-colors hover:bg-[var(--lp-band)] sm:inline-flex"
          >
            Log in
          </Link>
          <Link
            href="/login"
            className="inline-flex h-10 items-center rounded-full bg-[var(--lp-accent)] px-5 text-[14px] font-medium text-[#1f1e1b] transition-colors hover:bg-[#ffb24d]"
          >
            Get started
          </Link>
        </div>
      </div>
    </header>
  );
}

/* ---------- sticky jumplinks (the pill under the header) ---------- */

function Jumplinks() {
  const [active, setActive] = useState<string | null>(null);
  const pillRefs = useRef<Record<string, HTMLAnchorElement | null>>({});

  useEffect(() => {
    const els = SECTIONS.map((s) => document.getElementById(s.id)).filter(Boolean) as HTMLElement[];
    const io = new IntersectionObserver(
      (entries) => {
        // The section occupying the middle band of the viewport wins.
        const hit = entries.filter((e) => e.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (hit) setActive(hit.target.id);
      },
      { rootMargin: "-45% 0px -45% 0px", threshold: [0, 0.01, 0.5, 1] }
    );
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, []);

  useEffect(() => {
    // The pill row scrolls horizontally on narrow screens, so the pill for
    // whichever section is now active can end up scrolled out of view —
    // keep it in frame instead of just changing its color off-screen.
    if (active) pillRefs.current[active]?.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
  }, [active]);

  return (
    <div className="sticky top-[var(--lp-header-h)] z-40 flex justify-center px-4 pt-4">
      <nav className="lp-jump flex max-w-full gap-1 overflow-x-auto rounded-full border border-[var(--lp-line)] bg-white px-2 py-1.5 shadow-[0_4px_16px_-8px_rgb(55_53_47/0.25)]">
        {SECTIONS.map((s) => (
          <a
            key={s.id}
            ref={(el) => {
              pillRefs.current[s.id] = el;
            }}
            href={`#${s.id}`}
            className={
              "shrink-0 rounded-full px-3.5 py-1.5 text-[13.5px] font-medium transition-colors " +
              (active === s.id
                ? "bg-[var(--lp-amber)] text-[var(--lp-accent-ink)]"
                : "text-[var(--lp-fg-2)] hover:bg-[var(--lp-band)] hover:text-[var(--lp-fg)]")
            }
          >
            {s.label}
          </a>
        ))}
      </nav>
    </div>
  );
}

/* ---------- promo section: eyebrow / headline / body / cta + media ---------- */

function Promo({
  id,
  eyebrow,
  title,
  body,
  bullets,
  cta,
  media,
  mediaLeft,
  band,
}: {
  id: string;
  eyebrow: string;
  title: string;
  body: string;
  bullets?: string[];
  cta?: { label: string; href: string; external?: boolean };
  media: ReactNode;
  mediaLeft?: boolean;
  band?: boolean;
}) {
  return (
    <Reveal id={id} className={"scroll-mt-[140px] " + (band ? "bg-[var(--lp-band)]" : "bg-white")}>
      <div className="mx-auto grid min-w-0 max-w-[1200px] items-center gap-10 px-6 py-20 md:py-28 lg:grid-cols-2 lg:gap-24">
        <div data-fade-order="1" data-fade-media="" className={"min-w-0 " + (mediaLeft ? "lg:order-1" : "lg:order-2")}>
          {media}
        </div>
        <div className={"min-w-0 max-w-[480px] " + (mediaLeft ? "lg:order-2" : "lg:order-1")}>
          <div data-fade-order="3" className="text-[14px] font-medium uppercase tracking-[0.04em] text-[var(--lp-fg)]">
            {eyebrow}
          </div>
          <h2
            data-fade-order="3"
            className="mt-3 text-[34px] font-normal leading-[1.15] tracking-[-0.01em] sm:text-[44px] lg:text-[48px]"
          >
            {title}
          </h2>
          <p data-fade-order="3" className="mt-5 text-[16px] leading-[1.6] text-[var(--lp-fg-2)] sm:text-[18px]">
            {body}
          </p>
          {bullets && (
            <ul data-fade-order="3" className="mt-5 space-y-2.5 text-[15px] text-[var(--lp-fg-2)]">
              {bullets.map((b) => (
                <li key={b} className="flex gap-3">
                  <Check className="mt-[3px] h-4 w-4 shrink-0 text-[#1f9a5f]" strokeWidth={2.5} />
                  <span>{b}</span>
                </li>
              ))}
            </ul>
          )}
          {cta && (
            <div data-fade-order="3" className="mt-8">
              <PillLink href={cta.href} variant="secondary" external={cta.external}>
                {cta.label}
              </PillLink>
            </div>
          )}
        </div>
      </div>
    </Reveal>
  );
}

/* ---------- floating install card (Wallet's "scan to get the app") ---------- */

function InstallCard() {
  const [copied, setCopied] = useState(false);
  const cmd = "pip install auditagent";

  async function copy() {
    try {
      await navigator.clipboard.writeText(cmd);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      /* clipboard blocked; the text is still selectable */
    }
  }

  return (
    <div className="fixed bottom-5 right-5 z-40 hidden w-[252px] rounded-2xl border border-[var(--lp-line)] bg-white p-4 shadow-[0_8px_24px_-8px_rgb(55_53_47/0.3)] lg:block">
      <div className="text-[12px] font-medium text-[var(--lp-fg-3)]">Install the SDK</div>
      <button
        type="button"
        onClick={copy}
        className="mt-2 flex w-full items-center justify-between gap-2 whitespace-nowrap rounded-lg bg-[var(--lp-band)] px-3 py-2 text-left font-mono text-[13px] text-[var(--lp-fg)] transition-colors hover:bg-[var(--lp-line)]"
        aria-label="Copy install command"
      >
        <span>
          <span className="text-[var(--lp-fg-3)]">$ </span>
          {cmd}
        </span>
        {copied ? <Check className="h-3.5 w-3.5 text-[#1f9a5f]" /> : <Copy className="h-3.5 w-3.5 text-[var(--lp-fg-3)]" />}
      </button>
      <div className="mt-2 text-center text-[11.5px] text-[var(--lp-fg-3)]">Python 3.10+ · async &amp; sync</div>
    </div>
  );
}

/* ---------- page ---------- */

export function Landing() {
  return (
    <div className="lp min-h-screen">
      <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
      <link rel="stylesheet" href={FONT_HREF} precedence="default" />
      <Header />
      <main className="pt-[var(--lp-header-h)]">
        <Jumplinks />
        <Hero />

        <Promo
          id="logging"
          eyebrow="Logging"
          title="One decorator. Every action, on the record."
          body="Put @audit.track above any function your agent calls. From then on, every time it runs, AuditAgent writes down what happened: what went in, what came out, and when. Your agent doesn't slow down; the bookkeeping happens in the background."
          cta={{ label: "Read the SDK docs", href: DOCS_URL, external: true }}
          media={<LoggingArt />}
        />

        <Promo
          id="approvals"
          eyebrow="Approvals"
          title="Risky actions wait for a human."
          body="You decide which actions need a person: refunds over a certain amount, anything that deletes data, whatever matters to you. Before your agent runs one, it stops and asks your team in Slack. One tap to approve or deny, and the agent carries on."
          bullets={[
            "Rules are written in plain text, not code",
            "Falls back to email if Slack isn't connected",
            "Every decision is recorded too: who, when, how long it took",
          ]}
          cta={{ label: "See an example policy", href: DOCS_URL, external: true }}
          media={<ApprovalsArt />}
          mediaLeft
          band
        />

        <Promo
          id="ledger"
          eyebrow="Ledger"
          title="Nothing can be changed after the fact."
          body="Each record is linked to the one before it and checked every day. Nothing can be edited or deleted later, not by your agent, not by your team, not by us. That's what makes it evidence rather than a log."
          bullets={[
            "Personal details and secrets are removed before anything is stored",
            "Auditors can verify the record themselves",
          ]}
          media={<LedgerArt />}
        />

        <Promo
          id="evidence"
          eyebrow="Evidence"
          title="Security questionnaires, answered from your logs."
          body="Upload a security questionnaire. AuditAgent finds the records that answer each question and writes a first draft, with sources. You read and approve every answer before it goes anywhere, then export as a Word document or spreadsheet."
          cta={{ label: "How evidence packs work", href: DOCS_URL, external: true }}
          media={<EvidenceArt />}
          mediaLeft
          band
        />

        <Promo
          id="dashboard"
          eyebrow="Dashboard"
          title="See what your agents did today."
          body="A timeline of every action, the approvals waiting on your team, your rules, and how it all maps to SOC 2, in one place and always up to date."
          media={<DashboardArt />}
        />

        <Promo
          id="mcp"
          eyebrow="MCP"
          title="Ask Claude about your audit trail."
          body="Connect AuditAgent to Claude and just ask: anything waiting on me? What did the billing agent do last night? It reads the same record as the dashboard, and it can only read."
          cta={{ label: "Set up the MCP server", href: DOCS_URL, external: true }}
          media={<McpArt />}
          mediaLeft
          band
        />

        {/* closing: echoes the hero, like the reference */}
        <Reveal className="bg-white">
          <div className="mx-auto flex max-w-[1200px] flex-col items-center px-6 py-28 text-center md:py-36">
            <h2
              data-fade-order="1"
              className="text-[44px] font-bold leading-[1.02] tracking-[-0.02em] sm:text-[64px] lg:text-[76px]"
            >
              It&rsquo;s not a log.
              <br />
              It&rsquo;s evidence.
            </h2>
            <p data-fade-order="2" className="mt-5 text-[16px] text-[var(--lp-fg-3)]">
              Free while in beta · works with any Python agent · set up in an afternoon
            </p>
            <div data-fade-order="3" className="mt-9 flex flex-wrap justify-center gap-3">
              <PillLink href="/login" variant="primary">
                Get started
              </PillLink>
              <PillLink href={DOCS_URL} variant="outline" external>
                Read the docs
              </PillLink>
            </div>
          </div>
        </Reveal>

        <footer className="border-t border-[var(--lp-line)] bg-[var(--lp-band)]">
          <div className="mx-auto flex max-w-[1200px] flex-col gap-4 px-6 py-8 text-[13px] text-[var(--lp-fg-3)] sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-2">
              {/* eslint-disable-next-line @next/next/no-img-element -- see header */}
              <img src="/logo.png" alt="" width={18} height={18} />
              <span>AuditAgent · compliance infrastructure for AI agent teams</span>
            </div>
            <div className="flex gap-5">
              <a href={DOCS_URL} target="_blank" rel="noreferrer" className="hover:text-[var(--lp-fg)]">
                Docs
              </a>
              <Link href="/login" className="hover:text-[var(--lp-fg)]">
                Log in
              </Link>
              <a href="mailto:hello@auditagent.dev" className="hover:text-[var(--lp-fg)]">
                Contact
              </a>
            </div>
          </div>
        </footer>
      </main>
      <InstallCard />
    </div>
  );
}
