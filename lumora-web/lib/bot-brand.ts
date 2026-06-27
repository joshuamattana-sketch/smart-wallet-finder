// Single source of truth for the Gold Bot signal product brand. This is a
// SEPARATE serious "clean fintech" brand from Lumora (the trading terminal).
// Rename `name` / `product` once you pick the real brand — everything reads here.
//
// PLACEHOLDER name: "Meridian". Change it in one place.

export const BOT_BRAND = {
  name: "Meridian",
  product: "Meridian Signals",
  tagline: "Algorithmic gold, XAUUSD",
  blurb:
    "One strategy, traded by the rules, on gold. You pick how to take profit and you place every trade yourself. We show you exactly how it has gone so far, with nothing rounded up and nothing hidden.",
  // Product switch targets (same app, two brands).
  terminalHref: "/", // Lumora terminal landing (canonical)
  // The switch jumps straight to the booted hero (skips the galaxy intro) so the
  // round-trip feels like a quick toggle, not a full re-intro each time.
  terminalSwitchHref: "/?intro=off",
  signalsHref: "/bot", // this product
} as const;

// Risk / legal posture shown on the landing. Kept plain and honest: the product
// is research and signals, not advice and not execution.
export const BOT_RISK_NOTE =
  "This is not investment advice. Trading leveraged products can lose you money quickly. " +
  "Past results, including backtested ones, tell you nothing certain about the future. " +
  "Signals are information. Every trade is your decision, and your risk.";
