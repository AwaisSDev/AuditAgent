"use client";

import { useEffect, useRef, type ReactNode } from "react";

/* A section that, once ~20% visible, gets [data-scrolled] and never loses
   it. Children opt in with data-fade-order="1..5" (see landing.css). */
export function Reveal({
  id,
  className,
  children,
  as: Tag = "section",
}: {
  id?: string;
  className?: string;
  children: ReactNode;
  as?: "section" | "div" | "footer";
}) {
  const ref = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            el.setAttribute("data-scrolled", "true");
            io.disconnect();
          }
        }
      },
      { threshold: 0.2 }
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <Tag ref={ref as never} id={id} data-fade="" className={className}>
      {children}
    </Tag>
  );
}
