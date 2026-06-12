"use client";

// components/gold-bot/PlannedModules.tsx
// LM73D — the planned-architecture band under the command room.
//
// Four compact modules that state where the bot is going without pretending
// any of it exists yet: daily risk limits (the +10% goal vs the -7% hard
// stop), funded-account guardrails, execution targets (live adapter visibly
// LOCKED), and the Discord daily-review system. Everything here is contract
// copy — no integrations, no broker logic, no webhooks.

import { clsx } from "clsx";
import { Target, Landmark, PlugZap, MessageSquareText, Lock } from "lucide-react";
import type { LucideIcon } from "lucide-react";

function Module({
  icon: Icon,
  title,
  tag,
  tagClass,
  children,
}: {
  icon: LucideIcon;
  title: string;
  tag: string;
  tagClass?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="overflow-hidden rounded-lg bg-[#0d0c09]/80 ring-1 ring-amber-400/[0.08] shadow-[inset_0_1px_0_rgba(255,255,255,0.03),0_10px_26px_-14px_rgba(0,0,0,0.8)]">
      <div className="relative flex items-center justify-between gap-2 px-3 py-2">
        <span className="flex items-center gap-1.5">
          <Icon className="h-3 w-3 text-amber-400/70" />
          <span className="num text-[9.5px] font-semibold uppercase tracking-[0.18em] text-amber-200/80">
            {title}
          </span>
        </span>
        <span className={clsx("num text-[8px] uppercase tracking-wider", tagClass ?? "text-lm-muted")}>
          {tag}
        </span>
        <span aria-hidden className="pointer-events-none absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-amber-400/25 via-white/[0.04] to-transparent" />
      </div>
      {children}
    </section>
  );
}

function Row({ label, value, valueClass }: { label: string; value: string; valueClass?: string }) {
  return (
    <div className="flex items-center justify-between gap-3 px-3 py-[5px] transition-colors duration-150 hover:bg-amber-400/[0.02]">
      <span className="text-[10px] leading-snug text-lm-text-dim">{label}</span>
      <span className={clsx("num shrink-0 text-[9.5px] font-semibold", valueClass ?? "text-lm-text")}>
        {value}
      </span>
    </div>
  );
}

export function PlannedModules({ className }: { className?: string }) {
  return (
    <div className={clsx("grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4", className)}>

      {/* Daily targets / hard limits */}
      <Module icon={Target} title="Daily Limits" tag="enforced" tagClass="text-emerald-400/80">
        <div className="divide-y divide-white/[0.04] py-1">
          <Row label="Daily target" value="+10% · aspirational" valueClass="text-amber-300/90" />
          <Row label="Hard max daily loss" value="-7% · hard stop" valueClass="text-rose-400" />
          <Row label="On hard stop" value="flat for the day" />
          <Row label="Chasing the target" value="never" valueClass="text-rose-400/80" />
        </div>
        <p className="border-t border-white/[0.04] px-3 py-1.5 text-[9px] leading-snug text-lm-muted">
          +10% is a benchmark, not a promise. The engine will not overtrade to reach it.
        </p>
      </Module>

      {/* Funded account guardrails */}
      <Module icon={Landmark} title="Funded Guardrails" tag="planned" tagClass="text-amber-300/70">
        <div className="divide-y divide-white/[0.04] py-1">
          <Row label="Daily / total drawdown caps" value="per profile" />
          <Row label="Martingale · revenge trading" value="banned" valueClass="text-rose-400" />
          <Row label="News restrictions · max open risk" value="profile rule" />
          <Row label="Consistency rules" value="profile rule" />
        </div>
        <p className="num border-t border-white/[0.04] px-3 py-1.5 text-[8.5px] uppercase tracking-wider text-lm-muted">
          Profiles: FTMO · The5ers · Alpha Capital · Custom — all planned
        </p>
      </Module>

      {/* Execution targets */}
      <Module icon={PlugZap} title="Execution Targets" tag="paper first" tagClass="text-amber-300/70">
        <div className="divide-y divide-white/[0.04] py-1">
          <Row label="Lumora Paper Engine" value="active" valueClass="text-emerald-400" />
          <Row label="TradingView alerts / webhook" value="planned" valueClass="text-lm-muted" />
          <Row label="MetaTrader 5 demo adapter" value="planned" valueClass="text-lm-muted" />
          <Row label="Funded account safe mode" value="planned" valueClass="text-lm-muted" />
        </div>
        <p className="flex items-center gap-1.5 border-t border-rose-400/[0.12] bg-rose-400/[0.03] px-3 py-1.5">
          <Lock className="h-2.5 w-2.5 shrink-0 text-rose-400" />
          <span className="num text-[8.5px] uppercase tracking-wider text-rose-400/90">
            Live execution adapter · locked
          </span>
        </p>
      </Module>

      {/* Discord daily review */}
      <Module icon={MessageSquareText} title="Discord Review" tag="planned" tagClass="text-amber-300/70">
        <div className="px-3 py-2">
          <p className="text-[10px] leading-snug text-lm-text-dim">
            One report per session: paper PnL, trades taken vs skipped (with reasons), best and
            worst setup, mistakes detected, lesson learned, tomorrow&apos;s watchlist.
          </p>
          <p className="mt-1.5 text-[9.5px] leading-snug text-lm-muted">
            Includes a risk warning when behavior was poor — the review never flatters the engine.
          </p>
        </div>
        <p className="num border-t border-white/[0.04] px-3 py-1.5 text-[8.5px] uppercase tracking-wider text-lm-muted">
          No webhook wired yet · report format staged
        </p>
      </Module>
    </div>
  );
}
