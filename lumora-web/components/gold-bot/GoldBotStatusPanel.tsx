"use client";

// LM91A — Gold Bot local status panel (READ-ONLY).
//
// One compact command-room card that mirrors the local demo artifacts via
// GET /api/gold-bot/status: latest session, safety, learning, outcomes, review
// and Discord-digest readiness. It is STRICTLY read-only — there are NO trading
// controls, no start/stop, no order buttons. The only button reloads status.
// Failed fetch / missing files degrade to a calm "no local data yet" state.

import { useCallback, useEffect, useRef, useState } from "react";
import { clsx } from "clsx";
import { RotateCw } from "lucide-react";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { GoldBotStatus } from "@/lib/gold-bot-status";

type Pill = "ACTIVE" | "BLOCKED" | "MISSING" | "REJECTED" | "ACCEPTED" | "DEMO ONLY" | "READ ONLY";

const PILL_VARIANT: Record<Pill, "live" | "warning" | "neutral" | "demo"> = {
  ACTIVE: "live",
  ACCEPTED: "live",
  BLOCKED: "warning",
  REJECTED: "neutral",
  MISSING: "neutral",
  "DEMO ONLY": "demo",
  "READ ONLY": "neutral",
};

function P({ kind }: { kind: Pill }) {
  return (
    <StatusBadge variant={PILL_VARIANT[kind]} size="sm">
      {kind}
    </StatusBadge>
  );
}

// Tiny labelled cell.
function Cell({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Panel level="subtle" compact className="min-w-0">
      <div className="num mb-1 text-[9px] uppercase tracking-[0.16em] text-lm-muted">{label}</div>
      <div className="space-y-1 text-[11.5px] text-lm-text">{children}</div>
    </Panel>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <span className="text-lm-muted">{k}</span>
      <span className="num truncate text-right">{v}</span>
    </div>
  );
}

const DASH = "—";

