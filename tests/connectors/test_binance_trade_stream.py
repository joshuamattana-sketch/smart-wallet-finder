"""
tests/connectors/test_binance_trade_stream.py
----------------------------------------------
LM63B — Tests for the Binance Spot aggTrade collector.

All deterministic. No network. The real-network code path
(`_default_ws_messages_with_reconnect`) is never exercised here — we
always inject `message_iter`.
"""

from __future__ import annotations

import json

import pytest

from services.connectors.binance_trade_stream import (
    EXCHANGE_TAG,
    SOURCE_TYPE,
    build_binance_aggtrade_ws_url,
    is_valid_binance_symbol,
    iter_binance_aggtrades,
    normalize_agg_trade_to_whale_input,
    parse_agg_trade_message,
)
from services.whale_alert_engine import detect_whale_events


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _agg_trade(
    agg_id: int = 12345,
    symbol: str = "BTCUSDT",
    price: float = 67_000.0,
    quantity: float = 5.0,
    trade_ts_ms: int = 1_700_000_000_000,
    is_maker: bool = False,
) -> dict:
    """Build a single-stream Binance aggTrade JSON object."""
    return {
        "e": "aggTrade",
        "E": trade_ts_ms,
        "s": symbol,
        "a": agg_id,
        "p": str(price),
        "q": str(quantity),
        "f": 1,
        "l": 2,
        "T": trade_ts_ms,
        "m": is_maker,
        "M": True,
    }


def _combined(agg: dict) -> dict:
    """Wrap a single-stream payload in the combined-stream envelope."""
    return {"stream": f"{agg['s'].lower()}@aggTrade", "data": agg}


# ── URL builder ───────────────────────────────────────────────────────────────

class TestBuildUrl:
    def test_single_symbol_uses_ws_endpoint(self):
        url = build_binance_aggtrade_ws_url(["BTCUSDT"])
        assert url == "wss://stream.binance.com:9443/ws/btcusdt@aggTrade"

    def test_multi_symbol_uses_combined_endpoint(self):
        url = build_binance_aggtrade_ws_url(["BTCUSDT", "ETHUSDT", "SOLUSDT"])
        assert url.startswith("wss://stream.binance.com:9443/stream?streams=")
        # Each symbol should appear lower-cased with the @aggTrade suffix.
        assert "btcusdt@aggTrade" in url
        assert "ethusdt@aggTrade" in url
        assert "solusdt@aggTrade" in url
        # Streams are joined with '/'.
        assert url.count("/") >= 5  # protocol slashes + stream separators

    def test_normalises_case_and_whitespace(self):
        url = build_binance_aggtrade_ws_url([" btcusdt ", "EthUsdt"])
        assert "btcusdt@aggTrade" in url
        assert "ethusdt@aggTrade" in url

    def test_dedupes_symbols(self):
        url = build_binance_aggtrade_ws_url(["BTCUSDT", "BTCUSDT", "BTCUSDT"])
        # Single after dedupe → single endpoint.
        assert url == "wss://stream.binance.com:9443/ws/btcusdt@aggTrade"

    def test_drops_invalid_symbols_silently(self):
        url = build_binance_aggtrade_ws_url(["BTCUSDT", "BTC-USDT", "??"])
        # Only BTCUSDT survives → single endpoint.
        assert url == "wss://stream.binance.com:9443/ws/btcusdt@aggTrade"

    def test_raises_when_no_valid_symbols(self):
        with pytest.raises(ValueError):
            build_binance_aggtrade_ws_url([])
        with pytest.raises(ValueError):
            build_binance_aggtrade_ws_url(["???", "", None])  # type: ignore[list-item]


# ── Symbol validator ──────────────────────────────────────────────────────────

