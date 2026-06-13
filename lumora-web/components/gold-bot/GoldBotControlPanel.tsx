"use client";

// LM94B — Gold Bot local control panel.
//
// A compact command console that triggers the LM94A local gateway via
// POST /api/gold-bot/command. It is LOCAL-OWNER tooling: whitelisted actions
// only, no live trading, no order buttons, no free-form command input. The
// heavier actions (guarded demo, Discord send) are gated behind explicit
// confirm checkboxes here AND re-gated by the Python gateway. Secrets/webhook
// values never cross this surface.

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
  {
    key: "preflight",
    label: "Preflight",
    desc: "Read-only GO / NO-GO checklist.",
    icon: PlayCircle,
    opts: { execute: true },
  },
  {
    key: "daily_cycle_offline",
    label: "Offline Cycle",
    desc: "Offline learn + review. No demo trades.",
    icon: FileText,
    opts: { execute: true, includeRealTrades: true },
  },
  {
    key: "session_review",
    label: "Build Review",
    desc: "Build the local session review digest.",
    icon: FileText,
    opts: { execute: true },
  },
  {
    key: "discord_preview",
    label: "Discord Preview",
    desc: "Preview the review. No network, no env.",
    icon: Eye,
    opts: { execute: true },
  },
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

  const run = useCallback(
    async (action: GoldBotAction, opts: Partial<GoldBotCommandRequest>) => {
      if (running) return;
      setRunning(action);
      setCopied(false);
      const res = await runGoldBotCommand({ action, ...opts });
      setResult({ ...res, at: new Date().toISOString() });
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

  return (
    <section className={clsx("space-y-2", className)} aria-label="Gold Bot local controls">
      <Panel level="focus" className="space-y-3">
        {/* header + safety badges */}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Terminal className="h-4 w-4 text-amber-300/90" aria-hidden />
            <h3 className="num text-[11px] font-semibold uppercase tracking-[0.18em] text-amber-200/90">
              Gold Bot Controls
            </h3>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <StatusBadge variant="neutral" size="sm">LOCAL ONLY</StatusBadge>
            <StatusBadge variant="demo" size="sm">DEMO ENV</StatusBadge>
            <StatusBadge variant="neutral" size="sm">LIVE LOCKED</StatusBadge>
            <StatusBadge variant="neutral" size="sm">GATEWAY WHITELIST</StatusBadge>
          </div>
        </div>

        <p className="text-[10.5px] leading-relaxed text-lm-muted">
          Controls call the local Gateway. No live trading. Guarded demo still passes the
          safety supervisor + risk gate. Whitelisted actions only — no free-form commands.
        </p>

        {/* safe actions */}
        <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
          {SAFE_ACTIONS.map((a) => {
            const Icon = a.icon;
            const active = running === a.key;
            return (
              <button
                key={a.key}
                type="button"
                data-action={a.key}
                onClick={() => void run(a.key, a.opts)}
                disabled={busy}
                aria-label={a.label}
                className={clsx(
                  "num group flex flex-col gap-1 rounded-md border border-amber-400/[0.18] bg-black/30 p-2.5 text-left",
                  "shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] transition-colors duration-150",
                  "hover:border-amber-400/40 hover:bg-amber-400/[0.06] disabled:cursor-not-allowed disabled:opacity-50",
                  "focus-visible:outline focus-visible:outline-1 focus-visible:-outline-offset-1 focus-visible:outline-amber-300/60",
                )}
              >
                <span className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-amber-200/90">
                  {active ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
                  ) : (
                    <Icon className="h-3.5 w-3.5 text-amber-300/80" aria-hidden />
                  )}
                  {a.label}
                </span>
                <span className="text-[9.5px] leading-snug text-lm-muted">{a.desc}</span>
              </button>
            );
          })}
        </div>

        {/* gated actions */}
        <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
          {/* guarded demo */}
          <Panel level="subtle" compact className="space-y-2 border border-rose-400/[0.16]">
            <div className="flex items-center gap-1.5">
              <FlaskConical className="h-3.5 w-3.5 text-rose-300/80" aria-hidden />
              <span className="num text-[10.5px] font-semibold uppercase tracking-wider text-rose-200/90">
                Guarded Demo 5m
              </span>
            </div>
            <p className="text-[9.5px] leading-snug text-lm-muted">
              Starts a 5-minute demo-only cycle, max 3 trades, risk scalp, learning modifiers on.
            </p>
            <label className="flex items-start gap-1.5 text-[9.5px] leading-snug text-lm-text-dim">
              <input
                type="checkbox"
                checked={confirmDemo}
                onChange={(e) => setConfirmDemo(e.target.checked)}
                className="mt-0.5 h-3 w-3 accent-rose-400"
              />
              I understand this starts a guarded MT5 demo session
            </label>
            <button
              type="button"
              data-action="daily_cycle_guarded_demo"
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
              Start Guarded Demo
            </button>
          </Panel>

          {/* discord send */}
          <Panel level="subtle" compact className="space-y-2 border border-amber-400/[0.16]">
            <div className="flex items-center gap-1.5">
              <Send className="h-3.5 w-3.5 text-amber-300/80" aria-hidden />
              <span className="num text-[10.5px] font-semibold uppercase tracking-wider text-amber-200/90">
                Send Discord
              </span>
            </div>
            <p className="text-[9.5px] leading-snug text-lm-muted">
              Requires local <span className="num">LUMORA_GOLD_DISCORD_WEBHOOK_URL</span> env var.
              The app never displays the value.
            </p>
            <label className="flex items-start gap-1.5 text-[9.5px] leading-snug text-lm-text-dim">
              <input
                type="checkbox"
                checked={confirmDiscord}
                onChange={(e) => setConfirmDiscord(e.target.checked)}
                className="mt-0.5 h-3 w-3 accent-amber-400"
              />
              I understand this sends the latest review to Discord
            </label>
            <button
              type="button"
              data-action="discord_send"
              onClick={() =>
                void run("discord_send", { execute: true, allowDiscordSend: true })
              }
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
              Send Review
            </button>
          </Panel>
        </div>

        {/* result console */}
        {result && (
          <Panel level="subtle" compact className="space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="num text-[10px] uppercase tracking-wider text-lm-muted">
                  {result.action ?? "result"}
                </span>
                <StatusBadge variant={actionVariant(result.status)} size="sm">
                  {result.ok ? (result.status ?? "ok").toUpperCase() : "API ERROR"}
                </StatusBadge>
              </div>
              <span className="num text-[9px] text-lm-muted/70">
                {new Date(result.at).toLocaleTimeString("en-GB")}
              </span>
            </div>

            {(result.reason || result.error) && (
              <p className="text-[10.5px] leading-snug text-lm-text-dim">
                {result.error ?? result.reason}
              </p>
            )}

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
              <pre className="num max-h-40 overflow-auto whitespace-pre-wrap rounded bg-black/40 p-2 text-[9.5px] leading-snug text-lm-muted">
                {result.stdoutTail}
              </pre>
            ) : null}
            {result.stderrTail ? (
              <pre className="num max-h-28 overflow-auto whitespace-pre-wrap rounded bg-rose-950/30 p-2 text-[9.5px] leading-snug text-rose-200/80">
                {result.stderrTail}
              </pre>
            ) : null}

            <div className="num flex flex-wrap items-center gap-x-3 gap-y-1 text-[9px] uppercase tracking-wider text-lm-muted/70">
              {result.runLog ? <span>run log · {result.runLog}</span> : <span>run log · none</span>}
              <span>redactions · {result.redactionsApplied ?? 0}</span>
            </div>
          </Panel>
        )}

        <p className="num text-[9px] uppercase tracking-[0.14em] text-lm-muted/70">
          local gateway · whitelisted actions · no live · no order buttons · no webhook value read
        </p>
      </Panel>
    </section>
  );
}
