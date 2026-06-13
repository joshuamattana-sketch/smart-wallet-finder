"""
tests/test_gold_bot_demo_session_runner.py
-------------------------------------------
LM88A - Bounded demo auto-session runner. Pure orchestration: no MT5, no internet.
The worker is faked (scripted iterations) so whole sessions run offline.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

from services.gold_bot_demo_session_runner import (
    DemoSessionConfig,
    DemoSessionRunner,
)
from services.gold_bot_worker import WorkerConfig

NOW = datetime(2026, 6, 13, 13, 0, 0, tzinfo=timezone.utc)
_REPO = Path(__file__).resolve().parent.parent


def _entry(*, decision="NO_TRADE", strategy="no_trade", status="simulated_opportunity",
           equity=10000.0, pnl=0.0, severity="info", open_pos=0, conf=70, macro="clear"):
    blocked = status == "blocked_by_safety_supervisor"
    return {"decision": decision, "strategy": strategy, "confidence": conf,
            "execution_status": status, "open_positions": open_pos, "equity": equity,
            "today_pnl": pnl, "macro_event_state": macro, "reasons": [],
            "safety": {"allowed": not blocked, "severity": severity,
                       "reason": ("kill_switch" if severity == "critical" else "spread_guard")
                       if blocked else "all_clear", "cooldown_until": None}}


class FakeWorker:
    """Drives the runner's iteration hook with scripted entries (mirrors the real loop)."""

    def __init__(self, worker_cfg, hook, entries, *, learning_modifiers=None,
                 learning_safety=None, learning_warns=None):
        self.cfg = worker_cfg
        self._hook = hook
        self._entries = entries
        self.iterations = []
        self.stop_reason = None
        self._learning_modifiers = learning_modifiers or {}
        self._learning_safety = learning_safety
        self._learning_warns = learning_warns or []

    def run(self):
        i = 0
        for e in self._entries:
            if self.cfg.max_iterations is not None and i >= self.cfg.max_iterations:
                break
            i += 1
            self.iterations.append(e)
            reason = self._hook(e)
            if reason:
                self.stop_reason = reason
                break
        return 0


def _runner(cfg, tmp_path, entries, holder=None, *, outcome_sync_fn=None, **fwkw):
    # Default to a stub so a test NEVER triggers the real MT5 outcome sync.
    outcome_sync_fn = outcome_sync_fn or (lambda **k: {"synced": False, "reason": "test_stub"})

    def factory(worker_cfg, hook):
        if holder is not None:
            holder["cfg"] = worker_cfg
        return FakeWorker(worker_cfg, hook, entries, **fwkw)
    return DemoSessionRunner(cfg, worker_factory=factory, sessions_dir=tmp_path,
                             outcome_sync_fn=outcome_sync_fn,
                             now_fn=lambda: NOW, printer=lambda *_a: None)


# ── arming ──────────────────────────────────────────────────────────────────────
def test_session_without_confirm_runs_observe_no_orders(tmp_path):
    holder = {}
    cfg = DemoSessionConfig(max_iterations=3, duration_minutes=60)
    r = _runner(cfg, tmp_path, [_entry() for _ in range(3)], holder).run()
    assert holder["cfg"].mode == "observe"
    assert holder["cfg"].auto_execute_demo is False
    assert holder["cfg"].confirm_demo_order is False
    assert r.report["mode"] == "observe" and r.report["armed"] is False
    assert r.report["demo_orders_sent"] == 0
    assert any("observe only" in w.lower() for w in r.report["warnings"])


def test_session_with_confirm_arms_demo_flags(tmp_path):
    holder = {}
    cfg = DemoSessionConfig(max_iterations=1, duration_minutes=60, confirm_demo_session=True)
    _runner(cfg, tmp_path, [_entry()], holder).run()
    assert holder["cfg"].mode == "demo"
    assert holder["cfg"].auto_execute_demo is True
    assert holder["cfg"].confirm_demo_order is True


