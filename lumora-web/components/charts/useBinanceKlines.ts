"use client";

// components/charts/useBinanceKlines.ts
// LM68C — client hook feeding live Binance candles into the chart.
//
// Flow per (symbol, interval):
//   1. REST snapshot (one retry)        → onSnapshot(candles)
//   2. kline WebSocket stream           → onUpdate(candle) per tick
//   3. WS unavailable/closed            → degrade to REST polling every 8s
//   4. no tick for 30s                  → status "stale"
//   5. snapshot failed twice            → status "error" (caller falls back
//                                         to mock candles)
//
// Candle data is delivered through callbacks (held in refs), NOT React
// state — the chart applies series.update() directly, so per-tick updates
// never re-render the page. Only coarse status/transport changes and a
// throttled (2s) last-update timestamp touch state.

import { useEffect, useRef, useState } from "react";
import {
  fetchBinanceKlines,
  klineStreamUrl,
  parseKlineMessage,
  type BinanceInterval,
} from "@/lib/binance-klines";
import type { ChartCandle } from "@/components/charts/mock-intelligence-chart-data";

export type KlineStatus = "loading" | "live" | "stale" | "error";
export type KlineTransport = "ws" | "rest" | null;

interface UseBinanceKlinesOptions {
  symbol: string;
  interval: BinanceInterval;
  /** REST snapshot size (clamped to Binance's 1000 max). Default 300. */
  limit?: number;
  /** Full candle array on (re)load. */
  onSnapshot: (candles: ChartCandle[]) => void;
  /** Single updated/new candle per live tick. */
  onUpdate: (candle: ChartCandle) => void;
}

export interface UseBinanceKlinesResult {
  status: KlineStatus;
  transport: KlineTransport;
  /** Throttled (≥2s apart) timestamp of the most recent data event. */
  lastUpdateMs: number | null;
}

const POLL_MS = 8_000;
const STALE_MS = 30_000;
const WATCHDOG_MS = 10_000;
const RETRY_MS = 2_500;
const LAST_UPDATE_THROTTLE_MS = 2_000;

export function useBinanceKlines({
  symbol,
  interval,
  limit = 300,
  onSnapshot,
  onUpdate,
}: UseBinanceKlinesOptions): UseBinanceKlinesResult {
  const [status, setStatus] = useState<KlineStatus>("loading");
  const [transport, setTransport] = useState<KlineTransport>(null);
  const [lastUpdateMs, setLastUpdateMs] = useState<number | null>(null);

  // Callbacks live in refs so changing identities never restarts the feed.
  const onSnapshotRef = useRef(onSnapshot);
  onSnapshotRef.current = onSnapshot;
  const onUpdateRef = useRef(onUpdate);
  onUpdateRef.current = onUpdate;

  useEffect(() => {
    let cancelled = false;
    let ws: WebSocket | null = null;
    let pollId: number | null = null;
    let watchdogId: number | null = null;
    let retryId: number | null = null;
    let lastTick = 0;
    let lastShown = 0;

    setStatus("loading");
    setTransport(null);

    const markUpdate = () => {
      lastTick = Date.now();
      if (lastTick - lastShown >= LAST_UPDATE_THROTTLE_MS) {
        lastShown = lastTick;
        setLastUpdateMs(lastTick);
      }
    };

    const loadSnapshot = async (): Promise<boolean> => {
      try {
        const candles = await fetchBinanceKlines(symbol, interval, limit);
        if (cancelled) return true;
        if (candles.length === 0) return false;
        onSnapshotRef.current(candles);
        markUpdate();
        setStatus("live");
        return true;
      } catch {
        return false;
      }
    };

    // REST polling fallback when the WS can't run (blocked, closed, errored).
    const startPolling = () => {
      if (cancelled || pollId !== null) return;
      setTransport("rest");
      pollId = window.setInterval(async () => {
        try {
          const tail = await fetchBinanceKlines(symbol, interval, 2);
          if (cancelled) return;
          for (const c of tail) onUpdateRef.current(c);
          markUpdate();
          setStatus("live");
        } catch {
          if (!cancelled) setStatus("stale");
        }
      }, POLL_MS);
    };

    const startWs = () => {
      if (cancelled || typeof WebSocket === "undefined") {
        startPolling();
        return;
      }
      try {
        ws = new WebSocket(klineStreamUrl(symbol, interval));
      } catch {
        startPolling();
        return;
      }
      ws.onopen = () => {
        if (!cancelled) setTransport("ws");
      };
      ws.onmessage = (ev: MessageEvent) => {
        if (cancelled) return;
        const candle = parseKlineMessage(ev.data);
        if (!candle) return;
        onUpdateRef.current(candle);
        markUpdate();
        setStatus("live");
      };
      const degrade = () => {
        if (cancelled) return;
        ws = null;
        startPolling();
      };
      ws.onerror = degrade;
      ws.onclose = degrade;
    };

    void (async () => {
      let ok = await loadSnapshot();
      if (!ok && !cancelled) {
        await new Promise<void>((resolve) => {
          retryId = window.setTimeout(resolve, RETRY_MS);
        });
        if (!cancelled) ok = await loadSnapshot();
      }
      if (cancelled) return;
      if (!ok) {
        setStatus("error");
        return;
      }
      startWs();
      watchdogId = window.setInterval(() => {
        if (!cancelled && lastTick > 0 && Date.now() - lastTick > STALE_MS) {
          setStatus("stale");
        }
      }, WATCHDOG_MS);
    })();

    return () => {
      cancelled = true;
      if (ws) {
        ws.onerror = null;
        ws.onclose = null;
        ws.onmessage = null;
        ws.close();
      }
      if (pollId !== null) clearInterval(pollId);
      if (watchdogId !== null) clearInterval(watchdogId);
      if (retryId !== null) clearTimeout(retryId);
    };
  }, [symbol, interval, limit]);

  return { status, transport, lastUpdateMs };
}
