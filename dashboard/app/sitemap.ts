import type { MetadataRoute } from "next";
import { SITE_URL } from "@/lib/site";

// Only the pages a signed-out visitor (or a search engine) can actually
// reach and would want indexed. Everything under (app) requires a session,
// so there's nothing for a crawler to see there even if it tried.
export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  return [
    { url: SITE_URL, lastModified: now, changeFrequency: "weekly", priority: 1 },
    { url: `${SITE_URL}/docs`, lastModified: now, changeFrequency: "monthly", priority: 0.8 },
    { url: `${SITE_URL}/login`, lastModified: now, changeFrequency: "yearly", priority: 0.3 },
  ];
}
