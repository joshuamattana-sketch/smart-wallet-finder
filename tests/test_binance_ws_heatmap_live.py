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


def _mock_snapshot() -> dict:
    return {
        "symbol":         "BTCUSDT",
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
        assert out == {"bestBid": 100.0, "bestAsk": 101.0,
                       "bestBidQty": 1.0, "bestAskQty": 1.0}

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
