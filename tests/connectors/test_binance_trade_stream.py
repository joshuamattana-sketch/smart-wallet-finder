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


# ── LM63C: smoke runner pipeline (aggTrade → whale → filter → Discord) ───────

# Imported lazily inside the test class so importing this test module
# never executes the smoke runner's top-level code.

def _build_args(**overrides) -> "object":
    """
    Return an argparse.Namespace-like object with safe defaults that mirror
    the LM63D CLI: per-symbol thresholds on, no explicit overrides.
    """
    from scripts.run_binance_trade_stream_smoke import (
        DEFAULT_MAX_EVENTS,
        DEFAULT_SYMBOLS,
    )
    import argparse
    ns = argparse.Namespace(
        symbols=DEFAULT_SYMBOLS,
        min_notional=None,            # per-symbol thresholds apply unless overridden
        max_events=DEFAULT_MAX_EVENTS,
        min_confidence=None,          # per-symbol thresholds apply unless overridden
        use_symbol_thresholds=True,
        send_discord=False,
        discord_webhook_url="",
        print_payload=False,
        journal_path="",              # LM63E — off by default
        target="stdout",              # LM63H — no Supabase by default
        forever=False,                # LM63J — worker mode off
        heartbeat_interval=0.0,       # LM63J — quiet in tests by default
        use_env_config=False,         # LM63J — env reader off in tests
        market="spot",                # LM64B — spot default
    )
    for k, v in overrides.items():
        setattr(ns, k, v)
    return ns


class _FakeSender:
    """Stand-in for `send_discord_webhook` — records every call."""

    def __init__(self, ok: bool = True):
        self.ok = ok
        self.calls: list[dict] = []

    def __call__(self, payload, webhook_url=""):
        self.calls.append({"payload": payload, "webhook_url": webhook_url})
        return {"ok": self.ok, "status": 204 if self.ok else 500}


class TestSmokeRunnerPipeline:
    def _run(self, *, msgs, sender=None, **arg_overrides):
        """Run the pipeline once with captured stdout/stderr lines."""
        from scripts.run_binance_trade_stream_smoke import run_pipeline
        args = _build_args(**arg_overrides)
        out_lines: list[str] = []
        err_lines: list[str] = []
        counters = run_pipeline(
            args=args,
            message_iter=iter(msgs),
            sender=sender or _FakeSender(),
            print_fn=out_lines.append,
            err_fn=err_lines.append,
        )
        return counters, out_lines, err_lines

    def test_default_does_not_send_discord(self):
        """No --send-discord → sender must never be called even for valid events."""
        sender = _FakeSender()
        msgs = [json.dumps(_agg_trade(
            agg_id=1, symbol="BTCUSDT", price=70_000, quantity=20.0
        ))]  # $1.4M, extreme
        counters, out, _err = self._run(
            msgs=msgs, sender=sender,
            symbols="BTCUSDT", min_notional=250_000,
        )
        assert counters["events"] == 1
        assert counters["sendable"] >= 1
        assert counters["sent"] == 0
        assert sender.calls == []
        # Human-readable line printed for the event.
        assert any("BTCUSDT" in line for line in out)

    def test_send_flag_calls_mocked_webhook_sender(self):
        sender = _FakeSender()
        msgs = [
            json.dumps(_agg_trade(agg_id=1, symbol="BTCUSDT",
                                   price=70_000, quantity=20.0)),  # $1.4M
            json.dumps(_agg_trade(agg_id=2, symbol="BTCUSDT",
                                   price=70_001, quantity=15.0)),  # $1.05M
        ]
        counters, _out, _err = self._run(
            msgs=msgs, sender=sender,
            symbols="BTCUSDT", min_notional=250_000,
            send_discord=True, discord_webhook_url="https://example.test/webhook",
        )
        assert counters["sent"] == 2
        assert len(sender.calls) == 2
        for call in sender.calls:
            assert call["webhook_url"] == "https://example.test/webhook"
            assert isinstance(call["payload"], dict)
            # Discord payload shape: must carry embeds.
            assert "embeds" in call["payload"]

    def test_missing_webhook_safe_no_crash(self):
        """--send-discord without a URL must not crash; must not call sender."""
        sender = _FakeSender()
        msgs = [json.dumps(_agg_trade(agg_id=1, symbol="BTCUSDT",
                                       price=70_000, quantity=20.0))]
        counters, out, err = self._run(
            msgs=msgs, sender=sender,
            symbols="BTCUSDT",
            send_discord=True, discord_webhook_url="",
        )
        assert counters["stopped_reason"] == "missing_webhook"
        assert counters["events"] == 0     # exited before processing
        assert counters["sent"] == 0
        assert sender.calls == []
        # An explanatory error line should have been emitted to err_fn.
        assert any("missing" in line.lower() or "webhook" in line.lower() for line in err)

    def test_max_events_respected(self):
        """Loop stops at --max-events regardless of how many input msgs remain."""
        msgs = [
            json.dumps(_agg_trade(agg_id=i, symbol="BTCUSDT",
                                   price=70_000, quantity=20.0))
            for i in range(1, 11)
        ]
        counters, _out, _err = self._run(
            msgs=msgs,
            symbols="BTCUSDT", min_notional=250_000, max_events=3,
        )
        assert counters["events"] == 3
        assert counters["stopped_reason"] == "max_events"

    def test_below_min_notional_skipped(self):
        # 70_000 × 0.001 = $70 → far below the 250k floor.
        msgs = [
            json.dumps(_agg_trade(agg_id=1, symbol="BTCUSDT",
                                   price=70_000, quantity=0.001)),
            json.dumps(_agg_trade(agg_id=2, symbol="BTCUSDT",
                                   price=70_000, quantity=0.002)),
        ]
        counters, out, _err = self._run(
            msgs=msgs, symbols="BTCUSDT", min_notional=250_000,
        )
        assert counters["events"] == 0
        assert counters["below_threshold"] == 2
        # Nothing should have been printed to the readable stream.
        assert out == []

    def test_filter_blocks_low_confidence(self):
        """
        Set --min-confidence above the engine's emitted confidence (~0.8 when
        tx_hash is present). The filter result still passes for an extreme
        whale, but the smoke runner must mark it blocked and skip the sender.
        """
        sender = _FakeSender()
        msgs = [json.dumps(_agg_trade(agg_id=1, symbol="BTCUSDT",
                                       price=70_000, quantity=20.0))]  # $1.4M, extreme
        counters, out, _err = self._run(
            msgs=msgs, sender=sender,
            symbols="BTCUSDT", min_notional=250_000,
            min_confidence=0.95,
            send_discord=True, discord_webhook_url="https://example.test/webhook",
        )
        assert counters["events"] == 1
        assert counters["blocked_low_confidence"] == 1
        assert counters["sendable"] == 0
        assert counters["sent"] == 0
        assert sender.calls == []
        # The readable line should mark the block reason.
        assert any("--min-confidence" in line for line in out)

    def test_print_payload_outputs_json(self):
        sender = _FakeSender()
        msgs = [json.dumps(_agg_trade(agg_id=1, symbol="BTCUSDT",
                                       price=70_000, quantity=20.0))]
        counters, out, _err = self._run(
            msgs=msgs, sender=sender,
            symbols="BTCUSDT", min_notional=250_000,
            print_payload=True,
        )
        assert counters["events"] == 1
        # One human-readable line + one JSON payload line.
        json_lines = [line for line in out if line.startswith("{")]
        assert len(json_lines) == 1
        payload = json.loads(json_lines[0])
        assert "embeds" in payload

    def test_invalid_symbols_safe_exit(self):
        sender = _FakeSender()
        counters, _out, err = self._run(
            msgs=[], sender=sender,
            symbols="BTC-USDT",   # invalid Binance shape
        )
        assert counters["stopped_reason"] == "no_valid_symbols"
        assert counters["events"] == 0
        assert sender.calls == []
        assert any("invalid" in line.lower() or "no valid" in line.lower() for line in err)

    def test_bad_min_confidence_safe_exit(self):
        counters, _out, err = self._run(
            msgs=[], symbols="BTCUSDT", min_confidence=1.5,
        )
        assert counters["stopped_reason"] == "bad_min_confidence"
        assert any("--min-confidence" in line for line in err)

    def test_negative_min_notional_safe_exit(self):
        counters, _out, err = self._run(
            msgs=[], symbols="BTCUSDT", min_notional=-1.0,
        )
        assert counters["stopped_reason"] == "bad_min_notional"
        assert any("--min-notional" in line for line in err)

    def test_sender_failure_counted_not_raised(self):
        sender = _FakeSender(ok=False)
        msgs = [json.dumps(_agg_trade(agg_id=1, symbol="BTCUSDT",
                                       price=70_000, quantity=20.0))]
        counters, _out, _err = self._run(
            msgs=msgs, sender=sender,
            symbols="BTCUSDT", min_notional=250_000,
            send_discord=True, discord_webhook_url="https://example.test/webhook",
        )
        assert counters["sendable"] == 1
        assert counters["sent"] == 0
        assert counters["send_failures"] == 1


