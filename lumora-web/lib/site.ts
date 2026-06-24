// Single source of truth for site-wide constants (LM72A). metadata, robots,
// sitemap, manifest and JSON-LD all read from here so the origin/brand never
// drift. Override the origin per-environment with NEXT_PUBLIC_SITE_URL.

export const SITE_URL = (
  process.env.NEXT_PUBLIC_SITE_URL ?? "https://lumora.app"
).replace(/\/$/, "");

export const SITE_NAME = "Lumora";

export const SITE_TITLE = "Lumora — Trading Intelligence Terminal";

export const SITE_DESCRIPTION =
  "Lumora is a liquidity intelligence terminal for crypto — orderbook depth, whale flow, funding, open interest, liquidity heatmaps and sweep-risk zones, distilled into a single market read.";

// Real Discord invite. Override with NEXT_PUBLIC_DISCORD_URL if it ever rotates.
export const DISCORD_URL =
  process.env.NEXT_PUBLIC_DISCORD_URL ?? "https://discord.gg/5RNbkW962";
