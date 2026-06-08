"""
tests/test_whale_event_journal.py
----------------------------------
LM63E — Tests for the local JSONL whale event journal.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.whale_event_journal import (
    COMPACT_EVENT_FIELDS,
    DEFAULT_READ_LIMIT,
    append_whale_event_journal,
    compact_whale_event_for_journal,
    read_whale_event_journal,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _full_event(**overrides) -> dict:
    """A complete whale event dict, matching detect_whale_events output."""
    base = {
        "whale_event_id": "abc123def456",
        "source_type":    "exchange_trade",
        "symbol":         "BTCUSDT",
        "exchange":       "binance_spot",
        "chain":          "",
        "side":           "buy",
        "amount":         5.0,
        "price":          70_000.0,
        "notional_usd":   350_000.0,
        "severity":       "high",
        "confidence":     0.8,
        "reason":         "exchange_trade of BTCUSDT worth $350,000",
        "event_ts":       "2026-06-08T12:00:00+00:00",
        "wallet":         "agg:42",
        "tx_hash":        "agg:BTCUSDT:42",
        "metadata":       {"agg_trade_id": 42, "source": "binance_aggtrade"},
        # field that must NOT be carried (not in COMPACT_EVENT_FIELDS):
        "stray_debug":    "should_be_dropped",
    }
    base.update(overrides)
    return base


# ── compact_whale_event_for_journal ───────────────────────────────────────────

class TestCompact:
    def test_keeps_known_fields_only(self):
        compact = compact_whale_event_for_journal(_full_event())
        assert compact is not None
        assert set(compact) == set(COMPACT_EVENT_FIELDS)
        # The stray field should be dropped.
        assert "stray_debug" not in compact

    def test_returns_none_for_non_dict(self):
        assert compact_whale_event_for_journal(None) is None
        assert compact_whale_event_for_journal("a string") is None
        assert compact_whale_event_for_journal(42) is None
        assert compact_whale_event_for_journal(["list"]) is None

    def test_missing_fields_are_omitted_not_nulled(self):
        partial = {
            "whale_event_id": "x",
            "symbol":         "BTCUSDT",
            "notional_usd":   1_000_000.0,
        }
        compact = compact_whale_event_for_journal(partial)
        assert compact == partial
        assert "side" not in compact

    def test_compact_includes_metadata_subdict(self):
        compact = compact_whale_event_for_journal(_full_event())
        assert compact is not None
        assert compact["metadata"] == {"agg_trade_id": 42, "source": "binance_aggtrade"}


# ── append_whale_event_journal ────────────────────────────────────────────────

class TestAppend:
    def test_append_creates_parent_directory(self, tmp_path: Path):
        path = tmp_path / "nested" / "deeper" / "whales.jsonl"
        assert not path.parent.exists()
        ok = append_whale_event_journal(path, _full_event())
        assert ok is True
        assert path.exists()

    def test_append_writes_one_line_per_event(self, tmp_path: Path):
        path = tmp_path / "whales.jsonl"
        append_whale_event_journal(path, _full_event(whale_event_id="evt-1"))
        append_whale_event_journal(path, _full_event(whale_event_id="evt-2"))
        append_whale_event_journal(path, _full_event(whale_event_id="evt-3"))
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 3
        for line in lines:
            row = json.loads(line)
            assert isinstance(row, dict)

    def test_append_row_shape(self, tmp_path: Path):
        path = tmp_path / "whales.jsonl"
        meta = {"should_send": True, "filter_reason": "high severity above thresholds"}
        ok = append_whale_event_journal(path, _full_event(), meta=meta)
        assert ok is True

        row = json.loads(path.read_text(encoding="utf-8").strip())
        assert set(row) == {"event", "meta", "written_at"}
        assert row["meta"] == meta
        assert isinstance(row["written_at"], str)
        # Written_at must parse as a UTC ISO timestamp.
        from datetime import datetime
        parsed = datetime.fromisoformat(row["written_at"])
        assert parsed.tzinfo is not None

    def test_event_inside_row_is_compacted(self, tmp_path: Path):
        path = tmp_path / "whales.jsonl"
        append_whale_event_journal(path, _full_event())
        row = json.loads(path.read_text(encoding="utf-8").strip())
        assert "stray_debug" not in row["event"]
        assert set(row["event"]) == set(COMPACT_EVENT_FIELDS)

    def test_falsy_path_is_noop(self, tmp_path: Path):
        assert append_whale_event_journal("", _full_event()) is False
        assert append_whale_event_journal(None, _full_event()) is False

    def test_non_dict_event_is_noop(self, tmp_path: Path):
        path = tmp_path / "whales.jsonl"
        assert append_whale_event_journal(path, None) is False
        assert append_whale_event_journal(path, "not a dict") is False
        assert append_whale_event_journal(path, 42) is False
        # File should not have been created.
        assert not path.exists()

    def test_meta_can_be_none_or_dict(self, tmp_path: Path):
        path = tmp_path / "whales.jsonl"
        append_whale_event_journal(path, _full_event(), meta=None)
        append_whale_event_journal(path, _full_event(), meta={"x": 1})
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        row0 = json.loads(lines[0])
        row1 = json.loads(lines[1])
        assert row0["meta"] is None
        assert row1["meta"] == {"x": 1}

    def test_meta_non_dict_wrapped_safely(self, tmp_path: Path):
        path = tmp_path / "whales.jsonl"
        append_whale_event_journal(path, _full_event(), meta="oops a string")
        row = json.loads(path.read_text(encoding="utf-8").strip())
        # Non-dict, non-None meta values are wrapped in {"value": ...} so the
        # row shape stays uniform for downstream readers.
        assert row["meta"] == {"value": "oops a string"}

    def test_unicode_preserved(self, tmp_path: Path):
        path = tmp_path / "whales.jsonl"
        ev = _full_event(reason="aggressive long · 🐋 entered support")
        append_whale_event_journal(path, ev)
        row = json.loads(path.read_text(encoding="utf-8").strip())
        assert "🐋" in row["event"]["reason"]


# ── read_whale_event_journal ──────────────────────────────────────────────────

class TestRead:
    def test_returns_empty_for_missing_file(self, tmp_path: Path):
        assert read_whale_event_journal(tmp_path / "missing.jsonl") == []

    def test_returns_empty_for_directory(self, tmp_path: Path):
        assert read_whale_event_journal(tmp_path) == []

    def test_returns_empty_for_empty_path(self):
        assert read_whale_event_journal("") == []
        assert read_whale_event_journal(None) == []  # type: ignore[arg-type]

    def test_returns_empty_when_limit_le_zero(self, tmp_path: Path):
        path = tmp_path / "whales.jsonl"
        append_whale_event_journal(path, _full_event(whale_event_id="a"))
        assert read_whale_event_journal(path, limit=0) == []
        assert read_whale_event_journal(path, limit=-5) == []

    def test_newest_first_order(self, tmp_path: Path):
        path = tmp_path / "whales.jsonl"
        append_whale_event_journal(path, _full_event(whale_event_id="old"))
        append_whale_event_journal(path, _full_event(whale_event_id="mid"))
        append_whale_event_journal(path, _full_event(whale_event_id="new"))
        rows = read_whale_event_journal(path)
        ids = [r["event"]["whale_event_id"] for r in rows]
        assert ids == ["new", "mid", "old"]

    def test_limit_caps_result_size(self, tmp_path: Path):
        path = tmp_path / "whales.jsonl"
        for i in range(7):
            append_whale_event_journal(path, _full_event(whale_event_id=f"e{i}"))
        rows = read_whale_event_journal(path, limit=3)
        assert len(rows) == 3
        # Newest 3 → e6, e5, e4.
        ids = [r["event"]["whale_event_id"] for r in rows]
        assert ids == ["e6", "e5", "e4"]

    def test_default_limit_constant_used(self, tmp_path: Path):
        # Smoke check that the public constant matches the documented default.
        assert DEFAULT_READ_LIMIT == 100

    def test_invalid_lines_skipped(self, tmp_path: Path):
        path = tmp_path / "whales.jsonl"
        append_whale_event_journal(path, _full_event(whale_event_id="ok-1"))
        # Inject some garbage lines mid-file.
        with path.open("a", encoding="utf-8") as fh:
            fh.write("not json at all\n")
            fh.write("\n")          # blank line — skipped
            fh.write('"a string"\n')  # valid JSON but not an object — skipped
            fh.write("{broken\n")
        append_whale_event_journal(path, _full_event(whale_event_id="ok-2"))

        rows = read_whale_event_journal(path)
        ids = [r["event"]["whale_event_id"] for r in rows]
        # Only the two valid object rows should come back.
        assert ids == ["ok-2", "ok-1"]

    def test_blank_lines_only_returns_empty(self, tmp_path: Path):
        path = tmp_path / "whales.jsonl"
        path.write_text("\n\n   \n", encoding="utf-8")
        assert read_whale_event_journal(path) == []


# ── Round-trip ────────────────────────────────────────────────────────────────

class TestRoundTrip:
    def test_append_then_read_preserves_meta(self, tmp_path: Path):
        path = tmp_path / "whales.jsonl"
        meta = {
            "should_send":   True,
            "filter_reason": "high severity above thresholds",
            "send_result":   {"ok": True, "status": 204},
        }
        append_whale_event_journal(path, _full_event(), meta=meta)
        rows = read_whale_event_journal(path)
        assert len(rows) == 1
        assert rows[0]["meta"] == meta
        assert rows[0]["event"]["whale_event_id"] == "abc123def456"

    def test_append_many_then_limit_reads(self, tmp_path: Path):
        path = tmp_path / "whales.jsonl"
        for i in range(150):
            append_whale_event_journal(
                path, _full_event(whale_event_id=f"evt-{i:04d}"),
            )
        rows = read_whale_event_journal(path)  # default limit 100
        assert len(rows) == 100
        # First row should be the latest event.
        assert rows[0]["event"]["whale_event_id"] == "evt-0149"
        # Last row in result should be 50 from the top.
        assert rows[-1]["event"]["whale_event_id"] == "evt-0050"


@pytest.mark.parametrize("bad_event", [None, "string", 1, [1, 2], (1, 2)])
def test_append_rejects_bad_event_types(tmp_path: Path, bad_event):
    path = tmp_path / "whales.jsonl"
    assert append_whale_event_journal(path, bad_event) is False
    assert not path.exists()
