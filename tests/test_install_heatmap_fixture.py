"""
tests/test_install_heatmap_fixture.py
--------------------------------------
Tests for scripts/install_heatmap_fixture.py.

Pure local file operations — no network, no API calls, no Supabase. Input
payloads are written to a temp dir and installed into a temp output dir.
"""

import json

import pytest

from scripts import install_heatmap_fixture as installer


# ── Helpers ───────────────────────────────────────────────────────────────────

def _valid_payload(symbol: str = "BTCUSDT", timeframe: str = "5m") -> dict:
    return {
        "symbol": symbol,
        "exchange": "binance_spot",
        "timeframe": timeframe,
        "priceMin": 67000.0,
        "priceMax": 68000.0,
        "priceStep": 10.0,
        "timeBuckets": ["2026-06-01T12:00:00+00:00"],
        "cells": [
            {"p": 0, "t": 0, "bid": 50.0, "ask": 0.0, "total": 50.0},
            {"p": 5, "t": 0, "bid": 0.0, "ask": 80.0, "total": 80.0},
        ],
        "walls": [],
        "summary": {"symbol": symbol},
        "meta": {
            "schemaVersion": "1.0",
            "generatedAt": "2026-06-01T12:00:00+00:00",
            "cellCount": 2,
            "wallCount": 0,
            "isDemo": False,
            "source": "binance_spot_rest_snapshot",
        },
    }


def _write(path, data) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestInstallHeatmapFixture:

    def test_installs_valid_payload(self, tmp_path):
        inp = tmp_path / "in.json"
        outdir = tmp_path / "fixtures" / "heatmap"
        _write(inp, _valid_payload())

        code = installer.main([
            "--input", str(inp),
            "--symbol", "BTCUSDT",
            "--timeframe", "5m",
            "--output-dir", str(outdir),
        ])

        assert code == 0
        out = outdir / "BTCUSDT_5m.json"
        assert out.exists()
        json.loads(out.read_text(encoding="utf-8"))  # valid JSON

    def test_output_filename_convention(self, tmp_path):
        inp = tmp_path / "in.json"
        outdir = tmp_path / "out"
        _write(inp, _valid_payload(symbol="ethusdt", timeframe="1h"))

        installer.main([
            "--input", str(inp),
            "--symbol", "ethusdt",   # lower-case in → upper-case file
            "--timeframe", "1h",
            "--output-dir", str(outdir),
        ])

        assert (outdir / "ETHUSDT_1h.json").exists()

    def test_symbol_and_timeframe_are_overwritten(self, tmp_path):
        inp = tmp_path / "in.json"
        outdir = tmp_path / "out"
        # Input claims BTCUSDT/5m, but we install it as SOLUSDT/15m.
        _write(inp, _valid_payload(symbol="BTCUSDT", timeframe="5m"))

        installer.main([
            "--input", str(inp),
            "--symbol", "SOLUSDT",
            "--timeframe", "15m",
            "--output-dir", str(outdir),
        ])

        payload = json.loads((outdir / "SOLUSDT_15m.json").read_text(encoding="utf-8"))
        assert payload["symbol"] == "SOLUSDT"
        assert payload["timeframe"] == "15m"

    def test_meta_fields_are_set(self, tmp_path):
        inp = tmp_path / "in.json"
        outdir = tmp_path / "out"
        _write(inp, _valid_payload())

        installer.main([
            "--input", str(inp),
            "--symbol", "BTCUSDT",
            "--timeframe", "5m",
            "--output-dir", str(outdir),
        ])

        meta = json.loads((outdir / "BTCUSDT_5m.json").read_text(encoding="utf-8"))["meta"]
        assert meta["source"] == "fixture"
        assert meta["dataSource"] == "fixture"
        assert "installedAt" in meta and meta["installedAt"]

    def test_output_directory_is_created(self, tmp_path):
        inp = tmp_path / "in.json"
        outdir = tmp_path / "deep" / "nested" / "heatmap"
        _write(inp, _valid_payload())
        assert not outdir.exists()

        code = installer.main([
            "--input", str(inp),
            "--symbol", "BTCUSDT",
            "--timeframe", "5m",
            "--output-dir", str(outdir),
        ])

        assert code == 0
        assert outdir.is_dir()

    def test_invalid_timeframe_fails(self, tmp_path):
        inp = tmp_path / "in.json"
        _write(inp, _valid_payload())
        # argparse rejects values outside the choices list → SystemExit(2).
        with pytest.raises(SystemExit) as exc:
            installer.main([
                "--input", str(inp),
                "--symbol", "BTCUSDT",
                "--timeframe", "3m",
                "--output-dir", str(tmp_path / "out"),
            ])
        assert exc.value.code != 0

    def test_missing_input_fails(self, tmp_path, capsys):
        code = installer.main([
            "--input", str(tmp_path / "does_not_exist.json"),
            "--symbol", "BTCUSDT",
            "--timeframe", "5m",
            "--output-dir", str(tmp_path / "out"),
        ])
        assert code == 1
        assert "input file not found" in capsys.readouterr().err

    def test_invalid_json_fails(self, tmp_path, capsys):
        inp = tmp_path / "bad.json"
        inp.write_text("{ not valid json", encoding="utf-8")
        code = installer.main([
            "--input", str(inp),
            "--symbol", "BTCUSDT",
            "--timeframe", "5m",
            "--output-dir", str(tmp_path / "out"),
        ])
        assert code == 1
        assert "invalid JSON" in capsys.readouterr().err

    def test_invalid_payload_fails(self, tmp_path, capsys):
        inp = tmp_path / "in.json"
        # Missing 'cells' / 'meta' etc.
        _write(inp, {"symbol": "BTCUSDT"})
        code = installer.main([
            "--input", str(inp),
            "--symbol", "BTCUSDT",
            "--timeframe", "5m",
            "--output-dir", str(tmp_path / "out"),
        ])
        assert code == 1
        err = capsys.readouterr().err
        assert "error:" in err
