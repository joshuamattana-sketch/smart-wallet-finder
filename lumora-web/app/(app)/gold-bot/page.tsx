"use client";

// LM73C — Gold Bot Command Room (visual upgrade over LM73A).
//
// The private wing of Lumora: a three-column command room for the XAUUSD
// paper-trading bot. Center = the chart instrument (the heart of the room),
// left = the bot's analytical brain, right = the engine feed and risk
// permission. Everything is PAPER MODE — no broker keys, no live orders,
// no autonomous execution — and the room says so in three places.
//
// Visual language: dark gold command room. Amber is the bot's identity,
// cyan marks intelligence/live data, violet appears only on journal/memory.
// Atmosphere: gold dawn + fine instrument grid + corner vignette, a slow
// scanner in the status strip, pulse dots and a watching ring on the chart.
// All motion is reduced-motion gated; staged data is labeled as such.

import { useEffect, useState } from "react";
import { PageShell } from "@/components/ui/PageShell";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { GoldChartInstrument } from "@/components/gold-bot/GoldChartInstrument";
import { BotBrainRail } from "@/components/gold-bot/BotBrainRail";
import { CommandFeed } from "@/components/gold-bot/CommandFeed";
import { PlannedModules } from "@/components/gold-bot/PlannedModules";
import { GoldBotStatusPanel } from "@/components/gold-bot/GoldBotStatusPanel";
import { GoldBotControlPanel } from "@/components/gold-bot/GoldBotControlPanel";
import { clsx } from "clsx";
import { Bot, Radar, ShieldHalf } from "lucide-react";

const ROOM_CSS = `
@media (prefers-reduced-motion: no-preference) {
  .lmgb-scan { animation: lmgb-scan 8s ease-in-out infinite; }
  @keyframes lmgb-scan {
    0%, 100% { transform: translateX(-115%); opacity: 0; }
    35%, 65% { opacity: 1; }
    50%      { transform: translateX(15%); }
    99%      { transform: translateX(115%); }
  }
  .lmgb-watch { animation: lmgb-watch 2.4s ease-in-out infinite; }
  @keyframes lmgb-watch {
    0%, 100% { opacity: 1; box-shadow: 0 0 8px 2px rgba(252,211,77,0.45); }
    50%      { opacity: 0.45; box-shadow: 0 0 3px 0 rgba(252,211,77,0.2); }
  }
  .lmgb-iris { animation: lmgb-iris 5s ease-in-out infinite; }
  @keyframes lmgb-iris {
    0%, 100% { opacity: 0.5; transform: scale(1); }
    50%      { opacity: 1; transform: scale(1.12); }
  }
}
`;

// In-room mode tabs — presentation only, no logic behind them yet.
const MODES = ["Watch", "Hunt", "Review"] as const;

// Risk modes — selectable posture, presentation only. Even Aggressive obeys
// the hard limits: the Risk Engine always has final authority, no mode can
// bypass hard stops.
const RISK_MODES = ["Safe", "Balanced", "Aggressive"] as const;

