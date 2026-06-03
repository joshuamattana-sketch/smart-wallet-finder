"""
tests/test_signal_journal.py
-----------------------------
LM50 — Signal journal foundation tests.

Pure-function tests. No network, no Supabase, no file writes.
All timestamps passed explicitly so output is fully deterministic.
"""

from __future__ import annotations

import pytest

from services.signal_journal import (
    OUTCOME_EXPIRED,
    OUTCOME_INVALIDATED,
    OUTCOME_NO_TRADE,
    OUTCOME_PENDING,
    OUTCOME_TARGET_HIT,
    OUTCOME_UNKNOWN,
    VALID_DIRECTIONS,
    VALID_OUTCOME_STATUSES,
    VALID_SIGNAL_LEVELS,
    create_signal_journal_entries,
    create_signal_journal_entry,
    summarize_signal_journal,
    update_signal_outcome,
)


# ── Signal fixture ──────────────────────────────────────────────────────────

def _signal(
    *,
    signal_id: str = "sig_test_0001",
    symbol: str = "BTCUSDT",
    exchange: str = "binance_spot",
    timeframe: str = "5m",
    signal_ts: str = "2026-06-01T12:00:00+00:00",
    setup_id: str = "setup_test_0001",
    setup_type: str = "long_absorption",
    direction: str = "long",
    signal_level: str = "strong_setup",
    score: float = 82.0,
    confidence: float = 0.88,
    entry_zone_low: float = 67000.0,
    entry_zone_high: float = 67010.0,
    entry_zone_mid: float | None = None,
    invalidation_price: float | None = 66865.99,
    targets: list[float] | None = None,
    reasons: list[str] | None = None,
    risks: list[str] | None = None,
    action_hint: str = "wait_for_retest",
    status: str = "active",
    metadata: dict | None = None,
) -> dict:
    mid = entry_zone_mid if entry_zone_mid is not None else (entry_zone_low + entry_zone_high) / 2.0
    return {
        "signal_id":          signal_id,
        "symbol":             symbol,
        "exchange":           exchange,
        "timeframe":          timeframe,
        "signal_ts":          signal_ts,
        "setup_id":           setup_id,
        "setup_type":         setup_type,
        "direction":          direction,
        "signal_level":       signal_level,
        "score":              score,
        "confidence":         confidence,
        "entry_zone_low":     entry_zone_low,
        "entry_zone_high":    entry_zone_high,
        "entry_zone_mid":     mid,
        "invalidation_price": invalidation_price,
        "targets":            targets if targets is not None else [67215.0, 67425.0],
        "reasons":            reasons or [],
        "risks":              risks or [],
        "action_hint":        action_hint,
        "status":             status,
        "metadata":           metadata or {},
    }


_CREATED_AT = "2026-06-01T12:00:05+00:00"


# ── Creation: long signal ───────────────────────────────────────────────────

class TestCreateFromLongSignal:

    def test_long_signal_creates_pending_journal_entry(self):
        s = _signal(direction="long", signal_level="strong_setup")
        e = create_signal_journal_entry(s, created_at=_CREATED_AT)
        assert e is not None
        assert e["signal_id"]         == "sig_test_0001"
        assert e["direction"]         == "long"
        assert e["signal_level"]      == "strong_setup"
        assert e["entry_zone_mid"]    == 67005.0
        assert e["invalidation_price"] == 66865.99
        assert e["targets"]           == [67215.0, 67425.0]
        assert e["outcome_status"]    == OUTCOME_PENDING
        assert e["outcome_checked_at"] is None
        assert e["max_favorable_excursion_pct"] is None
        assert e["created_at"]        == _CREATED_AT

    def test_required_fields_present(self):
        s = _signal()
        e = create_signal_journal_entry(s, created_at=_CREATED_AT)
        required = {
            "journal_id", "signal_id", "symbol", "exchange", "timeframe",
            "created_at", "signal_ts", "setup_type", "direction",
            "signal_level", "score", "confidence",
            "entry_zone_low", "entry_zone_high", "entry_zone_mid",
            "invalidation_price", "targets", "reasons", "risks",
            "action_hint", "status",
            "outcome_status", "outcome_checked_at",
            "outcome_5m", "outcome_15m", "outcome_1h",
            "max_favorable_excursion_pct", "max_adverse_excursion_pct",
            "notes", "metadata",
        }
        assert required <= set(e.keys())


# ── Creation: short signal ──────────────────────────────────────────────────

