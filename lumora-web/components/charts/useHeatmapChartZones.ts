"use client";

// components/charts/useHeatmapChartZones.ts
// LM68F — client hook feeding real liquidity zones into the Intelligence Chart.
//
// Fetches /api/heatmap (server resolves live → fixture → mock) for the charted
// symbol/timeframe on mount, then polls every 6s and refreshes on tab
// visibility. The raw payload is returned un-mapped — symbol/price filtering
// and candle alignment happen in `mapHeatmapZonesToChart`, so a symbol switch
// re-fetches (new symbol) but density changes never do.
//
// `feed` semantics mirror the whale hook:
//   "loading"     → first request still in flight
//   "real"        → API resolved to the live source AND the payload carries
//                   usable bid/ask zones; the chart should render them
//   "unavailable" → fixture/mock payload, no usable zones, or request failed;
//                   the chart should fall back to demo zones

import { useEffect, useState } from "react";
import type { HeatmapApiPayload } from "@/lib/heatmap-types";
import { heatmapResolvedStatus } from "@/lib/heatmap-types";
import { hasRealHeatmapZones } from "@/lib/chart-heatmap-zones";

export type HeatmapFeedStatus = "loading" | "real" | "unavailable";

export interface UseHeatmapChartZonesResult {
  payload: HeatmapApiPayload | null;
  feed: HeatmapFeedStatus;
}

const POLL_MS = 6_000;

/** Chart interval → /api/heatmap timeframe (the heatmap has no 1m bucket). */
function toHeatmapTimeframe(interval: string): string {
  return interval === "1m" ? "5m" : interval;
}

export function useHeatmapChartZones(
  symbol: string,
  interval: string,
): UseHeatmapChartZonesResult {
  const [payload, setPayload] = useState<HeatmapApiPayload | null>(null);
  const [feed, setFeed] = useState<HeatmapFeedStatus>("loading");

  const timeframe = toHeatmapTimeframe(interval);

  useEffect(() => {
    const controller = new AbortController();

    const fetchZones = async () => {
      try {
        const res = await fetch(
          `/api/heatmap?source=live&symbol=${symbol}&exchange=binance_spot&timeframe=${timeframe}&_ts=${Date.now()}`,
          { cache: "no-store", signal: controller.signal },
        );
        if (controller.signal.aborted) return;
        if (!res.ok) {
          setFeed("unavailable");
          return;
        }
        const data: HeatmapApiPayload = await res.json();
        if (controller.signal.aborted) return;

        setPayload(data);
        // Real only when the route served the live pipeline AND we actually
        // have usable zones — otherwise the chart keeps its demo bands.
        const live = heatmapResolvedStatus(data).variant === "green";
        setFeed(live && hasRealHeatmapZones(data) ? "real" : "unavailable");
      } catch {
        if (!controller.signal.aborted) setFeed("unavailable");
      }
    };

    // Reset to loading on symbol/timeframe change so stale zones don't linger.
    setFeed("loading");
    fetchZones();
    const id = window.setInterval(fetchZones, POLL_MS);
    const onVisible = () => {
      if (document.visibilityState === "visible") fetchZones();
    };
    document.addEventListener("visibilitychange", onVisible);

    return () => {
      controller.abort();
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [symbol, timeframe]);

  return { payload, feed };
}
