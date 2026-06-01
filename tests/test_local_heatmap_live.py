"""
tests/test_local_heatmap_live.py
---------------------------------
Tests for scripts/run_local_heatmap_live.py.

No real network and no real waiting: fetch_depth_snapshot and time.sleep are
always mocked. Verifies the rolling fixture writer, live metadata, frame
capping, and error handling.
"""

import json
from unittest.mock import patch

import pytest

from scripts import run_local_heatmap_live as live
from services.connectors.binance_depth_collector import DepthCollectorError


# ── Mock snapshot ─────────────────────────────────────────────────────────────

def _lvl(price: float, qty: float) -> dict:
    return {"price": price, "quantity": qty, "usd": round(price * qty, 2)}


def _mock_snapshot(symbol: str = "BTCUSDT") -> dict:
    return {
        "symbol": symbol,
        "last_update_id": 1,
        "captured_at": "2026-06-01T12:00:00+00:00",
        "bids": [_lvl(67490.0, 0.5), _lvl(67420.0, 25.0), _lvl(67410.0, 0.4)],
        "asks": [_lvl(67500.0, 0.5), _lvl(67560.0, 22.0), _lvl(67570.0, 0.4)],
    }


def _run(tmp_path, args):
    out = tmp_path / "fixtures" / "BTCUSDT_5m.json"
    full = ["--output", str(out)] + args
    with patch.object(live, "fetch_depth_snapshot",
                      side_effect=lambda *a, **k: _mock_snapshot()) as mock_fetch, \
         patch.object(live.time, "sleep") as mock_sleep:
        code = live.main(full)
    return code, out, mock_fetch, mock_sleep


def _payload(out):
    return json.loads(out.read_text(encoding="utf-8"))


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestLocalHeatmapLive:

    def test_output_json_is_created(self, tmp_path):
        code, out, fetch, _ = _run(tmp_path, ["--samples", "3", "--interval", "2"])
        assert code == 0
        assert out.exists()
        _payload(out)  # valid JSON
        assert fetch.call_count == 3

    def test_multiple_frames_processed(self, tmp_path):
        _, out, _, _ = _run(tmp_path, ["--samples", "3", "--interval", "2",
                                       "--max-frames", "60"])
        payload = _payload(out)
        assert len(payload["timeBuckets"]) == 3
        assert len(payload["cells"]) > 0

    def test_meta_source_and_datasource(self, tmp_path):
        _, out, _, _ = _run(tmp_path, ["--samples", "2", "--interval", "2"])
        meta = _payload(out)["meta"]
        assert meta["source"] == "local_live_fixture"
        assert meta["dataSource"] == "local_live_fixture"

    def test_meta_live_updated_at_set(self, tmp_path):
        _, out, _, _ = _run(tmp_path, ["--samples", "2", "--interval", "2"])
        meta = _payload(out)["meta"]
        assert meta.get("liveUpdatedAt")

    def test_meta_sample_count_set(self, tmp_path):
        _, out, _, _ = _run(tmp_path, ["--samples", "3", "--interval", "2"])
        meta = _payload(out)["meta"]
        assert meta["sampleCount"] == 3

    def test_max_frames_caps_frames(self, tmp_path):
        _, out, _, _ = _run(tmp_path, ["--samples", "5", "--interval", "2",
                                       "--max-frames", "2"])
        payload = _payload(out)
        assert payload["meta"]["maxFrames"] == 2
        # rolling window → only the last 2 frames survive
        assert len(payload["timeBuckets"]) == 2

    def test_sleep_called_between_ticks_only(self, tmp_path):
        _, _, _, sleep = _run(tmp_path, ["--samples", "4", "--interval", "2"])
        assert sleep.call_count == 3  # samples - 1

    def test_invalid_samples_fails(self, tmp_path, capsys):
        code, out, _, _ = _run(tmp_path, ["--samples", "0", "--interval", "2"])
        assert code == 1
        assert "invalid argument" in capsys.readouterr().err
        assert not out.exists()

    def test_invalid_interval_fails(self, tmp_path, capsys):
        code, _, _, _ = _run(tmp_path, ["--samples", "3", "--interval", "0"])
        assert code == 1
        assert "invalid argument" in capsys.readouterr().err

    def test_invalid_max_frames_fails(self, tmp_path, capsys):
        code, _, _, _ = _run(tmp_path, ["--samples", "3", "--interval", "2",
                                        "--max-frames", "0"])
        assert code == 1
        assert "invalid argument" in capsys.readouterr().err

    def test_continues_after_transient_fetch_error(self, tmp_path):
        out = tmp_path / "f" / "BTCUSDT_5m.json"
        # First call fails, next two succeed.
        seq = [DepthCollectorError("boom"),
               _mock_snapshot(), _mock_snapshot()]

        def _side(*_a, **_k):
            item = seq.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        with patch.object(live, "fetch_depth_snapshot", side_effect=_side), \
             patch.object(live.time, "sleep"):
            code = live.main(["--samples", "3", "--interval", "2",
                              "--output", str(out)])
        assert code == 0
        assert out.exists()
        assert _payload(out)["meta"]["sampleCount"] == 2

    def test_all_failures_exit_1(self, tmp_path, capsys):
        out = tmp_path / "f" / "BTCUSDT_5m.json"
        with patch.object(live, "fetch_depth_snapshot",
                          side_effect=DepthCollectorError("boom")), \
             patch.object(live.time, "sleep"):
            code = live.main(["--samples", "3", "--interval", "2",
                              "--output", str(out)])
        assert code == 1
        assert "no snapshots were collected" in capsys.readouterr().err
        assert not out.exists()

    def test_no_network_uses_mock_only(self, tmp_path):
        _, _, fetch, _ = _run(tmp_path, ["--symbol", "BTCUSDT", "--limit", "500",
                                         "--samples", "2", "--interval", "2"])
        assert fetch.call_count == 2
        for call in fetch.call_args_list:
            assert call.args == ("BTCUSDT", 500)

    # ── price path ──────────────────────────────────────────────────────────

    def test_output_contains_price_path(self, tmp_path):
        _, out, _, _ = _run(tmp_path, ["--samples", "3", "--interval", "2"])
        payload = _payload(out)
        assert isinstance(payload["pricePath"], list)
        assert len(payload["pricePath"]) > 0
        pt = payload["pricePath"][0]
        assert {"t", "price", "bestBid", "bestAsk"} <= set(pt.keys())

    def test_price_path_length_matches_time_buckets(self, tmp_path):
        _, out, _, _ = _run(tmp_path, ["--samples", "4", "--interval", "2"])
        payload = _payload(out)
        assert len(payload["pricePath"]) == len(payload["timeBuckets"])

    def test_price_path_capped_by_max_frames(self, tmp_path):
        _, out, _, _ = _run(tmp_path, ["--samples", "5", "--interval", "2",
                                       "--max-frames", "2"])
        payload = _payload(out)
        assert len(payload["pricePath"]) == 2
        assert len(payload["pricePath"]) == len(payload["timeBuckets"])

    def test_mid_price_computed_from_best_bid_ask(self, tmp_path):
        # mock best bid = 67490, best ask = 67500 → mid = 67495.0
        _, out, _, _ = _run(tmp_path, ["--samples", "2", "--interval", "2"])
        payload = _payload(out)
        pt = payload["pricePath"][-1]
        assert pt["bestBid"] == 67490.0
        assert pt["bestAsk"] == 67500.0
        assert pt["price"] == 67495.0
        assert payload["meta"]["currentPrice"] == 67495.0
        assert payload["summary"]["currentPrice"] == 67495.0
