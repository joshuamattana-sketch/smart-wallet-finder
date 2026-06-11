"use client";

// components/charts/IntelligenceChartPanel.tsx
// LM68B — Unified Intelligence Chart (mock panel).
//
// A lightweight-charts candlestick base with optional Lumora intelligence
// overlays, evolving The Lumora Field hero into real product UI: candles
// instead of the hero price path, optional heatmap signal bands instead of
// staged ask/bid walls, whale markers, futures pressure context and the
// current read — all togglable through three view modes.
//
// Layering:
//   1–2. candles + volume      → lightweight-charts series
//   3.   zones + sweep bands   → absolutely-positioned overlay <canvas>,
//        redrawn on pan/zoom via series.priceToCoordinate (pointer-events:
//        none, so the chart stays fully interactive)
//   4.   whale markers         → series.setMarkers()
//   5.   read chip / pressure  → DOM overlays
//   6.   controls              → React header; toggles never rebuild the chart
//
// Mock only: no API calls, no live data. Calm by design — no animation loops,
// so prefers-reduced-motion is trivially respected.

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
import { clsx } from "clsx";
import {
  MODE_PRESETS,
  MOCK_SCENE,
  isImportantWhale,
  isKeyZone,
  matchedMode,
  type OverlayState,
  type ViewMode,
} from "@/components/charts/mock-intelligence-chart-data";

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

const OVERLAY_KEYS = ["heatmap", "whales", "pressure", "read"] as const;

