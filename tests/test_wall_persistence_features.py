"""
tests/test_wall_persistence_features.py
----------------------------------------
LM47 — Wall persistence feature engine tests.

Pure-function tests. No network, no Supabase, no time mocks.
Timestamps are passed explicitly so output is fully deterministic.
"""

from __future__ import annotations

from services.wall_persistence_features import (
    STATUS_ACTIVE,
    STATUS_BROKEN,
    STATUS_DEFENDED,
    STATUS_PULLED,
    STATUS_WEAKENING,
    VALID_STATUSES,
    WallFeatureOptions,
    compute_wall_features,
)


# ── Event builder ────────────────────────────────────────────────────────────

def _event(
    *,
    event_type: str,
    ts: str,
    symbol: str = "BTCUSDT",
    exchange: str = "binance_spot",
    timeframe: str = "5m",
    side: str = "bid",
    price_low: float = 67000.0,
    price_high: float = 67010.0,
    price_mid: float | None = None,
    strength: float = 70.0,
    previous_strength: float | None = None,
    distance_to_price_pct: float | None = None,
    confidence: float = 0.9,
    reason: str = "",
    metadata: dict | None = None,
) -> dict:
    mid = price_mid if price_mid is not None else (price_low + price_high) / 2.0
    return {
        "symbol":                symbol,
        "exchange":              exchange,
        "timeframe":             timeframe,
        "event_ts":              ts,
        "event_type":            event_type,
        "side":                  side,
        "price_low":             price_low,
        "price_high":            price_high,
        "price_mid":             mid,
        "strength":              strength,
        "previous_strength":     previous_strength,
        "strength_delta_pct":    None,
        "distance_to_price_pct": distance_to_price_pct,
        "confidence":            confidence,
        "reason":                reason,
        "metadata":              metadata or {},
    }


# ── grouping ─────────────────────────────────────────────────────────────────

class TestGrouping:

    def test_three_events_same_wall_merge_into_one_feature(self):
        events = [
            _event(event_type="wall_created",      ts="2026-06-01T12:00:00+00:00", strength=70.0, reason="r1"),
            _event(event_type="wall_strengthened", ts="2026-06-01T12:00:10+00:00", strength=85.0, previous_strength=70.0, reason="r2"),
            _event(event_type="wall_touched",      ts="2026-06-01T12:00:20+00:00", strength=85.0, distance_to_price_pct=0.05, reason="r3"),
        ]
        feats = compute_wall_features(events)
        assert len(feats) == 1
        f = feats[0]
        assert f["touch_count"]        == 1
        assert f["strengthen_count"]   == 1
        assert f["max_strength"]       == 85.0
        assert f["min_strength"]       == 70.0
        assert f["current_strength"]   == 85.0
        assert f["first_seen_ts"]      == "2026-06-01T12:00:00+00:00"
        assert f["last_seen_ts"]       == "2026-06-01T12:00:20+00:00"

    def test_different_sides_kept_separate(self):
        events = [
            _event(event_type="wall_created", ts="2026-06-01T12:00:00+00:00",
                   side="bid",  price_low=67000, price_high=67010),
            _event(event_type="wall_created", ts="2026-06-01T12:00:00+00:00",
                   side="ask",  price_low=67500, price_high=67510),
            _event(event_type="wall_created", ts="2026-06-01T12:00:00+00:00",
                   side="bid",  price_low=66000, price_high=66010),
        ]
        feats = compute_wall_features(events)
        assert len(feats) == 3
        sides_count = {f["side"]: 0 for f in feats}
        for f in feats:
            sides_count[f["side"]] += 1
        assert sides_count == {"bid": 2, "ask": 1}

    def test_walls_too_far_apart_not_merged(self):
        events = [
            _event(event_type="wall_created", ts="2026-06-01T12:00:00+00:00",
                   price_low=67000, price_high=67010, strength=70.0),
            _event(event_type="wall_created", ts="2026-06-01T12:00:00+00:00",
                   price_low=80000, price_high=80010, strength=70.0),
        ]
        feats = compute_wall_features(events, options=WallFeatureOptions(zone_merge_pct=0.10))
        assert len(feats) == 2

    def test_walls_within_zone_merge_pct_merge(self):
        # 67005 mid; 67100 mid → 0.14% apart. zone_merge_pct=2.0 merges them.
        events = [
            _event(event_type="wall_created", ts="2026-06-01T12:00:00+00:00",
                   price_low=67000, price_high=67010, strength=70.0),
            _event(event_type="wall_strengthened", ts="2026-06-01T12:00:30+00:00",
                   price_low=67095, price_high=67105, strength=85.0, previous_strength=70.0),
        ]
        feats = compute_wall_features(events, options=WallFeatureOptions(zone_merge_pct=2.0))
        assert len(feats) == 1
        # Group band expanded to span both contributing bands.
        assert feats[0]["price_low"]  == 67000.0
        assert feats[0]["price_high"] == 67105.0


