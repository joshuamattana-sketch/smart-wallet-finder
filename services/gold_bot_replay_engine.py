"""
services/gold_bot_replay_engine.py
-----------------------------------
LM85A - No-lookahead historical replay / backtest engine for the Gold Bot.

Streams stored XAUUSD history (LM84A) one bar at a time, aligns macro history
(LM84B DXY/US10Y/US02Y/VIX) AS-OF the current bar only, runs the existing
Decision Engine V2 through a thin adapter (NO MT5, NO orders), then scores each
decision against FUTURE bars - but only after the decision is already recorded.

NO-LOOKAHEAD CONTRACT (enforced in code + tests):
  * At step i the decision sees only bars with time <= current_bar.time
    (``ReplayStep.visible_bars``) and macro rows with time <= current_bar.time
    (``MacroSeries.snapshot``).
  * Forward scoring reads bars STRICTLY AFTER i (``bars[i+1:]``) and is called
    only after ``idea`` has been produced and journaled.
This separation is deliberate and load-bearing - keep decision inputs and
forward-scoring inputs apart.

Pure + offline: never imports/calls MT5, never sends orders, no network. Reads
local CSVs only; unit tests use temp dirs.
"""

from __future__ import annotations

import bisect
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from services.gold_bot_decision_engine import decide
from services.gold_bot_historical_market_data import (
    DEFAULT_HISTORY_DIR,
    HistoricalBar,
    csv_path,
    read_bars_csv,
)
from services.gold_bot_macro_context import build_macro_context
from services.gold_bot_macro_history import (
    DEFAULT_MACRO_HISTORY_DIR,
    MACRO_INSTRUMENTS,
    macro_csv_path,
    read_macro_csv,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPLAY_DIR = _REPO_ROOT / "data" / "gold_bot" / "replay"
POINT = 0.01
DEFAULT_HORIZONS = (5, 15, 30)
_BIAS_EPS = 0.001


# ── ReplayClock ────────────────────────────────────────────────────────────────
@dataclass
class ReplayStep:
    index: int                       # absolute index into the full sorted series
    step: int                        # 0-based counter among scored steps
    time: datetime                   # current bar time (the "now" of this step)
    current_bar: HistoricalBar
    visible_bars: list[HistoricalBar]  # bars with time <= current time (NO future)

    @property
    def visible_count(self) -> int:
        return len(self.visible_bars)


class ReplayClock:
    """
    Iterates stored bars in chronological order, exposing only past+current bars
    at each step. ``warmup_bars`` history must exist before the first scored step
    (the decision engine needs enough lookback). ``from_time``/``to_time`` bound
    the scored range; ``max_bars`` caps how many steps run.
    """

    def __init__(self, bars: list[HistoricalBar], *, warmup_bars: int = 120,
                 max_bars: int | None = None, from_time: datetime | None = None,
                 to_time: datetime | None = None, visible_window: int | None = None):
        self.bars = sorted(bars, key=lambda b: b.time)
        self.warmup_bars = max(0, warmup_bars)
        self.max_bars = max_bars
        self.from_time = from_time
        self.to_time = to_time
        # Window of past bars handed to the engine each step (bounded for perf;
        # always ends at the current bar so it can never include the future).
        self.visible_window = visible_window or max(self.warmup_bars, 256)

    def _first_scored_index(self) -> int:
        idx = self.warmup_bars
        if self.from_time is not None:
            while idx < len(self.bars) and self.bars[idx].time < self.from_time:
                idx += 1
        return idx

    def __iter__(self) -> Iterator[ReplayStep]:
        start = self._first_scored_index()
        scored = 0
        for index in range(start, len(self.bars)):
            bar = self.bars[index]
            if self.to_time is not None and bar.time > self.to_time:
                break
            if self.max_bars is not None and scored >= self.max_bars:
                break
            lo = max(0, index - self.visible_window + 1)
            visible = self.bars[lo:index + 1]   # <= current time, never future
            yield ReplayStep(index=index, step=scored, time=bar.time,
                             current_bar=bar, visible_bars=visible)
            scored += 1

    def planned_steps(self) -> int:
        """Count of scored steps WITHOUT materializing each step's visible-bar slice.

        Mirrors __iter__'s start index and the same to_time / max_bars stop
        conditions exactly, but skips the per-step ``self.bars[lo:index + 1]`` copy
        — a full pre-pass over the history was otherwise allocating one bounded
        list per bar just to produce this integer.
        """
        start = self._first_scored_index()
        count = 0
        for index in range(start, len(self.bars)):
            if self.to_time is not None and self.bars[index].time > self.to_time:
                break
            if self.max_bars is not None and count >= self.max_bars:
                break
            count += 1
        return count


# ── Macro as-of join (causal) ──────────────────────────────────────────────────
@dataclass
class _Series:
    times: list[datetime]
    closes: list[float]

    def as_of_index(self, t: datetime) -> int:
        """Index of the latest row with time <= t, or -1 if none (no future leak)."""
        return bisect.bisect_right(self.times, t) - 1


class MacroSeries:
    """Loads DXY/US10Y/US02Y/VIX D1 closes; answers as-of (<= t) snapshots."""

    def __init__(self, series: dict[str, _Series], warnings: list[str]):
        self.series = series
        self.warnings = warnings

    @classmethod
    def load(cls, macro_history_dir: str | Path = DEFAULT_MACRO_HISTORY_DIR,
             timeframe: str = "D1") -> "MacroSeries":
        series: dict[str, _Series] = {}
        warnings: list[str] = []
        for sym in MACRO_INSTRUMENTS:
            cp = macro_csv_path(macro_history_dir, sym, timeframe)
            if not cp.exists():
                warnings.append(f"macro {sym}_{timeframe} missing - values unknown.")
                continue
            bars = sorted(read_macro_csv(cp, symbol=sym, timeframe=timeframe),
                          key=lambda b: b.time)
            if bars:
                series[sym] = _Series([b.time for b in bars], [b.close for b in bars])
        return cls(series, warnings)

    def _bias(self, sym: str, t: datetime, lookback: int = 3) -> str:
        s = self.series.get(sym)
        if s is None:
            return "unknown"
        i = s.as_of_index(t)
        if i < 1:
            return "unknown"
        prev = s.closes[max(0, i - lookback)]
        if prev == 0:
            return "unknown"
        pct = (s.closes[i] - prev) / abs(prev)
        if pct > _BIAS_EPS:
            return "rising"
        if pct < -_BIAS_EPS:
            return "falling"
        return "flat"

    def _close_as_of(self, sym: str, t: datetime) -> float | None:
        s = self.series.get(sym)
        if s is None:
            return None
        i = s.as_of_index(t)
        return s.closes[i] if i >= 0 else None

    def snapshot(self, t: datetime) -> dict[str, Any]:
        """Macro values/biases AS-OF t (never uses a row with time > t)."""
        dxy_bias = self._bias("DXY", t)
        yields_bias = self._bias("US10Y", t)
        vix_bias = self._bias("VIX", t)
        risk_bias = ({"rising": "risk_off", "falling": "risk_on", "flat": "neutral"}
                     .get(vix_bias, "unknown"))
        return {
            "as_of": t.isoformat(),
            "dxy_close": self._close_as_of("DXY", t),
            "us10y_close": self._close_as_of("US10Y", t),
            "us02y_close": self._close_as_of("US02Y", t),
            "vix_close": self._close_as_of("VIX", t),
            "dxy_bias": dxy_bias,
            "yields_bias": yields_bias,
            "vix_bias": vix_bias,
            "risk_bias": risk_bias,
        }


# ── Decision adapter (no MT5) ──────────────────────────────────────────────────
def _bar_to_candle(b: HistoricalBar) -> dict[str, Any]:
    return {"time": b.time.isoformat(), "open": b.open, "high": b.high,
            "low": b.low, "close": b.close}


def replay_decide(step: ReplayStep, macro_snapshot: dict, *, symbol: str,
                  timeframe: str, risk_mode: str, point: float = POINT,
                  learning_modifiers: dict | None = None, learning_mode: str = "replay",
                  use_trend_filter: bool = False, use_mean_reversion: bool = False):
    """
    Run the real Decision Engine V2 on the visible (past+current) bars only.
    Builds a MacroContext from the as-of DXY/yields biases (no calendar file).
    Execution is impossible here: no connector, has_open_position=False. Optional
    demo-only learning modifiers may nudge confidence (default none).
    """
    candles = [_bar_to_candle(b) for b in step.visible_bars]
    cur = step.current_bar
    spread_points = cur.spread if cur.spread is not None else 0.0
    macro = build_macro_context(
        step.time, [], "replay",
        dxy_bias=macro_snapshot.get("dxy_bias", "unknown"),
        yields_bias=macro_snapshot.get("yields_bias", "unknown"),
    )
    return decide(candles, symbol=symbol, timeframe=timeframe, risk_mode=risk_mode,
                  spread_points=spread_points, point=point, has_open_position=False, macro=macro,
                  use_learning_modifiers=bool(learning_modifiers),
                  learning_modifiers=learning_modifiers, learning_mode=learning_mode,
                  use_trend_filter=use_trend_filter, use_mean_reversion=use_mean_reversion)


# ── Forward return scoring (only AFTER the decision is recorded) ────────────────
def _first_touch(future: list[HistoricalBar], entry: float, direction: str,
                 sl_points: int | None, tp_points: int | None, point: float) -> str | None:
    if sl_points is None or tp_points is None:
        return None
    if direction == "LONG":
        tp, sl = entry + tp_points * point, entry - sl_points * point
    else:
        tp, sl = entry - tp_points * point, entry + sl_points * point
    for f in future:
        if direction == "LONG":
            hit_tp, hit_sl = f.high >= tp, f.low <= sl
        else:
            hit_tp, hit_sl = f.low <= tp, f.high >= sl
        if hit_tp and hit_sl:
            return "sl"          # conservative: assume the adverse level filled first
        if hit_tp:
            return "tp"
        if hit_sl:
            return "sl"
    return None


def score_horizon(bars: list[HistoricalBar], index: int, *, decision: str, horizon: int,
                  sl_points: int | None, tp_points: int | None, point: float = POINT,
                  cost_points: float = 0.0) -> dict:
    """
    Score one horizon using ONLY bars after ``index``. Pure forward-looking.
    ``cost_points`` is the round-trip trading cost (spread + commission) in points,
    subtracted from a TRADE's directional return to give net_return_points. Default
    0.0 → net == gross (unchanged behaviour).
    """
    entry = bars[index].close
    future = bars[index + 1: index + 1 + horizon]
    out: dict[str, Any] = {"horizon": horizon, "bars_available": len(future)}
    if not future:
        out["outcome"] = "no_data"
        out["ret_points"] = None
        out["dir_return_points"] = None
        out["net_return_points"] = None
        out["realized_return_points"] = None
        return out

    fwd_close = future[-1].close
    ret_points = (fwd_close - entry) / point
    max_high = max(f.high for f in future)
    min_low = min(f.low for f in future)
    if decision == "LONG":
        dir_ret = ret_points
        mfe = (max_high - entry) / point
        mae = (entry - min_low) / point
    elif decision == "SHORT":
        dir_ret = -ret_points
        mfe = (entry - min_low) / point
        mae = (max_high - entry) / point
    else:  # NO_TRADE - record what price did, but it is not a trade
        dir_ret = ret_points
        mfe = (max_high - entry) / point
        mae = (entry - min_low) / point

    is_trade = decision in ("LONG", "SHORT")
    net_ret = dir_ret - (cost_points if is_trade else 0.0)
    out.update({
        "ret_points": round(ret_points, 1),
        "dir_return_points": round(dir_ret, 1),
        "net_return_points": round(net_ret, 1),
        "cost_points": round(cost_points, 1) if is_trade else 0.0,
        "mfe_points": round(mfe, 1),
        "mae_points": round(mae, 1),
    })

    if decision in ("LONG", "SHORT"):
        ft = _first_touch(future, entry, decision, sl_points, tp_points, point)
        out["tp_hit"] = ft == "tp"
        out["sl_hit"] = ft == "sl"
        out["tp_sl_first"] = ft
        out["outcome"] = "win" if ft == "tp" else "loss" if ft == "sl" else "neutral"
        # Realized exit P&L (net): TP hit -> +tp, SL hit -> -sl, else exit at the
        # horizon close. This models the ACTUAL exit, so SL/TP settings can be tuned.
        if ft == "tp" and tp_points is not None:
            realized_gross = float(tp_points)
        elif ft == "sl" and sl_points is not None:
            realized_gross = -float(sl_points)
        else:
            realized_gross = dir_ret
        out["realized_return_points"] = round(realized_gross - cost_points, 1)
    else:
        out["outcome"] = "no_trade"
        out["realized_return_points"] = None
    return out


def score_forward(bars, index, *, decision, sl_points, tp_points, horizons, point=POINT,
                  cost_points=0.0) -> dict:
    return {str(h): score_horizon(bars, index, decision=decision, horizon=h,
                                  sl_points=sl_points, tp_points=tp_points, point=point,
                                  cost_points=cost_points)
            for h in horizons}


# ── Replay orchestration ────────────────────────────────────────────────────────
class ReplayError(Exception):
    """Replay cannot proceed (e.g. no local history)."""


@dataclass
class ReplayResult:
    summary: dict
    jsonl_path: Path | None = None
    summary_path: Path | None = None
    rows: list[dict] = field(default_factory=list)


def _next_replay_id(out_dir: Path, symbol: str, timeframe: str, now: datetime) -> str:
    stamp = now.strftime("%Y%m%d")
    prefix = f"replay_{symbol}_{timeframe}_{stamp}_"
    existing = list(out_dir.glob(prefix + "*.jsonl")) if out_dir.exists() else []
    return f"{prefix}{len(existing) + 1:03d}"


def run_replay(*, symbol: str = "XAUUSD", timeframe: str = "M1",
               history_dir: str | Path = DEFAULT_HISTORY_DIR,
               macro_history_dir: str | Path = DEFAULT_MACRO_HISTORY_DIR,
               out_dir: str | Path = DEFAULT_REPLAY_DIR, warmup_bars: int = 120,
               max_bars: int | None = 500, from_time: datetime | None = None,
               to_time: datetime | None = None, risk_mode: str = "balanced",
               horizons: tuple[int, ...] = DEFAULT_HORIZONS, dry_run: bool = False,
               use_learning_modifiers: bool = False, learning_modifiers_file: str | None = None,
               cost_points: float = 0.0, spread_cost: bool = False,
               max_spread_points: float | None = None,
               sl_points_override: int | None = None, tp_points_override: int | None = None,
               use_trend_filter: bool = False, use_mean_reversion: bool = False,
               now: datetime | None = None) -> ReplayResult:
    """
    Run a no-lookahead replay. Reads local history only - NEVER MT5. dry_run
    validates inputs and writes nothing. Raises ReplayError if history is absent.
    Optional demo-only learning modifiers (LM86B) may nudge confidence; default off.
    """
    now = now or datetime.now(timezone.utc)
    timeframe = timeframe.upper()
    cp = csv_path(history_dir, symbol, timeframe)
    if not cp.exists():
        raise ReplayError(
            f"no local history at {cp} - run scripts/run_gold_bot_history_backfill.py "
            f"--timeframes {timeframe} first.")
    bars = read_bars_csv(cp, symbol=symbol, timeframe=timeframe)
    if not bars:
        raise ReplayError(f"history file {cp} has no rows.")

    macro = MacroSeries.load(macro_history_dir, "D1")
    clock = ReplayClock(bars, warmup_bars=warmup_bars, max_bars=max_bars,
                        from_time=from_time, to_time=to_time)

    warnings: list[str] = list(macro.warnings)
    learning_modifiers: dict = {}
    learning_source = None
    if use_learning_modifiers:
        from services.gold_bot_learning_modifiers import (
            DEFAULT_ACTIVE_MODIFIERS_PATH, load_active_modifiers,
        )
        lpath = learning_modifiers_file or DEFAULT_ACTIVE_MODIFIERS_PATH
        learning_modifiers, lwarn = load_active_modifiers(lpath)
        warnings += lwarn
        learning_source = str(lpath)
    planned = clock.planned_steps()
    if planned == 0:
        warnings.append(
            f"no scored steps (rows={len(bars)}, warmup={warmup_bars}) - need more history "
            "or a smaller --warmup-bars.")

    base = {
        "symbol": symbol, "timeframe": timeframe, "risk_mode": risk_mode,
        "history_file": str(cp), "history_rows": len(bars),
        "first_bar": bars[0].time.isoformat(), "last_bar": bars[-1].time.isoformat(),
        "warmup_bars": warmup_bars, "max_bars": max_bars, "horizons": list(horizons),
        "planned_steps": planned, "macro_loaded": sorted(macro.series.keys()),
        "no_lookahead": True, "calls_mt5": False, "warnings": warnings,
        "used_learning_modifiers": bool(use_learning_modifiers and learning_modifiers),
        "learning_modifiers_count": len(learning_modifiers),
        "learning_modifiers_source": learning_source,
        "cost_points": round(cost_points, 1),
        "spread_cost": spread_cost,
        "max_spread_points": max_spread_points,
        "use_trend_filter": use_trend_filter,
        "use_mean_reversion": use_mean_reversion,
        "expectancy_basis": "net_return_points" if (cost_points or spread_cost) else "gross",
        "generated_at": now.isoformat(),
    }

    if dry_run:
        base["mode"] = "dry_run"
        return ReplayResult(summary=base)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    replay_id = _next_replay_id(out_dir, symbol, timeframe, now)
    jsonl_path = out_dir / f"{replay_id}.jsonl"
    summary_path = out_dir / f"{replay_id}.summary.json"

    agg = _Aggregator(horizons)
    rows: list[dict] = []
    with jsonl_path.open("w", encoding="utf-8") as fh:
        for step in clock:
            # ── decision: PAST + CURRENT bars only (no future) ──────────────
            snapshot = macro.snapshot(step.time)
            idea = replay_decide(step, snapshot, symbol=symbol, timeframe=timeframe,
                                 risk_mode=risk_mode, learning_modifiers=learning_modifiers or None,
                                 learning_mode="replay", use_trend_filter=use_trend_filter,
                                 use_mean_reversion=use_mean_reversion)
            # Spread filter: only take entries when the bar's spread is tight enough.
            # Tests whether avoiding wide-spread bars turns scalp net-positive.
            if (max_spread_points is not None and idea.decision in ("LONG", "SHORT")
                    and (step.current_bar.spread or 0.0) > max_spread_points):
                idea.decision = "NO_TRADE"
                idea.strategy = "no_trade_spread_filter"
            # ── forward scoring: STRICTLY future bars, AFTER the decision ────
            # Real round-trip cost: the entry bar's actual spread (when spread_cost)
            # plus any flat commission. This is scalp's true killer, measured.
            step_cost = cost_points + ((step.current_bar.spread or 0.0) if spread_cost else 0.0)
            sl_pts = sl_points_override if sl_points_override is not None else idea.sl_points
            tp_pts = tp_points_override if tp_points_override is not None else idea.tp_points
            scores = score_forward(bars, step.index, decision=idea.decision,
                                   sl_points=sl_pts, tp_points=tp_pts,
                                   horizons=horizons, cost_points=step_cost)
            row = {
                "replay_id": replay_id, "step": step.step, "time": step.time.isoformat(),
                "symbol": symbol, "timeframe": timeframe,
                "current_close": step.current_bar.close,
                "decision": idea.decision, "strategy": idea.strategy,
                "confidence": idea.confidence, "reasons": idea.reasons,
                "blockers": idea.blockers, "warnings": idea.warnings,
                "learning": idea.learning,
                "macro": snapshot, "score": scores,
                "no_lookahead_visible_bars_count": step.visible_count,
                "forward_scoring_uses_future_after_decision": True,
            }
            fh.write(json.dumps(row, default=str) + "\n")
            rows.append(row)
            agg.add(idea, scores)

    summary = {**base, "mode": "run", "replay_id": replay_id, **agg.finalize()}
    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    return ReplayResult(summary=summary, jsonl_path=jsonl_path, summary_path=summary_path, rows=rows)


class _Aggregator:
    def __init__(self, horizons: tuple[int, ...]):
        self.horizons = horizons
        self.bars = 0
        self.long = self.short = self.no_trade = 0
        self.conf_sum = 0
        self.setups: dict[str, int] = {}
        self.h: dict[str, dict] = {
            str(hz): {"win": 0, "loss": 0, "neutral": 0, "no_data": 0, "no_trade": 0,
                      "ret_sum": 0.0, "ret_count": 0, "real_sum": 0.0, "real_count": 0}
            for hz in horizons}

    def add(self, idea, scores: dict) -> None:
        self.bars += 1
        self.conf_sum += idea.confidence
        self.setups[idea.strategy] = self.setups.get(idea.strategy, 0) + 1
        if idea.decision == "LONG":
            self.long += 1
        elif idea.decision == "SHORT":
            self.short += 1
        else:
            self.no_trade += 1
        for hz, sc in scores.items():
            bucket = self.h[hz]
            bucket[sc["outcome"]] = bucket.get(sc["outcome"], 0) + 1
            # Expectancy uses NET return (gross - cost). net == gross when cost is
            # 0, so default replays are unchanged; cost-aware replays size expectancy
            # after spread/commission.
            ret = sc.get("net_return_points")
            if ret is None:
                ret = sc.get("dir_return_points")
            if idea.decision in ("LONG", "SHORT") and ret is not None:
                bucket["ret_sum"] += ret
                bucket["ret_count"] += 1
            real = sc.get("realized_return_points")
            if idea.decision in ("LONG", "SHORT") and real is not None:
                bucket["real_sum"] += real
                bucket["real_count"] += 1

    def finalize(self) -> dict:
        per_h = {}
        for hz, b in self.h.items():
            avg = round(b["ret_sum"] / b["ret_count"], 1) if b["ret_count"] else None
            avg_real = round(b["real_sum"] / b["real_count"], 1) if b["real_count"] else None
            per_h[hz] = {"win": b["win"], "loss": b["loss"], "neutral": b["neutral"],
                         "no_data": b["no_data"], "no_trade": b["no_trade"],
                         "avg_trade_return_points": avg,
                         "avg_realized_return_points": avg_real}
        top = sorted(self.setups.items(), key=lambda kv: -kv[1])
        return {
            "bars_processed": self.bars,
            "decisions": {"long": self.long, "short": self.short, "no_trade": self.no_trade},
            "avg_confidence": round(self.conf_sum / self.bars, 1) if self.bars else 0.0,
            "by_horizon": per_h,
            "top_setups": [{"strategy": s, "count": c} for s, c in top],
        }
