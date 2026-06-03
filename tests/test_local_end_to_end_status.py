"""Tests for local_end_to_end_status (LM58)."""

from unittest.mock import patch
from services.local_end_to_end_status import run_local_end_to_end_status


def test_all_checks_ready():
    result = run_local_end_to_end_status()
    assert result["status"] == "ready"
    assert all(c["ok"] for c in result["checks"])


def test_degraded_when_one_check_fails():
    import services.local_end_to_end_status as mod
    original_checks = mod._CHECKS

    def _bad():
        raise RuntimeError("boom")

    mod._CHECKS = [("bad_check", _bad)] + list(original_checks)
    try:
        result = run_local_end_to_end_status()
        assert result["status"] == "degraded"
        bad = [c for c in result["checks"] if c["name"] == "bad_check"]
        assert len(bad) == 1
        assert bad[0]["ok"] is False
        assert "boom" in bad[0]["error"]
    finally:
        mod._CHECKS = original_checks


def test_check_output_shape():
    result = run_local_end_to_end_status()
    for c in result["checks"]:
        assert set(c.keys()) == {"ok", "name", "details", "error"}
        assert isinstance(c["ok"], bool)
        assert isinstance(c["name"], str)


def test_summary_counts():
    result = run_local_end_to_end_status()
    s = result["summary"]
    assert s["total"] == len(result["checks"])
    assert s["ok"] + s["failed"] == s["total"]
    assert s["ok"] == sum(1 for c in result["checks"] if c["ok"])


def test_no_network_db_dependency():
    result = run_local_end_to_end_status()
    assert result["status"] in ("ready", "degraded")
    assert isinstance(result["checks"], list)


def test_missing_options_safe():
    r1 = run_local_end_to_end_status(None)
    r2 = run_local_end_to_end_status({})
    assert r1["status"] in ("ready", "degraded")
    assert r2["status"] in ("ready", "degraded")
