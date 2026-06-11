// components/charts/mock-intelligence-chart-data.ts
// LM68B — deterministic mock scene for the Unified Intelligence Chart.
//
// One believable BTCUSDT 5m session (~10 hours, 120 candles) that interacts
// with the mock liquidity zones the way The Lumora Field hero narrates it:
// price drifts into the ask band near 68,000, a whale sell rejects it, the
// bid band at 67,350 absorbs and holds twice, then price recovers.
//
// Everything is seeded/fixed — no Date.now(), no Math.random() at module
// scope — so SSR and client always agree and snapshots are reproducible.

// ── View modes / overlay state ───────────────────────────────────────────────

export type ViewMode = "clean" | "assisted" | "full";

export interface OverlayState {
  heatmap: boolean;
  whales: boolean;
  pressure: boolean;
  read: boolean;
}

export const MODE_PRESETS: Record<ViewMode, OverlayState> = {
  clean:    { heatmap: false, whales: false, pressure: false, read: false },
  assisted: { heatmap: true,  whales: true,  pressure: false, read: true  },
  full:     { heatmap: true,  whales: true,  pressure: true,  read: true  },
};

export function sameOverlayState(a: OverlayState, b: OverlayState): boolean {
  return (
    a.heatmap === b.heatmap &&
    a.whales === b.whales &&
    a.pressure === b.pressure &&
    a.read === b.read
  );
}

/** Which preset (if any) the given overlay state matches exactly. */
export function matchedMode(s: OverlayState): ViewMode | null {
  for (const mode of ["clean", "assisted", "full"] as const) {
    if (sameOverlayState(s, MODE_PRESETS[mode])) return mode;
  }
  return null;
}

// ── Data contracts (mock-shaped; live adapters arrive in LM68C/D) ───────────

