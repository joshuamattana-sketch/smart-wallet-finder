"""
tests/test_discord_webhook_sender.py
-------------------------------------
LM51B — Discord webhook sender tests.

No real network calls — `urllib.request.urlopen` is patched throughout.
No secrets in fixtures (the URL "https://example/fake" is a placeholder
and never reaches the network).
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

import urllib.error

from services.discord_webhook_sender import (
    ENV_WEBHOOK_URL,
    send_discord_webhook,
)


# ── Reusable fixtures ───────────────────────────────────────────────────────

_FAKE_URL = "https://example/fake"
_PAYLOAD = {
    "content": "hello",
    "embeds": [
        {"title": "T", "description": "D", "fields": [], "footer": {"text": "f"}},
    ],
}


class _Resp:
    """Minimal urlopen response context-manager double."""

    def __init__(self, status: int, body: bytes = b"") -> None:
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_Resp":
        return self

    def __exit__(self, *exc_info) -> bool:
        return False


# ── 2xx success ─────────────────────────────────────────────────────────────

class TestSuccess:

    def test_status_204_no_content(self):
        captured: dict = {}
        def _fake_urlopen(req, timeout=None):
            captured["url"]     = req.full_url
            captured["headers"] = dict(req.headers)
            captured["body"]    = req.data
            return _Resp(204)
        with patch.object(__import__("services.discord_webhook_sender",
                                     fromlist=["urllib"]).urllib.request,
                          "urlopen", side_effect=_fake_urlopen):
            result = send_discord_webhook(_PAYLOAD, webhook_url=_FAKE_URL)
        assert result["ok"]            is True
        assert result["status_code"]   == 204
        assert result["error"]         is None
        assert result["response_text"] == ""
        # Body is JSON-encoded payload; URL never echoed in result.
        assert captured["url"] == _FAKE_URL
        assert json.loads(captured["body"]) == _PAYLOAD
        # Webhook URL must not appear in the result dict.
        assert _FAKE_URL not in str(result)

    def test_status_200_with_body(self):
        with patch("services.discord_webhook_sender.urllib.request.urlopen",
                   return_value=_Resp(200, b"OK-ish body")):
            result = send_discord_webhook(_PAYLOAD, webhook_url=_FAKE_URL)
        assert result["ok"]            is True
        assert result["status_code"]   == 200
        assert "OK-ish body"           in result["response_text"]


# ── Invalid payload ────────────────────────────────────────────────────────

class TestInvalidPayload:

    def test_none_payload(self):
        result = send_discord_webhook(None, webhook_url=_FAKE_URL)
        assert result["ok"]          is False
        assert result["status_code"] is None
        assert "invalid payload"     in result["error"]

    def test_non_dict_payload(self):
        result = send_discord_webhook("hi", webhook_url=_FAKE_URL)  # type: ignore[arg-type]
        assert result["ok"]    is False
        assert "invalid payload" in result["error"]

    def test_empty_dict_payload(self):
        result = send_discord_webhook({}, webhook_url=_FAKE_URL)
        assert result["ok"]    is False
        assert "invalid payload" in result["error"]

    def test_payload_with_neither_content_nor_embeds(self):
        result = send_discord_webhook({"other": 1}, webhook_url=_FAKE_URL)
        assert result["ok"]    is False


# ── Missing webhook URL ─────────────────────────────────────────────────────

class TestMissingWebhookUrl:

    def test_no_arg_and_no_env(self, monkeypatch):
        monkeypatch.delenv(ENV_WEBHOOK_URL, raising=False)
        result = send_discord_webhook(_PAYLOAD)
        assert result["ok"]          is False
        assert result["status_code"] is None
        assert "no webhook URL"      in result["error"]
        # Reassure ourselves no real send was attempted.

    def test_env_used_when_arg_missing(self, monkeypatch):
        monkeypatch.setenv(ENV_WEBHOOK_URL, _FAKE_URL)
        with patch("services.discord_webhook_sender.urllib.request.urlopen",
                   return_value=_Resp(204)) as mock_open:
            result = send_discord_webhook(_PAYLOAD)
        assert result["ok"] is True
        assert mock_open.call_count == 1

    def test_empty_string_url_treated_as_missing(self, monkeypatch):
        monkeypatch.delenv(ENV_WEBHOOK_URL, raising=False)
        result = send_discord_webhook(_PAYLOAD, webhook_url="   ")
        assert result["ok"]     is False
        assert "no webhook URL" in result["error"]


# ── Network errors ─────────────────────────────────────────────────────────

class TestNetworkErrors:

    def test_http_error_4xx(self):
        # Force urlopen to raise HTTPError directly.
        class _FakeHTTPError(urllib.error.HTTPError):
            def __init__(self):
                super().__init__(
                    url="https://example/fake", code=400,
                    msg="Bad Request", hdrs=None, fp=None,
                )
            def read(self) -> bytes:
                return b'{"message": "Cannot send empty message"}'
        with patch("services.discord_webhook_sender.urllib.request.urlopen",
                   side_effect=_FakeHTTPError()):
            result = send_discord_webhook(_PAYLOAD, webhook_url=_FAKE_URL)
        assert result["ok"]          is False
        assert result["status_code"] == 400
        assert result["error"]       == "HTTP 400"
        assert "Cannot send empty"   in result["response_text"]

    def test_http_error_5xx(self):
        class _FakeHTTPError(urllib.error.HTTPError):
            def __init__(self):
                super().__init__(
                    url="https://example/fake", code=503,
                    msg="Service Unavailable", hdrs=None, fp=None,
                )
            def read(self) -> bytes:
                return b""
        with patch("services.discord_webhook_sender.urllib.request.urlopen",
                   side_effect=_FakeHTTPError()):
            result = send_discord_webhook(_PAYLOAD, webhook_url=_FAKE_URL)
        assert result["ok"]          is False
        assert result["status_code"] == 503

    def test_network_url_error(self):
        with patch("services.discord_webhook_sender.urllib.request.urlopen",
                   side_effect=urllib.error.URLError("connection refused")):
            result = send_discord_webhook(_PAYLOAD, webhook_url=_FAKE_URL)
        assert result["ok"]          is False
        assert result["status_code"] is None
        assert "network error"       in result["error"]
        assert "connection refused"  in result["error"]


# ── Timeout ────────────────────────────────────────────────────────────────

class TestTimeout:

    def test_timeout_error_returns_clean_result(self):
        with patch("services.discord_webhook_sender.urllib.request.urlopen",
                   side_effect=TimeoutError("read timed out")):
            result = send_discord_webhook(_PAYLOAD, webhook_url=_FAKE_URL,
                                          timeout=0.1)
        assert result["ok"]          is False
        assert result["status_code"] is None
        assert "timeout"             in result["error"]

    def test_timeout_arg_passed_to_urlopen(self):
        captured: dict = {}
        def _fake_urlopen(req, timeout=None):
            captured["timeout"] = timeout
            return _Resp(204)
        with patch("services.discord_webhook_sender.urllib.request.urlopen",
                   side_effect=_fake_urlopen):
            send_discord_webhook(_PAYLOAD, webhook_url=_FAKE_URL, timeout=3.5)
        assert captured["timeout"] == 3.5


# ── Secrets safety ─────────────────────────────────────────────────────────

class TestSecretsSafety:

    def test_url_not_present_in_result(self, monkeypatch):
        monkeypatch.setenv(ENV_WEBHOOK_URL, "https://secret/abc123")
        with patch("services.discord_webhook_sender.urllib.request.urlopen",
                   return_value=_Resp(204)):
            result = send_discord_webhook(_PAYLOAD)
        for v in result.values():
            assert "secret" not in str(v)
            assert "abc123" not in str(v)

    def test_url_not_in_error_messages(self):
        # Even on network failure the URL must not leak.
        with patch("services.discord_webhook_sender.urllib.request.urlopen",
                   side_effect=urllib.error.URLError("oops")):
            result = send_discord_webhook(_PAYLOAD,
                                          webhook_url="https://very/secret/path")
        assert "secret" not in str(result)
        assert "https"   not in str(result["error"] or "")


# ── Result shape ───────────────────────────────────────────────────────────

class TestResultShape:

    def test_always_has_four_keys(self):
        # Successful call.
        with patch("services.discord_webhook_sender.urllib.request.urlopen",
                   return_value=_Resp(204)):
            r = send_discord_webhook(_PAYLOAD, webhook_url=_FAKE_URL)
        assert set(r.keys()) == {"ok", "status_code", "error", "response_text"}
        # Invalid payload — same keys.
        r2 = send_discord_webhook(None)
        assert set(r2.keys()) == {"ok", "status_code", "error", "response_text"}

    def test_response_text_truncated_to_400_chars(self):
        big = b"x" * 5000
        with patch("services.discord_webhook_sender.urllib.request.urlopen",
                   return_value=_Resp(200, big)):
            r = send_discord_webhook(_PAYLOAD, webhook_url=_FAKE_URL)
        assert len(r["response_text"]) == 400
