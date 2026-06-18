"""
services/gold_bot_learning_cycle.py
------------------------------------
LM86C - Automatic learning cycle runner for the Gold Bot (DEMO-ONLY).

Closes the replay -> learning -> adaptation loop autonomously, but objectively:

    1. baseline replay        (no learning modifiers)
    2. scorecard              (LM86A: build setup_modifiers.preview.json)
    3. promote CANDIDATE      (LM86C: candidate_demo_modifiers.json, NOT active)
    4. candidate replay       (with the candidate modifiers, explicit file)
    5. compare                (baseline vs candidate at the selected horizon)
    6. keep or rollback       (accept -> backup + replace active; reject -> keep active)

The whole point is the LM86B regression we observed: promoting modifiers made
replay WORSE (h15 avg trade ret ~-41.1pt -> ~-49.8pt). This runner detects that
automatically and refuses to replace the active demo modifiers.

STRICT BOUNDARIES (same as the rest of the Gold Bot learning stack):
  * DEMO-ONLY. Never enables live trading, never sends orders, never touches MT5.
  * Modifiers stay CONFIDENCE-ONLY. Volume / lot sizing is never changed here.
  * Never bypasses the macro lockout, risk gate, or kill switch.
  * No HTTP, no secrets, no paid APIs. Pure local files only.

Pure + offline + injectable: the heavy replay/scorecard steps are passed in as
callables (defaults wire the real LM85A/LM86A services) so tests drive the whole
cycle with fake summaries and temp dirs - no MT5, no internet.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from services.gold_bot_learning_modifiers import (
    ACTIVE_FILE,
    CANDIDATE_FILE,
    DEFAULT_EXPIRY_DAYS,
    DEFAULT_LEARNING_DIR,
    REJECTED_FILE,
    activate_candidate,
    modifiers_expired,
    promote_candidate,
    rollback_active,
    write_rejected,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPLAY_DIR = _REPO_ROOT / "data" / "gold_bot" / "replay"
CYCLES_DIRNAME = "cycles"
CYCLE_EVENTS_FILE = "cycle_events.jsonl"

# Default accept thresholds (see compare_summaries).
DEFAULT_MIN_IMPROVEMENT_POINTS = 10.0
DEFAULT_MIN_TRADE_COUNT_RATIO = 0.5
DEFAULT_MIN_TRADES = 30
DEFAULT_MAX_WINRATE_DROP = 0.05
STRONG_IMPROVEMENT_FACTOR = 2.0   # winrate drop is forgiven if expectancy gains >= this x min_improvement


class CycleError(Exception):
    """The cycle cannot proceed (missing replay rows, no preview, etc.)."""


# ── summary extraction ───────────────────────────────────────────────────────────
def extract_summary(replay_summary: dict | None, horizon: int) -> dict[str, Any]:
    """
    Reduce a replay summary (LM85A `.summary.json` shape) to the comparison view
    at one horizon. `no_data` is True when the horizon produced no scored trades -
    the caller must reject safely in that case.
    """
    s = replay_summary or {}
    by_h = s.get("by_horizon") or {}
    bucket = by_h.get(str(horizon)) or {}
    decisions = s.get("decisions") or {}
    win = int(bucket.get("win", 0) or 0)
    loss = int(bucket.get("loss", 0) or 0)
    neutral = int(bucket.get("neutral", 0) or 0)
    no_data_bars = int(bucket.get("no_data", 0) or 0)
    trade_count = win + loss + neutral + no_data_bars
    expectancy = bucket.get("avg_trade_return_points")
    winrate = round(win / (win + loss), 3) if (win + loss) else None
    no_trade_count = bucket.get("no_trade", decisions.get("no_trade"))
    has_data = expectancy is not None and trade_count > 0
    return {
        "horizon": horizon,
        "no_data": not has_data,
        "trade_count": trade_count,
        "winrate": winrate,
        "expectancy_points": expectancy,
        "avg_trade_return_points": expectancy,
        "no_trade_count": no_trade_count,
        "decisions": {"long": decisions.get("long"), "short": decisions.get("short"),
                      "no_trade": decisions.get("no_trade")},
        "avg_confidence": s.get("avg_confidence"),
        "top_setups": (s.get("top_setups") or [])[:5],
        "used_learning_modifiers": s.get("used_learning_modifiers"),
        "replay_id": s.get("replay_id"),
    }


# ── comparison (pure) ─────────────────────────────────────────────────────────────
def compare_summaries(baseline_summary: dict | None, candidate_summary: dict | None, *,
                      horizon: int, min_improvement_points: float = DEFAULT_MIN_IMPROVEMENT_POINTS,
                      min_trade_count_ratio: float = DEFAULT_MIN_TRADE_COUNT_RATIO,
                      min_trades: int = DEFAULT_MIN_TRADES,
                      max_winrate_drop: float = DEFAULT_MAX_WINRATE_DROP) -> dict[str, Any]:
    """
    Objective accept/reject. PRIMARY metric is expectancy (avg trade return in
    points); secondary guards stop the candidate from collapsing trade count or
    quietly trading worse. Fails closed when either side has no data.
    """
    base = extract_summary(baseline_summary, horizon)
    cand = extract_summary(candidate_summary, horizon)
    out: dict[str, Any] = {
        "horizon": horizon,
        "baseline": base,
        "candidate": cand,
        "thresholds": {
            "min_improvement_points": min_improvement_points,
            "min_trade_count_ratio": min_trade_count_ratio,
            "min_trades": min_trades,
            "max_winrate_drop": max_winrate_drop,
        },
    }

    if base["no_data"] or cand["no_data"]:
        which = "baseline" if base["no_data"] else "candidate"
        out.update({"accepted": False, "checks": {"has_data": False},
                    "reason": f"rejected: no scored trades at horizon {horizon} "
                              f"({which} has no data) - kept active modifiers unchanged."})
        return out

    be, ce = float(base["expectancy_points"]), float(cand["expectancy_points"])
    expectancy_improvement = round(ce - be, 1)
    bwr = base["winrate"] if base["winrate"] is not None else 0.0
    cwr = cand["winrate"] if cand["winrate"] is not None else 0.0
    winrate_change = round(cwr - bwr, 3)
    winrate_drop = round(bwr - cwr, 3)
    trade_ratio = round(cand["trade_count"] / base["trade_count"], 3) if base["trade_count"] else 0.0
    strong = expectancy_improvement >= min_improvement_points * STRONG_IMPROVEMENT_FACTOR

    checks = {
        "has_data": True,
        "min_trades": cand["trade_count"] >= min_trades,
        "expectancy_improved": ce >= be + min_improvement_points,
        "trade_count_kept": cand["trade_count"] >= base["trade_count"] * min_trade_count_ratio,
        "winrate_ok": (winrate_drop <= max_winrate_drop) or strong,
    }
    accepted = all(checks.values())

    out.update({
        "accepted": accepted,
        "checks": checks,
        "expectancy_improvement": expectancy_improvement,
        "baseline_expectancy": be,
        "candidate_expectancy": ce,
        "winrate_change": winrate_change,
        "trade_count_ratio": trade_ratio,
        "strong_improvement": strong,
    })

    if accepted:
        out["reason"] = (f"accepted: expectancy {be:+.1f}pt -> {ce:+.1f}pt "
                         f"({expectancy_improvement:+.1f}pt), winrate {bwr:.3f} -> {cwr:.3f}, "
                         f"trades {base['trade_count']} -> {cand['trade_count']}.")
    else:
        fails = []
        if not checks["min_trades"]:
            fails.append(f"only {cand['trade_count']} candidate trades (< {min_trades})")
        if not checks["expectancy_improved"]:
            fails.append(f"expectancy {be:+.1f}pt -> {ce:+.1f}pt "
                         f"({expectancy_improvement:+.1f}pt, need >= +{min_improvement_points:.0f}pt)")
        if not checks["trade_count_kept"]:
            fails.append(f"trade count collapsed {base['trade_count']} -> {cand['trade_count']} "
                         f"(ratio {trade_ratio} < {min_trade_count_ratio})")
        if not checks["winrate_ok"]:
            fails.append(f"winrate dropped {bwr:.3f} -> {cwr:.3f} (> {max_winrate_drop})")
        out["reason"] = "rejected: " + "; ".join(fails) + " - kept active modifiers unchanged."
    return out


# ── cycle result ──────────────────────────────────────────────────────────────────
@dataclass
class CycleResult:
    cycle_id: str
    generated_at: str
    accepted: bool
    reason: str
    baseline: dict = field(default_factory=dict)
    candidate: dict = field(default_factory=dict)
    comparison: dict = field(default_factory=dict)
    active_modifiers_path: str | None = None
    candidate_modifiers_path: str | None = None
    rejected_modifiers_path: str | None = None
    backup_modifiers_path: str | None = None
    cycle_summary_path: str | None = None
    warnings: list[str] = field(default_factory=list)
    dry_run: bool = False
    planned_steps: list[str] = field(default_factory=list)
    real_trades_used: bool = False
    real_trade_count: int = 0
    real_trade_weight: float = 2.0
    walk_forward: bool = False
    split_info: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id, "generated_at": self.generated_at,
            "accepted": self.accepted, "reason": self.reason,
            "baseline": self.baseline, "candidate": self.candidate,
            "comparison": self.comparison,
            "active_modifiers_path": self.active_modifiers_path,
            "candidate_modifiers_path": self.candidate_modifiers_path,
            "rejected_modifiers_path": self.rejected_modifiers_path,
            "backup_modifiers_path": self.backup_modifiers_path,
            "cycle_summary_path": self.cycle_summary_path,
            "warnings": self.warnings, "dry_run": self.dry_run,
            "planned_steps": self.planned_steps,
            "real_trades_used": self.real_trades_used,
            "real_trade_count": self.real_trade_count,
            "real_trade_weight": self.real_trade_weight,
            "walk_forward": self.walk_forward,
            "split_info": self.split_info,
        }


# ── default (real) step runners - lazily wire LM85A/LM86A ─────────────────────────
def default_replay_runner(*, symbol: str, timeframe: str, risk_mode: str, max_bars: int,
                          horizons: tuple[int, ...], history_dir: str | Path | None,
                          macro_history_dir: str | Path | None, replay_out_dir: str | Path,
                          train_to: datetime | None = None,
                          validate_from: datetime | None = None,
                          train_dir: str | Path | None = None,
                          validate_dir: str | Path | None = None) -> Callable[..., dict]:
    """Returns a callable(use_learning, modifiers_file, phase=None) -> replay summary (LM85A).

    Without `phase` (or with the train/validate bounds unset) it replays the whole
    window into `replay_out_dir` — the original behaviour. For walk-forward it
    routes by `phase`: "train" replays bars up to `train_to` into `train_dir`,
    "validate" replays bars from `validate_from` into `validate_dir`. Train and
    validate windows are disjoint, so a candidate fit on train is judged on data
    it never saw.
    """
    from services.gold_bot_replay_engine import (
        DEFAULT_HISTORY_DIR, DEFAULT_MACRO_HISTORY_DIR, run_replay,
    )

    def runner(*, use_learning: bool, modifiers_file: str | None, phase: str | None = None) -> dict:
        from_time = to_time = None
        out_dir: str | Path = replay_out_dir
        if phase == "train":
            to_time, out_dir = train_to, (train_dir or replay_out_dir)
        elif phase == "validate":
            from_time, out_dir = validate_from, (validate_dir or replay_out_dir)
        res = run_replay(
            symbol=symbol, timeframe=timeframe, risk_mode=risk_mode, max_bars=max_bars,
            horizons=tuple(horizons), from_time=from_time, to_time=to_time,
            history_dir=history_dir or DEFAULT_HISTORY_DIR,
            macro_history_dir=macro_history_dir or DEFAULT_MACRO_HISTORY_DIR,
            out_dir=out_dir, use_learning_modifiers=use_learning,
            learning_modifiers_file=modifiers_file)
        return res.summary

    return runner


def default_split_time(*, symbol: str, timeframe: str, history_dir: str | Path | None,
                       warmup_bars: int = 120, train_fraction: float = 0.6
                       ) -> tuple[datetime, datetime] | None:
    """Derive disjoint train/validate time bounds from local history.

    Returns ``(train_to, validate_from)`` where ``train_to`` is the last scored
    bar time in the train slice and ``validate_from`` is the FIRST scored bar
    time in the validate slice (so the two windows never share a bar). Returns
    None when there is not enough history to split. Reads local CSVs only — no MT5.
    """
    from services.gold_bot_replay_engine import ReplayClock
    from services.gold_bot_historical_market_data import (
        DEFAULT_HISTORY_DIR, csv_path, read_bars_csv,
    )
    cp = csv_path(history_dir or DEFAULT_HISTORY_DIR, symbol, timeframe.upper())
    if not cp.exists():
        return None
    bars = read_bars_csv(cp, symbol=symbol, timeframe=timeframe)
    if not bars:
        return None
    times = [s.time for s in ReplayClock(bars, warmup_bars=warmup_bars, max_bars=None)]
    if len(times) < 2:
        return None
    cut = max(1, min(len(times) - 1, int(len(times) * train_fraction)))
    return times[cut - 1], times[cut]


def default_scorecard_runner(*, symbol: str, timeframe: str, risk_mode: str, horizon: int,
                             min_samples: int, replay_out_dir: str | Path,
                             learning_dir: str | Path, include_real_trades: bool = False,
                             real_trade_weight: float = 2.0, min_real_trades: int = 5,
                             train_dir: str | Path | None = None
                             ) -> Callable[..., None]:
    """Returns a callable(phase=None) that builds + writes the LM86A scorecard/preview.
    With include_real_trades it blends LM89A demo_trade_outcome events (LM89B).
    For walk-forward, phase="train" fits the scorecard on the TRAIN replay rows
    only (`train_dir`), so the modifiers are never derived from validate data."""
    from services.gold_bot_learning_journal import (
        build_real_trade_stats, build_scorecard, load_demo_trade_outcomes,
        load_replay_rows, write_real_trade_blend, write_scorecard,
    )

    def runner(phase: str | None = None) -> None:
        src_dir = train_dir if (phase == "train" and train_dir is not None) else replay_out_dir
        rows, files, warns = load_replay_rows(
            src_dir, symbol=symbol, timeframe=timeframe, risk_mode=risk_mode)
        if not rows:
            raise CycleError(
                f"scorecard: no replay rows in {src_dir} for "
                f"symbol={symbol} timeframe={timeframe} risk={risk_mode}.")
        real_stats = None
        if include_real_trades:
            outcomes, rt_warn, dups = load_demo_trade_outcomes(learning_dir=learning_dir)
            real_stats = build_real_trade_stats(outcomes, min_real_trades=min_real_trades,
                                                duplicates_ignored=dups, warnings=rt_warn)
            warns = warns + rt_warn
        scorecard = build_scorecard(rows, horizon=horizon, min_samples=min_samples, warnings=warns,
                                    real_stats=real_stats, real_trade_weight=real_trade_weight)
        write_scorecard(learning_dir, scorecard, symbol=symbol, timeframe=timeframe,
                        risk_mode=risk_mode)
        if real_stats is not None:
            write_real_trade_blend(learning_dir, scorecard, real_stats)

    return runner


def _history_present(symbol: str, timeframe: str, history_dir: str | Path | None) -> tuple[bool, str]:
    """Dry-run validation helper - reports whether local history exists (no MT5)."""
    try:
        from services.gold_bot_historical_market_data import DEFAULT_HISTORY_DIR, csv_path
        cp = csv_path(history_dir or DEFAULT_HISTORY_DIR, symbol, timeframe.upper())
        return cp.exists(), str(cp)
    except Exception as exc:                       # noqa: BLE001 - dry-run must never crash
        return False, f"(history path check failed: {exc})"


# ── the cycle ─────────────────────────────────────────────────────────────────────
def run_cycle(*, symbol: str = "XAUUSD", timeframe: str = "M1", risk_mode: str = "balanced",
              max_bars: int = 500, horizons: tuple[int, ...] = (5, 15, 30), horizon: int = 15,
              min_samples: int = 10, min_trades: int = DEFAULT_MIN_TRADES,
              min_improvement_points: float = DEFAULT_MIN_IMPROVEMENT_POINTS,
              min_trade_count_ratio: float = DEFAULT_MIN_TRADE_COUNT_RATIO,
              max_winrate_drop: float = DEFAULT_MAX_WINRATE_DROP,
              learning_dir: str | Path = DEFAULT_LEARNING_DIR,
              replay_out_dir: str | Path = DEFAULT_REPLAY_DIR,
              history_dir: str | Path | None = None, macro_history_dir: str | Path | None = None,
              expiry_days: int | None = DEFAULT_EXPIRY_DAYS, dry_run: bool = False,
              include_real_trades: bool = False, real_trade_weight: float = 2.0,
              min_real_trades: int = 5, now: datetime | None = None,
              walk_forward: bool = False, split_time: datetime | None = None,
              train_fraction: float = 0.6, warmup_bars: int = 120,
              replay_runner: Callable[..., dict] | None = None,
              scorecard_runner: Callable[..., None] | None = None) -> CycleResult:
    """
    Run the full demo-only learning cycle. With dry_run it validates inputs and
    writes NOTHING. Heavy steps are injectable for tests; defaults wire the real
    LM85A replay + LM86A scorecard. Never calls MT5, never sends orders, no HTTP.
    """
    now = now or datetime.now(timezone.utc)
    cycle_id = "cycle_" + now.strftime("%Y%m%d_%H%M%S")
    learning_dir = Path(learning_dir)
    warnings: list[str] = []

    planned = [
        f"1. baseline replay  (symbol={symbol} tf={timeframe} risk={risk_mode} "
        f"max_bars={max_bars} horizons={list(horizons)}, learning OFF)",
        f"2. scorecard        (horizon={horizon} min_samples={min_samples} -> setup_modifiers.preview.json)",
        f"3. promote candidate (-> {CANDIDATE_FILE}; active file untouched)",
        "4. candidate replay  (same params, learning ON using the candidate file)",
        f"5. compare           (horizon={horizon}: expectancy +>={min_improvement_points}pt, "
        f"trades >= {min_trades}, ratio >= {min_trade_count_ratio})",
        f"6. keep or rollback  (accept -> backup + replace {ACTIVE_FILE}; reject -> keep active)",
    ]
    if walk_forward:
        planned.insert(0, f"0. walk-forward ON (train_fraction={train_fraction}): scorecard fits on "
                          "the TRAIN window; accept/reject measured on a disjoint VALIDATE window.")

    if dry_run:
        ok, hist = _history_present(symbol, timeframe, history_dir)
        if not ok:
            warnings.append(f"history not found at {hist} - run scripts/run_gold_bot_history_backfill.py "
                            f"--timeframes {timeframe.upper()} before a real run.")
        expired, exp = modifiers_expired(learning_dir / ACTIVE_FILE, now=now)
        if expired:
            warnings.append(f"active modifiers expired at {exp} - a real cycle will refresh them.")
        return CycleResult(cycle_id=cycle_id, generated_at=now.isoformat(), accepted=False,
                           reason="dry-run: planned steps validated, nothing written.",
                           warnings=warnings, dry_run=True, planned_steps=planned,
                           active_modifiers_path=str(learning_dir / ACTIVE_FILE))

    # Walk-forward windows: fit the scorecard on a TRAIN slice, then accept/reject
    # on a DISJOINT, unseen VALIDATE slice. This is the structural defence against
    # the in-sample overfitting the old single-window cycle could not detect.
    split_info: dict[str, Any] = {}
    train_dir = validate_dir = None
    train_to = validate_from = None
    if walk_forward:
        train_dir = Path(replay_out_dir) / "wf_train"
        validate_dir = Path(replay_out_dir) / "wf_validate"
        if split_time is not None:
            train_to = validate_from = split_time
        elif replay_runner is None:   # real path: derive the split from local history
            split = default_split_time(symbol=symbol, timeframe=timeframe, history_dir=history_dir,
                                       warmup_bars=warmup_bars, train_fraction=train_fraction)
            if split is None:
                raise CycleError(
                    "walk-forward: not enough local history to split into train/validate windows.")
            train_to, validate_from = split
        split_info = {
            "train_fraction": train_fraction,
            "train_to": train_to.isoformat() if train_to else None,
            "validate_from": validate_from.isoformat() if validate_from else None,
        }

    replay_runner = replay_runner or default_replay_runner(
        symbol=symbol, timeframe=timeframe, risk_mode=risk_mode, max_bars=max_bars,
        horizons=horizons, history_dir=history_dir, macro_history_dir=macro_history_dir,
        replay_out_dir=replay_out_dir, train_to=train_to, validate_from=validate_from,
        train_dir=train_dir, validate_dir=validate_dir)
    scorecard_runner = scorecard_runner or default_scorecard_runner(
        symbol=symbol, timeframe=timeframe, risk_mode=risk_mode, horizon=horizon,
        min_samples=min_samples, replay_out_dir=replay_out_dir, learning_dir=learning_dir,
        include_real_trades=include_real_trades, real_trade_weight=real_trade_weight,
        min_real_trades=min_real_trades, train_dir=train_dir)

    real_trade_count = 0
    if include_real_trades:
        from services.gold_bot_learning_journal import load_demo_trade_outcomes
        _ro, _rw, _ = load_demo_trade_outcomes(learning_dir=learning_dir)
        real_trade_count = len(_ro)
        warnings += _rw

    # 1+2. fit the scorecard. Walk-forward fits on the TRAIN window only (its replay
    # rows feed the scorecard); the standard cycle fits on the whole window and the
    # same baseline is reused for the comparison.
    if walk_forward:
        replay_runner(use_learning=False, modifiers_file=None, phase="train")
        scorecard_runner(phase="train")
    else:
        baseline_summary = replay_runner(use_learning=False, modifiers_file=None)
        scorecard_runner()
    # 3. promote candidate (staged separately; active untouched)
    cand_payload, evaluated, promo_warn = promote_candidate(
        learning_dir, min_samples=min_samples, now=now, cycle_id=cycle_id, expiry_days=expiry_days)
    warnings += promo_warn
    if not cand_payload.get("modifiers"):
        warnings.append("no candidate modifiers cleared the sample guard - "
                        "comparison will run but the candidate replay is effectively the baseline.")
    candidate_path = learning_dir / CANDIDATE_FILE
    # 4. candidate replay (learning ON, explicit candidate file). Walk-forward
    # measures BOTH baseline and candidate on the unseen VALIDATE window.
    if walk_forward:
        baseline_summary = replay_runner(use_learning=False, modifiers_file=None, phase="validate")
        candidate_summary = replay_runner(use_learning=True, modifiers_file=str(candidate_path),
                                          phase="validate")
        warnings.append("walk-forward: modifiers fit on the TRAIN window; accepted/rejected on a "
                        "disjoint, unseen VALIDATE window.")
    else:
        candidate_summary = replay_runner(use_learning=True, modifiers_file=str(candidate_path))
    # 5. compare
    comparison = compare_summaries(
        baseline_summary, candidate_summary, horizon=horizon,
        min_improvement_points=min_improvement_points, min_trade_count_ratio=min_trade_count_ratio,
        min_trades=min_trades, max_winrate_drop=max_winrate_drop)
    base_view, cand_view = comparison["baseline"], comparison["candidate"]
    accepted, reason = comparison["accepted"], comparison["reason"]

    # 6. keep or rollback
    active_path: Path | None = learning_dir / ACTIVE_FILE
    backup_path: Path | None = None
    rejected_path: Path | None = None
    if accepted:
        active_path, backup_path = activate_candidate(
            learning_dir, cand_payload, now=now, reason=reason,
            baseline_summary=base_view, candidate_summary=cand_view)
    else:
        rejected_path = write_rejected(
            learning_dir, cand_payload, reason=reason, now=now,
            baseline_summary=base_view, candidate_summary=cand_view)
        if not active_path.exists():
            active_path = None

    result = CycleResult(
        cycle_id=cycle_id, generated_at=now.isoformat(), accepted=accepted, reason=reason,
        baseline=base_view, candidate=cand_view, comparison=comparison,
        active_modifiers_path=str(active_path) if active_path else None,
        candidate_modifiers_path=str(candidate_path),
        rejected_modifiers_path=str(rejected_path) if rejected_path else None,
        backup_modifiers_path=str(backup_path) if backup_path else None,
        warnings=warnings, planned_steps=planned,
        real_trades_used=include_real_trades, real_trade_count=real_trade_count,
        real_trade_weight=real_trade_weight, walk_forward=walk_forward, split_info=split_info)

    summary_path = _write_cycle_summary(learning_dir, result, symbol=symbol, timeframe=timeframe,
                                        risk_mode=risk_mode, now=now)
    result.cycle_summary_path = str(summary_path)
    _append_cycle_event(learning_dir, result, event="accepted" if accepted else "rejected",
                        symbol=symbol, timeframe=timeframe, risk_mode=risk_mode, now=now)
    return result


# ── cycle output files ────────────────────────────────────────────────────────────
def _cycles_dir(learning_dir: str | Path) -> Path:
    d = Path(learning_dir) / CYCLES_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_cycle_summary(learning_dir: str | Path, result: CycleResult, *, symbol: str,
                         timeframe: str, risk_mode: str, now: datetime) -> Path:
    d = _cycles_dir(learning_dir)
    payload = {
        "cycle_id": result.cycle_id, "generated_at": now.isoformat(),
        "symbol": symbol, "timeframe": timeframe, "risk_mode": risk_mode,
        "horizon": result.comparison.get("horizon"),
        "mode": "demo_auto_learning_cycle", "safety": "demo_only",
        **result.to_dict(),
    }
    p = d / f"{result.cycle_id}.json"
    p.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return p


def _append_cycle_event(learning_dir: str | Path, result: CycleResult, *, event: str, symbol: str,
                        timeframe: str, risk_mode: str, now: datetime) -> None:
    d = _cycles_dir(learning_dir)
    line = {
        "generated_at": now.isoformat(), "cycle_id": result.cycle_id, "event": event,
        "symbol": symbol, "timeframe": timeframe, "risk_mode": risk_mode,
        "horizon": result.comparison.get("horizon"),
        "expectancy_improvement": result.comparison.get("expectancy_improvement"),
        "baseline_expectancy": result.comparison.get("baseline_expectancy"),
        "candidate_expectancy": result.comparison.get("candidate_expectancy"),
        "reason": result.reason,
    }
    with (d / CYCLE_EVENTS_FILE).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(line, default=str) + "\n")


def run_rollback(learning_dir: str | Path = DEFAULT_LEARNING_DIR, *,
                 now: datetime | None = None) -> tuple[bool, str]:
    """
    Restore the active modifiers from backup and append a rollback cycle event.
    Returns (ok, message). DEMO-only; no MT5, no orders.
    """
    now = now or datetime.now(timezone.utc)
    ok, message = rollback_active(learning_dir)
    d = _cycles_dir(learning_dir)
    with (d / CYCLE_EVENTS_FILE).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"generated_at": now.isoformat(), "event": "rollback",
                             "ok": ok, "reason": message}, default=str) + "\n")
    return ok, message
