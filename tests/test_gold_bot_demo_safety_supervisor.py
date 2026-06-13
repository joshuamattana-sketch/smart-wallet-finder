"""
tests/test_gold_bot_demo_safety_supervisor.py
----------------------------------------------
LM87A - Demo safety supervisor. Pure + offline: no MT5, no internet, temp dirs.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from services.gold_bot_demo_safety_supervisor import (
    DemoSafetySupervisor,
    SafetyExecContext,
    SupervisorConfig,
)

NOW = datetime(2026, 6, 13, 12, 0, 0, tzinfo=timezone.utc)
_REPO = Path(__file__).resolve().parent.parent


def _sup(tmp_path, config=None):
    return DemoSafetySupervisor(config or SupervisorConfig(),
                                state_path=tmp_path / "safety_state.json",
                                events_path=tmp_path / "safety_events.jsonl")


def _valid_payload(*, expires_at="2026-12-31T00:00:00+00:00", mods=None):
    return {"safety": "demo_only", "mode": "demo_auto_learning", "expires_at": expires_at,
            "modifiers": mods if mods is not None
            else {"momentum": {"setup": "momentum", "confidence_modifier": -8,
                               "status": "active", "reason": "avoid"}}}


def _write(tmp_path, payload, name="active_demo_modifiers.json"):
    p = tmp_path / name
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def _ctx(**kw):
    base = dict(now=NOW, risk_mode="balanced", account_is_demo=True, symbol_selected=True,
                open_positions=0, spread_points=10.0, equity=10000.0, free_margin=9000.0,
                daily_realized_pnl=0.0, tick_fresh=True, kill_switch=False, macro_lockout=False,
                decision="LONG")
    base.update(kw)
    return SafetyExecContext(**base)


# ── 1. learning-modifier contract ──────────────────────────────────────────────
def test_valid_demo_modifier_file_passes(tmp_path):
    p = _write(tmp_path, _valid_payload())
    dec = _sup(tmp_path).evaluate_learning(p, enabled=True, now=NOW)
    assert dec.allowed is True and dec.severity == "info"


def test_learning_not_requested_is_allowed(tmp_path):
    dec = _sup(tmp_path).evaluate_learning(None, enabled=False, now=NOW)
    assert dec.allowed is True
    assert dec.details["enabled"] is False


def test_expired_modifier_file_disables_learning(tmp_path):
    p = _write(tmp_path, _valid_payload(expires_at="2020-01-01T00:00:00+00:00"))
    dec = _sup(tmp_path).evaluate_learning(p, enabled=True, now=NOW)
    assert dec.allowed is False
    assert "disable_learning" in dec.actions
    assert any("expired" in v for v in dec.details["violations"])


def test_forbidden_keys_disable_learning(tmp_path):
    bad = _valid_payload(mods={"x": {"confidence_modifier": 3, "status": "active",
                                     "reason": "r", "volume": 0.1}})
    p = _write(tmp_path, bad)
    dec = _sup(tmp_path).evaluate_learning(p, enabled=True, now=NOW)
    assert dec.allowed is False
    assert any("forbidden key 'volume'" in v for v in dec.details["violations"])


def test_out_of_clamp_modifier_disables_learning(tmp_path):
    bad = _valid_payload(mods={"x": {"confidence_modifier": 99, "status": "active", "reason": "r"}})
    p = _write(tmp_path, bad)
    dec = _sup(tmp_path).evaluate_learning(p, enabled=True, now=NOW)
    assert dec.allowed is False
    assert any("out of clamp" in v for v in dec.details["violations"])


def test_wrong_safety_or_mode_disables_learning(tmp_path):
    p = _write(tmp_path, {"safety": "live", "mode": "demo_auto_learning", "modifiers": {}})
    dec = _sup(tmp_path).evaluate_learning(p, enabled=True, now=NOW)
    assert dec.allowed is False
    assert any("safety != demo_only" in v for v in dec.details["violations"])


def test_missing_modifier_file_disables_without_crash(tmp_path):
    dec = _sup(tmp_path).evaluate_learning(tmp_path / "nope.json", enabled=True, now=NOW)
    assert dec.allowed is False and dec.severity == "warning"
    assert "disable_learning" in dec.actions


# ── 2/3. open positions + stacking ──────────────────────────────────────────────
def test_max_open_positions_blocks(tmp_path):
    dec = _sup(tmp_path).evaluate_execution(_ctx(open_positions=1))
    assert dec.allowed is False
    assert dec.reason == "max_open_positions_reached"


def test_stacking_blocks_when_position_open(tmp_path):
    # max_open_positions high so the open-guard passes; stacking guard catches it.
    cfg = SupervisorConfig(max_open_positions=5)
    dec = _sup(tmp_path, cfg).evaluate_execution(_ctx(open_positions=1))
    assert dec.allowed is False
    assert dec.reason == "no_stacking"


def test_stacking_allowed_when_configured(tmp_path):
    cfg = SupervisorConfig(max_open_positions=5, allow_stacking=True)
    dec = _sup(tmp_path, cfg).evaluate_execution(_ctx(open_positions=1))
    assert dec.allowed is True


# ── 7. spread ───────────────────────────────────────────────────────────────────
def test_spread_too_high_blocks(tmp_path):
    dec = _sup(tmp_path).evaluate_execution(_ctx(spread_points=40.0))   # balanced ceiling 35
    assert dec.allowed is False and dec.reason == "spread_guard"


def test_scalp_spread_ceiling_is_tighter(tmp_path):
    dec = _sup(tmp_path).evaluate_execution(_ctx(risk_mode="scalp", spread_points=30.0))  # scalp 25
    assert dec.allowed is False and dec.reason == "spread_guard"


# ── 4. trade frequency ──────────────────────────────────────────────────────────
def test_trade_frequency_min_gap_blocks(tmp_path):
    sup = _sup(tmp_path)
    sup.save_state({"recent_trades": [], "last_trade_at": (NOW - timedelta(seconds=10)).isoformat(),
                    "consecutive_losses": 0, "cooldown_until": None}, now=NOW)
    dec = sup.evaluate_execution(_ctx())
    assert dec.allowed is False and dec.reason == "trade_frequency_guard"


def test_trade_frequency_per_hour_blocks(tmp_path):
    sup = _sup(tmp_path)
    recent = [(NOW - timedelta(minutes=m)).isoformat() for m in (1, 5, 9, 13, 17, 21)]  # 6 in last hour
    sup.save_state({"recent_trades": recent, "last_trade_at": None,
                    "consecutive_losses": 0, "cooldown_until": None}, now=NOW)
    dec = sup.evaluate_execution(_ctx())
    assert dec.allowed is False and dec.reason == "trade_frequency_guard"


def test_register_trade_sent_feeds_frequency(tmp_path):
    sup = _sup(tmp_path)
    sup.register_trade_sent(now=NOW)
    state = sup.load_state()
    assert state["last_trade_at"] == NOW.isoformat()
    assert state["recent_trades"] == [NOW.isoformat()]


# ── 5. loss streak cooldown ──────────────────────────────────────────────────────
def test_loss_streak_triggers_cooldown(tmp_path):
    sup = _sup(tmp_path)
    sup.save_state({"recent_trades": [], "last_trade_at": None, "consecutive_losses": 3,
                    "cooldown_until": None}, now=NOW)
    dec = sup.evaluate_execution(_ctx())
    assert dec.allowed is False and dec.reason == "loss_streak_cooldown"
    assert dec.cooldown_until is not None
    # cooldown persisted to state
    assert sup.load_state()["cooldown_until"] == dec.cooldown_until


def test_active_cooldown_blocks_until_expiry(tmp_path):
    sup = _sup(tmp_path)
    until = (NOW + timedelta(minutes=20)).isoformat()
    sup.save_state({"recent_trades": [], "last_trade_at": None, "consecutive_losses": 3,
                    "cooldown_until": until}, now=NOW)
    dec = sup.evaluate_execution(_ctx())
    assert dec.allowed is False and dec.reason == "loss_streak_cooldown"


def test_expired_cooldown_resets_and_allows(tmp_path):
    sup = _sup(tmp_path)
    past = (NOW - timedelta(minutes=5)).isoformat()
    sup.save_state({"recent_trades": [], "last_trade_at": None, "consecutive_losses": 3,
                    "cooldown_until": past}, now=NOW)
    dec = sup.evaluate_execution(_ctx())
    assert dec.allowed is True                       # cooldown expired -> reset
    assert sup.load_state()["consecutive_losses"] == 0


def test_record_trade_result_tracks_streak(tmp_path):
    sup = _sup(tmp_path)
    sup.record_trade_result(won=False, now=NOW)
    sup.record_trade_result(won=False, now=NOW)
    assert sup.load_state()["consecutive_losses"] == 2
    sup.record_trade_result(won=True, now=NOW)
    assert sup.load_state()["consecutive_losses"] == 0


# ── 6. daily drawdown ────────────────────────────────────────────────────────────
def test_daily_drawdown_block(tmp_path):
    dec = _sup(tmp_path).evaluate_execution(_ctx(equity=10000.0, daily_realized_pnl=-800.0))  # -8%
    assert dec.allowed is False and dec.reason == "daily_drawdown_guard"


def test_daily_drawdown_warning_allows(tmp_path):
    dec = _sup(tmp_path).evaluate_execution(_ctx(equity=10000.0, daily_realized_pnl=-500.0))  # -5%
    assert dec.allowed is True and dec.severity == "warning"
    assert dec.details["loss_pct"] == 5.0


# ── 10/9. kill switch + macro lockout ────────────────────────────────────────────
def test_kill_switch_blocks(tmp_path):
    dec = _sup(tmp_path).evaluate_execution(_ctx(kill_switch=True))
    assert dec.allowed is False and dec.reason == "kill_switch"
    assert dec.severity == "critical" and "pause_demo" in dec.actions


def test_macro_lockout_blocks_and_is_never_overridden(tmp_path):
    dec = _sup(tmp_path).evaluate_execution(_ctx(macro_lockout=True))
    assert dec.allowed is False and dec.reason == "macro_lockout"


# ── 8. MT5 health ────────────────────────────────────────────────────────────────
def test_demo_account_required(tmp_path):
    dec = _sup(tmp_path).evaluate_execution(_ctx(account_is_demo=False))
    assert dec.allowed is False and dec.reason == "mt5_health_guard"
    assert dec.severity == "critical" and "require_manual_restart" in dec.actions


def test_stale_tick_blocks(tmp_path):
    dec = _sup(tmp_path).evaluate_execution(_ctx(tick_fresh=False))
    assert dec.allowed is False and dec.reason == "mt5_health_guard"


def test_no_free_margin_blocks(tmp_path):
    dec = _sup(tmp_path).evaluate_execution(_ctx(free_margin=0.0))
    assert dec.allowed is False and dec.reason == "mt5_health_guard"


# ── all clear ─────────────────────────────────────────────────────────────────────
def test_all_clear_allows(tmp_path):
    dec = _sup(tmp_path).evaluate_execution(_ctx())
    assert dec.allowed is True and dec.severity == "info" and dec.reason == "all_clear"


def test_kill_switch_priority_over_other_blocks(tmp_path):
    # Many failures at once → kill switch (critical) is the reported reason.
    dec = _sup(tmp_path).evaluate_execution(
        _ctx(kill_switch=True, open_positions=3, spread_points=99.0, macro_lockout=True))
    assert dec.reason == "kill_switch"


# ── safety probe CLI ──────────────────────────────────────────────────────────────
def _load_probe():
    spec = importlib.util.spec_from_file_location(
        "run_gold_bot_safety_probe", _REPO / "scripts" / "run_gold_bot_safety_probe.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_safety_probe_runs_json(tmp_path, capsys):
    probe = _load_probe()
    mf = _write(tmp_path, _valid_payload())
    rc = probe.main(["--learning-modifiers-file", str(mf),
                     "--state-file", str(tmp_path / "safety_state.json"), "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["learning_contract"]["allowed"] is True
    assert out["cooldown_active"] is False


def test_safety_probe_args_defaults():
    probe = _load_probe()
    args = probe.parse_args([])
    assert args.learning_modifiers_file.endswith("active_demo_modifiers.json")
    assert args.state_file.endswith("safety_state.json")
    assert args.json_output is False


# ── no MT5 / orders / network in the supervisor source ────────────────────────────
def test_supervisor_source_has_no_mt5_orders_or_http():
    src = (_REPO / "services" / "gold_bot_demo_safety_supervisor.py").read_text(encoding="utf-8")
    for forbidden in ("MetaTrader5", ".order_send(", "import requests", "urllib", "socket("):
        assert forbidden not in src
