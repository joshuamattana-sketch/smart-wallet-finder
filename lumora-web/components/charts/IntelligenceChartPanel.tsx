"use client";

// components/charts/IntelligenceChartPanel.tsx
// LM68B/LM68C — Unified Intelligence Chart.
//
// Base candle layer is now LIVE: public Binance REST klines for the initial
// snapshot + the public kline WebSocket for per-tick updates (REST polling
// fallback when the WS can't run). If Binance is unreachable, the chart
// keeps the deterministic mock session and shows a DEMO FALLBACK badge —
// the page never crashes.
//
// Intelligence overlays (heatmap bands, whale markers, pressure, read)
// remain DEMO data in this patch, derived relative to whatever candles are
// displayed so they stay meaningful at any price level. Live overlay wiring
// lands in LM68D.
//
// Layering (unchanged from LM68B):
//   1–2. candles + volume      → lightweight-charts series
//   3.   zones + sweep bands   → overlay <canvas>, synced via priceToCoordinate
//   4.   whale markers         → series.setMarkers()
//   5.   read chip / pressure  → DOM overlays
//   6.   controls              → React header; toggles never rebuild the chart
//
// Per-tick candle updates go straight to series.update() through refs — no
// React re-render per tick. No animation loops, so prefers-reduced-motion
// is trivially respected.

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ColorType,
  CrosshairMode,
  LineStyle,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import {
  IntelligenceDock,
  type DockTone,
} from "@/components/ui/IntelligenceDock";
import {
  CandlestickChart,
  Crosshair,
  Radar,
  Flame,
  Waves,
  Gauge,
  Eye,
  type LucideIcon,
} from "lucide-react";
import { clsx } from "clsx";
import {
  MODE_PRESETS,
  MOCK_CANDLES,
  MOCK_FUTURES,
  MOCK_READ,
  deriveMockOverlays,
  isImportantWhale,
  isKeyZone,
  matchedMode,
  type ChartCandle,
  type OverlayState,
  type ViewMode,
} from "@/components/charts/mock-intelligence-chart-data";
import {
  BINANCE_CHART_SYMBOLS,
  BINANCE_INTERVALS,
  type BinanceInterval,
} from "@/lib/binance-klines";
import { useBinanceKlines } from "@/components/charts/useBinanceKlines";

interface IntelligenceChartPanelProps {
  /** Chart pane height in CSS px (header/footer come on top). */
  height?: number;
  /** Initial view mode preset. */
  defaultMode?: ViewMode;
  className?: string;
}

const MODE_LABELS: Record<ViewMode, string> = {
  clean: "Clean",
  assisted: "Assisted",
  full: "Full Intel",
};

// IntelligenceDock wiring — modes carry the violet selected accent; overlays
// carry their semantic tone (cyan = intelligence, emerald = whale flow,
// amber = pressure/caution, cyan = read).
const MODE_ICONS: Record<ViewMode, LucideIcon> = {
  clean: CandlestickChart,
  assisted: Crosshair,
  full: Radar,
};
const MODE_HINTS: Record<ViewMode, string> = {
  clean: "price only",
  assisted: "key zones + whales",
  full: "every layer",
};

const OVERLAY_KEYS = ["heatmap", "whales", "pressure", "read"] as const;
type OverlayKey = (typeof OVERLAY_KEYS)[number];

const OVERLAY_LABELS: Record<OverlayKey, string> = {
  heatmap: "Heatmap",
  whales: "Whales",
  pressure: "Pressure",
  read: "Read",
};
const OVERLAY_ICONS: Record<OverlayKey, LucideIcon> = {
  heatmap: Flame,
  whales: Waves,
  pressure: Gauge,
  read: Eye,
};
const OVERLAY_TONES: Record<OverlayKey, DockTone> = {
  heatmap: "cyan",
  whales: "emerald",
  pressure: "amber",
  read: "cyan",
};

function toBar(c: ChartCandle) {
  return {
    time: c.time as UTCTimestamp,
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
  };
}

function toVol(c: ChartCandle) {
  return {
    time: c.time as UTCTimestamp,
    value: c.volume,
    color: c.close >= c.open ? "rgba(34,197,94,0.22)" : "rgba(239,68,68,0.22)",
  };
}

