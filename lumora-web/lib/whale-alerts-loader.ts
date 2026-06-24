/**
 * lumora-web/lib/whale-alerts-loader.ts
 * --------------------------------------
 * LM63F + LM63I — Server-side loader for whale events.
 *
 * Source priority (server-side only; service-role key never leaves the server):
 *   1. Supabase whale_events  (env: SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY,
 *      or SUPABASE_ANON_KEY when the table has an anon read policy)
 *   2. Local JSONL journal    (<repo_root>/data/whale_events.jsonl)
 *   3. Built-in mock alerts   (`lib/mock-data`)
 *
 * Every tier is defensive: missing env / file / network error / malformed
 * rows all silently fall through to the next tier. The loader never throws,
 * so the API route and the page can never crash regardless of deploy target.
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
  /**
   * LM68D — raw machine-readable fields for chart consumers. Optional so
   * mock alerts (which lack them) and existing consumers stay untouched.
   */
  event_ts?:     string;     // ISO 8601 event timestamp
  notional_usd?: number;     // raw notional in USD
  severity?:     string;     // raw severity bucket, e.g. "high" / "notable"
  source_type?:  string;     // e.g. "binance_spot_aggtrade"
}

export type WhaleAlertsDataSource = "supabase" | "journal" | "mock";

export interface WhaleAlertsResponse {
  data_source: WhaleAlertsDataSource;
  /** ISO 8601 of the loader call. */
  generated_at: string;
  /** Rows obtained from whichever source actually answered. 0 when mock. */
  row_count: number;
  /**
   * Back-compat: existing API consumers read `journal_row_count`. Kept
   * alongside `row_count` and set to the journal-tier count when the
   * journal tier answered, else 0.
   */
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

/**
 * Normalize a whale-event-shaped dict into the UI view. Used by both the
 * journal tier (`row.event`) and the Supabase tier (row columns from
 * whale_events). Returns null when the input lacks a symbol.
 */
function normalizeEventDict(
  event: Record<string, unknown>,
  index: number,
): WhaleAlertView | null {
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
  const eventTs    = asString(event.event_ts);
  const time       = fmtTimeFromIso(eventTs);
  const id         = asString(event.whale_event_id) || `evt-${index}`;
  const sourceType = asString(event.source_type);

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
    event_ts: eventTs || undefined,
    notional_usd: notional > 0 ? notional : undefined,
    severity,
    source_type: sourceType || undefined,
  };
}

function normalizeJournalRow(row: JournalRow, index: number): WhaleAlertView | null {
  const event = row.event;
  if (!event || typeof event !== "object") return null;
  return normalizeEventDict(event, index);
}

function normalizeSupabaseRow(row: unknown, index: number): WhaleAlertView | null {
  if (!row || typeof row !== "object") return null;
  return normalizeEventDict(row as Record<string, unknown>, index);
}

// ── Supabase tier ─────────────────────────────────────────────────────────────

/**
 * Read up to `limit` rows from public.whale_events via PostgREST.
 *
 * Returns `null` (no throw, no log spam) when:
 *   - env vars are missing,
 *   - the HTTP call errors,
 *   - the response is not an array,
 *   - or every returned row fails to normalize.
 *
 * The service-role key never leaves this function — it's only attached to
 * the outbound server-side fetch headers.
 */
async function loadFromSupabase(
  limit: number,
): Promise<{ alerts: WhaleAlertView[]; rowCount: number } | null> {
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY ?? process.env.SUPABASE_ANON_KEY;
  if (!url || !key) return null;

  const endpoint =
    `${url.replace(/\/$/, "")}/rest/v1/whale_events` +
    `?select=*&order=event_ts.desc.nullslast,created_at.desc&limit=${limit}`;

  let res: Response;
  try {
    res = await fetch(endpoint, {
      method: "GET",
      headers: {
        apikey:        key,
        Authorization: `Bearer ${key}`,
        Accept:        "application/json",
      },
      // Always fresh — the page itself is force-dynamic and short-lived.
      cache: "no-store",
    });
  } catch {
    return null;
  }

  if (!res.ok) return null;

  let body: unknown;
  try {
    body = await res.json();
  } catch {
    return null;
  }
  if (!Array.isArray(body)) return null;
  if (body.length === 0) return null;

  const alerts: WhaleAlertView[] = [];
  for (let i = 0; i < body.length; i++) {
    const view = normalizeSupabaseRow(body[i], i);
    if (view) alerts.push(view);
  }
  if (alerts.length === 0) return null;
  return { alerts, rowCount: body.length };
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
    row_count: 0,
    journal_row_count: 0,
    alerts: MOCK_ALERTS,
    note,
  };
}

