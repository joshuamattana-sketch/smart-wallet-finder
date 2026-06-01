"""
tests/test_real_heatmap_history_export.py
------------------------------------------
Tests for scripts/export_real_heatmap_history.py.

No real network access and no real waiting: fetch_depth_snapshot and
time.sleep are always mocked. Verifies multi-sample collection, history
metadata stamping, JSON output, and error handling.
"""

import json
from unittest.mock import patch

import pytest

from scripts import export_real_heatmap_history as exporter
from services.connectors.binance_depth_collector import DepthCollectorError


# ── Mock snapshot ─────────────────────────────────────────────────────────────

def _lvl(price: float, qty: float) -> dict:
    return {"price": price, "quantity": qty, "usd": round(price * qty, 2)}


def _mock_snapshot(symbol: str = "BTCUSDT") -> dict:
    """Fresh snapshot per call (script overwrites captured_at per sample)."""
    return {
        "symbol": symbol,
        "last_update_id": 1,
        "captured_at": "2026-06-01T12:00:00+00:00",
        "bids": [
            _lvl(67490.0, 0.5),
            _lvl(67420.0, 25.0),   # bid wall
            _lvl(67410.0, 0.4),
        ],
        "asks": [
            _lvl(67500.0, 0.5),
            _lvl(67560.0, 22.0),   # ask wall
            _lvl(67570.0, 0.4),
        ],
    }


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestRealHeatmapHistoryExport:

    def test_creates_json_from_multiple_samples(self, tmp_path):
        out = tmp_path / "history.json"
        with patch.object(exporter, "fetch_depth_snapshot",
                          side_effect=lambda *a, **k: _mock_snapshot()) as mock_fetch, \
             patch.object(exporter.time, "sleep") as mock_sleep:
            code = exporter.main([
                "--symbol", "BTCUSDT", "--samples", "3", "--interval", "0",
                "--output", str(out),
            ])

        assert code == 0
        assert out.exists()
        json.loads(out.read_text(encoding="utf-8"))  # valid JSON
        assert mock_fetch.call_count == 3
        # interval 0 → no sleeps
        mock_sleep.assert_not_called()

    def test_payload_contains_symbol(self, tmp_path):
        out = tmp_path / "h.json"
        with patch.object(exporter, "fetch_depth_snapshot",
                          side_effect=lambda *a, **k: _mock_snapshot()), \
             patch.object(exporter.time, "sleep"):
            exporter.main(["--symbol", "BTCUSDT", "--samples", "3",
                           "--interval", "0", "--output", str(out)])
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["symbol"] == "BTCUSDT"

    def test_time_buckets_length_equals_samples(self, tmp_path):
        out = tmp_path / "h.json"
        with patch.object(exporter, "fetch_depth_snapshot",
                          side_effect=lambda *a, **k: _mock_snapshot()), \
             patch.object(exporter.time, "sleep"):
            exporter.main(["--samples", "5", "--interval", "0", "--output", str(out)])
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert len(payload["timeBuckets"]) == 5

    def test_cells_not_empty(self, tmp_path):
        out = tmp_path / "h.json"
        with patch.object(exporter, "fetch_depth_snapshot",
                          side_effect=lambda *a, **k: _mock_snapshot()), \
             patch.object(exporter.time, "sleep"):
            exporter.main(["--samples", "3", "--interval", "0", "--output", str(out)])
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert isinstance(payload["cells"], list)
        assert len(payload["cells"]) > 0

    def test_meta_is_not_demo(self, tmp_path):
        out = tmp_path / "h.json"
        with patch.object(exporter, "fetch_depth_snapshot",
                          side_effect=lambda *a, **k: _mock_snapshot()), \
             patch.object(exporter.time, "sleep"):
            exporter.main(["--samples", "3", "--interval", "0", "--output", str(out)])
        meta = json.loads(out.read_text(encoding="utf-8"))["meta"]
        assert meta["isDemo"] is False

    def test_meta_source_and_datasource(self, tmp_path):
        out = tmp_path / "h.json"
        with patch.object(exporter, "fetch_depth_snapshot",
                          side_effect=lambda *a, **k: _mock_snapshot()), \
             patch.object(exporter.time, "sleep"):
            exporter.main(["--samples", "3", "--interval", "0", "--output", str(out)])
        meta = json.loads(out.read_text(encoding="utf-8"))["meta"]
        assert meta["source"] == "binance_spot_rest_history"
        assert meta["dataSource"] == "binance_spot_rest_history"

    def test_meta_sample_count_and_interval(self, tmp_path):
        out = tmp_path / "h.json"
        with patch.object(exporter, "fetch_depth_snapshot",
                          side_effect=lambda *a, **k: _mock_snapshot()), \
             patch.object(exporter.time, "sleep") as mock_sleep:
            exporter.main(["--samples", "4", "--interval", "5", "--output", str(out)])
        meta = json.loads(out.read_text(encoding="utf-8"))["meta"]
        assert meta["sampleCount"] == 4
        assert meta["intervalSeconds"] == 5
        # sleeps between samples only (samples - 1), and never really waited
        assert mock_sleep.call_count == 3

    def test_invalid_samples_fails(self, tmp_path, capsys):
        out = tmp_path / "h.json"
        with patch.object(exporter, "fetch_depth_snapshot",
                          side_effect=lambda *a, **k: _mock_snapshot()), \
             patch.object(exporter.time, "sleep"):
            code = exporter.main(["--samples", "0", "--interval", "0",
                                  "--output", str(out)])
        assert code == 1
        assert "invalid argument" in capsys.readouterr().err
        assert not out.exists()

    def test_invalid_interval_fails(self, tmp_path, capsys):
        out = tmp_path / "h.json"
        with patch.object(exporter, "fetch_depth_snapshot",
                          side_effect=lambda *a, **k: _mock_snapshot()), \
             patch.object(exporter.time, "sleep"):
            code = exporter.main(["--samples", "3", "--interval", "-1",
                                  "--output", str(out)])
        assert code == 1
        assert "invalid argument" in capsys.readouterr().err

    def test_binance_error_returns_exit_code_1(self, tmp_path, capsys):
        out = tmp_path / "h.json"
        with patch.object(exporter, "fetch_depth_snapshot",
                          side_effect=DepthCollectorError("boom", status_code=500)), \
             patch.object(exporter.time, "sleep"):
            code = exporter.main(["--samples", "3", "--interval", "0",
                                  "--output", str(out)])
        assert code == 1
        assert "Binance depth fetch failed" in capsys.readouterr().err

    def test_no_network_access_uses_mock_only(self, tmp_path):
        out = tmp_path / "h.json"
        with patch.object(exporter, "fetch_depth_snapshot",
                          side_effect=lambda *a, **k: _mock_snapshot()) as mock_fetch, \
             patch.object(exporter.time, "sleep"):
            exporter.main(["--symbol", "BTCUSDT", "--limit", "500",
                           "--samples", "2", "--interval", "0", "--output", str(out)])
        assert mock_fetch.call_count == 2
        for call in mock_fetch.call_args_list:
            assert call.args == ("BTCUSDT", 500)

    # ── price path ──────────────────────────────────────────────────────────

    def test_price_path_present_and_matches_buckets(self, tmp_path):
        out = tmp_path / "h.json"
        with patch.object(exporter, "fetch_depth_snapshot",
                          side_effect=lambda *a, **k: _mock_snapshot()), \
             patch.object(exporter.time, "sleep"):
            exporter.main(["--samples", "4", "--interval", "0", "--output", str(out)])
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert isinstance(payload["pricePath"], list)
        assert len(payload["pricePath"]) == len(payload["timeBuckets"]) == 4

    def test_mid_price_computed(self, tmp_path):
        out = tmp_path / "h.json"
        with patch.object(exporter, "fetch_depth_snapshot",
                          side_effect=lambda *a, **k: _mock_snapshot()), \
             patch.object(exporter.time, "sleep"):
            exporter.main(["--samples", "2", "--interval", "0", "--output", str(out)])
        pt = json.loads(out.read_text(encoding="utf-8"))["pricePath"][-1]
        assert pt["bestBid"] == 67490.0
        assert pt["bestAsk"] == 67500.0
        assert pt["price"] == 67495.0

    def test_payload_without_price_path_stays_valid(self):
        # build_heatmap_api_payload without price_path must omit the key and
        # still validate — older consumers keep working.
        from services.orderbook_depth_bucketer import build_heatmap_cells
        from services.heatmap_matrix_builder import build_heatmap_matrix
        from services.heatmap_api_payload import (
            build_heatmap_api_payload,
            validate_heatmap_api_payload,
        )

        snap = dict(_mock_snapshot())
        snap["captured_at"] = "2026-06-01T12:00:00+00:00"
        frame = build_heatmap_cells(snap, price_step=10.0, wall_threshold_usd=500_000.0)
        matrix = build_heatmap_matrix([frame])
        payload = build_heatmap_api_payload(matrix, timeframe="5m")

        assert "pricePath" not in payload
        assert validate_heatmap_api_payload(payload) is True
