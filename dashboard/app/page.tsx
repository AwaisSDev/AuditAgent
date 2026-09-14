import type { Metadata } from "next";
import { Landing } from "@/components/landing/landing";
import { SITE_URL } from "@/lib/site";

const TITLE = "AuditAgent: It's not a log. It's evidence.";
const DESCRIPTION =
  "AuditAgent records every action your AI agents take, pauses the risky ones for a human, and turns the trail into audit-ready evidence. One decorator to start.";

export const metadata: Metadata = {
  // `absolute` opts out of the root layout's title template (`%s / AuditAgent`)
  // -- this title already reads as a complete, standalone tagline.
  title: { absolute: TITLE },
  description: DESCRIPTION,
  // Next.js does NOT deep-merge nested metadata objects across layout/page --
  // a child's `openGraph`/`twitter` object fully replaces the parent's, so
  // images/type/siteName have to be repeated here too, not just title/description.
  openGraph: {
    title: TITLE,
    description: DESCRIPTION,
    url: SITE_URL,
    siteName: "AuditAgent",
    images: [{ url: "/logo.png", width: 512, height: 512 }],
    type: "website",
  },
  twitter: { card: "summary", title: TITLE, description: DESCRIPTION, images: ["/logo.png"] },
};

export default function RootPage() {
  return <Landing />;
}