// ── Local JSONL journal tier ─────────────────────────────────────────────────

async function loadFromJournal(
  cap: number,
): Promise<{ alerts: WhaleAlertView[]; rowCount: number; note?: string } | { fallbackNote: string } | null> {
  let raw: string;
  try {
    raw = await fs.readFile(resolveJournalPath(), "utf-8");
  } catch (err) {
    const code = (err as NodeJS.ErrnoException)?.code ?? "";
    if (code === "ENOENT") {
      return { fallbackNote: "journal file not present" };
    }
    return { fallbackNote: `journal read error: ${code || (err as Error).message}` };
  }

  const lines = raw.split(/\r?\n/);
  const rows: JournalRow[] = [];
  for (const line of lines) {
    const parsed = tryParseLine(line);
    if (parsed) rows.push(parsed);
  }
  if (rows.length === 0) {
    return { fallbackNote: "journal present but no valid rows" };
  }
  rows.reverse(); // newest first

  const alerts: WhaleAlertView[] = [];
  for (let i = 0; i < rows.length && alerts.length < cap; i++) {
    const view = normalizeJournalRow(rows[i], i);
    if (view) alerts.push(view);
  }
  if (alerts.length === 0) {
    return { fallbackNote: "journal rows present but none normalised" };
  }
  return { alerts, rowCount: rows.length };
}

function isJournalSuccess(
  out: Awaited<ReturnType<typeof loadFromJournal>>,
): out is { alerts: WhaleAlertView[]; rowCount: number; note?: string } {
  return out !== null && Object.prototype.hasOwnProperty.call(out, "alerts");
}

// ── Public API ────────────────────────────────────────────────────────────────

/**
 * Load whale alerts, walking the source priority: Supabase → JSONL → mock.
 *
 * Every tier is defensive — never throws. `limit` is clamped to [1, 500].
 */
export async function loadWhaleAlerts(limit = DEFAULT_LIMIT): Promise<WhaleAlertsResponse> {
  const cap = Number.isFinite(limit) ? Math.max(1, Math.min(500, Math.trunc(limit))) : DEFAULT_LIMIT;

  // ── Tier 1: Supabase ────────────────────────────────────────────────────
  try {
    const sb = await loadFromSupabase(cap);
    if (sb) {
      return {
        data_source: "supabase",
        generated_at: new Date().toISOString(),
        row_count: sb.alerts.length,
        journal_row_count: 0,
        alerts: sb.alerts,
      };
    }
  } catch {
    // Loader is defensive but never trust transitive deps; swallow + fall through.
  }

  // ── Tier 2: Local JSONL ─────────────────────────────────────────────────
  const journalNotes: string[] = [];
  try {
    const j = await loadFromJournal(cap);
    if (isJournalSuccess(j)) {
      return {
        data_source: "journal",
        generated_at: new Date().toISOString(),
        row_count: j.alerts.length,
        journal_row_count: j.rowCount,
        alerts: j.alerts,
      };
    }
    if (j && "fallbackNote" in j) journalNotes.push(j.fallbackNote);
  } catch (err) {
    journalNotes.push(`journal exception: ${(err as Error).message ?? "unknown"}`);
  }

  // ── Tier 3: Mock ────────────────────────────────────────────────────────
  return mockResponse(journalNotes.length > 0 ? journalNotes.join(" · ") : undefined);
}
