"""
tests/test_gold_bot_command_gateway.py
----------------------------------------
LM94A - Local command gateway. Subprocess + env are mocked; no real commands run,
no MT5, no Discord, no internet.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from services.gold_bot_command_gateway import (
    ALLOWED_ACTIONS,
    ALLOWED_FLAGS,
    DURATION_MAX,
    MAX_TRADES_MAX,
    SCRIPTS,
    WEBHOOK_ENV,
    GatewayRequest,
    build_command,
    redact,
    run_gateway,
    validate,
)

NOW = datetime(2026, 6, 13, 12, 0, 0, tzinfo=timezone.utc)
_REPO = Path(__file__).resolve().parent.parent


class FakeRunner:
    def __init__(self, *, returncode=0, stdout="ok\n", stderr="", raise_timeout=False):
        self.calls: list[tuple] = []
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.raise_timeout = raise_timeout

    def __call__(self, cmd, *, cwd, timeout):
        self.calls.append((cmd, cwd, timeout))
        if self.raise_timeout:
            raise subprocess.TimeoutExpired(cmd, timeout)
        return SimpleNamespace(returncode=self.returncode, stdout=self.stdout, stderr=self.stderr)


def _run(tmp_path, req, runner=None, *, env=None, write_log=False):
    return run_gateway(req, out_dir=tmp_path / "commands",
                       runner_fn=runner or FakeRunner(), now_fn=lambda: NOW,
                       env={} if env is None else env, write_log=write_log)


def _script_in(cmd, key):
    return any(c.endswith(SCRIPTS[key]) for c in cmd)


# ── unknown action ─────────────────────────────────────────────────────────────────
def test_unknown_action_blocked(tmp_path):
    res = _run(tmp_path, GatewayRequest(action="rm_rf_everything"))
    assert res.accepted is False and res.status == "blocked"
    assert "unknown action" in res.reason
    assert build_command(GatewayRequest(action="rm_rf_everything")) is None


def test_unknown_action_never_runs_subprocess(tmp_path):
    def boom(*a, **k):
        raise AssertionError("subprocess called for a blocked action!")
    res = run_gateway(GatewayRequest(action="bogus", dry_run=False),
                      out_dir=tmp_path / "c", runner_fn=boom, now_fn=lambda: NOW, env={})
    assert res.status == "blocked"


# ── dry-run default ────────────────────────────────────────────────────────────────
def test_dry_run_does_not_call_subprocess(tmp_path):
    def boom(*a, **k):
        raise AssertionError("subprocess called in dry-run!")
    res = run_gateway(GatewayRequest(action="preflight", dry_run=True),
                      out_dir=tmp_path / "c", runner_fn=boom, now_fn=lambda: NOW, env={})
    assert res.status == "planned" and res.accepted is True
    assert res.command and "run_gold_bot_first_run_preflight.py" in res.command
    assert not (tmp_path / "c").exists()        # no log without write_log


def test_dry_run_log_only_with_write_log(tmp_path):
    res = _run(tmp_path, GatewayRequest(action="preflight", dry_run=True), write_log=True)
    assert res.status == "planned"
    assert res.generated_files and Path(res.generated_files[0]).exists()


# ── command builders ───────────────────────────────────────────────────────────────
def test_preflight_command_built_correctly():
    cmd = build_command(GatewayRequest(action="preflight",
                                       use_learning_modifiers=True, include_real_trades=True))
    assert _script_in(cmd, "preflight")
    assert "--use-learning-modifiers" in cmd and "--include-real-trades" in cmd
    assert "--send-discord" not in cmd
    # bare preflight has no optional flags
    bare = build_command(GatewayRequest(action="preflight"))
    assert "--use-learning-modifiers" not in bare and "--include-real-trades" not in bare


def test_offline_daily_cycle_command_built_correctly():
    cmd = build_command(GatewayRequest(action="daily_cycle_offline", include_real_trades=True))
    assert _script_in(cmd, "daily_cycle")
    assert "--execute" in cmd and "--skip-session" in cmd          # no demo session
    assert "--include-real-trades" in cmd
    assert "--confirm-demo-session" not in cmd                      # never a demo trade


# ── guarded demo gating + caps ──────────────────────────────────────────────────────
def test_guarded_demo_blocked_without_confirm(tmp_path):
    res = _run(tmp_path, GatewayRequest(action="daily_cycle_guarded_demo"))
    assert res.status == "blocked" and "confirm_guarded_demo" in res.reason


def test_guarded_demo_rejects_duration_over_cap(tmp_path):
    res = _run(tmp_path, GatewayRequest(action="daily_cycle_guarded_demo",
                                        confirm_guarded_demo=True, duration_minutes=DURATION_MAX + 1))
    assert res.status == "blocked" and "duration_minutes" in res.reason and "cap" in res.reason


def test_guarded_demo_rejects_max_trades_over_cap(tmp_path):
    res = _run(tmp_path, GatewayRequest(action="daily_cycle_guarded_demo",
                                        confirm_guarded_demo=True, max_trades=MAX_TRADES_MAX + 1))
    assert res.status == "blocked" and "max_trades" in res.reason


def test_guarded_demo_rejects_aggressive_and_experimental(tmp_path):
    for bad in ("aggressive", "experimental"):
        res = _run(tmp_path, GatewayRequest(action="daily_cycle_guarded_demo",
                                            confirm_guarded_demo=True, risk_mode=bad))
        assert res.status == "blocked" and "risk_mode" in res.reason


def test_guarded_demo_command_uses_existing_safety_path_only():
    cmd = build_command(GatewayRequest(action="daily_cycle_guarded_demo",
                                       confirm_guarded_demo=True, duration_minutes=5,
                                       max_trades=3, risk_mode="scalp"))
    assert _script_in(cmd, "daily_cycle")                           # the guarded path
    assert "--confirm-demo-session" in cmd                          # routes through safety supervisor
    assert "--duration-minutes" in cmd and "5" in cmd
    assert "--risk-mode" in cmd and "scalp" in cmd
    # never any live / environment escape hatch
    assert "--allow-live-trading" not in cmd and "--environment" not in cmd
    assert "live" not in cmd


# ── discord preview vs send ─────────────────────────────────────────────────────────
def test_discord_preview_needs_no_env_no_network(tmp_path):
    accepted, reason, _ = validate(GatewayRequest(action="discord_preview"), env={})
    assert accepted is True and reason is None
    cmd = build_command(GatewayRequest(action="discord_preview"))
    assert _script_in(cmd, "discord_review") and "--send-discord" not in cmd
    # planning makes no subprocess call at all
    def boom(*a, **k):
        raise AssertionError("network/subprocess in preview dry-run!")
    res = run_gateway(GatewayRequest(action="discord_preview", dry_run=True),
                      out_dir=tmp_path / "c", runner_fn=boom, now_fn=lambda: NOW, env={})
    assert res.status == "planned"


def test_discord_send_blocked_without_allow_flag(tmp_path):
    res = _run(tmp_path, GatewayRequest(action="discord_send"),
               env={WEBHOOK_ENV: "https://discord.com/api/webhooks/1/TOKEN"})
    assert res.status == "blocked" and "allow_discord_send" in res.reason


def test_discord_send_blocked_without_env(tmp_path):
    res = _run(tmp_path, GatewayRequest(action="discord_send", allow_discord_send=True), env={})
    assert res.status == "blocked" and WEBHOOK_ENV in res.reason


def test_discord_send_command_built_with_allow_and_env(tmp_path):
    env = {WEBHOOK_ENV: "https://discord.com/api/webhooks/1/TOKEN"}
    accepted, reason, _ = validate(
        GatewayRequest(action="discord_send", allow_discord_send=True), env=env)
    assert accepted is True and reason is None
    cmd = build_command(GatewayRequest(action="discord_send", allow_discord_send=True))
    assert _script_in(cmd, "discord_review") and "--send-discord" in cmd
    # the command itself never carries the webhook value
    assert "TOKEN" not in " ".join(cmd)
    # planned result also free of the secret
    res = run_gateway(GatewayRequest(action="discord_send", allow_discord_send=True, dry_run=True),
                      out_dir=tmp_path / "c", runner_fn=FakeRunner(), now_fn=lambda: NOW, env=env,
                      write_log=True)
    assert res.status == "planned"
    assert "TOKEN" not in Path(res.generated_files[0]).read_text(encoding="utf-8")


# ── webhook redaction ───────────────────────────────────────────────────────────────
def test_redact_unit():
    out = redact("posting to https://discord.com/api/webhooks/123/SECRET now")
    assert "SECRET" not in out and "...REDACTED" in out


def test_webhook_redacted_from_logs(tmp_path):
    leak = "sent to https://discord.com/api/webhooks/999/TOPSECRETTOKEN ok\n"
    runner = FakeRunner(stdout=leak)
    env = {WEBHOOK_ENV: "https://discord.com/api/webhooks/999/TOPSECRETTOKEN"}
    res = run_gateway(GatewayRequest(action="discord_send", allow_discord_send=True, dry_run=False),
                      out_dir=tmp_path / "c", runner_fn=runner, now_fn=lambda: NOW, env=env,
                      write_log=True)
    assert res.status == "success"
    assert "TOPSECRETTOKEN" not in json.dumps(res.to_dict())
    assert res.redactions_applied >= 1
    assert "TOPSECRETTOKEN" not in Path(res.generated_files[0]).read_text(encoding="utf-8")


# ── subprocess success / failure / timeout ──────────────────────────────────────────
def test_subprocess_success(tmp_path):
    res = run_gateway(GatewayRequest(action="session_review", dry_run=False),
                      out_dir=tmp_path / "c", runner_fn=FakeRunner(returncode=0),
                      now_fn=lambda: NOW, env={})
    assert res.status == "success" and res.exit_code == 0
    assert Path(res.generated_files[0]).exists()


def test_subprocess_failure(tmp_path):
    res = run_gateway(GatewayRequest(action="session_review", dry_run=False),
                      out_dir=tmp_path / "c", runner_fn=FakeRunner(returncode=3),
                      now_fn=lambda: NOW, env={})
    assert res.status == "failed" and res.exit_code == 3 and "exit 3" in res.reason


def test_subprocess_timeout(tmp_path):
    res = run_gateway(GatewayRequest(action="session_review", dry_run=False, timeout_seconds=42),
                      out_dir=tmp_path / "c", runner_fn=FakeRunner(raise_timeout=True),
                      now_fn=lambda: NOW, env={})
    assert res.status == "failed" and res.exit_code is None and "timeout after 42s" in res.reason


# ── no arbitrary command input ──────────────────────────────────────────────────────
def test_no_arbitrary_command_input():
    known_scripts = {f"scripts/{s}" for s in SCRIPTS.values()}
    for action in ALLOWED_ACTIONS:
        cmd = build_command(GatewayRequest(action=action, confirm_guarded_demo=True,
                                           allow_discord_send=True, use_learning_modifiers=True,
                                           include_real_trades=True))
        assert cmd[0] == sys.executable
        assert cmd[1].replace("\\", "/") in known_scripts
        for tok in cmd[2:]:
            if tok.startswith("--"):
                assert tok in ALLOWED_FLAGS, f"unexpected flag {tok}"
            else:
                # only validated values: an int, or the allowed risk_mode
                assert tok.isdigit() or tok in ("safe", "balanced", "scalp"), \
                    f"unexpected value token {tok!r}"


# ── source safety: no MT5 / orders / network / heatmap ──────────────────────────────
def test_source_has_no_mt5_orders_or_network():
    src = (_REPO / "services" / "gold_bot_command_gateway.py").read_text(encoding="utf-8")
    for forbidden in ("import MetaTrader5", "order_send", "send_demo_order",
                      "import requests", "urllib"):
        assert forbidden not in src, f"gateway must not contain {forbidden}"
    # references the demo cycle SCRIPT by name (allowed) but adds no trading logic
    assert "run_gold_bot_daily_cycle.py" in src


def test_source_does_not_touch_heatmap_or_ui():
    src = (_REPO / "services" / "gold_bot_command_gateway.py").read_text(encoding="utf-8")
    cli = (_REPO / "scripts" / "run_gold_bot_command_gateway.py").read_text(encoding="utf-8")
    for blob in (src, cli):
        assert "heatmap" not in blob.lower()
        assert "lumora-web" not in blob


def test_generated_command_logs_gitignored():
    gi = (_REPO / ".gitignore").read_text(encoding="utf-8")
    assert "data/gold_bot/commands/*.json" in gi
    assert "data/gold_bot/commands/*.jsonl" in gi
    assert "data/gold_bot/commands/*.csv" in gi


# ── CLI defaults ─────────────────────────────────────────────────────────────────────
def _load_cli():
    spec = importlib.util.spec_from_file_location(
        "run_gold_bot_command_gateway", _REPO / "scripts" / "run_gold_bot_command_gateway.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_cli_defaults_are_safe():
    cli = _load_cli()
    a = cli.parse_args(["--action", "preflight"])
    assert a.execute is False and a.dry_run is False        # -> dry-run by default
    assert a.allow_discord_send is False and a.confirm_guarded_demo is False
    assert a.duration_minutes == 5 and a.max_trades == 3 and a.risk_mode == "scalp"
    assert a.include_real_trades is False and a.use_learning_modifiers is False


def test_cli_rejects_execute_and_dry_run_together():
    cli = _load_cli()
    rc = cli.main(["--action", "preflight", "--execute", "--dry-run"])
    assert rc == 2
