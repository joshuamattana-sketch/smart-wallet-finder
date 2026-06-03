"""
tests/test_binance_ws_heatmap_live.py
--------------------------------------
Tests for scripts/run_binance_ws_heatmap_live.py.

No real WebSocket calls and no real Supabase calls:
  * `message_iter` is a plain Python iterator/list of fake JSON strings.
  * `fetch_depth` is injected; default `upsert_supabase_payload` is patched.
  * `now()` is a controllable counter so write-interval throttling is
    fully deterministic.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from scripts import run_binance_ws_heatmap_live as ws
from scripts.run_local_heatmap_live import SupabaseConfig


# ── Fixtures / helpers ────────────────────────────────────────────────────────

def _lvl(price: float, qty: float) -> dict:
    return {"price": price, "quantity": qty, "usd": round(price * qty, 2)}


def _mock_snapshot(symbol: str = "BTCUSDT") -> dict:
    return {
        "symbol":         symbol,
        "last_update_id": 1,
        "captured_at":    "2026-06-01T12:00:00+00:00",
        "bids": [_lvl(67490.0, 0.5), _lvl(67420.0, 25.0)],
        "asks": [_lvl(67500.0, 0.5), _lvl(67560.0, 22.0)],
    }


def _bt(bid: float, ask: float) -> str:
    """A Binance bookTicker JSON string."""
    return json.dumps({
        "u": 1, "s": "BTCUSDT",
        "b": f"{bid}", "B": "1.0",
        "a": f"{ask}", "A": "1.0",
    })


class _Clock:
    """Monotonic clock that ticks `step` seconds per call."""
    def __init__(self, step: float = 0.5) -> None:
        self.t = 0.0
        self.step = step

    def __call__(self) -> float:
        self.t += self.step
        return self.t


def _output_factory(tmp_path: Path):
    out_dir = tmp_path / "live"
    return out_dir, (lambda sym, tf: out_dir / f"{sym}_{tf}.json")


# ── parse_book_ticker ─────────────────────────────────────────────────────────

class TestParseBookTicker:

    def test_valid_message_yields_bid_ask(self):
        out = ws.parse_book_ticker(_bt(100.0, 101.0))
        # LM42B: parse_book_ticker also surfaces `symbol` from the message
        # so combined-stream collectors can route to per-symbol state.
        assert out == {
            "bestBid":    100.0,
            "bestAsk":    101.0,
            "bestBidQty": 1.0,
            "bestAskQty": 1.0,
            "symbol":     "BTCUSDT",
        }

    def test_combined_stream_wrapper(self):
        wrapped = json.dumps({
            "stream": "btcusdt@bookTicker",
            "data":   {"s": "BTCUSDT", "b": "1.0", "B": "1", "a": "1.5", "A": "1"},
        })
        out = ws.parse_book_ticker(wrapped)
        assert out is not None
        assert out["bestBid"] == 1.0 and out["bestAsk"] == 1.5

    def test_bad_json_returns_none(self):
        assert ws.parse_book_ticker("{not json") is None

    def test_none_input_returns_none(self):
        assert ws.parse_book_ticker(None) is None

    def test_missing_fields_returns_none(self):
        assert ws.parse_book_ticker(json.dumps({"s": "BTCUSDT"})) is None

    def test_non_numeric_returns_none(self):
        assert ws.parse_book_ticker(json.dumps({"b": "x", "a": "y"})) is None


# ── run_ws_collector ─────────────────────────────────────────────────────────

class TestRunWsCollector:

    def test_first_write_updates_bid_ask_mid_in_pricepath(self, tmp_path):
        out_dir, output_for = _output_factory(tmp_path)
        msgs = [_bt(100.0, 102.0), None, None, None]
        upserts: list[dict] = []

        ws.run_ws_collector(
            symbol="BTCUSDT", timeframes=["5m"],
            write_interval=1.0, max_frames=10,
            target="live", supabase=None,
            output_for=output_for,
            message_iter=iter(msgs),
            fetch_depth=lambda *a, **k: _mock_snapshot(),
            samples=1, forever=False,
            now=_Clock(step=0.5),
            upsert=lambda *a, **k: upserts.append({}),
        )
        payload = json.loads((out_dir / "BTCUSDT_5m.json").read_text("utf-8"))
        assert payload["pricePath"], "pricePath should have at least one point"
        last = payload["pricePath"][-1]
        assert last["bestBid"] == 100.0
        assert last["bestAsk"] == 102.0
        assert last["price"] == 101.0  # mid

    def test_payload_meta_collector_tags(self, tmp_path):
        out_dir, output_for = _output_factory(tmp_path)
        ws.run_ws_collector(
            symbol="BTCUSDT", timeframes=["5m"],
            write_interval=1.0, max_frames=10,
            target="live", supabase=None,
            output_for=output_for,
            message_iter=iter([_bt(100.0, 101.0)]),
            fetch_depth=lambda *a, **k: _mock_snapshot(),
            samples=1, forever=False, now=_Clock(step=0.5),
        )
        meta = json.loads((out_dir / "BTCUSDT_5m.json").read_text("utf-8"))["meta"]
        assert meta["source"]               == "binance_ws_live_writer"
        assert meta["dataSource"]           == "binance_ws_live_writer"
        assert meta["resolvedSource"]       == "live"
        assert meta["isDemo"]               is False
        assert meta["stale"]                is False
        assert meta["collector"]            == "binance_websocket"
        assert meta["stream"]               == "bookTicker"
        assert meta["writeIntervalSeconds"] == 1.0
        assert meta.get("liveUpdatedAt")

    def test_supabase_row_shape_calls_upsert_per_timeframe(self, tmp_path):
        _, output_for = _output_factory(tmp_path)
        sb_cfg = SupabaseConfig("https://example.supabase.co", "key")
        calls: list[tuple[str, str, dict]] = []

        def _fake_upsert(cfg, symbol, timeframe, payload, **_):
            assert cfg is sb_cfg
            calls.append((symbol, timeframe, payload))

        ws.run_ws_collector(
            symbol="BTCUSDT", timeframes=["5m", "15m"],
            write_interval=1.0, max_frames=10,
            target="supabase", supabase=sb_cfg,
            output_for=output_for,
            message_iter=iter([_bt(100.0, 101.0)]),
            fetch_depth=lambda *a, **k: _mock_snapshot(),
            samples=1, forever=False, now=_Clock(step=0.5),
            upsert=_fake_upsert,
        )
        # One write cycle × two timeframes = two upserts.
        assert [c[1] for c in calls] == ["5m", "15m"]
        for sym, tf, payload in calls:
            assert sym == "BTCUSDT"
            assert payload["symbol"] == "BTCUSDT"
            assert payload["timeframe"] == tf
            meta = payload["meta"]
            assert meta["collector"] == "binance_websocket"
            assert meta["resolvedSource"] == "live"

    def test_write_interval_throttles_writes(self, tmp_path):
        """100 messages, write_interval=2s, clock=0.1s/step → ~5 writes max."""
        _, output_for = _output_factory(tmp_path)
        msgs = [_bt(100.0 + i * 0.01, 101.0 + i * 0.01) for i in range(100)]
        writes_seen: list[int] = []

        def _fake_upsert(*_a, **_k):
            writes_seen.append(1)

        sb_cfg = SupabaseConfig("https://example.supabase.co", "key")
        result = ws.run_ws_collector(
            symbol="BTCUSDT", timeframes=["5m"],
            write_interval=2.0, max_frames=10,
            target="supabase", supabase=sb_cfg,
            output_for=output_for,
            message_iter=iter(msgs),
            fetch_depth=lambda *a, **k: _mock_snapshot(),
            samples=None, forever=False,  # finite — exits when msgs exhausted
            now=_Clock(step=0.1),
            upsert=_fake_upsert,
        )
        # 100 msgs × 0.1s = ~10s elapsed; write_interval=2s → at most 6 writes
        # (including the bootstrap-eager first write).
        assert 2 <= result["writes"] <= 6
        assert len(writes_seen) == result["writes"]
        assert result["messages"] == 100

    def test_samples_stops_after_n_writes(self, tmp_path):
        _, output_for = _output_factory(tmp_path)
        # Provide far more messages than needed; loop must exit at samples=3.
        msgs = [_bt(100.0, 101.0)] * 500
        result = ws.run_ws_collector(
            symbol="BTCUSDT", timeframes=["5m"],
            write_interval=0.5, max_frames=10,
            target="live", supabase=None,
            output_for=output_for,
            message_iter=iter(msgs),
            fetch_depth=lambda *a, **k: _mock_snapshot(),
            samples=3, forever=False,
            now=_Clock(step=1.0),
        )
        assert result["writes"] == 3

    def test_keyboard_interrupt_exits_cleanly(self, tmp_path):
        _, output_for = _output_factory(tmp_path)

        def _interrupting_iter():
            yield _bt(100.0, 101.0)
            raise KeyboardInterrupt

        result = ws.run_ws_collector(
            symbol="BTCUSDT", timeframes=["5m"],
            write_interval=10.0, max_frames=10,
            target="live", supabase=None,
            output_for=output_for,
            message_iter=_interrupting_iter(),
            fetch_depth=lambda *a, **k: _mock_snapshot(),
            samples=None, forever=True,
            now=_Clock(step=0.1),
        )
        # KeyboardInterrupt is caught and we return normally with stats.
        assert result["messages"] == 1
        assert result["writes"] >= 0  # may or may not have hit the gate yet

    def test_bad_messages_do_not_crash(self, tmp_path):
        _, output_for = _output_factory(tmp_path)
        msgs = ["{not json", json.dumps({"s": "x"}), _bt(100.0, 101.0)]
        result = ws.run_ws_collector(
            symbol="BTCUSDT", timeframes=["5m"],
            write_interval=0.1, max_frames=10,
            target="live", supabase=None,
            output_for=output_for,
            message_iter=iter(msgs),
            fetch_depth=lambda *a, **k: _mock_snapshot(),
            samples=1, forever=False, now=_Clock(step=0.5),
        )
        assert result["writes"] == 1

    def test_depth_failure_does_not_crash(self, tmp_path):
        """First depth fetch fails → no frames → no writes; loop survives."""
        _, output_for = _output_factory(tmp_path)
        from services.connectors.binance_depth_collector import DepthCollectorError

        def _bad_depth(*_a, **_k):
            raise DepthCollectorError("boom")

        result = ws.run_ws_collector(
            symbol="BTCUSDT", timeframes=["5m"],
            write_interval=0.1, max_frames=10,
            target="live", supabase=None,
            output_for=output_for,
            message_iter=iter([_bt(100.0, 101.0)] * 5),
            fetch_depth=_bad_depth,
            depth_refresh_seconds=1000.0,  # don't retry within the test window
            samples=None, forever=False, now=_Clock(step=0.5),
        )
        assert result["writes"] == 0  # no frames → no writes
        assert result["messages"] == 5

    def test_supabase_upsert_failure_does_not_crash(self, tmp_path):
        _, output_for = _output_factory(tmp_path)
        sb_cfg = SupabaseConfig("https://example.supabase.co", "key")

        def _flaky_upsert(*_a, **_k):
            raise RuntimeError("network")

        result = ws.run_ws_collector(
            symbol="BTCUSDT", timeframes=["5m"],
            write_interval=0.1, max_frames=10,
            target="supabase", supabase=sb_cfg,
            output_for=output_for,
            message_iter=iter([_bt(100.0, 101.0)] * 3),
            fetch_depth=lambda *a, **k: _mock_snapshot(),
            samples=2, forever=False, now=_Clock(step=0.5),
            upsert=_flaky_upsert,
        )
        assert result["writes"] == 2  # writes still counted; per-target failure swallowed

    # ── validation ──────────────────────────────────────────────────────────

    def test_invalid_timeframe(self, tmp_path):
        _, output_for = _output_factory(tmp_path)
        import pytest
        with pytest.raises(ValueError, match="invalid timeframe"):
            ws.run_ws_collector(
                symbol="BTCUSDT", timeframes=["3m"],
                write_interval=1.0, max_frames=10,
                target="live", supabase=None,
                output_for=output_for,
                message_iter=iter([]),
                fetch_depth=lambda *a, **k: _mock_snapshot(),
            )

    def test_invalid_write_interval(self, tmp_path):
        _, output_for = _output_factory(tmp_path)
        import pytest
        with pytest.raises(ValueError, match="write-interval"):
            ws.run_ws_collector(
                symbol="BTCUSDT", timeframes=["5m"],
                write_interval=0, max_frames=10,
                target="live", supabase=None,
                output_for=output_for,
                message_iter=iter([]),
                fetch_depth=lambda *a, **k: _mock_snapshot(),
            )

    def test_supabase_target_without_config_raises(self, tmp_path):
        _, output_for = _output_factory(tmp_path)
        import pytest
        with pytest.raises(ValueError, match="supabase target"):
            ws.run_ws_collector(
                symbol="BTCUSDT", timeframes=["5m"],
                write_interval=1.0, max_frames=10,
                target="supabase", supabase=None,
                output_for=output_for,
                message_iter=iter([]),
                fetch_depth=lambda *a, **k: _mock_snapshot(),
            )


# ── CLI main() ────────────────────────────────────────────────────────────────

class TestMainCli:

    def test_supabase_target_requires_env(self, tmp_path, capsys, monkeypatch):
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
        code = ws.main([
            "--symbol", "BTCUSDT", "--target", "supabase",
            "--samples", "1",
            "--live-dir", str(tmp_path / "live"),
        ])
        assert code == 1
        assert "SUPABASE" in capsys.readouterr().err

    def test_invalid_timeframe_cli(self, tmp_path, capsys):
        code = ws.main([
            "--symbol", "BTCUSDT", "--timeframes", "3m", "--target", "live",
            "--samples", "1",
            "--live-dir", str(tmp_path / "live"),
        ])
        assert code == 1
        assert "invalid timeframe" in capsys.readouterr().err

    def test_payload_carries_lm44_zones(self, tmp_path):
        """LM44: WS collector payload includes zones / keyZones / meta."""
        out_dir, output_for = _output_factory(tmp_path)
        ws.run_ws_collector(
            symbol="BTCUSDT", timeframes=["5m"],
            write_interval=1.0, max_frames=10,
            target="live", supabase=None,
            output_for=output_for,
            message_iter=iter([_bt(100000.0, 100020.0)]),
            fetch_depth=lambda *a, **k: _mock_snapshot(),
            samples=1, forever=False, now=_Clock(step=0.5),
            range_mode="standard",
        )
        payload = json.loads((out_dir / "BTCUSDT_5m.json").read_text("utf-8"))
        assert "zones" in payload
        assert "keyZones" in payload
        assert payload["meta"]["wallScoreVersion"] == "2"
        assert payload["meta"]["aggregationMode"] == "standard"

    def test_range_mode_stamps_meta_on_payload(self, tmp_path):
        """WS collector stamps priceRangeMode/Min/Max after the first message."""
        out_dir, output_for = _output_factory(tmp_path)
        ws.run_ws_collector(
            symbol="BTCUSDT", timeframes=["5m"],
            write_interval=1.0, max_frames=10,
            target="live", supabase=None,
            output_for=output_for,
            message_iter=iter([_bt(100000.0, 100020.0)]),
            fetch_depth=lambda *a, **k: _mock_snapshot(),
            samples=1, forever=False, now=_Clock(step=0.5),
            range_mode="standard",
        )
        meta = json.loads((out_dir / "BTCUSDT_5m.json").read_text("utf-8"))["meta"]
        # mid = 100010 → BTC standard ±3000 → [97010, 103010].
        assert meta["priceRangeMode"] == "standard"
        assert meta["priceRangeAbs"] == 3000.0
        assert meta["priceRangeMin"] == 97010.0
        assert meta["priceRangeMax"] == 103010.0

    def test_range_mode_abs_override(self, tmp_path):
        out_dir, output_for = _output_factory(tmp_path)
        ws.run_ws_collector(
            symbol="BTCUSDT", timeframes=["5m"],
            write_interval=1.0, max_frames=10,
            target="live", supabase=None,
            output_for=output_for,
            message_iter=iter([_bt(100000.0, 100020.0)]),
            fetch_depth=lambda *a, **k: _mock_snapshot(),
            samples=1, forever=False, now=_Clock(step=0.5),
            range_mode="tight", price_range_abs=4000.0,
        )
        meta = json.loads((out_dir / "BTCUSDT_5m.json").read_text("utf-8"))["meta"]
        assert meta["priceRangeAbs"] == 4000.0
        assert meta["priceRangeMax"] - meta["priceRangeMin"] == 8000.0

    def test_invalid_range_mode_raises(self, tmp_path):
        _, output_for = _output_factory(tmp_path)
        import pytest
        with pytest.raises(ValueError, match="invalid range mode"):
            ws.run_ws_collector(
                symbol="BTCUSDT", timeframes=["5m"],
                write_interval=1.0, max_frames=10,
                target="live", supabase=None,
                output_for=output_for,
                message_iter=iter([]),
                fetch_depth=lambda *a, **k: _mock_snapshot(),
                range_mode="bogus",
            )

    def test_wide_range_auto_bumps_depth_limit(self, tmp_path):
        """LM43B: --range-mode wide bumps WS collector's depth_limit to 5000."""
        captured_depth_limits: list[int] = []
        def _spy_collector(*, depth_limit, **_):
            captured_depth_limits.append(depth_limit)
            return {"writes": 0, "messages": 0}
        with patch.object(ws, "_default_ws_messages_with_reconnect",
                          return_value=iter([])), \
             patch.object(ws, "run_ws_collector", side_effect=_spy_collector):
            ws.main([
                "--symbol", "BTCUSDT", "--range-mode", "wide",
                "--target", "live", "--samples", "1",
                "--live-dir", str(tmp_path / "live"),
            ])
        assert captured_depth_limits == [5000]

    def test_standard_range_keeps_default_depth_limit(self, tmp_path):
        captured_depth_limits: list[int] = []
        def _spy_collector(*, depth_limit, **_):
            captured_depth_limits.append(depth_limit)
            return {"writes": 0, "messages": 0}
        with patch.object(ws, "_default_ws_messages_with_reconnect",
                          return_value=iter([])), \
             patch.object(ws, "run_ws_collector", side_effect=_spy_collector):
            ws.main([
                "--symbol", "BTCUSDT",
                "--target", "live", "--samples", "1",
                "--live-dir", str(tmp_path / "live"),
            ])
        assert captured_depth_limits == [1000]

    def test_explicit_depth_limit_wins_over_auto_bump(self, tmp_path):
        captured_depth_limits: list[int] = []
        def _spy_collector(*, depth_limit, **_):
            captured_depth_limits.append(depth_limit)
            return {"writes": 0, "messages": 0}
        with patch.object(ws, "_default_ws_messages_with_reconnect",
                          return_value=iter([])), \
             patch.object(ws, "run_ws_collector", side_effect=_spy_collector):
            ws.main([
                "--symbol", "BTCUSDT", "--range-mode", "macro",
                "--depth-limit", "100",
                "--target", "live", "--samples", "1",
                "--live-dir", str(tmp_path / "live"),
            ])
        assert captured_depth_limits == [100]

    # ── LM42B: multi-symbol ──────────────────────────────────────────────────

    def test_symbols_cli_parses_csv(self, tmp_path, monkeypatch):
        captured: dict = {}
        def _spy(*, symbols, **_):
            captured["symbols"] = list(symbols)
            return {"writes": 0, "messages": 0, "per_symbol": {}}
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
        with patch.object(ws, "_default_ws_messages_with_reconnect",
                          return_value=iter([])), \
             patch.object(ws, "run_ws_collector", side_effect=_spy):
            code = ws.main([
                "--symbols", "BTCUSDT,ETHUSDT,SOLUSDT",
                "--target", "live", "--samples", "1",
                "--live-dir", str(tmp_path / "live"),
            ])
        assert code == 0
        assert captured["symbols"] == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

    def test_symbol_backward_compat(self, tmp_path):
        """Old --symbol BTCUSDT flow still resolves to a single-symbol list."""
        captured: dict = {}
        def _spy(*, symbols, **_):
            captured["symbols"] = list(symbols)
            return {"writes": 0, "messages": 0, "per_symbol": {}}
        with patch.object(ws, "_default_ws_messages_with_reconnect",
                          return_value=iter([])), \
             patch.object(ws, "run_ws_collector", side_effect=_spy):
            code = ws.main([
                "--symbol", "BTCUSDT",
                "--target", "live", "--samples", "1",
                "--live-dir", str(tmp_path / "live"),
            ])
        assert code == 0
        assert captured["symbols"] == ["BTCUSDT"]

    def test_invalid_symbol_fails_cli(self, tmp_path, capsys):
        code = ws.main([
            "--symbols", "BTC-USDT",  # dash not allowed
            "--target", "live", "--samples", "1",
            "--live-dir", str(tmp_path / "live"),
        ])
        assert code == 1
        assert "invalid Binance symbol" in capsys.readouterr().err

    def test_build_ws_url_single(self):
        assert ws.build_ws_url(["BTCUSDT"]) == (
            "wss://stream.binance.com:9443/ws/btcusdt@bookTicker"
        )

    def test_build_ws_url_combined(self):
        assert ws.build_ws_url(["BTCUSDT", "ETHUSDT", "SOLUSDT"]) == (
            "wss://stream.binance.com:9443/stream"
            "?streams=btcusdt@bookTicker/ethusdt@bookTicker/solusdt@bookTicker"
        )

    def test_build_ws_url_empty_raises(self):
        import pytest
        with pytest.raises(ValueError, match="at least one symbol"):
            ws.build_ws_url([])

    def test_parse_book_ticker_returns_symbol(self):
        out = ws.parse_book_ticker(_bt(100.0, 101.0))
        assert out is not None
        assert out["symbol"] == "BTCUSDT"

    def test_parse_combined_payload_routes_per_symbol(self):
        eth_wrapped = json.dumps({
            "stream": "ethusdt@bookTicker",
            "data": {"s": "ETHUSDT", "b": "2000.0", "B": "1", "a": "2010.0", "A": "1"},
        })
        out = ws.parse_book_ticker(eth_wrapped)
        assert out["symbol"] == "ETHUSDT"
        assert out["bestBid"] == 2000.0

    def test_multi_symbol_state_isolation(self, tmp_path):
        """BTC message updates only BTC state; ETH message only ETH state."""
        out_dir = tmp_path / "live"
        # 3 BTC msgs + 1 ETH msg. Samples=4: BTC writes 3 times, ETH writes once.
        msgs = [
            _bt(100.0, 101.0),                  # BTC
            _bt(100.0, 101.0),                  # BTC
            _bt(100.0, 101.0),                  # BTC
            json.dumps({"s": "ETHUSDT", "b": "2000.0", "B": "1",
                        "a": "2010.0", "A": "1"}),
        ]
        result = ws.run_ws_collector(
            symbols=["BTCUSDT", "ETHUSDT"], timeframes=["5m"],
            write_interval=0.1, max_frames=10,
            target="live", supabase=None,
            output_for=lambda sym, tf: out_dir / f"{sym}_{tf}.json",
            message_iter=iter(msgs),
            fetch_depth=lambda sym, _l: _mock_snapshot(sym),
            samples=None, forever=False, now=_Clock(step=0.5),
        )
        assert result["per_symbol"]["BTCUSDT"] >= 1
        assert result["per_symbol"]["ETHUSDT"] >= 1
        # Both files exist with the correct symbol baked in.
        btc = json.loads((out_dir / "BTCUSDT_5m.json").read_text("utf-8"))
        eth = json.loads((out_dir / "ETHUSDT_5m.json").read_text("utf-8"))
        assert btc["symbol"] == "BTCUSDT"
        assert eth["symbol"] == "ETHUSDT"

    def test_one_symbol_depth_failure_does_not_erase_other(self, tmp_path):
        """A failing fetch_depth for ETH doesn't wipe BTC's frames."""
        from services.connectors.binance_depth_collector import DepthCollectorError
        out_dir = tmp_path / "live"

        def _spotty_depth(sym, _l):
            if sym == "ETHUSDT":
                raise DepthCollectorError("simulated ETH outage")
            return _mock_snapshot(sym)

        msgs = [_bt(100.0, 101.0)] * 5  # BTC msgs only
        result = ws.run_ws_collector(
            symbols=["BTCUSDT", "ETHUSDT"], timeframes=["5m"],
            write_interval=0.1, max_frames=10,
            target="live", supabase=None,
            output_for=lambda sym, tf: out_dir / f"{sym}_{tf}.json",
            message_iter=iter(msgs),
            fetch_depth=_spotty_depth,
            samples=2, forever=False, now=_Clock(step=0.5),
        )
        # BTC kept rolling, ETH never got a frame → only BTC writes counted.
        assert result["per_symbol"]["BTCUSDT"] >= 1
        assert result["per_symbol"]["ETHUSDT"] == 0
        assert (out_dir / "BTCUSDT_5m.json").exists()
        assert not (out_dir / "ETHUSDT_5m.json").exists()

    def test_samples_caps_total_across_symbols(self, tmp_path):
        """`samples` counts TOTAL writes across all symbols, not per-symbol."""
        out_dir = tmp_path / "live"
        # Lots of messages for both BTC and ETH; cap total at 4.
        msgs = []
        for _ in range(20):
            msgs.append(_bt(100.0, 101.0))
            msgs.append(json.dumps({"s": "ETHUSDT", "b": "2000", "B": "1",
                                    "a": "2010", "A": "1"}))
        result = ws.run_ws_collector(
            symbols=["BTCUSDT", "ETHUSDT"], timeframes=["5m"],
            write_interval=0.5, max_frames=10,
            target="live", supabase=None,
            output_for=lambda sym, tf: out_dir / f"{sym}_{tf}.json",
            message_iter=iter(msgs),
            fetch_depth=lambda sym, _l: _mock_snapshot(sym),
            samples=4, forever=False, now=_Clock(step=1.0),
        )
        assert result["writes"] == 4

    def test_invalid_symbol_in_collector_raises(self, tmp_path):
        import pytest
        with pytest.raises(ValueError, match="invalid Binance symbol"):
            ws.run_ws_collector(
                symbols=["BTC-USDT"], timeframes=["5m"],
                write_interval=1.0, max_frames=10,
                target="live", supabase=None,
                output_for=lambda s, t: tmp_path / f"{s}_{t}.json",
                message_iter=iter([]),
                fetch_depth=lambda *a, **k: _mock_snapshot(),
            )

    # ── LM45: history persistence ─────────────────────────────────────────────

    def test_default_history_target_is_none_no_history_calls(self, tmp_path):
        """Default --history-target none: history append funcs are never called."""
        out_dir, output_for = _output_factory(tmp_path)
        history_calls: list = []
        def _spy_history(*a, **k): history_calls.append(("history", a, k))
        def _spy_walls(*a, **k):   history_calls.append(("walls", a, k))
        ws.run_ws_collector(
            symbols=["BTCUSDT"], timeframes=["5m"],
            write_interval=0.5, max_frames=10,
            target="live", supabase=None,
            output_for=output_for,
            message_iter=iter([_bt(100.0, 101.0)] * 3),
            fetch_depth=lambda *a, **k: _mock_snapshot(),
            samples=2, forever=False, now=_Clock(step=0.5),
            append_history=_spy_history, append_walls=_spy_walls,
        )
        assert history_calls == []  # off by default → never called

    def test_history_target_supabase_requires_config(self, tmp_path):
        """history_target=supabase but no SupabaseConfig → ValueError up front."""
        _, output_for = _output_factory(tmp_path)
        import pytest
        with pytest.raises(ValueError, match="history-target=supabase requires"):
            ws.run_ws_collector(
                symbols=["BTCUSDT"], timeframes=["5m"],
                write_interval=1.0, max_frames=10,
                target="live", supabase=None,
                output_for=output_for,
                message_iter=iter([]),
                fetch_depth=lambda *a, **k: _mock_snapshot(),
                history_target="supabase",
            )

    def test_invalid_history_target_rejected(self, tmp_path):
        _, output_for = _output_factory(tmp_path)
        import pytest
        with pytest.raises(ValueError, match="invalid history-target"):
            ws.run_ws_collector(
                symbols=["BTCUSDT"], timeframes=["5m"],
                write_interval=1.0, max_frames=10,
                target="live", supabase=None,
                output_for=output_for,
                message_iter=iter([]),
                fetch_depth=lambda *a, **k: _mock_snapshot(),
                history_target="bogus",
            )

    def test_invalid_history_interval_rejected(self, tmp_path):
        _, output_for = _output_factory(tmp_path)
        import pytest
        with pytest.raises(ValueError, match="history-interval"):
            ws.run_ws_collector(
                symbols=["BTCUSDT"], timeframes=["5m"],
                write_interval=1.0, max_frames=10,
                target="live", supabase=None,
                output_for=output_for,
                message_iter=iter([]),
                fetch_depth=lambda *a, **k: _mock_snapshot(),
                history_interval=0,
            )

    def test_history_interval_throttles_writes(self, tmp_path):
        """Many latest writes but only one history append within the interval."""
        _, output_for = _output_factory(tmp_path)
        sb_cfg = SupabaseConfig("https://example.supabase.co", "fake-key")
        history_frames: list = []
        wall_batches:   list = []
        def _spy_frame(_cfg, row): history_frames.append(row)
        def _spy_walls(_cfg, rows): wall_batches.append(list(rows))
        # 10 msgs, clock advances 0.5s per iteration so total ~5s elapsed.
        # write_interval=0.5 → ~10 latest writes; history_interval=3.0 →
        # at most 2 history appends per symbol per timeframe.
        result = ws.run_ws_collector(
            symbols=["BTCUSDT"], timeframes=["5m"],
            write_interval=0.5, max_frames=10,
            target="supabase", supabase=sb_cfg,
            output_for=output_for,
            message_iter=iter([_bt(100.0, 101.0)] * 10),
            fetch_depth=lambda *a, **k: _mock_snapshot(),
            samples=None, forever=False, now=_Clock(step=0.5),
            upsert=lambda *a, **k: None,                   # latest no-op
            history_target="supabase", history_interval=3.0,
            append_history=_spy_frame, append_walls=_spy_walls,
        )
        assert result["writes"] >= 5
        # History throttled — at most 3 frames over a ~5s window.
        assert 1 <= len(history_frames) <= 3
        assert result["history_writes"] == len(history_frames)
        # Wall append called the same number of times as frame append.
        assert len(wall_batches) == len(history_frames)

    def test_history_failure_does_not_stop_latest_writes(self, tmp_path):
        """append_history raising HistoryWriteError must not abort the loop."""
        _, output_for = _output_factory(tmp_path)
        sb_cfg = SupabaseConfig("https://example.supabase.co", "fake-key")
        from services.heatmap_history import HistoryWriteError
        upserts: list = []
        def _ok_upsert(*a, **k): upserts.append(1)
        def _bad_history(*a, **k):
            raise HistoryWriteError("supabase 500")
        result = ws.run_ws_collector(
            symbols=["BTCUSDT"], timeframes=["5m"],
            write_interval=0.5, max_frames=10,
            target="supabase", supabase=sb_cfg,
            output_for=output_for,
            message_iter=iter([_bt(100.0, 101.0)] * 8),
            fetch_depth=lambda *a, **k: _mock_snapshot(),
            samples=4, forever=False, now=_Clock(step=0.5),
            upsert=_ok_upsert,
            history_target="supabase", history_interval=0.1,
            append_history=_bad_history,
            append_walls=lambda *a, **k: None,
        )
        # Latest writes happened despite history failing every time.
        assert result["writes"] == 4
        assert len(upserts) == 4
        assert result["history_failures"] >= 1
        assert result["history_writes"] == 0

    def test_history_row_carries_collector_and_symbol(self, tmp_path):
        """Row shape: symbol/exchange/timeframe/frame_ts/collector/range_mode set."""
        _, output_for = _output_factory(tmp_path)
        sb_cfg = SupabaseConfig("https://example.supabase.co", "fake-key")
        captured_rows: list = []
        def _spy_frame(_cfg, row): captured_rows.append(row)
        ws.run_ws_collector(
            symbols=["BTCUSDT"], timeframes=["5m"],
            write_interval=0.5, max_frames=10,
            target="supabase", supabase=sb_cfg,
            output_for=output_for,
            message_iter=iter([_bt(100.0, 101.0)] * 3),
            fetch_depth=lambda *a, **k: _mock_snapshot(),
            samples=1, forever=False, now=_Clock(step=0.5),
            upsert=lambda *a, **k: None,
            history_target="supabase", history_interval=0.1,
            append_history=_spy_frame,
            append_walls=lambda *a, **k: None,
        )
        assert captured_rows
        row = captured_rows[0]
        assert row["symbol"]    == "BTCUSDT"
        assert row["exchange"]  == "binance_spot"
        assert row["timeframe"] == "5m"
        assert row["collector"] == "binance_websocket"
        assert row["range_mode"] in ("standard", "wide", "tight", "macro")
        assert row["current_price"] is not None

    def test_history_cli_flags_parse(self, tmp_path, monkeypatch):
        captured: dict = {}
        def _spy(**kwargs):
            captured.update(kwargs)
            return {"writes": 0, "messages": 0, "per_symbol": {},
                    "history_writes": 0, "history_failures": 0,
                    "history_per_symbol": {}}
        monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "fake-key")
        with patch.object(ws, "_default_ws_messages_with_reconnect",
                          return_value=iter([])), \
             patch.object(ws, "run_ws_collector", side_effect=_spy):
            code = ws.main([
                "--symbols", "BTCUSDT", "--target", "supabase",
                "--samples", "1", "--live-dir", str(tmp_path / "live"),
                "--history-target", "supabase",
                "--history-interval", "5",
                "--history-max-cells", "120",
                "--history-max-walls", "10",
            ])
        assert code == 0
        assert captured["history_target"]    == "supabase"
        assert captured["history_interval"]  == 5.0
        assert captured["history_max_cells"] == 120
        assert captured["history_max_walls"] == 10

    def test_startup_banner_no_secrets(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "super-secret-xyz")

        # Patch the real WS transport so we never touch the network, and the
        # collector so the test exits immediately after the banner.
        with patch.object(ws, "_default_ws_messages_with_reconnect",
                          return_value=iter([])), \
             patch.object(ws, "run_ws_collector",
                          return_value={"writes": 0, "messages": 0}):
            code = ws.main([
                "--symbol", "BTCUSDT", "--target", "supabase",
                "--samples", "1", "--live-dir", str(tmp_path / "live"),
            ])
        assert code == 0
        out = capsys.readouterr().out
        assert "run_binance_ws_heatmap_live startup" in out
        assert "collector          = binance_websocket" in out
        assert "supabase           = configured" in out
        assert "super-secret-xyz" not in out