def test_dry_run_forces_observe_even_if_confirmed(tmp_path):
    holder = {}
    cfg = DemoSessionConfig(max_iterations=1, duration_minutes=60,
                            confirm_demo_session=True, dry_run=True)
    _runner(cfg, tmp_path, [_entry()], holder).run()
    assert holder["cfg"].mode == "observe"
    assert holder["cfg"].auto_execute_demo is False


# ── stop conditions ──────────────────────────────────────────────────────────────
def test_session_stops_at_duration(tmp_path):
    cfg = DemoSessionConfig(duration_minutes=0.0, max_iterations=None)   # deadline 0 -> stop iter 1
    r = _runner(cfg, tmp_path, [_entry() for _ in range(5)]).run()
    assert r.report["stop_reason"] == "duration_reached"
    assert r.report["iterations"] == 1


def test_session_stops_at_max_iterations(tmp_path):
    cfg = DemoSessionConfig(max_iterations=3, duration_minutes=600)
    r = _runner(cfg, tmp_path, [_entry() for _ in range(10)]).run()
    assert r.report["stop_reason"] == "max_iterations_reached"
    assert r.report["iterations"] == 3


def test_session_stops_at_max_trades(tmp_path):
    cfg = DemoSessionConfig(max_trades=2, duration_minutes=600, confirm_demo_session=True)
    sent = [_entry(decision="LONG", strategy="momentum", status="demo_order_sent") for _ in range(5)]
    r = _runner(cfg, tmp_path, sent).run()
    assert r.report["stop_reason"] == "max_trades_reached"
    assert r.report["demo_orders_sent"] == 2
    assert r.report["iterations"] == 2


def test_session_stops_on_critical_safety(tmp_path):
    cfg = DemoSessionConfig(duration_minutes=600, confirm_demo_session=True)
    entries = [_entry(decision="LONG", status="blocked_by_safety_supervisor", severity="critical")]
    r = _runner(cfg, tmp_path, entries + [_entry() for _ in range(3)]).run()
    assert r.report["stop_reason"] == "critical_safety"
    assert r.report["iterations"] == 1
    assert r.report["blocked_by_safety_count"] == 1


def test_session_stops_on_consecutive_safety_blocks(tmp_path):
    cfg = DemoSessionConfig(duration_minutes=600, confirm_demo_session=True)
    blocks = [_entry(decision="LONG", status="blocked_by_safety_supervisor", severity="block")
              for _ in range(4)]
    r = _runner(cfg, tmp_path, blocks).run()
    assert r.report["stop_reason"] == "consecutive_safety_blocks"
    assert r.report["iterations"] == 3
    assert r.report["blocked_reasons"].get("spread_guard") == 3


def test_session_stops_on_runtime_loss(tmp_path):
    cfg = DemoSessionConfig(duration_minutes=600, max_runtime_loss_pct=3.0,
                            confirm_demo_session=True)
    entries = [_entry(equity=10000.0), _entry(equity=9600.0)]   # -4% -> stop
    r = _runner(cfg, tmp_path, entries).run()
    assert r.report["stop_reason"] == "runtime_loss_limit"
    assert r.report["runtime_loss_pct"] == 4.0


# ── report + events ──────────────────────────────────────────────────────────────
def test_session_report_contains_required_fields(tmp_path):
    cfg = DemoSessionConfig(max_iterations=2, duration_minutes=600)
    r = _runner(cfg, tmp_path, [_entry(decision="LONG", strategy="momentum"),
                                _entry(decision="SHORT", strategy="fvg_retest")],
                learning_modifiers={"momentum": {"confidence_modifier": -8}},
                learning_safety={"allowed": True}).run()
    rep = r.report
    for key in ("session_id", "started_at", "ended_at", "duration_seconds", "symbol",
                "risk_mode", "mode", "learning_enabled", "active_modifiers_count",
                "iterations", "decisions", "demo_orders_attempted", "demo_orders_sent",
                "blocked_by_safety_count", "blocked_reasons", "macro_lockout_count",
                "no_trade_count", "long_count", "short_count", "starting_equity",
                "ending_equity", "realized_pnl", "stop_reason", "warnings"):
        assert key in rep, f"missing report field {key}"
    assert rep["long_count"] == 1 and rep["short_count"] == 1
    assert rep["active_modifiers_count"] == 1
    assert rep["live_trading"] == "never" and rep["safety_supervisor"] == "always_on"