class TestIsValidSymbol:
    def test_accepts_typical_binance_symbols(self):
        for s in ["BTCUSDT", "ETHUSDT", "SOLUSDT", "LINKUSDT", "DOGEUSDT", "BNBUSDT"]:
            assert is_valid_binance_symbol(s)

    def test_normalises_case(self):
        assert is_valid_binance_symbol("btcusdt")
        assert is_valid_binance_symbol("  BtCUsdT ")

    def test_rejects_garbage(self):
        for bad in ["", "  ", "BTC-USDT", "BTC/USDT", "x", None, 123, {"sym": "BTC"}]:
            assert not is_valid_binance_symbol(bad)  # type: ignore[arg-type]


# ── Message parsing ───────────────────────────────────────────────────────────

class TestParseAggTrade:
    def test_parses_single_stream_dict(self):
        msg = _agg_trade(agg_id=99, price=67_500.5, quantity=2.0)
        out = parse_agg_trade_message(msg)
        assert out == {
            "agg_id": 99,
            "symbol": "BTCUSDT",
            "price": 67_500.5,
            "quantity": 2.0,
            "trade_ts_ms": 1_700_000_000_000,
            "is_maker": False,
        }

    def test_parses_combined_stream_wrapper(self):
        wrapped = _combined(_agg_trade(agg_id=77, symbol="ethusdt"))
        out = parse_agg_trade_message(wrapped)
        assert out is not None
        assert out["agg_id"] == 77
        assert out["symbol"] == "ETHUSDT"   # normalized to upper

    def test_parses_raw_json_string(self):
        raw = json.dumps(_agg_trade(agg_id=42))
        out = parse_agg_trade_message(raw)
        assert out is not None
        assert out["agg_id"] == 42

    def test_parses_raw_json_bytes(self):
        raw = json.dumps(_agg_trade(agg_id=43)).encode("utf-8")
        out = parse_agg_trade_message(raw)
        assert out is not None
        assert out["agg_id"] == 43

    def test_returns_none_on_invalid_json(self):
        assert parse_agg_trade_message("{not valid json") is None

    def test_returns_none_on_empty_inputs(self):
        assert parse_agg_trade_message(None) is None
        assert parse_agg_trade_message("") is None
        assert parse_agg_trade_message(b"") is None
        assert parse_agg_trade_message({}) is None

    def test_returns_none_on_missing_required_fields(self):
        bare = {"e": "aggTrade", "s": "BTCUSDT"}  # missing a/p/q
        assert parse_agg_trade_message(bare) is None
        assert parse_agg_trade_message({"a": 1, "p": "1", "q": "1"}) is None  # no s

    def test_returns_none_on_non_numeric_price_or_qty(self):
        bad_price = _agg_trade()
        bad_price["p"] = "not_a_number"
        assert parse_agg_trade_message(bad_price) is None

        bad_qty = _agg_trade()
        bad_qty["q"] = None  # type: ignore[assignment]
        assert parse_agg_trade_message(bad_qty) is None

    def test_returns_none_on_zero_or_negative_price_qty(self):
        zero_price = _agg_trade(); zero_price["p"] = "0"
        assert parse_agg_trade_message(zero_price) is None
        neg_qty = _agg_trade(); neg_qty["q"] = "-1"
        assert parse_agg_trade_message(neg_qty) is None

    def test_falls_back_to_event_time_when_T_missing(self):
        msg = _agg_trade(trade_ts_ms=1_700_000_000_111)
        del msg["T"]   # remove trade time, keep event time E
        out = parse_agg_trade_message(msg)
        assert out is not None
        assert out["trade_ts_ms"] == 1_700_000_000_111

    def test_falls_back_to_now_when_T_and_E_missing(self):
        msg = _agg_trade()
        msg.pop("T", None)
        msg.pop("E", None)
        out = parse_agg_trade_message(msg)
        assert out is not None
        assert out["trade_ts_ms"] > 0

    def test_returns_none_on_non_dict_non_string(self):
        assert parse_agg_trade_message(12345) is None
        assert parse_agg_trade_message([1, 2, 3]) is None


# ── Normalize to whale-engine v2 input ───────────────────────────────────────

