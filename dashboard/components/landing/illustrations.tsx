"use client";

import {
  BadgeCheck,
  BookOpen,
  Check,
  ChevronDown,
  ChevronRight,
  ClipboardList,
  Copy,
  FileText,
  Link2,
  Mail,
  Mic,
  Pin,
  Plus,
  RotateCcw,
  Search,
  Share2,
  ShieldCheck,
  SlidersHorizontal,
  Trash2,
  Volume2,
  UserRoundCheck,
  X,
  type LucideIcon,
} from "lucide-react";
import type { CSSProperties, ReactNode } from "react";

/* Each illustration is a small, plain language mock of the real product
   surface, sitting in a pastel rounded card (the equivalent of the Lottie
   cards on wallet.google). One shot entrance animations are keyed off the
   parent section's [data-scrolled], see landing.css. */

function Frame({ tint, children }: { tint: string; children: ReactNode }) {
  return (
    <div
      className="relative flex min-h-[440px] w-full items-center justify-center overflow-hidden rounded-[28px] p-6 sm:min-h-[500px] sm:p-10"
      style={{ background: tint }}
    >
      {children}
    </div>
  );
}

const pop = (i: number): CSSProperties => ({ ["--i" as string]: i });

const EVENTS: { icon: LucideIcon; color: string; title: string; time: string; status?: string }[] = [
  { icon: Mail, color: "#2f66d6", title: "Email sent to customer", time: "9:41", status: "Logged" },
  { icon: RotateCcw, color: "#d9463a", title: "Refund approved by Maya", time: "9:40", status: "Needed a human" },
  { icon: Search, color: "#1f9a5f", title: "Order looked up", time: "9:40", status: "Logged" },
  { icon: UserRoundCheck, color: "#e0891a", title: "Lead marked qualified", time: "9:39", status: "Logged" },
];

function EventRow({
  e,
  i,
  right,
}: {
  e: (typeof EVENTS)[number];
  i: number;
  right?: ReactNode;
}) {
  const Icon = e.icon;
  return (
    <div
      className="lp-anim-pop flex items-center gap-3 rounded-2xl bg-white px-4 py-3 shadow-[0_1px_2px_rgb(60_64_67/0.08)]"
      style={pop(i)}
    >
      <span
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-white"
        style={{ background: e.color }}
      >
        <Icon className="h-4 w-4" strokeWidth={2.25} />
      </span>
      <span className="min-w-0 flex-1 truncate text-[15px] font-medium">{e.title}</span>
      {right ?? <span className="text-[13px] text-[var(--lp-fg-3)]">{e.time}</span>}
    </div>
  );
}

/* 1: Logging: the one line you add, and what it produces. */
export function LoggingArt() {
  return (
    <Frame tint="var(--lp-amber)">
      <div className="w-full max-w-[420px]">
        <div className="rounded-2xl bg-white p-5 shadow-[0_12px_32px_-12px_rgb(60_64_67/0.3)]">
          <div className="text-[12px] font-medium text-[var(--lp-fg-3)]">The only line you add</div>
          <div className="mt-2 font-mono text-[15px] leading-[1.6]">
            <span className="text-[#b45f06]">@audit.track</span>(&quot;refund_payment&quot;)
          </div>
          <div className="mt-1 text-[14px] text-[var(--lp-fg-2)]">…above any function your agent calls.</div>
        </div>
        <div className="mt-4 space-y-2">
          {EVENTS.slice(0, 3).map((e, i) => (
            <EventRow
              key={e.title}
              e={e}
              i={i}
              right={
                <span
                  className={
                    "rounded-full px-2.5 py-0.5 text-[12px] font-medium " +
                    (e.status === "Logged" ? "bg-[var(--lp-sage)] text-[#2b6a43]" : "bg-[var(--lp-rose)] text-[#a2453a]")
                  }
                >
                  {e.status}
                </span>
              }
            />
          ))}
        </div>
      </div>
    </Frame>
  );
}