def test_session_writes_report_and_latest(tmp_path):
    cfg = DemoSessionConfig(max_iterations=1, duration_minutes=600)
    r = _runner(cfg, tmp_path, [_entry()]).run()
    assert r.report_path.exists() and r.latest_path.exists()
    assert (tmp_path / "session_latest.json").exists()
    assert json.loads(r.latest_path.read_text())["session_id"] == r.report["session_id"]


def test_session_jsonl_events_written(tmp_path):
    cfg = DemoSessionConfig(max_iterations=2, duration_minutes=600, confirm_demo_session=True)
    r = _runner(cfg, tmp_path, [_entry(decision="LONG", status="demo_order_sent"),
                                _entry(decision="SHORT", status="risk_blocked")]).run()
    lines = [json.loads(x) for x in r.events_path.read_text().strip().splitlines()]
    events = [l["event"] for l in lines]
    assert events[0] == "session_start"
    assert events[-1] == "session_stop"
    assert "heartbeat" in events and "decision" in events
    assert "order_sent" in events and "order_attempt" in events


def test_macro_lockout_counted(tmp_path):
    cfg = DemoSessionConfig(max_iterations=1, duration_minutes=600)
    r = _runner(cfg, tmp_path, [_entry(decision="NO_TRADE", strategy="macro_lockout",
                                       macro="lockout")]).run()
    assert r.report["macro_lockout_count"] == 1


# ── safety supervisor cannot be disabled by the session ───────────────────────────
def test_runner_never_disables_supervisor(tmp_path):
    # The worker config the runner builds has no supervisor off switch, and the
    # runner never passes one.
    cfg = DemoSessionConfig(max_iterations=1, duration_minutes=600)
    holder = {}
    _runner(cfg, tmp_path, [_entry()], holder).run()
    assert not hasattr(holder["cfg"], "disable_safety_supervisor")
    src = (_REPO / "services" / "gold_bot_demo_session_runner.py").read_text(encoding="utf-8")
    assert "disable_safety_supervisor" not in src    # no off switch
    # the worker the runner builds gets NO supervisor override -> it constructs its own always-on one
    assert "GoldBotWorker(worker_cfg, connector=self._connector, iteration_hook=hook" in src


def test_no_live_trading_or_network_in_sources():
    config_blob = DemoSessionConfig().__dict__
    for forbidden in ("live", "live_trading", "allow_real"):
        assert forbidden not in config_blob
    for fname in ("services/gold_bot_demo_session_runner.py", "scripts/run_gold_bot_demo_session.py"):
        src = (_REPO / fname).read_text(encoding="utf-8")
        for forbidden in ("MetaTrader5", ".order_send(", "import requests", "urllib", "socket(",
                          "live_trading_enabled=True", "allow_real_orders=True"):
            assert forbidden not in src, f"{fname} must not reference {forbidden}"


# ── PowerShell launcher ───────────────────────────────────────────────────────────
def test_powershell_script_exists_and_not_armed_by_default():
    ps = _REPO / "scripts" / "start_gold_bot_demo_session.ps1"
    assert ps.exists()
    text = ps.read_text(encoding="utf-8")
    assert "-ConfirmDemoSession" in text
    # default (no-confirm) branch must NOT pass --confirm-demo-session
    observe_branch = text.split("if (-not $ConfirmDemoSession)")[1].split("exit $LASTEXITCODE")[0]
    assert "--confirm-demo-session" not in observe_branch


