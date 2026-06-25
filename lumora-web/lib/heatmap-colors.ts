// lib/heatmap-colors.ts
// Color scale for the Liquidity Map Canvas renderer.
// Pure functions — no DOM, no dependencies. Safe to import anywhere.

export type HeatmapSide = "bid" | "ask" | "mixed";

/** A control point on the intensity ramp (interpolated between neighbours). */
interface Stop {
  v: number;                              // intensity 0–100
  c: [number, number, number, number];    // r,g,b,a
}

// Below this intensity a cell is treated as empty (fully transparent) so the
// dark chart background shows through and low noise does not wash the map out.
const MIN_VISIBLE = 6;

// Magma / inferno ramp — matches the look of pro liquidation heatmaps
// (Alphractal-style): near-black background → deep purple → magenta → orange →
// bright yellow for the hottest liquidity. Single perceptual ramp keyed on
// intensity only; bid/ask direction is shown by the side profile rail, not by
// tinting the map (so the heatmap reads as one clean magnitude field).
//   0–18   black → deep indigo/purple   (low alpha → background shows through)
//   18–42  purple → magenta
//   42–68  magenta → red/orange
//   68–90  orange → gold
//   90–100 gold → pale yellow (reserved for genuinely critical liquidity)
const RAMP: Stop[] = [
  { v: 0,   c: [0, 0, 4, 0.0] },
  { v: 8,   c: [12, 8, 38, 0.18] },
  { v: 18,  c: [40, 11, 84, 0.34] },
  { v: 30,  c: [85, 15, 109, 0.5] },
  { v: 42,  c: [136, 34, 106, 0.64] },
  { v: 55,  c: [186, 54, 85, 0.76] },
  { v: 68,  c: [227, 89, 51, 0.85] },
  { v: 80,  c: [249, 140, 10, 0.9] },
  { v: 90,  c: [249, 201, 50, 0.94] },
  { v: 100, c: [252, 245, 150, 0.98] },
];

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

function clamp01(t: number): number {
  return t < 0 ? 0 : t > 1 ? 1 : t;
}

function rgba(r: number, g: number, b: number, a: number): string {
  return `rgba(${Math.round(r)},${Math.round(g)},${Math.round(b)},${Math.round(a * 1000) / 1000})`;
}

/**
 * Map an intensity 0–100 to an interpolated rgba color string on the magma
 * ramp. `side` is accepted for backwards compatibility but no longer tints the
 * map — direction is conveyed by the liquidity profile rail instead.
 */
export function intensityToColor(value: number, _side?: HeatmapSide): string {
  const v = Number.isFinite(value) ? Math.max(0, Math.min(100, value)) : 0;

  if (v < MIN_VISIBLE) {
    // Transparent — caller skips these. Keep "...,0)" suffix for that check.
    return "rgba(0,0,4,0)";
  }

  // Find the surrounding ramp segment and interpolate within it.
  let lo = RAMP[0];
  let hi = RAMP[RAMP.length - 1];
  for (let i = 0; i < RAMP.length - 1; i++) {
    if (v >= RAMP[i].v && v <= RAMP[i + 1].v) {
      lo = RAMP[i];
      hi = RAMP[i + 1];
      break;
    }
  }
  const span = hi.v - lo.v;
  const t = span <= 0 ? 0 : (v - lo.v) / span;

  const r = lerp(lo.c[0], hi.c[0], t);
  const g = lerp(lo.c[1], hi.c[1], t);
  const b = lerp(lo.c[2], hi.c[2], t);
  const a = lerp(lo.c[3], hi.c[3], t);

  return rgba(r, g, b, a);
}

/**
 * Side-aware color for the liquidity profile rail (right gutter). Bids read
 * green (long / support, below price), asks read red (short / resistance,
 * above price). `t` is the normalised magnitude 0–1 → brighter + more opaque
 * for the heaviest levels.
 */
export function profileColor(side: HeatmapSide, t: number): string {
  const m = clamp01(t);
  const a = 0.35 + 0.6 * m;
  if (side === "ask") {
    // red: 239,68,68 → 248,113,113
    return rgba(lerp(214, 248, m), lerp(52, 113, m), lerp(52, 113, m), a);
  }
  // bid (and mixed) → green: 16,185,129 → 52,211,153
  return rgba(lerp(16, 52, m), lerp(185, 211, m), lerp(129, 153, m), a);
}

/**
 * Subtle highlight color for a liquidity wall marker. Alpha is intentionally
 * moderate so walls read as accents, not dominant bars.
 */
export function wallColor(side: HeatmapSide): string {
  if (side === "ask") return "rgba(255,140,60,0.7)";
  if (side === "bid") return "rgba(70,220,150,0.7)";
  return "rgba(240,210,90,0.7)";
}
