/**
 * lumora-web/lib/gold-bot-status.ts
 * ----------------------------------
 * LM91A — Server-side READ-ONLY loader for the Gold Bot local status surface.
 *
 * Reads the local artifacts the LM86–LM90 demo loop writes (session report,
 * session review, trade outcomes, safety state, active modifiers, scorecard,
 * latest learning cycle, worker status) from `<repo_root>/data/gold_bot/…` and
 * returns one tolerant status object for `/api/gold-bot/status`.
 *
 * STRICT boundaries (mirrors the rest of the Gold Bot demo-only posture):
 *   * READ-ONLY. No writes, no MT5, no Python/shell execution, no external HTTP.
 *   * NEVER reads secrets / env webhook values. Discord "ready to send" is
 *     deliberately reported as unknown — the env is never inspected here.
 *   * Defensive: missing / malformed files degrade to flags + warnings, never
 *     throw. The route and panel can never crash regardless of what exists.
 */

import { promises as fs } from "node:fs";
import path from "node:path";

// process.cwd() at runtime is the lumora-web directory; the data lives one up.
const DATA_ROOT = path.resolve(process.cwd(), "..", "data", "gold_bot");

// ── output shape (camelCase; tolerant of upstream schema drift) ────────────────
export interface GoldBotStatus {
  ok: boolean;
  generatedAt: string;
  mode: "local_read_only";
  session: {
    exists: boolean;
    sessionId: string | null;
    mode: string | null;
    symbol: string | null;
    riskMode: string | null;
    stopReason: string | null;
    startedAt: string | null;
    endedAt: string | null;
    iterations: number | null;
    ordersAttempted: number | null;
    ordersSent: number | null;
    blockedBySafety: number | null;
    blockedReasons: Record<string, number>;
  };
  review: { exists: boolean; keyFindings: string[]; nextActions: string[] };
  outcomes: {
    exists: boolean;
    wins: number; losses: number; breakeven: number; open: number;
    realizedPnl: number;
  };
  safety: {
    stateExists: boolean;
    cooldownActive: boolean;
    consecutiveLosses: number;
    topBlockers: { reason: string; count: number }[];
  };
  learning: {
    activeModifiersExists: boolean;
    modifierCount: number;
    modifiers: { setup: string; confidenceModifier: number }[];
    scorecardStatus: string | null;
    latestCycleVerdict: string | null;
  };
  worker: { exists: boolean; lastHeartbeat: string | null; mode: string | null };
  discord: {
    readyToPreview: boolean;
    readyToSend: "unknown_env_not_checked";
    lastReviewExists: boolean;
  };
  warnings: string[];
}

// ── tolerant readers (never throw) ─────────────────────────────────────────────
type Dict = Record<string, unknown>;

async function readJsonFile(rel: string): Promise<Dict | null> {
  try {
    const raw = await fs.readFile(path.join(DATA_ROOT, rel), "utf-8");
    const obj = JSON.parse(raw);
    return obj && typeof obj === "object" && !Array.isArray(obj) ? (obj as Dict) : null;
  } catch {
    return null; // ENOENT / parse error / anything → absent
  }
}

async function readJsonlLast(rel: string): Promise<Dict | null> {
  try {
    const raw = await fs.readFile(path.join(DATA_ROOT, rel), "utf-8");
    const lines = raw.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
    for (let i = lines.length - 1; i >= 0; i--) {
      try {
        const obj = JSON.parse(lines[i]);
        if (obj && typeof obj === "object") return obj as Dict;
      } catch {
        /* skip bad line */
      }
    }
    return null;
  } catch {
    return null;
  }
}

const asNum = (v: unknown, d: number | null = null): number | null =>
  typeof v === "number" && Number.isFinite(v) ? v : d;
const asStr = (v: unknown): string | null => (typeof v === "string" && v ? v : null);
const asInt = (v: unknown): number => (typeof v === "number" && Number.isFinite(v) ? v : 0);

function asStringList(v: unknown, cap: number): string[] {
  if (!Array.isArray(v)) return [];
  return v.filter((x) => typeof x === "string").slice(0, cap) as string[];
}

function cooldownIsActive(until: unknown): boolean {
  if (typeof until !== "string" || !until) return false;
  const t = Date.parse(until.replace(" ", "T"));
  return Number.isFinite(t) && Date.now() < t;
}

