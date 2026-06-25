"use client";

// components/liquidity/HeatmapCanvas.tsx
// Canvas Renderer v1 for the Lumora Liquidity Map.
// Renders a /api/heatmap payload onto an HTML 2D canvas. No external libraries,
// no new dependencies. Designed as a stable technical foundation — not a final
// visual design.

import { useEffect, useRef, useState, useCallback } from "react";
import type { HeatmapApiPayload, HeatmapCell } from "@/lib/heatmap-types";
import { intensityToColor, wallColor, profileColor } from "@/lib/heatmap-colors";

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

// Right-hand liquidity profile rail (Alphractal-style): a horizontal histogram
// of total liquidity per price level, aggregated across the visible time
// window. Bids (support) read green, asks (resistance) read red. Shares the
// heatmap's exact price axis so bars line up with the hot zones to their left.
const RAIL_W = 74;   // CSS px width of the profile gutter
const RAIL_GAP = 8;  // gap between heatmap plot and rail

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

      // Reserve the right gutter for the liquidity profile rail (only when the
      // canvas is wide enough to be worth it — otherwise reclaim the space).
      const railOn = width >= 420;
      const railTotal = railOn ? RAIL_W + RAIL_GAP : 0;
      const plotW = Math.max(0, width - PAD_LEFT - PAD_RIGHT - railTotal);
      const plotH = Math.max(0, height - PAD_TOP - PAD_BOTTOM);
      const railX0 = PAD_LEFT + plotW + RAIL_GAP;

      // ── Layer 1: dark chart background ──────────────────────────────────────
      ctx.clearRect(0, 0, width, height);
      ctx.fillStyle = "#0a0a0c";
      ctx.fillRect(0, 0, width, height);
      ctx.fillStyle = "#0d0d10";
      ctx.fillRect(PAD_LEFT, PAD_TOP, plotW, plotH);

      // ── Derive price axis from priceMin/priceMax/priceStep ──────────────────
      // LM43B: when meta carries a requested analysis range, treat it as a
      // valid axis even if the snapshot is empty (no observed buckets) — we
      // still want to draw the wider y-axis instead of "no data".
      const observedMin = payload.priceMin;
      const observedMax = payload.priceMax;
      const metaRangeMin = payload.meta?.priceRangeMin;
      const metaRangeMax = payload.meta?.priceRangeMax;
      const haveMetaRange =
        typeof metaRangeMin === "number" &&
        typeof metaRangeMax === "number" &&
        metaRangeMax > metaRangeMin;
      const priceMin = observedMin ?? (haveMetaRange ? metaRangeMin : null);
      const priceMax = observedMax ?? (haveMetaRange ? metaRangeMax : null);
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

      // p index → price (relative to the full payload axis). LM43B: this
      // is now a *fallback* — the writer also stamps absolute `price_bucket`
      // on every cell since LM43B, which is correct even when the observed
      // axis has gaps (common for wide/macro ranges with coarse steps).
      const indexToPrice = (p: number) => payloadMin + p * step;
      const cellPrice = (cell: HeatmapCell): number =>
        typeof cell.price_bucket === "number"
          ? cell.price_bucket
          : indexToPrice(cell.p);

      // ── Pick the rendered y-axis bounds (LM43C: smart viewport) ─────────────
      // Wide/macro modes COLLECT a wide context but the *viewport* should
      // focus on where liquidity actually sits, padded around the current
      // price. The requested range stays available in meta and acts as the
      // outer ceiling for that viewport — never as a forced bound. This
      // avoids the macro-mode failure case where all real liquidity gets
      // compressed into a thin strip in the middle of an otherwise empty
      // 30,000-USD-tall axis.
      const rangeMin = payload.meta?.priceRangeMin;
      const rangeMax = payload.meta?.priceRangeMax;
      const availMin = payload.meta?.availableDepthMin;
      const availMax = payload.meta?.availableDepthMax;
      const haveRequestedRange =
        typeof rangeMin === "number" &&
        typeof rangeMax === "number" &&
        rangeMax > rangeMin;

      // 1) Start from where real data is: prefer observed cells/walls;
      //    fall back to writer-reported available depth; finally the
      //    requested range so something always renders.
      let dataLo = Infinity;
      let dataHi = -Infinity;
      for (const cell of payload.cells) {
        if (cell.total < 6) continue;
        const price = cellPrice(cell);
        if (price < dataLo) dataLo = price;
        if (price > dataHi) dataHi = price;
      }
      for (const wall of payload.walls) {
        if (wall.price_bucket < dataLo) dataLo = wall.price_bucket;
        if (wall.price_bucket > dataHi) dataHi = wall.price_bucket;
      }
      if (!(dataHi > dataLo)) {
        if (typeof availMin === "number" && typeof availMax === "number"
            && availMax > availMin) {
          dataLo = availMin;
          dataHi = availMax;
        } else if (haveRequestedRange) {
          dataLo = rangeMin as number;
          dataHi = rangeMax as number;
        } else {
          dataLo = payloadMin;
          dataHi = payloadMax;
        }
      }

      // 2) Pad around the data band. For wide/macro, use a larger relative
      //    pad so the user perceives more context above/below liquidity
      //    while still keeping the band readable.
      const isWideContext = haveRequestedRange &&
        ((rangeMax as number) - (rangeMin as number)) >= ((dataHi - dataLo) * 3);
      const padFrac = isWideContext ? 0.20 : 0.08;
      const pad = Math.max(step * 2, (dataHi - dataLo) * padFrac);

      let pMin = dataLo - pad;
      let pMax = dataHi + pad;

      // 3) Always keep the current price visible, with breathing room.
      if (typeof currentPrice === "number") {
        const cpPad = Math.max(step * 4, (dataHi - dataLo) * 0.05);
        pMin = Math.min(pMin, currentPrice - cpPad);
        pMax = Math.max(pMax, currentPrice + cpPad);
      }

      // 4) Clamp to the requested range as an outer CEILING — never expand
      //    the viewport to fill the whole wide/macro band.
      if (haveRequestedRange) {
        pMin = Math.max(pMin, rangeMin as number);
        pMax = Math.min(pMax, rangeMax as number);
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
          const price = cellPrice(cell);
          if (price < pMin || price > pMax) continue;

          // Magma map is keyed on magnitude only — direction lives in the rail.
          const color = intensityToColor(cell.total);
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

      // ── Layer 3.5: LM44 zone bands ──────────────────────────────────────────
      // Render aggregated liquidity zones as semi-transparent bands spanning
      // priceMin..priceMax. Gives wide/macro modes a readable "where is the
      // liquidity" silhouette instead of just thin smoothed cell rows. Bands
      // get a small minimum pixel height so very narrow zones stay visible.
      // Old payloads without `zones` simply skip this layer.
      const zonesArr = payload.zones;
      if (Array.isArray(zonesArr) && zonesArr.length > 0) {
        const minBandPx = 3;
        for (const z of zonesArr) {
          if (z.priceMax < pMin || z.priceMin > pMax) continue;
          const clampedHi = Math.min(z.priceMax, pMax);
          const clampedLo = Math.max(z.priceMin, pMin);
          const yTop = priceToY(clampedHi);
          const yBot = priceToY(clampedLo);
          const top = Math.min(yTop, yBot);
          const rawHeight = Math.abs(yBot - yTop);
          const height = Math.max(minBandPx, rawHeight);
          // Strength → alpha (0.06 baseline so weak zones don't disappear).
          const alpha = Math.min(0.35, 0.06 + (z.strengthScore / 100) * 0.25);
          const rgb = z.side === "bid" ? "16,185,129" : "239,68,68";
          ctx.fillStyle = `rgba(${rgb},${alpha})`;
          ctx.fillRect(PAD_LEFT, top, plotW, height);
        }
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
          ctx.shadowBlur = 4;
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

      // ── Layer 4.4: liquidity profile rail (right gutter) ────────────────────
      // Aggregate every visible cell into per-pixel-row bid/ask totals, then
      // draw a horizontal histogram aligned to the shared price axis. This is
      // the "where does liquidity actually sit" silhouette — the real,
      // data-driven version of the old synthetic depth rail.
      if (railOn && plotH > 0) {
        const rows = Math.max(1, Math.floor(plotH));
        const bidRow = new Float32Array(rows);
        const askRow = new Float32Array(rows);

        for (const cell of payload.cells) {
          const price = cellPrice(cell);
          if (price < pMin || price > pMax) continue;
          const row = Math.max(0, Math.min(rows - 1, Math.round(priceToY(price)) - PAD_TOP));
          bidRow[row] += cell.bid;
          askRow[row] += cell.ask;
        }

        let maxMag = 0;
        for (let i = 0; i < rows; i++) {
          const m = bidRow[i] + askRow[i];
          if (m > maxMag) maxMag = m;
        }

        // Gutter backdrop + left baseline.
        ctx.fillStyle = "rgba(255,255,255,0.018)";
        ctx.fillRect(railX0, PAD_TOP, RAIL_W, plotH);
        ctx.strokeStyle = "rgba(255,255,255,0.08)";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(railX0 + 0.5, PAD_TOP);
        ctx.lineTo(railX0 + 0.5, PAD_TOP + plotH);
        ctx.stroke();

        if (maxMag > 0) {
          for (let i = 0; i < rows; i++) {
            const bid = bidRow[i];
            const ask = askRow[i];
            const mag = bid + ask;
            if (mag <= 0) continue;
            const t = mag / maxMag;
            const len = Math.max(1, t * RAIL_W);
            const side = ask >= bid ? "ask" : "bid";
            ctx.fillStyle = profileColor(side, t);
            ctx.fillRect(railX0 + 1, PAD_TOP + i, len, 1);
          }
        }

        // Caption.
        ctx.fillStyle = "rgba(255,255,255,0.4)";
        ctx.font = "9px sans-serif";
        ctx.textAlign = "left";
        ctx.fillText("LIQUIDITY", railX0 + 2, PAD_TOP - 1);
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
        ctx.save();
        ctx.strokeStyle = "rgba(34,211,238,0.85)";
        ctx.lineWidth = 1.5;
        ctx.shadowColor = "rgba(34,211,238,0.55)";
        ctx.shadowBlur = 3;
        ctx.setLineDash([4, 3]);
        ctx.beginPath();
        ctx.moveTo(PAD_LEFT, y);
        ctx.lineTo(PAD_LEFT + plotW, y);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.restore();

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

      {/* LM43C: tiny non-invasive label so the user knows the viewport
          auto-fits the data even though the underlying mode collects a wider
          context. Only shown when a range mode is stamped. */}
      {payload.meta?.priceRangeMode && !error && (
        <div className="absolute bottom-1 left-1 px-1.5 py-0.5 rounded bg-black/40 text-[9px] leading-none text-white/45 font-mono pointer-events-none">
          View: Auto · Range: {payload.meta.priceRangeMode}
        </div>
      )}
    </div>
  );
}

export default HeatmapCanvas;