class TestCreateFromShortSignal:

    def test_short_signal_creates_pending_journal_entry(self):
        s = _signal(
            signal_id="sig_test_short", direction="short",
            signal_level="strong_setup",
            entry_zone_low=67500, entry_zone_high=67510,
            invalidation_price=67644.02,
            targets=[67294.97, 66985.0],
        )
        e = create_signal_journal_entry(s, created_at=_CREATED_AT)
        assert e is not None
        assert e["direction"]      == "short"
        assert e["outcome_status"] == OUTCOME_PENDING
        # Short geometry: invalidation above entry high.
        assert e["invalidation_price"] > e["entry_zone_high"]
        assert all(t < e["entry_zone_mid"] for t in e["targets"])


# ── Creation: no_trade signal ───────────────────────────────────────────────

class TestCreateFromNoTradeSignal:

    def test_no_trade_signal_yields_no_trade_outcome(self):
        s = _signal(
            signal_level="no_trade", direction="neutral",
            score=0.0, confidence=0.0, action_hint="avoid_trade",
            status="no_trade", invalidation_price=None, targets=[],
        )
        e = create_signal_journal_entry(s, created_at=_CREATED_AT)
        assert e is not None
        assert e["outcome_status"] == OUTCOME_NO_TRADE
        assert e["invalidation_price"] is None
        assert e["targets"]        == []

    def test_neutral_direction_signal_yields_no_trade_outcome(self):
        # Non-no_trade level but neutral direction → still no_trade outcome
        # because the journal can't track without a direction.
        s = _signal(
            signal_level="watch", direction="neutral",
            score=35.0, confidence=0.80,
            invalidation_price=None, targets=[],
        )
        e = create_signal_journal_entry(s, created_at=_CREATED_AT)
        assert e["outcome_status"] == OUTCOME_NO_TRADE


# ── Deterministic journal_id ────────────────────────────────────────────────

class TestDeterministicJournalId:

    def test_same_signal_same_journal_id(self):
        s = _signal()
        a = create_signal_journal_entry(s, created_at=_CREATED_AT)
        b = create_signal_journal_entry(s, created_at="2030-01-01T00:00:00+00:00")
        # journal_id is keyed only on signal_id, so created_at differences
        # do NOT change the id (it stays sticky to the signal).
        assert a["journal_id"] == b["journal_id"]

    def test_different_signal_ids_different_journal_ids(self):
        a = create_signal_journal_entry(
            _signal(signal_id="sig_a"), created_at=_CREATED_AT,
        )
        b = create_signal_journal_entry(
            _signal(signal_id="sig_b"), created_at=_CREATED_AT,
        )
        assert a["journal_id"] != b["journal_id"]

    def test_journal_id_format(self):
        e = create_signal_journal_entry(_signal(), created_at=_CREATED_AT)
        assert e["journal_id"].startswith("journal_")
        assert len(e["journal_id"]) == len("journal_") + 12


# ── Missing / partial inputs ────────────────────────────────────────────────

class TestMissingAndPartial:

    def test_none_signal_returns_none(self):
        assert create_signal_journal_entry(None) is None

    def test_non_dict_signal_returns_none(self):
        assert create_signal_journal_entry("nope") is None  # type: ignore[arg-type]

    def test_missing_fields_returns_none(self):
        # Missing signal_level, entry_zone fields, etc.
        assert create_signal_journal_entry({"signal_id": "x"}) is None

    def test_bad_direction_returns_none(self):
        s = _signal()
        s["direction"] = "sideways"
        assert create_signal_journal_entry(s) is None

    def test_bulk_skips_malformed_and_keeps_valid(self):
        items = [
            None,
            "x",                                       # type: ignore[list-item]
            {},
            {"signal_id": "x"},
            _signal(signal_id="sig_a"),
            _signal(signal_id="sig_b", direction="short",
                    entry_zone_low=67500, entry_zone_high=67510),
        ]
        out = create_signal_journal_entries(items, created_at=_CREATED_AT)
        assert len(out) == 2
        sig_ids = {e["signal_id"] for e in out}
        assert sig_ids == {"sig_a", "sig_b"}

    def test_bulk_none_returns_empty(self):
        assert create_signal_journal_entries(None) == []
        assert create_signal_journal_entries([]) == []

    def test_iterable_generator_accepted(self):
        def _gen():
            yield _signal()
        out = create_signal_journal_entries(_gen(), created_at=_CREATED_AT)
        assert len(out) == 1


# ── Update outcome ──────────────────────────────────────────────────────────

