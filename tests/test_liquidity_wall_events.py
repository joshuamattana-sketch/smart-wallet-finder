"""
tests/test_liquidity_wall_events.py
------------------------------------
LM46 — Liquidity wall event detector tests.

Pure-function tests. No network, no Supabase, no time mocks needed
(we pass `event_ts` explicitly so output is deterministic).
"""

from __future__ import annotations

import pytest

from services.liquidity_wall_events import (
    EVENT_WALL_BROKEN,
    EVENT_WALL_CREATED,
    EVENT_WALL_DEFENDED,
    EVENT_WALL_PULLED,
    EVENT_WALL_STRENGTHENED,
    EVENT_WALL_TOUCHED,
    EVENT_WALL_WEAKENED,
    VALID_EVENT_TYPES,
    WallEventThresholds,
    detect_wall_events,
    normalize_wall,
)

_FIXED_TS = "2026-06-01T12:00:00+00:00"


# ── Wall builders ────────────────────────────────────────────────────────────

def _zone(side: str, price_min: float, price_max: float, strength: float,
          *, center: float | None = None) -> dict:
    return {
        "side":          side,
        "priceMin":      price_min,
        "priceMax":      price_max,
        "centerPrice":   center if center is not None else (price_min + price_max) / 2.0,
        "strengthScore": strength,
        "totalUsd":      1_000_000.0,
        "maxIntensity":  90.0,
        "bucketCount":   5,
        "label":         f"{side.capitalize()} Zone",
    }


def _run(prev, cur, *, current_price=None, thresholds=None):
    return detect_wall_events(
        previous_walls=prev,
        current_walls=cur,
        symbol="BTCUSDT",
        timeframe="5m",
        current_price=current_price,
        event_ts=_FIXED_TS,
        thresholds=thresholds,
    )


# ── created ──────────────────────────────────────────────────────────────────

class TestCreated:

    def test_emits_wall_created_when_new(self):
        cur = [_zone("bid", 67000, 67010, 80.0)]
        events = _run([], cur)
        assert len(events) == 1
        ev = events[0]
        assert ev["event_type"]         == EVENT_WALL_CREATED
        assert ev["side"]               == "bid"
        assert ev["strength"]           == 80.0
        assert ev["previous_strength"]  is None
        assert ev["price_mid"]          == 67005.0
        assert ev["confidence"]         > 0.5
        assert ev["symbol"]             == "BTCUSDT"
        assert ev["timeframe"]          == "5m"
        assert ev["exchange"]           == "binance_spot"
        assert ev["event_ts"]           == _FIXED_TS
        assert "metadata" in ev
        assert "raw" in ev["metadata"]

    def test_skipped_when_below_created_threshold(self):
        cur = [_zone("bid", 67000, 67010, 35.0)]  # below default 50
        events = _run([], cur)
        assert events == []


# ── strengthened ─────────────────────────────────────────────────────────────

class TestStrengthened:

    def test_emits_wall_strengthened(self):
        prev = [_zone("bid", 67000, 67010, 50.0)]
        cur  = [_zone("bid", 67000, 67010, 70.0)]
        events = _run(prev, cur)
        assert len(events) == 1
        ev = events[0]
        assert ev["event_type"]        == EVENT_WALL_STRENGTHENED
        assert ev["previous_strength"] == 50.0
        assert ev["strength"]          == 70.0
        assert ev["strength_delta_pct"] == 40.0
        assert ev["confidence"]        > 0.5

    def test_not_emitted_below_threshold(self):
        # 50 → 55 = +10% < default 15% threshold → silent
        prev = [_zone("bid", 67000, 67010, 50.0)]
        cur  = [_zone("bid", 67000, 67010, 55.0)]
        assert _run(prev, cur) == []


# ── weakened ─────────────────────────────────────────────────────────────────

class TestWeakened:

    def test_emits_wall_weakened(self):
        prev = [_zone("ask", 67500, 67520, 80.0)]
        cur  = [_zone("ask", 67500, 67520, 55.0)]
        events = _run(prev, cur)
        assert len(events) == 1
        ev = events[0]
        assert ev["event_type"]         == EVENT_WALL_WEAKENED
        assert ev["previous_strength"]  == 80.0
        assert ev["strength"]           == 55.0
        assert ev["strength_delta_pct"] == -31.25
        assert ev["confidence"]         > 0.5

    def test_not_emitted_for_tiny_drop(self):
        prev = [_zone("ask", 67500, 67520, 80.0)]
        cur  = [_zone("ask", 67500, 67520, 75.0)]  # -6.25% < 15%
        assert _run(prev, cur) == []


# ── pulled ───────────────────────────────────────────────────────────────────

