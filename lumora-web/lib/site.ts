// Single source of truth for site-wide constants (LM72A). metadata, robots,
// sitemap, manifest and JSON-LD all read from here so the origin/brand never
// drift. Override the origin per-environment with NEXT_PUBLIC_SITE_URL.

export const SITE_URL = (
  process.env.NEXT_PUBLIC_SITE_URL ?? "https://lumora-app.app"
).replace(/\/$/, "");

export const SITE_NAME = "Lumora";

export const SITE_TITLE = "Lumora · Trading Intelligence Terminal";

export const SITE_DESCRIPTION =
  "Lumora is a liquidity intelligence terminal for crypto: orderbook depth, whale flow, funding, open interest, liquidity heatmaps and sweep-risk zones, distilled into a single market read.";

// Real Discord invite. Override with NEXT_PUBLIC_DISCORD_URL if it ever rotates.
export const DISCORD_URL =
  process.env.NEXT_PUBLIC_DISCORD_URL ?? "https://discord.gg/5RNbkW962";

// ── Legal / operator identity (LM77A) ────────────────────────────────────────
// Single source of truth for Impressum + Datenschutz. Everything is a PLACEHOLDER
// until the operator fills real details — keep LEGAL_DETAILS_FILLED = false until
// then, which renders a visible "replace before release" banner on every legal
// page so it can never ship unfilled.
//
// ⚠️ BEFORE RELEASE: fill every "[ … ]" value below, then set
//    LEGAL_DETAILS_FILLED = true. That removes the warning banners.
export const LEGAL_DETAILS_FILLED = true;

export const OPERATOR = {
  // Swiss private operator (UWG Art. 3 Abs. 1 lit. s). Minimum: full name,
  // postal address, contact email. Street is optional for a free, non-commerce
  // beta — add it once paid plans launch.
  name: "Joshua Mattana",
  // Company only (GmbH/AG/UG): managing director / authorised representative.
  representedBy: "", // leave "" for a sole private operator
  street: "", // optional — add street & number once Lumora sells anything
  city: "8200 Schaffhausen",
  country: "Switzerland",
  email: "legal.lumora@gmail.com",
  phone: "", // optional
  registerCourt: "", // company only (Handelsregister entry)
  vatId: "", // company only (CHE-… MWST, if VAT-registered)
} as const;

// Hosting / data processors named in the Datenschutzerklärung. Update if the
// stack changes. Verify each address against the provider's current DPA before
// relying on it. Analytics only runs after the visitor consents (LM78A).
export const PROCESSORS = {
  host: "Vercel Inc., 340 S Lemon Ave #4133, Walnut, CA 91789, USA (hosting, server logs)",
  database:
    "Supabase, Inc., 970 Toa Payoh North #07-04, Singapore 318992 (database, waitlist + invite codes)",
  analytics:
    "Google Ireland Ltd., Gordon House, Barrow Street, Dublin 4, Ireland (Google Analytics 4 — only after consent)",
} as const;

// Bump when legal copy materially changes.
export const LEGAL_LAST_UPDATED = "28 June 2026";

// Footer legal links — one place so landing + app + legal pages stay in sync.
export const LEGAL_LINKS: ReadonlyArray<{ href: string; label: string }> = [
  { href: "/impressum", label: "Impressum" },
  { href: "/datenschutz", label: "Datenschutz" },
  { href: "/risk", label: "Risk & Terms" },
];
