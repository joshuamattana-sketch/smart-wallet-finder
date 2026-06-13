/**
 * lumora-web/app/api/gold-bot/command/route.ts
 * ----------------------------------------------
 * LM94B — Local-only Gold Bot command endpoint.
 *
 * POST /api/gold-bot/command
 *   Bridges the website to the LM94A Python command gateway. It does NOT run
 *   trading logic, shell strings, or arbitrary commands — it validates a small
 *   whitelist + caps, then invokes the EXISTING gateway script with a fixed argv
 *   array (execFile, never a shell). The gateway re-validates everything and is
 *   the final authority on safety (demo session runner + safety supervisor + risk
 *   gate + macro lockout + kill switch). Live trading is impossible by construction.
 *
 * Boundaries:
 *   * No shell. execFile("python", [argv...]) only — no string interpolation.
 *   * No arbitrary actions. Only the 6 whitelisted actions reach the gateway.
 *   * No secrets. The route NEVER reads or returns the Discord webhook value;
 *     discord_send only forwards the allow flag and the gateway checks env
 *     presence itself. Captured output is redacted again here, defensively.
 *   * Local-only guard: non-local hosts get 403 (see isLocalRequest). This is
 *     local-owner tooling — add real auth before any non-local deployment (TODO).
 *
 * Marked dynamic + nodejs so Next never pre-renders it and child_process is allowed.
 */

import { NextResponse } from "next/server";
import { execFile } from "node:child_process";
import path from "node:path";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

// ── whitelist + caps (mirrors the LM94A gateway; the gateway re-checks too) ──────
const ALLOWED_ACTIONS = [
  "preflight",
  "daily_cycle_offline",
  "daily_cycle_guarded_demo",
  "session_review",
  "discord_preview",
  "discord_send",
] as const;
type Action = (typeof ALLOWED_ACTIONS)[number];

const RISK_MODES = ["safe", "balanced", "scalp"] as const;
const DURATION_DEFAULT = 5;
const DURATION_MAX = 15;
const MAX_TRADES_DEFAULT = 3;
const MAX_TRADES_MAX = 5;
const TIMEOUT_MS = 900_000; // 900s, matches the gateway default

const GATEWAY_SCRIPT = "scripts/run_gold_bot_command_gateway.py";

// ── secrets hygiene (defensive; the gateway already redacts) ─────────────────────
const WEBHOOK_RE = /https?:\/\/(?:\w+\.)?discord(?:app)?\.com\/api\/webhooks\/\S+/gi;
function redact(s: string): string {
  return (s ?? "").replace(WEBHOOK_RE, "https://discord.com/api/webhooks/...REDACTED");
}
function tail(s: string, n = 1500): string {
  const r = redact(s ?? "");
  return r.length > n ? r.slice(-n) : r;
}

function clampInt(v: unknown, def: number, min: number, max: number): number {
  const n = typeof v === "number" && Number.isFinite(v) ? Math.floor(v) : def;
  return Math.min(Math.max(n, min), max);
}

// ── local-only guard ─────────────────────────────────────────────────────────────
// Dev server is inherently local-owner tooling. In production, only allow loopback
// hosts/origins. TODO(LM94x): add a real local token / CSRF check before exposing
// this beyond localhost — do NOT rely on this guard alone for a public deployment.
const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "::1", "[::1]", "0.0.0.0"]);
function isLocalRequest(request: Request): boolean {
  if (process.env.NODE_ENV !== "production") return true;
  const host = (request.headers.get("host") ?? "").toLowerCase();
  const hostname = host.replace(/:\d+$/, "");
  if (!LOCAL_HOSTS.has(hostname)) return false;
  const origin = request.headers.get("origin");
  if (origin) {
    try {
      if (!LOCAL_HOSTS.has(new URL(origin).hostname.toLowerCase())) return false;
    } catch {
      return false;
    }
  }
  return true;
}

// ── spawn the gateway (argv array, never a shell), never rejects ─────────────────
interface RunOutput {
  stdout: string;
  stderr: string;
  code: number;
  timedOut: boolean;
  spawnError: string | null;
}
function runGateway(args: string[], cwd: string): Promise<RunOutput> {
  return new Promise((resolve) => {
    execFile(
      "python",
      args,
      { cwd, timeout: TIMEOUT_MS, maxBuffer: 2_000_000, windowsHide: true },
      (error, stdout, stderr) => {
        const err = error as (NodeJS.ErrnoException & { killed?: boolean }) | null;
        const spawnError = err && err.code === "ENOENT"
          ? "python executable not found on PATH"
          : null;
        const timedOut = !!(err && err.killed);
        const code = err && typeof err.code === "number" ? (err.code as number) : err ? 1 : 0;
        resolve({ stdout: stdout ?? "", stderr: stderr ?? "", code, timedOut, spawnError });
      },
    );
  });
}

