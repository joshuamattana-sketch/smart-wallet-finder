"""
tests/test_heatmap_pipeline_integration.py
--------------------------------------------
Integration tests for the full liquidity-map data pipeline:

  Binance depth snapshot (mock)
  → build_heatmap_cells      (orderbook_depth_bucketer)
  → build_heatmap_matrix     (heatmap_matrix_builder)
  → build_heatmap_api_payload (heatmap_api_payload)

No real API calls, no network access, no Supabase writes.
"""

from services.orderbook_depth_bucketer import build_heatmap_cells
from services.heatmap_matrix_builder import build_heatmap_matrix
from services.heatmap_api_payload import build_heatmap_api_payload, validate_heatmap_api_payload


# ── Mock data ─────────────────────────────────────────────────────────────────

def _lvl(price: float, qty: float) -> dict:
    return {"price": price, "quantity": qty, "usd": round(price * qty, 2)}


# Three synthetic snapshots spread over time.
# Large qty levels create walls; small qty levels fill out the normal book.
_SNAPSHOTS = [
    {
        "symbol": "BTCUSDT",
        "captured_at": "2026-06-01T12:00:00+00:00",
        "bids": [
            _lvl(67490.0, 0.5),
            _lvl(67480.0, 0.8),
            _lvl(67470.0, 1.2),
            _lvl(67460.0, 0.6),
            _lvl(67450.0, 0.9),
            _lvl(67420.0, 25.0),   # strong bid wall
            _lvl(67410.0, 0.4),
            _lvl(67400.0, 0.7),
        ],
        "asks": [
            _lvl(67500.0, 0.5),
            _lvl(67510.0, 0.8),
            _lvl(67520.0, 1.1),
            _lvl(67530.0, 0.6),
            _lvl(67560.0, 22.0),   # strong ask wall
            _lvl(67570.0, 0.4),
            _lvl(67580.0, 0.9),
            _lvl(67590.0, 0.3),
        ],
    },
    {
        "symbol": "BTCUSDT",
        "captured_at": "2026-06-01T12:05:00+00:00",
        "bids": [
            _lvl(67488.0, 0.6),
            _lvl(67478.0, 1.0),
            _lvl(67468.0, 0.7),
            _lvl(67420.0, 28.0),   # wall persists, grows slightly
            _lvl(67408.0, 0.5),
            _lvl(67398.0, 0.8),
        ],
        "asks": [
            _lvl(67502.0, 0.4),
            _lvl(67512.0, 0.9),
            _lvl(67558.0, 20.0),   # wall shifts slightly
            _lvl(67568.0, 0.5),
            _lvl(67578.0, 1.1),
        ],
    },
    {
        "symbol": "BTCUSDT",
        "captured_at": "2026-06-01T12:10:00+00:00",
        "bids": [
            _lvl(67492.0, 0.7),
            _lvl(67482.0, 0.9),
            _lvl(67422.0, 30.0),   # wall still present
            _lvl(67412.0, 0.6),
            _lvl(67402.0, 1.0),
        ],
        "asks": [
            _lvl(67504.0, 0.5),
            _lvl(67514.0, 0.7),
            _lvl(67562.0, 24.0),   # ask wall
            _lvl(67572.0, 0.8),
            _lvl(67582.0, 0.4),
        ],
    },
]

_WALL_THRESHOLD = 500_000.0   # ~25 BTC × 67 420 ≈ 1.7 M USD — walls will hit this
_PRICE_STEP = 10.0


def _build_payload(snapshots=None, wall_threshold=_WALL_THRESHOLD):
    snaps = snapshots if snapshots is not None else _SNAPSHOTS
    frames = [build_heatmap_cells(s, price_step=_PRICE_STEP,
                                  wall_threshold_usd=wall_threshold) for s in snaps]
    matrix = build_heatmap_matrix(frames)
    return build_heatmap_api_payload(matrix, timeframe="5m", exchange="binance_spot")


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestFullHeatmapPipeline:

    def test_full_heatmap_pipeline_builds_valid_payload(self):
        payload = _build_payload()

        assert payload["symbol"] == "BTCUSDT"
        assert payload["timeframe"] == "5m"
        assert len(payload["cells"]) > 0, "cells must not be empty"
        assert len(payload["timeBuckets"]) == 3, "one time bucket per snapshot"
        assert payload["priceMin"] is not None
        assert payload["priceMax"] is not None
        assert payload["priceMin"] < payload["priceMax"]
        assert isinstance(payload["summary"], dict)
        assert isinstance(payload["meta"], dict)
        assert payload["meta"]["wallCount"] >= 1, "at least one wall expected"
        assert validate_heatmap_api_payload(payload) is True

    def test_pipeline_preserves_bid_and_ask_intensity(self):
        payload = _build_payload()
        cells = payload["cells"]

        bid_cells  = [c for c in cells if c["bid"] > 0]
        ask_cells  = [c for c in cells if c["ask"] > 0]

        assert len(bid_cells) > 0, "at least one cell with bid intensity"
        assert len(ask_cells) > 0, "at least one cell with ask intensity"

        # All intensities must stay within valid range
        for c in cells:
            assert 0.0 <= c["bid"]   <= 100.0
            assert 0.0 <= c["ask"]   <= 100.0
            assert 0.0 <= c["total"] <= 100.0

    def test_pipeline_handles_empty_snapshots_gracefully(self):
        empty_snaps = [
            {"symbol": "BTCUSDT", "captured_at": "2026-06-01T13:00:00+00:00",
             "bids": [], "asks": []},
        ]
        payload = _build_payload(snapshots=empty_snaps)

        assert validate_heatmap_api_payload(payload) is True
        assert payload["cells"] == []
        assert payload["timeBuckets"] == [] or isinstance(payload["timeBuckets"], list)

    def test_pipeline_wall_detection_survives_to_payload(self):
        payload = _build_payload()
        walls = payload["walls"]

        assert len(walls) >= 1, "walls must reach final payload"
        for w in walls:
            assert "price_bucket" in w
            assert "side" in w
            assert "label" in w
            assert w["side"] in ("bid", "ask", "mixed")

        # At least one bid wall and one ask wall expected from our mock data
        bid_walls = [w for w in walls if w["side"] == "bid"]
        ask_walls = [w for w in walls if w["side"] == "ask"]
        assert len(bid_walls) >= 1, "expected at least one bid wall"
        assert len(ask_walls) >= 1, "expected at least one ask wall"
