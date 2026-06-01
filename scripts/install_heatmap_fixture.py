"""
scripts/install_heatmap_fixture.py
-----------------------------------
Manual, local file tool.

Copies an exported heatmap payload (as produced by
scripts/export_real_heatmap_payload.py) into the Lumora web fixture directory,
under the naming convention the web API expects:

    lumora-web/fixtures/heatmap/{SYMBOL}_{timeframe}.json

It re-stamps the payload's symbol/timeframe and marks it as a fixture so the
`/api/heatmap?source=fixture` route can serve it.

No network, no Supabase, no live worker — just a one-shot local file copy.

Usage:
    python scripts/install_heatmap_fixture.py \
        --input data/heatmap_payload_BTCUSDT.json \
        --symbol BTCUSDT --timeframe 5m

    python scripts/install_heatmap_fixture.py \
        --input out.json --symbol ETHUSDT --timeframe 1h \
        --output-dir lumora-web/fixtures/heatmap
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Repo root (parent of scripts/) — used to resolve the default fixture dir
# regardless of the current working directory.
_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = _REPO_ROOT / "lumora-web" / "fixtures" / "heatmap"

VALID_TIMEFRAMES = ("5m", "15m", "1h", "4h", "1d")


class FixtureInstallError(Exception):
    """Raised for any handled install failure (maps to exit code 1)."""


# ── Validation ────────────────────────────────────────────────────────────────

def validate_payload(payload: object) -> None:
    """
    Rough structural check. Raises FixtureInstallError on the first problem.

    Requires: dict with a string 'symbol', a 'timeBuckets' field, a list
    'cells', and a 'meta' object.
    """
    if not isinstance(payload, dict):
        raise FixtureInstallError("payload must be a JSON object")
    if not payload.get("symbol"):
        raise FixtureInstallError("payload is missing 'symbol'")
    if "timeBuckets" not in payload:
        raise FixtureInstallError("payload is missing 'timeBuckets'")
    if not isinstance(payload.get("cells"), list):
        raise FixtureInstallError("payload 'cells' must be a list")
    if not isinstance(payload.get("meta"), dict):
        raise FixtureInstallError("payload is missing 'meta' object")


# ── Core ──────────────────────────────────────────────────────────────────────

def install_fixture(
    input_path: Path,
    symbol: str,
    timeframe: str,
    output_dir: Path,
) -> tuple[Path, dict]:
    """
    Read, re-stamp, and write the fixture. Returns (output_path, payload).

    Raises:
        FixtureInstallError: input missing, invalid JSON, or invalid payload.
        ValueError:          invalid timeframe.
    """
    if timeframe not in VALID_TIMEFRAMES:
        raise ValueError(
            f"invalid timeframe {timeframe!r}. Allowed: {', '.join(VALID_TIMEFRAMES)}"
        )

    if not input_path.exists():
        raise FixtureInstallError(f"input file not found: {input_path}")

    try:
        raw = input_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FixtureInstallError(f"could not read input {input_path}: {exc}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FixtureInstallError(f"invalid JSON in {input_path}: {exc}") from exc

    validate_payload(payload)

    # Re-stamp identity + fixture metadata.
    sym = symbol.upper()
    payload["symbol"] = sym
    payload["timeframe"] = timeframe
    meta = payload["meta"]
    meta["source"] = "fixture"
    meta["dataSource"] = "fixture"
    meta["installedAt"] = datetime.now(timezone.utc).isoformat()

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{sym}_{timeframe}.json"
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return output_path, payload


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="install_heatmap_fixture",
        description="Install an exported heatmap payload as a Lumora web fixture.",
    )
    parser.add_argument("--input", required=True,
                        help="Path to the exported payload JSON.")
    parser.add_argument("--symbol", required=True,
                        help="Symbol to stamp, e.g. BTCUSDT (uppercased).")
    parser.add_argument("--timeframe", required=True, choices=VALID_TIMEFRAMES,
                        help="Timeframe label: 5m, 15m, 1h, 4h, 1d.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR),
                        dest="output_dir",
                        help="Target fixture directory "
                             "(default: lumora-web/fixtures/heatmap).")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns process exit code (0 ok, 1 on handled error)."""
    args = parse_args(argv)

    try:
        output_path, payload = install_fixture(
            input_path=Path(args.input),
            symbol=args.symbol,
            timeframe=args.timeframe,
            output_dir=Path(args.output_dir),
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except FixtureInstallError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    cells = payload.get("cells", [])
    print("Heatmap fixture installed:")
    print(f"  input     : {args.input}")
    print(f"  output    : {output_path}")
    print(f"  symbol    : {payload.get('symbol')}")
    print(f"  timeframe : {payload.get('timeframe')}")
    print(f"  cells     : {len(cells)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
