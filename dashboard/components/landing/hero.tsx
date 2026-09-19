"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Check, Mail, RotateCcw, Search, UserRoundCheck, X, type LucideIcon } from "lucide-react";

/* Scroll-scrubbed hero.

   The outer wrapper is DURATION px taller than the viewport; the inner
   block is position:sticky, so the page "pins" while the user scrolls
   through DURATION px. Scroll offset within that range → eased progress
   (easeOutSine, like wallet.google) → written straight to inline styles
   in a requestAnimationFrame. No state updates per frame.

   What the progress drives: four loose "agent action" cards tuck into a
   single light folder (the audit trail) which then reads "Sealed". At
   10% the headline fades out and the stage lifts to centre (a CSS
   transition keyed off data-text-out, not scrubbed, same as the
   reference).

   Cards are clickable at any scroll position: an open card expands over
   the stage with a plain-English account of the event and is exempt from
   the scrub until it's closed. */

const DURATION_DESKTOP = 1500;
const DURATION_MOBILE = 1000;
const TEXT_OUT_AT = 0.1;

const STAGE_W = 480;
const STAGE_H = 400;

// loose card
const CARD_W = 440;
const CARD_H = 168;
const CARD_STEP = 72;
// folded row
const FOLDER_TOP = 24;
const FOLDER_H = 352;
const FOLDER_HEADER = 68;
const ROW_H = 56;
const ROW_STEP = 66;
// expanded card
const OPEN_H = 292;

type Card = {
  bg: string;
  icon: LucideIcon;
  title: string;
  who: string;
  story: string;
  outcome: string;
};

const CARDS: Card[] = [
  {
    bg: "#2f66d6",
    icon: Mail,
    title: "Email sent to customer",
    who: "Support agent · 9:41 this morning",
    story:
      "Sent “Your refund has been processed”. The customer's email address was hidden before anything was stored.",
    outcome: "Logged automatically",
  },
  {
    bg: "#d9463a",
    icon: RotateCcw,
    title: "Refund approved by Maya",
    who: "Billing agent · 9:40 this morning",
    story:
      "Asked to refund $1,240 on order 48213. Your policy sends refunds over $500 to a person. Maya approved it in Slack in two minutes.",
    outcome: "Needed a human",
  },
  {
    bg: "#1f9a5f",
    icon: Search,
    title: "Order looked up",
    who: "Support agent · 9:40 this morning",
    story: "Read one order from the database to answer a support question. Nothing was changed.",
    outcome: "Logged automatically",
  },
  {
    bg: "#e0891a",
    icon: UserRoundCheck,
    title: "Lead marked qualified",
    who: "Sales agent · 9:39 this morning",
    story: "Moved lead 8f21 from “contacted” to “qualified” after they replied to step 3 of the sequence.",
    outcome: "Logged automatically",
  },
];

const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const clamp01 = (t: number) => Math.min(1, Math.max(0, t));
const range = (p: number, a: number, b: number) => clamp01((p - a) / (b - a));
const easeOutSine = (t: number) => -(Math.cos(Math.PI * t) - 1) / 2;

