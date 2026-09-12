import type { Metadata } from "next";
import { Landing } from "@/components/landing/landing";

export const metadata: Metadata = {
  title: "AuditAgent — It's not a log. It's evidence.",
  description:
    "AuditAgent records every action your AI agents take, pauses the risky ones for a human, and turns the trail into audit-ready evidence. One decorator to start.",
};

export default function RootPage() {
  return <Landing />;
}
