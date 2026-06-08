"use client";

import { useCallback, useEffect, useState } from "react";

export const SUPPORTED_SYMBOLS = [
  "BTCUSDT",
  "ETHUSDT",
  "SOLUSDT",
  "HYPEUSDT",
  "XMRUSDT",
  "LINKUSDT",
  "BNBUSDT",
  "DOGEUSDT",
] as const;

export type SupportedSymbol = (typeof SUPPORTED_SYMBOLS)[number];

export const DEFAULT_WATCHLIST: SupportedSymbol[] = ["BTCUSDT", "ETHUSDT", "SOLUSDT"];

const STORAGE_KEY = "lumora.watchlist.v1";
const EVENT_NAME = "lumora-watchlist-change";

const isSupported = (s: string): s is SupportedSymbol =>
  (SUPPORTED_SYMBOLS as readonly string[]).includes(s);

function sanitize(list: readonly string[]): SupportedSymbol[] {
  const seen = new Set<string>();
  const out: SupportedSymbol[] = [];
  for (const s of list) {
    const trimmed = s.trim().toUpperCase();
    if (!isSupported(trimmed) || seen.has(trimmed)) continue;
    seen.add(trimmed);
    out.push(trimmed);
  }
  return out;
}

export function loadWatchlist(): SupportedSymbol[] {
  if (typeof window === "undefined") return [...DEFAULT_WATCHLIST];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [...DEFAULT_WATCHLIST];
    const cleaned = sanitize(raw.split(","));
    return cleaned.length > 0 ? cleaned : [...DEFAULT_WATCHLIST];
  } catch {
    return [...DEFAULT_WATCHLIST];
  }
}

export function saveWatchlist(list: readonly string[]): void {
  if (typeof window === "undefined") return;
  try {
    const cleaned = sanitize(list);
    if (cleaned.length === 0) return; // never persist empty
    window.localStorage.setItem(STORAGE_KEY, cleaned.join(","));
    window.dispatchEvent(new Event(EVENT_NAME));
  } catch {
    /* quota / privacy mode — ignore */
  }
}

export interface UseWatchlistResult {
  list: SupportedSymbol[];
  primary: SupportedSymbol;
  secondaries: SupportedSymbol[];
  available: SupportedSymbol[];
  add: (sym: SupportedSymbol) => void;
  remove: (sym: SupportedSymbol) => void;
  move: (sym: SupportedSymbol, direction: "up" | "down") => void;
  setPrimary: (sym: SupportedSymbol) => void;
}

/**
 * React hook backed by localStorage. SSR-safe: starts with DEFAULT_WATCHLIST
 * then hydrates from storage on the client. Cross-tab and same-tab updates
 * are synced via the `storage` event and a custom `lumora-watchlist-change`
 * event respectively.
 */
export function useWatchlist(): UseWatchlistResult {
  const [list, setList] = useState<SupportedSymbol[]>(DEFAULT_WATCHLIST);

  useEffect(() => {
    setList(loadWatchlist());
    const refresh = () => setList(loadWatchlist());
    window.addEventListener(EVENT_NAME, refresh);
    window.addEventListener("storage", refresh);
    return () => {
      window.removeEventListener(EVENT_NAME, refresh);
      window.removeEventListener("storage", refresh);
    };
  }, []);

  const update = useCallback((next: readonly string[]) => {
    const clean = sanitize(next);
    if (clean.length === 0) return;
    setList(clean);
    saveWatchlist(clean);
  }, []);

  const add = useCallback(
    (sym: SupportedSymbol) => {
      if (list.includes(sym)) return;
      update([...list, sym]);
    },
    [list, update],
  );

  const remove = useCallback(
    (sym: SupportedSymbol) => {
      if (list.length <= 1) return; // always keep at least one symbol
      update(list.filter((s) => s !== sym));
    },
    [list, update],
  );

  const move = useCallback(
    (sym: SupportedSymbol, direction: "up" | "down") => {
      const idx = list.indexOf(sym);
      if (idx < 0) return;
      const j = direction === "up" ? idx - 1 : idx + 1;
      if (j < 0 || j >= list.length) return;
      const next = [...list];
      [next[idx], next[j]] = [next[j], next[idx]];
      update(next);
    },
    [list, update],
  );

  const setPrimary = useCallback(
    (sym: SupportedSymbol) => {
      if (!list.includes(sym) || list[0] === sym) return;
      update([sym, ...list.filter((s) => s !== sym)]);
    },
    [list, update],
  );

  const available = (SUPPORTED_SYMBOLS as readonly SupportedSymbol[]).filter(
    (s) => !list.includes(s),
  );

  return {
    list,
    primary: list[0] ?? DEFAULT_WATCHLIST[0],
    secondaries: list.slice(1),
    available,
    add,
    remove,
    move,
    setPrimary,
  };
}