# ── LM53B: --use-env-config wiring ──────────────────────────────────────────

class TestUseEnvConfig:

    def test_default_behavior_unchanged_without_flag(self, tmp_path):
        """Without --use-env-config, symbols/timeframes use CLI defaults."""
        captured: dict = {}
        def _spy(*, symbols, timeframes, **kw):
            captured["symbols"] = list(symbols)
            captured["timeframes"] = list(timeframes)
            return {"writes": 0, "messages": 0, "per_symbol": {}}
        with patch.object(ws, "_default_ws_messages_with_reconnect",
                          return_value=iter([])), \
             patch.object(ws, "run_ws_collector", side_effect=_spy):
            code = ws.main([
                "--target", "live", "--samples", "1",
                "--live-dir", str(tmp_path / "live"),
            ])
        assert code == 0
        assert captured["symbols"] == ["BTCUSDT"]
        assert captured["timeframes"] == ["5m", "15m", "1h"]

    def test_use_env_config_reads_env(self, tmp_path, monkeypatch):
        """--use-env-config picks up WORKER_SYMBOLS and WORKER_TIMEFRAMES."""
        monkeypatch.setenv("WORKER_SYMBOLS", "HYPEUSDT,SOLUSDT")
        monkeypatch.setenv("WORKER_TIMEFRAMES", "15m")
        monkeypatch.setenv("WORKER_HISTORY_TARGET", "none")
        captured: dict = {}
        def _spy(*, symbols, timeframes, **kw):
            captured["symbols"] = list(symbols)
            captured["timeframes"] = list(timeframes)
            return {"writes": 0, "messages": 0, "per_symbol": {}}
        with patch.object(ws, "_default_ws_messages_with_reconnect",
                          return_value=iter([])), \
             patch.object(ws, "run_ws_collector", side_effect=_spy):
            code = ws.main([
                "--use-env-config",
                "--target", "live", "--samples", "1",
                "--live-dir", str(tmp_path / "live"),
            ])
        assert code == 0
        assert captured["symbols"] == ["HYPEUSDT", "SOLUSDT"]
        assert captured["timeframes"] == ["15m"]

    def test_explicit_cli_overrides_env(self, tmp_path, monkeypatch):
        """Explicit --symbols on CLI wins over WORKER_SYMBOLS env."""
        monkeypatch.setenv("WORKER_SYMBOLS", "HYPEUSDT")
        monkeypatch.setenv("WORKER_TIMEFRAMES", "15m")
        monkeypatch.setenv("WORKER_HISTORY_TARGET", "none")
        captured: dict = {}
        def _spy(*, symbols, timeframes, **kw):
            captured["symbols"] = list(symbols)
            captured["timeframes"] = list(timeframes)
            return {"writes": 0, "messages": 0, "per_symbol": {}}
        with patch.object(ws, "_default_ws_messages_with_reconnect",
                          return_value=iter([])), \
             patch.object(ws, "run_ws_collector", side_effect=_spy):
            code = ws.main([
                "--use-env-config",
                "--symbols", "BTCUSDT,ETHUSDT",
                "--timeframes", "15m",
                "--target", "live", "--samples", "1",
                "--live-dir", str(tmp_path / "live"),
            ])
        assert code == 0
        assert captured["symbols"] == ["BTCUSDT", "ETHUSDT"]
        assert captured["timeframes"] == ["15m"]

    def test_history_settings_mapped(self, tmp_path, monkeypatch):
        """--use-env-config maps WORKER_HISTORY_* and WORKER_MAX_* env vars."""
        monkeypatch.setenv("WORKER_HISTORY_TARGET", "supabase")
        monkeypatch.setenv("WORKER_HISTORY_INTERVAL", "30")
        monkeypatch.setenv("WORKER_MAX_CELLS", "150")
        monkeypatch.setenv("WORKER_MAX_WALLS", "25")
        monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "fake-key")
        captured: dict = {}
        def _spy(**kw):
            captured.update(kw)
            return {"writes": 0, "messages": 0, "per_symbol": {},
                    "history_writes": 0, "history_failures": 0,
                    "history_per_symbol": {}}
        with patch.object(ws, "_default_ws_messages_with_reconnect",
                          return_value=iter([])), \
             patch.object(ws, "run_ws_collector", side_effect=_spy):
            code = ws.main([
                "--use-env-config",
                "--target", "supabase", "--samples", "1",
                "--live-dir", str(tmp_path / "live"),
            ])
        assert code == 0
        assert captured["history_target"] == "supabase"
        assert captured["history_interval"] == 30.0
        assert captured["history_max_cells"] == 150
        assert captured["history_max_walls"] == 25

    def test_missing_env_uses_defaults(self, tmp_path, monkeypatch):
        """--use-env-config with no WORKER_* env vars falls back to config defaults."""
        for key in ["WORKER_SYMBOLS", "WORKER_TIMEFRAMES", "WORKER_EXCHANGE",
                     "WORKER_HISTORY_INTERVAL", "WORKER_MAX_CELLS", "WORKER_MAX_WALLS"]:
            monkeypatch.delenv(key, raising=False)
        # Override history target to none so test doesn't require Supabase config
        monkeypatch.setenv("WORKER_HISTORY_TARGET", "none")
        captured: dict = {}
        def _spy(*, symbols, timeframes, **kw):
            captured["symbols"] = list(symbols)
            captured["timeframes"] = list(timeframes)
            captured.update(kw)
            return {"writes": 0, "messages": 0, "per_symbol": {}}
        with patch.object(ws, "_default_ws_messages_with_reconnect",
                          return_value=iter([])), \
             patch.object(ws, "run_ws_collector", side_effect=_spy):
            code = ws.main([
                "--use-env-config",
                "--target", "live", "--samples", "1",
                "--live-dir", str(tmp_path / "live"),
            ])
        assert code == 0
        assert captured["symbols"] == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        assert captured["timeframes"] == ["5m"]