# ── LM63D: per-symbol thresholds wired into the smoke runner ─────────────────

class TestSymbolThresholdsInSmokeRunner:
    def _run(self, *, msgs, **arg_overrides):
        from scripts.run_binance_trade_stream_smoke import run_pipeline
        args = _build_args(**arg_overrides)
        out_lines: list[str] = []
        err_lines: list[str] = []
        counters = run_pipeline(
            args=args,
            message_iter=iter(msgs),
            sender=_FakeSender(),
            print_fn=out_lines.append,
            err_fn=err_lines.append,
        )
        return counters, out_lines, err_lines

    def test_smoke_uses_per_symbol_threshold_passes_sol(self):
        """
        $60k SOL fill clears SOLUSDT's $50k preset min — should be detected.
        """
        msgs = [json.dumps(_agg_trade(
            agg_id=1, symbol="SOLUSDT", price=150.0, quantity=400.0,  # $60k
        ))]
        counters, out, _err = self._run(
            msgs=msgs, symbols="SOLUSDT",  # use_symbol_thresholds=True by default
        )
        assert counters["events"] == 1
        assert counters["below_threshold"] == 0
        assert any("SOLUSDT" in line for line in out)

    def test_smoke_uses_per_symbol_threshold_filters_btc(self):
        """
        Same $60k notional, but on BTCUSDT (preset min $250k) → skipped.
        """
        msgs = [json.dumps(_agg_trade(
            agg_id=1, symbol="BTCUSDT", price=60_000.0, quantity=1.0,  # $60k
        ))]
        counters, out, _err = self._run(
            msgs=msgs, symbols="BTCUSDT",
        )
        assert counters["events"] == 0
        assert counters["below_threshold"] == 1
        assert out == []

    def test_smoke_mixed_symbol_stream_applies_per_symbol_floors(self):
        """
        Same notional ($60k) on a mixed BTC/SOL stream: SOL passes, BTC skipped.
        """
        msgs = [
            json.dumps(_agg_trade(agg_id=1, symbol="SOLUSDT",
                                   price=150.0, quantity=400.0)),   # $60k → pass
            json.dumps(_agg_trade(agg_id=2, symbol="BTCUSDT",
                                   price=60_000.0, quantity=1.0)),   # $60k → skip
        ]
        counters, out, _err = self._run(
            msgs=msgs, symbols="BTCUSDT,SOLUSDT",
        )
        assert counters["events"] == 1
        assert counters["below_threshold"] == 1
        # Only the SOL event line should appear.
        assert sum("SOLUSDT" in line for line in out) == 1
        assert not any("BTCUSDT" in line for line in out)

    def test_explicit_min_notional_overrides_symbol_threshold(self):
        """
        With explicit --min-notional=10000, a $20k BTC fill should be
        detected even though the BTC preset floor is $250k.
        """
        msgs = [json.dumps(_agg_trade(
            agg_id=1, symbol="BTCUSDT", price=60_000.0, quantity=20.0 / 60.0,  # $20k
        ))]
        counters, out, _err = self._run(
            msgs=msgs, symbols="BTCUSDT", min_notional=10_000.0,
        )
        assert counters["events"] == 1
        assert counters["below_threshold"] == 0
        assert any("BTCUSDT" in line for line in out)

    def test_no_use_symbol_thresholds_falls_back_to_global_default(self):
        """
        With --no-use-symbol-thresholds, the global $250k default applies
        to every symbol — so a $60k SOL fill should be skipped.
        """
        msgs = [json.dumps(_agg_trade(
            agg_id=1, symbol="SOLUSDT", price=150.0, quantity=400.0,  # $60k
        ))]
        counters, _out, _err = self._run(
            msgs=msgs, symbols="SOLUSDT", use_symbol_thresholds=False,
        )
        assert counters["events"] == 0
        assert counters["below_threshold"] == 1

    def test_explicit_min_notional_overrides_even_when_thresholds_off(self):
        """
        Even with --no-use-symbol-thresholds, an explicit --min-notional
        still wins over the global default.
        """
        msgs = [json.dumps(_agg_trade(
            agg_id=1, symbol="SOLUSDT", price=150.0, quantity=400.0,  # $60k
        ))]
        counters, _out, _err = self._run(
            msgs=msgs, symbols="SOLUSDT",
            use_symbol_thresholds=False, min_notional=10_000.0,
        )
        assert counters["events"] == 1
        assert counters["below_threshold"] == 0

    def test_min_confidence_resolves_per_symbol_by_default(self):
        """
        Per-symbol preset is 0.6 for BTC; engine emits 0.8 for our tx_hash-bearing
        events → an extreme whale on BTC should sail through the filter.
        """
        msgs = [json.dumps(_agg_trade(
            agg_id=1, symbol="BTCUSDT", price=70_000.0, quantity=40.0,  # $2.8M
        ))]
        counters, _out, _err = self._run(
            msgs=msgs, symbols="BTCUSDT",
        )
        assert counters["events"] == 1
        assert counters["sendable"] == 1
        assert counters["blocked_low_confidence"] == 0

    def test_explicit_min_confidence_overrides_per_symbol(self):
        """
        --min-confidence 0.95 must override per-symbol presets and block the
        otherwise-sendable extreme whale.
        """
        msgs = [json.dumps(_agg_trade(
            agg_id=1, symbol="BTCUSDT", price=70_000.0, quantity=40.0,  # $2.8M
        ))]
        counters, out, _err = self._run(
            msgs=msgs, symbols="BTCUSDT", min_confidence=0.95,
        )
        assert counters["events"] == 1
        assert counters["sendable"] == 0
        assert counters["blocked_low_confidence"] == 1
        assert any("--min-confidence" in line for line in out)