function fmtClock(ms: number): string {
  return new Date(ms).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function IntelligenceChartPanel({
  height = 400,
  defaultMode = "assisted",
  className,
}: IntelligenceChartPanelProps) {
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [interval, setInterval] = useState<BinanceInterval>("5m");
  const [mode, setMode] = useState<ViewMode>(defaultMode);
  const [overlays, setOverlays] = useState<OverlayState>(MODE_PRESETS[defaultMode]);
  const [usingMock, setUsingMock] = useState(true);

  const containerRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const anchorRef = useRef<ISeriesApi<"Line"> | null>(null);
  const hatchRef = useRef<CanvasPattern | null>(null);
  const rafRef = useRef(0);
  const usingMockRef = useRef(true);

  // Current candle set + demo overlays derived from it. Mutated through
  // refs so live ticks never re-render the component.
  const candlesRef = useRef<ChartCandle[]>(MOCK_CANDLES);
  const overlayDataRef = useRef(deriveMockOverlays(MOCK_CANDLES));

  // Density: which preset shapes zone/whale filtering. Custom toggle combos
  // keep the density of the last preset the user selected.
  const density: ViewMode = matchedMode(overlays) ?? mode;
  const stateRef = useRef({ overlays, density });
  stateRef.current = { overlays, density };

  // ── Layer 3: overlay canvas draw (zones + sweep bands) ─────────────────────
  const drawOverlay = useCallback(() => {
    const chart = chartRef.current;
    const series = candleRef.current;
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!chart || !series || !canvas || !container) return;

    const paneW = chart.timeScale().width();
    const paneH = container.clientHeight - chart.timeScale().height();
    if (paneW <= 0 || paneH <= 0) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(paneW * dpr);
    canvas.height = Math.round(paneH * dpr);
    canvas.style.width = `${paneW}px`;
    canvas.style.height = `${paneH}px`;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, paneW, paneH);

    const { overlays: ov, density: dens } = stateRef.current;
    if (!ov.heatmap) return;

    const data = overlayDataRef.current;
    const mono = "600 9px 'JetBrains Mono', monospace";
    const zones = dens === "full" ? data.zones : data.zones.filter(isKeyZone);

    for (const z of zones) {
      const yA = series.priceToCoordinate(z.priceMax);
      const yB = series.priceToCoordinate(z.priceMin);
      if (yA == null || yB == null) continue;
      let top = Math.min(yA, yB);
      let bot = Math.max(yA, yB);
      if (bot < 0 || top > paneH) continue;
      top = Math.max(0, top);
      bot = Math.min(paneH, bot);
      const h = Math.max(2, bot - top);

      const rgb = z.side === "ask" ? "239,68,68" : "34,197,94";
      ctx.fillStyle = `rgba(${rgb},${(0.05 + (z.strength / 100) * 0.2).toFixed(3)})`;
      ctx.fillRect(0, top, paneW, h);

      // Edge facing price: bottom of ask bands, top of bid bands.
      const edgeY = Math.round(z.side === "ask" ? bot : top);
      ctx.fillStyle = `rgba(${rgb},0.35)`;
      ctx.fillRect(0, edgeY - 0.5, paneW, 1);

      ctx.font = mono;
      ctx.fillStyle =
        z.side === "ask" ? "rgba(248,113,113,0.85)" : "rgba(74,222,128,0.85)";
      ctx.fillText(z.label, 8, Math.min(Math.max(top + 11, 11), paneH - 4));
    }

    // Sweep risk — Full Intel only.
    if (dens === "full") {
      if (!hatchRef.current) {
        const pc = document.createElement("canvas");
        pc.width = 8;
        pc.height = 8;
        const pctx = pc.getContext("2d");
        if (pctx) {
          pctx.strokeStyle = "rgba(245,158,11,0.3)";
          pctx.lineWidth = 1.5;
          pctx.beginPath();
          pctx.moveTo(0, 8);
          pctx.lineTo(8, 0);
          pctx.stroke();
          hatchRef.current = ctx.createPattern(pc, "repeat");
        }
      }
      for (const s of data.sweeps) {
        const yA = series.priceToCoordinate(s.priceMax);
        const yB = series.priceToCoordinate(s.priceMin);
        if (yA == null || yB == null) continue;
        let top = Math.min(yA, yB);
        let bot = Math.max(yA, yB);
        if (bot < 0 || top > paneH) continue;
        top = Math.max(0, top);
        bot = Math.min(paneH, bot);
        const h = Math.max(3, bot - top);

        if (hatchRef.current) {
          ctx.fillStyle = hatchRef.current;
          ctx.fillRect(0, top, paneW, h);
        }
        ctx.save();
        ctx.strokeStyle = "rgba(245,158,11,0.3)";
        ctx.setLineDash([4, 4]);
        ctx.strokeRect(0.5, top + 0.5, paneW - 1, h - 1);
        ctx.restore();

        ctx.font = mono;
        ctx.fillStyle = "rgba(251,191,36,0.8)";
        ctx.fillText(s.label, 8, Math.min(Math.max(top + 11, 11), paneH - 4));
      }
    }
  }, []);

  const scheduleDraw = useCallback(() => {
    cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(drawOverlay);
  }, [drawOverlay]);

  // ── Layer 4 + autoscale anchor sync — no chart rebuild ─────────────────────
  const syncOverlays = useCallback(() => {
    const candles = candleRef.current;
    const anchor = anchorRef.current;
    if (!candles || !anchor) return;

    const { overlays: ov, density: dens } = stateRef.current;
    const data = overlayDataRef.current;
    const bars = candlesRef.current;

    const whales = ov.whales
      ? dens === "full"
        ? data.whales
        : data.whales.filter(isImportantWhale)
      : [];
    const markers: SeriesMarker<Time>[] = whales.map((w) => ({
      time: w.time as UTCTimestamp,
      position: w.side === "BUY" ? "belowBar" : "aboveBar",
      color: w.side === "BUY" ? "#22c55e" : "#ef4444",
      shape: w.side === "BUY" ? "arrowUp" : "arrowDown",
      text: w.label,
      size: w.risk === "HIGH" ? 2 : 1,
    }));
    candles.setMarkers(markers);

    // Invisible autoscale anchor so visible bands fit in the viewport.
    if (ov.heatmap && bars.length > 0) {
      const zones = dens === "full" ? data.zones : data.zones.filter(isKeyZone);
      const lows = zones.map((z) => z.priceMin);
      const highs = zones.map((z) => z.priceMax);
      if (dens === "full") {
        for (const s of data.sweeps) {
          lows.push(s.priceMin);
          highs.push(s.priceMax);
        }
      }
      if (lows.length > 0) {
        anchor.setData([
          { time: bars[0].time as UTCTimestamp, value: Math.min(...lows) },
          { time: bars[bars.length - 1].time as UTCTimestamp, value: Math.max(...highs) },
        ]);
      } else {
        anchor.setData([]);
      }
    } else {
      anchor.setData([]);
    }

    scheduleDraw();
  }, [scheduleDraw]);

  // ── Candle data application (snapshot + per-tick update) ───────────────────
  const applySnapshot = useCallback(
    (candles: ChartCandle[], mock: boolean) => {
      candlesRef.current = candles;
      overlayDataRef.current = deriveMockOverlays(candles);
      usingMockRef.current = mock;
      setUsingMock(mock);

      const series = candleRef.current;
      const vol = volumeRef.current;
      if (series) series.setData(candles.map(toBar));
      if (vol) vol.setData(candles.map(toVol));
      chartRef.current?.timeScale().fitContent();
      syncOverlays();
    },
    [syncOverlays],
  );

  const applyUpdate = useCallback((c: ChartCandle) => {
    const series = candleRef.current;
    const vol = volumeRef.current;
    if (!series || !vol) return;

    // Guard against out-of-order ticks (e.g. around a symbol switch).
    const bars = candlesRef.current;
    const last = bars[bars.length - 1];
    if (last && c.time < last.time) return;
    if (last && c.time === last.time) bars[bars.length - 1] = c;
    else bars.push(c);

    series.update(toBar(c));
    vol.update(toVol(c));
  }, []);

  // ── Live Binance feed (REST snapshot + WS updates + fallbacks) ─────────────
  const { status, transport, lastUpdateMs } = useBinanceKlines({
    symbol,
    interval,
    onSnapshot: (candles) => applySnapshot(candles, false),
    onUpdate: applyUpdate,
  });

  // Snapshot failed twice → keep the product alive on the mock session.
  useEffect(() => {
    if (status === "error") applySnapshot(MOCK_CANDLES, true);
  }, [status, applySnapshot]);

  // ── Chart creation (once) ───────────────────────────────────────────────────
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const chart = createChart(el, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "#0d0d10" },
        textColor: "#71717a",
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 10,
      },
      grid: {
        vertLines: { color: "#141418" },
        horzLines: { color: "#17171b" },
      },
      rightPriceScale: { borderColor: "#1e1e22" },
      timeScale: {
        borderColor: "#1e1e22",
        timeVisible: true,
        secondsVisible: false,
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: "rgba(34,211,238,0.35)", labelBackgroundColor: "#1e1e22" },
        horzLine: { color: "rgba(34,211,238,0.35)", labelBackgroundColor: "#1e1e22" },
      },
    });

    const candles = chart.addCandlestickSeries({
      upColor: "rgba(34,197,94,0.85)",
      downColor: "rgba(239,68,68,0.85)",
      borderVisible: false,
      wickUpColor: "rgba(34,197,94,0.55)",
      wickDownColor: "rgba(239,68,68,0.55)",
      priceLineColor: "#22d3ee",
      priceLineStyle: LineStyle.Dashed,
      priceLineWidth: 1,
    });

    const volume = chart.addHistogramSeries({
      priceScaleId: "",
      priceFormat: { type: "volume" },
      lastValueVisible: false,
      priceLineVisible: false,
    });
    volume.priceScale().applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } });

    // Invisible autoscale anchor — extends the price range so toggled-on
    // zone/sweep bands fit inside the viewport. Empty data = no effect.
    const anchor = chart.addLineSeries({
      color: "rgba(0,0,0,0)",
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });

    chart.timeScale().subscribeVisibleLogicalRangeChange(scheduleDraw);

    chartRef.current = chart;
    candleRef.current = candles;
    volumeRef.current = volume;
    anchorRef.current = anchor;

    // Seed with whatever the candle ref currently holds (mock until the
    // first Binance snapshot replaces it).
    applySnapshot(candlesRef.current, usingMockRef.current);

    const ro = new ResizeObserver(scheduleDraw);
    ro.observe(el);

    return () => {
      ro.disconnect();
      cancelAnimationFrame(rafRef.current);
      chart.remove();
      chartRef.current = null;
      candleRef.current = null;
      volumeRef.current = null;
      anchorRef.current = null;
    };
  }, [applySnapshot, scheduleDraw]);

  // ── Overlay/mode changes — resync layers only ───────────────────────────────
  useEffect(() => {
    syncOverlays();
  }, [overlays, density, syncOverlays]);

  // ── Controls ────────────────────────────────────────────────────────────────
  const selectMode = (m: ViewMode) => {
    setMode(m);
    setOverlays(MODE_PRESETS[m]);
  };
  const toggleOverlay = (k: (typeof OVERLAY_KEYS)[number]) => {
    setOverlays((prev) => ({ ...prev, [k]: !prev[k] }));
  };
  const activePreset = matchedMode(overlays);

  const fut = MOCK_FUTURES;
  const read = MOCK_READ;

  // Source/status badge: live → stale → connecting → demo fallback.
  const sourceBadge = usingMock
    ? status === "loading"
      ? { variant: "neutral" as const, label: "CONNECTING…", dot: false }
      : { variant: "warning" as const, label: "DEMO FALLBACK", dot: false }
    : status === "live"
      ? { variant: "live" as const, label: "LIVE · BINANCE", dot: true }
      : status === "stale"
        ? { variant: "stale" as const, label: "STALE", dot: false }
        : status === "loading"
          ? { variant: "neutral" as const, label: "CONNECTING…", dot: false }
          : { variant: "warning" as const, label: "DEMO FALLBACK", dot: false };

  return (
    // No overflow-hidden on the panel itself — the dock tooltips float ABOVE
    // the header and must not be clipped. The chart pane clips its own canvas
    // and the footer rounds its own bottom corners instead.
    <Panel level="focus" flush className={className}>
      {/* Layer 6: controls header */}
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-2 border-b border-lm-border px-3 py-2">
        <span className="lm-section-title">Intelligence Chart</span>

        <span aria-hidden className="hidden h-4 w-px bg-lm-border sm:block" />

        {/* Symbol */}
        <select
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          className="num cursor-pointer appearance-none rounded-md border border-lm-border bg-lm-bg px-2 py-1 text-[11px] text-lm-text transition-colors duration-150 hover:border-zinc-600 focus:outline-none focus-visible:outline focus-visible:outline-1 focus-visible:outline-cyan-400/60"
        >
          {BINANCE_CHART_SYMBOLS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>

        {/* Interval */}
        <div className="flex overflow-hidden rounded-md border border-lm-border">
          {BINANCE_INTERVALS.map((iv) => (
            <button
              key={iv}
              onClick={() => setInterval(iv)}
              aria-pressed={interval === iv}
              className={clsx(
                "lm-segment-btn px-2 py-1 text-[11px] font-medium focus-visible:outline focus-visible:outline-1 focus-visible:-outline-offset-1 focus-visible:outline-cyan-400/60",
                interval === iv ? "lm-segment-active" : "bg-lm-surface text-lm-muted",
              )}
            >
              {iv}
            </button>
          ))}
        </div>

        {/* Source / status — quiet emerald halo when actually live */}
        <StatusBadge
          variant={sourceBadge.variant}
          size="sm"
          dot={sourceBadge.dot}
          className={clsx(
            sourceBadge.variant === "live" &&
              "shadow-[0_0_12px_-3px_rgba(52,211,153,0.45)]",
          )}
        >
          {sourceBadge.label}
        </StatusBadge>
        {lastUpdateMs !== null && !usingMock && (
          <span className="num hidden text-[9px] uppercase tracking-wider text-lm-muted sm:inline">
            UPD {fmtClock(lastUpdateMs)}
            {transport === "ws" ? " · WS" : transport === "rest" ? " · REST" : ""}
          </span>
        )}

        {/* IntelligenceDock — mode presets + overlay channels in one glass pill */}
        <IntelligenceDock
          className="ml-auto"
          groups={[
            (["clean", "assisted", "full"] as const).map((m) => ({
              id: m,
              label: MODE_LABELS[m],
              hint: MODE_HINTS[m],
              icon: MODE_ICONS[m],
              active: activePreset === m,
              tone: "violet" as const,
              onSelect: () => selectMode(m),
            })),
            OVERLAY_KEYS.map((k) => ({
              id: k,
              label: OVERLAY_LABELS[k],
              hint: overlays[k] ? "on · demo data" : "off",
              icon: OVERLAY_ICONS[k],
              active: overlays[k],
              tone: OVERLAY_TONES[k],
              onSelect: () => toggleOverlay(k),
            })),
          ]}
        />
      </div>

      {/* Layers 1–4: chart + overlay canvas (pane clips its own content) */}
      <div className="relative overflow-hidden" style={{ height }}>
        <div ref={containerRef} className="absolute inset-0" />
        <canvas
          ref={canvasRef}
          className="pointer-events-none absolute left-0 top-0"
          aria-hidden
        />

        {/* Edge lighting — faint cyan/violet hairlines falling from the top
            corners so the instrument frame reads live, not boxed. */}
        <span
          aria-hidden
          className="pointer-events-none absolute left-0 top-0 z-10 h-28 w-px bg-gradient-to-b from-cyan-400/25 to-transparent"
        />
        <span
          aria-hidden
          className="pointer-events-none absolute right-0 top-0 z-10 h-28 w-px bg-gradient-to-b from-violet-400/20 to-transparent"
        />

        {/* Layer 5: current read chip — demo data until LM68D */}
        {overlays.read && (
          <div
            className={clsx(
              "pointer-events-none absolute right-16 top-2.5 z-10 rounded-md border border-lm-border border-l-2 bg-lm-surface/95 px-2.5 py-1.5 shadow-[0_4px_14px_rgba(0,0,0,0.5)] backdrop-blur-[2px]",
              read.bias === "LONG"
                ? "border-l-emerald-400/60"
                : read.bias === "SHORT"
                  ? "border-l-red-400/60"
                  : "border-l-zinc-500/60",
            )}
          >
            <p className="num flex items-center gap-1.5 text-[9px] uppercase tracking-[0.2em] text-lm-muted">
              <span aria-hidden className="h-1 w-1 rounded-full bg-cyan-400/70" />
              Current read · demo
            </p>
            <div className="mt-0.5 flex items-baseline gap-1.5">
              <span
                className={clsx(
                  "num text-[12px] font-bold leading-none",
                  read.bias === "LONG"
                    ? "text-emerald-400"
                    : read.bias === "SHORT"
                      ? "text-red-400"
                      : "text-lm-text-dim",
                )}
              >
                {read.bias}
              </span>
              <span className="num text-[10px] leading-none text-lm-text">
                {read.score}
                <span className="text-lm-muted">/100</span>
              </span>
              {density === "full" && (
                <>
                  <span className="num text-[9px] leading-none text-lm-muted">
                    CONF {read.confidence}%
                  </span>
                  <span
                    className={clsx(
                      "num text-[9px] font-semibold leading-none",
                      read.risk === "HIGH"
                        ? "text-red-400"
                        : read.risk === "MEDIUM"
                          ? "text-amber-400"
                          : "text-emerald-400",
                    )}
                  >
                    {read.risk} RISK
                  </span>
                </>
              )}
            </div>
          </div>
        )}
        {/* Layer 5: futures pressure strip — absolute bottom overlay inside
            the pane so toggling Pressure NEVER changes the instrument height
            (no layout shift, nothing pushed below the chart). */}
        {overlays.pressure && (
          <div className="pointer-events-none absolute inset-x-0 bottom-0 z-10 flex items-center justify-between gap-3 overflow-hidden border-t border-lm-border/60 bg-[#0d0d10]/85 px-3 py-1.5 backdrop-blur-[2px]">
          <div className="num flex items-center gap-3.5 whitespace-nowrap text-[9px] uppercase tracking-wider text-lm-muted">
            <span>
              FUNDING{" "}
              <span className="text-lm-text">
                {fut.fundingRatePct >= 0 ? "+" : ""}
                {fut.fundingRatePct.toFixed(3)}%
              </span>
            </span>
            <span>
              OI{" "}
              <span className="text-lm-text">
                {fut.oiChangePct >= 0 ? "+" : ""}
                {fut.oiChangePct.toFixed(1)}%
              </span>
            </span>
            <span>
              PRESSURE{" "}
              <span
                className={clsx(
                  fut.pressure === "long"
                    ? "text-emerald-400"
                    : fut.pressure === "short"
                      ? "text-red-400"
                      : "text-lm-text-dim",
                )}
              >
                → {fut.pressure.toUpperCase()}
              </span>
            </span>
            <span>
              LEV HEAT{" "}
              <span
                className={clsx(
                  fut.leverageHeat === "high"
                    ? "text-red-400"
                    : fut.leverageHeat === "medium"
                      ? "text-amber-400"
                      : "text-emerald-400",
                )}
              >
                {fut.leverageHeat.toUpperCase()}
              </span>
            </span>
            {density === "full" && (
              <span className="text-amber-400">POSSIBLE SWEEP BELOW RANGE LOWS</span>
            )}
          </div>
          <span className="num hidden whitespace-nowrap text-[9px] text-lm-muted sm:inline">
            {read.action}
          </span>
          </div>
        )}
      </div>

      {/* Honesty footer — deliberate two-sided status line */}
      <div className="flex items-center justify-between gap-3 rounded-b-lg border-t border-lm-border bg-lm-surface-muted/40 px-3 py-1.5">
        <p className="num text-[9px] uppercase tracking-[0.15em] text-lm-muted">
          Candles · Binance public data · overlays demo until LM68D
        </p>
        <p className="num hidden whitespace-nowrap text-[9px] uppercase tracking-[0.15em] text-lm-muted sm:block">
          Context only · not financial advice
        </p>
      </div>
    </Panel>
  );
}

export default IntelligenceChartPanel;
