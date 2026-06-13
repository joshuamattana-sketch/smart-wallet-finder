"""
tests/test_gold_bot_session_review.py
--------------------------------------
LM90A - Session review digest. Pure offline: no MT5, no internet, fake temp files.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

from services.gold_bot_session_review import (
    build_review,
    build_outcome_summary,
    render_markdown,
)

NOW = datetime(2026, 6, 13, 12, 0, 0, tzinfo=timezone.utc)
_REPO = Path(__file__).resolve().parent.parent

_SECTIONS = ("# Lumora Gold Bot Session Review", "## Summary", "## Decisions",
             "## Orders & Outcomes", "## Safety", "## Learning", "## Key Findings",
             "## Next Actions", "## Files Used", "## Warnings")


def _session(**kw):
    base = {"session_id": "session_x", "mode": "demo", "armed": True,
            "started_at": "2026-06-13T11:00:00+00:00", "ended_at": "2026-06-13T11:05:00+00:00",
            "duration_seconds": 300.0, "symbol": "XAUUSD", "risk_mode": "scalp", "iterations": 5,
            "long_count": 3, "short_count": 1, "no_trade_count": 1, "macro_lockout_count": 0,
            "demo_orders_attempted": 2, "demo_orders_sent": 1, "blocked_by_safety_count": 1,
            "blocked_reasons": {"spread_guard": 1}, "stop_reason": "max_trades_reached",
            "starting_equity": 10000.0, "ending_equity": 10010.0, "realized_pnl": 10.0,
            "learning_enabled": True, "active_modifiers_count": 2}
    base.update(kw)
    return base


def _outcomes(rows):
    closed = [r for r in rows if r.get("outcome") in ("win", "loss", "breakeven")]
    return {"session_id": "session_x", "source": "mt5_demo",
            "summary": {"count": len(rows), "wins": sum(r["outcome"] == "win" for r in rows),
                        "losses": sum(r["outcome"] == "loss" for r in rows),
                        "breakeven": sum(r["outcome"] == "breakeven" for r in rows),
                        "open": sum(r["outcome"] == "open" for r in rows),
                        "realized_pnl": round(sum(r.get("pnl") or 0 for r in closed), 2)},
            "outcomes": rows}


def _o(outcome, pnl, *, setup="momentum", side="LONG", exit_reason="tp"):
    return {"trade_id": 1, "outcome": outcome, "pnl": pnl, "setup": setup, "side": side,
            "exit_reason": exit_reason}


# ── build (pure) ─────────────────────────────────────────────────────────────────────
def test_build_full_inputs():
    r = build_review(
        session_report=_session(),
        outcomes_doc=_outcomes([_o("win", 18.0), _o("loss", -8.0)]),
        safety_events=[{"allowed": False, "severity": "block", "reason": "spread_guard"}],
        safety_state={"consecutive_losses": 1, "cooldown_until": None},
        learning_events=[{"event": "demo_trade_outcome"}],
        cycle_events=[{"event": "rejected", "reason": "expectancy worsened", "cycle_id": "c1"}],
        active_modifiers={"active_count": 2, "modifiers": {"momentum": {"confidence_modifier": -8}}},
        scorecard={"global": {"recommended_status": "avoid"},
                   "by_setup": {"momentum": {"recommended_status": "avoid"}}},
        now=NOW)
    assert r.session_id == "session_x" and r.mode == "demo"
    assert r.order_counts["sent"] == 1
    assert r.outcome_summary["wins"] == 1 and r.outcome_summary["losses"] == 1
    assert r.learning_summary["latest_cycle_event"] == "rejected"
    assert r.safety_summary["consecutive_losses"] == 1
    assert r.key_findings and r.next_actions


def test_observe_only_finding():
    r = build_review(session_report=_session(mode="observe", armed=False, demo_orders_sent=0), now=NOW)
    assert any("observe-only" in f for f in r.key_findings)


def test_mt5_health_block_finding():
    r = build_review(
        session_report=_session(demo_orders_sent=0, blocked_by_safety_count=3,
                                blocked_reasons={"mt5_health_guard": 3}),
        safety_events=[{"allowed": False, "severity": "block", "reason": "mt5_health_guard"}] * 3,
        now=NOW)
    assert any("mt5_health_guard" in f for f in r.key_findings)
    assert any("tick freshness" in a for a in r.next_actions)


def test_outcome_summary_wins_losses_pnl():
    s = build_outcome_summary(_outcomes([_o("win", 20.0, setup="fvg_retest"),
                                         _o("loss", -12.0, setup="momentum"),
                                         _o("open", None)]))
    assert s["wins"] == 1 and s["losses"] == 1 and s["open"] == 1
    assert s["realized_pnl"] == 8.0
    assert s["largest_win"] == 20.0 and s["largest_loss"] == -12.0
    assert s["by_setup"]["fvg_retest"]["wins"] == 1
    assert s["open_warning"] is not None


def test_no_outcomes_states_no_match():
    s = build_outcome_summary(None)
    assert s["available"] is False and "matched by symbol/magic" in s["note"]


def test_learning_accepted_cycle_finding():
    r = build_review(session_report=_session(),
                     cycle_events=[{"event": "accepted", "reason": "expectancy +30pt"}], now=NOW)
    assert r.learning_summary["latest_cycle_event"] == "accepted"
    assert any("accepted" in f for f in r.key_findings)


def test_real_contradiction_finding():
    r = build_review(session_report=_session(),
                     scorecard={"global": {"recommended_status": "avoid"},
                                "by_setup": {"momentum": {"recommended_status": "avoid",
                                                          "real_contradicts_replay": True}}},
                     now=NOW)
    assert r.learning_summary["real_contradicts_replay"] == ["momentum"]
    assert any("contradicts replay" in f for f in r.key_findings)


def test_cooldown_active_finding():
    r = build_review(session_report=_session(),
                     safety_state={"consecutive_losses": 3,
                                   "cooldown_until": "2026-06-13T12:30:00+00:00"}, now=NOW)
    assert r.safety_summary["cooldown_active"] is True
    assert any("cooldown is active" in f for f in r.key_findings)


# ── missing inputs degrade safely ─────────────────────────────────────────────────────
def test_missing_outcomes_no_crash():
    r = build_review(session_report=_session(), outcomes_doc=None, now=NOW)
    assert r.outcome_summary["available"] is False     # no crash


def test_missing_safety_no_crash():
    r = build_review(session_report=_session(), safety_events=[], safety_state=None, now=NOW)
    assert r.safety_summary["total_events"] == 0


# ── markdown + json ────────────────────────────────────────────────────────────────────
def test_markdown_contains_required_sections():
    md = render_markdown(build_review(session_report=_session(), now=NOW))
    for h in _SECTIONS:
        assert h in md, f"missing section {h}"


def test_json_contains_required_fields():
    d = build_review(session_report=_session(), now=NOW).to_dict()
    for k in ("session_id", "generated_at", "mode", "decision_counts", "order_counts",
              "safety_summary", "outcome_summary", "learning_summary", "key_findings",
              "next_actions", "warnings", "files_used"):
        assert k in d


# ── CLI ─────────────────────────────────────────────────────────────────────────────────
def _load_cli():
    spec = importlib.util.spec_from_file_location(
        "run_gold_bot_session_review", _REPO / "scripts" / "run_gold_bot_session_review.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _setup_dirs(tmp_path, *, with_optional=True):
    sdir = tmp_path / "sessions"; sdir.mkdir()
    (sdir / "session_latest.json").write_text(json.dumps(_session()), encoding="utf-8")
    ldir = tmp_path / "learning"; ldir.mkdir()
    safedir = tmp_path / "safety"; safedir.mkdir()
    odir = tmp_path / "trade_outcomes"; odir.mkdir()
    if with_optional:
        (odir / "outcomes_latest.json").write_text(
            json.dumps(_outcomes([_o("win", 10.0)])), encoding="utf-8")
        (safedir / "safety_events.jsonl").write_text(
            json.dumps({"allowed": False, "severity": "block", "reason": "spread_guard"}) + "\n",
            encoding="utf-8")
    return sdir, ldir, safedir, odir


def _args(tmp_path, sdir, ldir, safedir, odir, *extra):
    return ["--session-file", str(sdir / "session_latest.json"),
            "--out-dir", str(tmp_path / "reviews"), "--learning-dir", str(ldir),
            "--safety-dir", str(safedir), "--trade-outcomes-dir", str(odir), *extra]


def test_cli_no_session_file_errors(tmp_path):
    cli = _load_cli()
    rc = cli.main(["--session-file", str(tmp_path / "nope.json")])
    assert rc == 1


def test_cli_dry_run_writes_nothing(tmp_path):
    cli = _load_cli()
    sdir, ldir, safedir, odir = _setup_dirs(tmp_path)
    rc = cli.main(_args(tmp_path, sdir, ldir, safedir, odir, "--dry-run"))
    assert rc == 0
    assert not (tmp_path / "reviews").exists()


def test_cli_writes_md_and_json(tmp_path):
    cli = _load_cli()
    sdir, ldir, safedir, odir = _setup_dirs(tmp_path)
    rc = cli.main(_args(tmp_path, sdir, ldir, safedir, odir, "--json"))
    assert rc == 0
    rev = tmp_path / "reviews"
    assert (rev / "session_review_session_x.md").exists()
    assert (rev / "session_review_session_x.json").exists()
    assert (rev / "session_review_latest.md").exists()
    assert (rev / "session_review_latest.json").exists()
    data = json.loads((rev / "session_review_latest.json").read_text())
    assert data["session_id"] == "session_x"


def test_cli_missing_optional_files_no_crash(tmp_path):
    cli = _load_cli()
    sdir, ldir, safedir, odir = _setup_dirs(tmp_path, with_optional=False)
    rc = cli.main(_args(tmp_path, sdir, ldir, safedir, odir))
    assert rc == 0
    md = (tmp_path / "reviews" / "session_review_latest.md").read_text(encoding="utf-8")
    assert "## Warnings" in md


def test_generated_review_files_gitignored():
    gi = (_REPO / ".gitignore").read_text(encoding="utf-8")
    assert "data/gold_bot/reviews/" in gi


def test_source_has_no_mt5_orders_or_http():
    src = (_REPO / "services" / "gold_bot_session_review.py").read_text(encoding="utf-8")
    for forbidden in ("MetaTrader5", ".order_send(", "import requests", "urllib", "socket("):
        assert forbidden not in src
