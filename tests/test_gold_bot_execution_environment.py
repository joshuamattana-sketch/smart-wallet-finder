"""
tests/test_gold_bot_execution_environment.py
---------------------------------------------
LM93A - Execution environment model. Pure: no MT5, no internet.
"""

from __future__ import annotations

from pathlib import Path

from services.gold_bot_execution_environment import (
    DEMO_ALLOWED,
    LIVE_ENV_TOKEN,
    LIVE_ENV_VAR,
    LIVE_IMPLEMENTED,
    LIVE_NOT_IMPLEMENTED,
    OBSERVE_ONLY,
    PAPER_NO_BROKER,
    UNKNOWN_ACCOUNT,
    account_type_from_info,
    assert_execution_allowed,
    build_execution_context,
    context_from_legacy_mode,
    describe_execution_context,
    is_demo_execution,
    is_live_blocked,
    live_lock_active,
    normalize_environment,
    normalize_mode,
)

_REPO = Path(__file__).resolve().parent.parent
DEMO_INFO = {"demo_verified": True, "trade_mode_label": "demo"}
LIVE_INFO = {"demo_verified": False, "trade_mode_label": "real"}


# ── normalization ─────────────────────────────────────────────────────────────────
def test_normalize_environment():
    assert normalize_environment("demo") == "demo"
    assert normalize_environment("PAPER") == "paper"
    assert normalize_environment("live") == "live"
    assert normalize_environment("garbage") == "demo"      # safe default
    assert normalize_environment(None) == "demo"


def test_normalize_mode_legacy():
    assert normalize_mode("observe") == "observe"
    assert normalize_mode("demo") == "execute"             # legacy --mode demo => execute
    assert normalize_mode("execute") == "execute"
    assert normalize_mode("weird") == "observe"            # safe default


def test_account_type_from_info():
    assert account_type_from_info(DEMO_INFO) == "demo"
    assert account_type_from_info(LIVE_INFO) == "live"
    assert account_type_from_info({"trade_mode_label": "live"}) == "live"
    assert account_type_from_info(None) == "unknown"
    assert account_type_from_info({}) == "unknown"


# ── observe / paper never send ────────────────────────────────────────────────────
def test_observe_blocks_orders():
    ctx = build_execution_context("demo", "observe", account_info=DEMO_INFO)
    g = assert_execution_allowed(ctx)
    assert g.allowed is False and g.code == OBSERVE_ONLY and g.level == "pass"


def test_paper_blocks_broker_orders():
    ctx = build_execution_context("paper", "execute")
    g = assert_execution_allowed(ctx)
    assert g.allowed is False and g.code == PAPER_NO_BROKER
    assert ctx.account_type == "paper"


# ── demo execute ──────────────────────────────────────────────────────────────────
def test_demo_execute_allowed_on_demo_account():
    ctx = build_execution_context("demo", "execute", account_info=DEMO_INFO)
    g = assert_execution_allowed(ctx)
    assert g.allowed is True and g.code == DEMO_ALLOWED
    assert is_demo_execution(ctx) is True


def test_demo_execute_blocked_on_unknown_account():
    ctx = build_execution_context("demo", "execute", account_info=None)
    g = assert_execution_allowed(ctx)
    assert g.allowed is False and g.code == UNKNOWN_ACCOUNT and g.level == "block"


def test_demo_execute_blocked_on_live_account():
    ctx = build_execution_context("demo", "execute", account_info=LIVE_INFO)
    g = assert_execution_allowed(ctx)
    assert g.allowed is False and g.level == "block"


# ── live hard-locked ──────────────────────────────────────────────────────────────
def test_live_blocked_by_default():
    ctx = build_execution_context("live", "execute", account_info=LIVE_INFO)
    g = assert_execution_allowed(ctx)
    assert g.allowed is False and g.code == LIVE_NOT_IMPLEMENTED and g.level == "block"
    assert is_live_blocked(ctx) is True


