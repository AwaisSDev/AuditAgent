import type { MetadataRoute } from "next";
import { SITE_URL } from "@/lib/site";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        // Everything under the authenticated app shell needs a session and
        // has nothing for a crawler to index; keep crawl budget on the
        // marketing/docs pages instead.
        disallow: ["/dashboard", "/approvals", "/questionnaires", "/policy", "/soc2", "/settings"],
      },
    ],
    sitemap: `${SITE_URL}/sitemap.xml`,
  };
}