class TestNormalize:
    def test_basic_shape(self):
        parsed = parse_agg_trade_message(_agg_trade(agg_id=1, price=2.0, quantity=3.0))
        assert parsed is not None
        out = normalize_agg_trade_to_whale_input(parsed)

        expected_keys = {
            "source_type", "symbol", "chain", "exchange", "side",
            "amount", "price", "notional_usd", "wallet", "tx_hash",
            "event_ts", "metadata",
        }
        assert expected_keys.issubset(set(out))
        assert out["source_type"] == SOURCE_TYPE == "exchange_trade"
        assert out["exchange"] == EXCHANGE_TAG == "binance_spot"
        assert out["chain"] == ""

    def test_side_buy_when_buyer_is_not_maker(self):
        parsed = parse_agg_trade_message(_agg_trade(is_maker=False))
        assert parsed is not None
        out = normalize_agg_trade_to_whale_input(parsed)
        assert out["side"] == "buy"
        assert out["metadata"]["is_maker"] is False

    def test_side_sell_when_buyer_is_maker(self):
        parsed = parse_agg_trade_message(_agg_trade(is_maker=True))
        assert parsed is not None
        out = normalize_agg_trade_to_whale_input(parsed)
        assert out["side"] == "sell"
        assert out["metadata"]["is_maker"] is True

    def test_notional_math(self):
        parsed = parse_agg_trade_message(_agg_trade(price=1234.5, quantity=2.0))
        assert parsed is not None
        out = normalize_agg_trade_to_whale_input(parsed)
        assert out["notional_usd"] == pytest.approx(1234.5 * 2.0)
        assert out["amount"] == 2.0
        assert out["price"] == 1234.5

    def test_deterministic_wallet_and_tx_hash(self):
        agg = _agg_trade(agg_id=98765, symbol="ETHUSDT")
        parsed = parse_agg_trade_message(agg)
        assert parsed is not None
        out1 = normalize_agg_trade_to_whale_input(parsed)
        out2 = normalize_agg_trade_to_whale_input(parsed)
        assert out1["wallet"] == out2["wallet"] == "agg:98765"
        assert out1["tx_hash"] == out2["tx_hash"] == "agg:ETHUSDT:98765"

    def test_event_ts_is_iso8601(self):
        parsed = parse_agg_trade_message(_agg_trade(trade_ts_ms=1_700_000_000_000))
        assert parsed is not None
        out = normalize_agg_trade_to_whale_input(parsed)
        # Round-trip via fromisoformat. Python supports the +00:00 offset.
        from datetime import datetime
        parsed_back = datetime.fromisoformat(out["event_ts"])
        assert parsed_back.year >= 2023

    def test_metadata_carries_agg_id_and_source(self):
        parsed = parse_agg_trade_message(_agg_trade(agg_id=42))
        assert parsed is not None
        out = normalize_agg_trade_to_whale_input(parsed)
        assert out["metadata"]["agg_trade_id"] == 42
        assert out["metadata"]["source"] == "binance_aggtrade"
        assert "trade_ts_ms" in out["metadata"]
        assert "is_maker" in out["metadata"]

    def test_type_error_on_non_dict(self):
        with pytest.raises(TypeError):
            normalize_agg_trade_to_whale_input("not a dict")  # type: ignore[arg-type]

    def test_key_error_on_missing_field(self):
        with pytest.raises(KeyError):
            normalize_agg_trade_to_whale_input({"agg_id": 1})


# ── End-to-end via iter_binance_aggtrades ─────────────────────────────────────

