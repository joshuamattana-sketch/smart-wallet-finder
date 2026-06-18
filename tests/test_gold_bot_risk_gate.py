"""
tests/test_gold_bot_risk_gate.py
---------------------------------
LM75B — Pure tests for the demo-order risk gate and the trade journal.
No MT5, no env mutation leaks (env is set/cleared per test), no network.
"""

from __future__ import annotations

import pytest

from services.gold_bot_risk_gate import (
    DEFAULT_MAX_VOLUME,
    SafetyConfig,
    evaluate_demo_order,
)
from services import gold_bot_trade_journal as journal


def _approve_kwargs(**over):
    base = dict(
        config=SafetyConfig(),
        account_is_demo=True,
        side="buy",
        volume=0.01,
        sl_present=True,
        tp_present=True,
        trades_today=0,
    )
    base.update(over)
    return base


# ── approval path ─────────────────────────────────────────────────────────────
def test_clean_demo_order_is_approved():
    d = evaluate_demo_order(**_approve_kwargs())
    assert d.approved is True
    assert d.reasons == []
    # daily-loss TODO always warns (never silently passes)
    assert any("daily-loss" in w for w in d.warnings)


# ── hard blocks ───────────────────────────────────────────────────────────────
def test_non_demo_blocked():
    d = evaluate_demo_order(**_approve_kwargs(account_is_demo=False))
    assert d.approved is False
    assert any("demo" in r for r in d.reasons)


def test_kill_switch_blocks():
    cfg = SafetyConfig(kill_switch=True)
    d = evaluate_demo_order(**_approve_kwargs(config=cfg))
    assert d.approved is False
    assert any("KILL_SWITCH" in r for r in d.reasons)


def test_live_or_real_flags_block():
    d1 = evaluate_demo_order(**_approve_kwargs(config=SafetyConfig(live_trading_enabled=True)))
    d2 = evaluate_demo_order(**_approve_kwargs(config=SafetyConfig(allow_real_orders=True)))
    assert d1.approved is False and d2.approved is False


def test_missing_sl_or_tp_blocks():
    assert evaluate_demo_order(**_approve_kwargs(sl_present=False)).approved is False
    assert evaluate_demo_order(**_approve_kwargs(tp_present=False)).approved is False


def test_volume_bounds():
    assert evaluate_demo_order(**_approve_kwargs(volume=0)).approved is False
    assert evaluate_demo_order(
        **_approve_kwargs(volume=DEFAULT_MAX_VOLUME + 1)).approved is False


def test_daily_trade_cap_blocks():
    cfg = SafetyConfig(max_trades_per_day=3)
    assert evaluate_demo_order(**_approve_kwargs(config=cfg, trades_today=3)).approved is False
    assert evaluate_demo_order(**_approve_kwargs(config=cfg, trades_today=2)).approved is True


def test_bad_side_blocks():
    assert evaluate_demo_order(**_approve_kwargs(side="hold")).approved is False


# ── config from_env stays safe ────────────────────────────────────────────────
def test_safety_config_from_env_defaults_safe(monkeypatch):
    for k in ("MT5_DEMO_ONLY", "LIVE_TRADING_ENABLED", "ALLOW_REAL_ORDERS",
              "GOLD_BOT_KILL_SWITCH", "GOLD_BOT_MAX_TRADES_PER_DAY"):
        monkeypatch.delenv(k, raising=False)
    cfg = SafetyConfig.from_env()
    assert cfg.mt5_demo_only is True
    assert cfg.live_trading_enabled is False
    assert cfg.allow_real_orders is False
    assert cfg.kill_switch is False
    assert cfg.max_trades_per_day is None   # high-activity: no fixed cap by default


def test_safety_config_from_env_reads_overrides(monkeypatch):
    monkeypatch.setenv("GOLD_BOT_KILL_SWITCH", "true")
    monkeypatch.setenv("GOLD_BOT_MAX_TRADES_PER_DAY", "5")
    cfg = SafetyConfig.from_env()
    assert cfg.kill_switch is True
    assert cfg.max_trades_per_day == 5


def test_high_activity_default_has_no_trade_cap():
    # Default config: no cap, so even many trades pass the count check.
    d = evaluate_demo_order(**_approve_kwargs(trades_today=999))
    assert d.approved is True