/* 2: Approvals: the Slack message a person actually sees. */
export function ApprovalsArt() {
  return (
    <Frame tint="var(--lp-rose)">
      <div className="w-full max-w-[420px] rounded-2xl bg-white p-5 shadow-[0_12px_32px_-12px_rgb(60_64_67/0.3)]">
        <div className="flex items-center gap-2.5">
          <span className="flex h-9 w-9 items-center justify-center overflow-hidden rounded-lg border border-[var(--lp-line)] bg-white">
            {/* eslint-disable-next-line @next/next/no-img-element -- see header */}
            <img src="/logo.png" alt="" width={26} height={26} />
          </span>
          <span className="text-[15px] font-semibold">AuditAgent</span>
          <span className="rounded bg-[var(--lp-band)] px-1.5 text-[11px] font-medium text-[var(--lp-fg-3)]">APP</span>
          <span className="text-[13px] text-[var(--lp-fg-3)]">9:40 AM</span>
        </div>
        <p className="mt-3 text-[16px] leading-[1.55]">
          <b>Billing agent</b> wants to refund <b>$1,240</b> on order 48213. Your policy asks a person
          for refunds over $500.
        </p>
        <div className="mt-4 flex gap-2">
          <span className="flex items-center gap-1.5 rounded-lg bg-[#1f9a5f] px-4 py-2 text-[14px] font-semibold text-white">
            <Check className="h-4 w-4" strokeWidth={3} /> Approve
          </span>
          <span className="flex items-center gap-1.5 rounded-lg border border-[var(--lp-line)] px-4 py-2 text-[14px] font-semibold">
            <X className="h-4 w-4" strokeWidth={3} /> Deny
          </span>
        </div>
        <div className="lp-anim-pop mt-4 flex items-center gap-2 border-t border-[var(--lp-line)] pt-4 text-[15px]" style={pop(0)}>
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[#1f9a5f] text-white">
            <Check className="h-3.5 w-3.5" strokeWidth={3} />
          </span>
          Approved by Maya · 2 minutes later
        </div>
      </div>
    </Frame>
  );
}

/* 3: Ledger: each record linked to the one before it. */
export function LedgerArt() {
  return (
    <Frame tint="var(--lp-sage)">
      <div className="w-full max-w-[420px]">
        {EVENTS.map((e, i) => (
          <div key={e.title}>
            <EventRow
              e={e}
              i={3 - i}
              right={
                <span className="flex items-center gap-1 text-[13px] font-medium text-[#2b6a43]">
                  <Link2 className="h-3.5 w-3.5" /> linked
                </span>
              }
            />
            {i < EVENTS.length - 1 && (
              <svg className="ml-[33px] block h-5 w-1 overflow-visible" viewBox="0 0 4 20" aria-hidden>
                <path d="M2 0 V20" stroke="#2b6a43" strokeWidth="2.5" pathLength={1} className="lp-anim-draw" style={pop(2 - i)} />
              </svg>
            )}
          </div>
        ))}
        <div className="lp-anim-pop mt-4 flex items-center justify-between rounded-2xl bg-white/70 px-4 py-3 text-[14px]" style={pop(4)}>
          <span>Checked this morning</span>
          <span className="flex items-center gap-1.5 font-medium text-[#2b6a43]">
            <Check className="h-4 w-4" strokeWidth={3} /> Nothing changed
          </span>
        </div>
      </div>
    </Frame>
  );
}

/* 4: Evidence: a questionnaire answer, written from the record. */
export function EvidenceArt() {
  return (
    <Frame tint="var(--lp-sky)">
      <div className="w-full max-w-[420px] rounded-2xl bg-white p-5 shadow-[0_12px_32px_-12px_rgb(60_64_67/0.3)]">
        <div className="flex items-center gap-2 text-[12px] font-medium text-[var(--lp-fg-3)]">
          <FileText className="h-3.5 w-3.5" /> Vendor security questionnaire · question 7.2
        </div>
        <div className="mt-2 text-[17px] font-medium leading-[1.4]">
          Do you keep a record of actions taken by automated systems, and can it be altered?
        </div>
        <div className="mt-4 rounded-2xl bg-[var(--lp-band)] p-4 text-[15px] leading-[1.6] text-[var(--lp-fg-2)]">
          <p className="lp-anim-pop" style={pop(0)}>
            Yes. Every action an agent takes is written to a record that can&rsquo;t be edited or deleted.
            Sensitive actions need a person&rsquo;s approval before they run.
          </p>
          <div className="lp-anim-pop mt-3 text-[13px] text-[var(--lp-fg-3)]" style={pop(1)}>
            Based on 3 records from 12 September
          </div>
        </div>
        <div className="lp-anim-pop mt-4 flex items-center justify-between text-[14px]" style={pop(2)}>
          <span className="text-[var(--lp-fg-3)]">Drafted for you to review</span>
          <span className="flex items-center gap-1 font-medium">
            Review <ChevronRight className="h-4 w-4" />
          </span>
        </div>
      </div>
    </Frame>
  );
}

/* 5: Dashboard: the timeline, as it looks in the app. */
export function DashboardArt() {
  const rows = [
    ...EVENTS,
    { icon: Trash2, color: "#5f6368", title: "Bulk delete stopped", time: "9:38", status: "Denied" },
  ];
  const nav: [LucideIcon, string, number?][] = [
    [ClipboardList, "Timeline"],
    [BadgeCheck, "Approvals", 2],
    [SlidersHorizontal, "Rules"],
    [ShieldCheck, "SOC 2"],
    [FileText, "Evidence"],
  ];
  return (
    <Frame tint="var(--lp-lilac)">
      <div className="flex w-full max-w-[460px] overflow-hidden rounded-2xl bg-white shadow-[0_12px_32px_-12px_rgb(60_64_67/0.3)]">
        <div className="hidden w-[148px] shrink-0 border-r border-[var(--lp-line)] bg-[var(--lp-band)] p-3 sm:block">
          <div className="flex items-center gap-2 px-1.5 pb-4 pt-1">
            {/* eslint-disable-next-line @next/next/no-img-element -- see header */}
            <img src="/logo.png" alt="" width={18} height={18} />
            <span className="text-[13px] font-semibold">Meridian</span>
            <ChevronDown className="ml-auto h-3.5 w-3.5 text-[var(--lp-fg-3)]" />
          </div>
          <div className="space-y-0.5">
            {nav.map(([Icon, label, badge], i) => (
              <div
                key={label}
                className={
                  "flex items-center gap-2 rounded-lg px-2 py-1.5 text-[13px] " +
                  (i === 0 ? "bg-white font-medium shadow-[0_1px_2px_rgb(60_64_67/0.08)]" : "text-[var(--lp-fg-2)]")
                }
              >
                <Icon className="h-3.5 w-3.5 text-[var(--lp-fg-3)]" strokeWidth={2} />
                {label}
                {badge && (
                  <span className="ml-auto rounded-full bg-[#d9463a] px-1.5 text-[11px] font-medium text-white">{badge}</span>
                )}
              </div>
            ))}
          </div>
        </div>
        <div className="min-w-0 flex-1 p-4">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-[16px] font-semibold">Timeline</div>
              <div className="text-[12px] text-[var(--lp-fg-3)]">Today · 4 agents · 14 actions</div>
            </div>
            <span className="rounded-full border border-[var(--lp-line)] px-2.5 py-1 text-[12px] font-medium">Today</span>
          </div>
          <div className="mt-3 divide-y divide-[var(--lp-line)]">
            {rows.map((e, i) => {
              const Icon = e.icon;
              return (
                <div key={e.title} className="lp-anim-pop flex items-center gap-2.5 py-2.5 text-[13.5px]" style={pop(i)}>
                  <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-white" style={{ background: e.color }}>
                    <Icon className="h-3.5 w-3.5" strokeWidth={2.5} />
                  </span>
                  <span className="min-w-0 flex-1 truncate">{e.title}</span>
                  <span className="text-[12px] text-[var(--lp-fg-3)]">{e.time}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </Frame>
  );
}

/* 6: MCP: the conversation as it looks in the Claude desktop app (dark). */
export function McpArt() {
  return (
    <Frame tint="var(--lp-sand)">
      <div className="w-full max-w-[440px] overflow-hidden rounded-2xl bg-[#1c1c1c] text-[#e8e6e2] shadow-[0_16px_40px_-14px_rgb(0_0_0/0.5)]">
        <div className="flex items-center gap-2 border-b border-white/[0.06] px-4 py-2.5 text-[13px]">
          <BookOpen className="h-3.5 w-3.5 text-[#9c9a94]" />
          <span className="font-medium">Approvals check</span>
          <span className="rounded bg-white/[0.08] px-1.5 py-0.5 text-[11px] text-[#c9c6c0]">Meridian</span>
        </div>
        <div className="px-4 pt-4">
          <div className="flex justify-end">
            <div className="max-w-[80%] rounded-xl bg-[#2b2b2b] px-4 py-2.5 text-[14px] leading-[1.5]">
              anything waiting on me?
            </div>
          </div>
          <div className="lp-anim-pop mt-5 flex items-center gap-1 text-[13px] text-[#9c9a94]" style={pop(0)}>
            Used 1 tool <ChevronRight className="h-3.5 w-3.5" />
          </div>
          <div className="lp-anim-pop mt-2 text-[14px] leading-[1.6]" style={pop(1)}>
            Two approvals are waiting from the last hour: a $1,240 refund from the billing agent
            (2 minutes ago) and a bulk delete of 340 records from the ops agent (41 minutes ago).
            Want me to open them?
          </div>
          <div className="lp-anim-pop mt-3 flex items-center gap-3 text-[12px] text-[#9c9a94]" style={pop(2)}>
            <Copy className="h-3.5 w-3.5" />
            <Share2 className="h-3.5 w-3.5" />
            <Pin className="h-3.5 w-3.5" />
            <Volume2 className="h-3.5 w-3.5" />
            <span>just now</span>
          </div>
        </div>
        <div className="p-4 pt-5">
          <div className="rounded-xl border border-white/[0.1] bg-[#242424] px-3.5 py-3 text-[14px] text-[#9c9a94]">
            Type / for commands
          </div>
          <div className="mt-2.5 flex items-center justify-between text-[12.5px] text-[#c9c6c0]">
            <div className="flex items-center gap-2.5">
              <Plus className="h-3.5 w-3.5" />
              <Mic className="h-3.5 w-3.5" />
              <ChevronDown className="h-3 w-3" />
              <span>AuditAgent connected</span>
            </div>
            <div className="flex items-center gap-3">
              <span>Opus 5</span>
              <span>High</span>
              <span className="h-3.5 w-3.5 rounded-full border-2 border-[#5b8def]" />
            </div>
          </div>
        </div>
      </div>
    </Frame>
  );
}