export function GoldBotStatusPanel({
  className,
  showReview = true,
  onData,
}: {
  className?: string;
  // LM95A: review can be lifted to a dedicated REPORT section to avoid duplication.
  showReview?: boolean;
  // LM95A: emits the latest status so a parent REPORT card can render from one fetch.
  onData?: (status: GoldBotStatus) => void;
}) {
  const [data, setData] = useState<GoldBotStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [errored, setErrored] = useState(false);

  // Held in a ref so a fresh onData identity each render never re-triggers the fetch.
  const onDataRef = useRef(onData);
  useEffect(() => {
    onDataRef.current = onData;
  }, [onData]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/gold-bot/status", { cache: "no-store" });
      const json = (await res.json()) as GoldBotStatus;
      setData(json);
      setErrored(!json?.ok);
      onDataRef.current?.(json);
    } catch {
      setData(null);
      setErrored(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const s = data?.session;
  const sf = data?.safety;
  const ln = data?.learning;
  const oc = data?.outcomes;
  const rv = data?.review;
  const dc = data?.discord;

  const pnl = oc?.realizedPnl ?? 0;
  const verdict = ln?.latestCycleVerdict?.toLowerCase();

  return (
    <section
      className={clsx("space-y-2", className)}
      aria-label="Gold Bot local status (read-only)"
    >
      <Panel level="focus" className="space-y-3">
        {/* header */}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <h3 className="num text-[11px] font-semibold uppercase tracking-[0.18em] text-amber-200/90">
              Bot Status
            </h3>
            <P kind="READ ONLY" />
            <P kind="DEMO ONLY" />
          </div>
          <button
            type="button"
            onClick={() => void load()}
            disabled={loading}
            aria-label="Refresh status"
            className={clsx(
              "num inline-flex items-center gap-1.5 rounded border border-lm-border bg-lm-surface-muted",
              "px-2 py-1 text-[10px] uppercase tracking-wider text-lm-muted transition-colors",
              "hover:text-lm-text disabled:opacity-50",
            )}
          >
            <RotateCw className={clsx("h-3 w-3", loading && "animate-spin")} aria-hidden />
            Refresh
          </button>
        </div>

        <p className="text-[10.5px] leading-relaxed text-lm-muted">
          Read-only status. No trading controls — this surface only displays local demo artifacts.
          {errored && " (No local data yet; showing a safe empty state.)"}
        </p>

        {/* grid */}
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
          <Cell label="Latest Session">
            {s?.exists ? (
              <>
                <Row
                  k="mode / stop"
                  v={
                    <>
                      {s.mode ?? DASH}{" "}
                      {(s.blockedBySafety ?? 0) > 0 ? <P kind="BLOCKED" /> : null}
                    </>
                  }
                />
                <Row k="stop reason" v={s.stopReason ?? DASH} />
                <Row k="iterations" v={s.iterations ?? DASH} />
                <Row
                  k="orders a/s/blk"
                  v={`${s.ordersAttempted ?? 0}/${s.ordersSent ?? 0}/${s.blockedBySafety ?? 0}`}
                />
              </>
            ) : (
              <Row k="session" v={<P kind="MISSING" />} />
            )}
          </Cell>

          <Cell label="Safety">
            <Row k="state" v={sf?.stateExists ? "recorded" : <P kind="MISSING" />} />
            <Row
              k="cooldown"
              v={sf?.cooldownActive ? <P kind="BLOCKED" /> : "none"}
            />
            <Row k="loss streak" v={sf?.consecutiveLosses ?? 0} />
            <Row
              k="top blockers"
              v={
                sf?.topBlockers?.length
                  ? sf.topBlockers.map((b) => `${b.reason} x${b.count}`).join(", ")
                  : "none"
              }
            />
          </Cell>

          <Cell label="Learning">
            <Row
              k="modifiers"
              v={ln?.activeModifiersExists ? <>{ln.modifierCount} <P kind="ACTIVE" /></> : <P kind="MISSING" />}
            />
            <Row
              k="top"
              v={
                ln?.modifiers?.length
                  ? ln.modifiers
                      .slice(0, 3)
                      .map((m) => `${m.setup} ${m.confidenceModifier > 0 ? "+" : ""}${m.confidenceModifier}`)
                      .join(", ")
                  : DASH
              }
            />
            <Row k="scorecard" v={ln?.scorecardStatus ?? DASH} />
            <Row
              k="latest cycle"
              v={
                verdict === "rejected" ? <P kind="REJECTED" />
                : verdict === "accepted" ? <P kind="ACCEPTED" />
                : (ln?.latestCycleVerdict ?? DASH)
              }
            />
          </Cell>

          <Cell label="Outcomes">
            {oc?.exists ? (
              <>
                <Row k="W/L/BE/open" v={`${oc.wins}/${oc.losses}/${oc.breakeven}/${oc.open}`} />
                <Row
                  k="realized PnL"
                  v={
                    <span
                      className={clsx(
                        pnl > 0 && "text-emerald-400",
                        pnl < 0 && "text-rose-400",
                      )}
                    >
                      {pnl > 0 ? "+" : ""}
                      {pnl}
                    </span>
                  }
                />
              </>
            ) : (
              <Row k="outcomes" v={<>none matched <P kind="DEMO ONLY" /></>} />
            )}
          </Cell>

          {showReview ? (
            <>
              <Cell label="Review — findings">
                {rv?.keyFindings?.length ? (
                  <ul className="space-y-1">
                    {rv.keyFindings.slice(0, 3).map((f, i) => (
                      <li key={i} className="text-[10.5px] leading-snug text-lm-muted">
                        • {f}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <Row k="findings" v={<P kind="MISSING" />} />
                )}
              </Cell>

              <Cell label="Review — next + digest">
                {rv?.nextActions?.length ? (
                  <ul className="space-y-1">
                    {rv.nextActions.slice(0, 2).map((a, i) => (
                      <li key={i} className="text-[10.5px] leading-snug text-lm-muted">
                        → {a}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <Row k="next actions" v={DASH} />
                )}
                <Row k="discord digest" v={dc?.lastReviewExists ? "ready" : <P kind="MISSING" />} />
                <Row k="sender" v="manual / explicit only" />
              </Cell>
            </>
          ) : null}
        </div>

        <p className="num text-[9px] uppercase tracking-[0.14em] text-lm-muted/70">
          source: local files · no MT5 · no orders · no webhook env read ·{" "}
          {data?.generatedAt ? `as of ${new Date(data.generatedAt).toLocaleTimeString("en-GB")}` : "loading…"}
        </p>
      </Panel>
    </section>
  );
}