export async function POST(request: Request) {
  try {
    if (!isLocalRequest(request)) {
      return NextResponse.json(
        { ok: false, error: "forbidden: local-only endpoint" },
        { status: 403, headers: { "Cache-Control": "no-store" } },
      );
    }

    const body = (await request.json().catch(() => null)) as Record<string, unknown> | null;
    if (!body || typeof body !== "object") {
      return NextResponse.json(
        { ok: false, error: "invalid JSON body" },
        { status: 400, headers: { "Cache-Control": "no-store" } },
      );
    }

    const action = String(body.action ?? "");
    if (!(ALLOWED_ACTIONS as readonly string[]).includes(action)) {
      return NextResponse.json(
        { ok: false, error: `unknown action '${action}' — not on the gateway whitelist` },
        { status: 400, headers: { "Cache-Control": "no-store" } },
      );
    }

    // Validate + clamp before we ever spawn. The gateway re-validates as well.
    const execute = body.execute === true; // dry-run unless explicitly true
    const confirmGuardedDemo = body.confirmGuardedDemo === true;
    const allowDiscordSend = body.allowDiscordSend === true;
    const useLearningModifiers = body.useLearningModifiers === true;
    const includeRealTrades = body.includeRealTrades === true;
    const durationMinutes = clampInt(body.durationMinutes, DURATION_DEFAULT, 1, DURATION_MAX);
    const maxTrades = clampInt(body.maxTrades, MAX_TRADES_DEFAULT, 1, MAX_TRADES_MAX);
    const riskMode = (RISK_MODES as readonly string[]).includes(String(body.riskMode))
      ? (body.riskMode as string)
      : "scalp";

    // Build the fixed argv. No caller free-text is interpolated.
    const args: string[] = [GATEWAY_SCRIPT, "--action", action as Action, "--json", "--write-log"];
    if (execute) args.push("--execute");
    if (useLearningModifiers) args.push("--use-learning-modifiers");
    if (includeRealTrades) args.push("--include-real-trades");
    if (confirmGuardedDemo) args.push("--confirm-guarded-demo");
    if (allowDiscordSend) args.push("--allow-discord-send"); // gateway checks env presence itself
    if (action === "daily_cycle_guarded_demo") {
      args.push("--duration-minutes", String(durationMinutes));
      args.push("--max-trades", String(maxTrades));
      args.push("--risk-mode", riskMode);
    }

    // cwd = repo root (one up from lumora-web), so the relative script path resolves.
    const repoRoot = path.resolve(process.cwd(), "..");
    const { stdout, stderr, timedOut, spawnError } = await runGateway(args, repoRoot);

    if (spawnError) {
      return NextResponse.json(
        { ok: false, error: spawnError, command: ["python", ...args] },
        { status: 500, headers: { "Cache-Control": "no-store" } },
      );
    }

    let parsed: Record<string, unknown> | null = null;
    try {
      parsed = JSON.parse(stdout) as Record<string, unknown>;
    } catch {
      parsed = null;
    }

    if (!parsed) {
      return NextResponse.json(
        {
          ok: false,
          error: timedOut ? "gateway timed out (900s)" : "gateway produced no parseable result",
          command: ["python", ...args],
          stdoutTail: tail(stdout),
          stderrTail: tail(stderr),
        },
        { status: 200, headers: { "Cache-Control": "no-store" } },
      );
    }

    const innerErr = [parsed.stderr_tail as string, stderr].filter(Boolean).join("\n");
    return NextResponse.json(
      {
        ok: true,
        accepted: parsed.accepted ?? false,
        status: parsed.status ?? "failed",
        action: parsed.action ?? action,
        reason: (parsed.reason as string) ?? null,
        command: ["python", ...args],
        stdoutTail: tail(String(parsed.stdout_tail ?? "")),
        stderrTail: tail(innerErr),
        warnings: parsed.warnings ?? [],
        runLog: (parsed.generated_files as string[] | undefined)?.[0] ?? null,
        redactionsApplied: parsed.redactions_applied ?? 0,
      },
      { status: 200, headers: { "Cache-Control": "no-store" } },
    );
  } catch (err) {
    return NextResponse.json(
      { ok: false, error: `route error: ${(err as Error)?.message ?? "unknown"}` },
      { status: 500, headers: { "Cache-Control": "no-store" } },
    );
  }
}