def test_explicit_cap_still_blocks():
    cfg = SafetyConfig(max_trades_per_day=1)
    assert evaluate_demo_order(**_approve_kwargs(config=cfg, trades_today=1)).approved is False
    assert evaluate_demo_order(**_approve_kwargs(config=cfg, trades_today=0)).approved is True


# ── journal ───────────────────────────────────────────────────────────────────
def test_journal_append_and_count_today(tmp_path):
    path = tmp_path / "j.jsonl"
    journal.append_entry({"mode": journal.MODE_DEMO_ORDER, "account_server": "S",
                          "account_login": 1, "timestamp": "2026-06-12T10:00:00+00:00"}, path)
    journal.append_entry({"mode": journal.MODE_DRY_RUN, "account_server": "S",
                          "account_login": 1, "timestamp": "2026-06-12T11:00:00+00:00"}, path)
    journal.append_entry({"mode": journal.MODE_DEMO_ORDER, "account_server": "S",
                          "account_login": 1, "timestamp": "2026-06-11T10:00:00+00:00"}, path)
    import datetime as dt
    now = dt.datetime(2026, 6, 12, 23, 0, tzinfo=dt.timezone.utc)
    # only the one sent demo_order dated 2026-06-12 counts
    assert journal.count_sent_today(server="S", login=1, path=path, now=now) == 1


def test_journal_missing_file_is_empty(tmp_path):
    assert journal.read_entries(tmp_path / "none.jsonl") == []


# ── LM75C: close evaluation ───────────────────────────────────────────────────
from services.gold_bot_risk_gate import evaluate_demo_close  # noqa: E402


def _close_kwargs(**over):
    base = dict(config=SafetyConfig(), account_is_demo=True, ticket_found=True,
                volume=0.01, emergency=False)
    base.update(over)
    return base


def test_clean_close_is_approved():
    assert evaluate_demo_close(**_close_kwargs()).approved is True


def test_close_blocked_when_ticket_missing():
    assert evaluate_demo_close(**_close_kwargs(ticket_found=False)).approved is False


def test_close_blocked_on_non_demo():
    assert evaluate_demo_close(**_close_kwargs(account_is_demo=False)).approved is False


def test_close_blocked_by_kill_switch_without_emergency():
    cfg = SafetyConfig(kill_switch=True)
    assert evaluate_demo_close(**_close_kwargs(config=cfg)).approved is False


def test_emergency_close_overrides_kill_switch_demo_only():
    cfg = SafetyConfig(kill_switch=True)
    d = evaluate_demo_close(**_close_kwargs(config=cfg, emergency=True))
    assert d.approved is True
    assert any("EMERGENCY" in w for w in d.warnings)


def test_emergency_close_still_blocked_on_non_demo():
    cfg = SafetyConfig(kill_switch=True)
    d = evaluate_demo_close(**_close_kwargs(config=cfg, emergency=True, account_is_demo=False))
    assert d.approved is False


# ── LM75D: evaluate_risk_plan ─────────────────────────────────────────────────
from services.gold_bot_risk_gate import evaluate_risk_plan  # noqa: E402


def _plan_kwargs(**over):
    base = dict(
        config=SafetyConfig(), account_is_demo=True, side="buy", volume=0.1,
        sl_present=True, tp_present=True, est_sl_loss=30.0, require_risk_calc=True,
        margin_required=238.0, free_margin=10000.0, equity=10000.0,
        daily_realized_pnl=0.0, trades_today=0, risk_pct=0.5,
    )
    base.update(over)
    return base


def test_risk_plan_approves_and_reports_budget():
    d = evaluate_risk_plan(**_plan_kwargs())
    assert d.approved is True
    assert d.info["remaining_daily_budget"] == pytest.approx(700.0)  # 7% of 10000
    assert d.info["margin_allowed"] == pytest.approx(1000.0)         # 10% of free margin


def test_risk_plan_blocks_when_sl_loss_exceeds_budget():
    # already down 690 today, budget left 10; SL loss 30 > 10
    d = evaluate_risk_plan(**_plan_kwargs(daily_realized_pnl=-690.0, est_sl_loss=30.0))
    assert d.approved is False
    assert any("remaining daily budget" in r for r in d.reasons)


