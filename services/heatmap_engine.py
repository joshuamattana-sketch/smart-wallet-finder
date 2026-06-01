"""
services/heatmap_engine.py
---------------------------
Liquidity Heatmap Engine for the Pro Trading Terminal.

Transforms an OrderBookSnapshot into a list of HeatmapCells
that can be rendered as a Bookmap-style liquidity wall map.

Concepts:
  - Each cell represents a price level on one side (bid or ask).
  - Intensity (0–100) reflects how large that level is relative to
    the deepest level in the visible range.
  - Hot zones are cells with intensity >= a configurable threshold.
  - The demo data gives a realistic BTC-like price ladder for UI testing.

Rules:
- No Streamlit imports.
- No network calls.
- No external dependencies beyond stdlib.
- No silent except pass.
- All intensities are clamped to [0, 100].
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# ── Side constants ────────────────────────────────────────────────────────────

SIDE_BID = "bid"
SIDE_ASK = "ask"

# ── HeatmapCell dataclass ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class HeatmapCell:
    """
    A single price level in the liquidity heatmap.

    Attributes:
        price:     Price of the level in quote currency (e.g. USD).
        side:      "bid" or "ask".
        size_usd:  Notional size of the level in USD.
        intensity: 0–100. Relative heat: 100 = largest level in view.
        label:     Human-readable label, e.g. "$5.2M", "WALL".
    """
    price:     float
    side:      str
    size_usd:  float
    intensity: int
    label:     str = ""

    def __post_init__(self) -> None:
        if self.side not in (SIDE_BID, SIDE_ASK):
            raise ValueError(
                f"Invalid side '{self.side}'. Must be 'bid' or 'ask'."
            )
        if self.price < 0:
            raise ValueError(f"price must be >= 0, got {self.price}")
        if self.size_usd < 0:
            raise ValueError(f"size_usd must be >= 0, got {self.size_usd}")
        if not (0 <= self.intensity <= 100):
            raise ValueError(
                f"intensity must be in [0, 100], got {self.intensity}"
            )

    @property
    def is_hot(self) -> bool:
        return self.intensity >= 70

    @property
    def is_wall(self) -> bool:
        return self.intensity >= 85

    @property
    def is_bid(self) -> bool:
        return self.side == SIDE_BID

    @property
    def is_ask(self) -> bool:
        return self.side == SIDE_ASK


# ── Intensity calculation ─────────────────────────────────────────────────────

def calculate_intensity(size_usd: float, max_size_usd: float) -> int:
    """
    Calculate the heat intensity of a price level as an integer in [0, 100].

    Intensity is the linear ratio of this level's size to the largest
    level in the visible range. A level matching max_size_usd scores 100.
    A level with zero size scores 0.

    Args:
        size_usd:     USD size of this level. Must be >= 0.
        max_size_usd: USD size of the largest level in the set. Must be > 0.

    Returns:
        Integer in [0, 100].

    Raises:
        ValueError: if size_usd < 0 or max_size_usd <= 0.

    Examples:
        >>> calculate_intensity(5_000_000, 10_000_000)
        50
        >>> calculate_intensity(10_000_000, 10_000_000)
        100
        >>> calculate_intensity(0, 10_000_000)
        0
    """
    if size_usd < 0:
        raise ValueError(f"size_usd must be >= 0, got {size_usd}")
    if max_size_usd <= 0:
        raise ValueError(f"max_size_usd must be > 0, got {max_size_usd}")
    raw = (size_usd / max_size_usd) * 100.0
    return int(_clamp(raw, 0.0, 100.0))


# ── Build heatmap from orderbook ──────────────────────────────────────────────

def build_heatmap_from_orderbook(
    snapshot,                   # OrderBookSnapshot from core.models
    levels: int = 20,
) -> list[HeatmapCell]:
    """
    Build a list of HeatmapCells from an OrderBookSnapshot.

    Takes the top `levels` bids and asks, computes intensity relative
    to the single largest level across both sides, and assigns labels
    to notable walls.

    Args:
        snapshot: OrderBookSnapshot (from connectors or tests).
                  Must have .bids, .asks lists of OrderBookLevel objects.
        levels:   Number of price levels to include per side. Default 20.

    Returns:
        List of HeatmapCell, bids first (sorted descending by price),
        then asks (sorted ascending). Returns [] for empty books.

    Raises:
        TypeError:  if snapshot is not a valid snapshot object.
        ValueError: if levels < 1.
    """
    if not hasattr(snapshot, "bids") or not hasattr(snapshot, "asks"):
        raise TypeError(
            f"snapshot must have 'bids' and 'asks' attributes, "
            f"got {type(snapshot).__name__}"
        )
    if levels < 1:
        raise ValueError(f"levels must be >= 1, got {levels}")

    bids = list(snapshot.bids[:levels])
    asks = list(snapshot.asks[:levels])

    if not bids and not asks:
        return []

    # Find max size across all levels for normalisation
    def _usd(lvl) -> float:
        return lvl.usd_size if lvl.usd_size > 0 else (lvl.price * lvl.qty)

    all_sizes = [_usd(lvl) for lvl in bids + asks]
    max_size  = max(all_sizes) if all_sizes else 0.0

    if max_size <= 0:
        return []

    cells: list[HeatmapCell] = []

    for lvl in bids:
        size      = _usd(lvl)
        intensity = calculate_intensity(size, max_size)
        label     = _make_label(size, intensity)
        cells.append(HeatmapCell(
            price=round(lvl.price, 8),
            side=SIDE_BID,
            size_usd=round(size, 2),
            intensity=intensity,
            label=label,
        ))

    for lvl in asks:
        size      = _usd(lvl)
        intensity = calculate_intensity(size, max_size)
        label     = _make_label(size, intensity)
        cells.append(HeatmapCell(
            price=round(lvl.price, 8),
            side=SIDE_ASK,
            size_usd=round(size, 2),
            intensity=intensity,
            label=label,
        ))

    return cells


# ── Hot zone detection ────────────────────────────────────────────────────────

def detect_hot_zones(
    cells: list[HeatmapCell],
    min_intensity: int = 70,
) -> list[HeatmapCell]:
    """
    Filter cells to those with intensity >= min_intensity.

    Hot zones are price levels with unusually large liquidity —
    often acting as support/resistance walls.

    Args:
        cells:         List of HeatmapCell objects.
        min_intensity: Minimum intensity threshold. Default 70.

    Returns:
        Filtered list sorted by intensity descending.
        Empty list if no cells qualify.

    Raises:
        ValueError: if min_intensity < 0 or > 100.
        TypeError:  if cells is not a list.

    Examples:
        >>> cells = [HeatmapCell(100.0, "bid", 1000.0, 90, "WALL"), ...]
        >>> detect_hot_zones(cells, min_intensity=85)
        [HeatmapCell(price=100.0, side='bid', ...)]
    """
    if not isinstance(cells, list):
        raise TypeError(f"cells must be a list, got {type(cells).__name__}")
    if not (0 <= min_intensity <= 100):
        raise ValueError(
            f"min_intensity must be in [0, 100], got {min_intensity}"
        )

    hot = [c for c in cells if c.intensity >= min_intensity]
    hot.sort(key=lambda c: c.intensity, reverse=True)
    return hot


# ── Demo data ─────────────────────────────────────────────────────────────────

def demo_heatmap_cells() -> list[HeatmapCell]:
    """
    Return a realistic demo list of HeatmapCells for UI testing.

    Simulates a BTC/USDT order book around $67,400 mid price.
    Includes a prominent bid wall (support) and ask wall (resistance).

    Returns:
        List of 40 HeatmapCell objects (20 bids, 20 asks).
    """
    mid = 67_400.0
    cells: list[HeatmapCell] = []

    # Bid size profile: wall at -0.4% (67,130), elevated at -0.1%
    _bid_sizes: dict[int, float] = {
        0:  320_000,    # best bid — moderate
        1:  280_000,
        2:  180_000,
        3:  4_800_000,  # WALL — key support
        4:  210_000,
        5:  150_000,
        6:  90_000,
        7:  340_000,    # secondary wall
        8:  70_000,
        9:  55_000,
        10: 40_000,
        11: 35_000,
        12: 1_200_000,  # medium wall
        13: 30_000,
        14: 25_000,
        15: 20_000,
        16: 18_000,
        17: 15_000,
        18: 12_000,
        19: 10_000,
    }

    # Ask size profile: wall at +0.3% (67,602), elevated at +0.6%
    _ask_sizes: dict[int, float] = {
        0:  290_000,    # best ask — moderate
        1:  260_000,
        2:  5_200_000,  # WALL — key resistance
        3:  200_000,
        4:  130_000,
        5:  85_000,
        6:  370_000,    # secondary ask wall
        7:  60_000,
        8:  48_000,
        9:  1_500_000,  # medium resistance
        10: 38_000,
        11: 32_000,
        12: 28_000,
        13: 24_000,
        14: 20_000,
        15: 17_000,
        16: 14_000,
        17: 12_000,
        18: 10_000,
        19: 8_000,
    }

    max_size = max(
        max(_bid_sizes.values()),
        max(_ask_sizes.values()),
    )

    # Bids: prices descending from mid - tick
    tick = mid * 0.00005  # ~$3.37 per tick
    for i in range(20):
        price     = round(mid - (i + 1) * tick, 2)
        size      = _bid_sizes.get(i, 10_000)
        intensity = calculate_intensity(size, max_size)
        label     = _make_label(size, intensity)
        cells.append(HeatmapCell(
            price=price, side=SIDE_BID,
            size_usd=size, intensity=intensity, label=label,
        ))

    # Asks: prices ascending from mid + tick
    for i in range(20):
        price     = round(mid + (i + 1) * tick, 2)
        size      = _ask_sizes.get(i, 8_000)
        intensity = calculate_intensity(size, max_size)
        label     = _make_label(size, intensity)
        cells.append(HeatmapCell(
            price=price, side=SIDE_ASK,
            size_usd=size, intensity=intensity, label=label,
        ))

    return cells


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_label(size_usd: float, intensity: int) -> str:
    """Generate a compact label for a heatmap cell."""
    size_str = _fmt_size(size_usd)
    if intensity >= 85:
        return f"WALL {size_str}"
    if intensity >= 70:
        return f"HOT {size_str}"
    if intensity >= 40:
        return size_str
    return ""


def _fmt_size(size_usd: float) -> str:
    if size_usd >= 1_000_000:
        return f"${size_usd / 1_000_000:.1f}M"
    if size_usd >= 1_000:
        return f"${size_usd / 1_000:.0f}K"
    return f"${size_usd:.0f}"


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


if __name__ == "__main__":
    # ── Self-tests ────────────────────────────────────────────────────────────

    # calculate_intensity
    assert calculate_intensity(5_000_000, 10_000_000) == 50
    assert calculate_intensity(10_000_000, 10_000_000) == 100
    assert calculate_intensity(0, 10_000_000) == 0
    assert calculate_intensity(3_333_333, 10_000_000) == 33

    try:
        calculate_intensity(-1, 1000)
        assert False
    except ValueError:
        pass
    try:
        calculate_intensity(100, 0)
        assert False
    except ValueError:
        pass

    # HeatmapCell
    c = HeatmapCell(price=100.0, side="bid", size_usd=50_000, intensity=45)
    assert not c.is_hot
    assert not c.is_wall
    assert c.is_bid
    assert not c.is_ask

    hot_c = HeatmapCell(price=100.0, side="ask", size_usd=5_000_000, intensity=90, label="WALL")
    assert hot_c.is_hot
    assert hot_c.is_wall
    assert hot_c.is_ask

    try:
        HeatmapCell(price=100, side="invalid", size_usd=1000, intensity=50)
        assert False
    except ValueError:
        pass
    try:
        HeatmapCell(price=100, side="bid", size_usd=1000, intensity=150)
        assert False
    except ValueError:
        pass

    # detect_hot_zones
    cells = [
        HeatmapCell(100.0, "bid", 5_000_000, 90, "WALL"),
        HeatmapCell(99.0,  "bid",   500_000, 50, ""),
        HeatmapCell(101.0, "ask", 3_000_000, 75, "HOT"),
        HeatmapCell(98.0,  "bid",   100_000, 20, ""),
    ]
    hot = detect_hot_zones(cells, min_intensity=70)
    assert len(hot) == 2
    assert hot[0].intensity >= hot[1].intensity

    assert detect_hot_zones([], min_intensity=70) == []

    try:
        detect_hot_zones("not a list")
        assert False
    except TypeError:
        pass
    try:
        detect_hot_zones([], min_intensity=150)
        assert False
    except ValueError:
        pass

    # build_heatmap_from_orderbook — import here to avoid circular in module load
    import sys
    sys.path.insert(0, ".")
    from core.models import OrderBookLevel, OrderBookSnapshot
    bids = [OrderBookLevel(67_390.0, 5.0, 336_950.0),
            OrderBookLevel(67_380.0, 2.0, 134_760.0)]
    asks = [OrderBookLevel(67_410.0, 3.0, 202_230.0),
            OrderBookLevel(67_420.0, 8.0, 539_360.0)]
    snap = OrderBookSnapshot("BTCUSDT", "binance", 0, bids=bids, asks=asks)
    hm = build_heatmap_from_orderbook(snap, levels=10)
    assert len(hm) == 4
    assert all(isinstance(c, HeatmapCell) for c in hm)
    assert all(0 <= c.intensity <= 100 for c in hm)
    # largest cell should have intensity 100
    assert max(c.intensity for c in hm) == 100

    # empty snapshot
    empty = OrderBookSnapshot("X", "y", 0)
    assert build_heatmap_from_orderbook(empty) == []

    # bad input
    try:
        build_heatmap_from_orderbook("not a snapshot")
        assert False
    except TypeError:
        pass
    try:
        build_heatmap_from_orderbook(snap, levels=0)
        assert False
    except ValueError:
        pass

    # demo_heatmap_cells
    demo = demo_heatmap_cells()
    assert len(demo) == 40
    assert sum(1 for c in demo if c.side == "bid") == 20
    assert sum(1 for c in demo if c.side == "ask") == 20
    assert all(0 <= c.intensity <= 100 for c in demo)
    assert any(c.is_wall for c in demo)
    hot = detect_hot_zones(demo, min_intensity=70)
    assert len(hot) >= 2

    print("services/heatmap_engine.py — all assertions passed.")