# ── deterministic wall_id ────────────────────────────────────────────────────

class TestWallId:

    def test_same_input_same_wall_id(self):
        events = [
            _event(event_type="wall_created", ts="2026-06-01T12:00:00+00:00", strength=70.0),
            _event(event_type="wall_touched", ts="2026-06-01T12:00:10+00:00", strength=70.0),
        ]
        a = compute_wall_features(events)
        b = compute_wall_features(events)
        assert a[0]["wall_id"] == b[0]["wall_id"]
        assert a == b

    def test_different_symbols_yield_different_wall_ids(self):
        events = [
            _event(event_type="wall_created", ts="2026-06-01T12:00:00+00:00",
                   symbol="BTCUSDT", strength=70.0),
            _event(event_type="wall_created", ts="2026-06-01T12:00:00+00:00",
                   symbol="ETHUSDT", strength=70.0),
        ]
        feats = compute_wall_features(events)
        wall_ids = {f["wall_id"] for f in feats}
        assert len(wall_ids) == 2

    def test_wall_id_format(self):
        events = [_event(event_type="wall_created", ts="2026-06-01T12:00:00+00:00", strength=70.0)]
        feats = compute_wall_features(events)
        assert feats[0]["wall_id"].startswith("wall_")
        assert len(feats[0]["wall_id"]) == len("wall_") + 12


# ── persistence_seconds ──────────────────────────────────────────────────────

class TestPersistenceSeconds:

    def test_basic_persistence_seconds(self):
        events = [
            _event(event_type="wall_created", ts="2026-06-01T12:00:00+00:00", strength=70.0),
            _event(event_type="wall_touched", ts="2026-06-01T12:01:00+00:00", strength=70.0),
        ]
        feats = compute_wall_features(events)
        assert feats[0]["persistence_seconds"] == 60.0

    def test_zero_when_single_event(self):
        events = [_event(event_type="wall_created", ts="2026-06-01T12:00:00+00:00", strength=70.0)]
        feats = compute_wall_features(events)
        assert feats[0]["persistence_seconds"] == 0.0

    def test_min_persistence_seconds_filters_short_walls(self):
        events = [
            _event(event_type="wall_created", ts="2026-06-01T12:00:00+00:00", strength=70.0),
            _event(event_type="wall_touched", ts="2026-06-01T12:00:05+00:00", strength=70.0),
        ]
        feats = compute_wall_features(
            events, options=WallFeatureOptions(min_persistence_seconds=10.0),
        )
        assert feats == []


# ── counts ───────────────────────────────────────────────────────────────────

class TestCounts:

    def test_all_six_counts_increment_correctly(self):
        events = [
            _event(event_type="wall_created",      ts="2026-06-01T12:00:00+00:00", strength=70.0),
            _event(event_type="wall_strengthened", ts="2026-06-01T12:00:10+00:00", strength=85.0, previous_strength=70.0),
            _event(event_type="wall_strengthened", ts="2026-06-01T12:00:20+00:00", strength=92.0, previous_strength=85.0),
            _event(event_type="wall_weakened",     ts="2026-06-01T12:00:30+00:00", strength=80.0, previous_strength=92.0),
            _event(event_type="wall_touched",      ts="2026-06-01T12:00:40+00:00", strength=80.0, distance_to_price_pct=0.05),
            _event(event_type="wall_defended",     ts="2026-06-01T12:00:50+00:00", strength=88.0, previous_strength=80.0),
            _event(event_type="wall_broken",       ts="2026-06-01T12:01:00+00:00", strength=40.0, previous_strength=88.0),
        ]
        feats = compute_wall_features(events)
        f = feats[0]
        assert f["strengthen_count"] == 2
        assert f["weaken_count"]     == 1
        assert f["touch_count"]      == 1
        assert f["defense_count"]    == 1
        assert f["break_count"]      == 1
        assert f["pull_count"]       == 0


# ── strength min / max / delta ───────────────────────────────────────────────

