# Patch Context Mini

## Current architecture

- `app.py` should stay thin and should not be edited unless explicitly requested.
- UI files should only be edited in UI-specific patches.
- API routes should only be edited in API-specific patches.
- `services/` contains pure Python engines and business logic.
- `tests/` contains deterministic local tests.
- `docs/brain/` contains project context and terminal commands.
- Supabase SQL lives in `supabase/`.
- Discord logic is split into formatter, sender, and filter services.
- Signal flow: heatmap history -> wall events -> persistence features -> setup classifier -> signal builder -> signal journal -> alerts.
- Whale flow starts with whale event detection, then formatter/filter/sender later.
- Whale live pipeline: Binance aggTrade WS -> normalize -> detect_whale_events -> filter -> (Discord | JSONL journal | Supabase whale_events).
- Whale read path: website /api/whale-alerts reads Supabase -> local JSONL journal -> mock alerts (server-side, 3-tier fallback).
- Futures/leverage context (LM64 series, planned): Binance futures aggTrade + funding/OI poller + force-order stream feed `MarketContext` (funding_rate, oi_change_pct, derived leverage_heat) into existing whale events without claiming individual-account leverage. See `docs/brain/LM64_FUTURES_WHALE_SOURCE_DISCOVERY.md`.
- Landing page redesign (LM67 series, planned): signature hero "The Lumora Field" — a 2.5D SVG/CSS market pressure visualization (price path, liquidity bands, whale pulses, futures drift, sweep zones, Current Read badge) replacing the generic hero; new sections on Panel/lm-* design language. See `docs/brain/LM67_LANDING_PAGE_DISCOVERY.md`.
- Global visual cleanup (LM69 series, planned): art-directed app-wide cleanup — one instrument per page, 3-level Surface system (border is earned), StatusChip semantic re-token (demo = gray, amber = risk/stale only), 5 typography roles, telemetry behind "System" Disclosures, debug UI out of product. Plan in `docs/brain/LM69_GLOBAL_VISUAL_CLEANUP_DISCOVERY.md`. Sequence: LM69B shell+primitives, LM69C terminal, LM69D dashboard/IA, LM69E status/typography standardization.
- Unified Intelligence Chart (LM68 series): lightweight-charts candlestick base with optional Lumora overlays (liquidity zones, whale markers, futures context, current read, sweep risk) behind three view modes Clean/Assisted/Full Intel; layered architecture + data contracts in `docs/brain/LM68_UNIFIED_INTELLIGENCE_CHART_DISCOVERY.md`. LM68B (mock panel) and LM68C (live Binance candles via public REST klines + kline WS in `lumora-web/lib/binance-klines.ts` + `useBinanceKlines`, with REST-poll and demo fallbacks) are done; LM68D whale markers are live (client hook `useWhaleChartEvents` polls /api/whale-alerts 30s, `lib/chart-whale-events.ts` maps real events to candle-snapped markers; demo markers remain the fallback); heatmap zones / read overlays still demo.

- Gold Bot (LM73/LM74 series): private XAUUSD daytrading assistant — paper/demo first, no live trading. UI command room lives at `lumora-web/app/(app)/gold-bot/` (status strip with Watch/Hunt/Review + risk modes Safe/Balanced/Aggressive, staged XAUUSD chart instrument, bot-brain rail, engine feed, planned modules for daily limits/funded guardrails/execution targets/Discord review). Engine architecture (sources → memory → replay → strategies → risk → manager → execution → journal → review) is specified in `docs/brain/LM74_GOLD_BOT_CORE_ENGINE_BLUEPRINT.md`; planned code home `services/goldbot/`, MT5 demo as first real execution path behind safety flags (MT5_DEMO_ONLY, LIVE_TRADING_ENABLED=false, ALLOW_REAL_ORDERS=false, KILL_SWITCH). Risk Engine has final authority: +10%/day aspirational only, -7%/day hard stop, no martingale/revenge, news lockout; self-learning = journal + analytics + owner-approved suggestions only.

## Completed patches

