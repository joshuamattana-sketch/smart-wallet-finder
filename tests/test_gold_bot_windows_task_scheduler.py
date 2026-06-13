"""
tests/test_gold_bot_windows_task_scheduler.py
----------------------------------------------
LM96A - Static safety invariants for the Windows scheduling helper.

The helper is PowerShell + docs (run/registered only on Windows by the owner).
These offline checks guard the hard boundaries: the scheduled run is the
whitelisted OFFLINE gateway action only - no demo session, no Discord send, no
live, no secrets - and task creation defaults to a plan (never auto-registers).
No Windows registration, no MT5, no internet here.
"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
START = _ROOT / "scripts" / "start_gold_bot_offline_cycle.ps1"
CREATE = _ROOT / "scripts" / "create_gold_bot_offline_task.ps1"
DOC = _ROOT / "docs" / "gold_bot" / "WINDOWS_TASK_SCHEDULER.md"
SAMPLE = _ROOT / "docs" / "gold_bot" / "templates" / "gold_bot_offline_task.xml.sample"
GITIGNORE = _ROOT / ".gitignore"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ── files exist ───────────────────────────────────────────────────────────────────
def test_files_exist():
    for p in (START, CREATE, DOC, SAMPLE, GITIGNORE):
        assert p.exists(), f"missing {p}"


# ── start script: offline gateway action only ──────────────────────────────────────
def test_start_runs_offline_gateway_action():
    src = _read(START)
    assert "run_gold_bot_command_gateway.py" in src
    assert "daily_cycle_offline" in src
    assert "--execute" in src and "--write-log" in src
    assert "--include-real-trades" in src


def test_start_has_no_demo_session_or_discord_send():
    src = _read(START)
    for forbidden in ("--confirm", "--send-discord", "--allow-discord-send",
                      "--confirm-demo-session", "--confirm-guarded-demo"):
        assert forbidden not in src, f"start script must not contain {forbidden}"
    # scheduling lives only in the create helper, not here
    assert "Register-ScheduledTask" not in src


def test_start_has_no_live_or_secrets():
    src = _read(START)
    for forbidden in ("--allow-live-trading", "environment live", "ALLOW_REAL",
                      "LUMORA_GOLD_DISCORD_WEBHOOK_URL", "WEBHOOK"):
        assert forbidden not in src, f"start script must not contain {forbidden}"


# ── create task: plan by default, explicit register ─────────────────────────────────
def test_create_defaults_to_plan_not_register():
    src = _read(CREATE)
    assert "[switch]$WhatIfPlan" in src
    assert "[switch]$Register" in src
    assert "$doRegister = $Register -and -not $WhatIfPlan" in src
    assert "if (-not $doRegister)" in src           # plan path exits before registering
    assert "DRY-RUN (plan only)" in src


def test_create_registers_only_with_register_flag():
    src = _read(CREATE)
    assert "Register-ScheduledTask" in src
    # registration is gated behind $doRegister and runs in current-user, limited level
    assert "RunLevel Limited" in src
    assert "-Force" in src and "already exists" in src   # replace guard


def test_create_states_offline_maintenance_only():
    src = _read(CREATE)
    assert "offline maintenance only" in src
    assert "does not start demo" in src
    # the scheduled run is the offline gateway action
    assert "--action daily_cycle_offline --execute --include-real-trades --write-log" in src


def test_create_has_no_demo_send_live_or_secrets():
    src = _read(CREATE)
    for forbidden in ("--confirm", "--send-discord", "--allow-discord-send",
                      "--allow-live-trading", "LUMORA_GOLD_DISCORD_WEBHOOK_URL", "WEBHOOK"):
        assert forbidden not in src, f"create script must not contain {forbidden}"


# ── docs ────────────────────────────────────────────────────────────────────────────
def test_docs_warn_no_demo_trading_by_default():
    src = _read(DOC)
    assert "No demo trading is scheduled by default." in src
    assert "Do not store the Discord webhook" in src
    assert "daily_cycle_offline" in src


def test_sample_xml_is_template_only():
    src = _read(SAMPLE)
    assert "<REPO_ROOT>" in src                      # placeholder, not machine-specific
    assert "start_gold_bot_offline_cycle.ps1" in src
    assert "offline maintenance only" in src
    # never a real demo/live/secret in the sample
    for forbidden in ("--confirm", "--send-discord", "LUMORA_GOLD_DISCORD_WEBHOOK_URL"):
        assert forbidden not in src


# ── gitignore + no heatmap ──────────────────────────────────────────────────────────
def test_task_logs_gitignored():
    gi = _read(GITIGNORE)
    assert "data/gold_bot/task_logs/*.log" in gi
    assert "data/gold_bot/task_logs/*.jsonl" in gi


def test_no_heatmap_touched_by_helper():
    for p in (START, CREATE, DOC, SAMPLE):
        assert "heatmap" not in _read(p).lower(), f"{p.name} must not reference heatmap"
