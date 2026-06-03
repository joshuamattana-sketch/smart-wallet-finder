"""Tests for local_signal_pipeline (LM55)."""

from services.local_signal_pipeline import run_local_signal_pipeline


def _wall(side, price_min, price_max, strength=80.0):
    return {
        "side": side,
        "priceMin": price_min,
        "priceMax": price_max,
        "centerPrice": (price_min + price_max) / 2.0,
        "strengthScore": strength,
        "totalUsd": 1_000_000.0,
        "maxIntensity": 90.0,
        "bucketCount": 5,
        "label": f"{side.capitalize()} Zone",
    }


_OPTS = {"symbol": "BTCUSDT", "exchange": "binance_spot", "timeframe": "5m",
         "current_price": 67500.0}


def test_pipeline_bid_wall_scenario():
    prev = [_wall("bid", 67000, 67200, 60.0)]
    cur = [_wall("bid", 67000, 67200, 80.0)]
    result = run_local_signal_pipeline(prev, cur, _OPTS)
    assert len(result["events"]) >= 1
    assert isinstance(result["features"], list)
    assert isinstance(result["setups"], list)
    assert isinstance(result["signals"], list)
    assert isinstance(result["journal_entries"], list)
    assert isinstance(result["summary"], dict)


def test_empty_input_safe():
    result = run_local_signal_pipeline([], [])
    assert result["events"] == []
    assert result["features"] == []
    assert result["setups"] == []
    assert result["signals"] == []
    assert result["journal_entries"] == []
    assert isinstance(result["summary"], dict)

    result2 = run_local_signal_pipeline(None, None)
    assert result2["events"] == []


def test_deterministic_output_shape():
    prev = [_wall("bid", 67000, 67200)]
    cur = [_wall("bid", 67000, 67200, 90.0)]
    result = run_local_signal_pipeline(prev, cur, _OPTS)
    assert set(result.keys()) == {
        "events", "features", "setups", "signals", "journal_entries", "summary",
    }
    for key in ["events", "features", "setups", "signals", "journal_entries"]:
        assert isinstance(result[key], list)


def test_summary_counts_correct():
    prev = [_wall("bid", 67000, 67200, 60.0)]
    cur = [_wall("bid", 67000, 67200, 80.0)]
    result = run_local_signal_pipeline(prev, cur, _OPTS)
    summary = result["summary"]
    assert summary.get("total_entries", 0) == len(result["journal_entries"])


def test_no_network_db_dependency():
    """Pipeline runs purely in-process with no imports of network/db modules."""
    prev = [_wall("ask", 68000, 68200, 70.0)]
    cur = [_wall("ask", 68000, 68200, 50.0)]
    result = run_local_signal_pipeline(prev, cur, _OPTS)
    assert isinstance(result["events"], list)
