"""
services/gold_bot_confidence_calibration.py
---------------------------------------------
LM102A - Confidence calibration (RESEARCH / PREVIEW-ONLY).

Answers the real question behind "smart confidence": does a higher engine
confidence actually win more often? It buckets recorded trade outcomes by
confidence, computes win-rate + expectancy per bucket, and judges whether
confidence is PREDICTIVE, FLAT, or INVERTED. It also emits a PREVIEW remap
(bucket -> empirical win-rate as a calibrated confidence) that is NOT wired into
the decision engine - it is analysis only.

Pure + offline: no MT5, no orders, no network. Needs recorded outcomes first
(run the worker with --sync-outcomes-every, or the trade-outcomes probe). With
too few samples it says "insufficient" rather than inventing a number.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Confidence bins (inclusive lo, inclusive hi).
DEFAULT_BINS: tuple[tuple[int, int], ...] = (
    (0, 49), (50, 59), (60, 69), (70, 79), (80, 89), (90, 100),
)
DEFAULT_MIN_SAMPLES = 10
_MONOTONIC_EPS = 0.02   # win-rate change below this is treated as flat between buckets

VERDICT_PREDICTIVE = "predictive"
VERDICT_FLAT = "flat"
VERDICT_INVERTED = "inverted"
VERDICT_INSUFFICIENT = "insufficient"


@dataclass
class BucketStats:
    bucket: str
    lo: int
    hi: int
    count: int = 0
    wins: int = 0
    losses: int = 0
    breakeven: int = 0
    winrate: float | None = None          # wins / (wins + losses) — excludes breakeven
    winrate_incl_be: float | None = None  # wins / count — counts breakeven as non-wins
    avg_pnl: float | None = None
    avg_pnl_points: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "bucket": self.bucket, "lo": self.lo, "hi": self.hi, "count": self.count,
            "wins": self.wins, "losses": self.losses, "breakeven": self.breakeven,
            "winrate": self.winrate, "winrate_incl_be": self.winrate_incl_be,
            "avg_pnl": self.avg_pnl, "avg_pnl_points": self.avg_pnl_points,
        }


def _num(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def bucket_for(confidence: Any, bins: tuple[tuple[int, int], ...] = DEFAULT_BINS) -> str | None:
    c = _num(confidence)
    if c is None:
        return None
    for lo, hi in bins:
        if lo <= c <= hi:
            return f"{lo}-{hi}"
    return None


def calibrate(outcomes: list[dict], *, bins: tuple[tuple[int, int], ...] = DEFAULT_BINS,
              min_samples: int = DEFAULT_MIN_SAMPLES) -> dict[str, Any]:
    """
    Group closed outcomes by confidence bin and compute per-bucket win-rate +
    expectancy. `outcomes` items use keys: confidence, outcome (win|loss|
    breakeven), pnl, pnl_points. Returns a report dict with buckets, verdict, a
    PREVIEW calibrated-confidence map, and warnings. Pure; never raises.
    """
    buckets: dict[str, BucketStats] = {
        f"{lo}-{hi}": BucketStats(bucket=f"{lo}-{hi}", lo=lo, hi=hi) for lo, hi in bins
    }
    pnl_acc: dict[str, list[float]] = {k: [] for k in buckets}
    pts_acc: dict[str, list[float]] = {k: [] for k in buckets}
    skipped = 0
    for o in outcomes:
        key = bucket_for(o.get("confidence"), bins)
        outcome = o.get("outcome")
        if key is None or outcome not in ("win", "loss", "breakeven"):
            skipped += 1
            continue
        b = buckets[key]
        b.count += 1
        if outcome == "win":
            b.wins += 1
        elif outcome == "loss":
            b.losses += 1
        else:
            b.breakeven += 1
        pnl = _num(o.get("pnl"))
        if pnl is not None:
            pnl_acc[key].append(pnl)
        pts = _num(o.get("pnl_points"))
        if pts is not None:
            pts_acc[key].append(pts)

    for key, b in buckets.items():
        decided = b.wins + b.losses
        b.winrate = round(b.wins / decided, 3) if decided else None
        # Honest win-rate: counts breakeven trades in the denominator so a strategy
        # that mostly scratches at breakeven cannot look predictive on wins/losses alone.
        b.winrate_incl_be = round(b.wins / b.count, 3) if b.count else None
        b.avg_pnl = round(sum(pnl_acc[key]) / len(pnl_acc[key]), 2) if pnl_acc[key] else None
        b.avg_pnl_points = round(sum(pts_acc[key]) / len(pts_acc[key]), 1) if pts_acc[key] else None

    ordered = [buckets[f"{lo}-{hi}"] for lo, hi in bins]
    verdict = calibration_verdict(ordered, min_samples)
    warnings: list[str] = []
    if skipped:
        warnings.append(f"{skipped} outcome(s) skipped (no confidence / not closed).")
    total = sum(b.count for b in ordered)
    if total < min_samples:
        warnings.append(f"only {total} usable outcomes (< {min_samples}) - verdict is unreliable.")

    return {
        "total_outcomes": total,
        "min_samples": min_samples,
        "verdict": verdict,
        "buckets": [b.to_dict() for b in ordered],
        "suggested_confidence_map_preview": suggested_confidence_map(ordered, min_samples),
        "preview_only": True,
        "warnings": warnings,
    }


def calibration_verdict(buckets: list[BucketStats], min_samples: int) -> str:
    """predictive (win-rate rises with confidence) / inverted / flat / insufficient."""
    usable = [b for b in buckets if b.count >= min_samples and b.winrate is not None]
    if len(usable) < 2:
        return VERDICT_INSUFFICIENT
    usable.sort(key=lambda b: b.lo)
    ups = downs = 0
    for a, b in zip(usable, usable[1:]):
        if b.winrate > a.winrate + _MONOTONIC_EPS:
            ups += 1
        elif b.winrate < a.winrate - _MONOTONIC_EPS:
            downs += 1
    if ups > downs:
        return VERDICT_PREDICTIVE
    if downs > ups:
        return VERDICT_INVERTED
    return VERDICT_FLAT


def suggested_confidence_map(buckets: list[BucketStats], min_samples: int) -> dict[str, Any]:
    """
    PREVIEW remap only: for buckets with enough samples, a calibrated confidence =
    empirical win-rate * 100. Buckets below the sample floor map to None (keep the
    raw engine value). NEVER wired into the engine here - analysis output.
    """
    out: dict[str, Any] = {}
    for b in buckets:
        if b.count >= min_samples and b.winrate is not None:
            out[b.bucket] = round(b.winrate * 100)
        else:
            out[b.bucket] = None
    return out
