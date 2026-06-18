"""
tests/test_gold_bot_tactic_library_inverse.py
----------------------------------------------
LM98C - Tactic library + inverse replay test. Offline; fixture replay rows drive
the inverse evaluator. No real replay, no MT5, no network, no demo/live.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from services.gold_bot_tactic_library import (
    KNOWN_REPLAY_SETUPS,
    group_tactics,
    load_library,
    mapped_setup_tags,
    validate_tactic,
)
from services.gold_bot_inverse_replay_test import (
    DEFAULT_TACTIC_TESTS_DIR,
    InverseConfig,
    PREVIEW_NOTE,
    build_markdown,
    evaluate,
    run_inverse_test,
)

NOW = datetime(2026, 6, 13, 12, 0, 0, tzinfo=timezone.utc)
_REPO = Path(__file__).resolve().parent.parent


def _row(tf, setup, decision, h_to_dr, outcome="loss"):
    """Build a replay-shaped row with directional points per horizon."""
    score = {}
    for h, dr in h_to_dr.items():
        score[str(h)] = {"horizon": h, "dir_return_points": dr,
                         "outcome": outcome if dr < 0 else "win"}
    return {"timeframe": tf, "strategy": setup, "decision": decision, "score": score}


# breakout_retest: bad at h15 (loses), good at h30 (wins) -> original_better at h30
# momentum: consistently negative both horizons -> inverse_better
def _fixture_rows(n=40):
    rows = []
    for _ in range(n):
        rows.append(_row("M1", "breakout_retest", "LONG", {15: -30.0, 30: 40.0}))
        rows.append(_row("M1", "momentum", "SHORT", {15: -50.0, 30: -60.0}))
    return rows


# ── tactic library ──────────────────────────────────────────────────────────────
def test_library_loads_and_validates():
    tactics, meta, warnings = load_library()
    assert len(tactics) >= 8
    assert meta["symbol"] == "XAUUSD"
    # every loaded tactic passes the schema (load_library drops invalid ones)
    for t in tactics:
        assert validate_tactic(t) == []


def test_validate_catches_missing_fields():
    issues = validate_tactic({"id": "x"})
    assert any("missing field" in i for i in issues)


def test_grouping_maps_known_setups():
    tactics, _, _ = load_library()
    groups = group_tactics(tactics)
    mapped_ids = {t["id"] for t in groups["mapped"]}
    assert "breakout_retest" in mapped_ids
    assert "liquidity_sweep_reclaim" in mapped_ids
    # tactics with no replay feature are research-only / not implemented
    research = {t["id"] for t in groups["research_only"]} | {t["id"] for t in groups["not_implemented_yet"]}
    assert "vwap_reclaim" in research and "ema_trend_pullback" in research
    # mapped setup tags only reference real replay setups
    mapped = mapped_setup_tags(tactics)
    assert all(tag in KNOWN_REPLAY_SETUPS for tag in mapped)
    assert mapped.get("breakout_retest") == "breakout_retest"


# ── inverse evaluation ────────────────────────────────────────────────────────────
def test_evaluate_h15_vs_h30_and_inverse():
    rows = _fixture_rows(40)
    mapped = {"breakout_retest": "breakout_retest", "momentum": "ny_open_momentum"}
    cfg = InverseConfig(timeframes=("M1",), horizons=(15, 30), min_samples=10)
    result = evaluate(rows, cfg, mapped)

    g15 = result["global"]["15"]
    g30 = result["global"]["30"]
    # h15 and h30 differ (h30 less negative overall)
    assert g30["original"]["expectancy_points"] > g15["original"]["expectancy_points"]

    # breakout_retest: original better at h30 (it wins there)
    br = result["tactics"]["breakout_retest"]["by_horizon"]["30"]
    assert br["original"]["expectancy_points"] > 0
    assert br["inverse_edge"] in ("original_better", "both_promising")

    # momentum: negative both horizons -> inverse beats original
    mo = result["tactics"]["ny_open_momentum"]["by_horizon"]["30"]
    assert mo["original"]["expectancy_points"] < 0
    assert mo["inverse"]["expectancy_points"] > 0
    assert mo["inverse_edge"] == "inverse_better"


def test_report_has_whitelist_preview_only():
    rows = _fixture_rows(40)
    mapped = {"breakout_retest": "breakout_retest", "momentum": "ny_open_momentum"}
    cfg = InverseConfig(timeframes=("M1",), horizons=(15, 30), min_samples=10)
    result = evaluate(rows, cfg, mapped)
    md = build_markdown(result, cfg, {"path": "x"}, [])
    assert PREVIEW_NOTE in md
    assert "Demo whitelist preview (NOT active)" in md
    assert "h15" in md and "h30" in md
    assert "inverse" in md.lower()
    # breakout_retest h30 promising -> whitelisted; momentum -> not whitelisted (inverse-better)
    wl_ids = {w["tactic"] for w in result["demo_whitelist_preview"]["whitelist"]}
    assert "breakout_retest" in wl_ids


# ── run + artifacts ─────────────────────────────────────────────────────────────
def test_run_writes_artifacts_under_tactic_tests(tmp_path, monkeypatch):
    rows = _fixture_rows(40)
    import services.gold_bot_inverse_replay_test as mod
    monkeypatch.setattr(mod, "load_replay_rows", lambda *a, **k: (rows, ["replay_M1.jsonl"], []))
    cfg = InverseConfig(timeframes=("M1",), horizons=(15, 30), min_samples=10)
    result = run_inverse_test(cfg, out_dir=tmp_path / "tt", now_fn=lambda: NOW)
    assert result["ok"] is True
    assert Path(result["paths"]["latest_md"]).exists()
    assert Path(result["paths"]["whitelist_preview"]).exists()
    assert str(DEFAULT_TACTIC_TESTS_DIR).replace("\\", "/").endswith("data/gold_bot/tactic_tests")
    import json
    wl = json.loads(Path(result["paths"]["whitelist_preview"]).read_text(encoding="utf-8"))
    assert wl["note"] == PREVIEW_NOTE


def test_run_no_replay_data_fails_clearly(tmp_path, monkeypatch):
    import services.gold_bot_inverse_replay_test as mod
    monkeypatch.setattr(mod, "load_replay_rows", lambda *a, **k: ([], [], []))
    result = run_inverse_test(InverseConfig(), out_dir=tmp_path / "tt", now_fn=lambda: NOW)
    assert result["ok"] is False and "no replay data" in result["error"]


# ── source safety + gitignore ──────────────────────────────────────────────────────
def test_source_no_orders_demo_live_or_shell():
    for name in ("services/gold_bot_tactic_library.py", "services/gold_bot_inverse_replay_test.py",
                 "scripts/run_gold_bot_tactic_library_probe.py",
                 "scripts/run_gold_bot_inverse_replay_test.py"):
        src = (_REPO / name).read_text(encoding="utf-8")
        for forbidden in ("order_send", "send_demo_order", "confirm-demo-session",
                          "--allow-live-trading", "import MetaTrader5", "shell=True", "subprocess"):
            assert forbidden not in src, f"{name} must not contain {forbidden}"
        assert "heatmap" not in src.lower()


def test_gitignore_has_tactic_tests():
    gi = (_REPO / ".gitignore").read_text(encoding="utf-8")
    assert "data/gold_bot/tactic_tests/*.json" in gi
    assert "data/gold_bot/tactic_tests/*.md" in gi
    assert "data/gold_bot/tactics/*.manual.json" in gi
