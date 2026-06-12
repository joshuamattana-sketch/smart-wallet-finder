# Gold Bot — macro history (LM84B)

Local store for macro instrument history used by the Gold Bot for replay, macro
bias and pattern scoring: **DXY**, **US10Y**, **US02Y**, **VIX** (daily `D1`
first; `H1` optional).

This is the **first no-API bootstrap** — it imports free, manually-downloaded
CSV files. It is **not** the final workflow. Later patches (LM84C / LM84D) will
add automatic `yfinance` / `FRED` fetchers behind the *same* normalized CSV +
`ProviderStatus` interface, so nothing here gets thrown away.

## Free bootstrap workflow

1. Download a free CSV for the instrument (e.g. from a free historical-data
   source you already have access to). No API key, no scraping.
2. Save it anywhere local/temporary (e.g. your Downloads folder).
3. Import + normalize it into this folder:

   ```powershell
   python scripts/run_gold_bot_macro_history_import.py --input "C:\path\to\download.csv" --symbol DXY --timeframe D1 --overwrite
   ```

4. Inspect what landed:

   ```powershell
   python scripts/run_gold_bot_macro_history_probe.py --symbol DXY --timeframe D1 --tail 5
   python scripts/run_gold_bot_data_sources_probe.py
   ```

## Accepted input CSV formats

The importer auto-detects either shape (header row required):

**Format A — OHLC**
```
time,open,high,low,close
2026-06-12,98.12,98.55,97.90,98.30
```

**Format B — value only**
```
time,value
2026-06-12,4.21
```

`time` accepts `YYYY-MM-DD` or full ISO. For value-only series, `close` is set
to the value and OHLC stay blank.

## What is tracked vs ignored

- **Tracked (committed):** this `README.md` and `samples/*.sample.csv`.
- **Ignored (generated):** `data/gold_bot/macro_history/*.csv` and `*.json`
  (the normalized imports + metadata). Never commit downloaded or imported data.

## Try it with the bundled samples

```powershell
python scripts/run_gold_bot_macro_history_import.py --input data/gold_bot/macro_history/samples/DXY_D1.sample.csv --symbol DXY --timeframe D1 --overwrite
python scripts/run_gold_bot_macro_history_import.py --input data/gold_bot/macro_history/samples/US10Y_D1.sample.csv --symbol US10Y --timeframe D1 --overwrite
python scripts/run_gold_bot_macro_history_import.py --input data/gold_bot/macro_history/samples/US02Y_D1.sample.csv --symbol US02Y --timeframe D1 --overwrite
python scripts/run_gold_bot_macro_history_import.py --input data/gold_bot/macro_history/samples/VIX_D1.sample.csv --symbol VIX --timeframe D1 --overwrite
```
