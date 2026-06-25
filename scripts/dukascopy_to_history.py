"""
scripts/dukascopy_to_history.py
--------------------------------
Adapt Dukascopy-node M1 CSV exports into the Gold Bot's history format so the
existing replay/resample pipeline can consume them. RESEARCH-ONLY, offline.

Dukascopy-node CSV : timestamp(ms,UTC),open,high,low,close,volume   (bid prices)
Gold Bot history   : time(ISO UTC),open,high,low,close,tick_volume,spread,real_volume

To keep the engine's inputs IDENTICAL to the originally-validated HistData run
(so any difference in results is the PRICE REGIME, not changed inputs), we set:
    tick_volume = 0.0      (HistData/validated runs carried 0.0)
    spread      = 4.0      (the fixed 4pt spread the validation assumed)
    real_volume = 0.0
Rows are merged across all input files, sorted by time, de-duplicated by minute.

    python scripts/dukascopy_to_history.py \
        --in-glob "data/gold_bot/dukascopy/xauusd-m1-*.csv" \
        --out data/gold_bot/history_dukascopy/XAUUSD_M1.csv
"""

from __future__ import annotations

import argparse
import csv
import glob
from datetime import datetime, timezone
from pathlib import Path

FIXED_SPREAD = 4.0
HEADER = ["time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"]


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).isoformat()


def convert(in_paths: list[str], out_path: Path, spread: float) -> tuple[int, int]:
    """Merge/convert dukascopy CSVs → one sorted, de-duped history CSV.

    Returns (rows_written, files_read).
    """
    rows: dict[int, tuple[int, float, float, float, float]] = {}
    files_read = 0
    for p in in_paths:
        files_read += 1
        with open(p, "r", newline="") as f:
            reader = csv.reader(f)
            header = next(reader, None)  # skip header
            for r in reader:
                if not r or len(r) < 5:
                    continue
                try:
                    ms = int(float(r[0]))
                    o, h, l, c = float(r[1]), float(r[2]), float(r[3]), float(r[4])
                except (ValueError, IndexError):
                    continue
                rows[ms] = (ms, o, h, l, c)  # keyed by ms → de-dupes overlaps

    out_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        for ms in sorted(rows):
            _, o, h, l, c = rows[ms]
            w.writerow([_iso(ms), o, h, l, c, 0.0, spread, 0.0])
            written += 1
    return written, files_read


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="dukascopy_to_history")
    ap.add_argument("--in-glob", required=True,
                    help="Glob of dukascopy-node CSV files, e.g. 'data/.../xauusd-m1-*.csv'")
    ap.add_argument("--out", required=True, help="Output history CSV path (…/XAUUSD_M1.csv)")
    ap.add_argument("--spread", type=float, default=FIXED_SPREAD)
    args = ap.parse_args(argv)

    in_paths = sorted(glob.glob(args.in_glob))
    if not in_paths:
        print(f"No input files matched: {args.in_glob}")
        return 1
    written, files_read = convert(in_paths, Path(args.out), args.spread)
    print(f"Read {files_read} file(s) -> wrote {written} M1 bars to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
