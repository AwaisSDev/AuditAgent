// Used for SEO only: metadataBase (absolute OpenGraph/Twitter image URLs),
// sitemap.xml, and robots.txt. Falls back to the actual deployed domain so
// a missing env var never silently breaks metadata generation.
export const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || "https://auditagent.cloud";
