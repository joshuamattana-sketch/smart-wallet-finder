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
    build_heatmap_cells(snapshot, price_step, wall_threshold_usd, price_range) -> dict
    resolve_price_range(symbol, mode, center, ...)       -> dict   (LM43)
    auto_scale_price_step(range_total, base_step, ...)   -> float  (LM43)
"""

from __future__ import annotations

import math
from collections import defaultdict


# ── Range presets (LM43) ──────────────────────────────────────────────────────

VALID_RANGE_MODES = ("tight", "standard", "wide", "macro")

# Per-symbol absolute USD half-range presets. The actual span is ±value
# around the current mid price.
PRESET_ABS: dict[str, dict[str, float]] = {
    "BTCUSDT": {"tight": 1000.0, "standard": 3000.0, "wide": 7500.0, "macro": 15000.0},
    "ETHUSDT": {"tight": 100.0,  "standard": 300.0,  "wide": 750.0,  "macro": 1500.0},
    "SOLUSDT": {"tight": 10.0,   "standard": 30.0,   "wide": 75.0,   "macro": 150.0},
}

# Fallback percentage half-range for symbols without an explicit preset.
PRESET_PCT_FALLBACK: dict[str, float] = {
    "tight": 0.01, "standard": 0.03, "wide": 0.07, "macro": 0.15,
}

# Target number of buckets per row for auto-scaling — keeps canvas/payload
# size reasonable even for the widest macro ranges. The default (600) keeps
# the BTC standard preset (±3000 @ step 10 = 600 buckets) unchanged, and
# only widens the step for the wide / macro modes where it's actually needed.
DEFAULT_TARGET_BUCKETS = 600


def resolve_price_range(
    symbol: str,
    mode: str,
    center: float,
    abs_override: float | None = None,
    pct_override: float | None = None,
) -> dict:
    """
    Resolve a heatmap price range from preset + optional overrides.

    Precedence:
      1. abs_override (USD radius)
      2. pct_override (fraction of center, e.g. 0.05 = ±5%)
      3. PRESET_ABS for known symbol+mode
      4. PRESET_PCT_FALLBACK for unknown symbols

    Returns dict with keys: mode, abs, pct, min, max, center.

    Raises ValueError on invalid inputs.
    """
    if mode not in VALID_RANGE_MODES:
        raise ValueError(
            f"invalid range mode {mode!r}. Allowed: {', '.join(VALID_RANGE_MODES)}"
        )
    if center is None or center <= 0:
        raise ValueError(f"center price must be > 0, got {center!r}")

    abs_used: float | None = None
    pct_used: float | None = None

    if abs_override is not None and abs_override > 0:
        abs_used = float(abs_override)
        radius = float(abs_override)
    elif pct_override is not None and pct_override > 0:
        pct_used = float(pct_override)
        radius = float(center) * float(pct_override)
    else:
        sym_presets = PRESET_ABS.get(symbol.upper(), {})
        if mode in sym_presets:
            abs_used = sym_presets[mode]
            radius = sym_presets[mode]
        else:
            pct_used = PRESET_PCT_FALLBACK[mode]
            radius = float(center) * pct_used

    return {
        "mode":   mode,
        "abs":    abs_used,
        "pct":    pct_used,
        "center": float(center),
        "min":    float(center) - radius,
        "max":    float(center) + radius,
    }


def auto_scale_price_step(
    range_total: float,
    base_step: float,
    target_buckets: int = DEFAULT_TARGET_BUCKETS,
) -> float:
    """
    Return a price-bucket step that keeps bucket count near `target_buckets`.

    If `base_step` is already coarse enough for the range, return it
    unchanged (backward compatible for narrow ranges).

    Otherwise snap upward to a "nice" 1/2/5 × 10^n value so labels stay
    readable on the canvas axis.
    """
    if range_total <= 0 or base_step <= 0:
        return base_step
    if target_buckets <= 0:
        return base_step
    needed = range_total / float(target_buckets)
    if needed <= base_step:
        return float(base_step)
    decade = 10.0 ** math.floor(math.log10(needed))
    for m in (1, 2, 5, 10):
        candidate = m * decade
        if candidate >= needed:
            return float(candidate)
    return float(10 * decade)


# ── Helpers (LM43) ────────────────────────────────────────────────────────────

def _snapshot_depth_range(snapshot: dict) -> tuple[float | None, float | None]:
    """Return (min_price, max_price) across all bid+ask levels, or (None, None)."""
    prices: list[float] = []
    for lv in snapshot.get("bids", []) or []:
        prices.append(lv["price"])
    for lv in snapshot.get("asks", []) or []:
        prices.append(lv["price"])
    if not prices:
        return None, None
    return min(prices), max(prices)


def _filter_snapshot_by_range(
    snapshot: dict, lo: float, hi: float,
) -> dict:
    """Return a new snapshot with bids/asks restricted to [lo, hi] inclusive."""
    return {
        **snapshot,
        "bids": [lv for lv in (snapshot.get("bids") or []) if lo <= lv["price"] <= hi],
        "asks": [lv for lv in (snapshot.get("asks") or []) if lo <= lv["price"] <= hi],
    }


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
    price_range: tuple[float, float] | None = None,
) -> dict:
    """
    Full pipeline: bucket → intensity → walls.

    Args:
        snapshot:           DepthSnapshot-compatible dict.
        price_step:         Bucket width in USD price terms.
        wall_threshold_usd: Minimum total_usd to flag a bucket as a wall.
        price_range:        Optional (min, max) price-range filter applied
                            BEFORE bucketing. Levels outside the range are
                            dropped. `available_depth_min/max` in the result
                            reflects the raw snapshot extremes, not the
                            filtered subset, so callers can show the user
                            how much of their requested range is covered.

    Returns:
        Dict with 'symbol', 'captured_at', 'price_step', 'buckets' (with
        intensity), 'walls', and (LM43) 'available_depth_min' /
        'available_depth_max'.
    """
    available_min, available_max = _snapshot_depth_range(snapshot)
    work_snapshot = snapshot
    if price_range is not None:
        lo, hi = float(price_range[0]), float(price_range[1])
        if hi < lo:
            raise ValueError(
                f"price_range max ({hi}) must be >= min ({lo})"
            )
        work_snapshot = _filter_snapshot_by_range(snapshot, lo, hi)

    bucketed = bucket_depth_snapshot(work_snapshot, price_step)
    buckets_with_intensity = calculate_intensity_scale(bucketed["buckets"])
    walls = detect_liquidity_walls(buckets_with_intensity, wall_threshold_usd)

    return {
        "symbol":               bucketed["symbol"],
        "captured_at":          bucketed["captured_at"],
        "price_step":           bucketed["price_step"],
        "buckets":              buckets_with_intensity,
        "walls":                walls,
        "available_depth_min":  available_min,
        "available_depth_max":  available_max,
    }