function topBlockersFrom(reasons: unknown, fromReview: unknown): { reason: string; count: number }[] {
  // Prefer the review's pre-computed list; else derive from session blocked_reasons.
  if (Array.isArray(fromReview)) {
    return fromReview
      .filter((b): b is Dict => !!b && typeof b === "object")
      .map((b) => ({ reason: asStr(b.reason) ?? "unknown", count: asInt(b.count) }))
      .slice(0, 5);
  }
  if (reasons && typeof reasons === "object" && !Array.isArray(reasons)) {
    return Object.entries(reasons as Dict)
      .map(([reason, count]) => ({ reason, count: asInt(count) }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 5);
  }
  return [];
}

// ── public loader ───────────────────────────────────────────────────────────────
export async function loadGoldBotStatus(): Promise<GoldBotStatus> {
  const warnings: string[] = [];

  const [session, review, outcomesDoc, safetyState, activeMods, scorecard, cycleLast, worker] =
    await Promise.all([
      readJsonFile("sessions/session_latest.json"),
      readJsonFile("reviews/session_review_latest.json"),
      readJsonFile("trade_outcomes/outcomes_latest.json"),
      readJsonFile("safety/safety_state.json"),
      readJsonFile("learning/active_demo_modifiers.json"),
      readJsonFile("learning/scorecard_latest.json"),
      readJsonlLast("learning/cycles/cycle_events.jsonl"),
      readJsonFile("worker_status.json"),
    ]);

  if (!session) warnings.push("no session report (run a demo session)");
  if (!review) warnings.push("no session review (run run_gold_bot_session_review.py)");
  if (!outcomesDoc) warnings.push("no trade outcomes yet");
  if (!safetyState) warnings.push("no safety state file (no cooldown recorded yet)");
  if (!activeMods) warnings.push("no active learning modifiers");
  if (!scorecard) warnings.push("no scorecard");

  const summary = (outcomesDoc?.summary && typeof outcomesDoc.summary === "object"
    ? (outcomesDoc.summary as Dict)
    : {}) as Dict;

  const modsObj = (activeMods?.modifiers && typeof activeMods.modifiers === "object"
    ? (activeMods.modifiers as Dict)
    : {}) as Dict;
  const modifiers = Object.entries(modsObj)
    .filter(([, e]) => e && typeof e === "object")
    .map(([setup, e]) => ({
      setup,
      confidenceModifier: asInt((e as Dict).confidence_modifier),
    }))
    .slice(0, 8);

  const reviewSafety = (review?.safety_summary && typeof review.safety_summary === "object"
    ? (review.safety_summary as Dict)
    : {}) as Dict;

  return {
    ok: true,
    generatedAt: new Date().toISOString(),
    mode: "local_read_only",
    session: {
      exists: !!session,
      sessionId: asStr(session?.session_id),
      mode: asStr(session?.mode),
      symbol: asStr(session?.symbol),
      riskMode: asStr(session?.risk_mode),
      stopReason: asStr(session?.stop_reason),
      startedAt: asStr(session?.started_at),
      endedAt: asStr(session?.ended_at),
      iterations: asNum(session?.iterations),
      ordersAttempted: asNum(session?.demo_orders_attempted),
      ordersSent: asNum(session?.demo_orders_sent),
      blockedBySafety: asNum(session?.blocked_by_safety_count),
      blockedReasons:
        session?.blocked_reasons && typeof session.blocked_reasons === "object" &&
        !Array.isArray(session.blocked_reasons)
          ? (session.blocked_reasons as Record<string, number>)
          : {},
    },
    review: {
      exists: !!review,
      keyFindings: asStringList(review?.key_findings, 5),
      nextActions: asStringList(review?.next_actions, 5),
    },
    outcomes: {
      exists: !!outcomesDoc,
      wins: asInt(summary.wins),
      losses: asInt(summary.losses),
      breakeven: asInt(summary.breakeven),
      open: asInt(summary.open),
      realizedPnl: asNum(summary.realized_pnl, 0) ?? 0,
    },
    safety: {
      stateExists: !!safetyState,
      cooldownActive: cooldownIsActive(safetyState?.cooldown_until),
      consecutiveLosses: asInt(safetyState?.consecutive_losses),
      topBlockers: topBlockersFrom(session?.blocked_reasons, reviewSafety.top_blockers),
    },
    learning: {
      activeModifiersExists: !!activeMods,
      modifierCount: asNum(activeMods?.active_count, modifiers.length) ?? modifiers.length,
      modifiers,
      scorecardStatus:
        scorecard?.global && typeof scorecard.global === "object"
          ? asStr((scorecard.global as Dict).recommended_status)
          : null,
      latestCycleVerdict: asStr(cycleLast?.event),
    },
    worker: {
      exists: !!worker,
      lastHeartbeat: asStr(worker?.last_heartbeat_at),
      mode: asStr(worker?.mode),
    },
    discord: {
      // Never inspect the webhook env here — report it as deliberately unknown.
      readyToPreview: !!review,
      readyToSend: "unknown_env_not_checked",
      lastReviewExists: !!review,
    },
    warnings,
  };
}
