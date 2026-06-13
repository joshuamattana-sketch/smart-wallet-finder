"""
tests/test_gold_bot_status_api.py
----------------------------------
LM91A - Static safety invariants for the read-only Gold Bot web status surface.

The web code is TypeScript (verified functionally by `npm run lint` / `npm run
build`). These offline checks guard the hard boundaries the prompt requires:
the API route + loader must be server-side, read-only, and must NEVER read
secrets / the Discord webhook env, shell out, call MT5, or do external HTTP; the
panel must expose NO trading controls. No MT5, no internet, no Node needed.
"""

from __future__ import annotations

from pathlib import Path

_WEB = Path(__file__).resolve().parent.parent / "lumora-web"
ROUTE = _WEB / "app" / "api" / "gold-bot" / "status" / "route.ts"
LIB = _WEB / "lib" / "gold-bot-status.ts"
PANEL = _WEB / "components" / "gold-bot" / "GoldBotStatusPanel.tsx"
PAGE = _WEB / "app" / "(app)" / "gold-bot" / "page.tsx"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ── files exist ───────────────────────────────────────────────────────────────────
def test_files_exist():
    for p in (ROUTE, LIB, PANEL, PAGE):
        assert p.exists(), f"missing {p}"


# ── route invariants ────────────────────────────────────────────────────────────────
def test_route_is_dynamic_and_nodejs():
    src = _read(ROUTE)
    assert 'export const dynamic = "force-dynamic"' in src
    assert 'export const runtime = "nodejs"' in src
    assert "loadGoldBotStatus" in src


def test_server_files_have_no_secrets_shell_mt5_or_http():
    for p in (ROUTE, LIB):
        src = _read(p)
        for forbidden in ("process.env", "child_process", "execSync", "spawn(",
                          "MetaTrader5", "discord.com/api/webhooks", "https://",
                          "WEBHOOK", "SUPABASE", "order_send"):
            assert forbidden not in src, f"{p.name} must not reference {forbidden}"


def test_loader_reads_local_gold_bot_data_only():
    src = _read(LIB)
    assert 'path.resolve(process.cwd(), "..", "data", "gold_bot")' in src
    # never inspects the webhook env — reports send-readiness as unknown
    assert '"unknown_env_not_checked"' in src
    assert "fetch(" not in src           # no external HTTP in the loader
    # only fs reads, never writes
    assert "writeFile" not in src and "fs.write" not in src


def test_loader_emits_required_shape_keys():
    src = _read(LIB)
    for key in ("ok:", "generatedAt:", "local_read_only", "blockedReasons",
                "cooldownActive", "latestCycleVerdict", "readyToSend"):
        assert key in src, f"loader missing shape key {key}"


# ── panel invariants: read-only, no trading controls ─────────────────────────────────
def test_panel_is_read_only_no_trading_controls():
    src = _read(PANEL)
    assert "Read-only status. No trading controls" in src
    # exactly ONE button, and it is the status refresh (data reload only)
    assert src.count("<button") == 1
    assert 'aria-label="Refresh status"' in src
    # no trading / order / send actions
    for forbidden in ("order_send", "sendDiscord", "send-discord", "start-bot",
                      "stop-bot", 'method: "POST"', "POST"):
        assert forbidden not in src, f"panel must not contain {forbidden}"
    # only the read-only GET status endpoint is called
    assert '/api/gold-bot/status' in src


def test_panel_type_import_is_erased():
    # importing the server loader's TYPE only (no runtime node:fs pulled into client)
    src = _read(PANEL)
    assert "import type { GoldBotStatus }" in src


# ── page wires the panel without redesigning ─────────────────────────────────────────
def test_page_mounts_panel():
    src = _read(PAGE)
    assert "GoldBotStatusPanel" in src
    assert 'import { GoldBotStatusPanel }' in src
