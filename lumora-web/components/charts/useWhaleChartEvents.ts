"use client";

// components/charts/useWhaleChartEvents.ts
// LM68D — client hook feeding real whale events into the Intelligence Chart.
//
// Fetches /api/whale-alerts (server resolves Supabase → JSONL journal →
// mock) on mount, then polls every 30s and refreshes on tab-visibility.
// Events are kept un-filtered here — symbol filtering and candle snapping
// happen in `mapWhaleEventsToChartMarkers` so a symbol switch never refetches.
//
// `feed` semantics:
//   "loading"     → first request still in flight
//   "real"        → API answered from a real source (supabase/journal);
//                   events may still be empty for the charted symbol/range
//   "unavailable" → API answered mock-only or the request failed —
//                   the chart should fall back to demo whale markers

import { useEffect, useState } from "react";
import {
  parseWhaleAlertRows,
  type RawChartWhaleEvent,
} from "@/lib/chart-whale-events";

export type WhaleFeedStatus = "loading" | "real" | "unavailable";

export interface UseWhaleChartEventsResult {
  events: RawChartWhaleEvent[];
  feed: WhaleFeedStatus;
}

const DEFAULT_LIMIT = 120;
const POLL_MS = 30_000;

export function useWhaleChartEvents(
  limit = DEFAULT_LIMIT,
): UseWhaleChartEventsResult {
  const [events, setEvents] = useState<RawChartWhaleEvent[]>([]);
  const [feed, setFeed] = useState<WhaleFeedStatus>("loading");

  useEffect(() => {
    const controller = new AbortController();

    const fetchEvents = async () => {
      try {
        const res = await fetch(`/api/whale-alerts?limit=${limit}`, {
          cache: "no-store",
          signal: controller.signal,
        });
        if (controller.signal.aborted) return;
        if (!res.ok) {
          setFeed("unavailable");
          return;
        }
        const body: unknown = await res.json();
        if (controller.signal.aborted) return;

        const payload = (body ?? {}) as {
          data_source?: string;
          alerts?: unknown;
        };
        const real =
          payload.data_source === "supabase" ||
          payload.data_source === "journal";
        if (!real) {
          setEvents([]);
          setFeed("unavailable");
          return;
        }
        setEvents(parseWhaleAlertRows(payload.alerts));
        setFeed("real");
      } catch {
        if (!controller.signal.aborted) setFeed("unavailable");
      }
    };

    fetchEvents();
    const id = window.setInterval(fetchEvents, POLL_MS);
    const onVisible = () => {
      if (document.visibilityState === "visible") fetchEvents();
    };
    document.addEventListener("visibilitychange", onVisible);

    return () => {
      controller.abort();
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [limit]);

  return { events, feed };
}
