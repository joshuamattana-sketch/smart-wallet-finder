"""
tests/test_gold_bot_trade_outcomes.py
--------------------------------------
LM89A - Trade outcome reconstruction + feedback. No MT5, no internet, fake deals.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

from services.gold_bot_trade_outcomes import (
    DEFAULT_MAGIC,
    append_outcomes_to_learning_journal,
    reconstruct_outcomes,
    summarize_outcomes,
    write_outcomes,
)

NOW = datetime(2026, 6, 13, 12, 0, 0, tzinfo=timezone.utc)
_REPO = Path(__file__).resolve().parent.parent
BUY, SELL, IN, OUT = 0, 1, 0, 1


class _Deal:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _deal(position_id, dtype, entry, *, profit=0.0, price=2000.0, vol=0.1, comment="",
          symbol="XAUUSD", magic=DEFAULT_MAGIC, t=1000, commission=0.0, swap=0.0):
    return _Deal(position_id=position_id, type=dtype, entry=entry, profit=profit, price=price,
                 volume=vol, comment=comment, symbol=symbol, magic=magic, time=t,
                 commission=commission, swap=swap, sl=1995.0, tp=2010.0, ticket=t, order=position_id)


def _long(pid, *, profit, exit_price=2010.0, comment="", t0=1000):
    return [_deal(pid, BUY, IN, price=2000.0, t=t0),
            _deal(pid, SELL, OUT, profit=profit, price=exit_price, comment=comment, t=t0 + 60)]


# ── labeling ──────────────────────────────────────────────────────────────────────
def test_win_loss_breakeven_labeling():
    outs = reconstruct_outcomes(_long(1, profit=50.0) + _long(2, profit=-30.0)
                                + _long(3, profit=0.0))
    by = {o.trade_id: o.outcome for o in outs}
    assert by == {1: "win", 2: "loss", 3: "breakeven"}


def test_small_threshold_band_is_breakeven():
    assert reconstruct_outcomes(_long(1, profit=0.005))[0].outcome == "breakeven"
    assert reconstruct_outcomes(_long(1, profit=0.02))[0].outcome == "win"


def test_pnl_includes_commission_and_swap():
    deals = [_deal(1, BUY, IN, price=2000.0),
             _deal(1, SELL, OUT, profit=1.0, commission=-0.6, swap=-0.6, price=2000.5)]
    o = reconstruct_outcomes(deals)[0]
    assert o.pnl == -0.2 and o.outcome == "loss"   # 1.0 - 0.6 - 0.6


def test_missing_exit_volume_is_flagged():
    # A None exit-deal volume must surface a warning, not silently count as 0 lots
    # (which could make a full close look like a partial close).
    deals = [_deal(1, BUY, IN, price=2000.0, vol=0.1),
             _deal(1, SELL, OUT, profit=10.0, price=2010.0, vol=None)]
    o = reconstruct_outcomes(deals)[0]
    assert any("missing volume" in w for w in o.warnings)


# ── exit reason ────────────────────────────────────────────────────────────────────
def test_sl_tp_exit_reason_parsing():
    assert reconstruct_outcomes(_long(1, profit=20, comment="[tp 2010.0]"))[0].exit_reason == "tp"
    assert reconstruct_outcomes(_long(2, profit=-20, comment="[sl 1995.0]"))[0].exit_reason == "sl"
    assert reconstruct_outcomes(_long(3, profit=5, comment="close by bot"))[0].exit_reason == "manual_close"
    assert reconstruct_outcomes(_long(4, profit=5, comment=""))[0].exit_reason == "unknown"


# ── pairing + side + points ─────────────────────────────────────────────────────────
def test_pairing_by_position_id():
    outs = reconstruct_outcomes(_long(1, profit=10) + _long(2, profit=10))
    assert {o.trade_id for o in outs} == {1, 2}
    assert all(o.outcome == "win" and o.side == "LONG" for o in outs)


def test_short_side_and_points():
    deals = [_deal(9, SELL, IN, price=2000.0), _deal(9, BUY, OUT, profit=40, price=1990.0)]
    o = reconstruct_outcomes(deals)[0]
    assert o.side == "SHORT" and o.outcome == "win"
    assert o.pnl_points == 1000.0      # (2000-1990)/0.01


# ── open + partial ──────────────────────────────────────────────────────────────────
def test_open_trade_detection():
    o = reconstruct_outcomes([_deal(5, BUY, IN, price=2000.0)])[0]
    assert o.outcome == "open" and o.exit_time is None and o.exit_reason == "unknown"


def test_partial_close_aggregated_with_warning():
    deals = [_deal(7, BUY, IN, price=2000.0, vol=0.2),
             _deal(7, SELL, OUT, profit=5.0, price=2005.0, vol=0.1, t=1100),
             _deal(7, SELL, OUT, profit=5.0, price=2006.0, vol=0.1, t=1200)]
    outs = reconstruct_outcomes(deals)
    assert len(outs) == 1
    o = outs[0]
    assert o.outcome == "win" and o.pnl == 10.0
    assert any("partial" in w or "aggregated" in w for w in o.warnings)


# ── filtering ───────────────────────────────────────────────────────────────────────
def test_filters_by_symbol_and_magic():
    deals = (_long(1, profit=10)
             + [_deal(2, BUY, IN, magic=999), _deal(2, SELL, OUT, profit=10, magic=999)]
             + [_deal(3, BUY, IN, symbol="EURUSD"), _deal(3, SELL, OUT, profit=10, symbol="EURUSD")])
    outs = reconstruct_outcomes(deals, symbol="XAUUSD", magic=DEFAULT_MAGIC)
    assert [o.trade_id for o in outs] == [1]


def test_summarize_outcomes():
    outs = reconstruct_outcomes(_long(1, profit=50) + _long(2, profit=-30)
                                + [_deal(3, BUY, IN)])
    s = summarize_outcomes(outs)
    assert s == {**s, "count": 3, "wins": 1, "losses": 1, "breakeven": 0, "open": 1,
                 "realized_pnl": 20.0}


# ── write ────────────────────────────────────────────────────────────────────────────
def test_write_outcomes_creates_files(tmp_path):
    outs = reconstruct_outcomes(_long(1, profit=50), session_id="session_x")
    paths = write_outcomes(tmp_path, outs, session_id="session_x", now=NOW)
    assert paths["named"].exists() and paths["latest"].exists() and paths["events"].exists()
    latest = json.loads(paths["latest"].read_text())
    assert latest["session_id"] == "session_x" and latest["summary"]["wins"] == 1
    ev = [json.loads(l) for l in paths["events"].read_text().strip().splitlines()]
    assert ev[0]["trade_id"] == 1


def test_append_outcomes_to_learning_journal(tmp_path):
    outs = reconstruct_outcomes(_long(1, profit=50, comment="[tp 2010]"), session_id="session_x")
    n = append_outcomes_to_learning_journal(outs, learning_dir=tmp_path, now=NOW)
    assert n == 1
    rows = [json.loads(l) for l in (tmp_path / "learning_events.jsonl").read_text().strip().splitlines()]
    assert rows[0]["event"] == "demo_trade_outcome"
    assert rows[0]["source"] == "mt5_demo" and rows[0]["outcome"] == "win"
    assert rows[0]["exit_reason"] == "tp"


def test_append_outcomes_deduped_across_repeated_syncs(tmp_path):
    # Re-appending the same outcomes (as repeated session syncs do) must NOT bloat
    # the file — second call writes 0 new rows.
    outs = reconstruct_outcomes(_long(1, profit=50, comment="[tp 2010]")
                                + _long(2, profit=-20, comment="[sl]"))
    first = append_outcomes_to_learning_journal(outs, learning_dir=tmp_path, now=NOW)
    second = append_outcomes_to_learning_journal(outs, learning_dir=tmp_path, now=NOW)
    assert first == 2 and second == 0
    rows = (tmp_path / "learning_events.jsonl").read_text().strip().splitlines()
    assert len(rows) == 2                       # no duplicates appended


# ── no orders / no MT5 in source ──────────────────────────────────────────────────────
def test_source_has_no_orders_or_mt5_import():
    src = (_REPO / "services" / "gold_bot_trade_outcomes.py").read_text(encoding="utf-8")
    for forbidden in (".order_send(", "send_demo_order", "import requests", "urllib", "socket("):
        assert forbidden not in src


# ── probe CLI ──────────────────────────────────────────────────────────────────────────
def _load_probe():
    spec = importlib.util.spec_from_file_location(
        "run_gold_bot_trade_outcomes_probe",
        _REPO / "scripts" / "run_gold_bot_trade_outcomes_probe.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_probe_args_defaults_read_only():
    cli = _load_probe()
    args = cli.parse_args([])
    assert args.symbol == "XAUUSD" and args.magic == DEFAULT_MAGIC
    assert args.write is False          # default read-only
    assert args.json_output is False