# ── LM63E: smoke runner writes the local whale event journal ─────────────────

class TestSmokeRunnerJournal:
    def _run(self, *, msgs, sender=None, **arg_overrides):
        from scripts.run_binance_trade_stream_smoke import run_pipeline
        args = _build_args(**arg_overrides)
        out_lines: list[str] = []
        err_lines: list[str] = []
        counters = run_pipeline(
            args=args,
            message_iter=iter(msgs),
            sender=sender or _FakeSender(),
            print_fn=out_lines.append,
            err_fn=err_lines.append,
        )
        return counters, out_lines, err_lines

    def test_default_does_not_write_journal(self, tmp_path):
        msgs = [json.dumps(_agg_trade(
            agg_id=1, symbol="BTCUSDT", price=70_000, quantity=20.0,  # $1.4M
        ))]
        # Reserve a path but don't pass it. After the run, no file at that path.
        unused = tmp_path / "whales.jsonl"
        counters, _out, _err = self._run(
            msgs=msgs, symbols="BTCUSDT", min_notional=250_000,
        )
        assert counters["events"] == 1
        assert counters["journaled"] == 0
        assert not unused.exists()

    def test_writes_one_row_per_event_when_path_set(self, tmp_path):
        from services.whale_event_journal import read_whale_event_journal

        path = tmp_path / "whales.jsonl"
        msgs = [
            json.dumps(_agg_trade(agg_id=1, symbol="BTCUSDT",
                                   price=70_000, quantity=20.0)),   # $1.4M extreme
            json.dumps(_agg_trade(agg_id=2, symbol="BTCUSDT",
                                   price=70_001, quantity=15.0)),   # $1.05M extreme
        ]
        counters, _out, _err = self._run(
            msgs=msgs, symbols="BTCUSDT", min_notional=250_000,
            journal_path=str(path),
        )
        assert counters["events"] == 2
        assert counters["journaled"] == 2
        assert counters["journal_failures"] == 0
        assert path.exists()

        rows = read_whale_event_journal(path)
        assert len(rows) == 2
        for row in rows:
            assert set(row) == {"event", "meta", "written_at"}
            assert "whale_event_id" in row["event"]
            meta = row["meta"]
            assert isinstance(meta, dict)
            assert "should_send" in meta
            assert "filter_reason" in meta

    def test_journal_meta_includes_send_result_when_sent(self, tmp_path):
        from services.whale_event_journal import read_whale_event_journal

        path = tmp_path / "whales.jsonl"
        sender = _FakeSender()
        msgs = [json.dumps(_agg_trade(
            agg_id=1, symbol="BTCUSDT", price=70_000, quantity=20.0,
        ))]
        counters, _out, _err = self._run(
            msgs=msgs, sender=sender,
            symbols="BTCUSDT", min_notional=250_000,
            send_discord=True, discord_webhook_url="https://example.test/webhook",
            journal_path=str(path),
        )
        assert counters["sent"] == 1
        assert counters["journaled"] == 1

        rows = read_whale_event_journal(path)
        assert len(rows) == 1
        meta = rows[0]["meta"]
        assert meta["should_send"] is True
        assert meta.get("sent_attempted") is True
        assert isinstance(meta.get("send_result"), dict)
        assert meta["send_result"].get("ok") is True

    def test_journal_includes_low_confidence_block_meta(self, tmp_path):
        from services.whale_event_journal import read_whale_event_journal

        path = tmp_path / "whales.jsonl"
        msgs = [json.dumps(_agg_trade(
            agg_id=1, symbol="BTCUSDT", price=70_000, quantity=20.0,
        ))]
        counters, _out, _err = self._run(
            msgs=msgs, symbols="BTCUSDT", min_notional=250_000,
            min_confidence=0.99,        # blocks the extreme whale
            journal_path=str(path),
        )
        assert counters["events"] == 1
        assert counters["sendable"] == 0
        assert counters["journaled"] == 1

        rows = read_whale_event_journal(path)
        assert len(rows) == 1
        meta = rows[0]["meta"]
        # should_send (filter result) may still be True for an extreme severity
        # whale, but the runner records that we blocked it.
        assert meta["blocked_low_conf"] is True
        assert "send_result" not in meta   # we never attempted a send

    def test_below_threshold_trades_not_journaled(self, tmp_path):
        path = tmp_path / "whales.jsonl"
        msgs = [json.dumps(_agg_trade(
            agg_id=1, symbol="BTCUSDT", price=70_000, quantity=0.001,
        ))]
        counters, _out, _err = self._run(
            msgs=msgs, symbols="BTCUSDT", min_notional=250_000,
            journal_path=str(path),
        )
        assert counters["events"] == 0
        assert counters["journaled"] == 0
        assert not path.exists()

    def test_journal_returns_newest_first(self, tmp_path):
        from services.whale_event_journal import read_whale_event_journal

        path = tmp_path / "whales.jsonl"
        msgs = [
            json.dumps(_agg_trade(agg_id=1, symbol="BTCUSDT",
                                   price=70_000, quantity=20.0)),
            json.dumps(_agg_trade(agg_id=2, symbol="BTCUSDT",
                                   price=70_000, quantity=20.0)),
            json.dumps(_agg_trade(agg_id=3, symbol="BTCUSDT",
                                   price=70_000, quantity=20.0)),
        ]
        self._run(
            msgs=msgs, symbols="BTCUSDT", min_notional=250_000,
            journal_path=str(path),
        )
        rows = read_whale_event_journal(path)
        agg_ids = [r["event"]["metadata"]["agg_trade_id"] for r in rows]
        assert agg_ids == [3, 2, 1]


