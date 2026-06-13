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
                    warnings: list[str] | None = None) -> dict:
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

    return {
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
    for setup, v in scorecard.get("by_setup", {}).items():
        status = v["recommended_status"]
        if status not in _STATUS_MODIFIER:
            continue
        preview[setup] = {
            "setup": setup,
            "confidence_modifier": _STATUS_MODIFIER[status],
            "status": status,
            "sample_count": v["trade_count"],
            "expectancy_points": v["expectancy_points"],
            "winrate": v["winrate"],
            "horizon": horizon,
            "source_scorecard": source_scorecard,
            "reason": f"{status}: expectancy {v['expectancy_points']}pt at horizon "
                      f"{horizon} over {v['trade_count']} samples",
        }
    return preview


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