class TestStrengthAggregates:

    def test_min_max_current_delta(self):
        events = [
            _event(event_type="wall_created",      ts="2026-06-01T12:00:00+00:00", strength=50.0),
            _event(event_type="wall_strengthened", ts="2026-06-01T12:00:10+00:00", strength=80.0, previous_strength=50.0),
            _event(event_type="wall_weakened",     ts="2026-06-01T12:00:20+00:00", strength=40.0, previous_strength=80.0),
            _event(event_type="wall_strengthened", ts="2026-06-01T12:00:30+00:00", strength=70.0, previous_strength=40.0),
        ]
        feats = compute_wall_features(events)
        f = feats[0]
        assert f["min_strength"]     == 40.0
        assert f["max_strength"]     == 80.0
        assert f["current_strength"] == 70.0
        # (70 - 50) / 50 * 100 = 40%
        assert f["strength_delta_pct"] == 40.0

    def test_avg_distance_to_price(self):
        events = [
            _event(event_type="wall_created", ts="2026-06-01T12:00:00+00:00", strength=70.0),
            _event(event_type="wall_touched", ts="2026-06-01T12:00:10+00:00", strength=70.0,
                   distance_to_price_pct=0.10),
            _event(event_type="wall_touched", ts="2026-06-01T12:00:20+00:00", strength=70.0,
                   distance_to_price_pct=0.30),
        ]
        feats = compute_wall_features(events)
        # Mean of [0.10, 0.30] = 0.20 (the created event has no distance).
        assert feats[0]["avg_distance_to_price_pct"] == 0.20


# ── status ───────────────────────────────────────────────────────────────────

class TestStatus:

    def test_status_active_only_created_and_strengthened(self):
        events = [
            _event(event_type="wall_created",      ts="2026-06-01T12:00:00+00:00", strength=70.0),
            _event(event_type="wall_strengthened", ts="2026-06-01T12:00:10+00:00", strength=85.0, previous_strength=70.0),
        ]
        feats = compute_wall_features(events)
        assert feats[0]["status"] == STATUS_ACTIVE

    def test_status_weakening_last_event_weakened(self):
        events = [
            _event(event_type="wall_created",  ts="2026-06-01T12:00:00+00:00", strength=80.0),
            _event(event_type="wall_weakened", ts="2026-06-01T12:00:10+00:00", strength=55.0, previous_strength=80.0),
        ]
        feats = compute_wall_features(events)
        assert feats[0]["status"]          == STATUS_WEAKENING
        assert feats[0]["last_event_type"] == "wall_weakened"

    def test_status_defended_last_event_defended(self):
        events = [
            _event(event_type="wall_created",  ts="2026-06-01T12:00:00+00:00", strength=70.0),
            _event(event_type="wall_defended", ts="2026-06-01T12:00:10+00:00", strength=85.0, previous_strength=70.0),
        ]
        feats = compute_wall_features(events)
        assert feats[0]["status"] == STATUS_DEFENDED

    def test_status_broken_last_event_broken(self):
        events = [
            _event(event_type="wall_created", ts="2026-06-01T12:00:00+00:00", strength=70.0),
            _event(event_type="wall_broken",  ts="2026-06-01T12:00:10+00:00", strength=40.0, previous_strength=70.0),
        ]
        feats = compute_wall_features(events)
        assert feats[0]["status"] == STATUS_BROKEN

    def test_status_pulled_last_event_pulled(self):
        events = [
            _event(event_type="wall_created", ts="2026-06-01T12:00:00+00:00", strength=70.0),
            _event(event_type="wall_pulled",  ts="2026-06-01T12:00:10+00:00", strength=0.0, previous_strength=70.0),
        ]
        feats = compute_wall_features(events)
        assert feats[0]["status"] == STATUS_PULLED

    def test_status_weakening_by_count_when_last_event_neutral(self):
        # Last event is wall_touched (no terminal label), but the wall has
        # had more weakens than strengthens → weakening.
        events = [
            _event(event_type="wall_created",  ts="2026-06-01T12:00:00+00:00", strength=80.0),
            _event(event_type="wall_weakened", ts="2026-06-01T12:00:10+00:00", strength=60.0, previous_strength=80.0),
            _event(event_type="wall_weakened", ts="2026-06-01T12:00:20+00:00", strength=45.0, previous_strength=60.0),
            _event(event_type="wall_touched",  ts="2026-06-01T12:00:30+00:00", strength=45.0),
        ]
        feats = compute_wall_features(events)
        assert feats[0]["status"] == STATUS_WEAKENING


# ── missing / partial inputs ─────────────────────────────────────────────────