# ── LM63H: smoke runner wires --target supabase ──────────────────────────────

class _FakeSupabaseWriter:
    """Records every call. Default behavior returns {"ok": True}."""

    def __init__(self, result=None):
        self.calls: list[dict] = []
        self._result = result or {"ok": True}

    def __call__(self, event, *, meta=None, **kwargs):
        self.calls.append({"event": event, "meta": meta, "kwargs": kwargs})
        if callable(self._result):
            return self._result(event, meta=meta)
        return self._result


_VALID_SUPABASE_ENV = {
    "SUPABASE_URL":              "https://test.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "test-service-role-key",
}


class TestSmokeRunnerSupabaseWiring:
    def _run(self, *, msgs, supabase_writer=None, env=None, **arg_overrides):
        from scripts.run_binance_trade_stream_smoke import run_pipeline
        args = _build_args(**arg_overrides)
        out_lines: list[str] = []
        err_lines: list[str] = []
        counters = run_pipeline(
            args=args,
            message_iter=iter(msgs),
            sender=_FakeSender(),
            supabase_writer=supabase_writer or _FakeSupabaseWriter(),
            print_fn=out_lines.append,
            err_fn=err_lines.append,
            env=env if env is not None else dict(_VALID_SUPABASE_ENV),
        )
        return counters, out_lines, err_lines

    def test_default_target_does_not_write_supabase(self):
        writer = _FakeSupabaseWriter()
        msgs = [json.dumps(_agg_trade(
            agg_id=1, symbol="BTCUSDT", price=70_000, quantity=20.0,
        ))]
        counters, _out, _err = self._run(
            msgs=msgs, supabase_writer=writer,
            symbols="BTCUSDT", min_notional=250_000,
            # target defaults to 'stdout'
        )
        assert counters["events"] == 1
        assert counters["supabase_writes"] == 0
        assert counters["supabase_failures"] == 0
        assert writer.calls == []

    def test_target_supabase_writes_each_event(self):
        writer = _FakeSupabaseWriter()
        msgs = [
            json.dumps(_agg_trade(agg_id=1, symbol="BTCUSDT",
                                   price=70_000, quantity=20.0)),    # $1.4M
            json.dumps(_agg_trade(agg_id=2, symbol="BTCUSDT",
                                   price=70_001, quantity=15.0)),    # $1.05M
        ]
        counters, _out, _err = self._run(
            msgs=msgs, supabase_writer=writer,
            symbols="BTCUSDT", min_notional=250_000, target="supabase",
        )
        assert counters["events"] == 2
        assert counters["supabase_writes"] == 2
        assert counters["supabase_failures"] == 0
        assert len(writer.calls) == 2
        for call in writer.calls:
            ev = call["event"]
            assert ev["symbol"] == "BTCUSDT"
            assert isinstance(call["meta"], dict)
            assert "should_send" in call["meta"]

    def test_target_supabase_records_duplicates(self):
        writer = _FakeSupabaseWriter(
            result={"ok": True, "duplicate": True},
        )
        msgs = [json.dumps(_agg_trade(
            agg_id=1, symbol="BTCUSDT", price=70_000, quantity=20.0,
        ))]
        counters, _out, _err = self._run(
            msgs=msgs, supabase_writer=writer,
            symbols="BTCUSDT", min_notional=250_000, target="supabase",
        )
        assert counters["supabase_writes"] == 0
        assert counters["supabase_duplicates"] == 1
        assert counters["supabase_failures"] == 0

    def test_target_supabase_counts_failures(self):
        writer = _FakeSupabaseWriter(
            result={"ok": False, "error": "boom", "status": 500},
        )
        msgs = [json.dumps(_agg_trade(
            agg_id=1, symbol="BTCUSDT", price=70_000, quantity=20.0,
        ))]
        counters, _out, _err = self._run(
            msgs=msgs, supabase_writer=writer,
            symbols="BTCUSDT", min_notional=250_000, target="supabase",
        )
        assert counters["events"] == 1
        assert counters["supabase_writes"] == 0
        assert counters["supabase_failures"] == 1

    def test_target_both_writes_journal_and_supabase(self, tmp_path):
        from services.whale_event_journal import read_whale_event_journal

        writer = _FakeSupabaseWriter()
        path = tmp_path / "whales.jsonl"
        msgs = [json.dumps(_agg_trade(
            agg_id=1, symbol="BTCUSDT", price=70_000, quantity=20.0,
        ))]
        counters, _out, _err = self._run(
            msgs=msgs, supabase_writer=writer,
            symbols="BTCUSDT", min_notional=250_000,
            target="both", journal_path=str(path),
        )
        assert counters["events"] == 1
        assert counters["supabase_writes"] == 1
        assert counters["journaled"] == 1
        rows = read_whale_event_journal(path)
        assert len(rows) == 1

    def test_target_jsonl_without_journal_path_safe_exit(self):
        writer = _FakeSupabaseWriter()
        counters, _out, err = self._run(
            msgs=[], supabase_writer=writer,
            symbols="BTCUSDT", target="jsonl",
        )
        assert counters["stopped_reason"] == "missing_journal_path"
        assert counters["events"] == 0
        assert writer.calls == []
        assert any("journal-path" in line for line in err)