class TestPulled:

    def test_emits_wall_pulled_when_vanished(self):
        prev = [_zone("bid", 67000, 67010, 70.0)]
        cur  = []
        events = _run(prev, cur)
        assert len(events) == 1
        ev = events[0]
        assert ev["event_type"]        == EVENT_WALL_PULLED
        assert ev["previous_strength"] == 70.0
        assert ev["confidence"]        > 0.5

    def test_no_event_for_pull_below_min_strength(self):
        # Previous strength below min_strength → not considered a wall.
        prev = [_zone("bid", 67000, 67010, 20.0)]
        cur  = []
        assert _run(prev, cur) == []


# ── touched / defended ───────────────────────────────────────────────────────

class TestTouchedAndDefended:

    def test_touched_when_price_near_wall_no_strengthening(self):
        # Wall steady (delta=0), price right at wall mid.
        prev = [_zone("bid", 66900, 67100, 70.0)]
        cur  = [_zone("bid", 66900, 67100, 70.0)]
        events = _run(prev, cur, current_price=67000)
        assert len(events) == 1
        ev = events[0]
        assert ev["event_type"]            == EVENT_WALL_TOUCHED
        assert ev["distance_to_price_pct"] == 0.0
        assert ev["confidence"]            > 0.5

    def test_defended_when_price_near_and_strength_up(self):
        # Same band, strength jumped 50 → 70 (+40%) under pressure at price.
        prev = [_zone("bid", 66900, 67100, 50.0)]
        cur  = [_zone("bid", 66900, 67100, 70.0)]
        events = _run(prev, cur, current_price=67000)
        # Defended subsumes strengthened — exactly one event.
        assert len(events) == 1
        ev = events[0]
        assert ev["event_type"]         == EVENT_WALL_DEFENDED
        assert ev["previous_strength"]  == 50.0
        assert ev["strength"]           == 70.0
        assert ev["strength_delta_pct"] == 40.0

    def test_no_position_event_when_price_far(self):
        prev = [_zone("bid", 66900, 67100, 70.0)]
        cur  = [_zone("bid", 66900, 67100, 70.0)]
        # 67500 is well outside touch_distance_pct of 67000 (~0.75%)
        assert _run(prev, cur, current_price=67500) == []


# ── broken ───────────────────────────────────────────────────────────────────

class TestBroken:

    def test_broken_when_price_past_band_and_strength_dropped(self):
        prev = [_zone("bid", 67000, 67050, 80.0)]
        cur  = [_zone("bid", 67000, 67050, 50.0)]
        # Price now 0.7% below band low (66530 < 67000).
        events = _run(prev, cur, current_price=66530)
        assert len(events) == 1
        ev = events[0]
        assert ev["event_type"]    == EVENT_WALL_BROKEN
        assert ev["metadata"].get("past_band_pct", 0) > 0
        # Weakened is suppressed because broken fired for the same wall.
        assert all(e["event_type"] != EVENT_WALL_WEAKENED for e in events)

    def test_broken_when_wall_vanished_and_price_past_band(self):
        prev = [_zone("ask", 67100, 67150, 70.0)]
        cur  = []  # wall gone
        events = _run(prev, cur, current_price=67900)  # well above ask band
        assert len(events) == 1
        ev = events[0]
        assert ev["event_type"] == EVENT_WALL_BROKEN
        assert ev["metadata"].get("matched") is False

    def test_pulled_not_broken_when_price_didnt_pass(self):
        prev = [_zone("ask", 67100, 67150, 70.0)]
        cur  = []
        events = _run(prev, cur, current_price=67000)  # below ask, not past
        assert len(events) == 1
        assert events[0]["event_type"] == EVENT_WALL_PULLED


# ── noise suppression ────────────────────────────────────────────────────────

class TestNoiseSuppression:

    def test_tiny_change_emits_nothing(self):
        # +4% strength change is below threshold → 0 events.
        prev = [_zone("bid", 67000, 67010, 50.0)]
        cur  = [_zone("bid", 67000, 67010, 52.0)]
        assert _run(prev, cur, current_price=67500) == []

    def test_walls_below_min_strength_ignored(self):
        # Both walls below min_strength → not even considered.
        prev = [_zone("bid", 67000, 67010, 10.0)]
        cur  = [_zone("bid", 67000, 67010, 25.0)]
        assert _run(prev, cur) == []


# ── partial / missing inputs ─────────────────────────────────────────────────

class TestPartialAndMissingInputs:

    def test_none_inputs_return_empty(self):
        assert detect_wall_events(
            previous_walls=None, current_walls=None,
            event_ts=_FIXED_TS,
        ) == []

    def test_empty_inputs_return_empty(self):
        assert _run([], []) == []

    def test_malformed_entries_skipped(self):
        prev = [
            None,                                  # None entry
            "not a dict",                          # wrong type
            {"side": "x"},                         # bad side
            {"side": "bid"},                       # missing prices
            {"side": "bid", "priceMin": "abc",     # un-castable
             "priceMax": "xyz", "centerPrice": "n",
             "strengthScore": "z"},
            _zone("bid", 67000, 67010, 70.0),      # one valid entry
        ]
        # The valid entry vanishes in cur → wall_pulled.
        events = _run(prev, [])
        assert len(events) == 1
        assert events[0]["event_type"] == EVENT_WALL_PULLED

    def test_iterable_input_accepted(self):
        # Generators work — the detector uses Iterable[dict].
        def _gen():
            yield _zone("bid", 67000, 67010, 80.0)
        events = _run(prev=[], cur=_gen())  # type: ignore[arg-type]
        assert len(events) == 1
        assert events[0]["event_type"] == EVENT_WALL_CREATED