export default function GoldBotPage() {
  const [mode, setMode] = useState<(typeof MODES)[number]>("Watch");
  const [riskMode, setRiskMode] = useState<(typeof RISK_MODES)[number]>("Balanced");
  // Bumped after a control-panel action so the read-only status panel remounts + refetches.
  const [statusNonce, setStatusNonce] = useState(0);

  // Session clock (UTC, display only: London 07–16, New York 12–21).
  const [utcHour, setUtcHour] = useState<number | null>(null);
  useEffect(() => {
    const tick = () => setUtcHour(new Date().getUTCHours());
    tick();
    const id = setInterval(tick, 60_000);
    return () => clearInterval(id);
  }, []);
  const londonOpen = utcHour !== null && utcHour >= 7 && utcHour < 16;
  const nyOpen = utcHour !== null && utcHour >= 12 && utcHour < 21;

  return (
    <PageShell
      title={
        <span className="flex items-center gap-2">
          Gold Bot
          <StatusBadge variant="warning" size="sm">PAPER MODE</StatusBadge>
        </span>
      }
      context="Private XAUUSD command room · paper only · no live execution"
      status={
        <span className="num flex items-center gap-2 text-[11px] uppercase tracking-wide text-amber-300/90">
          <span className="lmgb-watch inline-block h-1.5 w-1.5 rounded-full bg-amber-300" />
          Engine · Watching
        </span>
      }
    >
      <style dangerouslySetInnerHTML={{ __html: ROOM_CSS }} />

      {/* Room atmosphere — gold dawn, fine instrument grid, cyan undercurrent */}
      <div aria-hidden className="pointer-events-none fixed inset-0 -z-10">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_70%_45%_at_60%_-8%,rgba(252,211,77,0.06),transparent_62%)]" />
        <div
          className="absolute inset-0 opacity-[0.3]"
          style={{
            backgroundImage:
              "linear-gradient(rgba(252,211,77,0.015) 1px, transparent 1px), linear-gradient(90deg, rgba(252,211,77,0.015) 1px, transparent 1px)",
            backgroundSize: "64px 64px",
            maskImage: "radial-gradient(ellipse 70% 60% at 50% 30%, black 25%, transparent 75%)",
            WebkitMaskImage: "radial-gradient(ellipse 70% 60% at 50% 30%, black 25%, transparent 75%)",
          }}
        />
        <div className="absolute inset-x-0 bottom-0 h-1/3 bg-[radial-gradient(ellipse_70%_90%_at_35%_115%,rgba(34,211,238,0.04),transparent_70%)]" />
      </div>

      {/* ── Status strip — the room's standing presence ─────────────────────── */}
      <div className="relative overflow-hidden rounded-xl border border-amber-400/[0.14] bg-gradient-to-r from-[#12100a]/95 via-[#0d0c09]/90 to-[#0c0b09]/95 shadow-[0_16px_40px_-20px_rgba(0,0,0,0.9),inset_0_1px_0_rgba(255,255,255,0.05)]">
        <span aria-hidden className="lmgb-scan pointer-events-none absolute inset-y-0 w-1/3 bg-gradient-to-r from-transparent via-amber-300/[0.05] to-transparent" />
        <span aria-hidden className="pointer-events-none absolute inset-y-1.5 left-0 w-[3px] rounded-full bg-amber-400/80 shadow-[0_0_10px_rgba(252,211,77,0.5)]" />

        <div className="relative flex flex-wrap items-center gap-x-5 gap-y-2.5 px-4 py-3">
          {/* identity */}
          <span className="flex items-center gap-3">
            <span className="relative flex h-9 w-9 items-center justify-center rounded-lg border border-amber-400/30 bg-gradient-to-br from-amber-400/[0.18] to-amber-600/[0.05] shadow-[inset_0_1px_0_rgba(255,255,255,0.08),0_0_16px_-5px_rgba(252,211,77,0.6)]">
              <span aria-hidden className="lmgb-iris absolute inset-0 rounded-lg bg-amber-300/[0.06]" />
              <Bot className="relative h-[18px] w-[18px] text-amber-300" strokeWidth={2} />
            </span>
            <span>
              <span className="num block text-[14px] font-bold tracking-[0.08em] text-amber-200 drop-shadow-[0_0_10px_rgba(252,211,77,0.3)]">
                GOLD BOT
              </span>
              <span className="num block text-[9px] uppercase tracking-[0.22em] text-lm-muted">
                XAUUSD · Daytrading Engine
              </span>
            </span>
          </span>

          {/* mode tabs — segmented, presentation only */}
          <span className="flex overflow-hidden rounded-md border border-amber-400/[0.18] bg-black/30 shadow-[inset_0_1px_3px_rgba(0,0,0,0.5)]">
            {MODES.map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                aria-pressed={mode === m}
                className={clsx(
                  "num px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider transition-colors duration-150",
                  "focus-visible:outline focus-visible:outline-1 focus-visible:-outline-offset-1 focus-visible:outline-amber-300/60",
                  mode === m
                    ? "bg-gradient-to-b from-amber-400/[0.2] to-amber-500/[0.08] text-amber-200 shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]"
                    : "text-lm-muted hover:text-amber-200/70",
                )}
              >
                {m}
              </button>
            ))}
          </span>

          {/* risk mode — selectable posture; Risk Engine keeps final authority */}
          <span className="flex items-center gap-1.5">
            <ShieldHalf className="h-3.5 w-3.5 text-amber-400/70" />
            <span className="flex overflow-hidden rounded-md border border-amber-400/[0.18] bg-black/30 shadow-[inset_0_1px_3px_rgba(0,0,0,0.5)]">
              {RISK_MODES.map((m) => (
                <button
                  key={m}
                  onClick={() => setRiskMode(m)}
                  aria-pressed={riskMode === m}
                  title={m === "Aggressive" ? "Riskier paper ideas allowed later — hard stops still apply" : undefined}
                  className={clsx(
                    "num px-2 py-1 text-[9.5px] font-semibold uppercase tracking-wider transition-colors duration-150",
                    "focus-visible:outline focus-visible:outline-1 focus-visible:-outline-offset-1 focus-visible:outline-amber-300/60",
                    riskMode === m
                      ? m === "Aggressive"
                        ? "bg-gradient-to-b from-rose-400/[0.18] to-rose-500/[0.07] text-rose-300 shadow-[inset_0_1px_0_rgba(255,255,255,0.07)]"
                        : "bg-gradient-to-b from-amber-400/[0.2] to-amber-500/[0.08] text-amber-200 shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]"
                      : "text-lm-muted hover:text-amber-200/70",
                  )}
                >
                  {m}
                </button>
              ))}
            </span>
          </span>

          {/* daily limits — goal vs hard stop, always visible */}
          <span className="num flex items-center gap-1.5 text-[9px] uppercase tracking-wider">
            <span className="rounded border border-amber-400/20 bg-amber-400/[0.05] px-1.5 py-0.5 text-amber-300/90">
              TARGET +10% · GOAL
            </span>
            <span className="rounded border border-rose-400/25 bg-rose-400/[0.05] px-1.5 py-0.5 text-rose-400/90">
              MAX LOSS -7% · HARD STOP
            </span>
          </span>

          {/* engine + sessions */}
          <span className="flex items-center gap-2">
            <Radar className="h-3.5 w-3.5 text-amber-400/70" />
            <span className="num text-[10.5px] uppercase tracking-wider text-lm-text-dim">
              Status <span className="font-semibold text-amber-300">WATCHING</span>
            </span>
          </span>
          <span className="num flex items-center gap-3 text-[10px] uppercase tracking-wider">
            <span className={clsx("flex items-center gap-1.5", londonOpen ? "text-emerald-400" : "text-lm-muted")}>
              <span className={clsx("h-1 w-1 rounded-full", londonOpen ? "bg-emerald-400" : "bg-zinc-600")} />
              London
            </span>
            <span className={clsx("flex items-center gap-1.5", nyOpen ? "text-emerald-400" : "text-lm-muted")}>
              <span className={clsx("h-1 w-1 rounded-full", nyOpen ? "bg-emerald-400" : "bg-zinc-600")} />
              New York
            </span>
          </span>

          {/* honesty chip */}
          <span className="num ml-auto rounded border border-amber-400/20 bg-amber-400/[0.04] px-2.5 py-1.5 text-[9.5px] uppercase tracking-wider text-amber-200/80">
            No live execution · no broker connection
          </span>
        </div>
      </div>

      {/* ── The room — brain | instrument | feed ────────────────────────────── */}
      <div className="grid grid-cols-1 items-start gap-3 xl:grid-cols-[290px_minmax(0,1fr)_310px]">
        {/* CENTER first on mobile — the chart is the heart of the room */}
        <div className="order-1 min-w-0 xl:order-2">
          <GoldChartInstrument />
        </div>
        <BotBrainRail className="order-2 xl:order-1" />
        <CommandFeed className="order-3 xl:order-3" />
      </div>

      {/* ── Planned architecture band — limits · funded · execution · review ── */}
      <PlannedModules />

      {/* ── LM94B local control panel (calls the LM94A gateway; no live, no orders) ── */}
      <GoldBotControlPanel onAfterRun={() => setStatusNonce((n) => n + 1)} />

      {/* ── LM91A read-only local status panel (no trading controls) ──────────── */}
      <GoldBotStatusPanel key={statusNonce} />

      {/* ── Command-room footer strip ───────────────────────────────────────── */}
      <div className="relative overflow-hidden rounded-lg border border-amber-400/[0.1] bg-[#0c0b08]/80 px-3.5 py-2">
        <span aria-hidden className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-amber-300/20 to-transparent" />
        <div className="num flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-[9px] uppercase tracking-[0.16em] text-lm-muted">
          <span>
            ROOM <span className="text-amber-300/80">PRIVATE</span> · MODE{" "}
            <span className="text-amber-300/80">{mode.toUpperCase()}</span> · RISK{" "}
            <span className={riskMode === "Aggressive" ? "text-rose-400/90" : "text-amber-300/80"}>
              {riskMode.toUpperCase()}
            </span>{" "}
            · ACCOUNT <span className="text-amber-300/80">PAPER</span>
          </span>
          <span>Risk Engine has final authority · no mode bypasses hard stops · no live trading · no profit guarantees</span>
        </div>
      </div>
    </PageShell>
  );
}
