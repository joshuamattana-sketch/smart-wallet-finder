/**
 * lumora-web/lib/whale-alerts-loader.ts
 * --------------------------------------
 * LM63F — Server-side loader for the local whale-events JSONL journal.
 *
 * The Python LM63E pipeline writes whale events to:
 *     <repo_root>/data/whale_events.jsonl
 *
 * From the Next.js working directory this is `../data/whale_events.jsonl`.
 *
 * Vercel-safe: if the file is missing, unreadable, or malformed, the loader
 * returns the existing mock alerts with `data_source: "mock"`. Never throws.
 */

import { promises as fs } from "node:fs";
import path from "node:path";

import { mockWhaleAlerts } from "@/lib/mock-data";

// ── Public types ──────────────────────────────────────────────────────────────

export type WhaleSide = "BUY" | "SELL";
export type WhaleRisk = "HIGH" | "MEDIUM" | "LOW";

/**
 * UI-shaped whale alert — mirrors the shape consumed by the existing
 * `app/(app)/whale-alerts/page.tsx`. Both mock and journal-derived alerts
 * fit this single interface so the page renders identically either way.
 */
export interface WhaleAlertView {
  id:         number | string;
  time:       string;        // "HH:MM"
  symbol:     string;        // e.g. "BTCUSDT"
  side:       WhaleSide;
  size:       string;        // e.g. "$4.2M"
  exchange:   string;        // human-readable, e.g. "Binance"
  leverage:   string;        // e.g. "1×" (spot)
  type:       string;        // "Aggressive Buy" / "Aggressive Sell" / "Whale Flow"
  risk:       WhaleRisk;
  confidence: number;        // 0–100
  reason:     string;
  action:     string;
}

export type WhaleAlertsDataSource = "journal" | "mock";

export interface WhaleAlertsResponse {
  data_source: WhaleAlertsDataSource;
  /** ISO 8601 of the loader call. */
  generated_at: string;
  /** Total rows read from the journal (0 when source = "mock"). */
  journal_row_count: number;
  alerts: WhaleAlertView[];
  /** Diagnostic note — short message about why we fell back, if applicable. */
  note?: string;
}

// ── Resolution / parsing ──────────────────────────────────────────────────────

const DEFAULT_LIMIT = 50;
const JOURNAL_RELATIVE_PATH = path.join("..", "data", "whale_events.jsonl");

function resolveJournalPath(): string {
  // process.cwd() at runtime is the lumora-web directory.
  return path.resolve(process.cwd(), JOURNAL_RELATIVE_PATH);
}

interface JournalRow {
  event?: Record<string, unknown>;
  meta?: Record<string, unknown> | null;
  written_at?: string;
}

function tryParseLine(line: string): JournalRow | null {
  const trimmed = line.trim();
  if (!trimmed) return null;
  try {
    const obj = JSON.parse(trimmed);
    if (!obj || typeof obj !== "object" || Array.isArray(obj)) return null;
    return obj as JournalRow;
  } catch {
    return null;
  }
}

// ── Field normalization ──────────────────────────────────────────────────────

function asNumber(v: unknown, fallback = 0): number {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string") {
    const n = Number.parseFloat(v);
    if (Number.isFinite(n)) return n;
  }
  return fallback;
}

function asString(v: unknown, fallback = ""): string {
  if (typeof v === "string") return v;
  if (v == null) return fallback;
  return String(v);
}