export interface ChartCandle {
  time: number; // unix seconds (bucket open)
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface LiquidityZone {
  id: string;
  side: "bid" | "ask";
  priceMin: number;
  priceMax: number;
  strength: number; // 0–100 → band alpha
  notionalUsd: number;
  label: string;
}

export interface SweepZone {
  id: string;
  priceMin: number;
  priceMax: number;
  severity: "watch" | "elevated";
  label: string;
}

export interface WhaleChartEvent {
  id: string;
  time: number; // unix seconds — snapped to a candle bucket
  price: number;
  side: "BUY" | "SELL";
  notionalUsd: number;
  risk: "LOW" | "MEDIUM" | "HIGH";
  label: string;
}

export interface FuturesContext {
  fundingRatePct: number; // already in %
  oiChangePct: number;
  pressure: "long" | "short" | "balanced";
  leverageHeat: "low" | "medium" | "high"; // aggregate bucket only (LM64)
}

export interface CurrentRead {
  bias: "LONG" | "SHORT" | "NEUTRAL";
  score: number;      // 0–100
  confidence: number; // 0–100
  risk: "LOW" | "MEDIUM" | "HIGH";
  reason: string;
  action: string;
}

export interface IntelligenceChartScene {
  symbol: string;
  timeframe: string;
  candles: ChartCandle[];
  zones: LiquidityZone[];
  sweeps: SweepZone[];
  whales: WhaleChartEvent[];
  futures: FuturesContext;
  read: CurrentRead;
}

// ── Candle synthesis ─────────────────────────────────────────────────────────

/** Fixed session anchor (unix seconds). Arbitrary but stable. */
const BASE_TIME = 1_760_000_000;
const BAR_SECONDS = 300; // 5m
const BAR_COUNT = 120;

/** Deterministic PRNG — same sequence every render, server and client. */
function mulberry32(seed: number): () => number {
  let a = seed;
  return () => {
    a += 0x6d2b79f5;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Close-price waypoints (bar index → target) shaping the Field narrative:
// approach → rejection at the ask band → absorption at the bid band (held
// twice) → recovery.
const WAYPOINTS: Array<[number, number]> = [
  [0, 67_250], [18, 67_520], [35, 67_940], [40, 67_860], [48, 67_550],
  [56, 67_340], [64, 67_480], [74, 67_430], [84, 67_360], [96, 67_560],
  [110, 67_680], [119, 67_620],
];

function targetAt(i: number): number {
  for (let s = 0; s < WAYPOINTS.length - 1; s++) {
    const [i0, p0] = WAYPOINTS[s];
    const [i1, p1] = WAYPOINTS[s + 1];
    if (i >= i0 && i <= i1) {
      const f = i1 === i0 ? 0 : (i - i0) / (i1 - i0);
      return p0 + (p1 - p0) * f;
    }
  }
  return WAYPOINTS[WAYPOINTS.length - 1][1];
}

// Bars where whale prints land — volume spikes there.
const WHALE_BARS = new Set([36, 56, 84, 102]);

function buildCandles(): ChartCandle[] {
  const rand = mulberry32(1337);
  const candles: ChartCandle[] = [];
  let prevClose = targetAt(0);

  for (let i = 0; i < BAR_COUNT; i++) {
    const drift = targetAt(i);
    const close = i === BAR_COUNT - 1 ? drift : drift + (rand() - 0.5) * 55;
    const open = i === 0 ? drift - 18 : prevClose;
    const high = Math.max(open, close) + rand() * 28;
    const low = Math.min(open, close) - rand() * 28;
    const boost = WHALE_BARS.has(i) ? 3.1 : i >= 34 && i <= 41 ? 1.8 : 1;
    const volume = Math.round((22 + rand() * 26) * boost);

    candles.push({
      time: BASE_TIME + i * BAR_SECONDS,
      open: Math.round(open),
      high: Math.round(high),
      low: Math.round(low),
      close: Math.round(close),
      volume,
    });
    prevClose = close;
  }
  return candles;
}

export const MOCK_CANDLES: ChartCandle[] = buildCandles();

// ── Intelligence layers ──────────────────────────────────────────────────────

export const MOCK_ZONES: LiquidityZone[] = [
  { id: "z-ask-38m", side: "ask", priceMin: 67_980, priceMax: 68_120, strength: 92, notionalUsd: 38_000_000, label: "ASK · $38M" },
  { id: "z-ask-12m", side: "ask", priceMin: 67_750, priceMax: 67_820, strength: 58, notionalUsd: 12_000_000, label: "ASK · $12M" },
  { id: "z-bid-26m", side: "bid", priceMin: 67_300, priceMax: 67_390, strength: 84, notionalUsd: 26_000_000, label: "BID · $26M" },
  { id: "z-bid-9m",  side: "bid", priceMin: 66_980, priceMax: 67_060, strength: 46, notionalUsd: 9_000_000,  label: "BID · $9M" },
];

/** Assisted mode shows only the zones that matter. */
export function isKeyZone(z: LiquidityZone): boolean {
  return z.strength >= 70;
}

export const MOCK_SWEEPS: SweepZone[] = [
  {
    id: "sweep-66k8",
    priceMin: 66_780,
    priceMax: 66_900,
    severity: "watch",
    label: "SWEEP RISK · POSSIBLE FLUSH",
  },
];

function whaleAt(
  bar: number,
  side: "BUY" | "SELL",
  notionalUsd: number,
  risk: WhaleChartEvent["risk"],
): WhaleChartEvent {
  const candle = MOCK_CANDLES[bar];
  return {
    id: `whale-${bar}`,
    time: candle.time,
    price: candle.close,
    side,
    notionalUsd,
    risk,
    label: `$${(notionalUsd / 1_000_000).toFixed(1)}M`,
  };
}

export const MOCK_WHALES: WhaleChartEvent[] = [
  whaleAt(36, "SELL", 7_100_000, "HIGH"),
  whaleAt(56, "BUY", 4_200_000, "MEDIUM"),
  whaleAt(84, "BUY", 2_800_000, "MEDIUM"),
  whaleAt(102, "SELL", 1_600_000, "LOW"),
];

/** Assisted mode shows only impactful whale prints. */
export function isImportantWhale(w: WhaleChartEvent): boolean {
  return w.risk === "HIGH" || w.notionalUsd >= 4_000_000;
}

export const MOCK_FUTURES: FuturesContext = {
  fundingRatePct: 0.012,
  oiChangePct: 2.4,
  pressure: "long",
  leverageHeat: "medium",
};

export const MOCK_READ: CurrentRead = {
  bias: "LONG",
  score: 72,
  confidence: 68,
  risk: "MEDIUM",
  reason: "Bid band at 67,350 absorbed two sell waves while ask pressure thins.",
  action: "Watch reclaim of 67,500 · read invalidates below 66,800.",
};

export const MOCK_SCENE: IntelligenceChartScene = {
  symbol: "BTCUSDT",
  timeframe: "5m",
  candles: MOCK_CANDLES,
  zones: MOCK_ZONES,
  sweeps: MOCK_SWEEPS,
  whales: MOCK_WHALES,
  futures: MOCK_FUTURES,
  read: MOCK_READ,
};