class TestUpdateOutcome:

    def _entry(self) -> dict:
        return create_signal_journal_entry(_signal(), created_at=_CREATED_AT)

    def test_update_to_pending_is_idempotent(self):
        e = self._entry()
        updated = update_signal_outcome(e, {"outcome_status": OUTCOME_PENDING,
                                            "outcome_checked_at": "t+10s"})
        assert updated["outcome_status"]     == OUTCOME_PENDING
        assert updated["outcome_checked_at"] == "t+10s"

    def test_update_to_target_hit(self):
        e = self._entry()
        updated = update_signal_outcome(e, {
            "outcome_status":               OUTCOME_TARGET_HIT,
            "outcome_checked_at":           "2026-06-01T12:05:00+00:00",
            "outcome_5m":                   {"hit_target": 1, "price": 67200.0},
            "max_favorable_excursion_pct":  0.34,
            "max_adverse_excursion_pct":    0.08,
            "notes":                        "first target reached",
        })
        assert updated["outcome_status"] == OUTCOME_TARGET_HIT
        assert updated["max_favorable_excursion_pct"] == 0.34
        assert updated["max_adverse_excursion_pct"]   == 0.08
        assert updated["notes"]          == "first target reached"
        assert updated["outcome_5m"]["hit_target"] == 1

    def test_update_to_invalidated(self):
        e = self._entry()
        updated = update_signal_outcome(e, {
            "outcome_status":               OUTCOME_INVALIDATED,
            "outcome_checked_at":           "2026-06-01T12:05:00+00:00",
            "max_adverse_excursion_pct":    0.45,
            "notes":                        "invalidation price hit",
        })
        assert updated["outcome_status"] == OUTCOME_INVALIDATED
        assert updated["max_adverse_excursion_pct"] == 0.45
        assert updated["notes"]          == "invalidation price hit"

    def test_input_entry_not_mutated(self):
        e = self._entry()
        before_status = e["outcome_status"]
        before_notes  = e["notes"]
        update_signal_outcome(e, {
            "outcome_status": OUTCOME_TARGET_HIT,
            "notes":          "something",
        })
        assert e["outcome_status"] == before_status
        assert e["notes"]          == before_notes

    def test_invalid_outcome_status_ignored(self):
        e = self._entry()
        updated = update_signal_outcome(e, {"outcome_status": "bogus_status",
                                            "notes": "kept"})
        assert updated["outcome_status"] == e["outcome_status"]
        assert updated["notes"]          == "kept"

    def test_unknown_fields_are_dropped(self):
        e = self._entry()
        updated = update_signal_outcome(e, {
            "outcome_status": OUTCOME_TARGET_HIT,
            "bogus_extra":    "ignored",
        })
        assert "bogus_extra" not in updated

    def test_no_trade_entry_status_cannot_be_promoted(self):
        # Informational entries stay informational.
        s = _signal(signal_level="no_trade", direction="neutral",
                    score=0.0, confidence=0.0,
                    invalidation_price=None, targets=[])
        e = create_signal_journal_entry(s, created_at=_CREATED_AT)
        updated = update_signal_outcome(e, {
            "outcome_status": OUTCOME_TARGET_HIT,
            "notes":          "kept",
        })
        assert updated["outcome_status"] == OUTCOME_NO_TRADE
        # But notes and excursion fields are still mergeable.
        assert updated["notes"] == "kept"

    def test_empty_or_none_outcome_returns_copy_unchanged(self):
        e = self._entry()
        assert update_signal_outcome(e, None) == e
        assert update_signal_outcome(e, {})   == e

    def test_non_dict_entry_raises(self):
        with pytest.raises(TypeError):
            update_signal_outcome("not a dict", {"outcome_status": OUTCOME_TARGET_HIT})  # type: ignore[arg-type]


# ── Summarize ───────────────────────────────────────────────────────────────

