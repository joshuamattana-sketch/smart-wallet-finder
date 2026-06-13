"""
tests/test_gold_bot_ui_hierarchy.py
------------------------------------
LM95A / LM95B - Static invariants for the Gold Bot page hierarchy + layout.

Pure-presentation patches: they organize the command room (OPERATE / WATCH /
LEARN / REPORT), make the controls a compact operations bar, and reduce the
status block to a compact strip — WITHOUT changing trading logic, the API, the
gateway whitelist, the required confirmations, or the read-only status surface.
These offline checks guard those boundaries (the visual result is verified by
`npm run lint` / `npm run build`). No Node / MT5 / internet needed.
"""

from __future__ import annotations

from pathlib import Path

_WEB = Path(__file__).resolve().parent.parent / "lumora-web"
PAGE = _WEB / "app" / "(app)" / "gold-bot" / "page.tsx"
CONTROL = _WEB / "components" / "gold-bot" / "GoldBotControlPanel.tsx"
STATUS = _WEB / "components" / "gold-bot" / "GoldBotStatusPanel.tsx"
STRIP = _WEB / "components" / "gold-bot" / "GoldBotStatusStrip.tsx"
SECTION = _WEB / "components" / "gold-bot" / "GoldBotSectionCard.tsx"
CHART = _WEB / "components" / "gold-bot" / "GoldChartInstrument.tsx"
HEATMAP = (
    _WEB / "components" / "charts" / "useHeatmapChartZones.ts",
    _WEB / "lib" / "chart-heatmap-zones.ts",
)

ACTIONS = (
    "preflight",
    "daily_cycle_offline",
    "daily_cycle_guarded_demo",
    "session_review",
    "discord_preview",
    "discord_send",
)
WEB_FILES = (PAGE, CONTROL, STATUS, STRIP, SECTION, CHART)


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ── files exist ───────────────────────────────────────────────────────────────────
def test_files_exist():
    for p in WEB_FILES:
        assert p.exists(), f"missing {p}"


# ── hierarchy: OPERATE / WATCH / LEARN / REPORT ─────────────────────────────────────
def test_page_has_operate_watch_learn_report_hierarchy():
    src = _read(PAGE)
    for header in ("OPERATE", "WATCH", "LEARN", "REPORT"):
        assert header in src, f"page missing section header {header}"
    assert 'import { GoldBotSectionCard }' in src


def test_page_imports_control_status_and_strip():
    src = _read(PAGE)
    assert 'import { GoldBotControlPanel }' in src
    assert 'import { GoldBotStatusPanel }' in src
    assert 'import { GoldBotStatusStrip }' in src
    # the compact strip renders near the top; the full panel is kept in a collapsible details
    assert "GoldBotStatusStrip" in src
    assert "<details" in src


def test_chart_room_present_in_watch_area():
    src = _read(PAGE)
    # the command-room instruments are still mounted (moved up under WATCH)
    for comp in ("GoldChartInstrument", "BotBrainRail", "CommandFeed"):
        assert comp in src, f"page missing room component {comp}"


def test_section_card_is_presentation_only():
    src = _read(SECTION)
    for forbidden in ("useState", "useEffect", "fetch(", "order_send", "MetaTrader5",
                      "process.env"):
        assert forbidden not in src, f"section card must not contain {forbidden}"


def test_status_strip_is_presentation_only():
    src = _read(STRIP)
    # pure: takes a status prop, no fetch / hooks / trading / secrets
    for forbidden in ("useState", "useEffect", "fetch(", "order_send", "send_demo_order",
                      "MetaTrader5", "process.env", "LUMORA_GOLD"):
        assert forbidden not in src, f"status strip must not contain {forbidden}"
    assert "GoldBotStatus" in src        # typed from the read-only loader shape


# ── operations bar: compact toolbar, whitelist intact, no free input ────────────────
def test_control_panel_keeps_only_whitelisted_actions():
    src = _read(CONTROL)
    for a in ACTIONS:
        assert a in src, f"control panel missing action {a}"
    for forbidden in ("order_send", "send_demo_order", 'type="text"', "contentEditable",
                      "--allow-live-trading"):
        assert forbidden not in src, f"control panel must not contain {forbidden}"


