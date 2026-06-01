// lib/market-sources.ts
// Single source of truth for which markets Lumora knows about, which data
// source backs them, and whether they are live-supported, demo, planned, or
// unsupported. Pure data + helpers — no network, no dependencies.

export type MarketStatus = "supported" | "demo" | "planned" | "unsupported";

export interface MarketSource {
  symbol: string;            // e.g. "BTCUSDT"
  displayName: string;       // e.g. "BTC / USDT"
  base: string;              // e.g. "BTC"
  quote: string;             // e.g. "USDT"
  defaultExchange: string;   // exchange slug, or "planned" when none wired
  supportedExchanges: string[];
  status: MarketStatus;
  sourceNote?: string;
  tags?: string[];
}

// Ordered — the UI dropdown follows this order.
export const MARKET_SOURCES: MarketSource[] = [
  {
    symbol: "BTCUSDT",
    displayName: "BTC / USDT",
    base: "BTC",
    quote: "USDT",
    defaultExchange: "binance_spot",
    supportedExchanges: ["binance_spot", "bybit_spot", "okx_spot"],
    status: "supported",
    sourceNote: "Binance Spot depth supported in MVP plan",
    tags: ["major"],
  },
  {
    symbol: "ETHUSDT",
    displayName: "ETH / USDT",
    base: "ETH",
    quote: "USDT",
    defaultExchange: "binance_spot",
    supportedExchanges: ["binance_spot", "bybit_spot", "okx_spot"],
    status: "supported",
    sourceNote: "Binance Spot depth supported in MVP plan",
    tags: ["major"],
  },
  {
    symbol: "SOLUSDT",
    displayName: "SOL / USDT",
    base: "SOL",
    quote: "USDT",
    defaultExchange: "binance_spot",
    supportedExchanges: ["binance_spot", "bybit_spot", "okx_spot"],
    status: "supported",
    sourceNote: "Binance Spot depth supported in MVP plan",
    tags: ["major"],
  },
  {
    symbol: "HYPEUSDT",
    displayName: "HYPE / USDT",
    base: "HYPE",
    quote: "USDT",
    defaultExchange: "hyperliquid",
    supportedExchanges: ["hyperliquid"],
    status: "demo",
    sourceNote: "Hyperliquid source planned. Demo data shown for now.",
    tags: ["planned"],
  },
  {
    symbol: "XMRUSDT",
    displayName: "XMR / USDT",
    base: "XMR",
    quote: "USDT",
    defaultExchange: "planned",
    supportedExchanges: [],
    status: "planned",
    sourceNote: "XMR source planned. Binance Spot depth unavailable for Monero.",
    tags: ["planned", "privacy"],
  },
];

const BY_SYMBOL: Record<string, MarketSource> = Object.fromEntries(
  MARKET_SOURCES.map((m) => [m.symbol, m]),
);

/** Look up a market's metadata. Returns undefined for unknown symbols. */
export function getMarketSource(symbol: string): MarketSource | undefined {
  return BY_SYMBOL[symbol.toUpperCase()];
}

/** All known symbols, in dropdown order. */
export function getMarketSymbols(): string[] {
  return MARKET_SOURCES.map((m) => m.symbol);
}

/** Only symbols whose data source is considered live-supported. */
export function getSupportedSymbols(): string[] {
  return MARKET_SOURCES.filter((m) => m.status === "supported").map(
    (m) => m.symbol,
  );
}

/** Whether a symbol is known to the metadata system at all. */
export function isKnownSymbol(symbol: string): boolean {
  return symbol.toUpperCase() in BY_SYMBOL;
}

/** Short capitalized label for the status badge ("Supported" / "Demo" / …). */
export function getMarketStatusLabel(symbol: string): string {
  const m = getMarketSource(symbol);
  if (!m) return "Unknown";
  switch (m.status) {
    case "supported":
      return "Supported";
    case "demo":
      return "Demo";
    case "planned":
      return "Planned";
    case "unsupported":
      return "Unsupported";
    default:
      return "Unknown";
  }
}

/**
 * True when a market should never be presented as live data — i.e. anything
 * that is not "supported" (demo, planned, unsupported, or unknown).
 */
export function isMarketDemoOnly(symbol: string): boolean {
  const m = getMarketSource(symbol);
  return m ? m.status !== "supported" : true;
}

/** Human-readable source note, or null when none is defined. */
export function getMarketSourceNote(symbol: string): string | null {
  return getMarketSource(symbol)?.sourceNote ?? null;
}