class TestMissingAndPartial:

    def test_none_input_returns_empty(self):
        assert compute_wall_features(None) == []

    def test_empty_input_returns_empty(self):
        assert compute_wall_features([]) == []

    def test_malformed_events_silently_skipped(self):
        # 6 garbage entries + 1 valid event → 1 feature.
        events = [
            None,
            "not a dict",                                                # type: ignore[list-item]
            {},                                                          # empty
            {"event_type": "wall_created"},                              # missing side/prices
            {"event_type": "bogus", "side": "bid", "price_low": 1,
             "price_high": 2, "price_mid": 1.5},                         # invalid type
            {"event_type": "wall_created", "side": "x", "price_low": 1,
             "price_high": 2, "price_mid": 1.5},                         # bad side
            _event(event_type="wall_created", ts="2026-06-01T12:00:00+00:00", strength=70.0),
        ]
        feats = compute_wall_features(events)
        assert len(feats) == 1

    def test_iterable_generator_accepted(self):
        def _gen():
            yield _event(event_type="wall_created", ts="2026-06-01T12:00:00+00:00", strength=70.0)
        feats = compute_wall_features(_gen())
        assert len(feats) == 1


# ── deterministic output ─────────────────────────────────────────────────────

class TestDeterministicOutput:

    def test_same_input_identical_lists(self):
        events = [
            _event(event_type="wall_created", ts="2026-06-01T12:00:00+00:00",
                   side="ask", price_low=67500, price_high=67510, strength=70.0),
            _event(event_type="wall_created", ts="2026-06-01T12:00:00+00:00",
                   side="bid", price_low=67000, price_high=67010, strength=70.0),
            _event(event_type="wall_touched", ts="2026-06-01T12:00:10+00:00",
                   side="bid", price_low=67000, price_high=67010, strength=70.0),
        ]
        a = compute_wall_features(events)
        b = compute_wall_features(events)
        assert a == b

    def test_sorted_by_symbol_timeframe_side_price(self):
        events = [
            _event(event_type="wall_created", ts="2026-06-01T12:00:00+00:00",
                   side="ask", price_low=67500, price_high=67510, strength=70.0),
            _event(event_type="wall_created", ts="2026-06-01T12:00:00+00:00",
                   side="bid", price_low=67000, price_high=67010, strength=70.0),
            _event(event_type="wall_created", ts="2026-06-01T12:00:00+00:00",
                   side="bid", price_low=66000, price_high=66010, strength=70.0),
        ]
        feats = compute_wall_features(events)
        keys = [(f["symbol"], f["timeframe"], f["side"], f["price_mid"]) for f in feats]
        assert keys == sorted(keys)

    def test_feature_dict_has_all_required_fields(self):
        events = [_event(event_type="wall_created", ts="2026-06-01T12:00:00+00:00", strength=70.0)]
        feats = compute_wall_features(events)
        assert feats
        required = {
            "wall_id", "symbol", "exchange", "timeframe", "side",
            "price_low", "price_high", "price_mid",
            "first_seen_ts", "last_seen_ts", "persistence_seconds",
            "touch_count", "defense_count", "break_count", "pull_count",
            "strengthen_count", "weaken_count",
            "current_strength", "max_strength", "min_strength",
            "strength_delta_pct", "avg_distance_to_price_pct",
            "last_event_type", "confidence", "status", "reasons", "metadata",
        }
        for f in feats:
            assert required <= set(f.keys())
            assert f["status"] in VALID_STATUSES
            assert isinstance(f["reasons"], list)
            assert isinstance(f["metadata"], dict)


# ── min_confidence ───────────────────────────────────────────────────────────

class TestMinConfidence:

    def test_low_confidence_events_filtered_before_grouping(self):
        events = [
            _event(event_type="wall_created", ts="2026-06-01T12:00:00+00:00",
                   strength=70.0, confidence=0.10),
            _event(event_type="wall_touched", ts="2026-06-01T12:00:10+00:00",
                   strength=70.0, confidence=0.10),
        ]
        feats = compute_wall_features(
            events, options=WallFeatureOptions(min_confidence=0.5),
        )
        assert feats == []

    def test_high_confidence_kept(self):
        events = [
            _event(event_type="wall_created", ts="2026-06-01T12:00:00+00:00",
                   strength=70.0, confidence=0.95),
        ]
        feats = compute_wall_features(
            events, options=WallFeatureOptions(min_confidence=0.5),
        )
        assert len(feats) == 1


# ── reasons ──────────────────────────────────────────────────────────────────

class TestReasons:

    def test_keeps_last_n_reasons(self):
        events = [
            _event(event_type="wall_created", ts=f"2026-06-01T12:00:{i:02d}+00:00",
                   strength=70.0, reason=f"reason_{i}")
            for i in range(10)
        ]
        feats = compute_wall_features(
            events, options=WallFeatureOptions(max_reasons=3),
        )
        assert feats[0]["reasons"] == ["reason_7", "reason_8", "reason_9"]