# ── LM63J: worker mode / env config / heartbeats ─────────────────────────────

_SENTINEL = object()


class TestSmokeRunnerWorkerMode:
    def _run(self, *, msgs, supabase_writer=None, env=_SENTINEL,
             now_fn=None, **arg_overrides):
        """
        Default env carries a valid SUPABASE_URL/SERVICE_ROLE_KEY pair so the
        target=supabase/both env-check passes. Pass `env={}` (or any explicit
        value) to exercise the failure path.
        """
        from scripts.run_binance_trade_stream_smoke import run_pipeline
        args = _build_args(**arg_overrides)
        out_lines: list[str] = []
        err_lines: list[str] = []
        kwargs: dict = {
            "args":          args,
            "message_iter":  iter(msgs),
            "sender":        _FakeSender(),
            "supabase_writer": supabase_writer or _FakeSupabaseWriter(),
            "print_fn":      out_lines.append,
            "err_fn":        err_lines.append,
            "env":           dict(_VALID_SUPABASE_ENV) if env is _SENTINEL else env,
        }
        if now_fn is not None:
            kwargs["now"] = now_fn
        counters = run_pipeline(**kwargs)
        return counters, out_lines, err_lines

    def test_forever_false_respects_max_events(self):
        # 10 fills, max_events=3 → stop at 3 even though more remain.
        msgs = [
            json.dumps(_agg_trade(agg_id=i, symbol="BTCUSDT",
                                   price=70_000, quantity=20.0))
            for i in range(1, 11)
        ]
        counters, _out, _err = self._run(
            msgs=msgs,
            symbols="BTCUSDT", min_notional=250_000,
            forever=False, max_events=3,
        )
        assert counters["events"] == 3
        assert counters["stopped_reason"] == "max_events"

    def test_forever_disables_default_max_events_cap(self):
        # max_events left at its CLI sentinel (None). --forever should turn
        # the default cap into "no cap" so all 25 events get processed.
        msgs = [
            json.dumps(_agg_trade(agg_id=i, symbol="BTCUSDT",
                                   price=70_000, quantity=20.0))
            for i in range(1, 26)
        ]
        counters, _out, _err = self._run(
            msgs=msgs,
            symbols="BTCUSDT", min_notional=250_000,
            forever=True, max_events=None,
        )
        assert counters["events"] == 25
        assert counters["stopped_reason"] == "exhausted"

    def test_forever_with_explicit_max_events_still_respects_it(self):
        msgs = [
            json.dumps(_agg_trade(agg_id=i, symbol="BTCUSDT",
                                   price=70_000, quantity=20.0))
            for i in range(1, 11)
        ]
        counters, _out, _err = self._run(
            msgs=msgs,
            symbols="BTCUSDT", min_notional=250_000,
            forever=True, max_events=4,
        )
        assert counters["events"] == 4
        assert counters["stopped_reason"] == "max_events"

    def test_target_supabase_with_missing_env_safe_exit(self):
        # Empty env dict → supabase env check fails BEFORE the stream opens.
        writer = _FakeSupabaseWriter()
        counters, _out, err = self._run(
            msgs=[json.dumps(_agg_trade())],  # never processed
            supabase_writer=writer,
            symbols="BTCUSDT", target="supabase",
            env={},  # critical: empty
        )
        assert counters["stopped_reason"] == "missing_supabase_env"
        assert counters["events"] == 0
        assert writer.calls == []
        # Error line surfaces the missing env names.
        assert any("SUPABASE_URL" in line for line in err)
        assert any("SUPABASE_SERVICE_ROLE_KEY" in line for line in err)

    def test_target_both_with_missing_env_safe_exit(self, tmp_path):
        writer = _FakeSupabaseWriter()
        path = tmp_path / "whales.jsonl"
        counters, _out, err = self._run(
            msgs=[json.dumps(_agg_trade())],
            supabase_writer=writer,
            symbols="BTCUSDT", target="both",
            journal_path=str(path),
            env={"SUPABASE_URL": "https://x.supabase.co"},  # key missing
        )
        assert counters["stopped_reason"] == "missing_supabase_env"
        assert writer.calls == []
        # Journal file should NOT have been opened either — we exit before the loop.
        assert not path.exists()
        assert any("SERVICE_ROLE_KEY" in line for line in err)

    def test_supabase_writer_exception_does_not_crash_loop(self):
        # A writer that raises on every call should be caught and counted
        # — the loop must keep processing the next event cleanly.
        class _ExplodingWriter:
            def __init__(self):
                self.calls = 0
            def __call__(self, event, *, meta=None, **kwargs):
                self.calls += 1
                raise RuntimeError(f"db is on fire #{self.calls}")

        writer = _ExplodingWriter()
        msgs = [
            json.dumps(_agg_trade(agg_id=1, symbol="BTCUSDT",
                                   price=70_000, quantity=20.0)),
            json.dumps(_agg_trade(agg_id=2, symbol="BTCUSDT",
                                   price=70_000, quantity=20.0)),
            json.dumps(_agg_trade(agg_id=3, symbol="BTCUSDT",
                                   price=70_000, quantity=20.0)),
        ]
        counters, _out, err = self._run(
            msgs=msgs, supabase_writer=writer,
            symbols="BTCUSDT", min_notional=250_000, target="supabase",
        )
        assert counters["events"] == 3
        assert counters["supabase_writes"] == 0
        assert counters["supabase_failures"] == 3
        assert writer.calls == 3
        # Each failure should produce a stderr line.
        assert sum("supabase write raised" in line for line in err) == 3

    def test_target_both_writes_both_sinks(self, tmp_path):
        from services.whale_event_journal import read_whale_event_journal

        path = tmp_path / "whales.jsonl"
        writer = _FakeSupabaseWriter()
        msgs = [
            json.dumps(_agg_trade(agg_id=i, symbol="BTCUSDT",
                                   price=70_000, quantity=20.0))
            for i in range(1, 4)
        ]
        counters, _out, _err = self._run(
            msgs=msgs, supabase_writer=writer,
            symbols="BTCUSDT", min_notional=250_000,
            target="both", journal_path=str(path),
        )
        assert counters["events"] == 3
        assert counters["journaled"] == 3
        assert counters["supabase_writes"] == 3
        rows = read_whale_event_journal(path)
        assert len(rows) == 3
        assert len(writer.calls) == 3

    def test_heartbeat_emitted_on_interval(self):
        # Fake monotonic clock:
        #   call 1 — pipeline startup  (started_at = 0)
        #   call 2 — iteration 1 begin (t = 0  → diff 0  → no heartbeat)
        #   call 3 — iteration 2 begin (t = 12 → diff 12 → heartbeat fires)
        ticks = iter([0.0, 0.0, 12.0, 12.0])
        def fake_now() -> float:
            try:
                return next(ticks)
            except StopIteration:
                return 12.0

        msgs = [
            json.dumps(_agg_trade(agg_id=1, symbol="BTCUSDT",
                                   price=70_000, quantity=20.0)),
            json.dumps(_agg_trade(agg_id=2, symbol="BTCUSDT",
                                   price=70_000, quantity=20.0)),
        ]
        counters, _out, err = self._run(
            msgs=msgs, symbols="BTCUSDT", min_notional=250_000,
            heartbeat_interval=10.0, now_fn=fake_now,
        )
        assert counters["events"] == 2
        # Exactly one heartbeat line — the second message crossed the interval.
        heartbeats = [line for line in err if line.startswith("heartbeat")]
        assert len(heartbeats) == 1
        assert "uptime=12s" in heartbeats[0]