def test_result_console_collapsible_and_capped():
    src = _read(CONTROL)
    assert "max-h-[220px]" in src           # console height is capped
    assert "setShowConsole" in src          # console is collapsible
    assert "runGoldBotCommand" in src       # still drives the gateway client


def test_guarded_demo_confirmation_still_required():
    src = _read(CONTROL)
    assert "I understand this starts a guarded MT5 demo session" in src
    assert "!confirmDemo" in src
    assert "confirmGuardedDemo: true" in src


def test_discord_send_confirmation_still_required():
    src = _read(CONTROL)
    assert "I understand this sends the latest review to Discord" in src
    assert "!confirmDiscord" in src
    assert "allowDiscordSend: true" in src
    assert "LUMORA_GOLD_DISCORD_WEBHOOK_URL" in src
    assert "never displays the value" in src


def test_required_safety_copy_present():
    src = _read(CONTROL)
    assert "No live trading. Gateway-whitelisted actions only." in src
    assert "Guarded demo still passes safety supervisor + risk gate." in src


# ── status panel: still read-only telemetry, manual refresh kept ────────────────────
def test_status_panel_still_read_only_with_refresh():
    src = _read(STATUS)
    assert "Read-only status. No trading controls" in src
    assert 'aria-label="Refresh status"' in src
    assert "/api/gold-bot/status" in src
    assert src.count("<button") == 1        # only the refresh button
    for forbidden in ("order_send", "send_demo_order", 'method: "POST"'):
        assert forbidden not in src, f"status panel must not contain {forbidden}"


# ── no live trading, no secrets, no MT5 anywhere in the touched web files ───────────
def test_no_live_or_secrets_or_mt5_in_web_files():
    for p in WEB_FILES:
        src = _read(p)
        for forbidden in ("MetaTrader5", "order_send", "send_demo_order",
                          "--allow-live-trading"):
            assert forbidden not in src, f"{p.name} must not contain {forbidden}"
    assert "LUMORA_GOLD" not in _read(PAGE)
    assert "discord.com/api/webhooks" not in _read(PAGE)


# ── Heatmap files untouched by this patch ───────────────────────────────────────────
def test_no_heatmap_referenced_by_gold_bot_web_files():
    for p in WEB_FILES:
        assert "heatmap" not in _read(p).lower(), f"{p.name} must not reference heatmap"


def test_heatmap_files_still_exist_unchanged_targets():
    for p in HEATMAP:
        assert p.exists(), f"protected heatmap file missing: {p}"


# ── LM95C: simplified mode language ─────────────────────────────────────────────────
def test_mode_language_simplified():
    src = _read(PAGE)
    # the fake overlapping mode tabs and the Aggressive risk mode are gone from the UI
    assert "Aggressive" not in src
    assert "Hunt" not in src
    # clear, non-overlapping state labels are present
    for token in ("ENV DEMO", "EXEC OBSERVE", "LIVE LOCKED", "LEARNING ACTIVE"):
        assert token in src, f"page missing state badge {token}"
    # risk posture matches the gateway modes (safe/balanced/scalp)
    assert '"Scalp"' in src and '"Safe"' in src and '"Balanced"' in src


def test_no_repeated_no_live_prose():
    src = _read(PAGE)
    assert "Live locked · demo guarded" in src        # one concise badge
    assert "no broker connection" not in src           # removed repeated prose


def test_chart_header_uses_demo_language():
    src = _read(CHART)
    assert "Demo environment" in src
    assert "VISUAL MOCK" in src
    assert "DEMO GUARDED" in src
    # stale/confusing VISIBLE labels removed (comments may still describe the mock)
    assert "Gold Spot · M5 · staged session" not in src
    assert "DISABLED" not in src


# ── LM95C: layout — align-start, no forced center min-height ─────────────────────────
def test_grid_uses_align_start_no_center_minheight():
    src = _read(PAGE)
    assert "items-start" in src                        # columns extend independently
    assert "min-h-" not in src                         # no forced blank space on the page
    assert "min-h-" not in _read(CHART)                # chart card is self-sized