# ── LM53F: env-config precedence fix ────────────────────────────────────────

class TestEnvConfigPrecedence:

    def test_env_history_target_none_no_supabase_required(self, tmp_path, monkeypatch):
        """WORKER_HISTORY_TARGET=none + --use-env-config should not require SUPABASE_URL."""
        monkeypatch.setenv("WORKER_HISTORY_TARGET", "none")
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
        captured: dict = {}
        def _spy(**kw):
            captured.update(kw)
            return {"writes": 0, "messages": 0, "per_symbol": {}}
        with patch.object(ws, "_default_ws_messages_with_reconnect",
                          return_value=iter([])), \
             patch.object(ws, "run_ws_collector", side_effect=_spy):
            code = ws.main([
                "--use-env-config",
                "--target", "live", "--samples", "1",
                "--live-dir", str(tmp_path / "live"),
            ])
        assert code == 0
        assert captured["history_target"] == "none"

    def test_env_history_target_supabase_requires_config(self, tmp_path, monkeypatch, capsys):
        """WORKER_HISTORY_TARGET=supabase + --use-env-config requires SUPABASE_URL."""
        monkeypatch.setenv("WORKER_HISTORY_TARGET", "supabase")
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
        code = ws.main([
            "--use-env-config",
            "--target", "live", "--samples", "1",
            "--live-dir", str(tmp_path / "live"),
        ])
        assert code == 1
        assert "SUPABASE" in capsys.readouterr().err

    def test_explicit_cli_history_target_supabase_overrides_env_none(self, tmp_path, monkeypatch):
        """Explicit --history-target supabase wins over WORKER_HISTORY_TARGET=none."""
        monkeypatch.setenv("WORKER_HISTORY_TARGET", "none")
        monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "fake-key")
        captured: dict = {}
        def _spy(**kw):
            captured.update(kw)
            return {"writes": 0, "messages": 0, "per_symbol": {},
                    "history_writes": 0, "history_failures": 0,
                    "history_per_symbol": {}}
        with patch.object(ws, "_default_ws_messages_with_reconnect",
                          return_value=iter([])), \
             patch.object(ws, "run_ws_collector", side_effect=_spy):
            code = ws.main([
                "--use-env-config",
                "--history-target", "supabase",
                "--target", "supabase", "--samples", "1",
                "--live-dir", str(tmp_path / "live"),
            ])
        assert code == 0
        assert captured["history_target"] == "supabase"

    def test_explicit_cli_history_target_none_overrides_env_supabase(self, tmp_path, monkeypatch):
        """Explicit --history-target none wins over WORKER_HISTORY_TARGET=supabase."""
        monkeypatch.setenv("WORKER_HISTORY_TARGET", "supabase")
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
        captured: dict = {}
        def _spy(**kw):
            captured.update(kw)
            return {"writes": 0, "messages": 0, "per_symbol": {}}
        with patch.object(ws, "_default_ws_messages_with_reconnect",
                          return_value=iter([])), \
             patch.object(ws, "run_ws_collector", side_effect=_spy):
            code = ws.main([
                "--use-env-config",
                "--history-target", "none",
                "--target", "live", "--samples", "1",
                "--live-dir", str(tmp_path / "live"),
            ])
        assert code == 0
        assert captured["history_target"] == "none"

    def test_default_unchanged_without_use_env_config(self, tmp_path, monkeypatch):
        """Without --use-env-config, WORKER_* env vars are ignored."""
        monkeypatch.setenv("WORKER_HISTORY_TARGET", "supabase")
        monkeypatch.setenv("WORKER_SYMBOLS", "HYPEUSDT")
        captured: dict = {}
        def _spy(*, symbols, **kw):
            captured["symbols"] = list(symbols)
            captured.update(kw)
            return {"writes": 0, "messages": 0, "per_symbol": {}}
        with patch.object(ws, "_default_ws_messages_with_reconnect",
                          return_value=iter([])), \
             patch.object(ws, "run_ws_collector", side_effect=_spy):
            code = ws.main([
                "--target", "live", "--samples", "1",
                "--live-dir", str(tmp_path / "live"),
            ])
        assert code == 0
        assert captured["symbols"] == ["BTCUSDT"]
        assert captured["history_target"] == "none"


