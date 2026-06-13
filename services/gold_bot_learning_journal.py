"""
services/gold_bot_learning_journal.py
---------------------------------------
LM86A - Pattern scoring / learning journal for the Gold Bot.

Aggregates the no-lookahead replay JSONL outputs (LM85A) into explainable setup
scorecards: expectancy, win/loss/neutral, avg return, sample size, confidence
buckets, direction / timeframe / risk-mode / session / macro slices, and a
NO_TRADE missed-opportunity analysis.

STRICTLY OFFLINE + READ-ONLY: reads local replay JSONL only. NO MT5, NO orders,
NO network. It produces a `setup_modifiers.preview.json` but that is a PREVIEW
ONLY - it is deliberately NOT wired into the decision engine or worker. Live
trading behavior is unchanged until a future owner-approved gate enables it.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPLAY_DIR = _REPO_ROOT / "data" / "gold_bot" / "replay"
DEFAULT_LEARNING_DIR = _REPO_ROOT / "data" / "gold_bot" / "learning"

# PREVIEW-ONLY. The decision engine never imports/reads this. Flipping live usage
# on is a future, explicit, owner-approved patch - not this one.
LEARNING_MODIFIERS_LIVE = False

WEAK_BAND_POINTS = 20.0          # |expectancy| <= this counts as "weak"
_STATUS_MODIFIER = {"promising": 5, "weak": -3, "avoid": -8}
_CONF_BUCKETS = ((0, 39), (40, 49), (50, 59), (60, 69), (70, 79), (80, 100))
_MACRO_DIMS = ("dxy_bias", "yields_bias", "risk_bias", "vix_bias")


# ── small helpers ──────────────────────────────────────────────────────────────
def _to_num(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _session_from_iso(iso: str | None) -> str:
    """Same UTC bands the decision engine uses; fallback when rows lack a session."""
    if not iso:
        return "unknown"
    try:
        h = datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone(timezone.utc).hour
    except (ValueError, TypeError):
        return "unknown"
    if 0 <= h < 7:
        return "Asia"
    if 7 <= h < 12:
        return "London"
    if 12 <= h < 21:
        return "NewYork"
    return "Off-session"


def _conf_bucket(conf: Any) -> str:
    c = _to_num(conf)
    if c is None:
        return "unknown"
    for lo, hi in _CONF_BUCKETS:
        if lo <= c <= hi:
            return f"{lo}-{hi}"
    return "unknown"


def row_session(row: dict) -> str:
    return row.get("session") or (row.get("macro") or {}).get("active_session") \
        or _session_from_iso(row.get("time"))


def recommended_status(trade_count: int, expectancy: float | None,
                       winrate: float | None, min_samples: int) -> str:
    """Explainable, conservative. No overfitting, no auto-delete."""
    if trade_count < min_samples:
        return "insufficient_sample"
    if expectancy is None or winrate is None:
        return "mixed"
    if expectancy < 0 and winrate < 0.45:
        return "avoid"
    if expectancy > WEAK_BAND_POINTS and winrate >= 0.50:
        return "promising"
    if abs(expectancy) <= WEAK_BAND_POINTS or (0.45 <= winrate < 0.50):
        return "weak"
    return "mixed"


# ── replay JSONL loading ────────────────────────────────────────────────────────
def _summary_path_for(jsonl: Path) -> Path:
    return jsonl.with_name(jsonl.name[:-6] + ".summary.json") if jsonl.name.endswith(".jsonl") \
        else jsonl.with_suffix(".summary.json")


def load_replay_rows(replay_dir: str | Path = DEFAULT_REPLAY_DIR, *, symbol: str | None = None,
                     timeframe: str | None = None, risk_mode: str | None = None
                     ) -> tuple[list[dict], list[str], list[str]]:
    """
    Load + lightly enrich replay rows. Returns (rows, files_loaded, warnings).
    Each row is enriched with `risk_mode` (from the sibling summary) and `session`.
    Missing/garbled fields are tolerated - bad lines are skipped with a warning.
    """
    d = Path(replay_dir)
    files_loaded: list[str] = []
    warnings: list[str] = []
    rows: list[dict] = []
    if not d.exists():
        return [], [], [f"replay dir not found: {replay_dir}"]

    for jsonl in sorted(d.glob("*.jsonl")):
        summary = {}
        sp = _summary_path_for(jsonl)
        if sp.exists():
            try:
                summary = json.loads(sp.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                warnings.append(f"unreadable summary {sp.name} - risk_mode unknown.")
        file_risk = summary.get("risk_mode", "unknown")
        file_used = False
        for ln, line in enumerate(jsonl.read_text(encoding="utf-8").splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                warnings.append(f"{jsonl.name}:{ln} bad JSON - skipped.")
                continue
            row.setdefault("risk_mode", file_risk)
            row.setdefault("symbol", summary.get("symbol", "unknown"))
            row.setdefault("timeframe", summary.get("timeframe", "unknown"))
            row["session"] = row_session(row)
            if symbol and row.get("symbol") != symbol:
                continue
            if timeframe and str(row.get("timeframe", "")).upper() != timeframe.upper():
                continue
            if risk_mode and row.get("risk_mode") != risk_mode:
                continue
            rows.append(row)
            file_used = True
        if file_used:
            files_loaded.append(jsonl.name)
    if not rows and not warnings:
        warnings.append("no replay rows matched the filters.")
    return rows, files_loaded, warnings


# ── accumulator ──────────────────────────────────────────────────────────────────
def _hz_zero() -> dict:
    return {"win": 0, "loss": 0, "neutral": 0, "no_data": 0, "ret_sum": 0.0, "ret_n": 0,
            "mfe_sum": 0.0, "mae_sum": 0.0, "exc_n": 0,
            "nt_count": 0, "nt_raw_sum": 0.0, "nt_raw_n": 0, "nt_missed": 0}


class _Acc:
    """Per-group accumulator tracking every horizon present in the rows."""

    def __init__(self) -> None:
        self.sample = self.trade = self.no_trade = self.long = self.short = 0
        self.conf_sum = 0.0
        self.conf_n = 0
        self.h: dict[str, dict] = {}

    def add(self, row: dict, missed_threshold: float) -> None:
        self.sample += 1
        conf = _to_num(row.get("confidence"))
        if conf is not None:
            self.conf_sum += conf
            self.conf_n += 1
        decision = row.get("decision", "NO_TRADE")
        is_trade = decision in ("LONG", "SHORT")
        if is_trade:
            self.trade += 1
            self.long += decision == "LONG"
            self.short += decision == "SHORT"
        else:
            self.no_trade += 1
        for hz, sc in (row.get("score") or {}).items():
            if not isinstance(sc, dict):
                continue
            b = self.h.setdefault(str(hz), _hz_zero())
            dr = _to_num(sc.get("dir_return_points"))
            if is_trade:
                outcome = sc.get("outcome")
                if outcome in ("win", "loss", "neutral", "no_data"):
                    b[outcome] += 1
                if dr is not None:
                    b["ret_sum"] += dr
                    b["ret_n"] += 1
                mfe, mae = _to_num(sc.get("mfe_points")), _to_num(sc.get("mae_points"))
                if mfe is not None and mae is not None:
                    b["mfe_sum"] += mfe
                    b["mae_sum"] += mae
                    b["exc_n"] += 1
            else:
                b["nt_count"] += 1
                if dr is not None:
                    b["nt_raw_sum"] += dr
                    b["nt_raw_n"] += 1
                    if abs(dr) > missed_threshold:
                        b["nt_missed"] += 1

    @property
    def avg_confidence(self) -> float | None:
        return round(self.conf_sum / self.conf_n, 1) if self.conf_n else None

    @staticmethod
    def _winrate(b: dict) -> float | None:
        denom = b["win"] + b["loss"]
        return round(b["win"] / denom, 3) if denom else None

    @staticmethod
    def _expectancy(b: dict) -> float | None:
        return round(b["ret_sum"] / b["ret_n"], 1) if b["ret_n"] else None

    def by_horizon(self) -> dict:
        out = {}
        for hz, b in sorted(self.h.items(), key=lambda kv: int(kv[0])):
            exp = self._expectancy(b)
            out[hz] = {"win": b["win"], "loss": b["loss"], "neutral": b["neutral"],
                       "no_data": b["no_data"], "winrate": self._winrate(b),
                       "avg_dir_return_points": exp, "expectancy_points": exp}
        return out

    def no_trade_by_horizon(self) -> dict:
        out = {}
        for hz, b in sorted(self.h.items(), key=lambda kv: int(kv[0])):
            out[hz] = {"count": b["nt_count"],
                       "avg_raw_move_points": round(b["nt_raw_sum"] / b["nt_raw_n"], 1)
                       if b["nt_raw_n"] else None,
                       "missed_large_moves": b["nt_missed"]}
        return out

    def summary(self, primary_h: int, min_samples: int) -> dict:
        prim = self.h.get(str(primary_h))
        winrate = self._winrate(prim) if prim else None
        expectancy = self._expectancy(prim) if prim else None
        avg_mfe = round(prim["mfe_sum"] / prim["exc_n"], 1) if prim and prim["exc_n"] else None
        avg_mae = round(prim["mae_sum"] / prim["exc_n"], 1) if prim and prim["exc_n"] else None
        return {
            "sample_count": self.sample, "trade_count": self.trade,
            "no_trade_count": self.no_trade, "long_count": self.long, "short_count": self.short,
            "avg_confidence": self.avg_confidence,
            "winrate": winrate, "expectancy_points": expectancy,
            "avg_dir_return_points": expectancy,
            "avg_mfe_points": avg_mfe, "avg_mae_points": avg_mae,
            "recommended_status": recommended_status(self.trade, expectancy, winrate, min_samples),
            "by_horizon": self.by_horizon(),
            "no_trade": {"by_horizon": self.no_trade_by_horizon()},
        }


def _group(rows: Iterable[dict], keyfn: Callable[[dict], str], *, primary_h: int,
           min_samples: int, missed: float, drop: tuple[str, ...] = ()) -> dict:
    accs: dict[str, _Acc] = {}
    for r in rows:
        k = keyfn(r)
        if k in drop:
            continue
        accs.setdefault(k, _Acc()).add(r, missed)
    return {k: accs[k].summary(primary_h, min_samples) for k in sorted(accs)}


# ── scorecard build ──────────────────────────────────────────────────────────────
def build_scorecard(rows: list[dict], *, horizon: int = 15, min_samples: int = 20,
                    missed_threshold: float = 150.0, top: int = 10,
                    warnings: list[str] | None = None, real_stats: dict | None = None,
                    real_trade_weight: float = 2.0) -> dict:
    glob = _Acc()
    for r in rows:
        glob.add(r, missed_threshold)

    by_setup = _group(rows, lambda r: str(r.get("strategy", "unknown")),
                      primary_h=horizon, min_samples=min_samples, missed=missed_threshold)
    confidence_buckets = _group(rows, lambda r: _conf_bucket(r.get("confidence")),
                                primary_h=horizon, min_samples=min_samples, missed=missed_threshold)
    direction = _group(rows, lambda r: str(r.get("decision", "NO_TRADE")),
                       primary_h=horizon, min_samples=min_samples, missed=missed_threshold,
                       drop=("NO_TRADE",))
    by_timeframe = _group(rows, lambda r: str(r.get("timeframe", "unknown")),
                          primary_h=horizon, min_samples=min_samples, missed=missed_threshold)
    by_risk_mode = _group(rows, lambda r: str(r.get("risk_mode", "unknown")),
                          primary_h=horizon, min_samples=min_samples, missed=missed_threshold)
    by_session = _group(rows, row_session,
                        primary_h=horizon, min_samples=min_samples, missed=missed_threshold)
    macro = {dim: _group(rows, lambda r, d=dim: str((r.get("macro") or {}).get(d, "unknown")),
                         primary_h=horizon, min_samples=min_samples, missed=missed_threshold)
             for dim in _MACRO_DIMS}

    # Ranked views (only setups that clear the sample guard).
    ranked = [(s, v) for s, v in by_setup.items()
              if v["trade_count"] >= min_samples and v["expectancy_points"] is not None]
    top_by_expectancy = sorted(ranked, key=lambda kv: kv[1]["expectancy_points"], reverse=True)[:top]
    weak_avoid = [s for s, v in by_setup.items()
                  if v["recommended_status"] in ("weak", "avoid")]

    scorecard = {
        "horizon": horizon, "min_samples": min_samples,
        "missed_move_threshold_points": missed_threshold,
        "rows": len(rows),
        "global": glob.summary(horizon, min_samples),
        "by_setup": by_setup,
        "top_setups_by_expectancy": [{"setup": s, **v} for s, v in top_by_expectancy],
        "weak_or_avoid_setups": weak_avoid,
        "confidence_buckets": confidence_buckets,
        "direction": direction,
        "by_timeframe": by_timeframe,
        "by_risk_mode": by_risk_mode,
        "by_session": by_session,
        "macro": macro,
        "no_trade_missed": glob.no_trade_by_horizon(),
        "warnings": list(warnings or []),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    if real_stats is not None:
        merge_real_into_scorecard(scorecard, real_stats, real_trade_weight=real_trade_weight)
    return scorecard


def build_setup_modifiers_preview(scorecard: dict, *, source_scorecard: str | None = None) -> dict:
    """
    PREVIEW. Suggests a confidence nudge per setup from its status, with the
    structured fields the LM86B promoter needs (sample_count / expectancy /
    winrate / status / horizon). This is NOT consumed by live decisions — it must
    be promoted to active_demo_modifiers.json (demo-only) before any use.
    """
    horizon = scorecard.get("horizon")
    preview: dict[str, Any] = {
        "_note": "PREVIEW - promote to active_demo_modifiers.json (demo-only) before use; "
                 "not read by live decisions.",
    }
    use_combined = bool(scorecard.get("include_real_trades"))
    for setup, v in scorecard.get("by_setup", {}).items():
        if use_combined and "recommended_status_combined" in v:
            entry = _combined_preview_entry(setup, v, horizon, source_scorecard)
        else:
            status = v["recommended_status"]
            if status not in _STATUS_MODIFIER:
                continue
            entry = {
                "setup": setup, "confidence_modifier": _STATUS_MODIFIER[status], "status": status,
                "sample_count": v["trade_count"], "expectancy_points": v["expectancy_points"],
                "winrate": v["winrate"], "horizon": horizon, "source_scorecard": source_scorecard,
                "reason": f"{status}: expectancy {v['expectancy_points']}pt at horizon "
                          f"{horizon} over {v['trade_count']} samples",
            }
        if entry is not None:
            preview[setup] = entry
    return preview


def _combined_preview_entry(setup: str, v: dict, horizon, source_scorecard) -> dict | None:
    """LM89B preview entry using combined replay+demo metrics, with a real-evidence reason."""
    status = v["recommended_status_combined"]
    if status not in _STATUS_MODIFIER:
        return None
    rep_n, real_n = v.get("replay_trade_count", 0), v.get("real_trade_count", 0)
    rep_exp, real_pts = v.get("expectancy_points"), v.get("real_avg_pnl_points")
    combined = v.get("combined_expectancy")
    if real_n:
        reason = (f"combined replay+demo: replay exp {rep_exp}pt over {rep_n}, "
                  f"demo exp {real_pts}pt over {real_n}, combined {combined}pt")
    else:
        reason = (f"{status}: combined {combined}pt over {rep_n} replay (no demo trades yet)")
    if v.get("real_contradicts_replay") and v.get("real_sample_quality") == "insufficient":
        reason += " | warning: real demo contradicts replay - sample small"
    return {
        "setup": setup, "confidence_modifier": _STATUS_MODIFIER[status], "status": status,
        "sample_count": rep_n + real_n, "expectancy_points": combined,
        "winrate": v.get("combined_winrate"), "horizon": horizon,
        "source_scorecard": source_scorecard,
        "replay_trade_count": rep_n, "real_trade_count": real_n,
        "real_avg_pnl": v.get("real_avg_pnl"), "real_avg_pnl_points": real_pts,
        "real_sample_quality": v.get("real_sample_quality"),
        "real_trade_weight": v.get("real_trade_weight"),
        "reason": reason,
    }


# ── output ────────────────────────────────────────────────────────────────────────
def write_scorecard(out_dir: str | Path, scorecard: dict, *, symbol: str, timeframe: str | None,
                    risk_mode: str | None, now: datetime | None = None) -> dict[str, Path]:
    now = now or datetime.now(timezone.utc)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tf = (timeframe or "all").upper() if timeframe else "all"
    rm = risk_mode or "all"
    stamp = now.strftime("%Y%m%d")
    named = out / f"scorecard_{symbol}_{tf}_{rm}_{stamp}.json"
    latest = out / "scorecard_latest.json"
    preview = out / "setup_modifiers.preview.json"
    events = out / "learning_events.jsonl"

    payload = json.dumps(scorecard, indent=2, default=str)
    named.write_text(payload, encoding="utf-8")
    latest.write_text(payload, encoding="utf-8")
    preview.write_text(json.dumps(
        build_setup_modifiers_preview(scorecard, source_scorecard=named.name),
        indent=2, default=str), encoding="utf-8")
    g = scorecard["global"]
    with events.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "generated_at": now.isoformat(), "scorecard_file": named.name,
            "symbol": symbol, "timeframe": tf, "risk_mode": rm, "horizon": scorecard["horizon"],
            "rows": scorecard["rows"], "trade_count": g["trade_count"],
            "global_expectancy_points": g["expectancy_points"], "global_winrate": g["winrate"],
        }, default=str) + "\n")
    return {"named": named, "latest": latest, "preview": preview, "events": events}


# ── LM89A: real demo-trade outcome feedback ────────────────────────────────────────
LEARNING_EVENTS_FILE = "learning_events.jsonl"


def append_demo_trade_outcome(outcome: Any, *, learning_dir: str | Path = DEFAULT_LEARNING_DIR,
                              now: datetime | None = None) -> Path:
    """
    Append one real demo-trade outcome (a TradeOutcome, LM89A) to
    learning_events.jsonl as a `demo_trade_outcome` event. This is the REAL-trade
    feedback dataset for a later scorecard ingestion patch (LM89B) - it does not
    retrain anything here. Read-only w.r.t. scorecards; append-only on the journal.
    """
    now = now or datetime.now(timezone.utc)
    d = Path(learning_dir)
    d.mkdir(parents=True, exist_ok=True)
    g = (lambda k: getattr(outcome, k, None))
    row = {
        "event": "demo_trade_outcome", "recorded_at": now.isoformat(),
        "trade_id": g("trade_id"), "setup": g("setup"), "side": g("side"),
        "confidence": g("confidence"), "learning_modifier": g("learning_modifier"),
        "risk_mode": g("risk_mode"), "pnl": g("pnl"), "pnl_points": g("pnl_points"),
        "outcome": g("outcome"), "exit_reason": g("exit_reason"),
        "session_id": g("session_id"), "source": "mt5_demo",
    }
    with (d / LEARNING_EVENTS_FILE).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
    return d / LEARNING_EVENTS_FILE


# ── LM89B: real demo-trade ingestion (read demo_trade_outcome -> stats -> blend) ────
DEMO_OUTCOME_EVENT = "demo_trade_outcome"
DEMO_OUTCOME_SOURCE = "mt5_demo"
DEFAULT_MIN_REAL_TRADES = 5
DEFAULT_REAL_TRADE_WEIGHT = 2.0
_CLOSED = ("win", "loss", "breakeven")


def default_events_file(learning_dir: str | Path = DEFAULT_LEARNING_DIR) -> Path:
    return Path(learning_dir) / LEARNING_EVENTS_FILE


def load_demo_trade_outcomes(events_file: str | Path = None, *, learning_dir: str | Path = DEFAULT_LEARNING_DIR,
                             include_open: bool = False) -> tuple[list[dict], list[str], int]:
    """
    Read `demo_trade_outcome` rows (LM89A) from learning_events.jsonl. Returns
    (outcomes, warnings, duplicates_ignored). Filters to source mt5_demo, dedups by
    trade_id, and skips open/unknown unless include_open. Tolerates bad lines.
    """
    p = Path(events_file) if events_file else default_events_file(learning_dir)
    if not p.exists():
        return [], [f"no learning events file: {p}"], 0
    seen: set = set()
    out: list[dict] = []
    warnings: list[str] = []
    duplicates = 0
    for ln, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            warnings.append(f"{p.name}:{ln} bad JSON - skipped.")
            continue
        if row.get("event") != DEMO_OUTCOME_EVENT:
            continue
        if row.get("source") not in (DEMO_OUTCOME_SOURCE, None):
            continue
        outcome = (row.get("outcome") or "unknown")
        if outcome not in _CLOSED and not include_open:
            continue
        tid = row.get("trade_id")
        if tid is not None and tid in seen:
            duplicates += 1
            continue
        if tid is not None:
            seen.add(tid)
        out.append({
            "trade_id": tid, "setup": row.get("setup") or "unknown",
            "side": row.get("side"), "confidence": _to_num(row.get("confidence")),
            "learning_modifier": row.get("learning_modifier"),
            "risk_mode": row.get("risk_mode") or "unknown",
            "pnl": _to_num(row.get("pnl")), "pnl_points": _to_num(row.get("pnl_points")),
            "outcome": outcome, "exit_reason": row.get("exit_reason"),
            "session_id": row.get("session_id"),
            "_tkey": row.get("exit_time") or row.get("recorded_at") or row.get("timestamp") or "",
        })
    return out, warnings, duplicates


def _real_quality(n: int, min_real: int) -> str:
    if n < min_real:
        return "insufficient"
    if n >= max(min_real * 4, 20):
        return "strong"
    return "usable"


class _RealAcc:
    """Aggregates real demo outcomes for one group (setup / risk / side / bucket)."""

    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add(self, o: dict) -> None:
        self.rows.append(o)

    def summary(self, min_real: int) -> dict:
        rows = sorted(self.rows, key=lambda r: r.get("_tkey") or "")
        n = len(rows)
        wins = sum(r["outcome"] == "win" for r in rows)
        losses = sum(r["outcome"] == "loss" for r in rows)
        be = sum(r["outcome"] == "breakeven" for r in rows)
        pnls = [r["pnl"] for r in rows if r["pnl"] is not None]
        pts = [r["pnl_points"] for r in rows if r["pnl_points"] is not None]
        confs = [r["confidence"] for r in rows if r["confidence"] is not None]
        cur = mx = 0
        for r in rows:
            if r["outcome"] == "loss":
                cur += 1
                mx = max(mx, cur)
            elif r["outcome"] == "win":
                cur = 0
        return {
            "trade_count": n, "win_count": wins, "loss_count": losses, "breakeven_count": be,
            "winrate": round(wins / (wins + losses), 3) if (wins + losses) else None,
            "realized_pnl": round(sum(pnls), 2) if pnls else 0.0,
            "avg_pnl": round(sum(pnls) / len(pnls), 2) if pnls else None,
            "avg_pnl_points": round(sum(pts) / len(pts), 1) if pts else None,
            "avg_confidence": round(sum(confs) / len(confs), 1) if confs else None,
            "loss_streak_max": mx,
            "last_trade_time": rows[-1]["_tkey"] if rows else None,
            "sample_quality": _real_quality(n, min_real),
        }


def _real_group(outcomes: list[dict], keyfn, *, min_real: int) -> dict:
    accs: dict[str, _RealAcc] = {}
    for o in outcomes:
        accs.setdefault(str(keyfn(o)), _RealAcc()).add(o)
    return {k: accs[k].summary(min_real) for k in sorted(accs)}


def build_real_trade_stats(outcomes: list[dict], *, min_real_trades: int = DEFAULT_MIN_REAL_TRADES,
                           duplicates_ignored: int = 0, warnings: list[str] | None = None) -> dict:
    """Aggregate real demo outcomes globally + by setup / risk_mode / side / confidence bucket."""
    glob = _RealAcc()
    for o in outcomes:
        glob.add(o)
    return {
        "min_real_trades": min_real_trades,
        "count": len(outcomes),
        "duplicates_ignored": duplicates_ignored,
        "global": glob.summary(min_real_trades),
        "by_setup": _real_group(outcomes, lambda o: o["setup"], min_real=min_real_trades),
        "by_risk_mode": _real_group(outcomes, lambda o: o["risk_mode"], min_real=min_real_trades),
        "by_side": _real_group(outcomes, lambda o: o["side"] or "unknown", min_real=min_real_trades),
        "by_confidence_bucket": _real_group(outcomes, lambda o: _conf_bucket(o["confidence"]),
                                            min_real=min_real_trades),
        "warnings": list(warnings or []),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _blend(replay_val: float | None, replay_n: int, real_val: float | None, real_n: int,
           weight: float) -> float | None:
    """Sample-weighted blend; real outcomes carry `weight`x their count (still can't dominate
    a much larger replay sample). Returns None only when neither side has a value."""
    rn, xn = max(0, replay_n or 0), max(0, real_n or 0)
    eff = xn * weight
    if replay_val is None and real_val is None:
        return None
    den = rn + eff
    if den <= 0:
        return None
    num = (replay_val or 0.0) * rn + (real_val or 0.0) * eff
    return round(num / den, 3)


def merge_real_into_scorecard(scorecard: dict, real_stats: dict, *,
                              real_trade_weight: float = DEFAULT_REAL_TRADE_WEIGHT) -> dict:
    """
    Fold real demo stats into each setup of an existing replay scorecard, adding
    combined_expectancy / combined_winrate / recommended_status_combined etc. The
    replay signal stays the base; real demo is weighted higher (execution-real) but
    can't dominate a tiny sample. Returns the same scorecard (mutated + returned).
    """
    real_by_setup = real_stats.get("by_setup", {})
    min_samples = scorecard.get("min_samples", 20)
    for setup, v in scorecard.get("by_setup", {}).items():
        rep_n = v.get("trade_count", 0)
        rep_exp = v.get("expectancy_points")
        rep_wr = v.get("winrate")
        rs = real_by_setup.get(setup, {})
        real_n = rs.get("trade_count", 0)
        real_pts = rs.get("avg_pnl_points")
        real_wr = rs.get("winrate")
        combined_exp = _blend(rep_exp, rep_n, real_pts, real_n, real_trade_weight)
        combined_wr = _blend(rep_wr, rep_n, real_wr, real_n, real_trade_weight)
        combined_n = rep_n + real_n
        contradicts = (rep_exp is not None and real_pts is not None
                       and (rep_exp >= 0) != (real_pts >= 0))
        v.update({
            "replay_trade_count": rep_n,
            "real_trade_count": real_n,
            "real_avg_pnl": rs.get("avg_pnl"),
            "real_avg_pnl_points": real_pts,
            "real_winrate": real_wr,
            "real_realized_pnl": rs.get("realized_pnl"),
            "real_sample_quality": rs.get("sample_quality", "insufficient"),
            "real_trade_weight": real_trade_weight,
            "combined_expectancy": combined_exp,
            "combined_winrate": combined_wr,
            "real_contradicts_replay": contradicts,
            "recommended_status_combined": recommended_status(
                combined_n, combined_exp, combined_wr, min_samples),
        })
    scorecard["include_real_trades"] = True
    scorecard["real_trade_weight"] = real_trade_weight
    scorecard["real_global"] = real_stats.get("global")
    scorecard["real_trade_count"] = real_stats.get("count", 0)
    scorecard["real_duplicates_ignored"] = real_stats.get("duplicates_ignored", 0)
    return scorecard


def write_real_trade_blend(out_dir: str | Path, scorecard: dict, real_stats: dict, *,
                           now: datetime | None = None) -> dict[str, Path]:
    """
    LM89B: persist the real-trade blend artifacts (gitignored):
      * real_trade_scorecard_latest.json  - real stats + combined per-setup view
      * real_trade_learning_summary.json  - compact global summary
      * real_trade_learning_events.jsonl  - one summary line per build (append)
    """
    now = now or datetime.now(timezone.utc)
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    combined = {s: {k: v.get(k) for k in (
                    "replay_trade_count", "real_trade_count", "real_avg_pnl_points",
                    "combined_expectancy", "combined_winrate", "real_sample_quality",
                    "real_contradicts_replay", "recommended_status_combined")}
                for s, v in scorecard.get("by_setup", {}).items() if "real_trade_count" in v}
    g = real_stats.get("global", {})
    scorecard_path = d / "real_trade_scorecard_latest.json"
    summary_path = d / "real_trade_learning_summary.json"
    events_path = d / "real_trade_learning_events.jsonl"
    scorecard_path.write_text(json.dumps({
        "generated_at": now.isoformat(), "real_trade_weight": scorecard.get("real_trade_weight"),
        "real_global": g, "by_setup": real_stats.get("by_setup"),
        "by_risk_mode": real_stats.get("by_risk_mode"), "combined_by_setup": combined,
    }, indent=2, default=str), encoding="utf-8")
    summary = {"generated_at": now.isoformat(), "real_trade_count": real_stats.get("count", 0),
               "duplicates_ignored": real_stats.get("duplicates_ignored", 0),
               "winrate": g.get("winrate"), "realized_pnl": g.get("realized_pnl"),
               "avg_pnl_points": g.get("avg_pnl_points"), "sample_quality": g.get("sample_quality"),
               "real_trade_weight": scorecard.get("real_trade_weight")}
    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    with events_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"event": "real_trade_blend", **summary}, default=str) + "\n")
    return {"scorecard": scorecard_path, "summary": summary_path, "events": events_path}
