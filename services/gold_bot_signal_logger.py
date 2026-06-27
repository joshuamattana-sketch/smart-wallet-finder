"""
services/gold_bot_signal_logger.py
----------------------------------
LM87A - Forward signal logger + track-record scorer for the Gold Bot.

Purpose: build an HONEST, auditable LIVE-tail track record. It reuses the exact
no-lookahead Decision Engine adapter the backtest uses (``replay_decide``) but
runs it on the freshly-backfilled tail of stored history instead of replaying
the past. Each CLOSED bar produces one signal record; later runs score still-open
signals against bars that arrived AFTER the signal - never before.

This is the foundation for proving the M15 swing edge LIVE before any product is
built on top of it. It is the same idea as the replay engine, pointed at "now".

NO-LOOKAHEAD CONTRACT (inherited from the replay engine):
  * A decision at bar T sees only bars with time <= T (ReplayClock visible_bars)
    and macro rows with time <= T (MacroSeries as-of join).
  * A signal logged at bar T is scored ONLY against bars with time > T.
  * The most recent bar may still be forming; by default it is NOT decided on
    (``skip_forming_bar=True``) so we never log a signal off a partial candle.

SAFETY (offline / research only):
  * NEVER imports or calls MT5, NEVER sends an order, NO network.
  * Reads local CSVs (refreshed out-of-band by the existing backfill script) and
    writes JSONL + a summary JSON. That is the entire side-effect surface.
  * A preset is an EXIT POLICY only (see gold_bot_signal_presets); it cannot move
    the stop, size a position, or route an order.
"""

from __future__ import annotations

