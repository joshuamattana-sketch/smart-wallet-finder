"use client";

// components/liquidity/HeatmapCanvas.tsx
// Canvas Renderer v1 for the Lumora Liquidity Map.
// Renders a /api/heatmap payload onto an HTML 2D canvas. No external libraries,
// no new dependencies. Designed as a stable technical foundation — not a final
// visual design.

import { useEffect, useRef, useState, useCallback } from "react";
import type { HeatmapApiPayload } from "@/lib/heatmap-types";
import { intensityToColor, wallColor } from "@/lib/heatmap-colors";

interface HeatmapCanvasProps {
  payload: HeatmapApiPayload;
  /** CSS pixel height of the chart area (default 560). */
  height?: number;
  /** Optional current price — draws a horizontal marker line when in range. */
  currentPrice?: number;
  /** Show a small debug overlay (cell count, dimensions, render time). */
  showDebug?: boolean;
}

// Plot margins (CSS px) — room for axis labels.
const PAD_LEFT = 56;
const PAD_RIGHT = 12;
const PAD_TOP = 10;
const PAD_BOTTOM = 26;

interface DebugInfo {
  w: number;
  h: number;
  cells: number;
  drawn: number;
  ms: number;
}

export function HeatmapCanvas({
  payload,
  height = 560,
  currentPrice,
  showDebug = false,
}: HeatmapCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [width, setWidth] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [debug, setDebug] = useState<DebugInfo | null>(null);

  // ── Responsive width via ResizeObserver (with window-resize fallback) ────────
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const measure = () => {
      const w = el.clientWidth;
      if (w > 0) setWidth(w);
    };

    measure();

    let ro: ResizeObserver | null = null;
    if (typeof ResizeObserver !== "undefined") {
      ro = new ResizeObserver(() => measure());
      ro.observe(el);
    } else if (typeof window !== "undefined") {
      window.addEventListener("resize", measure);
    }

    return () => {
      if (ro) ro.disconnect();
      else if (typeof window !== "undefined") {
        window.removeEventListener("resize", measure);
      }
    };
  }, []);

  // ── Draw ─────────────────────────────────────────────────────────────────────
  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || width <= 0) return;

    try {
      const t0 =
        typeof performance !== "undefined" ? performance.now() : Date.now();

      const ctx = canvas.getContext("2d");
      if (!ctx) {
        setError("Canvas 2D context unavailable");
        return;
      }

      const dpr =
        typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1;

      // Size the backing store for crisp rendering on HiDPI displays.
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      const plotW = Math.max(0, width - PAD_LEFT - PAD_RIGHT);
      const plotH = Math.max(0, height - PAD_TOP - PAD_BOTTOM);

      // ── Layer 1: dark chart background ──────────────────────────────────────
      ctx.clearRect(0, 0, width, height);
      ctx.fillStyle = "#05030f";
      ctx.fillRect(0, 0, width, height);
      ctx.fillStyle = "#070512";
      ctx.fillRect(PAD_LEFT, PAD_TOP, plotW, plotH);

      // ── Derive price axis from priceMin/priceMax/priceStep ──────────────────
      const priceMin = payload.priceMin;
      const priceMax = payload.priceMax;
      const step = payload.priceStep || 1;
      const buckets = payload.timeBuckets?.length ?? 0;

      const haveRange =
        priceMin !== null &&
        priceMax !== null &&
        priceMax > priceMin &&
        buckets > 0;

      if (!haveRange) {
        // Nothing renderable — leave the empty dark frame and a hint.
        ctx.fillStyle = "rgba(255,255,255,0.4)";
        ctx.font = "12px sans-serif";
        ctx.textAlign = "center";
        ctx.fillText(
          "No price range in payload",
          PAD_LEFT + plotW / 2,
          PAD_TOP + plotH / 2,
        );
        setDebug(
          showDebug
            ? { w: width, h: height, cells: payload.cells.length, drawn: 0, ms: 0 }
            : null,
        );
        setError(null);
        return;
      }

      const payloadMin = priceMin as number;
      const payloadMax = priceMax as number;

      // p index → price (always relative to the full payload axis).
      const indexToPrice = (p: number) => payloadMin + p * step;

      // ── Pick the rendered y-axis bounds ─────────────────────────────────────
      // LM43: when the writer stamps an analysis-grade requested range
      // (meta.priceRangeMin/Max), honor it so the user sees the full wider
      // context — even where Binance depth doesn't reach. Otherwise fall back
      // to auto-tightening around where the densest liquidity sits.
      const rangeMin = payload.meta?.priceRangeMin;
      const rangeMax = payload.meta?.priceRangeMax;
      let pMin = payloadMin;
      let pMax = payloadMax;
      if (
        typeof rangeMin === "number" &&
        typeof rangeMax === "number" &&
        rangeMax > rangeMin
      ) {
        pMin = rangeMin;
        pMax = rangeMax;
      } else {
        let dataLo = Infinity;
        let dataHi = -Infinity;
        for (const cell of payload.cells) {
          if (cell.total < 6) continue;
          const price = indexToPrice(cell.p);
          if (price < dataLo) dataLo = price;
          if (price > dataHi) dataHi = price;
        }
        for (const wall of payload.walls) {
          if (wall.price_bucket < dataLo) dataLo = wall.price_bucket;
          if (wall.price_bucket > dataHi) dataHi = wall.price_bucket;
        }
        if (dataHi > dataLo) {
          const pad = Math.max(step * 2, (dataHi - dataLo) * 0.08);
          pMin = Math.max(payloadMin, dataLo - pad);
          pMax = Math.min(payloadMax, dataHi + pad);
          if (typeof currentPrice === "number" &&
              currentPrice >= payloadMin && currentPrice <= payloadMax) {
            pMin = Math.min(pMin, currentPrice - pad);
            pMax = Math.max(pMax, currentPrice + pad);
          }
        }
      }
      if (!(pMax > pMin)) { pMin = payloadMin; pMax = payloadMax; }

      const priceRange = pMax - pMin;
      const levelCount = Math.max(1, Math.round(priceRange / step) + 1);

      // price → y (higher price near the top)
      const priceToY = (price: number) =>
        PAD_TOP + ((pMax - price) / priceRange) * plotH;

      // ── Layer 2: subtle grid lines ──────────────────────────────────────────
      ctx.lineWidth = 1;
      ctx.strokeStyle = "rgba(255,255,255,0.03)";
      const hLines = 8;
      ctx.beginPath();
      for (let i = 0; i <= hLines; i++) {
        const y = Math.round(PAD_TOP + (plotH / hLines) * i) + 0.5;
        ctx.moveTo(PAD_LEFT, y);
        ctx.lineTo(PAD_LEFT + plotW, y);
      }
      const vLines = Math.min(buckets, 12);
      for (let i = 0; i <= vLines; i++) {
        const x = Math.round(PAD_LEFT + (plotW / vLines) * i) + 0.5;
        ctx.moveTo(x, PAD_TOP);
        ctx.lineTo(x, PAD_TOP + plotH);
      }
      ctx.stroke();

      // ── Layer 3: heatmap cells via a smoothed offscreen buffer ──────────────
      // Paint cells onto a tiny buckets × levelCount canvas (one texel per
      // cell), then scale it up with bilinear smoothing. This removes hard
      // vertical blocks / gaps when there are only a few time buckets and gives
      // the map a softer, more depth-like look — no external library needed.
      let drawn = 0;
      const rowForPrice = (price: number) => {
        const row = Math.round((pMax - price) / step);
        return Math.max(0, Math.min(levelCount - 1, row));
      };

      const off = document.createElement("canvas");
      off.width = buckets;
      off.height = levelCount;
      const octx = off.getContext("2d");
      if (octx) {
        for (const cell of payload.cells) {
          if (cell.t < 0 || cell.t >= buckets) continue;
          const price = indexToPrice(cell.p);
          if (price < pMin || price > pMax) continue;

          const side =
            cell.bid > 0 && cell.ask > 0
              ? "mixed"
              : cell.ask > 0
                ? "ask"
                : "bid";

          const color = intensityToColor(cell.total, side);
          if (color.endsWith(",0)")) continue; // fully transparent — skip

          octx.fillStyle = color;
          octx.fillRect(cell.t, rowForPrice(price), 1, 1);
          drawn++;
        }

        const prevSmoothing = ctx.imageSmoothingEnabled;
        ctx.imageSmoothingEnabled = true;
        ctx.imageSmoothingQuality = "high";
        ctx.drawImage(off, 0, 0, buckets, levelCount, PAD_LEFT, PAD_TOP, plotW, plotH);
        ctx.imageSmoothingEnabled = prevSmoothing;
      }

      // ── Layer 4: wall highlights — accents, not dominant bars ───────────────
      for (const wall of payload.walls) {
        if (wall.price_bucket < pMin || wall.price_bucket > pMax) continue;
        const y = Math.round(priceToY(wall.price_bucket)) + 0.5;
        const critical = (wall.intensity ?? 0) >= 88;
        const col = wallColor(wall.side);

        ctx.save();
        ctx.strokeStyle = col;
        ctx.lineWidth = critical ? 1.25 : 1;
        // Major walls glow gently; ordinary walls stay flat and quiet.
        if (critical) {
          ctx.shadowColor = col;
          ctx.shadowBlur = 6;
        }
        ctx.beginPath();
        ctx.moveTo(PAD_LEFT, y);
        ctx.lineTo(PAD_LEFT + plotW, y);
        ctx.stroke();
        ctx.restore();

        // Tiny marker dot at the right edge.
        ctx.fillStyle = col;
        ctx.fillRect(PAD_LEFT + plotW - 3, y - 2, 3, 4);
      }

      // ── Layer 4.5: live price path overlay (over the heatmap + walls) ───────
      // Drawn only when payload.pricePath is present; missing/empty → no line,
      // no crash.
      const pricePath = payload.pricePath;
      if (Array.isArray(pricePath) && pricePath.length > 0) {
        const colW = plotW / buckets;
        const timeIndex = new Map<string, number>();
        payload.timeBuckets.forEach((t, i) => timeIndex.set(t, i));

        const pts: Array<{ x: number; y: number; price: number }> = [];
        for (let i = 0; i < pricePath.length; i++) {
          const pp = pricePath[i];
          if (!pp || typeof pp.price !== "number" || !Number.isFinite(pp.price)) continue;
          const idx = timeIndex.has(pp.t) ? (timeIndex.get(pp.t) as number) : i;
          const x = PAD_LEFT + (idx + 0.5) * colW;
          const yRaw = priceToY(pp.price);
          const y = Math.max(PAD_TOP, Math.min(PAD_TOP + plotH, yRaw));
          pts.push({ x, y, price: pp.price });
        }

        if (pts.length > 0) {
          // Bright line with a soft glow so it stays visible over hot cells.
          ctx.save();
          ctx.beginPath();
          pts.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)));
          ctx.strokeStyle = "rgba(255,255,255,0.92)";
          ctx.lineWidth = 2;
          ctx.lineJoin = "round";
          ctx.lineCap = "round";
          ctx.shadowColor = "rgba(255,255,255,0.45)";
          ctx.shadowBlur = 4;
          ctx.stroke();
          ctx.restore();

          // Per-sample dots — only when sparse enough to stay readable.
          if (pts.length <= 80) {
            ctx.fillStyle = "rgba(255,255,255,0.8)";
            for (const p of pts) {
              ctx.beginPath();
              ctx.arc(p.x, p.y, 1.4, 0, Math.PI * 2);
              ctx.fill();
            }
          }

          // Current price: marker dot + dezent label at the latest point.
          const last = pts[pts.length - 1];
          ctx.fillStyle = "#ffffff";
          ctx.beginPath();
          ctx.arc(last.x, last.y, 2.6, 0, Math.PI * 2);
          ctx.fill();

          ctx.fillStyle = "rgba(255,255,255,0.95)";
          ctx.font = "bold 10px sans-serif";
          ctx.textAlign = "right";
          ctx.fillText(
            last.price.toLocaleString(undefined, { maximumFractionDigits: 1 }),
            PAD_LEFT + plotW - 6,
            Math.max(PAD_TOP + 9, last.y - 5),
          );
        }
      }

      // ── Layer 5: current price line (if in range) ───────────────────────────
      if (
        typeof currentPrice === "number" &&
        currentPrice >= pMin &&
        currentPrice <= pMax
      ) {
        const y = Math.round(priceToY(currentPrice)) + 0.5;
        ctx.strokeStyle = "rgba(34,211,238,0.85)";
        ctx.lineWidth = 1.5;
        ctx.setLineDash([4, 3]);
        ctx.beginPath();
        ctx.moveTo(PAD_LEFT, y);
        ctx.lineTo(PAD_LEFT + plotW, y);
        ctx.stroke();
        ctx.setLineDash([]);

        ctx.fillStyle = "rgba(34,211,238,0.95)";
        ctx.font = "bold 10px sans-serif";
        ctx.textAlign = "right";
        ctx.fillText(
          currentPrice.toLocaleString(),
          PAD_LEFT + plotW - 6,
          y - 4,
        );
      }

      // ── Layer 6: axes labels ────────────────────────────────────────────────
      // Price axis (left)
      ctx.fillStyle = "rgba(255,255,255,0.45)";
      ctx.font = "10px sans-serif";
      ctx.textAlign = "right";
      const priceTicks = 6;
      for (let i = 0; i <= priceTicks; i++) {
        const price = pMin + (priceRange / priceTicks) * i;
        const y = priceToY(price);
        ctx.fillText(
          (price / 1000).toFixed(1) + "k",
          PAD_LEFT - 6,
          y + 3,
        );
      }

      // Time axis (bottom)
      ctx.textAlign = "center";
      const colW = plotW / buckets;
      const labelEvery = Math.max(1, Math.ceil(buckets / 6));
      for (let i = 0; i < buckets; i += labelEvery) {
        const iso = payload.timeBuckets[i];
        const d = new Date(iso);
        const label = Number.isNaN(d.getTime())
          ? String(i)
          : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
        const x = PAD_LEFT + i * colW + colW / 2;
        ctx.fillText(label, x, PAD_TOP + plotH + 14);
      }

      const t1 =
        typeof performance !== "undefined" ? performance.now() : Date.now();
      setDebug(
        showDebug
          ? {
              w: width,
              h: height,
              cells: payload.cells.length,
              drawn,
              ms: Math.round((t1 - t0) * 10) / 10,
            }
          : null,
      );
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Canvas render failed");
    }
  }, [payload, width, height, currentPrice, showDebug]);

  useEffect(() => {
    draw();
  }, [draw]);

  return (
    <div ref={containerRef} className="relative w-full" style={{ height }}>
      <canvas ref={canvasRef} className="block w-full" style={{ height }} />

      {error && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/30 text-red-300 text-xs">
            Canvas error: {error}
          </div>
        </div>
      )}

      {showDebug && debug && !error && (
        <div className="absolute top-1 right-1 px-1.5 py-0.5 rounded bg-black/40 text-[8px] leading-none text-white/35 font-mono pointer-events-none">
          {debug.drawn}/{debug.cells} · {debug.ms}ms
        </div>
      )}
    </div>
  );
}

export default HeatmapCanvas;