# ── LM63J: helpers (format_heartbeat / resolve_max_events / env config) ──────

class TestFormatHeartbeat:
    def test_includes_all_counters(self):
        from scripts.run_binance_trade_stream_smoke import format_heartbeat
        counters = {
            "seen": 100, "events": 7, "sendable": 5, "sent": 4,
            "supabase_writes": 5, "supabase_duplicates": 1,
            "supabase_failures": 0,
            "journaled": 7, "journal_failures": 0,
        }
        out = format_heartbeat(counters, 42.7)
        assert "uptime=43s" in out
        assert "events=7" in out
        assert "supabase_writes=5" in out
        assert "supabase_duplicates=1" in out
        assert "journaled=7" in out
        assert out.startswith("heartbeat")

    def test_handles_missing_keys_safely(self):
        from scripts.run_binance_trade_stream_smoke import format_heartbeat
        # Empty counters dict — must not raise; defaults to 0s.
        out = format_heartbeat({}, 0.0)
        assert "events=0" in out
        assert "supabase_writes=0" in out


class TestResolveMaxEvents:
    def _ns(self, **kw):
        import argparse
        base = {"max_events": None, "forever": False}
        base.update(kw)
        return argparse.Namespace(**base)

    def test_explicit_positive_wins(self):
        from scripts.run_binance_trade_stream_smoke import resolve_max_events
        assert resolve_max_events(self._ns(max_events=5)) == 5
        assert resolve_max_events(self._ns(max_events=5, forever=True)) == 5

    def test_explicit_zero_or_negative_disables_cap(self):
        from scripts.run_binance_trade_stream_smoke import resolve_max_events
        assert resolve_max_events(self._ns(max_events=0)) is None
        assert resolve_max_events(self._ns(max_events=-1, forever=True)) is None

    def test_omitted_with_forever_disables_cap(self):
        from scripts.run_binance_trade_stream_smoke import resolve_max_events
        assert resolve_max_events(self._ns(max_events=None, forever=True)) is None

    def test_omitted_without_forever_uses_default(self):
        from scripts.run_binance_trade_stream_smoke import (
            DEFAULT_MAX_EVENTS,
            resolve_max_events,
        )
        assert resolve_max_events(self._ns(max_events=None)) == DEFAULT_MAX_EVENTS


class TestApplyEnvConfig:
    def _ns(self, **kw):
        import argparse
        base = dict(
            symbols="BTCUSDT", min_notional=None, target="stdout",
            forever=False, use_env_config=False,
        )
        base.update(kw)
        return argparse.Namespace(**base)

    def test_no_op_when_disabled(self):
        from scripts.run_binance_trade_stream_smoke import apply_env_config
        ns = self._ns()
        env = {"WORKER_SYMBOLS": "ETHUSDT", "WHALE_WORKER_FOREVER": "true"}
        apply_env_config(ns, env=env, argv=[])
        assert ns.symbols == "BTCUSDT"
        assert ns.forever is False

    def test_env_applies_when_enabled_and_no_explicit_cli(self):
        from scripts.run_binance_trade_stream_smoke import apply_env_config
        ns = self._ns(use_env_config=True)
        env = {
            "WORKER_SYMBOLS":             "ETHUSDT,SOLUSDT",
            "WHALE_WORKER_MIN_NOTIONAL":  "75000",
            "WHALE_WORKER_TARGET":        "supabase",
            "WHALE_WORKER_FOREVER":       "true",
        }
        apply_env_config(ns, env=env, argv=[])
        assert ns.symbols == "ETHUSDT,SOLUSDT"
        assert ns.min_notional == 75_000.0
        assert ns.target == "supabase"
        assert ns.forever is True

    def test_explicit_cli_wins_over_env(self):
        from scripts.run_binance_trade_stream_smoke import apply_env_config
        ns = self._ns(use_env_config=True, symbols="BTCUSDT", target="stdout")
        env = {"WORKER_SYMBOLS": "ETHUSDT", "WHALE_WORKER_TARGET": "supabase"}
        # User passed --symbols and --target on the CLI explicitly.
        apply_env_config(ns, env=env, argv=["--symbols", "BTCUSDT", "--target", "stdout"])
        assert ns.symbols == "BTCUSDT"
        assert ns.target == "stdout"

    def test_invalid_target_in_env_ignored(self):
        from scripts.run_binance_trade_stream_smoke import apply_env_config
        ns = self._ns(use_env_config=True)
        apply_env_config(ns, env={"WHALE_WORKER_TARGET": "rabbit"}, argv=[])
        assert ns.target == "stdout"

    def test_invalid_min_notional_in_env_ignored(self):
        from scripts.run_binance_trade_stream_smoke import apply_env_config
        ns = self._ns(use_env_config=True)
        apply_env_config(ns, env={"WHALE_WORKER_MIN_NOTIONAL": "not a number"}, argv=[])
        assert ns.min_notional is None


