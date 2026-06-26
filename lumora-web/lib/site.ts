// Single source of truth for site-wide constants (LM72A). metadata, robots,
// sitemap, manifest and JSON-LD all read from here so the origin/brand never
// drift. Override the origin per-environment with NEXT_PUBLIC_SITE_URL.

export const SITE_URL = (
  process.env.NEXT_PUBLIC_SITE_URL ?? "https://lumora.app"
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
export const LEGAL_DETAILS_FILLED = false;

export const OPERATOR = {
  // Required for the Impressum (DDG §5). A private individual running the beta
  // needs at minimum: name, postal address, email.
  name: "[ OPERATOR NAME: full legal name or company ]",
  // If a company (GmbH/UG): also fill register + represented-by below.
  representedBy: "", // e.g. "Managing Director: …" (leave "" for a sole operator)
  street: "[ STREET & NUMBER ]",
  city: "[ POSTAL CODE & CITY ]",
  country: "Germany",
  email: "[ contact@yourdomain ]",
  phone: "", // optional
  registerCourt: "", // e.g. "Amtsgericht …, HRB ……" (company only)
  vatId: "", // e.g. "DE………" (if VAT-registered)
} as const;

// Hosting / data processors named in the Datenschutzerklärung. Update if the
// stack changes. Supabase is the email/waitlist + invite-code processor; the
// host is whoever serves the Next.js app (Vercel by default — change if not).
export const PROCESSORS = {
  host: "[ HOSTING PROVIDER: e.g. Vercel Inc., 340 S Lemon Ave #4133, Walnut, CA 91789, USA ]",
  database: "Supabase, Inc., 970 Toa Payoh North #07-04, Singapore 318992 (database, waitlist + invite codes)",
} as const;

// Bump when legal copy materially changes.
export const LEGAL_LAST_UPDATED = "25 June 2026";

// Footer legal links — one place so landing + app + legal pages stay in sync.
export const LEGAL_LINKS: ReadonlyArray<{ href: string; label: string }> = [
  { href: "/impressum", label: "Impressum" },
  { href: "/datenschutz", label: "Datenschutz" },
  { href: "/risk", label: "Risk & Terms" },
];
