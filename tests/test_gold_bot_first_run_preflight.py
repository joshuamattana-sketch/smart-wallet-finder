"""
tests/test_gold_bot_first_run_preflight.py
-------------------------------------------
LM92B - First market-open preflight (GO/NO-GO). Subprocess + safety/macro mocked;
no MT5, no Discord, no internet.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from services.gold_bot_first_run_preflight import (
    REQUIRED_SCRIPTS,
    PreflightConfig,
    run_preflight,
)

NOW = datetime(2026, 6, 13, 12, 0, 0, tzinfo=timezone.utc)
_REPO = Path(__file__).resolve().parent.parent

_DEFAULTS = {
    "run_gold_bot_daily_cycle.py": (0, "GOLD BOT DAILY CYCLE (PLAN (dry-run))"),
    "run_mt5_demo_connector_probe.py": (0, "tick fresh ... READ ONLY - NO ORDERS SENT"),
    "run_gold_bot_safety_probe.py": (0, "cooldown   : none active"),
}


class FakeRunner:
    def __init__(self, overrides=None):
        self.calls = []
        self.o = overrides or {}

    def __call__(self, cmd, *, cwd, timeout):
        self.calls.append(cmd)
        name = next((Path(c).name for c in cmd if c.endswith(".py")), "")
        rc, out = self.o.get(name, _DEFAULTS.get(name, (0, "ok")))
        return SimpleNamespace(returncode=rc, stdout=out, stderr="")


def _repo(tmp_path, *, scripts=None):
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    for s in (scripts if scripts is not None else REQUIRED_SCRIPTS):
        (root / "scripts" / s).write_text("# stub", encoding="utf-8")
    (root / "data" / "gold_bot").mkdir(parents=True)
    return root


def _run(tmp_path, cfg=None, *, runner=None, kill=False, live=False, macro="clear", scripts=None):
    root = _repo(tmp_path, scripts=scripts)
    sc = SimpleNamespace(kill_switch=kill, live_trading_enabled=live, allow_real_orders=False)
    return run_preflight(cfg or PreflightConfig(), repo_root=root, out_dir=tmp_path / "pf",
                         runner_fn=runner or FakeRunner(), safety_config_fn=lambda: sc,
                         macro_state_fn=lambda: macro, now_fn=lambda: NOW)


def _check(pf, name):
    return next(c for c in pf.checks if c["name"] == name)


# ── GO ────────────────────────────────────────────────────────────────────────────
def test_go_when_all_checks_pass(tmp_path):
    pf = _run(tmp_path)
    assert pf.overall == "GO" and pf.go is True
    assert _check(pf, "required_scripts")["status"] == "PASS"
    assert _check(pf, "mt5_demo_tick")["status"] == "PASS"
    assert _check(pf, "safety_probe")["status"] == "PASS"


def test_go_command_has_conservative_caps(tmp_path):
    pf = _run(tmp_path, PreflightConfig(use_learning_modifiers=True, include_real_trades=True))
    cmd = pf.go_command
    assert "-Execute" in cmd and "-ConfirmDemoSession" in cmd
    assert "-DurationMinutes 5.0" in cmd and "-MaxTrades 3" in cmd and "-RiskMode scalp" in cmd
    assert "-UseLearningModifiers" in cmd and "-IncludeRealTrades" in cmd


# ── NO-GO conditions ──────────────────────────────────────────────────────────────
def test_required_script_missing_is_nogo(tmp_path):
    pf = _run(tmp_path, scripts=[s for s in REQUIRED_SCRIPTS if s != "run_gold_bot_daily_cycle.py"])
    assert pf.go is False
    assert _check(pf, "required_scripts")["status"] == "FAIL"


def test_stale_tick_is_nogo(tmp_path):
    r = FakeRunner({"run_mt5_demo_connector_probe.py": (0, "warning: market closed, last tick old")})
    pf = _run(tmp_path, runner=r)
    assert pf.go is False and _check(pf, "mt5_demo_tick")["status"] == "FAIL"


def test_mt5_probe_failure_is_nogo(tmp_path):
    r = FakeRunner({"run_mt5_demo_connector_probe.py": (1, "could not initialize MT5")})
    pf = _run(tmp_path, runner=r)
    assert pf.go is False and _check(pf, "mt5_demo_tick")["status"] == "FAIL"


def test_safety_block_is_nogo(tmp_path):
    r = FakeRunner({"run_gold_bot_safety_probe.py": (0, "COOLDOWN   : ACTIVE until 2026-06-13T12:30")})
    pf = _run(tmp_path, runner=r)
    assert pf.go is False and _check(pf, "safety_probe")["status"] == "FAIL"


def test_daily_cycle_plan_failure_is_nogo(tmp_path):
    r = FakeRunner({"run_gold_bot_daily_cycle.py": (1, "boom")})
    pf = _run(tmp_path, runner=r)
    assert pf.go is False and _check(pf, "daily_cycle_plan")["status"] == "FAIL"


def test_kill_switch_active_is_nogo(tmp_path):
    pf = _run(tmp_path, kill=True)
    assert pf.go is False and _check(pf, "kill_switch")["status"] == "FAIL"


def test_live_flag_is_nogo(tmp_path):
    pf = _run(tmp_path, live=True)
    assert pf.go is False and _check(pf, "kill_switch")["status"] == "FAIL"


def test_macro_lockout_is_nogo(tmp_path):
    pf = _run(tmp_path, macro="lockout")
    assert pf.go is False and _check(pf, "macro_lockout")["status"] == "FAIL"


# ── skip modes (weekend / offline prep) ───────────────────────────────────────────
def test_skip_mt5_is_skip_not_fail(tmp_path):
    pf = _run(tmp_path, PreflightConfig(skip_mt5=True))
    assert _check(pf, "mt5_demo_tick")["status"] == "SKIP"
    assert pf.go is True            # skip does not block


def test_skip_safety_is_skip_not_fail(tmp_path):
    pf = _run(tmp_path, PreflightConfig(skip_safety=True))
    assert _check(pf, "safety_probe")["status"] == "SKIP"
    assert pf.go is True


def test_offline_prep_skip_both_is_go(tmp_path):
    r = FakeRunner()
    pf = _run(tmp_path, PreflightConfig(skip_mt5=True, skip_safety=True), runner=r)
    assert pf.go is True
    # mt5/safety probes were never invoked
    called = [Path(c[1]).name for c in r.calls]
    assert "run_mt5_demo_connector_probe.py" not in called
    assert "run_gold_bot_safety_probe.py" not in called


# ── discord (no webhook read unless asked) ────────────────────────────────────────
def test_discord_not_inspected_by_default(tmp_path):
    pf = _run(tmp_path)
    assert "no env checked" in _check(pf, "discord")["detail"]


def test_discord_env_presence_only_when_requested(tmp_path, monkeypatch):
    monkeypatch.delenv("LUMORA_GOLD_DISCORD_WEBHOOK_URL", raising=False)
    pf = _run(tmp_path, PreflightConfig(check_discord_env=True))
    d = _check(pf, "discord")
    assert d["status"] == "WARN" and "not set" in d["detail"]


def test_send_discord_in_go_command(tmp_path):
    pf = _run(tmp_path, PreflightConfig(send_discord=True))
    assert "-SendDiscord" in pf.go_command


# ── write ──────────────────────────────────────────────────────────────────────────
def test_no_write_by_default(tmp_path):
    pf = _run(tmp_path)
    assert pf.preflight_path is None and not (tmp_path / "pf").exists()


def test_write_creates_json(tmp_path):
    pf = _run(tmp_path, PreflightConfig(write=True))
    assert pf.preflight_path and Path(pf.preflight_path).exists()
    assert (tmp_path / "pf" / "preflight_latest.json").exists()
    data = json.loads(Path(pf.preflight_path).read_text())
    assert data["overall"] == "GO" and "checks" in data


# ── safety: read-only, no orders/MT5 ──────────────────────────────────────────────
def test_no_mt5_imported_during_mocked_run(tmp_path):
    _run(tmp_path)
    assert "MetaTrader5" not in sys.modules


def test_source_has_no_orders_or_mt5_import():
    src = (_REPO / "services" / "gold_bot_first_run_preflight.py").read_text(encoding="utf-8")
    for forbidden in ("import MetaTrader5", "order_send", "send_demo_order", "--confirm-demo-order",
                      "--auto-execute-demo"):
        assert forbidden not in src, f"preflight must not contain {forbidden}"


def test_generated_preflight_gitignored():
    gi = (_REPO / ".gitignore").read_text(encoding="utf-8")
    assert "data/gold_bot/preflight/" in gi


# ── CLI ─────────────────────────────────────────────────────────────────────────────
def _load_cli():
    spec = importlib.util.spec_from_file_location(
        "run_gold_bot_first_run_preflight", _REPO / "scripts" / "run_gold_bot_first_run_preflight.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_cli_defaults():
    cli = _load_cli()
    a = cli.parse_args([])
    assert a.skip_mt5 is False and a.skip_safety is False and a.write is False
    assert a.duration_minutes == 5.0 and a.max_trades == 3 and a.risk_mode == "scalp"
    assert a.check_discord_env is False and a.send_discord is False