# ── LM53E: worker health heartbeat wiring ───────────────────────────────────

class TestWorkerHealthWiring:

    def test_heartbeat_flag_exists(self):
        args = ws.parse_args(["--heartbeat-interval", "30"])
        assert args.heartbeat_interval == 30.0

    def test_default_heartbeat_interval_is_60(self):
        args = ws.parse_args([])
        assert args.heartbeat_interval == 60.0

    def test_health_state_created(self, tmp_path):
        _, output_for = _output_factory(tmp_path)
        result = ws.run_ws_collector(
            symbol="BTCUSDT", timeframes=["5m"],
            write_interval=1.0, max_frames=10,
            target="live", supabase=None,
            output_for=output_for,
            message_iter=iter([_bt(100.0, 101.0)]),
            fetch_depth=lambda *a, **k: _mock_snapshot(),
            samples=1, forever=False, now=_Clock(step=0.5),
        )
        hs = result["health_state"]
        assert hs is not None
        assert "started_at" in hs
        assert "total_ticks" in hs
        assert isinstance(hs["symbols_seen"], set)

    def test_ok_tick_recorded(self, tmp_path):
        _, output_for = _output_factory(tmp_path)
        result = ws.run_ws_collector(
            symbol="BTCUSDT", timeframes=["5m"],
            write_interval=0.5, max_frames=10,
            target="live", supabase=None,
            output_for=output_for,
            message_iter=iter([_bt(100.0, 101.0)] * 10),
            fetch_depth=lambda *a, **k: _mock_snapshot(),
            samples=3, forever=False, now=_Clock(step=0.5),
        )
        hs = result["health_state"]
        assert hs["ok_ticks"] >= 3
        assert "BTCUSDT" in hs["symbols_seen"]

    def test_error_tick_recorded(self, tmp_path):
        _, output_for = _output_factory(tmp_path)
        sb_cfg = SupabaseConfig("https://example.supabase.co", "key")

        def _bad_upsert(*a, **k):
            raise RuntimeError("network fail")

        result = ws.run_ws_collector(
            symbol="BTCUSDT", timeframes=["5m"],
            write_interval=0.5, max_frames=10,
            target="supabase", supabase=sb_cfg,
            output_for=output_for,
            message_iter=iter([_bt(100.0, 101.0)] * 10),
            fetch_depth=lambda *a, **k: _mock_snapshot(),
            samples=2, forever=False, now=_Clock(step=0.5),
            upsert=_bad_upsert,
        )
        hs = result["health_state"]
        assert hs["error_ticks"] >= 1
        assert "network fail" in (hs["last_error"] or "")

    def test_heartbeat_payload_shape(self, tmp_path):
        from services.worker_health import build_worker_heartbeat
        _, output_for = _output_factory(tmp_path)
        result = ws.run_ws_collector(
            symbol="BTCUSDT", timeframes=["5m"],
            write_interval=0.5, max_frames=10,
            target="live", supabase=None,
            output_for=output_for,
            message_iter=iter([_bt(100.0, 101.0)] * 5),
            fetch_depth=lambda *a, **k: _mock_snapshot(),
            samples=2, forever=False, now=_Clock(step=0.5),
        )
        hb = build_worker_heartbeat(result["health_state"], now=100.0)
        assert "status" in hb
        assert "uptime_seconds" in hb
        assert "total_ticks" in hb
        assert "ok_ticks" in hb
        assert "error_ticks" in hb
        assert "last_error" in hb
        assert "symbols_seen" in hb
        assert "exchanges_seen" in hb
        assert isinstance(hb["symbols_seen"], list)
