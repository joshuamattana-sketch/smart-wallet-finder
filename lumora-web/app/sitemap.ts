import type { MetadataRoute } from "next";
import { SITE_URL } from "@/lib/site";

// Only the public marketing page is indexable; the terminal/app routes are
// private beta and excluded (see robots.ts + the (app) layout noindex).
export default function sitemap(): MetadataRoute.Sitemap {
  return [
    {
      url: SITE_URL,
      changeFrequency: "weekly",
      priority: 1,
    },
    { url: `${SITE_URL}/impressum`, changeFrequency: "yearly", priority: 0.3 },
    { url: `${SITE_URL}/datenschutz`, changeFrequency: "yearly", priority: 0.3 },
    { url: `${SITE_URL}/risk`, changeFrequency: "yearly", priority: 0.3 },
  ];
}
