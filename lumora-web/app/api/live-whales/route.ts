import { NextResponse } from "next/server";
import type { WhaleAlertView } from "@/lib/whale-alerts-loader";

// LM82B — live whale tape straight from Binance public aggTrades. Same posture
// as /api/live-book: no Supabase, no DB load. Pulls recent aggregated trades
// for the core symbols, keeps the prints above a per-symbol notional threshold,
// and returns the largest as WhaleAlertView rows. This replaces the stale
// Supabase whale_events feed (whose writer is suspended) on the dashboard.

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const BINANCE = "https://data-api.binance.vision";

// Per-symbol notional floors (USD), tuned to the real spot-print distribution
// in a recent ~1-2 min aggTrades window (the largest BTC spot prints run
// ~$25-50k, not the $150k+ a futures tape shows). Floors sit near each
// symbol's top-decile so the tape surfaces the genuinely-largest recent prints.
const SYMBOLS: { symbol: string; min: number }[] = [
  { symbol: "BTCUSDT", min: 25_000 },
  { symbol: "ETHUSDT", min: 18_000 },
  { symbol: "SOLUSDT", min: 10_000 },
];
// Cap how many of each symbol's prints enter the merge, so one busy market
// can't crowd out the others.
const PER_SYMBOL_CAP = 8;

type AggTrade = { a: number; p: string; q: string; T: number; m: boolean };

function fmtSize(usd: number): string {
  if (usd >= 1_000_000) return `$${(usd / 1_000_000).toFixed(1)}M`;
  if (usd >= 1_000) return `$${Math.round(usd / 1_000)}K`;
  return `$${Math.round(usd)}`;
}

function hhmm(ms: number): string {
  const d = new Date(ms);
  return `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}`;
}

function toAlert(symbol: string, t: AggTrade): WhaleAlertView {
  const price = Number(t.p);
  const qty = Number(t.q);
  const usd = price * qty;
  // m = buyer is the maker → the aggressor is the SELLER. m=false → aggressive buy.
  const side: "BUY" | "SELL" = t.m ? "SELL" : "BUY";
  const base = symbol.replace(/USDT$/, "");
  const risk = usd >= 40_000 ? "HIGH" : usd >= 20_000 ? "MEDIUM" : "LOW";
  return {
    id: `${symbol}-${t.a}`,
    time: hhmm(t.T),
    symbol,
    side,
    size: fmtSize(usd),
    exchange: "Binance",
    leverage: "1×",
    type: side === "BUY" ? "Aggressive Buy" : "Aggressive Sell",
    risk,
    confidence: Math.min(99, 50 + Math.round(usd / 1000)),
    reason: `${fmtSize(usd)} market ${side === "BUY" ? "buy lifted" : "sell hit"} ${base} on Binance spot.`,
    action: side === "BUY" ? "Watch for follow-through." : "Watch for absorption.",
  };
}

type Hit = { symbol: string; trade: AggTrade };

async function fetchSymbol({ symbol, min }: { symbol: string; min: number }): Promise<Hit[]> {
  try {
    const res = await fetch(`${BINANCE}/api/v3/aggTrades?symbol=${symbol}&limit=1000`, {
      cache: "no-store",
      signal: AbortSignal.timeout(4000),
    });
    if (!res.ok) return [];
    const trades = (await res.json()) as AggTrade[];
    return trades
      .filter((t) => Number(t.p) * Number(t.q) >= min)
      .sort((a, b) => Number(b.p) * Number(b.q) - Number(a.p) * Number(a.q))
      .slice(0, PER_SYMBOL_CAP)
      .map((trade) => ({ symbol, trade }));
  } catch {
    return [];
  }
}

export async function GET(req: Request) {
  const limit = Math.min(30, Math.max(1, Number(new URL(req.url).searchParams.get("limit")) || 12));

  const perSymbol = await Promise.all(SYMBOLS.map(fetchSymbol));
  const alerts = perSymbol
    .flat()
    .sort((a, b) => b.trade.T - a.trade.T) // newest first by real trade time
    .slice(0, limit)
    .map(({ symbol, trade }) => toAlert(symbol, trade));

  return NextResponse.json(
    {
      data_source: alerts.length > 0 ? "binance" : "empty",
      generated_at: new Date().toISOString(),
      row_count: alerts.length,
      alerts,
    },
    { headers: { "Cache-Control": "no-store" } },
  );
}
