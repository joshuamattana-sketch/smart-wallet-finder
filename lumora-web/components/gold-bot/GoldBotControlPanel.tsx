"use client";

// LM94B / LM95B — Gold Bot local operations bar.
//
// A COMPACT command toolbar that triggers the LM94A local gateway via
// POST /api/gold-bot/command. It is LOCAL-OWNER tooling: whitelisted actions
// only, no live trading, no order buttons, no free-form command input. The
// heavier actions (guarded demo, Discord send) are gated behind explicit
// confirm checkboxes here AND re-gated by the Python gateway. Secrets/webhook
// values never cross this surface. The result console is collapsible / capped.

import { useCallback, useState } from "react";
import { clsx } from "clsx";
import {
  PlayCircle,
  FileText,
  Eye,
  FlaskConical,
  Send,
  Terminal,
  Copy,
  Check,
  Loader2,
  ChevronDown,
} from "lucide-react";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import {
  runGoldBotCommand,
  type GoldBotAction,
  type GoldBotCommandRequest,
  type GoldBotCommandResponse,
} from "@/lib/gold-bot-command-client";

type RunResult = GoldBotCommandResponse & { at: string };

const STATUS_VARIANT: Record<string, "live" | "warning" | "neutral" | "error"> = {
  success: "live",
  planned: "neutral",
  blocked: "warning",
  failed: "error",
};

// The four always-safe actions (read-only or offline; no demo trades, no network).
const SAFE_ACTIONS: {
  key: GoldBotAction;
  label: string;
  desc: string;
  icon: typeof PlayCircle;
  opts: Partial<GoldBotCommandRequest>;
}[] = [
  { key: "preflight", label: "Preflight", desc: "Read-only GO / NO-GO checklist.", icon: PlayCircle, opts: { execute: true } },
  {
    key: "daily_cycle_offline",
    label: "Offline Cycle",
    desc: "Offline learn + review. No demo trades.",
    icon: FileText,
    opts: { execute: true, includeRealTrades: true },
  },
  { key: "session_review", label: "Build Review", desc: "Build the local session review digest.", icon: FileText, opts: { execute: true } },
  { key: "discord_preview", label: "Discord Preview", desc: "Preview the review. No network, no env.", icon: Eye, opts: { execute: true } },
];

function actionVariant(status?: string): "live" | "warning" | "neutral" | "error" {
  return (status && STATUS_VARIANT[status]) || "neutral";
}