class TestSummarize:

    def _mixed_entries(self) -> list[dict]:
        return [
            # 2 long strong_setup → 1 target_hit, 1 pending
            update_signal_outcome(
                create_signal_journal_entry(
                    _signal(signal_id="a", direction="long",
                            signal_level="strong_setup"),
                    created_at=_CREATED_AT,
                ),
                {"outcome_status": OUTCOME_TARGET_HIT},
            ),
            create_signal_journal_entry(
                _signal(signal_id="b", direction="long",
                        signal_level="strong_setup"),
                created_at=_CREATED_AT,
            ),
            # 1 short setup, invalidated
            update_signal_outcome(
                create_signal_journal_entry(
                    _signal(signal_id="c", direction="short",
                            signal_level="setup",
                            entry_zone_low=67500, entry_zone_high=67510),
                    created_at=_CREATED_AT,
                ),
                {"outcome_status": OUTCOME_INVALIDATED},
            ),
            # 1 watch level, neutral direction
            create_signal_journal_entry(
                _signal(signal_id="d", direction="neutral",
                        signal_level="watch",
                        invalidation_price=None, targets=[]),
                created_at=_CREATED_AT,
            ),
            # 1 no_trade
            create_signal_journal_entry(
                _signal(signal_id="e", direction="neutral",
                        signal_level="no_trade",
                        score=0.0, confidence=0.0,
                        invalidation_price=None, targets=[]),
                created_at=_CREATED_AT,
            ),
        ]

    def test_total_entries(self):
        s = summarize_signal_journal(self._mixed_entries())
        assert s["total_entries"] == 5

    def test_by_direction(self):
        s = summarize_signal_journal(self._mixed_entries())
        assert s["by_direction"]["long"]    == 2
        assert s["by_direction"]["short"]   == 1
        assert s["by_direction"]["neutral"] == 2

    def test_by_signal_level(self):
        s = summarize_signal_journal(self._mixed_entries())
        assert s["by_signal_level"]["strong_setup"] == 2
        assert s["by_signal_level"]["setup"]        == 1
        assert s["by_signal_level"]["watch"]        == 1
        assert s["by_signal_level"]["no_trade"]     == 1

    def test_by_outcome_status(self):
        s = summarize_signal_journal(self._mixed_entries())
        assert s["by_outcome_status"][OUTCOME_TARGET_HIT]  == 1
        assert s["by_outcome_status"][OUTCOME_INVALIDATED] == 1
        # 1 pending long + 1 pending watch neutral? Neutral starts no_trade.
        assert s["by_outcome_status"][OUTCOME_PENDING]     == 1
        # neutral watch + explicit no_trade = 2 no_trade outcomes
        assert s["by_outcome_status"][OUTCOME_NO_TRADE]    == 2

    def test_by_setup_type_and_symbol(self):
        s = summarize_signal_journal(self._mixed_entries())
        assert s["by_setup_type"]["long_absorption"] == 5
        assert s["by_symbol"]["BTCUSDT"]             == 5

    def test_actionable_count_excludes_no_trade(self):
        s = summarize_signal_journal(self._mixed_entries())
        # strong_setup × 2 + setup × 1 (all non-no_trade) = 3
        assert s["actionable_count"] == 3

    def test_resolution_rate(self):
        s = summarize_signal_journal(self._mixed_entries())
        # 3 directional entries: 1 target_hit + 1 invalidated + 1 pending
        # → resolved/total = 2/3
        assert abs(s["resolution_rate"] - 2 / 3) < 0.001

    def test_summary_zero_filled_for_known_keys(self):
        s = summarize_signal_journal([])
        # Every direction / level / outcome bucket present, all zero.
        assert s["total_entries"] == 0
        for k in VALID_DIRECTIONS:
            assert s["by_direction"][k] == 0
        for k in VALID_SIGNAL_LEVELS:
            assert s["by_signal_level"][k] == 0
        for k in VALID_OUTCOME_STATUSES:
            assert s["by_outcome_status"][k] == 0
        assert s["actionable_count"] == 0
        assert s["resolution_rate"]  == 0.0

    def test_summary_handles_garbage_entries(self):
        s = summarize_signal_journal([None, "x", {}, 5])  # type: ignore[list-item]
        assert s["total_entries"] == 0


# ── Deterministic output shape ──────────────────────────────────────────────

class TestDeterministicOutputShape:

    def test_bulk_output_sorted(self):
        signals = [
            _signal(signal_id="z", symbol="ETHUSDT", direction="short",
                    entry_zone_low=3500, entry_zone_high=3510),
            _signal(signal_id="b", symbol="BTCUSDT", direction="long"),
            _signal(signal_id="a", symbol="BTCUSDT", direction="short",
                    entry_zone_low=67500, entry_zone_high=67510),
        ]
        out = create_signal_journal_entries(signals, created_at=_CREATED_AT)
        keys = [(e["symbol"], e["timeframe"], e["direction"], e["entry_zone_mid"])
                for e in out]
        assert keys == sorted(keys)

    def test_same_inputs_identical_outputs(self):
        signals = [
            _signal(signal_id="a"),
            _signal(signal_id="b", direction="short",
                    entry_zone_low=67500, entry_zone_high=67510),
        ]
        a = create_signal_journal_entries(signals, created_at=_CREATED_AT)
        b = create_signal_journal_entries(signals, created_at=_CREATED_AT)
        assert a == b

    def test_summary_dict_keys_sorted(self):
        # by_direction etc. should be sorted alphabetically so callers can
        # rely on iteration order.
        s = summarize_signal_journal([])
        for k in ("by_direction", "by_signal_level", "by_outcome_status"):
            keys = list(s[k].keys())
            assert keys == sorted(keys)
