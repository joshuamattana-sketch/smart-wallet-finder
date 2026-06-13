// LM95B — Gold Bot compact status strip (presentation only).
//
// A single-line telemetry summary that sits above the command room so the chart
// stays high on the page. It is PURE: it takes an already-fetched status object
// (lifted from the read-only GoldBotStatusPanel) and renders chips — no fetch, no
// hooks, no trading controls. The full detail lives in the collapsible panel below.

import { clsx } from "clsx";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { GoldBotStatus } from "@/lib/gold-bot-status";

function Chip({ label, value, warn }: { label: string; value: React.ReactNode; warn?: boolean }) {
  return (
    <span className="flex items-baseline gap-1">
      <span className="text-[9px] uppercase tracking-wider text-lm-muted/70">{label}</span>
      <span className={clsx("text-[10.5px]", warn ? "text-amber-300" : "text-lm-text")}>{value}</span>
    </span>
  );
}

export function GoldBotStatusStrip({
  status,
  className,
}: {
  status: GoldBotStatus | null;
  className?: string;
}) {
  if (!status) {
    return (
      <div
        className={clsx(
          "num rounded-md border border-lm-border/60 bg-black/20 px-3 py-1.5 text-[10px] uppercase tracking-wider text-lm-muted/70",
          className,
        )}
      >
        bot status · loading…
      </div>
    );
  }

  const s = status.session;
  const sf = status.safety;
  const ln = status.learning;
  const oc = status.outcomes;
  const blocker = sf?.topBlockers?.[0];
  const verdict = ln?.latestCycleVerdict?.toLowerCase();
  const blockedOrders = (s?.blockedBySafety ?? 0) > 0;

  return (
    <div
      className={clsx(
        "num flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-md border border-cyan-400/[0.14] bg-black/20 px-3 py-1.5",
        className,
      )}
    >
      <span className="text-[9px] uppercase tracking-[0.18em] text-cyan-300/80">BOT STATUS</span>
      <Chip label="session" value={s?.exists ? (s.mode ?? "—") : "none"} />
      {s?.exists && (s.blockedBySafety ?? 0) > 0 ? <StatusBadge variant="warning" size="sm">BLOCKED</StatusBadge> : null}
      {s?.stopReason ? <Chip label="stop" value={s.stopReason} /> : null}
      <Chip
        label="orders a/s/blk"
        value={`${s?.ordersAttempted ?? 0}/${s?.ordersSent ?? 0}/${s?.blockedBySafety ?? 0}`}
        warn={blockedOrders}
      />
      <Chip
        label="safety"
        value={blocker ? `${blocker.reason} ×${blocker.count}` : sf?.cooldownActive ? "cooldown" : "clear"}
        warn={!!blocker || !!sf?.cooldownActive}
      />
      <Chip label="mods" value={ln?.activeModifiersExists ? String(ln.modifierCount ?? 0) : "0"} />
      {verdict === "rejected" ? (
        <StatusBadge variant="neutral" size="sm">REJECTED</StatusBadge>
      ) : verdict === "accepted" ? (
        <StatusBadge variant="live" size="sm">ACCEPTED</StatusBadge>
      ) : null}
      <Chip
        label="W/L/BE"
        value={oc?.exists ? `${oc.wins}/${oc.losses}/${oc.breakeven}` : "—"}
      />
    </div>
  );
}
