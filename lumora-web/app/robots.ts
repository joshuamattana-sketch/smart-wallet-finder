import type { MetadataRoute } from "next";
import { SITE_URL } from "@/lib/site";

// Allow the marketing surface, keep the gated app + API out of the index.
export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: ["/dashboard", "/terminal", "/liquidity-map", "/whale-alerts", "/paper-trading", "/gold-bot", "/api/"],
    },
    sitemap: `${SITE_URL}/sitemap.xml`,
    host: SITE_URL,
  };
}
