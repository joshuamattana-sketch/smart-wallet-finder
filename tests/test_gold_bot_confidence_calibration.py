"""
tests/test_gold_bot_confidence_calibration.py
----------------------------------------------
LM102A - Pure tests for confidence calibration (preview-only analysis).
"""

from __future__ import annotations

from services.gold_bot_confidence_calibration import (
    VERDICT_INSUFFICIENT,
    VERDICT_INVERTED,
    VERDICT_PREDICTIVE,
    bucket_for,
    calibrate,
    calibration_verdict,
)


def _outcomes(bucket_winrates, *, n=20):
    """Build n outcomes per (confidence, winrate) so a bucket gets the target win-rate."""
    rows = []
    for conf, wr in bucket_winrates:
        wins = round(n * wr)
        for i in range(n):
            rows.append({"confidence": conf, "outcome": "win" if i < wins else "loss",
                         "pnl": 1.0 if i < wins else -1.0, "pnl_points": 10.0 if i < wins else -10.0})
    return rows


def test_bucket_for_ranges():
    assert bucket_for(55) == "50-59"
    assert bucket_for(95) == "90-100"
    assert bucket_for(49) == "0-49"
    assert bucket_for(None) is None
    assert bucket_for("x") is None


def test_predictive_when_winrate_rises_with_confidence():
    # 55→40%, 75→55%, 95→75% : monotonically rising → predictive
    rep = calibrate(_outcomes([(55, 0.40), (75, 0.55), (95, 0.75)]), min_samples=10)
    assert rep["verdict"] == VERDICT_PREDICTIVE
    by = {b["bucket"]: b for b in rep["buckets"]}
    assert by["90-100"]["winrate"] == 0.75
    # preview remap reflects empirical win-rate
    assert rep["suggested_confidence_map_preview"]["90-100"] == 75


def test_inverted_when_higher_confidence_wins_less():
    # higher confidence wins LESS → inverted (the mis-signed case)
    rep = calibrate(_outcomes([(55, 0.70), (75, 0.50), (95, 0.30)]), min_samples=10)
    assert rep["verdict"] == VERDICT_INVERTED


def test_insufficient_when_too_few_samples():
    rep = calibrate(_outcomes([(55, 0.5), (95, 0.5)], n=3), min_samples=10)
    assert rep["verdict"] == VERDICT_INSUFFICIENT
    # under-sampled buckets keep raw confidence (None in the preview map)
    assert rep["suggested_confidence_map_preview"]["50-59"] is None


def test_skips_open_and_missing_confidence():
    rows = [
        {"confidence": 75, "outcome": "win", "pnl_points": 10.0},
        {"confidence": None, "outcome": "win"},        # no confidence → skipped
        {"confidence": 75, "outcome": "open"},          # not closed → skipped
    ]
    rep = calibrate(rows, min_samples=1)
    assert rep["total_outcomes"] == 1
    assert any("skipped" in w for w in rep["warnings"])


def test_verdict_insufficient_with_one_bucket():
    from services.gold_bot_confidence_calibration import BucketStats
    one = [BucketStats(bucket="70-79", lo=70, hi=79, count=50, wins=30, losses=20, winrate=0.6)]
    assert calibration_verdict(one, min_samples=10) == VERDICT_INSUFFICIENT


def test_winrate_incl_be_counts_breakeven_in_denominator():
    # 5 wins, 3 losses, 12 breakeven: wins/(wins+losses)=0.625 looks decent, but the
    # honest win-rate over all 20 trades is only 0.25 (breakeven-farming is exposed).
    rows = ([{"confidence": 75, "outcome": "win", "pnl": 1.0, "pnl_points": 10.0}] * 5
            + [{"confidence": 75, "outcome": "loss", "pnl": -1.0, "pnl_points": -10.0}] * 3
            + [{"confidence": 75, "outcome": "breakeven", "pnl": 0.0, "pnl_points": 0.0}] * 12)
    rep = calibrate(rows, min_samples=1)
    b = {x["bucket"]: x for x in rep["buckets"]}["70-79"]
    assert b["winrate"] == 0.625          # wins / (wins + losses)
    assert b["winrate_incl_be"] == 0.25   # wins / count (20)
