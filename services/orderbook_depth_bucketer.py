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

# LM44: how many EMPTY buckets a zone is allowed to span before it splits.
# Tighter modes preserve detail; wider modes merge more aggressively so the
# canvas shows fewer, more meaningful key zones rather than many hairlines.
DEFAULT_ZONE_GAP_BUCKETS: dict[str, int] = {
    "tight":    0,
    "standard": 2,
    "wide":     5,
    "macro":    10,
}
# Default key-zone cap for the payload (top-N by strengthScore).
DEFAULT_KEY_ZONE_COUNT = 8
# Stamped on payloads aggregated under the LM44 wall/zone scoring model.
WALL_SCORE_VERSION = "2"


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


# ── Zone aggregation (LM44) ───────────────────────────────────────────────────

def _zone_from_levels(side: str, levels: list[dict]) -> dict:
    """Collapse a list of per-side levels into one zone dict."""
    prices       = [lv["price"]     for lv in levels]
    usds         = [lv["usd"]       for lv in levels]
    intensities  = [lv["intensity"] for lv in levels]
    p_min        = min(prices)
    p_max        = max(prices)
    total        = sum(usds)
    center = (
        sum(p * u for p, u in zip(prices, usds)) / total
        if total > 0 else (p_min + p_max) / 2.0
    )
    return {
        "side":          side,
        "priceMin":      round(p_min, 4),
        "priceMax":      round(p_max, 4),
        "centerPrice":   round(center, 4),
        "totalUsd":      round(total, 2),
        "maxIntensity":  round(max(intensities) if intensities else 0.0, 2),
        "bucketCount":   len(levels),
        "label":         "Bid Zone" if side == "bid" else "Ask Zone",
        "strengthScore": 0.0,
    }


def aggregate_liquidity_zones(
    buckets: list[dict],
    max_gap_buckets: int = 2,
    price_step: float = 10.0,
) -> list[dict]:
    """
    Group nearby buckets of the same side into liquidity zones.

    Mixed buckets contribute their bid_usd to bid zones and ask_usd to ask
    zones independently, so bids never get merged with asks.

    A zone breaks when the next same-side bucket is more than
    `max_gap_buckets * price_step` USD away from the previous one.

    Returns zones sorted by centerPrice ascending.
    """
    if not buckets or price_step <= 0:
        return []

    side_levels: dict[str, list[dict]] = {"bid": [], "ask": []}
    for b in buckets:
        if b.get("bid_usd", 0.0) > 0:
            side_levels["bid"].append({
                "price":     b["price_bucket"],
                "usd":       b["bid_usd"],
                "intensity": b.get("intensity", 0.0) or 0.0,
            })
        if b.get("ask_usd", 0.0) > 0:
            side_levels["ask"].append({
                "price":     b["price_bucket"],
                "usd":       b["ask_usd"],
                "intensity": b.get("intensity", 0.0) or 0.0,
            })

    # max_gap_buckets is the number of empty buckets allowed between members,
    # so two same-side buckets `g * price_step` apart are still grouped iff
    # the bucket count between them is <= max_gap_buckets.
    gap_threshold = (max(0, max_gap_buckets) + 1) * price_step + 1e-9

    zones: list[dict] = []
    for side in ("bid", "ask"):
        levels = sorted(side_levels[side], key=lambda x: x["price"])
        if not levels:
            continue
        current: list[dict] = [levels[0]]
        for lv in levels[1:]:
            if (lv["price"] - current[-1]["price"]) <= gap_threshold:
                current.append(lv)
            else:
                zones.append(_zone_from_levels(side, current))
                current = [lv]
        zones.append(_zone_from_levels(side, current))

    zones.sort(key=lambda z: z["centerPrice"])
    return zones


