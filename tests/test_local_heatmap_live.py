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


def _run_multi(tmp_path, args, side_effect=None):
    """Run main() in multi mode against a temp --output-dir."""
    outdir = tmp_path / "fix"
    full = ["--output-dir", str(outdir)] + args
    se = side_effect or (lambda *a, **k: _mock_snapshot())
    with patch.object(live, "fetch_depth_snapshot", side_effect=se) as mf, \
         patch.object(live.time, "sleep") as ms:
        code = live.main(full)
    return code, outdir, mf, ms


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

    # ── multi-symbol / multi-timeframe ────────────────────────────────────────

    def test_symbols_creates_multiple_files(self, tmp_path):
        code, outdir, fetch, _ = _run_multi(
            tmp_path,
            ["--symbols", "BTCUSDT,ETHUSDT,SOLUSDT", "--samples", "2", "--interval", "2"],
        )
        assert code == 0
        for sym in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
            assert (outdir / f"{sym}_5m.json").exists()
        # one fetch per symbol per tick: 3 symbols × 2 samples
        assert fetch.call_count == 6

    def test_timeframes_creates_multiple_files(self, tmp_path):
        code, outdir, fetch, _ = _run_multi(
            tmp_path,
            ["--symbol", "BTCUSDT", "--timeframes", "5m,15m,1h",
             "--samples", "2", "--interval", "2"],
        )
        assert code == 0
        for tf in ("5m", "15m", "1h"):
            assert (outdir / f"BTCUSDT_{tf}.json").exists()
        # one symbol fetched once per tick (timeframes share frames): 2 fetches
        assert fetch.call_count == 2

    def test_symbols_and_timeframes_matrix(self, tmp_path):
        code, outdir, _, _ = _run_multi(
            tmp_path,
            ["--symbols", "BTCUSDT,ETHUSDT", "--timeframes", "5m,15m",
             "--samples", "1", "--interval", "2"],
        )
        assert code == 0
        for sym in ("BTCUSDT", "ETHUSDT"):
            for tf in ("5m", "15m"):
                assert (outdir / f"{sym}_{tf}.json").exists()

    def test_backward_compat_single_symbol_timeframe(self, tmp_path):
        # The original single-file flow still works and stamps symbol/timeframe.
        _, out, _, _ = _run(tmp_path, ["--symbol", "BTCUSDT", "--timeframe", "5m",
                                       "--samples", "2", "--interval", "2"])
        meta = _payload(out)["meta"]
        assert meta["symbol"] == "BTCUSDT"
        assert meta["timeframe"] == "5m"

    def test_default_price_steps_per_symbol(self, tmp_path):
        _, outdir, _, _ = _run_multi(
            tmp_path,
            ["--symbols", "BTCUSDT,ETHUSDT,SOLUSDT", "--samples", "1", "--interval", "2"],
        )
        assert _payload(outdir / "BTCUSDT_5m.json")["priceStep"] == 10.0
        assert _payload(outdir / "ETHUSDT_5m.json")["priceStep"] == 5.0
        assert _payload(outdir / "SOLUSDT_5m.json")["priceStep"] == 0.5

    def test_global_price_step_override(self, tmp_path):
        _, outdir, _, _ = _run_multi(
            tmp_path,
            ["--symbols", "BTCUSDT,ETHUSDT", "--price-step", "2",
             "--samples", "1", "--interval", "2"],
        )
        assert _payload(outdir / "BTCUSDT_5m.json")["priceStep"] == 2.0
        assert _payload(outdir / "ETHUSDT_5m.json")["priceStep"] == 2.0

    def test_price_steps_map_override(self, tmp_path):
        _, outdir, _, _ = _run_multi(
            tmp_path,
            ["--symbols", "BTCUSDT,ETHUSDT", "--price-steps", "BTCUSDT:7,ETHUSDT:3",
             "--samples", "1", "--interval", "2"],
        )
        assert _payload(outdir / "BTCUSDT_5m.json")["priceStep"] == 7.0
        assert _payload(outdir / "ETHUSDT_5m.json")["priceStep"] == 3.0

    def test_meta_set_per_file_multi(self, tmp_path):
        _, outdir, _, _ = _run_multi(
            tmp_path,
            ["--symbols", "BTCUSDT,ETHUSDT", "--timeframes", "5m,15m",
             "--samples", "1", "--interval", "2"],
        )
        meta = _payload(outdir / "ETHUSDT_15m.json")["meta"]
        assert meta["symbol"] == "ETHUSDT"
        assert meta["timeframe"] == "15m"
        assert meta["source"] == "local_live_fixture"
        assert meta["dataSource"] == "local_live_fixture"
        assert meta.get("liveUpdatedAt")

    def test_one_symbol_failure_does_not_stop_others(self, tmp_path):
        def _side(symbol, *_a, **_k):
            if symbol == "ETHUSDT":
                raise DepthCollectorError("boom")
            return _mock_snapshot()

        code, outdir, _, _ = _run_multi(
            tmp_path,
            ["--symbols", "BTCUSDT,ETHUSDT,SOLUSDT", "--samples", "2", "--interval", "2"],
            side_effect=_side,
        )
        assert code == 0
        assert (outdir / "BTCUSDT_5m.json").exists()
        assert (outdir / "SOLUSDT_5m.json").exists()
        assert not (outdir / "ETHUSDT_5m.json").exists()

    def test_invalid_timeframe_in_list_fails(self, tmp_path, capsys):
        code, outdir, _, _ = _run_multi(
            tmp_path,
            ["--symbols", "BTCUSDT", "--timeframes", "5m,3m",
             "--samples", "1", "--interval", "2"],
        )
        assert code == 1
        assert "invalid argument" in capsys.readouterr().err

    def test_invalid_price_steps_format_fails(self, tmp_path, capsys):
        code, _, _, _ = _run_multi(
            tmp_path,
            ["--symbols", "BTCUSDT", "--price-steps", "BTCUSDT10",
             "--samples", "1", "--interval", "2"],
        )
        assert code == 1
        assert "invalid argument" in capsys.readouterr().err

    def test_multiple_symbols_fetched_in_parallel_per_tick(self, tmp_path):
        # Three symbols, two ticks → six fetches; all files written.
        code, outdir, fetch, _ = _run_multi(
            tmp_path,
            ["--symbols", "BTCUSDT,ETHUSDT,SOLUSDT", "--timeframes", "5m,15m",
             "--samples", "2", "--interval", "2"],
        )
        assert code == 0
        assert fetch.call_count == 6  # symbols × samples (not × timeframes)
        for sym in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
            for tf in ("5m", "15m"):
                assert (outdir / f"{sym}_{tf}.json").exists()

    # ── active market fast mode ───────────────────────────────────────────────

    def test_active_symbol_updates_more_often(self, tmp_path):
        # active 2s, background 10s → bg_every = 5 ticks. 6 ticks (0..5):
        # active every tick (6), background on ticks 0 and 5 (2).
        code, outdir, fetch, _ = _run_multi(
            tmp_path,
            ["--symbols", "BTCUSDT,ETHUSDT,SOLUSDT", "--active-symbol", "BTCUSDT",
             "--active-interval", "2", "--background-interval", "10",
             "--samples", "6", "--interval", "2"],
        )
        assert code == 0
        btc_calls = [c for c in fetch.call_args_list if c.args[0] == "BTCUSDT"]
        eth_calls = [c for c in fetch.call_args_list if c.args[0] == "ETHUSDT"]
        sol_calls = [c for c in fetch.call_args_list if c.args[0] == "SOLUSDT"]
        assert len(btc_calls) == 6
        assert len(eth_calls) == 2
        assert len(sol_calls) == 2
        # Cumulative sampleCount in fixtures reflects the faster active cadence.
        assert _payload(outdir / "BTCUSDT_5m.json")["meta"]["sampleCount"] == 6
        assert _payload(outdir / "ETHUSDT_5m.json")["meta"]["sampleCount"] == 2

    def test_active_mode_meta_fields(self, tmp_path):
        _, outdir, _, _ = _run_multi(
            tmp_path,
            ["--symbols", "BTCUSDT,ETHUSDT", "--active-symbol", "BTCUSDT",
             "--active-interval", "2", "--background-interval", "10",
             "--samples", "1", "--interval", "2"],
        )
        btc = _payload(outdir / "BTCUSDT_5m.json")["meta"]
        eth = _payload(outdir / "ETHUSDT_5m.json")["meta"]
        assert btc["activeSymbol"] == "BTCUSDT"
        assert btc["updateMode"] == "active_fast"
        assert btc["isActiveSymbol"] is True
        assert btc["effectiveIntervalSeconds"] == 2
        assert eth["updateMode"] == "standard"
        assert eth["isActiveSymbol"] is False
        assert eth["effectiveIntervalSeconds"] == 10
        assert eth["activeSymbol"] == "BTCUSDT"

    def test_active_symbol_not_in_symbols_fails(self, tmp_path, capsys):
        code, _, _, _ = _run_multi(
            tmp_path,
            ["--symbols", "ETHUSDT,SOLUSDT", "--active-symbol", "BTCUSDT",
             "--samples", "1", "--interval", "2"],
        )
        assert code == 1
        assert "invalid argument" in capsys.readouterr().err

    def test_invalid_active_interval_fails(self, tmp_path, capsys):
        code, _, _, _ = _run_multi(
            tmp_path,
            ["--symbols", "BTCUSDT", "--active-symbol", "BTCUSDT",
             "--active-interval", "0", "--samples", "1", "--interval", "2"],
        )
        assert code == 1
        assert "invalid argument" in capsys.readouterr().err

    def test_invalid_background_interval_fails(self, tmp_path, capsys):
        code, _, _, _ = _run_multi(
            tmp_path,
            ["--symbols", "BTCUSDT,ETHUSDT", "--active-symbol", "BTCUSDT",
             "--background-interval", "0", "--samples", "1", "--interval", "2"],
        )
        assert code == 1
        assert "invalid argument" in capsys.readouterr().err

    def test_standard_mode_meta_without_active(self, tmp_path):
        # Backward compatible: no --active-symbol → standard mode metadata.
        _, out, _, _ = _run(tmp_path, ["--samples", "1", "--interval", "2"])
        meta = _payload(out)["meta"]
        assert meta["activeSymbol"] is None
        assert meta["updateMode"] == "standard"
        assert meta["isActiveSymbol"] is False

    def test_tick_longer_than_interval_skips_extra_sleep(self, tmp_path):
        # Force each tick to appear to take longer than the interval; the writer
        # should then not sleep at all between ticks.
        out = tmp_path / "fix" / "BTCUSDT_5m.json"
        # monotonic is called twice per tick (start, end); make end-start = 5s.
        times = iter([0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0])
        with patch.object(live, "fetch_depth_snapshot",
                          side_effect=lambda *a, **k: _mock_snapshot()), \
             patch.object(live.time, "sleep") as mock_sleep, \
             patch.object(live.time, "monotonic", side_effect=lambda: next(times)):
            code = live.main(["--symbols", "BTCUSDT", "--samples", "3",
                              "--interval", "2", "--output-dir", str(out.parent)])
        assert code == 0
        mock_sleep.assert_not_called()

    # ── write targets (fixture / live / both) ─────────────────────────────────

    def _run_targets(self, tmp_path, args, side_effect=None):
        """Run main() with separate fixture (--output-dir) and live (--live-dir) dirs."""
        fix_dir = tmp_path / "fix"
        live_dir = tmp_path / "live"
        full = ["--output-dir", str(fix_dir), "--live-dir", str(live_dir)] + args
        se = side_effect or (lambda *a, **k: _mock_snapshot())
        with patch.object(live, "fetch_depth_snapshot", side_effect=se), \
             patch.object(live.time, "sleep"):
            code = live.main(full)
        return code, fix_dir, live_dir

    def test_target_fixture_writes_heatmap_file(self, tmp_path):
        code, fix_dir, live_dir = self._run_targets(
            tmp_path, ["--symbols", "BTCUSDT", "--target", "fixture",
                       "--samples", "1", "--interval", "2"],
        )
        assert code == 0
        assert (fix_dir / "BTCUSDT_5m.json").exists()
        assert not (live_dir / "BTCUSDT_5m.json").exists()

    def test_target_live_writes_live_file(self, tmp_path):
        code, fix_dir, live_dir = self._run_targets(
            tmp_path, ["--symbols", "BTCUSDT", "--target", "live",
                       "--samples", "1", "--interval", "2"],
        )
        assert code == 0
        assert (live_dir / "BTCUSDT_5m.json").exists()
        assert not (fix_dir / "BTCUSDT_5m.json").exists()
        meta = _payload(live_dir / "BTCUSDT_5m.json")["meta"]
        assert meta["source"] == "local_live_writer"
        assert meta["dataSource"] == "local_live_writer"
        assert meta["resolvedSource"] == "live"
        assert meta["writerTarget"] == "live"
        assert meta["isDemo"] is False
        assert meta["stale"] is False
        assert meta.get("liveUpdatedAt")

    def test_target_both_writes_both_files(self, tmp_path):
        code, fix_dir, live_dir = self._run_targets(
            tmp_path, ["--symbols", "BTCUSDT", "--target", "both",
                       "--samples", "1", "--interval", "2"],
        )
        assert code == 0
        assert (fix_dir / "BTCUSDT_5m.json").exists()
        assert (live_dir / "BTCUSDT_5m.json").exists()
        # Live file → live-writer meta; fixture file → existing local_live_fixture meta.
        assert _payload(live_dir / "BTCUSDT_5m.json")["meta"]["source"] == "local_live_writer"
        assert _payload(live_dir / "BTCUSDT_5m.json")["meta"]["writerTarget"] == "both"
        assert _payload(fix_dir / "BTCUSDT_5m.json")["meta"]["source"] == "local_live_fixture"

    def test_default_target_is_fixture(self, tmp_path):
        code, fix_dir, live_dir = self._run_targets(
            tmp_path, ["--symbols", "BTCUSDT", "--samples", "1", "--interval", "2"],
        )
        assert code == 0
        assert (fix_dir / "BTCUSDT_5m.json").exists()
        assert not (live_dir / "BTCUSDT_5m.json").exists()
        # No writerTarget on the default fixture write.
        assert "writerTarget" not in _payload(fix_dir / "BTCUSDT_5m.json")["meta"]

    def test_invalid_target_fails(self, tmp_path):
        # argparse rejects values outside choices → SystemExit(non-zero).
        with patch.object(live, "fetch_depth_snapshot",
                          side_effect=lambda *a, **k: _mock_snapshot()), \
             patch.object(live.time, "sleep"):
            with pytest.raises(SystemExit) as exc:
                live.main(["--symbols", "BTCUSDT", "--target", "bogus",
                           "--samples", "1", "--interval", "2",
                           "--output-dir", str(tmp_path / "fix")])
        assert exc.value.code != 0

    def test_active_fast_mode_with_both_targets(self, tmp_path):
        # Active fast mode stays compatible while writing to both targets.
        code, fix_dir, live_dir = self._run_targets(
            tmp_path,
            ["--symbols", "BTCUSDT,ETHUSDT,SOLUSDT", "--active-symbol", "BTCUSDT",
             "--active-interval", "2", "--background-interval", "10",
             "--target", "both", "--samples", "6", "--interval", "2"],
        )
        assert code == 0
        # Active symbol updated every tick (6); background symbols on ticks 0,5 (2).
        assert _payload(fix_dir / "BTCUSDT_5m.json")["meta"]["sampleCount"] == 6
        assert _payload(live_dir / "BTCUSDT_5m.json")["meta"]["sampleCount"] == 6
        assert _payload(fix_dir / "ETHUSDT_5m.json")["meta"]["sampleCount"] == 2
        assert _payload(live_dir / "ETHUSDT_5m.json")["meta"]["sampleCount"] == 2
        # Live files carry live-writer meta; active flag preserved.
        btc_live = _payload(live_dir / "BTCUSDT_5m.json")["meta"]
        assert btc_live["source"] == "local_live_writer"
        assert btc_live["isActiveSymbol"] is True

    # ── supabase targets ─────────────────────────────────────────────────────

    def test_supabase_upsert_url_format(self):
        cfg = live.SupabaseConfig("https://example.supabase.co", "key")
        assert cfg.upsert_endpoint == (
            "https://example.supabase.co/rest/v1/heatmap_latest_payloads"
            "?on_conflict=symbol,exchange,timeframe"
        )

    def test_supabase_upsert_url_strips_trailing_slash(self):
        cfg = live.SupabaseConfig("https://example.supabase.co/", "key")
        assert cfg.upsert_endpoint.startswith("https://example.supabase.co/rest/v1/")
        assert "//" not in cfg.upsert_endpoint.split("://", 1)[1]

    def test_supabase_upsert_url_no_double_rest(self):
        cfg = live.SupabaseConfig("https://example.supabase.co/rest/v1", "key")
        assert cfg.upsert_endpoint == (
            "https://example.supabase.co/rest/v1/heatmap_latest_payloads"
            "?on_conflict=symbol,exchange,timeframe"
        )

    def test_target_supabase_requires_env(self, tmp_path, capsys, monkeypatch):
        # Strip any developer-shell env so the test reflects a missing-env CI
        # box rather than the developer's local Supabase credentials.
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
        code, _, _ = self._run_targets(
            tmp_path, ["--symbols", "BTCUSDT", "--target", "supabase",
                       "--samples", "1", "--interval", "2"],
        )
        assert code == 1
        assert "SUPABASE" in capsys.readouterr().err

    def test_target_supabase_builds_correct_row(self, tmp_path):
        captured_rows: list[dict] = []

        def _fake_upsert(cfg, symbol, timeframe, payload, *, exchange="binance_spot"):
            captured_rows.append({
                "symbol": symbol, "timeframe": timeframe,
                "exchange": exchange, "payload": payload,
            })

        fix_dir = tmp_path / "fix"
        live_dir = tmp_path / "live"
        with patch.object(live, "fetch_depth_snapshot",
                          side_effect=lambda *a, **k: _mock_snapshot()), \
             patch.object(live.time, "sleep"), \
             patch.object(live, "upsert_supabase_payload", side_effect=_fake_upsert), \
             patch.dict("os.environ", {"SUPABASE_URL": "https://x.supabase.co",
                                       "SUPABASE_SERVICE_ROLE_KEY": "test-key"}):
            code = live.main(["--symbols", "BTCUSDT", "--target", "supabase",
                              "--samples", "1", "--interval", "2",
                              "--output-dir", str(fix_dir), "--live-dir", str(live_dir)])
        assert code == 0
        assert len(captured_rows) == 1
        row = captured_rows[0]
        assert row["symbol"] == "BTCUSDT"
        assert row["timeframe"] == "5m"
        assert row["exchange"] == "binance_spot"
        meta = row["payload"]["meta"]
        assert meta["source"] == "supabase_live_writer"
        assert meta["dataSource"] == "supabase_live_writer"
        assert meta["resolvedSource"] == "live"
        assert meta["isDemo"] is False
        assert meta["stale"] is False
        assert meta.get("writerTarget") == "supabase"
        # No local files written for supabase-only target.
        assert not (fix_dir / "BTCUSDT_5m.json").exists()
        assert not (live_dir / "BTCUSDT_5m.json").exists()

    def test_target_live_and_supabase_writes_both(self, tmp_path):
        upserted: list[str] = []

        def _fake_upsert(cfg, symbol, timeframe, payload, *, exchange="binance_spot"):
            upserted.append(f"{symbol}_{timeframe}")

        fix_dir = tmp_path / "fix"
        live_dir = tmp_path / "live"
        with patch.object(live, "fetch_depth_snapshot",
                          side_effect=lambda *a, **k: _mock_snapshot()), \
             patch.object(live.time, "sleep"), \
             patch.object(live, "upsert_supabase_payload", side_effect=_fake_upsert), \
             patch.dict("os.environ", {"SUPABASE_URL": "https://x.supabase.co",
                                       "SUPABASE_SERVICE_ROLE_KEY": "test-key"}):
            code = live.main(["--symbols", "BTCUSDT", "--target", "live-and-supabase",
                              "--samples", "1", "--interval", "2",
                              "--output-dir", str(fix_dir), "--live-dir", str(live_dir)])
        assert code == 0
        assert (live_dir / "BTCUSDT_5m.json").exists()
        assert not (fix_dir / "BTCUSDT_5m.json").exists()
        assert "BTCUSDT_5m" in upserted
        assert _payload(live_dir / "BTCUSDT_5m.json")["meta"]["source"] == "local_live_writer"

    def test_target_all_writes_fixture_live_supabase(self, tmp_path):
        upserted: list[str] = []

        def _fake_upsert(cfg, symbol, timeframe, payload, *, exchange="binance_spot"):
            upserted.append(f"{symbol}_{timeframe}")

        fix_dir = tmp_path / "fix"
        live_dir = tmp_path / "live"
        with patch.object(live, "fetch_depth_snapshot",
                          side_effect=lambda *a, **k: _mock_snapshot()), \
             patch.object(live.time, "sleep"), \
             patch.object(live, "upsert_supabase_payload", side_effect=_fake_upsert), \
             patch.dict("os.environ", {"SUPABASE_URL": "https://x.supabase.co",
                                       "SUPABASE_SERVICE_ROLE_KEY": "test-key"}):
            code = live.main(["--symbols", "BTCUSDT", "--target", "all",
                              "--samples", "1", "--interval", "2",
                              "--output-dir", str(fix_dir), "--live-dir", str(live_dir)])
        assert code == 0
        assert (fix_dir / "BTCUSDT_5m.json").exists()
        assert (live_dir / "BTCUSDT_5m.json").exists()
        assert "BTCUSDT_5m" in upserted

    def test_supabase_upsert_failure_does_not_crash(self, tmp_path):
        fix_dir = tmp_path / "fix"
        live_dir = tmp_path / "live"
        with patch.object(live, "fetch_depth_snapshot",
                          side_effect=lambda *a, **k: _mock_snapshot()), \
             patch.object(live.time, "sleep"), \
             patch.object(live, "upsert_supabase_payload",
                          side_effect=RuntimeError("network")), \
             patch.dict("os.environ", {"SUPABASE_URL": "https://x.supabase.co",
                                       "SUPABASE_SERVICE_ROLE_KEY": "test-key"}):
            code = live.main(["--symbols", "BTCUSDT", "--target", "live-and-supabase",
                              "--samples", "2", "--interval", "2",
                              "--output-dir", str(fix_dir), "--live-dir", str(live_dir)])
        assert code == 0
        assert (live_dir / "BTCUSDT_5m.json").exists()

    # ── forever / hosted worker mode ─────────────────────────────────────────

    def test_forever_runs_until_keyboard_interrupt(self, tmp_path):
        """--forever loops indefinitely; KeyboardInterrupt exits cleanly with rc 0."""
        fix_dir = tmp_path / "fix"
        live_dir = tmp_path / "live"

        sleep_calls = {"n": 0}
        def _sleep_then_interrupt(_secs: float) -> None:
            sleep_calls["n"] += 1
            if sleep_calls["n"] >= 3:
                raise KeyboardInterrupt

        with patch.object(live, "fetch_depth_snapshot",
                          side_effect=lambda *a, **k: _mock_snapshot()), \
             patch.object(live.time, "sleep", side_effect=_sleep_then_interrupt):
            code = live.main(["--symbols", "BTCUSDT", "--forever",
                              "--interval", "2",
                              "--output-dir", str(fix_dir),
                              "--live-dir", str(live_dir)])
        assert code == 0
        # Forever mode sleeps every tick (no "last tick" skip), so the
        # interrupt fires on the 3rd tick after 3 successful fetches.
        assert sleep_calls["n"] == 3
        assert (fix_dir / "BTCUSDT_5m.json").exists()

    def test_forever_ignores_samples(self, tmp_path):
        """--samples is ignored when --forever is set."""
        fix_dir = tmp_path / "fix"
        live_dir = tmp_path / "live"

        sleep_calls = {"n": 0}
        def _sleep_then_interrupt(_secs: float) -> None:
            sleep_calls["n"] += 1
            if sleep_calls["n"] >= 5:
                raise KeyboardInterrupt

        with patch.object(live, "fetch_depth_snapshot",
                          side_effect=lambda *a, **k: _mock_snapshot()), \
             patch.object(live.time, "sleep", side_effect=_sleep_then_interrupt):
            # --samples 1 would normally exit after one tick; --forever overrides.
            code = live.main(["--symbols", "BTCUSDT", "--forever",
                              "--samples", "1", "--interval", "2",
                              "--output-dir", str(fix_dir),
                              "--live-dir", str(live_dir)])
        assert code == 0
        assert sleep_calls["n"] == 5

    def test_forever_zero_samples_does_not_raise_validation(self, tmp_path):
        """--forever bypasses the samples > 0 validation check."""
        fix_dir = tmp_path / "fix"
        live_dir = tmp_path / "live"

        def _interrupt(_secs: float) -> None:
            raise KeyboardInterrupt

        with patch.object(live, "fetch_depth_snapshot",
                          side_effect=lambda *a, **k: _mock_snapshot()), \
             patch.object(live.time, "sleep", side_effect=_interrupt):
            code = live.main(["--symbols", "BTCUSDT", "--forever",
                              "--samples", "0", "--interval", "2",
                              "--output-dir", str(fix_dir),
                              "--live-dir", str(live_dir)])
        assert code == 0

    def test_forever_supabase_target_requires_env(self, tmp_path, capsys, monkeypatch):
        """--forever --target supabase still validates Supabase env up front."""
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
        code = live.main(["--symbols", "BTCUSDT", "--forever",
                          "--target", "supabase",
                          "--output-dir", str(tmp_path / "fix"),
                          "--live-dir", str(tmp_path / "live")])
        assert code == 1
        assert "SUPABASE" in capsys.readouterr().err

    def test_startup_banner_prints_mode_and_target_no_secrets(self, tmp_path, capsys, monkeypatch):
        """Banner shows mode/target/symbols but never echoes service-role key."""
        monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "super-secret-key-xyz")

        with patch.object(live, "fetch_depth_snapshot",
                          side_effect=lambda *a, **k: _mock_snapshot()), \
             patch.object(live.time, "sleep"), \
             patch.object(live, "upsert_supabase_payload"):
            live.main(["--symbols", "BTCUSDT", "--target", "supabase",
                       "--samples", "1", "--interval", "2",
                       "--output-dir", str(tmp_path / "fix"),
                       "--live-dir", str(tmp_path / "live")])
        captured = capsys.readouterr()
        out = captured.out + captured.err
        assert "mode" in out
        assert "samples=1" in out
        assert "target             = supabase" in out
        assert "BTCUSDT" in out
        assert "supabase           = configured" in out
        assert "super-secret-key-xyz" not in out

    def test_startup_banner_forever_label(self, tmp_path, capsys):
        """Banner says mode=forever when --forever is used."""
        def _interrupt(_secs: float) -> None:
            raise KeyboardInterrupt

        with patch.object(live, "fetch_depth_snapshot",
                          side_effect=lambda *a, **k: _mock_snapshot()), \
             patch.object(live.time, "sleep", side_effect=_interrupt):
            live.main(["--symbols", "BTCUSDT", "--forever",
                       "--interval", "2",
                       "--output-dir", str(tmp_path / "fix"),
                       "--live-dir", str(tmp_path / "live")])
        out = capsys.readouterr().out
        assert "mode               = forever" in out

    # ── LM43: price range presets ────────────────────────────────────────────

    def test_default_range_mode_stamps_btc_standard(self, tmp_path):
        """Default --range-mode=standard stamps the BTC ±3000 preset."""
        _, outdir, _, _ = _run_multi(
            tmp_path, ["--symbols", "BTCUSDT", "--samples", "1", "--interval", "2"],
        )
        meta = _payload(outdir / "BTCUSDT_5m.json")["meta"]
        assert meta["priceRangeMode"] == "standard"
        assert meta["priceRangeAbs"] == 3000.0
        # mid = 67495 → ±3000 → [64495, 70495]
        assert meta["priceRangeMin"] == 64495.0
        assert meta["priceRangeMax"] == 70495.0

    def test_range_mode_wide_is_wider_than_tight(self, tmp_path):
        _, outdir_tight, _, _ = _run_multi(
            tmp_path / "tight",
            ["--symbols", "BTCUSDT", "--range-mode", "tight",
             "--samples", "1", "--interval", "2"],
        )
        _, outdir_wide, _, _ = _run_multi(
            tmp_path / "wide",
            ["--symbols", "BTCUSDT", "--range-mode", "wide",
             "--samples", "1", "--interval", "2"],
        )
        m_tight = _payload(outdir_tight / "BTCUSDT_5m.json")["meta"]
        m_wide  = _payload(outdir_wide  / "BTCUSDT_5m.json")["meta"]
        tight_span = m_tight["priceRangeMax"] - m_tight["priceRangeMin"]
        wide_span  = m_wide["priceRangeMax"]  - m_wide["priceRangeMin"]
        assert wide_span > tight_span
        # BTC wide preset is ±7500 → 15000 wide.
        assert wide_span == 15000.0
        assert m_wide["priceRangeMode"] == "wide"

    def test_range_macro_keeps_bucket_count_bounded(self, tmp_path):
        """Macro range auto-scales price_step so the payload stays small."""
        _, outdir, _, _ = _run_multi(
            tmp_path,
            ["--symbols", "BTCUSDT", "--range-mode", "macro",
             "--samples", "1", "--interval", "2"],
        )
        payload = _payload(outdir / "BTCUSDT_5m.json")
        # macro = ±15000 = 30000 wide; auto-scaled step keeps cells modest.
        assert payload["meta"]["priceRangeMode"] == "macro"
        assert payload["meta"]["cellCount"] < 200  # mock snapshot is tiny

    def test_price_range_abs_overrides_preset(self, tmp_path):
        _, outdir, _, _ = _run_multi(
            tmp_path,
            ["--symbols", "BTCUSDT", "--range-mode", "tight",
             "--price-range-abs", "5000",
             "--samples", "1", "--interval", "2"],
        )
        meta = _payload(outdir / "BTCUSDT_5m.json")["meta"]
        assert meta["priceRangeAbs"] == 5000.0
        assert meta["priceRangeMax"] - meta["priceRangeMin"] == 10000.0

    def test_price_range_percent_overrides_preset(self, tmp_path):
        _, outdir, _, _ = _run_multi(
            tmp_path,
            ["--symbols", "BTCUSDT", "--range-mode", "tight",
             "--price-range-percent", "0.1",
             "--samples", "1", "--interval", "2"],
        )
        meta = _payload(outdir / "BTCUSDT_5m.json")["meta"]
        assert meta["priceRangePercent"] == 0.1
        # mid 67495 × 0.1 = 6749.5 radius → span ~13499
        span = meta["priceRangeMax"] - meta["priceRangeMin"]
        assert abs(span - 13499.0) < 1.0

    def test_unknown_symbol_falls_back_to_percent(self, tmp_path):
        """Symbols outside PRESET_ABS use the percent fallback."""
        # _run_multi calls main(), which requires the symbol to make it through
        # CLI parsing; symbol filtering happens server-side at fetch time.
        # We just verify the range meta uses percent fallback.
        from scripts import run_local_heatmap_live as live
        from unittest.mock import patch
        out = tmp_path / "fix"
        with patch.object(live, "fetch_depth_snapshot",
                          side_effect=lambda *a, **k: _mock_snapshot("FOOUSDT")), \
             patch.object(live.time, "sleep"):
            code = live.main([
                "--symbols", "FOOUSDT", "--range-mode", "wide",
                "--samples", "1", "--interval", "2",
                "--output-dir", str(out),
            ])
        assert code == 0
        meta = _payload(out / "FOOUSDT_5m.json")["meta"]
        # Unknown symbol → percent fallback (no abs).
        assert "priceRangeAbs" not in meta
        assert meta.get("priceRangePercent") == 0.07  # wide fallback

    def test_existing_default_behavior_still_writes_payload(self, tmp_path):
        """LM43 should be additive — default flow keeps producing valid payloads."""
        _, out, _, _ = _run(tmp_path, ["--samples", "2", "--interval", "2"])
        payload = _payload(out)
        # Cells still populated, meta still has the live writer tags.
        assert payload["cells"]
        assert payload["meta"]["source"] == "local_live_fixture"
        # And LM43 added a default range mode.
        assert payload["meta"]["priceRangeMode"] == "standard"

    def test_invalid_range_mode_cli_rejected(self, tmp_path):
        """argparse rejects unknown --range-mode values."""
        from scripts import run_local_heatmap_live as live
        from unittest.mock import patch
        with patch.object(live, "fetch_depth_snapshot",
                          side_effect=lambda *a, **k: _mock_snapshot()), \
             patch.object(live.time, "sleep"):
            with pytest.raises(SystemExit) as exc:
                live.main(["--symbols", "BTCUSDT", "--range-mode", "bogus",
                           "--samples", "1", "--interval", "2",
                           "--output-dir", str(tmp_path / "f")])
        assert exc.value.code != 0

    def test_wide_range_auto_bumps_depth_limit(self, tmp_path):
        """LM43B: --range-mode wide auto-requests deeper book (5000 vs 1000)."""
        from scripts import run_local_heatmap_live as live
        from unittest.mock import patch
        calls: list[tuple] = []
        def _spy(symbol, limit):
            calls.append((symbol, limit))
            return _mock_snapshot()
        with patch.object(live, "fetch_depth_snapshot", side_effect=_spy), \
             patch.object(live.time, "sleep"):
            code = live.main([
                "--symbols", "BTCUSDT", "--range-mode", "wide",
                "--samples", "1", "--interval", "2",
                "--output-dir", str(tmp_path / "fix"),
            ])
        assert code == 0
        assert calls and calls[0][1] == 5000

    def test_standard_range_keeps_default_depth_limit(self, tmp_path):
        from scripts import run_local_heatmap_live as live
        from unittest.mock import patch
        calls: list[tuple] = []
        def _spy(symbol, limit):
            calls.append((symbol, limit))
            return _mock_snapshot()
        with patch.object(live, "fetch_depth_snapshot", side_effect=_spy), \
             patch.object(live.time, "sleep"):
            code = live.main([
                "--symbols", "BTCUSDT",
                "--samples", "1", "--interval", "2",
                "--output-dir", str(tmp_path / "fix"),
            ])
        assert code == 0
        assert calls and calls[0][1] == 1000

    def test_explicit_limit_wins_over_auto_bump(self, tmp_path):
        from scripts import run_local_heatmap_live as live
        from unittest.mock import patch
        calls: list[tuple] = []
        def _spy(symbol, limit):
            calls.append((symbol, limit))
            return _mock_snapshot()
        with patch.object(live, "fetch_depth_snapshot", side_effect=_spy), \
             patch.object(live.time, "sleep"):
            code = live.main([
                "--symbols", "BTCUSDT", "--range-mode", "macro",
                "--limit", "100",
                "--samples", "1", "--interval", "2",
                "--output-dir", str(tmp_path / "fix"),
            ])
        assert code == 0
        assert calls and calls[0][1] == 100

    def test_payload_carries_lm44_zones(self, tmp_path):
        """LM44: writer-produced payload includes zones / keyZones / meta."""
        _, outdir, _, _ = _run_multi(
            tmp_path, ["--symbols", "BTCUSDT", "--samples", "1", "--interval", "2"],
        )
        payload = _payload(outdir / "BTCUSDT_5m.json")
        assert "zones" in payload
        assert "keyZones" in payload
        m = payload["meta"]
        assert m["aggregationMode"]   == "standard"
        assert m["wallScoreVersion"]  == "2"
        assert isinstance(m["zoneCount"], int)
        assert m["zoneCount"] == len(payload["zones"])
        # Every zone has the trader-facing fields.
        for z in payload["zones"]:
            for k in ("side", "priceMin", "priceMax", "centerPrice",
                      "totalUsd", "strengthScore", "label", "bucketCount"):
                assert k in z
            assert z["side"] in ("bid", "ask")

    def test_meta_available_depth_present(self, tmp_path):
        _, outdir, _, _ = _run_multi(
            tmp_path, ["--symbols", "BTCUSDT", "--samples", "1", "--interval", "2"],
        )
        meta = _payload(outdir / "BTCUSDT_5m.json")["meta"]
        assert "availableDepthMin" in meta
        assert "availableDepthMax" in meta
        # mock snapshot prices range 67410..67570
        assert meta["availableDepthMin"] == 67410.0
        assert meta["availableDepthMax"] == 67570.0

    def test_no_secret_values_printed(self, tmp_path, capsys):
        fix_dir = tmp_path / "fix"
        live_dir = tmp_path / "live"
        with patch.object(live, "fetch_depth_snapshot",
                          side_effect=lambda *a, **k: _mock_snapshot()), \
             patch.object(live.time, "sleep"), \
             patch.object(live, "upsert_supabase_payload"), \
             patch.dict("os.environ", {"SUPABASE_URL": "https://x.supabase.co",
                                       "SUPABASE_SERVICE_ROLE_KEY": "super-secret-key-123"}):
            live.main(["--symbols", "BTCUSDT", "--target", "supabase",
                       "--samples", "1", "--interval", "2",
                       "--output-dir", str(fix_dir), "--live-dir", str(live_dir)])
        captured = capsys.readouterr()
        assert "super-secret-key-123" not in captured.out
        assert "super-secret-key-123" not in captured.err
