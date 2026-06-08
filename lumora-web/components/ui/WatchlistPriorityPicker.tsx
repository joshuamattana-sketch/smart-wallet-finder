"use client";

import { useEffect, useRef, useState } from "react";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ChevronUp, ChevronDown, X, Plus, Star } from "lucide-react";
import { clsx } from "clsx";
import { useWatchlist } from "@/lib/watchlist";

interface Props {
  className?: string;
  /** Where the popover anchors relative to the trigger. */
  align?: "left" | "right";
}

export function WatchlistPriorityPicker({ className, align = "right" }: Props) {
  const { list, available, add, remove, move, setPrimary } = useWatchlist();
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  // Close on outside click + Escape
  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={wrapRef} className={clsx("relative", className)}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={clsx(
          "lm-segment-btn px-2.5 py-1 text-[11px] font-medium rounded-md border flex items-center gap-1.5",
          open
            ? "border-lm-cyan/40 bg-lm-cyan/5 text-lm-text"
            : "border-lm-border bg-lm-surface text-lm-muted",
        )}
        title="Edit watchlist priority"
      >
        <Star className="h-3 w-3" />
        <span className="uppercase tracking-wide">Watchlist</span>
        <span className="num text-lm-text">{list.length}</span>
      </button>

      {open && (
        <Panel
          flush
          className={clsx(
            "absolute z-30 top-full mt-2 w-72 p-2 shadow-xl shadow-black/40",
            align === "right" ? "right-0" : "left-0",
          )}
        >
          <div className="flex items-center justify-between mb-2 px-1">
            <span className="lm-section-title">Priority</span>
            <span className="text-[9px] uppercase tracking-widest text-lm-muted">
              local only
            </span>
          </div>

          {/* Ordered watchlist rows */}
          <div className="divide-y divide-lm-border/60 rounded border border-lm-border/60 overflow-hidden">
            {list.map((sym, i) => {
              const isPrimary = i === 0;
              return (
                <div key={sym} className="lm-row px-2 py-1.5 flex items-center gap-1">
                  <span className="num text-[10px] text-lm-muted w-4 text-center shrink-0">
                    {i + 1}
                  </span>
                  <span className="num text-[12px] text-lm-text flex-1 truncate">
                    {sym}
                  </span>
                  {isPrimary ? (
                    <StatusBadge variant="live" size="sm">PRIMARY</StatusBadge>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setPrimary(sym)}
                      title="Set as primary"
                      className="lm-segment-btn p-0.5 rounded text-lm-muted"
                    >
                      <Star className="h-3 w-3" />
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => move(sym, "up")}
                    disabled={i === 0}
                    title="Move up"
                    className="lm-segment-btn p-0.5 rounded text-lm-muted disabled:opacity-30"
                  >
                    <ChevronUp className="h-3 w-3" />
                  </button>
                  <button
                    type="button"
                    onClick={() => move(sym, "down")}
                    disabled={i === list.length - 1}
                    title="Move down"
                    className="lm-segment-btn p-0.5 rounded text-lm-muted disabled:opacity-30"
                  >
                    <ChevronDown className="h-3 w-3" />
                  </button>
                  <button
                    type="button"
                    onClick={() => remove(sym)}
                    disabled={list.length <= 1}
                    title={list.length <= 1 ? "At least one symbol required" : "Remove"}
                    className="lm-segment-btn p-0.5 rounded text-lm-muted disabled:opacity-30 hover:text-red-400"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </div>
              );
            })}
          </div>

          {/* Add picker */}
          {available.length > 0 && (
            <div className="mt-2 px-1">
              <span className="text-[9px] uppercase tracking-widest text-lm-muted">
                Add Symbol
              </span>
              <div className="flex flex-wrap gap-1 mt-1.5">
                {available.map((sym) => (
                  <button
                    key={sym}
                    type="button"
                    onClick={() => add(sym)}
                    className="lm-segment-btn px-1.5 py-0.5 rounded border border-lm-border bg-lm-surface text-[10px] num text-lm-muted flex items-center gap-1"
                  >
                    <Plus className="h-2.5 w-2.5" />
                    {sym}
                  </button>
                ))}
              </div>
            </div>
          )}

          <p className="text-[9px] text-lm-muted mt-2 px-1 leading-snug">
            Saved locally · syncs across this browser only
          </p>
        </Panel>
      )}
    </div>
  );
}