def score_zones(
    zones: list[dict],
    current_price: float | None = None,
) -> list[dict]:
    """
    Mutate each zone in-place with `strengthScore` (0-100), `zoneWidth`,
    `liquidityDensity`, and `distancePctFromPrice` (when current_price set).

    Score model = log-normalized USD percentile (up to 90) plus a proximity
    boost (up to 10) for zones within ±5% of the current price.
    """
    if not zones:
        return zones
    totals = [z["totalUsd"] for z in zones if z["totalUsd"] > 0]
    max_total = max(totals) if totals else 0.0
    log_max = math.log1p(max_total) if max_total > 0 else 0.0
    for z in zones:
        usd_score = (
            (math.log1p(z["totalUsd"]) / log_max) * 90.0
            if log_max > 0 else 0.0
        )
        proximity = 0.0
        if current_price is not None and current_price > 0:
            dist_frac = abs(z["centerPrice"] - current_price) / current_price
            proximity = max(0.0, 10.0 * (1.0 - min(dist_frac / 0.05, 1.0)))
            z["distancePctFromPrice"] = round(dist_frac * 100.0, 3)
        z["strengthScore"]    = round(min(100.0, usd_score + proximity), 2)
        z["zoneWidth"]        = round(z["priceMax"] - z["priceMin"], 4)
        z["liquidityDensity"] = round(z["totalUsd"] / max(1.0, z["zoneWidth"] + 1.0), 2)
    return zones


def pick_key_zones(
    zones: list[dict],
    top_n: int = DEFAULT_KEY_ZONE_COUNT,
) -> list[dict]:
    """Return the top-N zones by strengthScore (highest first)."""
    return sorted(zones, key=lambda z: z["strengthScore"], reverse=True)[:max(0, top_n)]


def score_walls(
    walls: list[dict],
    current_price: float | None = None,
) -> list[dict]:
    """
    Enrich walls with `strengthScore`, `wallRank`, and (when current_price
    set) `distancePctFromPrice`. Same scoring model as zones.
    """
    if not walls:
        return walls
    totals = [w["total_usd"] for w in walls if w.get("total_usd", 0.0) > 0]
    max_total = max(totals) if totals else 0.0
    log_max = math.log1p(max_total) if max_total > 0 else 0.0
    for w in walls:
        usd_score = (
            (math.log1p(w["total_usd"]) / log_max) * 90.0
            if log_max > 0 else 0.0
        )
        proximity = 0.0
        if current_price is not None and current_price > 0:
            dist_frac = abs(w["price_bucket"] - current_price) / current_price
            proximity = max(0.0, 10.0 * (1.0 - min(dist_frac / 0.05, 1.0)))
            w["distancePctFromPrice"] = round(dist_frac * 100.0, 3)
        w["strengthScore"] = round(min(100.0, usd_score + proximity), 2)
    # Stable rank by strengthScore (1 = strongest).
    for rank, w in enumerate(
        sorted(walls, key=lambda x: x["strengthScore"], reverse=True), start=1,
    ):
        w["wallRank"] = rank
    return walls


# ── Combined pipeline ─────────────────────────────────────────────────────────

def build_heatmap_cells(
    snapshot: dict,
    price_step: float = 10.0,
    wall_threshold_usd: float = 1_000_000.0,
    price_range: tuple[float, float] | None = None,
    aggregation_mode: str | None = None,
    current_price: float | None = None,
    key_zone_count: int = DEFAULT_KEY_ZONE_COUNT,
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

    # LM44: zone aggregation + percentile/proximity wall scoring.
    mode = aggregation_mode or "standard"
    gap = DEFAULT_ZONE_GAP_BUCKETS.get(mode, DEFAULT_ZONE_GAP_BUCKETS["standard"])
    zones = aggregate_liquidity_zones(
        buckets_with_intensity,
        max_gap_buckets=gap,
        price_step=price_step,
    )
    score_zones(zones, current_price=current_price)
    key_zones = pick_key_zones(zones, top_n=key_zone_count)
    score_walls(walls, current_price=current_price)

    return {
        "symbol":               bucketed["symbol"],
        "captured_at":          bucketed["captured_at"],
        "price_step":           bucketed["price_step"],
        "buckets":              buckets_with_intensity,
        "walls":                walls,
        "available_depth_min":  available_min,
        "available_depth_max":  available_max,
        "zones":                zones,
        "key_zones":            key_zones,
        "aggregation_mode":     mode,
        "bucket_aggregation":   gap,
    }