function fmtNotional(n: number): string {
  if (!Number.isFinite(n) || n <= 0) return "$0";
  if (n >= 1_000_000_000) return `$${(n / 1_000_000_000).toFixed(2)}B`;
  if (n >= 1_000_000)     return `$${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000)         return `$${(n / 1_000).toFixed(1)}K`;
  return `$${n.toFixed(0)}`;
}

function fmtTimeFromIso(iso: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

function normalizeExchange(raw: string): string {
  const v = raw.toLowerCase();
  if (v.includes("binance")) return "Binance";
  if (v.includes("bybit"))   return "Bybit";
  if (v.includes("okx"))     return "OKX";
  if (v.includes("coinbase")) return "Coinbase";
  if (v.includes("hyperliquid")) return "Hyperliquid";
  return raw || "—";
}

function normalizeSide(raw: string): WhaleSide {
  const v = raw.toLowerCase();
  if (v === "sell" || v === "short" || v === "ask") return "SELL";
  return "BUY";
}

function severityToRisk(severity: string): WhaleRisk {
  const v = severity.toLowerCase();
  if (v === "extreme") return "HIGH";
  if (v === "high")    return "HIGH";
  if (v === "notable") return "MEDIUM";
  return "LOW";
}

function normalizeConfidence(raw: number): number {
  // Journal events use 0–1 floats. The page expects 0–100.
  // Anything already in the 0–100 range is preserved.
  if (!Number.isFinite(raw)) return 0;
  if (raw <= 1) return Math.round(raw * 100);
  return Math.round(raw);
}

function deriveType(side: WhaleSide, severity: string): string {
  const s = severity.toLowerCase();
  if (s === "extreme") return side === "BUY" ? "Extreme Buy"   : "Extreme Sell";
  if (s === "high")    return side === "BUY" ? "Aggressive Buy" : "Aggressive Sell";
  if (s === "notable") return side === "BUY" ? "Whale Buy"      : "Whale Sell";
  return side === "BUY" ? "Buy Flow" : "Sell Flow";
}

function deriveAction(side: WhaleSide, risk: WhaleRisk): string {
  if (risk === "HIGH") {
    return side === "BUY"
      ? "Watch for follow-through and continuation."
      : "Monitor for distribution / reversal pressure.";
  }
  if (risk === "MEDIUM") {
    return side === "BUY"
      ? "Watch — confirm with bid wall holding."
      : "Watch — confirm with ask wall holding.";
  }
  return "Monitor — single flow, low conviction.";
}

function normalizeRow(row: JournalRow, index: number): WhaleAlertView | null {
  const event = row.event;
  if (!event || typeof event !== "object") return null;

  const symbol = asString(event.symbol).toUpperCase();
  if (!symbol) return null;

  const sideRaw    = asString(event.side);
  const side       = normalizeSide(sideRaw);
  const severity   = asString(event.severity, "notable");
  const risk       = severityToRisk(severity);
  const notional   = asNumber(event.notional_usd);
  const confidence = normalizeConfidence(asNumber(event.confidence));
  const reason     = asString(event.reason, `${symbol} whale flow`);
  const exchange   = normalizeExchange(asString(event.exchange));
  const time       = fmtTimeFromIso(asString(event.event_ts));
  const id         = asString(event.whale_event_id) || `evt-${index}`;

  return {
    id,
    time,
    symbol,
    side,
    size: fmtNotional(notional),
    exchange,
    leverage: "1×",            // exchange spot — no leverage info
    type: deriveType(side, severity),
    risk,
    confidence,
    reason,
    action: deriveAction(side, risk),
  };
}

// ── Public API ────────────────────────────────────────────────────────────────

/** Mock alerts already conform to `WhaleAlertView`. */
const MOCK_ALERTS: WhaleAlertView[] = mockWhaleAlerts.map((a) => ({
  id:         a.id,
  time:       a.time,
  symbol:     a.symbol,
  side:       a.side as WhaleSide,
  size:       a.size,
  exchange:   a.exchange,
  leverage:   a.leverage,
  type:       a.type,
  risk:       a.risk as WhaleRisk,
  confidence: a.confidence,
  reason:     a.reason,
  action:     a.action,
}));

function mockResponse(note?: string): WhaleAlertsResponse {
  return {
    data_source: "mock",
    generated_at: new Date().toISOString(),
    journal_row_count: 0,
    alerts: MOCK_ALERTS,
    note,
  };
}

/**
 * Load whale alerts. Reads the local LM63E JSONL journal when available;
 * falls back to the in-repo mock alerts otherwise.
 *
 * Never throws. `limit` is clamped to a sane range.
 */
export async function loadWhaleAlerts(limit = DEFAULT_LIMIT): Promise<WhaleAlertsResponse> {
  const cap = Number.isFinite(limit) ? Math.max(1, Math.min(500, Math.trunc(limit))) : DEFAULT_LIMIT;

  let raw: string;
  try {
    raw = await fs.readFile(resolveJournalPath(), "utf-8");
  } catch (err) {
    const code = (err as NodeJS.ErrnoException)?.code ?? "";
    if (code === "ENOENT") {
      return mockResponse("journal file not present");
    }
    return mockResponse(`journal read error: ${code || (err as Error).message}`);
  }

  const lines = raw.split(/\r?\n/);
  const rows: JournalRow[] = [];
  for (const line of lines) {
    const parsed = tryParseLine(line);
    if (parsed) rows.push(parsed);
  }

  if (rows.length === 0) {
    return mockResponse("journal present but no valid rows");
  }

  // Newest first. The journal is append-only with newest at EOF.
  rows.reverse();

  const alerts: WhaleAlertView[] = [];
  for (let i = 0; i < rows.length && alerts.length < cap; i++) {
    const view = normalizeRow(rows[i], i);
    if (view) alerts.push(view);
  }

  if (alerts.length === 0) {
    return mockResponse("journal rows present but none normalised");
  }

  return {
    data_source: "journal",
    generated_at: new Date().toISOString(),
    journal_row_count: rows.length,
    alerts,
  };
}