export function IntelligenceChartPanel({
  height = 400,
  defaultMode = "assisted",
  className,
}: IntelligenceChartPanelProps) {
  const scene = MOCK_SCENE;

  const [mode, setMode] = useState<ViewMode>(defaultMode);
  const [overlays, setOverlays] = useState<OverlayState>(MODE_PRESETS[defaultMode]);

  const containerRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const anchorRef = useRef<ISeriesApi<"Line"> | null>(null);
  const hatchRef = useRef<CanvasPattern | null>(null);
  const rafRef = useRef(0);

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

    const mono = "600 9px 'JetBrains Mono', monospace";
    const zones = dens === "full" ? scene.zones : scene.zones.filter(isKeyZone);

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
      for (const s of scene.sweeps) {
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
  }, [scene]);

  const scheduleDraw = useCallback(() => {
    cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(drawOverlay);
  }, [drawOverlay]);

  // ── Chart creation (once per height change) ─────────────────────────────────
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
    candles.setData(
      scene.candles.map((c) => ({
        time: c.time as UTCTimestamp,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      })),
    );

    const volume = chart.addHistogramSeries({
      priceScaleId: "",
      priceFormat: { type: "volume" },
      lastValueVisible: false,
      priceLineVisible: false,
    });
    volume.priceScale().applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } });
    volume.setData(
      scene.candles.map((c) => ({
        time: c.time as UTCTimestamp,
        value: c.volume,
        color:
          c.close >= c.open ? "rgba(34,197,94,0.22)" : "rgba(239,68,68,0.22)",
      })),
    );

    // Invisible autoscale anchor — extends the price range so toggled-on
    // zone/sweep bands fit inside the viewport. Empty data = no effect.
    const anchor = chart.addLineSeries({
      color: "rgba(0,0,0,0)",
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });

    chart.timeScale().fitContent();
    chart.timeScale().subscribeVisibleLogicalRangeChange(scheduleDraw);

    chartRef.current = chart;
    candleRef.current = candles;
    anchorRef.current = anchor;

    const ro = new ResizeObserver(scheduleDraw);
    ro.observe(el);

    return () => {
      ro.disconnect();
      cancelAnimationFrame(rafRef.current);
      chart.remove();
      chartRef.current = null;
      candleRef.current = null;
      anchorRef.current = null;
    };
  }, [scene, scheduleDraw]);

  // ── Overlay sync: markers, autoscale anchor, canvas — no chart rebuild ─────
  useEffect(() => {
    const candles = candleRef.current;
    const anchor = anchorRef.current;
    if (!candles || !anchor) return;

    // Layer 4: whale markers.
    const whales = overlays.whales
      ? density === "full"
        ? scene.whales
        : scene.whales.filter(isImportantWhale)
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

    // Autoscale anchor so visible bands fit in the viewport.
    if (overlays.heatmap) {
      const zones = density === "full" ? scene.zones : scene.zones.filter(isKeyZone);
      const lows = zones.map((z) => z.priceMin);
      const highs = zones.map((z) => z.priceMax);
      if (density === "full") {
        for (const s of scene.sweeps) {
          lows.push(s.priceMin);
          highs.push(s.priceMax);
        }
      }
      const first = scene.candles[0].time as UTCTimestamp;
      const last = scene.candles[scene.candles.length - 1].time as UTCTimestamp;
      anchor.setData([
        { time: first, value: Math.min(...lows) - 30 },
        { time: last, value: Math.max(...highs) + 30 },
      ]);
    } else {
      anchor.setData([]);
    }

    scheduleDraw();
  }, [overlays, density, scene, scheduleDraw]);

  // ── Controls ────────────────────────────────────────────────────────────────
  const selectMode = (m: ViewMode) => {
    setMode(m);
    setOverlays(MODE_PRESETS[m]);
  };
  const toggleOverlay = (k: (typeof OVERLAY_KEYS)[number]) => {
    setOverlays((prev) => ({ ...prev, [k]: !prev[k] }));
  };
  const activePreset = matchedMode(overlays);

  const fut = scene.futures;
  const read = scene.read;

  return (
    <Panel flush className={clsx("overflow-hidden", className)}>
      {/* Layer 6: controls header */}
      <div className="flex flex-wrap items-center gap-2 border-b border-lm-border px-3 py-2">
        <span className="lm-section-title">Intelligence Chart</span>
        <span className="num text-[10px] font-semibold uppercase tracking-widest text-lm-text">
          {scene.symbol}
        </span>
        <span className="num text-[9px] uppercase tracking-wider text-lm-muted">
          {scene.timeframe}
        </span>
        <StatusBadge variant="warning" size="sm">DEMO</StatusBadge>

        <div className="ml-auto flex flex-wrap items-center gap-2">
          {/* View mode presets */}
          <div className="flex overflow-hidden rounded-md border border-lm-border">
            {(["clean", "assisted", "full"] as const).map((m) => (
              <button
                key={m}
                onClick={() => selectMode(m)}
                className={clsx(
                  "lm-segment-btn px-2.5 py-1 text-[11px] font-medium",
                  activePreset === m
                    ? "lm-segment-active"
                    : "bg-lm-surface text-lm-muted",
                )}
              >
                {MODE_LABELS[m]}
              </button>
            ))}
          </div>
          {/* Individual overlay toggles */}
          <div className="flex items-center gap-1.5">
            {OVERLAY_KEYS.map((k) => (
              <button
                key={k}
                onClick={() => toggleOverlay(k)}
                title={`Toggle ${k} overlay`}
                className={clsx(
                  "lm-segment-btn rounded-md border px-2 py-1 text-[10px] font-medium capitalize",
                  overlays[k]
                    ? "lm-toggle-active"
                    : "border-lm-border bg-lm-surface text-lm-muted",
                )}
              >
                {k}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Layers 1–4: chart + overlay canvas */}
      <div className="relative" style={{ height }}>
        <div ref={containerRef} className="absolute inset-0" />
        <canvas
          ref={canvasRef}
          className="pointer-events-none absolute left-0 top-0"
          aria-hidden
        />

        {/* Layer 5: current read chip — same language as the app's Current Read */}
        {overlays.read && (
          <div className="pointer-events-none absolute right-16 top-2.5 z-10 rounded-md border border-lm-border bg-lm-surface/95 px-2.5 py-1.5">
            <p className="num text-[7.5px] uppercase tracking-[0.2em] text-lm-muted">
              Current read
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
      </div>

      {/* Layer 5: futures pressure strip */}
      {overlays.pressure && (
        <div className="lm-no-scrollbar flex items-center justify-between gap-3 overflow-x-auto border-t border-lm-border bg-lm-surface-muted/80 px-3 py-1.5">
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
            {density === "full" && scene.sweeps.length > 0 && (
              <span className="text-amber-400">POSSIBLE SWEEP BELOW 66.9K</span>
            )}
          </div>
          <span className="num hidden whitespace-nowrap text-[9px] text-lm-muted sm:inline">
            {read.action}
          </span>
        </div>
      )}

      {/* Honesty footer */}
      <div className="border-t border-lm-border px-3 py-1.5">
        <p className="num text-[8.5px] uppercase tracking-[0.15em] text-lm-muted">
          Mock preview · demo data, not live · informational context only — not
          financial advice
        </p>
      </div>
    </Panel>
  );
}

export default IntelligenceChartPanel;
