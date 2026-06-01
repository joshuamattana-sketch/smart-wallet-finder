"""
services/orderbook_depth_bucketer.py
-------------------------------------
Aggregates orderbook depth snapshots into price buckets for the liquidity
heatmap pipeline.

No API calls, no Supabase writes, no external dependencies.

Public API:
    bucket_depth_snapshot(snapshot, price_step)          -> dict
    calculate_intensity_scale(buckets, min_usd, max_usd) -> list[dict]
    detect_liquidity_walls(buckets, threshold_usd)       -> list[dict]
    build_heatmap_cells(snapshot, price_step, wall_threshold_usd) -> dict
"""

from __future__ import annotations

import math
from collections import defaultdict


# ── Core bucketing ────────────────────────────────────────────────────────────

def bucket_depth_snapshot(snapshot: dict, price_step: float = 10.0) -> dict:
    """
    Aggregate a depth snapshot into price buckets.

    Args:
        snapshot:   DepthSnapshot-compatible dict with 'bids' and 'asks' lists,
                    each entry having 'price', 'quantity', and 'usd' keys.
        price_step: Width of each price bucket in USD. Must be > 0.

    Returns:
        Dict with 'symbol', 'captured_at', 'price_step', and 'buckets' list.
        Each bucket has 'price_bucket', 'bid_usd', 'ask_usd', 'total_usd',
        and 'side' ("bid" | "ask" | "mixed").

    Raises:
        ValueError: If price_step <= 0.
    """
    if price_step <= 0:
        raise ValueError(f"price_step must be > 0, got {price_step!r}")

    bid_usd: dict[float, float] = defaultdict(float)
    ask_usd: dict[float, float] = defaultdict(float)

    for level in snapshot.get("bids", []):
        bucket = math.floor(level["price"] / price_step) * price_step
        bid_usd[bucket] += level["usd"]

    for level in snapshot.get("asks", []):
        bucket = math.floor(level["price"] / price_step) * price_step
        ask_usd[bucket] += level["usd"]

    all_buckets = sorted(set(bid_usd) | set(ask_usd))
    buckets = []
    for pb in all_buckets:
        b = round(bid_usd.get(pb, 0.0), 2)
        a = round(ask_usd.get(pb, 0.0), 2)
        total = round(b + a, 2)
        if b > 0 and a > 0:
            side = "mixed"
        elif b > 0:
            side = "bid"
        else:
            side = "ask"
        buckets.append({
            "price_bucket": pb,
            "bid_usd": b,
            "ask_usd": a,
            "total_usd": total,
            "side": side,
        })

    return {
        "symbol": snapshot.get("symbol", ""),
        "captured_at": snapshot.get("captured_at", ""),
        "price_step": price_step,
        "buckets": buckets,
    }


# ── Intensity scale ───────────────────────────────────────────────────────────

def calculate_intensity_scale(
    buckets: list[dict],
    min_usd: float | None = None,
    max_usd: float | None = None,
) -> list[dict]:
    """
    Add a log-scaled 'intensity' (0–100) to each bucket.

    Uses log1p so that large walls don't compress everything else to near-zero.
    Empty (total_usd == 0) buckets get intensity 0.

    Args:
        buckets:  List of bucket dicts (mutated in-place; copies are returned).
        min_usd:  Lower bound for scaling. Defaults to min non-zero total_usd.
        max_usd:  Upper bound for scaling. Defaults to max total_usd.

    Returns:
        New list of bucket dicts with 'intensity' key added.
    """
    non_zero = [b["total_usd"] for b in buckets if b["total_usd"] > 0]
    if not non_zero:
        return [{**b, "intensity": 0.0} for b in buckets]

    lo = math.log1p(min_usd if min_usd is not None else min(non_zero))
    hi = math.log1p(max_usd if max_usd is not None else max(non_zero))

    result = []
    for b in buckets:
        if b["total_usd"] <= 0:
            intensity = 0.0
        elif hi == lo:
            intensity = 100.0
        else:
            intensity = round(
                (math.log1p(b["total_usd"]) - lo) / (hi - lo) * 100.0, 2
            )
            intensity = max(0.0, min(100.0, intensity))
        result.append({**b, "intensity": intensity})

    return result


# ── Wall detection ────────────────────────────────────────────────────────────

def detect_liquidity_walls(buckets: list[dict], threshold_usd: float) -> list[dict]:
    """
    Return buckets whose total_usd meets or exceeds threshold_usd.

    Each wall dict includes:
        price_bucket, side, total_usd, intensity (if present), label.

    Labels:
        "Major Bid Wall"  — side == "bid"
        "Major Ask Wall"  — side == "ask"
        "Liquidity Wall"  — side == "mixed"

    Args:
        buckets:       List of bucket dicts, optionally with 'intensity' key.
        threshold_usd: Minimum total_usd to qualify as a wall.

    Returns:
        List of wall dicts sorted by total_usd descending.
    """
    label_map = {
        "bid": "Major Bid Wall",
        "ask": "Major Ask Wall",
        "mixed": "Liquidity Wall",
    }
    walls = []
    for b in buckets:
        if b["total_usd"] >= threshold_usd:
            walls.append({
                "price_bucket": b["price_bucket"],
                "side": b["side"],
                "total_usd": b["total_usd"],
                "intensity": b.get("intensity", None),
                "label": label_map.get(b["side"], "Liquidity Wall"),
            })

    walls.sort(key=lambda w: w["total_usd"], reverse=True)
    return walls


# ── Combined pipeline ─────────────────────────────────────────────────────────

def build_heatmap_cells(
    snapshot: dict,
    price_step: float = 10.0,
    wall_threshold_usd: float = 1_000_000.0,
) -> dict:
    """
    Full pipeline: bucket → intensity → walls.

    Args:
        snapshot:          DepthSnapshot-compatible dict.
        price_step:        Bucket width in USD price terms.
        wall_threshold_usd: Minimum total_usd to flag a bucket as a wall.

    Returns:
        Dict with 'symbol', 'captured_at', 'price_step', 'buckets' (with
        intensity), and 'walls'.
    """
    bucketed = bucket_depth_snapshot(snapshot, price_step)
    buckets_with_intensity = calculate_intensity_scale(bucketed["buckets"])
    walls = detect_liquidity_walls(buckets_with_intensity, wall_threshold_usd)

    return {
        "symbol": bucketed["symbol"],
        "captured_at": bucketed["captured_at"],
        "price_step": bucketed["price_step"],
        "buckets": buckets_with_intensity,
        "walls": walls,
    }
