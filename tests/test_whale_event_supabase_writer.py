"""
tests/test_whale_event_supabase_writer.py
------------------------------------------
LM63H — Tests for the Supabase writer.
"""

from __future__ import annotations

import json

import pytest

from services.whale_event_supabase_writer import (
    WHALE_EVENTS_TABLE,
    build_whale_event_supabase_row,
    write_whale_event_to_supabase,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _event(**overrides) -> dict:
    base = {
        "whale_event_id": "abc123def456",
        "source_type":    "exchange_trade",
        "symbol":         "BTCUSDT",
        "exchange":       "binance_spot",
        "chain":          "",
        "side":           "buy",
        "amount":         5.0,
        "price":          70_000.0,
        "notional_usd":   350_000.0,
        "severity":       "high",
        "confidence":     0.8,
        "reason":         "exchange_trade of BTCUSDT worth $350,000",
        "event_ts":       "2026-06-08T12:00:00+00:00",
        "wallet":         "agg:42",
        "tx_hash":        "agg:BTCUSDT:42",
        "metadata":       {"agg_trade_id": 42, "source": "binance_aggtrade"},
    }
    base.update(overrides)
    return base


class FakeResp:
    def __init__(self, status_code: int = 201, text: str = ""):
        self.status_code = status_code
        self.text = text


def _make_recorder(resp: FakeResp):
    calls: list[dict] = []
    def fake_post(url, data=None, headers=None, timeout=None):
        calls.append({"url": url, "data": data, "headers": headers, "timeout": timeout})
        return resp
    return fake_post, calls


# ── Row builder ───────────────────────────────────────────────────────────────

class TestRowBuilder:
    def test_basic_shape(self):
        row = build_whale_event_supabase_row(_event())
        assert isinstance(row, dict)
        expected_keys = {
            "whale_event_id", "source_type", "symbol", "exchange", "chain",
            "side", "severity", "reason", "event_ts", "wallet", "tx_hash",
            "amount", "price", "notional_usd", "confidence", "payload",
        }
        assert set(row) == expected_keys
        assert row["symbol"] == "BTCUSDT"
        assert row["notional_usd"] == pytest.approx(350_000.0)

    def test_payload_carries_event_and_meta(self):
        ev = _event()
        meta = {"should_send": True, "filter_reason": "extreme severity always sent"}
        row = build_whale_event_supabase_row(ev, meta=meta)
        assert row is not None
        assert row["payload"]["event"] == ev
        assert row["payload"]["meta"] == meta

    def test_payload_meta_none(self):
        row = build_whale_event_supabase_row(_event(), meta=None)
        assert row is not None
        assert row["payload"]["meta"] is None

    def test_payload_meta_non_dict_wrapped(self):
        row = build_whale_event_supabase_row(_event(), meta="oops")
        assert row is not None
        assert row["payload"]["meta"] == {"value": "oops"}

    def test_returns_none_for_non_dict(self):
        assert build_whale_event_supabase_row(None) is None
        assert build_whale_event_supabase_row("a string") is None
        assert build_whale_event_supabase_row(42) is None

    def test_returns_none_when_symbol_missing(self):
        ev = _event(); ev["symbol"] = ""
        assert build_whale_event_supabase_row(ev) is None
        ev2 = _event(); del ev2["symbol"]
        assert build_whale_event_supabase_row(ev2) is None

    def test_non_numeric_fields_become_none(self):
        ev = _event(amount="abc", price="N/A", notional_usd=None, confidence="?")
        row = build_whale_event_supabase_row(ev)
        assert row is not None
        assert row["amount"] is None
        assert row["price"] is None
        assert row["notional_usd"] is None
        assert row["confidence"] is None

    def test_row_payload_does_not_share_reference_with_input(self):
        ev = _event()
        row = build_whale_event_supabase_row(ev)
        assert row is not None
        # Mutating the original event after building must not change the row.
        ev["symbol"] = "MUTATED"
        assert row["payload"]["event"]["symbol"] == "BTCUSDT"


# ── Env handling ──────────────────────────────────────────────────────────────

class TestEnvHandling:
    def test_missing_env_returns_safe_error(self):
        result = write_whale_event_to_supabase(_event(), env={})
        assert result["ok"] is False
        assert "missing" in result["error"]
        assert "SUPABASE_URL" in result["error"]
        assert "SUPABASE_SERVICE_ROLE_KEY" in result["error"]
        assert result["status"] is None

    def test_missing_only_key_returns_safe_error(self):
        result = write_whale_event_to_supabase(
            _event(), env={"SUPABASE_URL": "https://x.supabase.co"},
        )
        assert result["ok"] is False
        assert "SUPABASE_SERVICE_ROLE_KEY" in result["error"]
        assert "SUPABASE_URL" not in result["error"]

    def test_explicit_args_override_env(self):
        post, calls = _make_recorder(FakeResp(201))
        result = write_whale_event_to_supabase(
            _event(),
            supabase_url="https://override.supabase.co",
            service_role_key="key-override",
            env={"SUPABASE_URL": "https://env.supabase.co",
                 "SUPABASE_SERVICE_ROLE_KEY": "key-env"},
            requester=post,
        )
        assert result == {"ok": True}
        assert calls[0]["url"].startswith("https://override.supabase.co")
        assert calls[0]["headers"]["apikey"] == "key-override"
        assert calls[0]["headers"]["Authorization"] == "Bearer key-override"


# ── Successful insert ────────────────────────────────────────────────────────

class TestSuccessfulInsert:
    def _good_env(self):
        return {"SUPABASE_URL": "https://x.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": "k"}

    def test_201_returns_ok(self):
        post, _calls = _make_recorder(FakeResp(201))
        result = write_whale_event_to_supabase(
            _event(), env=self._good_env(), requester=post,
        )
        assert result == {"ok": True}

    def test_200_and_204_treated_as_ok(self):
        for status in (200, 204):
            post, _calls = _make_recorder(FakeResp(status))
            result = write_whale_event_to_supabase(
                _event(), env=self._good_env(), requester=post,
            )
            assert result == {"ok": True}, f"status={status}"

    def test_endpoint_uses_on_conflict_param(self):
        post, calls = _make_recorder(FakeResp(201))
        write_whale_event_to_supabase(
            _event(), env=self._good_env(), requester=post,
        )
        assert calls[0]["url"].endswith(
            f"/rest/v1/{WHALE_EVENTS_TABLE}?on_conflict=whale_event_id"
        )

    def test_prefer_header_ignore_duplicates(self):
        post, calls = _make_recorder(FakeResp(201))
        write_whale_event_to_supabase(
            _event(), env=self._good_env(), requester=post,
        )
        prefer = calls[0]["headers"]["Prefer"]
        assert "return=minimal" in prefer
        assert "resolution=ignore-duplicates" in prefer

    def test_body_is_json_array_of_one_row(self):
        post, calls = _make_recorder(FakeResp(201))
        write_whale_event_to_supabase(
            _event(), env=self._good_env(), requester=post,
        )
        parsed = json.loads(calls[0]["data"])
        assert isinstance(parsed, list) and len(parsed) == 1
        row = parsed[0]
        assert row["symbol"] == "BTCUSDT"
        assert row["whale_event_id"] == "abc123def456"
        assert "payload" in row

    def test_custom_table_propagates(self):
        post, calls = _make_recorder(FakeResp(201))
        write_whale_event_to_supabase(
            _event(), env=self._good_env(), requester=post,
            table="whale_events_test",
        )
        assert "/rest/v1/whale_events_test?" in calls[0]["url"]


# ── Duplicate handling ───────────────────────────────────────────────────────

class TestDuplicateHandling:
    def _good_env(self):
        return {"SUPABASE_URL": "https://x.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": "k"}

    def test_409_treated_as_duplicate_ok(self):
        post, _calls = _make_recorder(FakeResp(409, text="conflict"))
        result = write_whale_event_to_supabase(
            _event(), env=self._good_env(), requester=post,
        )
        assert result == {"ok": True, "duplicate": True}

    def test_body_signals_unique_violation(self):
        post, _calls = _make_recorder(
            FakeResp(400, text='{"code":"23505","message":"duplicate key value"}'),
        )
        result = write_whale_event_to_supabase(
            _event(), env=self._good_env(), requester=post,
        )
        assert result == {"ok": True, "duplicate": True}

    def test_body_duplicate_key_phrase(self):
        post, _calls = _make_recorder(
            FakeResp(400, text='{"message":"duplicate key value violates unique constraint"}'),
        )
        result = write_whale_event_to_supabase(
            _event(), env=self._good_env(), requester=post,
        )
        assert result == {"ok": True, "duplicate": True}


# ── Failures ──────────────────────────────────────────────────────────────────

class TestFailures:
    def _good_env(self):
        return {"SUPABASE_URL": "https://x.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": "k"}

    def test_500_returns_error(self):
        post, _calls = _make_recorder(FakeResp(500, text="server boom"))
        result = write_whale_event_to_supabase(
            _event(), env=self._good_env(), requester=post,
        )
        assert result["ok"] is False
        assert result["status"] == 500
        assert "server boom" in result["error"]

    def test_404_returns_error(self):
        post, _calls = _make_recorder(FakeResp(404, text="not found"))
        result = write_whale_event_to_supabase(
            _event(), env=self._good_env(), requester=post,
        )
        assert result["ok"] is False
        assert result["status"] == 404

    def test_network_exception_returns_error(self):
        def boom(*args, **kwargs):
            raise ConnectionError("DNS exploded")
        result = write_whale_event_to_supabase(
            _event(), env=self._good_env(), requester=boom,
        )
        assert result["ok"] is False
        assert "network error" in result["error"]
        assert "DNS exploded" in result["error"]
        assert result["status"] is None

    def test_invalid_event_returns_error_without_post(self):
        post, calls = _make_recorder(FakeResp(201))
        result = write_whale_event_to_supabase(
            None, env=self._good_env(), requester=post,
        )
        assert result["ok"] is False
        assert "invalid event" in result["error"]
        # POST must not have been attempted.
        assert calls == []
