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

// Calm, depth-oriented ramp. Interpolated, not hard-banded, so few time
// buckets do not read as flat slabs of one colour:
//   0–20  very dark / deep navy   (low alpha → background shows through)
//   20–45 blue → cyan
//   45–70 green
//   70–88 muted yellow (not neon)
//   88–100 orange → red (reserved for genuinely critical liquidity)
// The alpha curve stays low at the bottom and only approaches opaque near the
// top, which gives the heatmap its sense of depth.
const RAMP: Stop[] = [
  { v: 0,   c: [6, 10, 32, 0.0] },
  { v: 12,  c: [10, 22, 70, 0.22] },
  { v: 22,  c: [16, 42, 120, 0.34] },
  { v: 33,  c: [22, 74, 182, 0.5] },
  { v: 45,  c: [26, 140, 202, 0.62] },
  { v: 57,  c: [26, 182, 168, 0.72] },
  { v: 70,  c: [42, 200, 120, 0.8] },
  { v: 80,  c: [150, 205, 92, 0.86] },
  { v: 88,  c: [230, 206, 92, 0.9] },
  { v: 94,  c: [240, 150, 56, 0.94] },
  { v: 100, c: [234, 78, 46, 0.97] },
];

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

function rgba(r: number, g: number, b: number, a: number): string {
  return `rgba(${Math.round(r)},${Math.round(g)},${Math.round(b)},${Math.round(a * 1000) / 1000})`;
}

/**
 * Map an intensity 0–100 to an interpolated rgba color string.
 *
 * `side` applies a gentle hue nudge so bids read a touch cooler (green/cyan)
 * and asks a touch warmer, without shifting the overall magnitude reading or
 * flooding the map with red.
 */
export function intensityToColor(value: number, side?: HeatmapSide): string {
  const v = Number.isFinite(value) ? Math.max(0, Math.min(100, value)) : 0;

  if (v < MIN_VISIBLE) {
    // Transparent — caller skips these. Keep "...,0)" suffix for that check.
    return "rgba(6,10,32,0)";
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

  let r = lerp(lo.c[0], hi.c[0], t);
  let g = lerp(lo.c[1], hi.c[1], t);
  let b = lerp(lo.c[2], hi.c[2], t);
  const a = lerp(lo.c[3], hi.c[3], t);

  // Gentle directional tint (kept small so asks don't read as "more red").
  if (side === "bid") {
    g = Math.min(255, g + 12);
    b = Math.min(255, b + 8);
    r = Math.max(0, r - 8);
  } else if (side === "ask") {
    r = Math.min(255, r + 10);
    g = Math.max(0, g - 4);
    b = Math.max(0, b - 10);
  }

  return rgba(r, g, b, a);
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