def test_risk_plan_blocks_when_daily_stop_reached():
    d = evaluate_risk_plan(**_plan_kwargs(daily_realized_pnl=-700.0))
    assert d.approved is False
    assert any("hard stop" in r for r in d.reasons)


def test_risk_plan_blocks_when_margin_exceeds_allowance():
    d = evaluate_risk_plan(**_plan_kwargs(margin_required=2000.0))  # > 10% of 10000
    assert d.approved is False
    assert any("margin" in r for r in d.reasons)


def test_risk_plan_fails_closed_when_risk_calc_required_but_missing():
    d = evaluate_risk_plan(**_plan_kwargs(est_sl_loss=None, require_risk_calc=True))
    assert d.approved is False
    assert any("could not be computed" in r for r in d.reasons)


def test_risk_plan_manual_volume_warns_not_blocks_on_missing_calc():
    d = evaluate_risk_plan(**_plan_kwargs(est_sl_loss=None, require_risk_calc=False,
                                          margin_required=238.0))
    # missing SL calc is only a warning for manual volume
    assert d.approved is True
    assert any("estimated SL loss unavailable" in w for w in d.warnings)


# ── fail-closed: missing/zero account numbers must BLOCK, not silently pass ────
def test_risk_plan_blocks_on_zero_equity():
    # A blown/zero account: equity == 0.0 must hard-block, not slip through as a
    # soft "unavailable" warning (the old `if equity and equity > 0` truthiness bug).
    d = evaluate_risk_plan(**_plan_kwargs(equity=0.0))
    assert d.approved is False
    assert any("blown or zero" in r for r in d.reasons)


def test_risk_plan_blocks_on_negative_equity():
    d = evaluate_risk_plan(**_plan_kwargs(equity=-5.0))
    assert d.approved is False
    assert any("blown or zero" in r for r in d.reasons)


def test_risk_plan_blocks_when_equity_unavailable_and_risk_calc_required():
    # Account read failed → equity None. On the sizing path (require_risk_calc) this
    # must fail closed, not approve on an unverifiable daily-loss budget.
    d = evaluate_risk_plan(**_plan_kwargs(equity=None, require_risk_calc=True))
    assert d.approved is False
    assert any("equity unavailable" in r for r in d.reasons)


def test_risk_plan_warns_when_equity_unavailable_on_manual_path():
    d = evaluate_risk_plan(**_plan_kwargs(equity=None, require_risk_calc=False,
                                          est_sl_loss=None))
    assert d.approved is True
    assert any("equity unavailable" in w for w in d.warnings)


def test_risk_plan_blocks_when_today_pnl_unavailable_and_risk_calc_required():
    # History read failed → daily_realized_pnl None. Budget unverifiable → block.
    d = evaluate_risk_plan(**_plan_kwargs(daily_realized_pnl=None, require_risk_calc=True))
    assert d.approved is False
    assert any("daily realized PnL unavailable" in r for r in d.reasons)


def test_risk_plan_warns_when_today_pnl_unavailable_on_manual_path():
    d = evaluate_risk_plan(**_plan_kwargs(daily_realized_pnl=None, require_risk_calc=False,
                                          est_sl_loss=None))
    assert d.approved is True
    assert any("daily realized PnL unavailable" in w for w in d.warnings)


def test_risk_plan_blocks_when_free_margin_unavailable():
    # margin_required known but free margin missing → cannot prove affordability.
    d = evaluate_risk_plan(**_plan_kwargs(free_margin=None))
    assert d.approved is False
    assert any("free margin unavailable" in r for r in d.reasons)


def test_risk_plan_blocks_on_zero_free_margin():
    # free_margin == 0.0 must block, not silently skip the margin check (truthiness bug).
    d = evaluate_risk_plan(**_plan_kwargs(free_margin=0.0))
    assert d.approved is False
    assert any("no margin available" in r for r in d.reasons)


def test_risk_plan_winning_day_keeps_full_budget():
    # A profitable day (positive realized PnL) must leave the FULL daily-loss budget
    # intact and approve — guards against a sign-flip granting unlimited budget.
    d = evaluate_risk_plan(**_plan_kwargs(daily_realized_pnl=500.0))
    assert d.approved is True
    assert d.info["remaining_daily_budget"] == pytest.approx(700.0)  # 7% of 10000, no loss