# ── deterministic shape ──────────────────────────────────────────────────────

class TestDeterministic:

    def test_same_inputs_produce_identical_lists(self):
        prev = [
            _zone("bid", 67000, 67050, 50.0),
            _zone("ask", 67200, 67250, 60.0),
        ]
        cur = [
            _zone("bid", 67000, 67050, 75.0),  # strengthened
            _zone("ask", 67200, 67250, 30.0),  # weakened then dropped by min_strength? 30 == min_strength, so still in
        ]
        out_a = _run(prev, cur)
        out_b = _run(prev, cur)
        assert out_a == out_b

    def test_output_sorted_by_event_type_side_price(self):
        prev = []
        cur = [
            _zone("ask", 67300, 67310, 80.0),
            _zone("bid", 67000, 67010, 80.0),
            _zone("bid", 67100, 67110, 80.0),
        ]
        events = _run(prev, cur)
        keys = [(e["event_type"], e["side"], e["price_mid"]) for e in events]
        assert keys == sorted(keys)

    def test_event_dict_has_all_required_fields(self):
        events = _run([], [_zone("bid", 67000, 67010, 80.0)])
        assert events
        required = {
            "symbol", "exchange", "timeframe", "event_ts", "event_type",
            "side", "price_low", "price_high", "price_mid", "strength",
            "previous_strength", "strength_delta_pct",
            "distance_to_price_pct", "confidence", "reason", "metadata",
        }
        for ev in events:
            assert required <= set(ev.keys())
            assert ev["event_type"] in VALID_EVENT_TYPES


# ── threshold tuning ─────────────────────────────────────────────────────────

class TestThresholds:

    def test_custom_thresholds_change_emission(self):
        # Default 15% threshold → no event; 5% threshold → strengthened.
        prev = [_zone("bid", 67000, 67010, 50.0)]
        cur  = [_zone("bid", 67000, 67010, 55.0)]  # +10%
        assert _run(prev, cur) == []
        loose = WallEventThresholds(strengthened_delta_pct=5.0)
        events = _run(prev, cur, thresholds=loose)
        assert len(events) == 1
        assert events[0]["event_type"] == EVENT_WALL_STRENGTHENED

    def test_min_strength_excludes_weak_walls(self):
        prev = []
        cur  = [_zone("bid", 67000, 67010, 25.0)]  # below default min_strength 30
        assert _run(prev, cur) == []
        # Drop min_strength to 20 → wall qualifies but is below
        # created_strength_threshold (50) → still nothing.
        events = _run(prev, cur, thresholds=WallEventThresholds(
            min_strength=20.0, created_strength_threshold=20.0,
        ))
        assert len(events) == 1
        assert events[0]["event_type"] == EVENT_WALL_CREATED


# ── normalize_wall ───────────────────────────────────────────────────────────

class TestNormalizeWall:

    def test_camelCase_keyzones(self):
        w = _zone("bid", 67000, 67010, 70.0)
        n = normalize_wall(w)
        assert n is not None
        assert n.side       == "bid"
        assert n.price_low  == 67000.0
        assert n.price_high == 67010.0
        assert n.price_mid  == 67005.0
        assert n.strength   == 70.0

    def test_snake_case_wall_history_row(self):
        row = {
            "side": "ask",
            "price_min": 67500.0,
            "price_max": 67550.0,
            "center_price": 67525.0,
            "strength_score": 80.0,
            "label": "Major Ask Wall",
        }
        n = normalize_wall(row)
        assert n is not None
        assert n.side       == "ask"
        assert n.price_low  == 67500.0
        assert n.price_high == 67550.0
        assert n.strength   == 80.0

    def test_single_bucket_wall(self):
        # LM44 walls (no priceMin/Max) collapse to a degenerate band.
        w = {
            "side": "bid",
            "price_bucket": 67000.0,
            "strengthScore": 70.0,
            "total_usd": 500000.0,
        }
        n = normalize_wall(w)
        assert n is not None
        assert n.price_low == n.price_high == 67000.0
        assert n.price_mid == 67000.0

    def test_returns_none_on_garbage(self):
        assert normalize_wall(None)        is None
        assert normalize_wall("x")         is None  # type: ignore[arg-type]
        assert normalize_wall({})          is None
        assert normalize_wall({"side": "x"}) is None
        assert normalize_wall({"side": "bid"}) is None  # no prices
