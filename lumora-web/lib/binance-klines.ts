// lib/binance-klines.ts
// LM68C — public Binance Spot market data (klines/candles) for the
// Intelligence Chart. Public read-only endpoints, no API keys, no secrets.
//
// REST:  https://api.binance.com/api/v3/klines   (initial snapshot)
// WS:    wss://stream.binance.com:9443/ws/<sym>@kline_<interval>  (updates)
//
// Everything here is transport + parsing only — no React. Bad rows/messages
// normalize to null instead of throwing, so a malformed payload can never
// crash the chart.

import type { ChartCandle } from "@/components/charts/mock-intelligence-chart-data";

export type BinanceInterval = "1m" | "5m" | "15m";

export const BINANCE_INTERVALS: BinanceInterval[] = ["1m", "5m", "15m"];
export const BINANCE_CHART_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"];

const REST_BASE = "https://api.binance.com/api/v3/klines";
const WS_BASE = "wss://stream.binance.com:9443/ws";

export function klineStreamUrl(symbol: string, interval: BinanceInterval): string {
  return `${WS_BASE}/${symbol.toLowerCase()}@kline_${interval}`;
}

function toCandle(
  openTimeMs: unknown,
  open: unknown,
  high: unknown,
  low: unknown,
  close: unknown,
  volume: unknown,
): ChartCandle | null {
  const time = Math.floor(Number(openTimeMs) / 1000);
  const o = Number(open);
  const h = Number(high);
  const l = Number(low);
  const c = Number(close);
  const v = Number(volume);
  if (
    !Number.isFinite(time) || time <= 0 ||
    !Number.isFinite(o) || !Number.isFinite(h) ||
    !Number.isFinite(l) || !Number.isFinite(c) || !Number.isFinite(v)
  ) {
    return null;
  }
  return { time, open: o, high: h, low: l, close: c, volume: v };
}

/**
 * Fetch a candle snapshot from the public Binance REST klines endpoint.
 * Throws on HTTP/network errors (the caller decides how to fall back);
 * malformed rows inside an otherwise valid response are skipped.
 */
export async function fetchBinanceKlines(
  symbol: string,
  interval: BinanceInterval,
  limit = 300,
  signal?: AbortSignal,
): Promise<ChartCandle[]> {
  const params = new URLSearchParams({
    symbol: symbol.toUpperCase(),
    interval,
    limit: String(Math.max(1, Math.min(1000, limit))),
  });
  const res = await fetch(`${REST_BASE}?${params.toString()}`, {
    cache: "no-store",
    signal,
  });
  if (!res.ok) throw new Error(`Binance klines HTTP ${res.status}`);
  const rows: unknown = await res.json();
  if (!Array.isArray(rows)) throw new Error("Unexpected klines payload shape");

  const candles: ChartCandle[] = [];
  for (const row of rows) {
    if (!Array.isArray(row) || row.length < 6) continue;
    const candle = toCandle(row[0], row[1], row[2], row[3], row[4], row[5]);
    if (candle) candles.push(candle);
  }
  return candles;
}

/**
 * Parse one kline WebSocket message into a candle. Returns null for
 * anything that isn't a well-formed kline event.
 */
export function parseKlineMessage(raw: unknown): ChartCandle | null {
  if (typeof raw !== "string") return null;
  try {
    const msg: unknown = JSON.parse(raw);
    if (typeof msg !== "object" || msg === null) return null;
    const m = msg as { e?: unknown; k?: Record<string, unknown> };
    if (m.e !== "kline" || typeof m.k !== "object" || m.k === null) return null;
    const k = m.k;
    return toCandle(k.t, k.o, k.h, k.l, k.c, k.v);
  } catch {
    return null;
  }
}
