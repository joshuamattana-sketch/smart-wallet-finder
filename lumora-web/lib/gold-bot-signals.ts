/**
 * lumora-web/lib/gold-bot-signals.ts
 * ----------------------------------
 * Server-side READ-ONLY loader for the Gold Bot forward-signal TRACK RECORD.
 *
 * Reads the summary JSON the Python signal logger writes
 * (`<repo_root>/data/gold_bot/signals/signals_<SYMBOL>_<TF>.summary.json`) and
 * returns one tolerant, camelCase object for the bot landing.
 *
 * STRICT boundaries (same posture as lib/gold-bot-status.ts):
 *   * READ-ONLY. No writes, no MT5, no Python/shell, no external HTTP, no secrets.
 *   * Defensive: a missing / malformed file degrades to `ok: false` + warnings,
 *     never throws. The route and landing can never crash.
 */

import { promises as fs } from "node:fs";
import path from "node:path";

// Build-time bundled snapshots, keyed by `${SYMBOL}_${TF}`. These are the
// reliable source in production: on Vercel a committed-but-untraced data file
// is NOT guaranteed to ship in the serverless function bundle, but a static
// JSON import is webpack-bundled into the function, so it always ships.
// The fs read below still runs first so local dev / a VPS with the live logger
// picks up fresher data when present.
import bundledXauusdM15 from "../data/gold_bot/signals/signals_XAUUSD_M15.summary.json";

const BUNDLED_SNAPSHOTS: Record<string, unknown> = {
  XAUUSD_M15: bundledXauusdM15,
};

// Candidate roots for an on-disk track-record file, tried in order:
//   1. App-local snapshot committed inside lumora-web.
//   2. Repo-root data/ — present in local dev where the Python logger writes.
const DATA_ROOTS = [
  path.resolve(process.cwd(), "data", "gold_bot"),
  path.resolve(process.cwd(), "..", "data", "gold_bot"),
];

export interface PresetRecord {
  name: string;
  label: string;
  description: string;
  trades: number;
  wins: number;
  losses: number;
  neutral: number;
  winRatePct: number | null;
  expectancyPoints: number | null;
  totalRealizedPoints: number | null;
  /** True when net expectancy is positive — the only presets worth selling. */
  isPositive: boolean;
}

export interface GoldBotTrackRecord {
  ok: boolean;
  generatedAt: string;
  dataAsOf: string | null;
  symbol: string | null;
  timeframe: string | null;
  expectancyBasis: string | null; // "net_of_cost" | "gross"
  closedTrades: number;
  defaultPreset: string | null;
  presets: PresetRecord[];
  warnings: string[];
}

type Dict = Record<string, unknown>;

const asNum = (v: unknown, d: number | null = null): number | null =>
  typeof v === "number" && Number.isFinite(v) ? v : d;
const asInt = (v: unknown): number =>
  typeof v === "number" && Number.isFinite(v) ? v : 0;
const asStr = (v: unknown): string | null =>
  typeof v === "string" && v ? v : null;

async function readJsonFile(rel: string): Promise<Dict | null> {
  for (const root of DATA_ROOTS) {
    try {
      const raw = await fs.readFile(path.join(root, rel), "utf-8");
      const obj = JSON.parse(raw);
      if (obj && typeof obj === "object" && !Array.isArray(obj)) return obj as Dict;
    } catch {
      // ENOENT / parse error → try the next candidate root
    }
  }
  return null; // absent in every candidate root
}

// Stable display order: low risk → high edge. Featured pick = swing_guarded.
const PRESET_ORDER = ["conservative", "balanced", "runner", "swing_guarded", "swing"];

function buildPresets(perPreset: Dict, presetMeta: Dict): PresetRecord[] {
  const names = Object.keys(perPreset);
  names.sort((a, b) => {
    const ia = PRESET_ORDER.indexOf(a);
    const ib = PRESET_ORDER.indexOf(b);
    return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
  });
  return names.map((name) => {
    const s = (perPreset[name] && typeof perPreset[name] === "object"
      ? (perPreset[name] as Dict)
      : {}) as Dict;
    const meta = (presetMeta[name] && typeof presetMeta[name] === "object"
      ? (presetMeta[name] as Dict)
      : {}) as Dict;
    const expectancy = asNum(s.expectancy_points);
    return {
      name,
      label: asStr(meta.label) ?? name,
      description: asStr(meta.description) ?? "",
      trades: asInt(s.trades),
      wins: asInt(s.wins),
      losses: asInt(s.losses),
      neutral: asInt(s.neutral),
      winRatePct: asNum(s.win_rate_pct),
      expectancyPoints: expectancy,
      totalRealizedPoints: asNum(s.total_realized_points),
      isPositive: typeof expectancy === "number" && expectancy > 0,
    };
  });
}

export async function loadGoldBotTrackRecord(
  symbol = "XAUUSD",
  timeframe = "M15",
): Promise<GoldBotTrackRecord> {
  const warnings: string[] = [];
  const rel = `signals/signals_${symbol}_${timeframe}.summary.json`;
  // Prefer a fresh on-disk file (dev / VPS); fall back to the build-time
  // bundled snapshot so production always has the track record.
  const fromDisk = await readJsonFile(rel);
  const bundled = BUNDLED_SNAPSHOTS[`${symbol}_${timeframe}`];
  const doc: Dict | null =
    fromDisk ??
    (bundled && typeof bundled === "object" && !Array.isArray(bundled)
      ? (bundled as Dict)
      : null);

  if (!doc) {
    warnings.push("no track record yet — run scripts/run_gold_bot_signal_logger.py");
    return {
      ok: false,
      generatedAt: new Date().toISOString(),
      dataAsOf: null,
      symbol,
      timeframe,
      expectancyBasis: null,
      closedTrades: 0,
      defaultPreset: null,
      presets: [],
      warnings,
    };
  }

  const perPreset = (doc.per_preset && typeof doc.per_preset === "object"
    ? (doc.per_preset as Dict)
    : {}) as Dict;
  const presetMeta = (doc.presets && typeof doc.presets === "object"
    ? (doc.presets as Dict)
    : {}) as Dict;
  const presets = buildPresets(perPreset, presetMeta);

  if (!presets.length) warnings.push("track record present but has no scored presets yet");

  return {
    ok: presets.length > 0,
    generatedAt: new Date().toISOString(),
    dataAsOf: asStr(doc.generated_at),
    symbol: asStr(doc.symbol) ?? symbol,
    timeframe: asStr(doc.timeframe) ?? timeframe,
    expectancyBasis: asStr(doc.expectancy_basis),
    closedTrades: asInt(doc.closed_trades),
    defaultPreset: asStr(doc.default_preset),
    presets,
    warnings,
  };
}