class TestSupabaseEnvReady:
    def test_returns_ok_when_both_present(self):
        from scripts.run_binance_trade_stream_smoke import supabase_env_ready
        ok, msg = supabase_env_ready({
            "SUPABASE_URL": "https://x.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "k",
        })
        assert ok is True
        assert msg == ""

    def test_returns_error_when_missing(self):
        from scripts.run_binance_trade_stream_smoke import supabase_env_ready
        ok, msg = supabase_env_ready({})
        assert ok is False
        assert "SUPABASE_URL" in msg
        assert "SUPABASE_SERVICE_ROLE_KEY" in msg

    def test_blank_values_treated_as_missing(self):
        from scripts.run_binance_trade_stream_smoke import supabase_env_ready
        ok, msg = supabase_env_ready({
            "SUPABASE_URL": "  ",
            "SUPABASE_SERVICE_ROLE_KEY": "",
        })
        assert ok is False
        assert "SUPABASE_URL" in msg
        assert "SUPABASE_SERVICE_ROLE_KEY" in msg


# ── LM64B: Binance Futures aggTrade support ──────────────────────────────────

class TestFuturesUrlBuilder:
    def test_single_symbol_futures_endpoint(self):
        url = build_binance_aggtrade_ws_url(["BTCUSDT"], market="futures")
        assert url == "wss://fstream.binance.com/ws/btcusdt@aggTrade"

    def test_multi_symbol_futures_combined_endpoint(self):
        url = build_binance_aggtrade_ws_url(
            ["BTCUSDT", "ETHUSDT"], market="futures",
        )
        assert url.startswith("wss://fstream.binance.com/stream?streams=")
        assert "btcusdt@aggTrade" in url
        assert "ethusdt@aggTrade" in url

    def test_default_market_is_spot(self):
        # LM63B back-compat — explicit assertion that the no-market call
        # still routes to the spot endpoint.
        url = build_binance_aggtrade_ws_url(["BTCUSDT"])
        assert url == "wss://stream.binance.com:9443/ws/btcusdt@aggTrade"

    def test_unknown_market_raises_clear_error(self):
        # LM64B-fix: silent fallback removed. A bad market must error out
        # before we open a websocket to the wrong venue.
        with pytest.raises(ValueError) as exc_info:
            build_binance_aggtrade_ws_url(["BTCUSDT"], market="bogus")
        msg = str(exc_info.value)
        assert "unsupported market" in msg
        assert "spot" in msg
        assert "futures" in msg

    def test_non_string_market_raises(self):
        with pytest.raises(ValueError):
            build_binance_aggtrade_ws_url(["BTCUSDT"], market=None)  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            build_binance_aggtrade_ws_url(["BTCUSDT"], market=42)    # type: ignore[arg-type]

    def test_no_valid_symbols_still_raises(self):
        with pytest.raises(ValueError):
            build_binance_aggtrade_ws_url([], market="futures")

    def test_spot_url_uses_stream_binance_com_base(self):
        url = build_binance_aggtrade_ws_url(["BTCUSDT", "ETHUSDT"], market="spot")
        assert url.startswith("wss://stream.binance.com:9443/")
        assert "fstream.binance.com" not in url

    def test_futures_url_uses_fstream_binance_com_base(self):
        url = build_binance_aggtrade_ws_url(["BTCUSDT", "ETHUSDT"], market="futures")
        assert url.startswith("wss://fstream.binance.com/")
        assert "stream.binance.com:9443" not in url


class TestFuturesNormalization:
    def test_source_type_and_exchange_for_futures(self):
        parsed = parse_agg_trade_message(_agg_trade(agg_id=1, symbol="BTCUSDT"))
        assert parsed is not None
        out = normalize_agg_trade_to_whale_input(parsed, market="futures")
        assert out["source_type"] == "futures_trade"
        assert out["exchange"]    == "binance_futures"
        assert out["metadata"]["market"] == "futures"

    def test_source_type_and_exchange_for_spot_default(self):
        parsed = parse_agg_trade_message(_agg_trade(agg_id=1, symbol="BTCUSDT"))
        assert parsed is not None
        out = normalize_agg_trade_to_whale_input(parsed)  # default
        assert out["source_type"] == "exchange_trade"
        assert out["exchange"]    == "binance_spot"
        assert out["metadata"]["market"] == "spot"

    def test_unknown_market_raises_in_normalize(self):
        parsed = parse_agg_trade_message(_agg_trade(agg_id=2, symbol="BTCUSDT"))
        assert parsed is not None
        with pytest.raises(ValueError) as exc_info:
            normalize_agg_trade_to_whale_input(parsed, market="lol")
        assert "unsupported market" in str(exc_info.value)

    def test_side_mapping_identical_across_markets(self):
        # Maker flag → SELL aggressor on both venues.
        for market in ("spot", "futures"):
            parsed = parse_agg_trade_message(
                _agg_trade(agg_id=99, symbol="BTCUSDT", is_maker=True),
            )
            assert parsed is not None
            out = normalize_agg_trade_to_whale_input(parsed, market=market)
            assert out["side"] == "sell", f"market={market}"

    def test_notional_math_identical_across_markets(self):
        for market in ("spot", "futures"):
            parsed = parse_agg_trade_message(
                _agg_trade(agg_id=1, symbol="BTCUSDT",
                           price=1234.5, quantity=2.0),
            )
            assert parsed is not None
            out = normalize_agg_trade_to_whale_input(parsed, market=market)
            assert out["notional_usd"] == pytest.approx(2469.0), \
                f"market={market}"


class TestFuturesIterator:
    def test_yields_futures_normalised_records(self):
        msgs = [json.dumps(_agg_trade(
            agg_id=1, symbol="BTCUSDT", price=70_000, quantity=20.0,
        ))]
        out = list(iter_binance_aggtrades(
            ["BTCUSDT"], message_iter=iter(msgs), market="futures",
        ))
        assert len(out) == 1
        assert out[0]["source_type"] == "futures_trade"
        assert out[0]["exchange"]    == "binance_futures"
        assert out[0]["metadata"]["market"] == "futures"

    def test_default_market_yields_spot_records(self):
        msgs = [json.dumps(_agg_trade(agg_id=1, symbol="BTCUSDT"))]
        out = list(iter_binance_aggtrades(["BTCUSDT"], message_iter=iter(msgs)))
        assert out[0]["exchange"] == "binance_spot"

    def test_iterator_validates_market_up_front(self):
        # Bad market must raise BEFORE any websocket is opened or any
        # message is consumed.
        with pytest.raises(ValueError):
            # Wrap the generator in list() to force the entry/setup phase.
            list(iter_binance_aggtrades(
                ["BTCUSDT"], message_iter=iter([]), market="oops",
            ))


