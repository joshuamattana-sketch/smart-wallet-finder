import { NextResponse } from "next/server";
import type {
  HeatmapApiPayload,
  HeatmapCell,
  HeatmapWall,
} from "@/lib/heatmap-types";

// LM82A — live order-book read straight from Binance public market data.
//
// This is the dashboard's live source: no Supabase, no writer, no DB load (so
// it can't trigger the disk-IO outage that the historical heatmap pipeline
// did). It fetches a depth snapshot from data-api.binance.vision (Binance's
// auth-free, geo-unblocked market-data host), aggregates it into the same
// HeatmapApiPayload shape the dashboard already consumes, and tags it
// resolvedSource:"live" so the read strip / watchlist / setups light up green.

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const BINANCE = "https://data-api.binance.vision";
const DEPTH_LIMIT = 1000; // snapshot depth (weight 10) — plenty for walls
const WALLS_PER_SIDE = 6;
const CELLS_PER_SIDE = 60;

type Level = { price: number; usd: number };
type Bucket = { price: number; usd: number; side: "bid" | "ask" };

// Aggregate raw [price, qty] depth levels into price buckets (~5 bps wide), so
// nearby resting liquidity collapses into trader-facing "walls" instead of
// thousands of dust levels.
function bucketize(raw: [string, string][], side: "bid" | "ask", step: number): Map<number, Bucket> {
  const out = new Map<number, Bucket>();
  for (const [pStr, qStr] of raw) {
    const price = Number(pStr);
    const qty = Number(qStr);
    if (!Number.isFinite(price) || !Number.isFinite(qty) || qty <= 0) continue;
    const key = Math.round(price / step);
    const bucketPrice = key * step;
    const usd = price * qty;
    const prev = out.get(key);
    if (prev) prev.usd += usd;
    else out.set(key, { price: bucketPrice, usd, side });
  }
  return out;
}

function vals(m: Map<number, Bucket>): Bucket[] {
  return Array.from(m.values());
}

function topBuckets(map: Map<number, Bucket>, n: number): Bucket[] {
  return vals(map).sort((a, b) => b.usd - a.usd).slice(0, n);
}

function buildPayload(symbol: string, depth: { bids: [string, string][]; asks: [string, string][] }): HeatmapApiPayload {
  const bestBid = Number(depth.bids[0]?.[0]);
  const bestAsk = Number(depth.asks[0]?.[0]);
  const mid = (bestBid + bestAsk) / 2;
  // ~5 bps bucket step, never zero.
  const step = Math.max(mid * 0.0005, 1e-8);

  const bidBuckets = bucketize(depth.bids, "bid", step);
  const askBuckets = bucketize(depth.asks, "ask", step);

  const maxUsd = Math.max(
    1,
    ...[...vals(bidBuckets), ...vals(askBuckets)].map((b) => b.usd),
  );
  const intensity = (usd: number) => Math.max(1, Math.round((usd / maxUsd) * 100));

  // Walls — strongest buckets per side (drives setup entry/target/stop levels).
  const wallBuckets = [
    ...topBuckets(bidBuckets, WALLS_PER_SIDE),
    ...topBuckets(askBuckets, WALLS_PER_SIDE),
  ];
  const walls: HeatmapWall[] = wallBuckets.map((b) => ({
    price_bucket: b.price,
    side: b.side,
    total_usd: Math.round(b.usd),
    intensity: intensity(b.usd),
    label: b.side === "bid" ? "Major Bid Wall" : "Major Ask Wall",
  }));

  // Cells — top buckets per side carry the bid/ask intensity that
  // heatmapIntensitySummary turns into the order-book skew (→ bias).
  const cellBuckets = [
    ...topBuckets(bidBuckets, CELLS_PER_SIDE),
    ...topBuckets(askBuckets, CELLS_PER_SIDE),
  ];
  const cells: HeatmapCell[] = cellBuckets.map((b) => {
    const i = intensity(b.usd);
    return {
      p: 0,
      t: 0,
      bid: b.side === "bid" ? i : 0,
      ask: b.side === "ask" ? i : 0,
      total: i,
      price_bucket: b.price,
    };
  });

  const prices = [...vals(bidBuckets), ...vals(askBuckets)].map((b) => b.price);
  const priceMin = prices.length ? Math.min(...prices) : null;
  const priceMax = prices.length ? Math.max(...prices) : null;
  const now = new Date().toISOString();

  return {
    symbol,
    exchange: "binance_spot",
    timeframe: "5m",
    priceMin,
    priceMax,
    priceStep: step,
    timeBuckets: [now],
    cells,
    walls,
    summary: {
      symbol,
      frame_count: 1,
      price_min: priceMin ?? mid,
      price_max: priceMax ?? mid,
      time_start: now,
      time_end: now,
      max_bid_intensity: 100,
      max_ask_intensity: 100,
      max_total_intensity: 100,
      wall_count: walls.length,
      currentPrice: mid,
    },
    meta: {
      schemaVersion: "1.0",
      generatedAt: now,
      cellCount: cells.length,
      wallCount: walls.length,
      isDemo: false,
      sourceAvailable: true,
      dataSource: "binance_rest_live",
      source: "live",
      collector: "binance_rest",
      resolvedSource: "live",
      requestedSource: "live",
      isFallback: false,
      stale: false,
      currentPrice: mid,
      liveUpdatedAt: now,
    },
    pricePath: [{ t: now, price: mid, bestBid, bestAsk }],
  };
}

export async function GET(req: Request) {
  const url = new URL(req.url);
  const symbol = (url.searchParams.get("symbol") ?? "BTCUSDT").toUpperCase();
  // Hard whitelist the shape — this value goes into an outbound URL.
  if (!/^[A-Z0-9]{5,15}$/.test(symbol)) {
    return NextResponse.json({ error: "bad_symbol", message: "Invalid symbol." }, { status: 400 });
  }

  try {
    const res = await fetch(`${BINANCE}/api/v3/depth?symbol=${symbol}&limit=${DEPTH_LIMIT}`, {
      cache: "no-store",
      // Don't hang a request on a slow upstream.
      signal: AbortSignal.timeout(4000),
    });
    if (!res.ok) {
      return NextResponse.json(
        { error: "upstream", message: `Binance depth ${res.status}` },
        { status: 502 },
      );
    }
    const depth = (await res.json()) as { bids: [string, string][]; asks: [string, string][] };
    if (!depth?.bids?.length || !depth?.asks?.length) {
      return NextResponse.json(
        { error: "empty", message: "Empty order book." },
        { status: 502 },
      );
    }
    return NextResponse.json(buildPayload(symbol, depth), {
      headers: { "Cache-Control": "no-store" },
    });
  } catch (e) {
    return NextResponse.json(
      { error: "fetch_failed", message: e instanceof Error ? e.message : "Live book unavailable." },
      { status: 502 },
    );
  }
}