export function GoldBotControlPanel({
  className,
  onAfterRun,
}: {
  className?: string;
  onAfterRun?: () => void;
}) {
  const [running, setRunning] = useState<GoldBotAction | null>(null);
  const [result, setResult] = useState<RunResult | null>(null);
  const [confirmDemo, setConfirmDemo] = useState(false);
  const [confirmDiscord, setConfirmDiscord] = useState(false);
  const [copied, setCopied] = useState(false);
  const [showConsole, setShowConsole] = useState(false);

  const run = useCallback(
    async (action: GoldBotAction, opts: Partial<GoldBotCommandRequest>) => {
      if (running) return;
      setRunning(action);
      setCopied(false);
      const res = await runGoldBotCommand({ action, ...opts });
      setResult({ ...res, at: new Date().toISOString() });
      setShowConsole(true); // surface the outcome; user can collapse it
      setRunning(null);
      onAfterRun?.();
    },
    [running, onAfterRun],
  );

  const copyCommand = useCallback(() => {
    const cmd = result?.command?.join(" ");
    if (!cmd) return;
    void navigator.clipboard?.writeText(cmd).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }, [result]);

  const busy = running !== null;

  // compact toolbar button (primary safe actions)
  const toolbarBtn =
    "num inline-flex items-center gap-1.5 rounded border border-amber-400/[0.18] bg-black/30 px-2.5 py-1 " +
    "text-[10px] font-semibold uppercase tracking-wider text-amber-200/90 transition-colors " +
    "hover:border-amber-400/40 hover:bg-amber-400/[0.06] disabled:cursor-not-allowed disabled:opacity-50 " +
    "focus-visible:outline focus-visible:outline-1 focus-visible:-outline-offset-1 focus-visible:outline-amber-300/60";

  return (
    <section className={clsx("space-y-2", className)} aria-label="Gold Bot local controls">
      <Panel level="focus" className="space-y-2.5">
        {/* header + safety badges (badges replace repeated prose) */}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Terminal className="h-3.5 w-3.5 text-amber-300/90" aria-hidden />
            <h3 className="num text-[11px] font-semibold uppercase tracking-[0.18em] text-amber-200/90">
              Gold Bot Controls
            </h3>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <StatusBadge variant="neutral" size="sm">LOCAL ONLY</StatusBadge>
            <StatusBadge variant="demo" size="sm">DEMO ENV</StatusBadge>
            <StatusBadge variant="neutral" size="sm">LIVE LOCKED</StatusBadge>
            <StatusBadge variant="neutral" size="sm">GATEWAY</StatusBadge>
          </div>
        </div>

        {/* primary actions — one compact toolbar row */}
        <div className="flex flex-wrap gap-1.5">
          {SAFE_ACTIONS.map((a) => {
            const Icon = a.icon;
            const active = running === a.key;
            return (
              <button
                key={a.key}
                type="button"
                data-action={a.key}
                title={a.desc}
                onClick={() => void run(a.key, a.opts)}
                disabled={busy}
                aria-label={a.label}
                className={toolbarBtn}
              >
                {active ? (
                  <Loader2 className="h-3 w-3 animate-spin" aria-hidden />
                ) : (
                  <Icon className="h-3 w-3 text-amber-300/80" aria-hidden />
                )}
                {a.label}
              </button>
            );
          })}
        </div>

        {/* secondary guarded actions — compact, each behind a confirm checkbox */}
        <div className="flex flex-col gap-2 rounded-md border border-amber-400/[0.12] bg-black/20 p-2 lg:flex-row lg:flex-wrap lg:items-center">
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-1.5 text-[9.5px] leading-snug text-lm-text-dim">
              <input
                type="checkbox"
                checked={confirmDemo}
                onChange={(e) => setConfirmDemo(e.target.checked)}
                className="h-3 w-3 accent-rose-400"
              />
              I understand this starts a guarded MT5 demo session
            </label>
            <button
              type="button"
              data-action="daily_cycle_guarded_demo"
              title="5-minute demo-only cycle, max 3 trades, risk scalp, learning modifiers on."
              onClick={() =>
                void run("daily_cycle_guarded_demo", {
                  execute: true,
                  confirmGuardedDemo: true,
                  durationMinutes: 5,
                  maxTrades: 3,
                  riskMode: "scalp",
                  useLearningModifiers: true,
                  includeRealTrades: true,
                })
              }
              disabled={busy || !confirmDemo}
              className={clsx(
                "num inline-flex items-center gap-1.5 rounded border border-rose-400/30 bg-rose-400/[0.08]",
                "px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-rose-200 transition-colors",
                "hover:bg-rose-400/[0.14] disabled:cursor-not-allowed disabled:opacity-40",
              )}
            >
              {running === "daily_cycle_guarded_demo" ? (
                <Loader2 className="h-3 w-3 animate-spin" aria-hidden />
              ) : (
                <FlaskConical className="h-3 w-3" aria-hidden />
              )}
              Guarded Demo 5m
            </button>
          </div>

          <span aria-hidden className="hidden h-4 w-px bg-lm-border/60 lg:block" />

          <div className="flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-1.5 text-[9.5px] leading-snug text-lm-text-dim">
              <input
                type="checkbox"
                checked={confirmDiscord}
                onChange={(e) => setConfirmDiscord(e.target.checked)}
                className="h-3 w-3 accent-amber-400"
              />
              I understand this sends the latest review to Discord
            </label>
            <button
              type="button"
              data-action="discord_send"
              title="Needs LUMORA_GOLD_DISCORD_WEBHOOK_URL env. The app never displays the value."
              onClick={() => void run("discord_send", { execute: true, allowDiscordSend: true })}
              disabled={busy || !confirmDiscord}
              className={clsx(
                "num inline-flex items-center gap-1.5 rounded border border-amber-400/30 bg-amber-400/[0.08]",
                "px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-amber-200 transition-colors",
                "hover:bg-amber-400/[0.14] disabled:cursor-not-allowed disabled:opacity-40",
              )}
            >
              {running === "discord_send" ? (
                <Loader2 className="h-3 w-3 animate-spin" aria-hidden />
              ) : (
                <Send className="h-3 w-3" aria-hidden />
              )}
              Send Discord
            </button>
          </div>
        </div>

        {/* one concise safety line — required phrases, no repetition elsewhere */}
        <p className="text-[9.5px] leading-snug text-lm-muted">
          No live trading. Gateway-whitelisted actions only. Guarded demo still passes safety supervisor + risk gate.{" "}
          Send needs <span className="num">LUMORA_GOLD_DISCORD_WEBHOOK_URL</span> env — the app never displays the value.
        </p>

        {/* collapsible result console (capped height) */}
        {result ? (
          <div className="rounded-md border border-lm-border/60 bg-black/30">
            <button
              type="button"
              onClick={() => setShowConsole((v) => !v)}
              aria-expanded={showConsole}
              aria-label="Toggle result console"
              className="flex w-full items-center justify-between gap-2 px-2 py-1.5 text-left"
            >
              <span className="flex min-w-0 items-center gap-2">
                <span className="num text-[10px] uppercase tracking-wider text-lm-muted">
                  {result.action ?? "result"}
                </span>
                <StatusBadge variant={actionVariant(result.status)} size="sm">
                  {result.ok ? (result.status ?? "ok").toUpperCase() : "API ERROR"}
                </StatusBadge>
                {result.reason || result.error ? (
                  <span className="truncate text-[10px] text-lm-text-dim">
                    {result.error ?? result.reason}
                  </span>
                ) : null}
              </span>
              <span className="flex shrink-0 items-center gap-2">
                <span className="num text-[9px] text-lm-muted/70">
                  {new Date(result.at).toLocaleTimeString("en-GB")}
                </span>
                <ChevronDown
                  className={clsx("h-3.5 w-3.5 text-lm-muted transition-transform", showConsole && "rotate-180")}
                  aria-hidden
                />
              </span>
            </button>

            {showConsole ? (
              <div className="max-h-[220px] space-y-2 overflow-auto border-t border-lm-border/50 p-2">
                {result.command?.length ? (
                  <div className="flex items-start gap-1.5">
                    <code className="num min-w-0 flex-1 break-all rounded bg-black/40 px-2 py-1 text-[9.5px] text-lm-muted">
                      {result.command.join(" ")}
                    </code>
                    <button
                      type="button"
                      onClick={copyCommand}
                      aria-label="Copy command"
                      className="num inline-flex shrink-0 items-center gap-1 rounded border border-lm-border bg-lm-surface-muted px-1.5 py-1 text-[9px] uppercase tracking-wider text-lm-muted hover:text-lm-text"
                    >
                      {copied ? <Check className="h-3 w-3" aria-hidden /> : <Copy className="h-3 w-3" aria-hidden />}
                      {copied ? "Copied" : "Copy"}
                    </button>
                  </div>
                ) : null}
                {result.stdoutTail ? (
                  <pre className="num whitespace-pre-wrap rounded bg-black/40 p-2 text-[9.5px] leading-snug text-lm-muted">
                    {result.stdoutTail}
                  </pre>
                ) : null}
                {result.stderrTail ? (
                  <pre className="num whitespace-pre-wrap rounded bg-rose-950/30 p-2 text-[9.5px] leading-snug text-rose-200/80">
                    {result.stderrTail}
                  </pre>
                ) : null}
                <div className="num flex flex-wrap items-center gap-x-3 gap-y-1 text-[9px] uppercase tracking-wider text-lm-muted/70">
                  <span>{result.runLog ? `run log · ${result.runLog}` : "run log · none"}</span>
                  <span>redactions · {result.redactionsApplied ?? 0}</span>
                </div>
              </div>
            ) : null}
          </div>
        ) : null}
      </Panel>
    </section>
  );
}
