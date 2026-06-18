# Gold Bot — Tactic Library & Inverse Replay Test (LM98C)

A structured, **research-only** library of known XAUUSD tactics plus an offline
inverse replay test that compares ORIGINAL vs INVERSE (LONG↔SHORT) results per
horizon / timeframe / tactic. It answers: *is the bot consistently wrong, or just
using a bad horizon?* — and emits a **preview-only** demo whitelist/blacklist.

Everything here is offline/replay only. No MT5, no orders, no demo/live execution,
no network. No tactic is activated for trading.

- Library template (committed): `docs/gold_bot/templates/tactic_library.sample.json`
- Library service: `services/gold_bot_tactic_library.py`
- Inverse evaluator: `services/gold_bot_inverse_replay_test.py`
- CLIs: `scripts/run_gold_bot_tactic_library_probe.py`, `scripts/run_gold_bot_inverse_replay_test.py`
- Artifacts (gitignored): `data/gold_bot/tactic_tests/inverse_*.json|.md`, `inverse_latest.*`, `demo_whitelist.preview.json`
- Local override (gitignored): `data/gold_bot/tactics/tactic_library.manual.json`

## Tactic library

12 tactics, each with id / name / category / description / allowed_timeframes /
preferred_horizons / setup_tags / entry+invalidation+target summaries / filters /
no_trade_conditions / replay_mapping / status (`research_only`). `replay_mapping.status`:

- `mapped` — tied to an existing replay setup tag (liquidity_sweep_reclaim,
  breakout_retest, fvg_retest, momentum, scalp_momentum, scalp_retest).
- `research_only` / `not_implemented_yet` — no replay feature yet (EMA, VWAP, ATR,
  session-range, mean-reversion bands).

To customize, copy the sample to `data/gold_bot/tactics/tactic_library.manual.json`
(it is gitignored and auto-detected).

## Inverse replay test

Reads the LM85A replay rows and, per scope/horizon, computes ORIGINAL metrics from
each trade's realized directional points (`score[h].dir_return_points`) and the
INVERSE by negating those points + flipping win/loss. Metrics: trades, winrate,
expectancy points, total points, avg win/loss, profit factor, max drawdown, status
(promising / weak / avoid / insufficient). `inverse_edge` ∈ {original_better,
inverse_better, both_bad, both_promising, insufficient}. If replay rows lack
directional fields it says so rather than inventing numbers.

## Commands

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
python -m pytest tests/test_gold_bot_tactic_library_inverse.py -q

python scripts/run_gold_bot_tactic_library_probe.py
python scripts/run_gold_bot_inverse_replay_test.py
python scripts/run_gold_bot_inverse_replay_test.py --horizons 30 --timeframes M1,M5 --min-samples 20
Get-Content "data/gold_bot/tactic_tests/inverse_latest.md"
```

## Sample finding (real replay)

```
Global by horizon:
- h15: original -6.4pt/avoid  | inverse +6.4pt/weak  -> inverse_better
- h30: original +29.3pt/weak  | inverse -29.3pt/weak -> original_better

breakout_retest: h15 original avoid (inverse_better) ; h30 original +164pt/weak
ny_open_momentum: h15 avoid (inverse_better) ; h30 original +51pt/weak
fvg_retest_filtered: avoid both horizons (inverse_better) -> blacklist until filtered
```

Read: short-horizon (h15) direction is largely **backwards** (inverse beats original
nearly everywhere), but **h30 flips most tactics positive**. The bot is mostly
suffering from a too-short horizon, not pure randomness — h30 is the better window.

## Demo whitelist preview (NOT active)

`data/gold_bot/tactic_tests/demo_whitelist.preview.json` lists a suggested
whitelist (tactics whose best original horizon is *promising*), a blacklist (avoid),
and suggested horizons (best first). It is **preview only — not used by demo
execution yet** and is never wired into the trader automatically.

## Safety

No MT5 order send, no demo order send, no demo session runner, no live, no
`--confirm-demo-session`, no `--allow-live-trading`, no arbitrary shell, no
`shell=True`, no network. Tactic status stays `research_only`; this patch changes no
execution, risk, or position-sizing logic.