def test_live_still_blocked_with_env_and_flag(monkeypatch):
    monkeypatch.setenv(LIVE_ENV_VAR, LIVE_ENV_TOKEN)
    ctx = build_execution_context("live", "execute", account_info=LIVE_INFO, allow_live_flag=True)
    # both gates present, but live is not implemented -> still refused
    assert ctx.live_enabled is True
    assert assert_execution_allowed(ctx).allowed is False
    assert LIVE_IMPLEMENTED is False and live_lock_active() is True


def test_live_not_enabled_without_both_gates(monkeypatch):
    monkeypatch.delenv(LIVE_ENV_VAR, raising=False)
    ctx = build_execution_context("live", "execute", allow_live_flag=True)  # flag but no env
    assert ctx.live_enabled is False
    assert assert_execution_allowed(ctx).allowed is False


# ── legacy mapping ────────────────────────────────────────────────────────────────
def test_legacy_mode_demo_maps_to_execute():
    ctx = context_from_legacy_mode("demo", account_info=DEMO_INFO)
    assert ctx.environment == "demo" and ctx.mode == "execute"
    assert is_demo_execution(ctx) is True


def test_legacy_mode_observe_maps_to_observe():
    ctx = context_from_legacy_mode("observe")
    assert ctx.mode == "observe"
    assert assert_execution_allowed(ctx).allowed is False


# ── describe ───────────────────────────────────────────────────────────────────────
def test_describe_mentions_environment_and_live_lock():
    text = describe_execution_context(build_execution_context("demo", "execute", account_info=DEMO_INFO))
    assert "environment: demo" in text and "live: locked" in text and "guarded broker demo" in text


# ── safety: no orders/MT5 in the module ───────────────────────────────────────────
def test_module_has_no_orders_or_mt5():
    src = (_REPO / "services" / "gold_bot_execution_environment.py").read_text(encoding="utf-8")
    for forbidden in ("import MetaTrader5", ".order_send(", "send_demo_order", "import requests"):
        assert forbidden not in src


# ── integration: CLIs map/refuse + framing (no MT5, no orders) ─────────────────────
import importlib.util  # noqa: E402


def _load(script):
    spec = importlib.util.spec_from_file_location(script, _REPO / "scripts" / f"{script}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_worker_cli_has_environment_flag_and_refuses_live():
    cli = _load("run_gold_bot_worker")
    assert cli.parse_args([]).environment == "demo"
    assert cli.parse_args(["--mode", "demo"]).mode == "demo"           # legacy flag still works
    assert cli.main(["--environment", "live"]) == 2                    # live refused, nothing runs


def test_demo_session_cli_refuses_live():
    cli = _load("run_gold_bot_demo_session")
    assert cli.parse_args([]).environment == "demo"
    assert cli.main(["--environment", "live"]) == 2


def test_daily_cycle_plan_prints_live_locked(capsys):
    cli = _load("run_gold_bot_daily_cycle")
    rc = cli.main([])                                                  # plan mode, no subprocess
    assert rc == 0
    out = capsys.readouterr().out
    assert "live: locked" in out and "environ" in out


def test_daily_cycle_cli_refuses_live():
    cli = _load("run_gold_bot_daily_cycle")
    assert cli.main(["--environment", "live"]) == 2


def test_preflight_reports_environment_and_live_locked(tmp_path):
    from types import SimpleNamespace
    from services.gold_bot_first_run_preflight import PreflightConfig, run_preflight
    sc = SimpleNamespace(kill_switch=False, live_trading_enabled=False, allow_real_orders=False)
    pf = run_preflight(
        PreflightConfig(skip_mt5=True, skip_safety=True), out_dir=tmp_path / "pf",
        runner_fn=lambda cmd, **k: SimpleNamespace(returncode=0, stdout="PLAN", stderr=""),
        safety_config_fn=lambda: sc, macro_state_fn=lambda: "clear")
    assert pf.environment == "demo" and pf.live_locked is True
    assert pf.execution_mode == "execute_candidate"


def test_preflight_cli_refuses_live():
    cli = _load("run_gold_bot_first_run_preflight")
    assert cli.main(["--environment", "live"]) == 2
