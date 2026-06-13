"""
tests/test_gold_bot_scheduled_runner.py
----------------------------------------
LM92A - Local cycle orchestrator. Subprocess is mocked; no real commands run,
no MT5, no internet.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from services.gold_bot_scheduled_runner import (
    SCRIPTS,
    CycleConfig,
    redact,
    run_cycle,
)

NOW = datetime(2026, 6, 13, 12, 0, 0, tzinfo=timezone.utc)
_REPO = Path(__file__).resolve().parent.parent


def _repo(tmp_path, *, session=False, review=False):
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    for s in SCRIPTS.values():
        (root / "scripts" / s).write_text("# stub", encoding="utf-8")
    (root / "data" / "gold_bot" / "sessions").mkdir(parents=True)
    (root / "data" / "gold_bot" / "reviews").mkdir(parents=True)
    if session:
        (root / "data" / "gold_bot" / "sessions" / "session_latest.json").write_text("{}", encoding="utf-8")
    if review:
        (root / "data" / "gold_bot" / "reviews" / "session_review_latest.json").write_text("{}", encoding="utf-8")
    return root


class FakeRunner:
    def __init__(self, fail=None, stdout_map=None):
        self.calls: list[list[str]] = []
        self.fail = set(fail or ())
        self.stdout_map = stdout_map or {}

    def __call__(self, cmd, *, cwd, timeout):
        self.calls.append(cmd)
        script = next((Path(c).name for c in cmd if c.endswith(".py")), "")
        rc = 1 if script in self.fail else 0
        return SimpleNamespace(returncode=rc, stdout=self.stdout_map.get(script, "ok\n"), stderr="")

    def scripts_called(self):
        return [next((Path(c).name for c in cmd if c.endswith(".py")), "") for cmd in self.calls]


def _run(tmp_path, cfg, runner, *, session=False, review=False):
    root = _repo(tmp_path, session=session, review=review)
    return run_cycle(cfg, repo_root=root, out_dir=tmp_path / "runs", runner_fn=runner,
                     now_fn=lambda: NOW)


def _step(run, name):
    return next(s for s in run.steps if s["name"] == name)


# ── default plan ─────────────────────────────────────────────────────────────────
def test_default_is_plan_only_no_subprocess(tmp_path):
    def boom(*a, **k):
        raise AssertionError("subprocess called in plan mode!")
    run = _run(tmp_path, CycleConfig(), boom)
    assert run.overall_status == "planned"
    assert run.run_json_path is None                       # no log in plan mode
    assert not (tmp_path / "runs").exists()
    # action steps are planned/skipped, none executed
    assert all(s["status"] in ("planned", "skipped", "success") for s in run.steps)
    assert _step(run, "demo_session")["status"] == "skipped"   # not confirmed


def test_dry_run_log_writes_in_plan(tmp_path):
    run = _run(tmp_path, CycleConfig(dry_run_log=True), FakeRunner())
    assert run.run_json_path and Path(run.run_json_path).exists()


# ── demo session gating ──────────────────────────────────────────────────────────
def test_execute_without_confirm_skips_demo(tmp_path):
    r = FakeRunner()
    run = _run(tmp_path, CycleConfig(execute=True), r)
    assert SCRIPTS["demo_session"] not in r.scripts_called()
    assert _step(run, "demo_session")["status"] == "skipped"
    assert "not confirmed" in _step(run, "demo_session")["reason"]


def test_execute_with_confirm_includes_demo(tmp_path):
    r = FakeRunner()
    cfg = CycleConfig(execute=True, confirm_demo_session=True, use_learning_modifiers=True)
    _run(tmp_path, cfg, r)
    demo = next(c for c in r.calls if SCRIPTS["demo_session"] in " ".join(c))
    assert "--confirm-demo-session" in demo and "--use-learning-modifiers" in demo


# ── outcome sync gating ──────────────────────────────────────────────────────────
def test_outcome_skipped_when_session_latest_missing(tmp_path):
    r = FakeRunner()
    run = _run(tmp_path, CycleConfig(execute=True, skip_session=True), r, session=False)
    assert SCRIPTS["outcome_sync"] not in r.scripts_called()
    assert "missing" in _step(run, "outcome_sync")["reason"]


def test_outcome_runs_when_session_present(tmp_path):
    r = FakeRunner()
    _run(tmp_path, CycleConfig(execute=True, skip_session=True), r, session=True)
    assert SCRIPTS["outcome_sync"] in r.scripts_called()


# ── learning cycle ────────────────────────────────────────────────────────────────
def test_learning_cycle_includes_real_trades_flag(tmp_path):
    r = FakeRunner()
    _run(tmp_path, CycleConfig(execute=True, skip_session=True, include_real_trades=True), r)
    lc = next(c for c in r.calls if SCRIPTS["learning_cycle"] in " ".join(c))
    assert "--include-real-trades" in lc and "--real-trade-weight" in lc


def test_learning_cycle_omits_real_trades_by_default(tmp_path):
    r = FakeRunner()
    _run(tmp_path, CycleConfig(execute=True, skip_session=True), r)
    lc = next(c for c in r.calls if SCRIPTS["learning_cycle"] in " ".join(c))
    assert "--include-real-trades" not in lc


# ── discord preview vs send ──────────────────────────────────────────────────────
def test_discord_preview_default_in_execute(tmp_path):
    r = FakeRunner()
    _run(tmp_path, CycleConfig(execute=True, skip_session=True), r, review=True)
    dc = next(c for c in r.calls if SCRIPTS["discord"] in " ".join(c))
    assert "--send-discord" not in dc                      # preview only by default


def test_discord_send_requires_flag(tmp_path):
    r = FakeRunner()
    _run(tmp_path, CycleConfig(execute=True, skip_session=True, send_discord=True), r, review=True)
    dc = next(c for c in r.calls if SCRIPTS["discord"] in " ".join(c))
    assert "--send-discord" in dc


def test_discord_skipped_when_no_review(tmp_path):
    r = FakeRunner()
    run = _run(tmp_path, CycleConfig(execute=True, skip_session=True), r, review=False)
    assert SCRIPTS["discord"] not in r.scripts_called()
    assert _step(run, "discord")["status"] == "skipped"


# ── redaction ─────────────────────────────────────────────────────────────────────
def test_redact_webhook_unit():
    out = redact("posting to https://discord.com/api/webhooks/123/SECRET now")
    assert "SECRET" not in out and "...REDACTED" in out


def test_webhook_redacted_from_logs(tmp_path):
    leak = "sending https://discord.com/api/webhooks/999/TOPSECRETTOKEN ok"
    r = FakeRunner(stdout_map={SCRIPTS["discord"]: leak})
    run = _run(tmp_path, CycleConfig(execute=True, skip_session=True, send_discord=True), r, review=True)
    blob = json.dumps(run.to_dict())
    assert "TOPSECRETTOKEN" not in blob and "...REDACTED" in _step(run, "discord")["stdout_tail"]
    # and the written log file is redacted too
    assert "TOPSECRETTOKEN" not in Path(run.run_json_path).read_text(encoding="utf-8")


# ── failure handling ──────────────────────────────────────────────────────────────
def test_failure_stops_by_default(tmp_path):
    r = FakeRunner(fail={SCRIPTS["learning_cycle"]})
    run = _run(tmp_path, CycleConfig(execute=True, skip_session=True), r, session=True, review=True)
    assert _step(run, "learning_cycle")["status"] == "failed"
    assert _step(run, "session_review")["status"] == "skipped"   # stopped after failure
    assert SCRIPTS["session_review"] not in r.scripts_called()
    assert run.overall_status in ("failed", "partial")


def test_continue_on_error_continues(tmp_path):
    r = FakeRunner(fail={SCRIPTS["learning_cycle"]})
    run = _run(tmp_path, CycleConfig(execute=True, skip_session=True, continue_on_error=True),
               r, session=True, review=True)
    assert _step(run, "learning_cycle")["status"] == "failed"
    assert SCRIPTS["session_review"] in r.scripts_called()        # continued past failure


# ── run logs ──────────────────────────────────────────────────────────────────────
def test_run_logs_written_in_execute(tmp_path):
    run = _run(tmp_path, CycleConfig(execute=True, skip_session=True), FakeRunner())
    assert Path(run.run_json_path).exists() and Path(run.run_jsonl_path).exists()
    assert (tmp_path / "runs" / "run_latest.json").exists()
    assert (tmp_path / "runs" / "run_latest.jsonl").exists()
    log = json.loads(Path(run.run_json_path).read_text())
    assert log["run_id"] == run.run_id and "steps" in log and "overall_status" in log


# ── safety: no trading/MT5 logic in source ─────────────────────────────────────────
def test_source_has_no_trading_or_mt5_logic():
    src = (_REPO / "services" / "gold_bot_scheduled_runner.py").read_text(encoding="utf-8")
    for forbidden in ("import MetaTrader5", "order_send", "send_demo_order", "import requests",
                      "urllib"):
        assert forbidden not in src, f"orchestrator must not contain {forbidden}"
    # it references the demo session SCRIPT by name (allowed) but adds no trading logic
    assert "run_gold_bot_demo_session.py" in src


def test_generated_runs_gitignored():
    gi = (_REPO / ".gitignore").read_text(encoding="utf-8")
    assert "data/gold_bot/runs/" in gi


# ── CLI defaults ───────────────────────────────────────────────────────────────────
def _load_cli():
    spec = importlib.util.spec_from_file_location(
        "run_gold_bot_daily_cycle", _REPO / "scripts" / "run_gold_bot_daily_cycle.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_cli_defaults_are_safe():
    cli = _load_cli()
    a = cli.parse_args([])
    assert a.execute is False and a.confirm_demo_session is False and a.send_discord is False
    assert a.duration_minutes == 5.0 and a.max_trades == 3 and a.risk_mode == "scalp"
    assert a.include_real_trades is False
