"""
tests/test_real_heatmap_export_script.py
-----------------------------------------
Tests for scripts/export_real_heatmap_payload.py.

No real network access: fetch_depth_snapshot is always mocked, so Binance is
never contacted. Verifies the script wires the heatmap pipeline together,
stamps real-source metadata, writes JSON, creates the output directory, and
handles errors with a non-zero exit code.
"""

import json
from unittest.mock import patch

import pytest

from scripts import export_real_heatmap_payload as exporter
from services.connectors.binance_depth_collector import DepthCollectorError


# ── Mock snapshot ─────────────────────────────────────────────────────────────

def _lvl(price: float, qty: float) -> dict:
    return {"price": price, "quantity": qty, "usd": round(price * qty, 2)}


def _mock_snapshot(symbol: str = "BTCUSDT") -> dict:
    """A small but realistic normalised depth snapshot with one wall per side."""
    return {
        "symbol": symbol,
        "last_update_id": 123456789,
        "captured_at": "2026-06-01T12:00:00+00:00",
        "bids": [
            _lvl(67490.0, 0.5),
            _lvl(67480.0, 0.8),
            _lvl(67420.0, 25.0),   # ~1.68M USD — bid wall
            _lvl(67410.0, 0.4),
        ],
        "asks": [
            _lvl(67500.0, 0.5),
            _lvl(67510.0, 0.8),
            _lvl(67560.0, 22.0),   # ~1.48M USD — ask wall
            _lvl(67570.0, 0.4),
        ],
    }


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestRealHeatmapExportScript:

    def test_creates_json_file_with_mock_snapshot(self, tmp_path):
        out = tmp_path / "heatmap.json"
        with patch.object(exporter, "fetch_depth_snapshot",
                          return_value=_mock_snapshot()) as mock_fetch:
            code = exporter.main(["--symbol", "BTCUSDT", "--output", str(out)])

        assert code == 0
        assert out.exists()
        # Valid JSON
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert isinstance(payload, dict)
        # Mock used — no real network
        mock_fetch.assert_called_once()

    def test_payload_contains_symbol(self, tmp_path):
        out = tmp_path / "out.json"
        with patch.object(exporter, "fetch_depth_snapshot",
                          return_value=_mock_snapshot("BTCUSDT")):
            exporter.main(["--symbol", "BTCUSDT", "--output", str(out)])
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["symbol"] == "BTCUSDT"

    def test_payload_contains_cells(self, tmp_path):
        out = tmp_path / "out.json"
        with patch.object(exporter, "fetch_depth_snapshot",
                          return_value=_mock_snapshot()):
            exporter.main(["--output", str(out)])
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert isinstance(payload["cells"], list)
        assert len(payload["cells"]) > 0

    def test_meta_marks_real_source_not_demo(self, tmp_path):
        out = tmp_path / "out.json"
        with patch.object(exporter, "fetch_depth_snapshot",
                          return_value=_mock_snapshot()):
            exporter.main(["--output", str(out)])
        meta = json.loads(out.read_text(encoding="utf-8"))["meta"]
        assert meta["isDemo"] is False
        assert meta["source"] == "binance_spot_rest_snapshot"

    def test_output_directory_is_created(self, tmp_path):
        # Nested path whose parents do not exist yet.
        out = tmp_path / "deep" / "nested" / "data" / "payload.json"
        assert not out.parent.exists()
        with patch.object(exporter, "fetch_depth_snapshot",
                          return_value=_mock_snapshot()):
            code = exporter.main(["--output", str(out)])
        assert code == 0
        assert out.parent.is_dir()
        assert out.exists()

    def test_default_output_path_uses_symbol(self, tmp_path, monkeypatch):
        # Run from an isolated cwd so the default data/ path lands in tmp.
        monkeypatch.chdir(tmp_path)
        with patch.object(exporter, "fetch_depth_snapshot",
                          return_value=_mock_snapshot("ETHUSDT")):
            code = exporter.main(["--symbol", "ETHUSDT"])
        assert code == 0
        expected = tmp_path / "data" / "heatmap_payload_ETHUSDT.json"
        assert expected.exists()

    def test_binance_error_returns_exit_code_1(self, tmp_path, capsys):
        out = tmp_path / "out.json"
        with patch.object(exporter, "fetch_depth_snapshot",
                          side_effect=DepthCollectorError("boom", status_code=500)):
            code = exporter.main(["--output", str(out)])
        assert code == 1
        assert not out.exists()
        err = capsys.readouterr().err
        assert "Binance depth fetch failed" in err

    def test_invalid_price_step_returns_exit_code_1(self, tmp_path, capsys):
        out = tmp_path / "out.json"
        with patch.object(exporter, "fetch_depth_snapshot",
                          return_value=_mock_snapshot()):
            code = exporter.main(["--price-step", "0", "--output", str(out)])
        assert code == 1
        err = capsys.readouterr().err
        assert "invalid argument" in err

    def test_no_network_access_fetch_is_mocked(self, tmp_path):
        # If the script tried a real call it would hit the un-mocked function;
        # here we assert it goes exclusively through the injected mock.
        out = tmp_path / "out.json"
        with patch.object(exporter, "fetch_depth_snapshot",
                          return_value=_mock_snapshot()) as mock_fetch:
            exporter.main(["--symbol", "BTCUSDT", "--limit", "500",
                           "--output", str(out)])
        mock_fetch.assert_called_once_with("BTCUSDT", 500)