class TestIterator:
    def test_yields_normalized_whale_inputs(self):
        msgs = [
            json.dumps(_agg_trade(agg_id=1, symbol="BTCUSDT", price=70_000, quantity=4.0)),
            json.dumps(_agg_trade(agg_id=2, symbol="BTCUSDT", price=70_010, quantity=0.1, is_maker=True)),
        ]
        out = list(iter_binance_aggtrades(["BTCUSDT"], message_iter=iter(msgs)))
        assert len(out) == 2
        assert out[0]["side"] == "buy"
        assert out[0]["notional_usd"] == pytest.approx(280_000.0)
        assert out[1]["side"] == "sell"

    def test_ignores_none_idle_ticks(self):
        msgs = [None, json.dumps(_agg_trade()), None]
        out = list(iter_binance_aggtrades(["BTCUSDT"], message_iter=iter(msgs)))
        assert len(out) == 1

    def test_ignores_malformed_messages(self):
        msgs = [
            "{bad json",
            {},
            json.dumps({"foo": "bar"}),
            json.dumps(_agg_trade(agg_id=7)),
        ]
        out = list(iter_binance_aggtrades(["BTCUSDT"], message_iter=iter(msgs)))
        assert len(out) == 1
        assert out[0]["wallet"] == "agg:7"

    def test_filters_unrequested_symbols_by_default(self):
        msgs = [
            json.dumps(_agg_trade(symbol="BTCUSDT", agg_id=1)),
            json.dumps(_agg_trade(symbol="ETHUSDT", agg_id=2)),
        ]
        out = list(iter_binance_aggtrades(["BTCUSDT"], message_iter=iter(msgs)))
        symbols = [r["symbol"] for r in out]
        assert symbols == ["BTCUSDT"]

    def test_symbol_filter_off_passes_through(self):
        msgs = [
            json.dumps(_agg_trade(symbol="ETHUSDT", agg_id=2)),
        ]
        out = list(iter_binance_aggtrades(
            ["BTCUSDT"], message_iter=iter(msgs), symbol_filter=False,
        ))
        assert len(out) == 1
        assert out[0]["symbol"] == "ETHUSDT"

    def test_real_network_path_not_touched_when_iter_provided(self):
        # If this test ever opens a socket, it would fail in offline CI.
        msgs = [json.dumps(_agg_trade())]
        list(iter_binance_aggtrades(["BTCUSDT"], message_iter=iter(msgs)))

    def test_raises_on_no_valid_symbols(self):
        with pytest.raises(ValueError):
            list(iter_binance_aggtrades(["BTC-USDT"], message_iter=iter([])))


# ── Round-trip into detect_whale_events (the consumer) ───────────────────────

class TestWhaleEngineRoundTrip:
    def test_large_trade_passes_threshold(self):
        # $1.4M notional — well above the $250k default threshold.
        parsed = parse_agg_trade_message(
            _agg_trade(agg_id=1001, symbol="BTCUSDT", price=70_000, quantity=20.0)
        )
        assert parsed is not None
        item = normalize_agg_trade_to_whale_input(parsed)
        events = detect_whale_events([item], options={"min_notional_usd": 250_000})

        assert len(events) == 1
        ev = events[0]
        assert ev["source_type"] == "exchange_trade"
        assert ev["symbol"] == "BTCUSDT"
        assert ev["exchange"] == "binance_spot"
        assert ev["notional_usd"] == pytest.approx(1_400_000.0)
        assert ev["side"] == "buy"
        assert ev["severity"] in ("notable", "high", "extreme")
        # Deterministic id derived from the underlying agg_id-carrying tx_hash.
        assert isinstance(ev["whale_event_id"], str)
        assert len(ev["whale_event_id"]) == 16

    def test_small_trade_filtered_out(self):
        parsed = parse_agg_trade_message(
            _agg_trade(agg_id=1, symbol="BTCUSDT", price=70_000, quantity=0.001)
        )
        assert parsed is not None
        item = normalize_agg_trade_to_whale_input(parsed)
        events = detect_whale_events([item], options={"min_notional_usd": 250_000})
        assert events == []

    def test_event_id_stable_across_runs(self):
        # Two identical agg trades produce the same whale_event_id (idempotent).
        item = normalize_agg_trade_to_whale_input(
            parse_agg_trade_message(_agg_trade(agg_id=555, symbol="BTCUSDT",
                                               price=70_000, quantity=5.0))  # type: ignore[arg-type]
        )
        e1 = detect_whale_events([item], options={"min_notional_usd": 250_000})
        e2 = detect_whale_events([item], options={"min_notional_usd": 250_000})
        assert e1[0]["whale_event_id"] == e2[0]["whale_event_id"]