import bisect
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.gold_bot_historical_market_data import (
    DEFAULT_HISTORY_DIR,
    HistoricalBar,
    csv_path,
    read_bars_csv,
)
from services.gold_bot_macro_history import DEFAULT_MACRO_HISTORY_DIR
from services.gold_bot_replay_engine import (
    POINT,
    MacroSeries,
    ReplayClock,
    _first_touch,
    _first_touch_partial,
    replay_decide,
)
from services.gold_bot_signal_presets import (
    DEFAULT_PRESET,
    PRESETS,
    resolve_preset_points,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SIGNALS_DIR = _REPO_ROOT / "data" / "gold_bot" / "signals"

# How many bars after entry to wait for TP/SL before declaring an expiry exit.
# M15: 192 bars ~ 2 trading days, ample room for a swing to resolve.
DEFAULT_MAX_FORWARD_BARS = 192


class SignalLoggerError(Exception):
    """Logger cannot proceed (e.g. no local history)."""


# ── persistence helpers ─────────────────────────────────────────────────────────
def signals_path(signals_dir: str | Path, symbol: str, timeframe: str) -> Path:
    return Path(signals_dir) / f"signals_{symbol}_{timeframe.upper()}.jsonl"


def summary_path(signals_dir: str | Path, symbol: str, timeframe: str) -> Path:
    return Path(signals_dir) / f"signals_{symbol}_{timeframe.upper()}.summary.json"


def read_signals(path: str | Path) -> list[dict]:
    """Read all signal records. Missing file -> []; bad lines skipped."""
    p = Path(path)
    if not p.exists():
        return []
    out: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _write_signals_atomic(path: Path, signals: list[dict]) -> None:
    """Rewrite the whole JSONL atomically (scoring mutates existing records)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for rec in signals:
            fh.write(json.dumps(rec, default=str) + "\n")
    os.replace(tmp, path)


def _write_json_atomic(path: Path, payload: dict) -> None:
    """Write a JSON file atomically so a concurrent cron reader never sees a
    half-written summary (os.replace is atomic on every platform)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    os.replace(tmp, path)


# ── signal logging (decisions on closed bars) ────────────────────────────────────
def _signal_id(symbol: str, timeframe: str, bar_time: datetime) -> str:
    return f"{symbol}_{timeframe.upper()}_{bar_time.strftime('%Y%m%dT%H%M%S')}"


def log_new_signals(
    *, symbol: str, timeframe: str,
    history_dir: str | Path = DEFAULT_HISTORY_DIR,
    macro_history_dir: str | Path = DEFAULT_MACRO_HISTORY_DIR,
    signals_dir: str | Path = DEFAULT_SIGNALS_DIR,
    risk_mode: str = "balanced", warmup_bars: int = 120,
    skip_forming_bar: bool = True, use_trend_filter: bool = False,
    use_mean_reversion: bool = False, now: datetime | None = None,
) -> tuple[list[dict], list[str]]:
    """Decide on every CLOSED bar not yet logged; append new records.

    Idempotent: re-running logs only bars whose time is not already on file, so a
    cron can run it as often as it likes. Returns (new_records, warnings).
    """
    now = now or datetime.now(timezone.utc)
    timeframe = timeframe.upper()
    cp = csv_path(history_dir, symbol, timeframe)
    if not cp.exists():
        raise SignalLoggerError(
            f"no local history at {cp} - run scripts/run_gold_bot_history_backfill.py "
            f"--timeframes {timeframe} first.")
    bars = read_bars_csv(cp, symbol=symbol, timeframe=timeframe)
    if not bars:
        raise SignalLoggerError(f"history file {cp} has no rows.")
    bars = sorted(bars, key=lambda b: b.time)

    # The newest bar may still be forming; exclude it from decision-making.
    decide_bars = bars[:-1] if (skip_forming_bar and len(bars) > 1) else bars

    spath = signals_path(signals_dir, symbol, timeframe)
    existing = read_signals(spath)
    logged_times = {r["bar_time"] for r in existing}

    macro = MacroSeries.load(macro_history_dir, "D1")
    warnings: list[str] = list(macro.warnings)

    # Start the clock near the tail when we already have history, else from warmup.
    from_time = None
    if logged_times:
        try:
            from_time = max(datetime.fromisoformat(t) for t in logged_times)
        except ValueError:
            from_time = None
    clock = ReplayClock(decide_bars, warmup_bars=warmup_bars, max_bars=None,
                        from_time=from_time)

    new_records: list[dict] = []
    for step in clock:
        bar_time_iso = step.time.isoformat()
        if bar_time_iso in logged_times:
            continue
        snapshot = macro.snapshot(step.time)
        idea = replay_decide(step, snapshot, symbol=symbol, timeframe=timeframe,
                             risk_mode=risk_mode, learning_modifiers=None,
                             learning_mode="off", use_trend_filter=use_trend_filter,
                             use_mean_reversion=use_mean_reversion)
        is_trade = idea.decision in ("LONG", "SHORT")
        rec = {
            "signal_id": _signal_id(symbol, timeframe, step.time),
            "logged_at": now.isoformat(),
            "bar_time": bar_time_iso,
            "symbol": symbol, "timeframe": timeframe, "risk_mode": risk_mode,
            "decision": idea.decision, "strategy": idea.strategy,
            "confidence": idea.confidence,
            "entry_reference_price": idea.entry_reference_price,
            "entry_spread_points": step.current_bar.spread,
            "sl_points": idea.sl_points, "tp_points": idea.tp_points,
            "session": idea.session, "regime": idea.regime,
            "reasons": idea.reasons, "blockers": idea.blockers,
            "warnings": idea.warnings,
            "macro": {k: snapshot.get(k) for k in ("dxy_bias", "yields_bias",
                                                   "vix_bias", "risk_bias")},
            "status": "open" if is_trade else "no_trade",
            "scored_at": None, "bars_forward": 0, "outcomes": {},
            "no_lookahead": True, "calls_mt5": False,
        }
        new_records.append(rec)
        logged_times.add(bar_time_iso)

    if new_records:
        _write_signals_atomic(spath, existing + new_records)
    return new_records, warnings


# ── forward scoring (only bars after the signal) ─────────────────────────────────
def _score_time_exit(window: list[HistoricalBar], direction: str, entry: float,
                     sl_points: int | None) -> tuple[float, str]:
    """Hold to the end of ``window`` then exit at market. If ``sl_points`` is set
    and the stop is touched first, exit there. Returns (gross_points, reason)."""
    if sl_points is not None and sl_points > 0:
        sl = entry - sl_points * POINT if direction == "LONG" else entry + sl_points * POINT
        for f in window:
            hit_sl = f.low <= sl if direction == "LONG" else f.high >= sl
            if hit_sl:
                return -float(sl_points), "sl"
    if not window:
        return 0.0, "expired"
    last = window[-1].close
    gross = (last - entry) / POINT if direction == "LONG" else (entry - last) / POINT
    return gross, "hold"


def _classify(net: float, exit_reason: str) -> str:
    if net > 0:
        return "win"
    if net < 0:
        return "loss"
    return "neutral"


def _score_one_preset(preset_name: str, direction: str, entry: float,
                      sl_points: int, future: list[HistoricalBar],
                      cost_points: float = 0.0) -> dict:
    """Score one signal under one preset using ONLY post-entry bars.

    ``cost_points`` is the round-trip trading cost (spread + commission) in
    points, subtracted once from the gross result so realized P&L is NET — what
    the trader actually keeps after costs.
    """
    preset = PRESETS[preset_name]

    # Time / swing exit: hold N bars then exit at market (optional SL floor).
    if preset.hold_bars is not None:
        sl_eff = None if preset.sl_r is None else int(round(sl_points * preset.sl_r))
        window = future[:preset.hold_bars]
        gross, exit_reason = _score_time_exit(window, direction, entry, sl_eff)
        net = gross - cost_points
        return {
            "outcome": _classify(net, exit_reason),
            "realized_points": round(net, 1),
            "exit_reason": exit_reason,
            "tp1_points": None,
            "tp_points": None,
            "hold_bars": preset.hold_bars,
            "sl_points": sl_eff,
            "cost_points": round(cost_points, 1),
        }

    tp1_points, tp_points = resolve_preset_points(preset, sl_points)
    if tp1_points is not None:
        detail, gross = _first_touch_partial(
            future, entry, direction, sl_points, tp1_points, tp_points,
            POINT, preset.partial_ratio)
        if gross is None:
            gross = 0.0
        exit_reason = detail
    else:
        ft = _first_touch(future, entry, direction, sl_points, tp_points, POINT)
        if ft == "tp":
            gross, exit_reason = float(tp_points), "tp"
        elif ft == "sl":
            gross, exit_reason = -float(sl_points), "sl"
        else:  # neither level touched within the window -> mark-to-market exit
            if future:
                last = future[-1].close
                gross = ((last - entry) / POINT if direction == "LONG"
                         else (entry - last) / POINT)
            else:
                gross = 0.0
            exit_reason = "expired"
    net = gross - cost_points
    return {
        "outcome": _classify(net, exit_reason),
        "realized_points": round(net, 1),
        "exit_reason": exit_reason,
        "tp1_points": tp1_points,
        "tp_points": tp_points,
        "hold_bars": None,
        "sl_points": sl_points,
        "cost_points": round(cost_points, 1),
    }


def _resolved(direction: str, entry: float, sl_points: int, max_tp_points: int,
              future: list[HistoricalBar], max_forward_bars: int,
              max_hold_bars: int) -> bool:
    """True once EVERY preset can produce a final outcome — only then do we close
    the signal and score them together. A bracket preset finalizes when its TP/SL
    is touched; a time-exit preset needs ``hold_bars`` bars to elapse. So we close
    when the largest bracket TP or the SL is touched AND enough bars exist for the
    longest hold, or when the hard expiry horizon is reached."""
    if len(future) >= max_forward_bars:
        return True
    if len(future) < max_hold_bars:
        return False  # a swing/time-exit preset has not finished holding yet
    ft = _first_touch(future, entry, direction, sl_points, max_tp_points, POINT)
    return ft in ("tp", "sl")


def score_open_signals(
    *, symbol: str, timeframe: str,
    history_dir: str | Path = DEFAULT_HISTORY_DIR,
    signals_dir: str | Path = DEFAULT_SIGNALS_DIR,
    max_forward_bars: int = DEFAULT_MAX_FORWARD_BARS,
    cost_points: float = 0.0, spread_cost: bool = False,
    now: datetime | None = None,
) -> tuple[int, list[str]]:
    """Score every still-open signal against bars that arrived after it.

    A signal is closed only once SL / the largest preset TP is touched or the
    expiry horizon passes; otherwise it stays open for a future run. Realized
    P&L is NET of round-trip cost: ``cost_points`` (flat commission) plus, when
    ``spread_cost`` is set, the entry bar's real spread. Returns
    (count_closed_this_run, warnings).
    """
    now = now or datetime.now(timezone.utc)
    timeframe = timeframe.upper()
    spath = signals_path(signals_dir, symbol, timeframe)
    signals = read_signals(spath)
    if not signals:
        return 0, []
    cp = csv_path(history_dir, symbol, timeframe)
    bars = sorted(read_bars_csv(cp, symbol=symbol, timeframe=timeframe),
                  key=lambda b: b.time)
    if not bars:
        return 0, [f"history file {cp} has no rows; cannot score."]
    bar_times = [b.time for b in bars]

    # Bracket presets resolve at their TP; the longest hold preset needs its bars.
    max_tp_r = max((p.tp_r for p in PRESETS.values() if p.hold_bars is None), default=0.0)
    max_hold_bars = max((p.hold_bars for p in PRESETS.values()
                         if p.hold_bars is not None), default=0)
    closed = 0
    warnings: list[str] = []
    changed = False
    for rec in signals:
        if rec.get("status") != "open":
            continue
        direction = rec["decision"]
        entry = rec.get("entry_reference_price")
        sl_points = rec.get("sl_points")
        if entry is None or not sl_points or sl_points <= 0:
            rec["status"] = "void"
            rec["scored_at"] = now.isoformat()
            rec["outcomes"] = {}
            warnings.append(f"{rec['signal_id']}: missing entry/SL; voided.")
            changed = True
            continue
        try:
            bar_time = datetime.fromisoformat(rec["bar_time"])
        except ValueError:
            continue
        start = bisect.bisect_right(bar_times, bar_time)  # strictly after entry bar
        future = bars[start:]
        rec["bars_forward"] = len(future)
        if not future:
            continue  # nothing arrived after the entry bar yet
        max_tp_points = int(round(sl_points * max_tp_r))
        if not _resolved(direction, entry, sl_points, max_tp_points, future,
                         max_forward_bars, max_hold_bars):
            continue  # still running; revisit next run
        window = future[:max_forward_bars]
        entry_spread = rec.get("entry_spread_points")
        sig_cost = cost_points + (float(entry_spread)
                                  if (spread_cost and entry_spread) else 0.0)
        rec["outcomes"] = {name: _score_one_preset(name, direction, float(entry),
                                                    int(sl_points), window, sig_cost)
                           for name in PRESETS}
        rec["scored_at"] = now.isoformat()
        rec["bars_forward"] = len(window)
        rec["status"] = "closed"
        closed += 1
        changed = True

    if changed:
        _write_signals_atomic(spath, signals)
    return closed, warnings


# ── track record (aggregate per preset) ─────────────────────────────────────────
def build_track_record(signals: list[dict]) -> dict:
    """Aggregate closed signals into a per-preset performance summary."""
    closed = [s for s in signals if s.get("status") == "closed"]
    per_preset: dict[str, dict] = {}
    for name in PRESETS:
        wins = losses = neutral = 0
        total = 0.0
        for s in closed:
            o = s.get("outcomes", {}).get(name)
            if not o:
                continue
            total += o.get("realized_points", 0.0)
            oc = o.get("outcome")
            if oc == "win":
                wins += 1
            elif oc == "loss":
                losses += 1
            else:
                neutral += 1
        n = wins + losses + neutral
        per_preset[name] = {
            "trades": n, "wins": wins, "losses": losses, "neutral": neutral,
            "win_rate_pct": round(100.0 * wins / n, 1) if n else None,
            "total_realized_points": round(total, 1),
            "expectancy_points": round(total / n, 1) if n else None,
        }
    statuses: dict[str, int] = {}
    for s in signals:
        st = s.get("status", "unknown")
        statuses[st] = statuses.get(st, 0) + 1
    return {
        "total_signals": len(signals),
        "by_status": statuses,
        "closed_trades": len(closed),
        "per_preset": per_preset,
        "presets": {name: {"label": p.label, "description": p.description,
                           "tp_r": p.tp_r, "tp1_r": p.tp1_r,
                           "partial_ratio": p.partial_ratio}
                    for name, p in PRESETS.items()},
        "default_preset": DEFAULT_PRESET,
    }


# ── orchestrator ─────────────────────────────────────────────────────────────────
@dataclass
class SignalLoggerResult:
    summary: dict
    signals_path: Path
    summary_path: Path
    new_signals: int
    closed_signals: int
    warnings: list[str] = field(default_factory=list)


def run_signal_logger(
    *, symbol: str = "XAUUSD", timeframe: str = "M15",
    history_dir: str | Path = DEFAULT_HISTORY_DIR,
    macro_history_dir: str | Path = DEFAULT_MACRO_HISTORY_DIR,
    signals_dir: str | Path = DEFAULT_SIGNALS_DIR,
    risk_mode: str = "balanced", warmup_bars: int = 120,
    skip_forming_bar: bool = True, use_trend_filter: bool = False,
    use_mean_reversion: bool = False,
    max_forward_bars: int = DEFAULT_MAX_FORWARD_BARS,
    cost_points: float = 0.0, spread_cost: bool = False,
    now: datetime | None = None,
) -> SignalLoggerResult:
    """Log new closed-bar signals, score open ones, regenerate the summary.

    Safe to run on a schedule (idempotent). Offline: reads local history,
    writes JSONL + summary JSON. Never calls MT5, never sends an order.
    ``cost_points``/``spread_cost`` make the track record NET of trading cost.
    """
    now = now or datetime.now(timezone.utc)
    timeframe = timeframe.upper()
    new_records, w1 = log_new_signals(
        symbol=symbol, timeframe=timeframe, history_dir=history_dir,
        macro_history_dir=macro_history_dir, signals_dir=signals_dir,
        risk_mode=risk_mode, warmup_bars=warmup_bars,
        skip_forming_bar=skip_forming_bar, use_trend_filter=use_trend_filter,
        use_mean_reversion=use_mean_reversion, now=now)
    closed, w2 = score_open_signals(
        symbol=symbol, timeframe=timeframe, history_dir=history_dir,
        signals_dir=signals_dir, max_forward_bars=max_forward_bars,
        cost_points=cost_points, spread_cost=spread_cost, now=now)

    spath = signals_path(signals_dir, symbol, timeframe)
    sumpath = summary_path(signals_dir, symbol, timeframe)
    all_signals = read_signals(spath)
    track = build_track_record(all_signals)
    summary = {
        "symbol": symbol, "timeframe": timeframe, "risk_mode": risk_mode,
        "warmup_bars": warmup_bars, "skip_forming_bar": skip_forming_bar,
        "use_trend_filter": use_trend_filter, "use_mean_reversion": use_mean_reversion,
        "max_forward_bars": max_forward_bars,
        "cost_points": round(cost_points, 1), "spread_cost": spread_cost,
        "expectancy_basis": "net_of_cost" if (cost_points or spread_cost) else "gross",
        "new_signals_this_run": len(new_records),
        "closed_this_run": closed,
        "no_lookahead": True, "calls_mt5": False,
        "generated_at": now.isoformat(),
        "warnings": w1 + w2,
        **track,
    }
    _write_json_atomic(sumpath, summary)
    return SignalLoggerResult(
        summary=summary, signals_path=spath, summary_path=sumpath,
        new_signals=len(new_records), closed_signals=closed,
        warnings=w1 + w2)