export function Hero() {
  const rootRef = useRef<HTMLDivElement>(null);
  const outerRef = useRef<HTMLDivElement>(null);
  const pinRef = useRef<HTMLDivElement>(null);
  const stageWrapRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const folderRef = useRef<HTMLDivElement>(null);
  const sealRef = useRef<HTMLDivElement>(null);
  const cardRefs = useRef<(HTMLDivElement | null)[]>([]);

  const [open, setOpen] = useState<number | null>(null);
  const openRef = useRef<number | null>(null);
  const repaintRef = useRef<() => void>(() => {});

  useLayoutEffect(() => {
    const root = rootRef.current;
    const outer = outerRef.current;
    const pin = pinRef.current;
    const stageWrap = stageWrapRef.current;
    const stage = stageRef.current;
    const folder = folderRef.current;
    const seal = sealRef.current;
    if (!root || !outer || !pin || !stageWrap || !stage || !folder || !seal) return;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    let duration = DURATION_DESKTOP;
    let outerTop = 0;
    let raf = 0;
    let textOut = false;

    function measure() {
      // Layout viewport, not window.innerWidth: excludes the scrollbar and
      // matches what the padded flex column actually gets.
      const vw = document.documentElement.clientWidth;
      const mobile = vw < 640;
      duration = mobile ? DURATION_MOBILE : DURATION_DESKTOP;
      outer!.style.height = `${duration + pin!.offsetHeight}px`;
      // The pin engages when the outer's top reaches the fixed header, so
      // progress is measured from there, not from the outer's own top.
      const headerH = parseFloat(getComputedStyle(root!).getPropertyValue("--lp-header-h")) || 64;
      outerTop = outer!.getBoundingClientRect().top + window.scrollY - headerH;

      // Scale the stage so the whole stack is visible under the headline on
      // narrow or short viewports; the maths stays in 480px units.
      const pinH = pin!.offsetHeight;
      const stageTop = stageWrap!.offsetTop;
      const fitW = (vw - 48) / STAGE_W;
      const fitH = (pinH - stageTop - 24) / STAGE_H;
      const scale = Math.max(0.5, Math.min(1, fitW, fitH));
      stageWrap!.style.width = `${STAGE_W * scale}px`;
      stageWrap!.style.height = `${STAGE_H * scale}px`;
      stage!.style.transform = `scale(${scale})`;

      // How far the stage lifts, once the text is gone, to sit centred.
      const lift = (pinH - STAGE_H * scale) / 2 - stageTop;
      root!.style.setProperty("--lp-stage-lift", `${Math.min(0, lift)}px`);
    }

    function place(el: HTMLDivElement, left: number, top: number, w: number, h: number, r: number, m: number) {
      el.style.transform = `translate3d(${left}px, ${top}px, 0)`;
      el.style.width = `${w}px`;
      el.style.height = `${h}px`;
      el.style.borderRadius = `${r}px`;
      el.style.setProperty("--icon", `${lerp(48, 32, m)}px`);
      el.style.setProperty("--glyph", `${lerp(22, 16, m)}px`);
      el.style.setProperty("--title", `${lerp(22, 15.5, m)}px`);
      el.style.setProperty("--pad", `${lerp(24, 16, m)}px`);
      el.style.setProperty("--row", `${lerp(72, ROW_H, m)}px`);
      el.style.boxShadow =
        m > 0.9
          ? "none"
          : `0 1px 2px rgb(20 18 12 / ${0.08 * (1 - m)}), 0 18px 40px -16px rgb(20 18 12 / ${0.4 * (1 - m)})`;
    }

    function paint(p: number) {
      const cards = cardRefs.current;
      const opened = openRef.current;
      for (let i = 0; i < cards.length; i++) {
        const el = cards[i];
        if (!el) continue;
        if (opened === i) {
          place(el, 0, 0, STAGE_W, OPEN_H, 28, 0);
          el.style.zIndex = "20";
          continue;
        }
        el.style.zIndex = String(i + 1);
        // Back cards start tucking first, so the stack folds from the top down.
        const m = range(p, 0.12 + i * 0.035, 0.68 + i * 0.035);
        place(
          el,
          lerp(20, 16, m),
          lerp(i * CARD_STEP, FOLDER_TOP + FOLDER_HEADER + i * ROW_STEP, m),
          lerp(CARD_W, STAGE_W - 32, m),
          lerp(CARD_H, ROW_H, m),
          lerp(28, 16, m),
          m
        );
      }

      const f = range(p, 0.45, 0.8);
      folder!.style.opacity = `${f}`;
      folder!.style.transform = `translateY(${lerp(24, 0, f)}px) scale(${lerp(0.97, 1, f)})`;

      const s = range(p, 0.86, 1);
      seal!.style.opacity = `${s}`;
      seal!.style.transform = `scale(${lerp(0.8, 1, s)})`;
    }

    function onFrame() {
      raf = 0;
      const raw = clamp01((window.scrollY - outerTop) / duration);
      const out = raw > TEXT_OUT_AT;
      if (out !== textOut) {
        textOut = out;
        root!.setAttribute("data-text-out", String(out));
      }
      paint(easeOutSine(raw));
    }

    function onScroll() {
      if (!raf) raf = requestAnimationFrame(onFrame);
    }

    repaintRef.current = () => paint(easeOutSine(clamp01((window.scrollY - outerTop) / duration)));

    measure();
    if (reduced) {
      // Land on the final frame; no pin, no scrub.
      outer.style.height = "auto";
      root.setAttribute("data-text-out", "false");
      root.style.setProperty("--lp-stage-lift", "0px");
      paint(1);
      return;
    }
    onFrame();
    // Fonts arriving late shift the layout; measure again once they're in.
    document.fonts?.ready.then(() => {
      measure();
      onScroll();
    });
    window.addEventListener("scroll", onScroll, { passive: true });
    const onResize = () => {
      measure();
      onScroll();
    };
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onResize);
      if (raf) cancelAnimationFrame(raf);
    };
  }, []);

  const toggle = useCallback((i: number) => {
    const next = openRef.current === i ? null : i;
    const closing = openRef.current;
    openRef.current = next;
    setOpen(next);
    // Transitions are only on for the card that's opening/closing, so the
    // scrub can keep writing frames to the others.
    const el = cardRefs.current[closing ?? -1];
    if (el && next === null) {
      el.setAttribute("data-closing", "true");
      window.setTimeout(() => el.removeAttribute("data-closing"), 650);
    }
    repaintRef.current();
  }, []);

  useEffect(() => {
    if (open === null) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") toggle(open);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, toggle]);

  return (
    <div ref={rootRef} className="lp-hero" data-text-out="false">
      <div ref={outerRef}>
        <div ref={pinRef} className="lp-hero-pin">
          <div className="mx-auto flex h-full max-w-[1200px] flex-col items-center px-6">
            <div className="lp-hero-text flex flex-col items-center pt-12 text-center sm:pt-16">
              <h1 className="text-[44px] font-bold leading-[1.02] tracking-[-0.02em] sm:text-[72px] lg:text-[84px]">
                It&rsquo;s not a log.
                <br />
                It&rsquo;s evidence.
              </h1>
              <p className="mt-5 max-w-[620px] text-[17px] leading-[1.5] text-[var(--lp-fg-2)] sm:text-[20px]">
                Tracyn keeps a record of everything your AI agents do, asks a person before the
                risky parts, and turns it all into evidence your auditors accept.
              </p>
            </div>

            <div ref={stageWrapRef} className="lp-hero-stage relative mt-8 shrink-0 sm:mt-10">
              <div
                ref={stageRef}
                className="absolute left-0 top-0 origin-top-left"
                style={{ width: STAGE_W, height: STAGE_H }}
              >
                {/* The folder the cards tuck into. */}
                <div
                  ref={folderRef}
                  className="absolute left-0 rounded-[28px] bg-[var(--lp-sand)]"
                  style={{ top: FOLDER_TOP, width: STAGE_W, height: FOLDER_H, opacity: 0 }}
                >
                  <div className="flex items-center justify-between px-6" style={{ height: FOLDER_HEADER }}>
                    <span className="text-[21px] font-semibold tracking-[-0.01em]">Audit trail</span>
                    <div
                      ref={sealRef}
                      className="flex items-center gap-1.5 rounded-full bg-[#1f9a5f] px-3 py-1.5 text-[13px] font-semibold text-white"
                      style={{ opacity: 0 }}
                    >
                      <Check className="h-4 w-4" strokeWidth={3} />
                      Sealed
                    </div>
                  </div>
                </div>

                {CARDS.map((c, i) => {
                  const isOpen = open === i;
                  const Icon = c.icon;
                  return (
                    <div
                      key={c.title}
                      ref={(el) => {
                        cardRefs.current[i] = el;
                      }}
                      role="button"
                      tabIndex={0}
                      aria-expanded={isOpen}
                      data-open={isOpen}
                      onClick={() => toggle(i)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          toggle(i);
                        }
                      }}
                      className="lp-card text-white"
                      style={{
                        background: c.bg,
                        width: CARD_W,
                        height: CARD_H,
                        borderRadius: 28,
                        transform: `translate3d(20px, ${i * CARD_STEP}px, 0)`,
                        zIndex: i + 1,
                      }}
                    >
                      <div className="lp-card-row">
                        <span className="lp-card-icon" style={{ color: c.bg }}>
                          <Icon strokeWidth={2.25} />
                        </span>
                        <span className="lp-card-title">{c.title}</span>
                        <span className="lp-card-close" aria-hidden>
                          <X className="h-4 w-4" strokeWidth={2.5} />
                        </span>
                      </div>
                      <div className="lp-card-more px-6 pb-6 text-[16px] leading-[1.5]">
                        <div className="text-white/75">{c.who}</div>
                        <p className="mt-3 text-[17px]">{c.story}</p>
                        <div className="mt-4 inline-flex items-center gap-1.5 rounded-full bg-white/20 px-3 py-1 text-[13.5px] font-medium">
                          <Check className="h-3.5 w-3.5" strokeWidth={3} />
                          {c.outcome}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
              <div className="lp-hero-hint absolute inset-x-0 top-full pt-4 text-center text-[13px] text-[var(--lp-fg-3)]">
                Click a card to see what happened
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
