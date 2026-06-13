"""
tests/test_gold_bot_web_command_api.py
---------------------------------------
LM94B - Static safety invariants for the local Gold Bot web control panel.

The web code is TypeScript (verified functionally by `npm run lint` / `npm run
build`). These offline checks guard the hard boundaries the prompt requires: the
command API route must be POST-only, dynamic+nodejs, local-only, must spawn the
LM94A gateway via an argv array (NEVER a shell), enforce the whitelist + caps, and
NEVER read or return the Discord webhook value. The control panel must expose only
the allowed actions, gate the heavy ones behind confirm checkboxes, and offer no
free-form command input or order buttons. No MT5, no internet, no Node needed.
"""

from __future__ import annotations

from pathlib import Path

_WEB = Path(__file__).resolve().parent.parent / "lumora-web"
ROUTE = _WEB / "app" / "api" / "gold-bot" / "command" / "route.ts"
PANEL = _WEB / "components" / "gold-bot" / "GoldBotControlPanel.tsx"
CLIENT = _WEB / "lib" / "gold-bot-command-client.ts"
PAGE = _WEB / "app" / "(app)" / "gold-bot" / "page.tsx"

ACTIONS = (
    "preflight",
    "daily_cycle_offline",
    "daily_cycle_guarded_demo",
    "session_review",
    "discord_preview",
    "discord_send",
)


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ── files exist ───────────────────────────────────────────────────────────────────
def test_files_exist():
    for p in (ROUTE, PANEL, CLIENT, PAGE):
        assert p.exists(), f"missing {p}"


# ── route: POST-only, dynamic, nodejs ───────────────────────────────────────────────
def test_route_is_post_only_dynamic_nodejs():
    src = _read(ROUTE)
    assert "export async function POST" in src
    assert "export async function GET" not in src      # no read endpoint here
    assert 'export const dynamic = "force-dynamic"' in src
    assert 'export const runtime = "nodejs"' in src


# ── route: argv spawn, never a shell ────────────────────────────────────────────────
def test_route_uses_execfile_argv_not_shell():
    src = _read(ROUTE)
    assert 'from "node:child_process"' in src
    assert "execFile(" in src
    for forbidden in ("shell: true", "shell:true", "/bin/sh", "execSync", "spawnSync"):
        assert forbidden not in src, f"route must not use {forbidden}"
    # the gateway script is referenced by a fixed constant, not built from input
    assert "scripts/run_gold_bot_command_gateway.py" in src


# ── route: whitelist + caps + risk modes ────────────────────────────────────────────
def test_route_enforces_whitelist_caps_riskmodes():
    src = _read(ROUTE)
    for a in ACTIONS:
        assert f'"{a}"' in src, f"route missing whitelisted action {a}"
    assert "DURATION_MAX = 15" in src
    assert "MAX_TRADES_MAX = 5" in src
    for rm in ("safe", "balanced", "scalp"):
        assert f'"{rm}"' in src
    # aggressive/experimental are NOT offered
    assert "aggressive" not in src.lower()
    assert "experimental" not in src.lower()


# ── route: local-only guard ─────────────────────────────────────────────────────────
def test_route_has_local_only_guard():
    src = _read(ROUTE)
    assert "isLocalRequest" in src
    assert "403" in src
    assert "localhost" in src and "127.0.0.1" in src


# ── route: no secrets, no MT5, no orders, defaults to dry-run ───────────────────────
def test_route_never_reads_or_returns_secrets():
    src = _read(ROUTE)
    # The webhook env NAME/value is never referenced; only the gateway checks it.
    # (A WEBHOOK_RE redaction constant that SCRUBS output is allowed and expected.)
    for forbidden in ("LUMORA_GOLD", "SUPABASE", "SERVICE_ROLE",
                      "MetaTrader5", "order_send", "send_demo_order"):
        assert forbidden not in src, f"route must not reference {forbidden}"
    # the only env it may read is NODE_ENV (for the dev/local guard)
    assert src.count("process.env") == src.count("process.env.NODE_ENV")
    # execute defaults false -> dry-run unless explicitly true
    assert "body.execute === true" in src


def test_route_response_shape_keys():
    src = _read(ROUTE)
    for key in ("ok:", "accepted:", "status:", "action:", "command:",
                "stdoutTail:", "stderrTail:", "warnings:", "runLog:", "redactionsApplied:"):
        assert key in src, f"route response missing {key}"


# ── panel: exactly the allowed actions, no orders, no free input ────────────────────
def test_panel_exposes_only_allowed_actions():
    src = _read(PANEL)
    for a in ACTIONS:
        assert a in src, f"panel missing action {a}"
    # no order / live / free-command surfaces
    for forbidden in ("order_send", "send_demo_order", 'type="text"', "contentEditable",
                      "--allow-live-trading"):
        assert forbidden not in src, f"panel must not contain {forbidden}"
    assert "MetaTrader5" not in src


def test_panel_gates_guarded_demo_behind_checkbox():
    src = _read(PANEL)
    assert "I understand this starts a guarded MT5 demo session" in src
    assert "!confirmDemo" in src                       # button disabled until checked
    assert "confirmGuardedDemo: true" in src


def test_panel_gates_discord_send_behind_checkbox():
    src = _read(PANEL)
    assert "I understand this sends the latest review to Discord" in src
    assert "!confirmDiscord" in src                    # button disabled until checked
    assert "allowDiscordSend: true" in src
    # shows the env var NAME only (copy), never reads/returns a value
    assert "LUMORA_GOLD_DISCORD_WEBHOOK_URL" in src
    assert "never displays the value" in src


def test_panel_copy_is_secret_free_and_uses_local_endpoint():
    src = _read(PANEL)
    assert "runGoldBotCommand" in src
    # the panel talks to the command client, which targets the local POST endpoint
    client = _read(CLIENT)
    assert '"/api/gold-bot/command"' in client
    assert 'method: "POST"' in client


# ── client: typed whitelist ──────────────────────────────────────────────────────────
def test_client_lists_only_whitelisted_actions():
    src = _read(CLIENT)
    for a in ACTIONS:
        assert f'"{a}"' in src, f"client missing action {a}"
    for forbidden in ("order_send", "send_demo_order", "MetaTrader5"):
        assert forbidden not in src


# ── page wires the panel without redesign; status panel still mounted ───────────────
def test_page_mounts_control_and_status_panels():
    src = _read(PAGE)
    assert "GoldBotControlPanel" in src
    assert 'import { GoldBotControlPanel }' in src
    assert "GoldBotStatusPanel" in src                 # read-only panel still present


# ── no Heatmap touched by any LM94B web file ────────────────────────────────────────
def test_no_heatmap_in_web_files():
    for p in (ROUTE, PANEL, CLIENT):
        assert "heatmap" not in _read(p).lower(), f"{p.name} must not touch heatmap"
