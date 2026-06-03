"""Tests for run_local_status_check (LM59)."""

import json
from unittest.mock import patch

from scripts import run_local_status_check as cli


def _mock_ready():
    return {
        "status": "ready",
        "checks": [
            {"ok": True, "name": "worker_config", "details": {"symbols": ["BTC"]}, "error": None},
            {"ok": True, "name": "signal_pipeline", "details": {}, "error": None},
        ],
        "summary": {"total": 2, "ok": 2, "failed": 0},
    }


def _mock_degraded():
    return {
        "status": "degraded",
        "checks": [
            {"ok": True, "name": "worker_config", "details": {}, "error": None},
            {"ok": False, "name": "signal_pipeline", "details": None, "error": "boom"},
        ],
        "summary": {"total": 2, "ok": 1, "failed": 1},
    }


def test_ready_exits_0(capsys):
    with patch.object(cli, "run_local_end_to_end_status", side_effect=lambda: _mock_ready()):
        code = cli.main([])
    assert code == 0
    out = capsys.readouterr().out
    assert "READY" in out


def test_degraded_exits_1(capsys):
    with patch.object(cli, "run_local_end_to_end_status", side_effect=lambda: _mock_degraded()):
        code = cli.main([])
    assert code == 1
    out = capsys.readouterr().out
    assert "DEGRADED" in out


def test_json_flag_output(capsys):
    with patch.object(cli, "run_local_end_to_end_status", side_effect=lambda: _mock_ready()):
        code = cli.main(["--json"])
    assert code == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["status"] == "ready"
    assert "checks" in data


def test_human_output_contains_check_names(capsys):
    with patch.object(cli, "run_local_end_to_end_status", side_effect=lambda: _mock_degraded()):
        cli.main([])
    out = capsys.readouterr().out
    assert "worker_config" in out
    assert "signal_pipeline" in out
    assert "FAIL" in out
    assert "boom" in out


def test_no_network_db_dependency():
    code = cli.main([])
    assert code in (0, 1)
