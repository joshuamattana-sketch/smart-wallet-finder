/**
 * lumora-web/lib/gold-bot-command-client.ts
 * -------------------------------------------
 * LM94B — Tiny typed client for the local Gold Bot command gateway.
 *
 * Wraps POST /api/gold-bot/command. The browser only ever sends a whitelisted
 * action + safe flags; the API route + the LM94A Python gateway both re-validate.
 * No secrets, no webhook values, no arbitrary command strings cross this boundary.
 */

export const GOLD_BOT_ACTIONS = [
  "preflight",
  "daily_cycle_offline",
  "daily_cycle_guarded_demo",
  "session_review",
  "discord_preview",
  "discord_send",
] as const;

export type GoldBotAction = (typeof GOLD_BOT_ACTIONS)[number];
export type GoldBotRiskMode = "safe" | "balanced" | "scalp";

export interface GoldBotCommandRequest {
  action: GoldBotAction;
  execute?: boolean;
  confirmGuardedDemo?: boolean;
  allowDiscordSend?: boolean;
  durationMinutes?: number;
  maxTrades?: number;
  riskMode?: GoldBotRiskMode;
  useLearningModifiers?: boolean;
  includeRealTrades?: boolean;
}

export interface GoldBotCommandResponse {
  ok: boolean;
  accepted?: boolean;
  status?: "planned" | "success" | "failed" | "blocked";
  action?: string;
  reason?: string | null;
  command?: string[];
  stdoutTail?: string;
  stderrTail?: string;
  warnings?: string[];
  runLog?: string | null;
  redactionsApplied?: number;
  error?: string;
}

export async function runGoldBotCommand(
  req: GoldBotCommandRequest,
): Promise<GoldBotCommandResponse> {
  try {
    const res = await fetch("/api/gold-bot/command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
      body: JSON.stringify(req),
    });
    return (await res.json()) as GoldBotCommandResponse;
  } catch (err) {
    return { ok: false, error: (err as Error)?.message ?? "request failed" };
  }
}
