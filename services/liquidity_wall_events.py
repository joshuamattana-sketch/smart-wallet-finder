"""
services/liquidity_wall_events.py
----------------------------------
LM46 — Liquidity wall event detector (deterministic, dependency-light).

Compares two heatmap wall snapshots (previous vs. current) and emits a
sorted list of event dicts. No I/O, no Supabase, no network — pure
functions only. Safe to call from any context (tests, the WS collector,
a future cron job, an API route).

Event types
~~~~~~~~~~~
    wall_created       — wall appeared in `current_walls`, was absent (or
                         too weak) in `previous_walls`.
    wall_strengthened  — same wall present in both; strength rose by
                         >= strengthened_delta_pct.
    wall_weakened      — same wall present in both; strength dropped by
                         >= weakened_delta_pct.
    wall_pulled        — wall in `previous_walls` is gone in
                         `current_walls`. Not preceded by a price break.
    wall_touched       — price is inside the wall band (within
                         touch_distance_pct) without strengthening.
    wall_defended      — price is inside the band AND strength rose
                         (>= strengthened_delta_pct). Implies "held".
    wall_broken        — price has moved past the band by
                         >= broken_distance_pct AND wall vanished or
                         significantly weakened. Implies "consumed".

Suppression rules (so each matched wall emits at most ONE event):
    * wall_defended suppresses wall_strengthened on the same wall.
    * wall_broken    suppresses wall_weakened    on the same wall.
    * State events (strengthened/weakened) and position events
      (touched/defended/broken) are otherwise independent slots.

Input shape
~~~~~~~~~~~
`previous_walls` and `current_walls` accept any iterable of wall-ish
dicts. The `normalize_wall` helper extracts the canonical fields from:

    * LM44 zones / keyZones
        {side, priceMin, priceMax, centerPrice, strengthScore, ...}
    * LM44 walls (single bucket — collapsed to a 1-bucket band)
        {price_bucket, side, total_usd, strengthScore, ...}
    * liquidity_wall_history rows (LM45)
        {side, price_min, price_max, center_price, strength_score, ...}

Missing / partial / None inputs are skipped silently — never raises.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable


# ── Event types ──────────────────────────────────────────────────────────────

EVENT_WALL_CREATED      = "wall_created"
EVENT_WALL_STRENGTHENED = "wall_strengthened"
EVENT_WALL_WEAKENED     = "wall_weakened"
EVENT_WALL_PULLED       = "wall_pulled"
EVENT_WALL_TOUCHED      = "wall_touched"
EVENT_WALL_DEFENDED     = "wall_defended"
EVENT_WALL_BROKEN       = "wall_broken"

VALID_EVENT_TYPES: tuple[str, ...] = (
    EVENT_WALL_CREATED,
    EVENT_WALL_STRENGTHENED,
    EVENT_WALL_WEAKENED,
    EVENT_WALL_PULLED,
    EVENT_WALL_TOUCHED,
    EVENT_WALL_DEFENDED,
    EVENT_WALL_BROKEN,
)


# ── Thresholds ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class WallEventThresholds:
    """
    Tunable thresholds for `detect_wall_events`. Defaults are conservative
    so the detector does not fire on noise.
    """
    min_strength:               float = 30.0   # walls below this are ignored
    created_strength_threshold: float = 50.0   # new wall must reach this
    strengthened_delta_pct:     float = 15.0   # strength rise to fire
    weakened_delta_pct:         float = 15.0   # strength drop to fire
    touch_distance_pct:         float = 0.50   # % of price away from wall center
    broken_distance_pct:        float = 0.50   # % past band edge to call broken


# ── Internal canonical wall ──────────────────────────────────────────────────

@dataclass
class _Wall:
    """Canonical wall used inside the detector. Always price_low <= price_high."""
    side:       str
    price_low:  float
    price_high: float
    price_mid:  float
    strength:   float
    raw:        dict = field(default_factory=dict)


# ── Normalization ────────────────────────────────────────────────────────────

def normalize_wall(w: dict | None) -> _Wall | None:
    """
    Accept a wall-shaped dict from any of the LM44/LM45 sources and return
    a canonical _Wall. Returns None when fields are missing or invalid.
    """
    if not isinstance(w, dict):
        return None

    side = w.get("side")
    if side not in ("bid", "ask"):
        return None

    # Try LM44-style camelCase first, then LM45 snake_case, then single-bucket.
    price_low  = w.get("priceMin")
    if price_low is None:
        price_low = w.get("price_min")
    price_high = w.get("priceMax")
    if price_high is None:
        price_high = w.get("price_max")
    price_mid  = w.get("centerPrice")
    if price_mid is None:
        price_mid = w.get("center_price")
    if price_mid is None:
        price_mid = w.get("price_bucket")

    # Single-bucket walls collapse to a degenerate band at price_mid.
    if price_low is None and price_mid is not None:
        price_low = price_mid
    if price_high is None and price_mid is not None:
        price_high = price_mid
    if price_low is None or price_high is None or price_mid is None:
        return None

    strength = w.get("strengthScore")
    if strength is None:
        strength = w.get("strength_score")
    if strength is None:
        strength = w.get("strength")
    if strength is None:
        return None

    try:
        lo, hi = float(price_low), float(price_high)
        return _Wall(
            side=side,
            price_low=min(lo, hi),
            price_high=max(lo, hi),
            price_mid=float(price_mid),
            strength=float(strength),
            raw=w,
        )
    except (TypeError, ValueError):
        return None


# ── Matching ─────────────────────────────────────────────────────────────────

def _overlap(a: _Wall, b: _Wall) -> bool:
    """Same side AND price bands intersect (inclusive)."""
    return a.side == b.side and not (
        a.price_high < b.price_low or b.price_high < a.price_low
    )


def _match_walls(
    prev: list[_Wall], cur: list[_Wall],
) -> tuple[list[tuple[_Wall, _Wall]], list[_Wall], list[_Wall]]:
    """
    Greedy 1:1 match by side + price-band overlap. Prev walls are matched
    in strength-desc order to the closest available current wall (by mid
    price). Returns (matched_pairs, unmatched_prev, unmatched_cur).
    """
    available_cur = list(cur)
    matched: list[tuple[_Wall, _Wall]] = []
    unmatched_prev: list[_Wall] = []

    for p in sorted(prev, key=lambda x: (-x.strength, x.price_mid)):
        candidates = [c for c in available_cur if _overlap(p, c)]
        if not candidates:
            unmatched_prev.append(p)
            continue
        best = min(candidates, key=lambda c: abs(c.price_mid - p.price_mid))
        matched.append((p, best))
        available_cur.remove(best)

    return matched, unmatched_prev, available_cur


# ── Helpers ──────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _distance_pct(price: float, ref: float) -> float:
    """|price - ref| / |price| × 100. Returns inf when price is 0/None."""
    if not price:
        return float("inf")
    return abs(price - ref) / abs(price) * 100.0


def _past_band(wall: _Wall, price: float) -> bool:
    """Is the current price strictly past the wall (bid: below low, ask: above high)?"""
    if wall.side == "bid":
        return price < wall.price_low
    return price > wall.price_high


def _past_band_pct(wall: _Wall, price: float) -> float:
    """How far past the band, as a % of the current price. 0 if not past."""
    if not _past_band(wall, price) or not price:
        return 0.0
    if wall.side == "bid":
        return (wall.price_low - price) / abs(price) * 100.0
    return (price - wall.price_high) / abs(price) * 100.0


def _safe_delta_pct(cur: float, prev: float) -> float | None:
    """(cur - prev) / prev × 100. None when prev is 0/None."""
    if prev is None or prev == 0:
        return None
    return (cur - prev) / prev * 100.0


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _make_event(
    event_type: str,
    wall: _Wall,
    *,
    symbol: str,
    exchange: str,
    timeframe: str,
    event_ts: str,
    previous_strength: float | None,
    current_price: float | None,
    reason: str,
    confidence: float,
    extra_metadata: dict | None = None,
) -> dict:
    delta = _safe_delta_pct(wall.strength, previous_strength) if previous_strength is not None else None
    dist  = _distance_pct(current_price, wall.price_mid) if current_price else None
    metadata: dict = {"raw": wall.raw}
    if extra_metadata:
        metadata.update(extra_metadata)
    return {
        "symbol":                symbol,
        "exchange":              exchange,
        "timeframe":             timeframe,
        "event_ts":              event_ts,
        "event_type":            event_type,
        "side":                  wall.side,
        "price_low":             wall.price_low,
        "price_high":            wall.price_high,
        "price_mid":             wall.price_mid,
        "strength":              wall.strength,
        "previous_strength":     previous_strength,
        "strength_delta_pct":    round(delta, 3) if delta is not None else None,
        "distance_to_price_pct": round(dist, 4)  if dist  is not None else None,
        "confidence":            round(_clamp01(confidence), 3),
        "reason":                reason,
        "metadata":              metadata,
    }


# ── Main detector ────────────────────────────────────────────────────────────

def detect_wall_events(
    *,
    previous_walls: Iterable[dict] | None,
    current_walls:  Iterable[dict] | None,
    symbol:         str = "",
    exchange:       str = "binance_spot",
    timeframe:      str = "",
    current_price:  float | None = None,
    event_ts:       str | None = None,
    thresholds:     WallEventThresholds | None = None,
) -> list[dict]:
    """
    Compare two snapshots of liquidity walls and emit deterministic events.

    Returns a list of event dicts sorted by (event_type, side, price_mid).
    Tolerant of partial / None / malformed input — never raises; bad
    entries are silently skipped.
    """
    th = thresholds or WallEventThresholds()
    ts = event_ts or _now_iso()

    # Normalize + filter by min_strength.
    def _norm_list(src: Iterable[dict] | None) -> list[_Wall]:
        out: list[_Wall] = []
        if not src:
            return out
        for w in src:
            n = normalize_wall(w)
            if n is not None and n.strength >= th.min_strength:
                out.append(n)
        return out

    prev_list = _norm_list(previous_walls)
    cur_list  = _norm_list(current_walls)

    matched, unmatched_prev, unmatched_cur = _match_walls(prev_list, cur_list)
    events: list[dict] = []

    # ── unmatched current walls → wall_created ───────────────────────────────
    for c in unmatched_cur:
        if c.strength < th.created_strength_threshold:
            continue
        events.append(_make_event(
            EVENT_WALL_CREATED, c,
            symbol=symbol, exchange=exchange, timeframe=timeframe,
            event_ts=ts, previous_strength=None, current_price=current_price,
            reason=(
                f"new wall at {c.price_mid:.2f} ({c.side}) "
                f"strength {c.strength:.1f}"
            ),
            confidence=c.strength / 100.0,
        ))

    # ── unmatched previous walls → wall_pulled / wall_broken ─────────────────
    for p in unmatched_prev:
        if current_price is not None and current_price > 0 and _past_band(p, current_price):
            past = _past_band_pct(p, current_price)
            if past >= th.broken_distance_pct:
                events.append(_make_event(
                    EVENT_WALL_BROKEN, p,
                    symbol=symbol, exchange=exchange, timeframe=timeframe,
                    event_ts=ts, previous_strength=p.strength,
                    current_price=current_price,
                    reason=(
                        f"wall vanished; price now {past:.3f}% past "
                        f"the {p.side} band"
                    ),
                    confidence=past / (th.broken_distance_pct * 2.0),
                    extra_metadata={"past_band_pct": past, "matched": False},
                ))
                continue
        # Otherwise simply pulled.
        events.append(_make_event(
            EVENT_WALL_PULLED, p,
            symbol=symbol, exchange=exchange, timeframe=timeframe,
            event_ts=ts, previous_strength=p.strength,
            current_price=current_price,
            reason=f"wall at {p.price_mid:.2f} ({p.side}) disappeared",
            confidence=p.strength / 100.0,
        ))

    # ── matched: state events + position events (with suppression) ───────────
    for prev, cur in matched:
        delta = _safe_delta_pct(cur.strength, prev.strength) or 0.0

        # Provisional state event.
        state_event_type: str | None = None
        if delta >= th.strengthened_delta_pct:
            state_event_type = EVENT_WALL_STRENGTHENED
        elif delta <= -th.weakened_delta_pct:
            state_event_type = EVENT_WALL_WEAKENED

        # Provisional position event (only when current_price is meaningful).
        position_event_type: str | None = None
        past_pct = 0.0
        dist_pct = float("inf")
        if current_price is not None and current_price > 0:
            if _past_band(cur, current_price):
                past_pct = _past_band_pct(cur, current_price)
                if past_pct >= th.broken_distance_pct and delta <= -th.weakened_delta_pct:
                    position_event_type = EVENT_WALL_BROKEN
            else:
                dist_pct = _distance_pct(current_price, cur.price_mid)
                if dist_pct <= th.touch_distance_pct:
                    if delta >= th.strengthened_delta_pct:
                        position_event_type = EVENT_WALL_DEFENDED
                    else:
                        position_event_type = EVENT_WALL_TOUCHED

        # Suppression: defended subsumes strengthened, broken subsumes weakened.
        if position_event_type == EVENT_WALL_DEFENDED:
            state_event_type = None
        if position_event_type == EVENT_WALL_BROKEN:
            state_event_type = None

        # Emit state event.
        if state_event_type == EVENT_WALL_STRENGTHENED:
            events.append(_make_event(
                EVENT_WALL_STRENGTHENED, cur,
                symbol=symbol, exchange=exchange, timeframe=timeframe,
                event_ts=ts, previous_strength=prev.strength,
                current_price=current_price,
                reason=(
                    f"strength rose {delta:+.1f}% "
                    f"({prev.strength:.1f} → {cur.strength:.1f})"
                ),
                confidence=min(1.0, delta / 30.0),
            ))
        elif state_event_type == EVENT_WALL_WEAKENED:
            events.append(_make_event(
                EVENT_WALL_WEAKENED, cur,
                symbol=symbol, exchange=exchange, timeframe=timeframe,
                event_ts=ts, previous_strength=prev.strength,
                current_price=current_price,
                reason=(
                    f"strength dropped {delta:+.1f}% "
                    f"({prev.strength:.1f} → {cur.strength:.1f})"
                ),
                confidence=min(1.0, abs(delta) / 30.0),
            ))

        # Emit position event.
        if position_event_type == EVENT_WALL_BROKEN:
            events.append(_make_event(
                EVENT_WALL_BROKEN, cur,
                symbol=symbol, exchange=exchange, timeframe=timeframe,
                event_ts=ts, previous_strength=prev.strength,
                current_price=current_price,
                reason=(
                    f"price {past_pct:+.3f}% past {cur.side} band, "
                    f"strength {delta:+.1f}%"
                ),
                confidence=(
                    0.5 * (past_pct / (th.broken_distance_pct * 2.0))
                    + 0.5 * (abs(delta) / 30.0)
                ),
                extra_metadata={"past_band_pct": past_pct, "matched": True},
            ))
        elif position_event_type == EVENT_WALL_DEFENDED:
            events.append(_make_event(
                EVENT_WALL_DEFENDED, cur,
                symbol=symbol, exchange=exchange, timeframe=timeframe,
                event_ts=ts, previous_strength=prev.strength,
                current_price=current_price,
                reason=(
                    f"price within {dist_pct:.3f}% of {cur.side} wall "
                    f"and strength {delta:+.1f}%"
                ),
                confidence=(
                    0.5 * (1.0 - dist_pct / th.touch_distance_pct)
                    + 0.5 * min(1.0, max(0.0, delta) / 30.0)
                ),
            ))
        elif position_event_type == EVENT_WALL_TOUCHED:
            events.append(_make_event(
                EVENT_WALL_TOUCHED, cur,
                symbol=symbol, exchange=exchange, timeframe=timeframe,
                event_ts=ts, previous_strength=prev.strength,
                current_price=current_price,
                reason=(
                    f"price within {dist_pct:.3f}% of {cur.side} wall "
                    f"at {cur.price_mid:.2f}"
                ),
                confidence=1.0 - dist_pct / th.touch_distance_pct,
            ))

    # Deterministic order so callers/tests can compare lists directly.
    events.sort(key=lambda e: (e["event_type"], e["side"], e["price_mid"]))
    return events
