"""
services/heatmap_matrix_builder.py
------------------------------------
Assembles multiple bucketed orderbook snapshots into a 2-D heatmap matrix
suitable for frontend canvas rendering or API delivery.

No API calls, no Supabase writes, no external dependencies.

Public API:
    build_heatmap_matrix(frames, price_min, price_max)  -> dict
    compress_heatmap_matrix(matrix)                     -> dict
    summarize_heatmap_matrix(matrix)                    -> dict
"""

from __future__ import annotations


# ── build_heatmap_matrix ──────────────────────────────────────────────────────

def build_heatmap_matrix(
    frames: list[dict],
    price_min: float | None = None,
    price_max: float | None = None,
) -> dict:
    """
    Combine a list of heatmap-cell snapshots into a 2-D matrix.

    Args:
        frames:    List of dicts as returned by build_heatmap_cells().
        price_min: Optional lower bound for price_axis filter (inclusive).
        price_max: Optional upper bound for price_axis filter (inclusive).

    Returns:
        Dict with symbol, price_axis, time_axis, bid_matrix, ask_matrix,
        total_matrix, walls, price_step, and frame_count.
        Matrix shape: rows = len(price_axis), cols = len(time_axis).
        Missing cells are 0.
    """
    symbol = ""
    price_step = 0.0

    # Collect valid frames (must have captured_at)
    valid_frames = [f for f in frames if f.get("captured_at")]

    # Derive symbol and price_step from first frame that has them
    for f in frames:
        if f.get("symbol"):
            symbol = f["symbol"]
        if f.get("price_step"):
            price_step = f["price_step"]
        if symbol and price_step:
            break

    if not valid_frames:
        return {
            "symbol": symbol,
            "price_axis": [],
            "time_axis": [],
            "bid_matrix": [],
            "ask_matrix": [],
            "total_matrix": [],
            "walls": [],
            "price_step": price_step,
            "frame_count": 0,
        }

    # Build price axis
    all_prices: set[float] = set()
    for f in valid_frames:
        for b in f.get("buckets", []):
            p = b["price_bucket"]
            if price_min is not None and p < price_min:
                continue
            if price_max is not None and p > price_max:
                continue
            all_prices.add(p)

    price_axis = sorted(all_prices)
    price_index = {p: i for i, p in enumerate(price_axis)}

    # Build time axis
    time_axis = sorted({f["captured_at"] for f in valid_frames})
    time_index = {t: i for i, t in enumerate(time_axis)}

    n_prices = len(price_axis)
    n_times = len(time_axis)

    bid_matrix   = [[0.0] * n_times for _ in range(n_prices)]
    ask_matrix   = [[0.0] * n_times for _ in range(n_prices)]
    total_matrix = [[0.0] * n_times for _ in range(n_prices)]

    for f in valid_frames:
        t_idx = time_index[f["captured_at"]]
        for b in f.get("buckets", []):
            p = b["price_bucket"]
            if p not in price_index:
                continue  # filtered out by price_min/max
            p_idx = price_index[p]
            intensity = b.get("intensity", 0.0) or 0.0

            if b.get("bid_usd", 0.0) > 0:
                bid_matrix[p_idx][t_idx] = intensity
            if b.get("ask_usd", 0.0) > 0:
                ask_matrix[p_idx][t_idx] = intensity
            total_matrix[p_idx][t_idx] = intensity

    # Collect and deduplicate walls (keep highest intensity per price+side+label)
    wall_key: dict[tuple, dict] = {}
    for f in valid_frames:
        for w in f.get("walls", []):
            key = (w.get("price_bucket"), w.get("side"), w.get("label"))
            existing = wall_key.get(key)
            w_intensity = w.get("intensity") or 0.0
            if existing is None or w_intensity > (existing.get("intensity") or 0.0):
                wall_key[key] = w

    walls = sorted(wall_key.values(), key=lambda w: w.get("total_usd", 0.0), reverse=True)

    return {
        "symbol": symbol,
        "price_axis": price_axis,
        "time_axis": time_axis,
        "bid_matrix": bid_matrix,
        "ask_matrix": ask_matrix,
        "total_matrix": total_matrix,
        "walls": walls,
        "price_step": price_step,
        "frame_count": len(valid_frames),
    }


# ── compress_heatmap_matrix ───────────────────────────────────────────────────

def compress_heatmap_matrix(matrix: dict) -> dict:
    """
    Convert a full matrix to a compact frontend format.

    Only non-zero cells are emitted. Each cell is:
        {"p": price_index, "t": time_index, "bid": ..., "ask": ..., "total": ...}

    Returns:
        Dict with symbol, priceMin, priceMax, priceStep, timeBuckets, cells, walls.
    """
    price_axis: list[float] = matrix.get("price_axis", [])
    time_axis: list[str]    = matrix.get("time_axis", [])
    bid_matrix   = matrix.get("bid_matrix", [])
    ask_matrix   = matrix.get("ask_matrix", [])
    total_matrix = matrix.get("total_matrix", [])

    cells = []
    for p_idx, price in enumerate(price_axis):
        for t_idx in range(len(time_axis)):
            bid   = bid_matrix[p_idx][t_idx]   if bid_matrix   else 0.0
            ask   = ask_matrix[p_idx][t_idx]   if ask_matrix   else 0.0
            total = total_matrix[p_idx][t_idx] if total_matrix else 0.0
            if bid or ask or total:
                # LM43B: emit absolute `price_bucket` so the canvas can place
                # cells correctly even when the observed price_axis has gaps
                # (which is common for wide/macro ranges with coarse steps).
                # Older consumers reading only `p` keep working.
                cells.append({
                    "p":            p_idx,
                    "t":            t_idx,
                    "bid":          bid,
                    "ask":          ask,
                    "total":        total,
                    "price_bucket": price,
                })

    return {
        "symbol": matrix.get("symbol", ""),
        "priceMin": price_axis[0] if price_axis else None,
        "priceMax": price_axis[-1] if price_axis else None,
        "priceStep": matrix.get("price_step", 0.0),
        "timeBuckets": time_axis,
        "cells": cells,
        "walls": matrix.get("walls", []),
    }


# ── summarize_heatmap_matrix ──────────────────────────────────────────────────

def summarize_heatmap_matrix(matrix: dict) -> dict:
    """
    Compute display-ready summary metrics from a built matrix.

    Returns:
        Dict with symbol, frame_count, price_min, price_max, time_start,
        time_end, max_bid_intensity, max_ask_intensity, max_total_intensity,
        wall_count.
    """
    price_axis = matrix.get("price_axis", [])
    time_axis  = matrix.get("time_axis", [])

    def _matrix_max(m: list[list[float]]) -> float:
        if not m or not m[0]:
            return 0.0
        return max(v for row in m for v in row)

    return {
        "symbol": matrix.get("symbol", ""),
        "frame_count": matrix.get("frame_count", 0),
        "price_min": price_axis[0] if price_axis else None,
        "price_max": price_axis[-1] if price_axis else None,
        "time_start": time_axis[0] if time_axis else None,
        "time_end": time_axis[-1] if time_axis else None,
        "max_bid_intensity": _matrix_max(matrix.get("bid_matrix", [])),
        "max_ask_intensity": _matrix_max(matrix.get("ask_matrix", [])),
        "max_total_intensity": _matrix_max(matrix.get("total_matrix", [])),
        "wall_count": len(matrix.get("walls", [])),
    }
