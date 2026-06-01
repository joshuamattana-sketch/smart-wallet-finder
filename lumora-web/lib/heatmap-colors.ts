// lib/heatmap-colors.ts
// Color scale for the Liquidity Map Canvas renderer (v1).
// Pure functions — no DOM, no dependencies. Safe to import anywhere.

export type HeatmapSide = "bid" | "ask" | "mixed";

/** A single rgba stop on the intensity ramp. */
interface Stop {
  v: number;            // upper bound of this band (intensity 0–100)
  c: [number, number, number, number]; // r,g,b,a
}

// Neutral ramp: dark → deep blue → cyan → green → yellow → orange → red.
// Mirrors the CoinGlass-style ramp already used by the legacy DOM map so the
// Canvas renderer stays visually consistent with the rest of the page.
const RAMP: Stop[] = [
  { v:  5, c: [6, 8, 24, 0] },
  { v: 14, c: [10, 18, 85, 0.55] },
  { v: 27, c: [12, 48, 160, 0.7] },
  { v: 40, c: [8, 95, 215, 0.78] },
  { v: 53, c: [0, 158, 215, 0.84] },
  { v: 66, c: [0, 195, 145, 0.88] },
  { v: 78, c: [35, 215, 55, 0.91] },
  { v: 87, c: [195, 225, 0, 0.93] },
  { v: 93, c: [255, 145, 0, 0.96] },
  { v: 101, c: [255, 50, 18, 0.98] },
];

function rgba(c: [number, number, number, number]): string {
  return `rgba(${c[0]},${c[1]},${c[2]},${c[3]})`;
}

/**
 * Map an intensity 0–100 to an rgba color string.
 *
 * Scale:
 *  - 0       → transparent / dark
 *  - low     → deep blue
 *  - medium  → cyan
 *  - high    → green
 *  - wall    → yellow
 *  - critical→ orange / red
 *
 * `side` applies a subtle tint so bids read cooler (green/cyan) and asks
 * warmer (yellow/orange/red) without breaking the underlying intensity ramp.
 */
export function intensityToColor(value: number, side?: HeatmapSide): string {
  const v = Number.isFinite(value) ? Math.max(0, Math.min(100, value)) : 0;

  let base: [number, number, number, number] = RAMP[RAMP.length - 1].c;
  for (const stop of RAMP) {
    if (v < stop.v) {
      base = stop.c;
      break;
    }
  }

  if (v < 5) return rgba(base); // transparent — skip tinting

  // Subtle directional tint. Keep it gentle so the ramp still communicates
  // magnitude; side only nudges hue at the margins.
  let [r, g, b, a] = base;
  if (side === "bid") {
    g = Math.min(255, g + 22);
    b = Math.min(255, b + 14);
    r = Math.max(0, r - 12);
  } else if (side === "ask") {
    r = Math.min(255, r + 24);
    g = Math.max(0, g - 6);
    b = Math.max(0, b - 14);
  }

  return rgba([Math.round(r), Math.round(g), Math.round(b), a]);
}

/** Solid highlight color for a liquidity wall marker (no transparency). */
export function wallColor(side: HeatmapSide): string {
  if (side === "ask") return "rgba(255,120,40,0.95)";
  if (side === "bid") return "rgba(60,230,140,0.95)";
  return "rgba(245,215,40,0.95)";
}