class TestFuturesIteratorTransportUrl:
    """
    Guard against the LM64B-fix regression: when `message_iter is None`,
    the iterator must hand the *futures* base URL to the WS transport for
    `market="futures"`. Spot must keep the spot base URL.
    """

    def _capture_url(self, market: str) -> str:
        """Monkey-patch the real-network transport, return the URL it saw."""
        import services.connectors.binance_trade_stream as bts
        captured: list[str] = []
        original = bts._default_ws_messages_with_reconnect

        def fake(url, progress=None):
            captured.append(url)
            return iter([])

        bts._default_ws_messages_with_reconnect = fake  # type: ignore[assignment]
        try:
            # message_iter=None → iterator builds a URL and hands it to the
            # (now mocked) transport. The generator exits immediately.
            list(bts.iter_binance_aggtrades(
                ["BTCUSDT", "ETHUSDT"], market=market,
            ))
        finally:
            bts._default_ws_messages_with_reconnect = original  # type: ignore[assignment]
        assert len(captured) == 1, f"expected one URL, got {captured!r}"
        return captured[0]

    def test_futures_iterator_opens_fstream_url(self):
        url = self._capture_url("futures")
        assert url.startswith("wss://fstream.binance.com/"), (
            f"futures must use fstream.binance.com but got {url!r}"
        )
        assert "stream.binance.com:9443" not in url

    def test_spot_iterator_opens_stream_url(self):
        url = self._capture_url("spot")
        assert url.startswith("wss://stream.binance.com:9443/"), (
            f"spot must use stream.binance.com:9443 but got {url!r}"
        )
        assert "fstream.binance.com" not in url


class TestSupabaseRowCarriesMarket:
    def test_futures_row_preserves_source_type_and_exchange(self):
        from services.whale_event_supabase_writer import (
            build_whale_event_supabase_row,
        )
        parsed = parse_agg_trade_message(_agg_trade(
            agg_id=42, symbol="BTCUSDT", price=70_000, quantity=20.0,
        ))
        assert parsed is not None
        ev = normalize_agg_trade_to_whale_input(parsed, market="futures")
        row = build_whale_event_supabase_row(ev)
        assert row is not None
        assert row["source_type"] == "futures_trade"
        assert row["exchange"]    == "binance_futures"
        # payload also keeps the event verbatim, including metadata.market.
        assert row["payload"]["event"]["metadata"]["market"] == "futures"


class TestSmokeRunnerMarketFlag:
    def _run(self, *, msgs, **arg_overrides):
        from scripts.run_binance_trade_stream_smoke import run_pipeline
        args = _build_args(**arg_overrides)
        out_lines: list[str] = []
        err_lines: list[str] = []
        counters = run_pipeline(
            args=args,
            message_iter=iter(msgs),
            sender=_FakeSender(),
            supabase_writer=_FakeSupabaseWriter(),
            print_fn=out_lines.append,
            err_fn=err_lines.append,
            env=dict(_VALID_SUPABASE_ENV),
        )
        return counters, out_lines, err_lines

    def test_market_futures_writes_futures_source_type(self, tmp_path):
        from services.whale_event_journal import read_whale_event_journal

        path = tmp_path / "whales.jsonl"
        msgs = [json.dumps(_agg_trade(
            agg_id=1, symbol="BTCUSDT", price=70_000, quantity=20.0,
        ))]
        counters, _out, _err = self._run(
            msgs=msgs, symbols="BTCUSDT", min_notional=250_000,
            target="jsonl", journal_path=str(path),
            market="futures",
        )
        assert counters["events"] == 1
        assert counters["journaled"] == 1

        rows = read_whale_event_journal(path)
        assert len(rows) == 1
        event = rows[0]["event"]
        assert event["source_type"] == "futures_trade"
        assert event["exchange"]    == "binance_futures"
        assert event["metadata"]["market"] == "futures"

    def test_default_market_remains_spot(self, tmp_path):
        from services.whale_event_journal import read_whale_event_journal

        path = tmp_path / "whales.jsonl"
        msgs = [json.dumps(_agg_trade(
            agg_id=1, symbol="BTCUSDT", price=70_000, quantity=20.0,
        ))]
        counters, _out, _err = self._run(
            msgs=msgs, symbols="BTCUSDT", min_notional=250_000,
            target="jsonl", journal_path=str(path),
            # market omitted → spot
        )
        assert counters["events"] == 1
        rows = read_whale_event_journal(path)
        assert rows[0]["event"]["source_type"] == "exchange_trade"
        assert rows[0]["event"]["exchange"]    == "binance_spot"

    def test_startup_banner_mentions_market(self):
        msgs = [json.dumps(_agg_trade(
            agg_id=1, symbol="BTCUSDT", price=70_000, quantity=20.0,
        ))]
        _counters, _out, err = self._run(
            msgs=msgs, symbols="BTCUSDT", min_notional=250_000,
            market="futures",
        )
        assert any("market=futures" in line for line in err)


class TestApplyEnvConfigMarket:
    def _ns(self, **kw):
        import argparse
        base = dict(
            symbols="BTCUSDT", min_notional=None, target="stdout",
            forever=False, use_env_config=False, market="spot",
        )
        base.update(kw)
        return argparse.Namespace(**base)

    def test_env_market_applied_when_enabled(self):
        from scripts.run_binance_trade_stream_smoke import apply_env_config
        ns = self._ns(use_env_config=True)
        apply_env_config(ns, env={"WHALE_WORKER_MARKET": "futures"}, argv=[])
        assert ns.market == "futures"

    def test_explicit_cli_market_wins_over_env(self):
        from scripts.run_binance_trade_stream_smoke import apply_env_config
        ns = self._ns(use_env_config=True, market="spot")
        apply_env_config(
            ns,
            env={"WHALE_WORKER_MARKET": "futures"},
            argv=["--market", "spot"],
        )
        assert ns.market == "spot"

    def test_invalid_env_market_ignored(self):
        from scripts.run_binance_trade_stream_smoke import apply_env_config
        ns = self._ns(use_env_config=True)
        apply_env_config(ns, env={"WHALE_WORKER_MARKET": "rabbit"}, argv=[])
        assert ns.market == "spot"
