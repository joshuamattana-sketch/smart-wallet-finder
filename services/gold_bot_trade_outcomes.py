"""
services/gold_bot_trade_outcomes.py
-------------------------------------
LM89A - Trade outcome feedback loop for the Gold Bot (DEMO ONLY).

Reads MT5 *demo* deal history for the bot's own trades (filtered by symbol +
magic), reconstructs entry/exit into TradeOutcome records (win/loss/breakeven/
open), and feeds the real outcomes back into:
  * the LM87A safety supervisor loss-streak state (makes the guard REAL), and
  * the LM86A learning journal (`demo_trade_outcome` events) for later ingestion.

This patch SENDS NO ORDERS and changes no strategy logic - it only READS history
and writes local feedback files. Pure + offline at the reconstruction layer: the
MT5 read is injectable (a connector or a deals list) so unit tests use fake deals
with no MT5 and no internet.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTCOMES_DIR = _REPO_ROOT / "data" / "gold_bot" / "trade_outcomes"
DEFAULT_LEARNING_DIR = _REPO_ROOT / "data" / "gold_bot" / "learning"

# Matches GoldBotWorker.WORKER_MAGIC (810810). Kept local to avoid an import cycle.
DEFAULT_MAGIC = 810_810
DEFAULT_SYMBOL = "XAUUSD"
POINT = 0.01
DEFAULT_SMALL_THRESHOLD = 0.01     # account-currency band for breakeven

# Standard MT5 deal enum values (stable; mirrors the connector's getattr defaults).
DEAL_TYPE_BUY, DEAL_TYPE_SELL = 0, 1
DEAL_ENTRY_IN, DEAL_ENTRY_OUT = 0, 1


# ── helpers ──────────────────────────────────────────────────────────────────────
def _int(v: Any) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _float(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _str(v: Any) -> str:
    return "" if v is None else str(v)


def _iso_time(v: Any) -> str | None:
    """MT5 deal.time is epoch seconds; tolerate datetime / iso-string fakes too."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()
    if isinstance(v, (int, float)):
        try:
            return datetime.fromtimestamp(v, tz=timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    return str(v)


# ── model ────────────────────────────────────────────────────────────────────────
@dataclass
class TradeOutcome:
    trade_id: int | str | None
    symbol: str
    magic: int | None
    side: str                          # LONG | SHORT
    outcome: str                       # win | loss | breakeven | open | unknown
    exit_reason: str                   # sl | tp | manual_close | opposite_signal | unknown
    volume: float | None = None
    entry_time: str | None = None
    exit_time: str | None = None
    entry_price: float | None = None
    exit_price: float | None = None
    sl: float | None = None
    tp: float | None = None
    pnl: float | None = None           # net realized (profit + commission + swap)
    pnl_points: float | None = None
    commission: float | None = None
    swap: float | None = None
    setup: str | None = None
    confidence: float | None = None
    learning_modifier: int | None = None
    risk_mode: str | None = None
    session_id: str | None = None
    source: str = "mt5_history"
    raw_deals: list[dict] | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── normalization ────────────────────────────────────────────────────────────────
def normalize_deal(d: Any) -> dict[str, Any]:
    """Duck-typed MT5 deal -> dict. Works on raw MT5 objects and fakes alike."""
    return {
        "ticket": _int(getattr(d, "ticket", None)),
        "order": _int(getattr(d, "order", None)),
        "position_id": _int(getattr(d, "position_id", None)),
        "magic": _int(getattr(d, "magic", None)),
        "time": _iso_time(getattr(d, "time", None)),
        "_time_raw": getattr(d, "time", None),
        "symbol": _str(getattr(d, "symbol", None)),
        "type": _int(getattr(d, "type", None)),
        "entry": _int(getattr(d, "entry", None)),
        "volume": _float(getattr(d, "volume", None)),
        "price": _float(getattr(d, "price", None)),
        "sl": _float(getattr(d, "sl", None)),
        "tp": _float(getattr(d, "tp", None)),
        "profit": _float(getattr(d, "profit", None)) or 0.0,
        "commission": _float(getattr(d, "commission", None)) or 0.0,
        "swap": _float(getattr(d, "swap", None)) or 0.0,
        "comment": _str(getattr(d, "comment", None)),
    }


def _exit_reason(comment: str) -> str:
    c = (comment or "").lower()
    if "[sl" in c or "[ sl" in c:
        return "sl"
    if "[tp" in c or "[ tp" in c:
        return "tp"
    if "close" in c:
        return "manual_close"
    return "unknown"


def _label(pnl: float, *, small_threshold: float) -> str:
    if pnl > small_threshold:
        return "win"
    if pnl < -small_threshold:
        return "loss"
    return "breakeven"


# ── reconstruction ───────────────────────────────────────────────────────────────
def reconstruct_outcomes(deals: list[Any], *, symbol: str = DEFAULT_SYMBOL,
                         magic: int = DEFAULT_MAGIC, session_id: str | None = None,
                         point: float = POINT,
                         small_threshold: float = DEFAULT_SMALL_THRESHOLD,
                         enrich: dict[Any, dict] | None = None) -> list[TradeOutcome]:
    """
    Pair entry/exit deals by position_id into TradeOutcomes. Filters to the bot's
    symbol + magic and to real trade deals (buy/sell). Partial closes are
    aggregated (sum exit volume/pnl) with a warning. Never raises on odd data.
    `enrich` optionally maps position_id -> {setup,confidence,learning_modifier,risk_mode}.
    """
    enrich = enrich or {}
    rows = [normalize_deal(d) for d in deals]
    groups: dict[Any, list[dict]] = {}
    for r in rows:
        if symbol and r["symbol"] != symbol:
            continue
        if magic is not None and r["magic"] != magic:
            continue
        if r["type"] not in (DEAL_TYPE_BUY, DEAL_TYPE_SELL):
            continue
        pid = r["position_id"] if r["position_id"] is not None else r["order"]
        groups.setdefault(pid, []).append(r)

    outcomes: list[TradeOutcome] = []
    for pid, group in groups.items():
        group.sort(key=lambda x: (x["_time_raw"] is None, x["_time_raw"]))
        ins = [g for g in group if g["entry"] == DEAL_ENTRY_IN]
        outs = [g for g in group if g["entry"] == DEAL_ENTRY_OUT]
        warnings: list[str] = []
        entry = ins[0] if ins else group[0]
        side = "LONG" if entry["type"] == DEAL_TYPE_BUY else "SHORT"
        if len(ins) > 1:
            warnings.append(f"multiple entry deals on position {pid} (scale-in); used first.")

        commission = round(sum(g["commission"] for g in group), 2)
        swap = round(sum(g["swap"] for g in group), 2)
        meta = enrich.get(pid, {})

        if not outs:
            outcomes.append(TradeOutcome(
                trade_id=pid, symbol=symbol, magic=magic, side=side, outcome="open",
                exit_reason="unknown", volume=entry["volume"], entry_time=entry["time"],
                entry_price=entry["price"], sl=entry["sl"], tp=entry["tp"],
                pnl=round(sum(g["profit"] for g in group) + commission + swap, 2),
                commission=commission, swap=swap, session_id=session_id,
                raw_deals=group, warnings=warnings, **_meta_fields(meta)))
            continue

        if len(outs) > 1:
            warnings.append(f"partial/multiple exits on position {pid}; aggregated {len(outs)} exits.")
        # A missing exit-deal volume would silently count as 0 lots and could make a
        # full close look like a partial close — surface it rather than swallow it.
        if any(g.get("volume") is None for g in outs):
            warnings.append(f"exit deal(s) on position {pid} missing volume; "
                            f"treated as 0 — exit-volume check may be unreliable.")
        exit_volume = round(sum(g["volume"] or 0.0 for g in outs), 2)
        if entry["volume"] and abs(exit_volume - entry["volume"]) > 1e-9:
            warnings.append(f"exit volume {exit_volume} != entry volume {entry['volume']} (partial close).")
        last_out = outs[-1]
        pnl = round(sum(g["profit"] for g in group) + commission + swap, 2)
        entry_price, exit_price = entry["price"], last_out["price"]
        pnl_points = None
        if entry_price is not None and exit_price is not None and point:
            diff = (exit_price - entry_price) if side == "LONG" else (entry_price - exit_price)
            pnl_points = round(diff / point, 1)
        outcomes.append(TradeOutcome(
            trade_id=pid, symbol=symbol, magic=magic, side=side,
            outcome=_label(pnl, small_threshold=small_threshold),
            exit_reason=_exit_reason(last_out["comment"]),
            volume=entry["volume"], entry_time=entry["time"], exit_time=last_out["time"],
            entry_price=entry_price, exit_price=exit_price, sl=entry["sl"], tp=entry["tp"],
            pnl=pnl, pnl_points=pnl_points, commission=commission, swap=swap,
            session_id=session_id, raw_deals=group, warnings=warnings, **_meta_fields(meta)))
    return outcomes


def _meta_fields(meta: dict) -> dict:
    return {"setup": meta.get("setup"), "confidence": meta.get("confidence"),
            "learning_modifier": meta.get("learning_modifier"), "risk_mode": meta.get("risk_mode")}


def summarize_outcomes(outcomes: list[TradeOutcome]) -> dict[str, Any]:
    closed = [o for o in outcomes if o.outcome in ("win", "loss", "breakeven")]
    return {
        "count": len(outcomes),
        "wins": sum(o.outcome == "win" for o in outcomes),
        "losses": sum(o.outcome == "loss" for o in outcomes),
        "breakeven": sum(o.outcome == "breakeven" for o in outcomes),
        "open": sum(o.outcome == "open" for o in outcomes),
        "realized_pnl": round(sum(o.pnl or 0.0 for o in closed), 2),
        "warnings": [w for o in outcomes for w in o.warnings],
    }


# ── output ────────────────────────────────────────────────────────────────────────
def write_outcomes(out_dir: str | Path, outcomes: list[TradeOutcome], *,
                   session_id: str | None = None, now: datetime | None = None) -> dict[str, Path]:
    now = now or datetime.now(timezone.utc)
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y%m%d_%H%M%S")
    payload = {
        "generated_at": now.isoformat(), "session_id": session_id, "source": "mt5_demo_history",
        "summary": summarize_outcomes(outcomes),
        "outcomes": [o.to_dict() for o in outcomes],
    }
    named = d / f"outcomes_{stamp}.json"
    latest = d / "outcomes_latest.json"
    blob = json.dumps(payload, indent=2, default=str)
    named.write_text(blob, encoding="utf-8")
    latest.write_text(blob, encoding="utf-8")
    events = d / "outcomes_events.jsonl"
    with events.open("a", encoding="utf-8") as fh:
        for o in outcomes:
            fh.write(json.dumps({"recorded_at": now.isoformat(), "session_id": session_id,
                                 **o.to_dict()}, default=str) + "\n")
    return {"named": named, "latest": latest, "events": events}


# ── decision context (LM108A: attach engine confidence to reconstructed trades) ────
def load_decision_context(path: str | Path) -> dict[Any, dict]:
    """
    Load a decision-context JSONL (one row per SENT order: position_id, confidence,
    setup, side, risk_mode) into an enrich map {position_id: {setup, confidence,
    learning_modifier, risk_mode}} for reconstruct_outcomes. Last write per
    position_id wins. Missing/garbled file -> {} (never raises).
    """
    p = Path(path)
    if not p.exists():
        return {}
    out: dict[Any, dict] = {}
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        pid = row.get("position_id")
        if pid is None:
            continue
        out[pid] = {"setup": row.get("setup"), "confidence": row.get("confidence"),
                    "learning_modifier": row.get("learning_modifier"),
                    "risk_mode": row.get("risk_mode")}
    return out


# ── feedback: supervisor + learning journal ───────────────────────────────────────
def update_safety_from_outcomes(supervisor: Any, outcomes: list[TradeOutcome], *,
                                now: datetime | None = None) -> bool:
    """
    Replay CLOSED outcomes (oldest first) into the supervisor loss-streak state.
    Returns True if any outcome was recorded. Open/unknown are skipped.
    """
    recorded = False
    closed = [o for o in outcomes if o.outcome in ("win", "loss", "breakeven")]
    closed.sort(key=lambda o: (o.exit_time is None, o.exit_time))
    for o in closed:
        supervisor.record_trade_result(o, now=now)
        recorded = True
    return recorded


def append_outcomes_to_learning_journal(outcomes: list[TradeOutcome], *,
                                        learning_dir: str | Path = DEFAULT_LEARNING_DIR,
                                        now: datetime | None = None) -> int:
    """
    Append `demo_trade_outcome` rows to learning_events.jsonl. DEDUPED by trade_id:
    outcomes already present are skipped, so repeated session syncs no longer bloat
    the file with thousands of duplicate rows. Returns count actually written.
    """
    from services.gold_bot_learning_journal import (
        append_demo_trade_outcome, load_demo_trade_outcomes,
    )
    existing, _w, _d = load_demo_trade_outcomes(learning_dir=learning_dir, include_open=True)
    seen = {o.get("trade_id") for o in existing if o.get("trade_id") is not None}
    n = 0
    for o in outcomes:
        tid = getattr(o, "trade_id", None)
        if tid is not None and tid in seen:
            continue
        append_demo_trade_outcome(o, learning_dir=learning_dir, now=now)
        seen.add(tid)
        n += 1
    return n


# ── orchestration: post-session sync ───────────────────────────────────────────────
def sync_session_outcomes(*, symbol: str = DEFAULT_SYMBOL, magic: int = DEFAULT_MAGIC,
                          session_id: str | None = None, from_time: datetime | None = None,
                          to_time: datetime | None = None, out_dir: str | Path = DEFAULT_OUTCOMES_DIR,
                          learning_dir: str | Path = DEFAULT_LEARNING_DIR,
                          supervisor: Any | None = None, connector: Any | None = None,
                          write: bool = True, now: datetime | None = None,
                          enrich: dict | None = None) -> dict[str, Any]:
    """
    Read demo deal history for [from_time, to_time], reconstruct outcomes, write
    them, update the supervisor loss-streak state, and append learning events.
    Fail-closed + safe: missing MT5 / non-demo account -> synced False with reason,
    never raises, NEVER sends orders. Connector is injectable for tests.
    """
    now = now or datetime.now(timezone.utc)
    warnings: list[str] = []
    own_connector = connector is None
    try:
        if connector is None:
            from services.connectors.mt5_demo_connector import Mt5DemoConnector, ProbeResult
            connector = Mt5DemoConnector()
            connector.connect()
            probe = ProbeResult()
            connector.read_account(probe)
        if not getattr(connector, "demo_verified", False):
            return {"synced": False, "reason": "mt5_unavailable_or_not_demo",
                    "warnings": ["account not a verified demo account - outcome sync skipped."]}
        if from_time is None or to_time is None:
            return {"synced": False, "reason": "no_time_window",
                    "warnings": ["from_time/to_time required for outcome sync."]}
        deals = connector.deal_history(from_time, to_time)
    except Exception as exc:  # noqa: BLE001 - sync must never break the caller
        return {"synced": False, "reason": "mt5_error", "warnings": [f"outcome sync failed: {exc}"]}
    finally:
        if own_connector and connector is not None:
            try:
                connector.shutdown()
            except Exception:  # noqa: BLE001
                pass

    outcomes = reconstruct_outcomes(deals, symbol=symbol, magic=magic, session_id=session_id,
                                    enrich=enrich)
    summary = summarize_outcomes(outcomes)
    paths = write_outcomes(out_dir, outcomes, session_id=session_id, now=now) if write else {}
    safety_updated = False
    if supervisor is not None:
        safety_updated = update_safety_from_outcomes(supervisor, outcomes, now=now)
    journaled = append_outcomes_to_learning_journal(outcomes, learning_dir=learning_dir, now=now) if write else 0

    return {
        "synced": True, "reason": "ok",
        "outcomes_count": summary["count"], "wins": summary["wins"], "losses": summary["losses"],
        "breakeven": summary["breakeven"], "open": summary["open"],
        "realized_pnl": summary["realized_pnl"],
        "outcome_file": str(paths.get("named")) if paths else None,
        "safety_state_updated": safety_updated, "journaled": journaled,
        "deals_scanned": len(deals), "warnings": warnings + summary["warnings"],
    }