# ── CLI defaults ───────────────────────────────────────────────────────────────────
def _load_cli():
    spec = importlib.util.spec_from_file_location(
        "run_gold_bot_demo_session", _REPO / "scripts" / "run_gold_bot_demo_session.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_cli_args_defaults_and_confirm_flag():
    cli = _load_cli()
    args = cli.parse_args([])
    assert args.symbol == "XAUUSD" and args.risk_mode == "scalp" and args.timeframe == "M1"
    assert args.duration_minutes == 30.0 and args.max_trades == 10
    assert args.max_runtime_loss_pct == 3.0
    assert args.use_learning_modifiers is True
    assert args.confirm_demo_session is False
    assert cli.parse_args(["--no-learning-modifiers"]).use_learning_modifiers is False
    assert cli.parse_args(["--confirm-demo-session"]).confirm_demo_session is True


def test_session_config_armed_property():
    assert DemoSessionConfig(confirm_demo_session=True).armed is True
    assert DemoSessionConfig(confirm_demo_session=True, dry_run=True).armed is False
    assert DemoSessionConfig().armed is False


# ── LM89A: post-session outcome sync ──────────────────────────────────────────────
def test_observe_session_skips_outcome_sync(tmp_path):
    called = []

    def sync_fn(**kw):
        called.append(kw)
        return {"synced": True}

    cfg = DemoSessionConfig(max_iterations=1, duration_minutes=600)   # not armed
    r = _runner(cfg, tmp_path, [_entry()], outcome_sync_fn=sync_fn).run()
    assert called == []                                              # never invoked in observe
    assert r.report["outcomes_synced"] is False
    assert r.report["outcome_sync_reason"] == "observe_session"


def test_armed_session_records_outcome_summary(tmp_path):
    captured = {}

    def sync_fn(*, session_id, from_time, to_time):
        captured["session_id"] = session_id
        return {"synced": True, "outcomes_count": 2, "wins": 1, "losses": 1, "breakeven": 0,
                "open": 0, "realized_pnl": 20.0, "outcome_file": "outcomes_x.json",
                "safety_state_updated": True, "reason": "ok", "warnings": []}

    cfg = DemoSessionConfig(max_iterations=1, duration_minutes=600, confirm_demo_session=True)
    r = _runner(cfg, tmp_path, [_entry(decision="LONG", status="demo_order_sent")],
                outcome_sync_fn=sync_fn).run()
    rep = r.report
    assert rep["outcomes_synced"] is True and rep["outcomes_count"] == 2
    assert rep["outcome_wins"] == 1 and rep["outcome_losses"] == 1
    assert rep["outcome_realized_pnl"] == 20.0 and rep["safety_state_updated"] is True
    assert rep["outcome_file"] == "outcomes_x.json"
    assert captured["session_id"] == rep["session_id"]
    events = [json.loads(x) for x in r.events_path.read_text().strip().splitlines()]
    assert any(e["event"] == "outcome_sync" for e in events)


def test_no_sync_outcomes_flag_skips(tmp_path):
    called = []
    cfg = DemoSessionConfig(max_iterations=1, duration_minutes=600,
                            confirm_demo_session=True, sync_outcomes=False)
    r = _runner(cfg, tmp_path, [_entry()], outcome_sync_fn=lambda **k: called.append(k)).run()
    assert called == []
    assert r.report["outcomes_synced"] is False
    assert r.report["outcome_sync_reason"] == "sync_outcomes_disabled"


def test_outcome_sync_error_is_safe(tmp_path):
    def boom(**kw):
        raise RuntimeError("mt5 down")

    cfg = DemoSessionConfig(max_iterations=1, duration_minutes=600, confirm_demo_session=True)
    r = _runner(cfg, tmp_path, [_entry()], outcome_sync_fn=boom).run()
    assert r.report["outcomes_synced"] is False
    assert "sync_error" in r.report["outcome_sync_reason"]