- LM45 heatmap history
- LM46 wall events
- LM47 wall persistence features
- LM48 setup classifier
- LM49 signal builder
- LM50 signal journal
- LM51A discord formatter
- LM51B discord webhook sender
- LM51C discord alert filter
- LM52A whale alert engine
- LM63A whale source discovery (recommendation only)
- LM63B Binance aggTrade collector
- LM63C whale live smoke + Discord pipeline
- LM63D per-symbol whale thresholds
- LM63E local JSONL whale event journal
- LM63F whale feed API + website fallback to mock
- LM63G Supabase whale_events schema (+ unique constraint fix)
- LM63H Supabase writer + smoke --target wiring
- LM63I website Supabase tier (Supabase -> journal -> mock)
- LM63J whale worker mode (--forever, --heartbeat-interval, env config)
- LM63K whale worker deployment docs
- LM64A futures whale source discovery (recommendation only)
- LM64B Binance Futures aggTrade connector (--market spot|futures; no schema change)
- LM67A landing page discovery — The Lumora Field (plan only, no frontend code)
- LM67B–LM67F landing page implementation — Lumora Field hero, signal tape, feature grid, cinematic polish, dynamic headline (framer-motion)
- LM68A unified intelligence chart discovery (plan only, no frontend code)
- LM68B intelligence chart mock panel (lightweight-charts, Clean/Assisted/Full Intel modes, overlay toggles, mock scene; mounted on Terminal + Liquidity Map)
- LM68C Binance kline live candles (public REST snapshot + kline WS, REST poll fallback, demo fallback on failure; overlays still demo, derived relative to displayed candle range)
- LM69A global visual cleanup discovery (plan only, no frontend code)
- LM69B app shell + panel primitives (PageShell, MetricStrip, Panel levels default/focus/subtle, StatusBadge re-token with gray `demo` variant, flat app bg, TopNav UTC clock; all five app pages adopted)
- LM69C UI texture + interaction pass (Panel depth: inner highlight + soft drop on default, instrument shadow + built-in cyan top stripe on focus; StatusBadge faint matching borders; PageShell header hairline; TopNav LIVE chip + active icon tint; chart header group dividers, aria-pressed segments, overlay toggles with cyan indicator dots, bias-railed read chip, two-sided honesty footer; Dashboard's oversized Current Read card replaced by a one-line command strip — bias/score/conf/risk/action/price/status — with watchlist + whale tape in the right rail)
- LM69C dock + visual liveness pass (`components/ui/IntelligenceDock.tsx`: dark glass pill with icon controls — hover halo + 1px lift + compact tooltip + active dot + optional live badge, tones cyan/violet/emerald/rose/amber, CSS transitions with motion-reduce gating; chart header mode presets Clean/Assisted/Full Intel (violet) + overlay channels Heatmap/Whales/Pressure/Read (semantic tones) now live in the dock; chart pane gained faint cyan/violet edge-light hairlines and an emerald halo on the LIVE badge; Terminal lost the perpetual walls spinner and gained a cyan-edged pressure caption)
- LM69C nav refinement fix (TopNav rebuilt as a dark-glass command bar styled fully in-component — violet-tiled logo mark + LUMORA + TERMINAL suffix, active link = soft violet inset pill with luminous violet→cyan bottom edge, hover = 1px lift + inner highlight (motion-reduce gated), UTC clock + LIVE dot fused into one bordered status capsule, faint violet edge-light hairline along the nav bottom; the old global .lm-topnav/.lm-nav-link classes are unused by TopNav. Chart fix: the futures pressure strip is now an absolute bottom overlay INSIDE the chart pane — toggling Pressure/Read no longer changes the instrument height, nothing renders below the chart)
- LM68D real whale markers on chart (client `useWhaleChartEvents` polls /api/whale-alerts; `lib/chart-whale-events.ts` filters by symbol, snaps event_ts to candle buckets, dedupes per bucket+side, caps Assisted 6 / Full 12 strongest; BUY below / SELL above bar, HIGH risk = bigger marker, short $-labels; loader exposes raw event_ts/notional_usd/severity/source_type on WhaleAlertView; footer + dock hint show whales live/fallback/none; demo markers stay as fallback)
- LM69C final nav/dashboard/tooltip fix (dock tooltips now float ABOVE each control — minimal-dock language, fade+rise on hover, hidden under md; IntelligenceChartPanel dropped its panel-level overflow-hidden so upward tooltips aren't clipped (the chart pane clips itself, footer rounds its own corners); TopNav pushed further: navy gradient glass, links ride inside ONE recessed channel rail, active = violet gradient pill + violet→cyan luminous edge, hover halo + press scale, gradient brand tile with soft glow, UTC/LIVE in a matching recessed rail; app backdrop is deep navy `#0a0b10` with a faint indigo top wash (layout.tsx); Dashboard rescue: read strip gained a bias-colored left edge + faint cyan→violet interior wash + glowing live price, setups rows carry bias side-rails with bias-toned score bars, watchlist confidence bars are bias-toned, subtle panels get a faint white ring for finish)

- LM73A gold bot command room page (`/gold-bot` route + Gold Bot nav tab with amber icon accent; paper-mode page with status header, bot brain, zone detection, risk engine, paper trading, learning journal — all staged data)
- LM73C gold bot visual upgrade (three-column command room: center staged XAUUSD SVG chart instrument with sweep+reclaim narrative/FVG/key levels/watching ring, left bot-brain rail with analytical meters + detector stack, right engine feed + risk permission + paper state; gold ambient field, scanner sweeps, Watch/Hunt/Review mode tabs, command-room footer)
- LM73D gold bot intelligence content pass (risk modes Safe/Balanced/Aggressive in status strip, TARGET +10% GOAL / MAX LOSS -7% HARD STOP chips, trade-permission evaluation checklist with STAY FLAT verdict, macro/spread meters, planned-modules band: daily limits / funded guardrails FTMO·The5ers·Alpha·Custom / execution targets with live adapter LOCKED / Discord review; feed types STRATEGY/NEWS/LEARNING/DISCORD/EXEC; 9-field journal contract with owner-approval rule)
- LM74A gold bot core engine blueprint (plan only, no code: `docs/brain/LM74_GOLD_BOT_CORE_ENGINE_BLUEPRINT.md` — 10-layer architecture, frozen-dataclass pipeline MarketContext→StrategySignal→RiskDecision→TradeIdea→OrderResult→ExitRecord→JournalEntry→ReviewReport, 7 strategy families, MT5 demo execution behind safety flags, historical backfill + no-lookahead replay learning, implementation sequence LM74B–LM75x)

## Rules

- No UI unless requested.
- No API route changes unless requested.
- No secrets.
- No commit/push.
- Tests must be local and deterministic.
- No network in tests.
- Keep patches small.
- Edit only listed files.

## Standard test commands

```bash
python -m pytest <target_test>
python -m compileall services tests