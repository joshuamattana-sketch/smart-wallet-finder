"""
services/gold_bot_equity_sim.py
--------------------------------
LM110A - Equity-curve / risk-of-ruin simulator (RESEARCH-ONLY).

The replay measures per-trade expectancy in POINTS. It says nothing about what a
SIZING choice does to the account. This turns a sequence of per-trade realized
returns (points) into an account equity curve under a risk-% sizing rule, and
reports final balance, max drawdown, and whether it hit RUIN. It exists to show,
from real data, why large per-trade risk (e.g. 80%) blows the account even on a
positive-edge sequence.

Pure: no MT5, no orders, no network. Each trade risks `risk_pct`% of the CURRENT
balance over `sl_points`; a trade returning `r` points changes the balance by
`r / sl_points * risk_pct%` (so a full SL loss == -risk_pct%). Compounds.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass
class EquityResult:
    risk_pct: float
    start_balance: float
    final_balance: float
    return_pct: float
    max_drawdown_pct: float
    ruined: bool
    ruin_at_trade: int | None
    trades: int
    wins: int
    losses: int
    longest_loss_streak: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def simulate_equity(realized_points: list[float | None], *, sl_points: float, risk_pct: float,
                    start_balance: float = 10000.0, ruin_threshold_frac: float = 0.2
                    ) -> EquityResult:
    """
    Compound a sequence of per-trade realized returns (in points) into an equity
    curve. Risk `risk_pct`% per trade over `sl_points`. Ruin = balance falls to/below
    `ruin_threshold_frac` of the start (a real account would be margin-called well
    before zero). Pure; never raises.
    """
    bal = peak = float(start_balance)
    max_dd = 0.0
    ruined = False
    ruin_at: int | None = None
    wins = losses = 0
    streak = longest = 0
    n = 0
    for i, r in enumerate(realized_points, start=1):
        if r is None:
            continue
        n += 1
        if r > 0:
            wins += 1
            streak = 0
        else:
            losses += 1
            streak += 1
            longest = max(longest, streak)
        frac = (r / sl_points) * (risk_pct / 100.0) if sl_points else 0.0
        bal *= (1.0 + frac)
        if bal < 0.0:
            bal = 0.0
        peak = max(peak, bal)
        dd = (peak - bal) / peak if peak > 0 else 0.0
        max_dd = max(max_dd, dd)
        if not ruined and bal <= start_balance * ruin_threshold_frac:
            ruined = True
            ruin_at = i
    return EquityResult(
        risk_pct=round(risk_pct, 2), start_balance=round(start_balance, 2),
        final_balance=round(bal, 2),
        return_pct=round((bal / start_balance - 1.0) * 100.0, 1) if start_balance else 0.0,
        max_drawdown_pct=round(max_dd * 100.0, 1),
        ruined=ruined, ruin_at_trade=ruin_at, trades=n, wins=wins, losses=losses,
        longest_loss_streak=longest,
    )


def extract_realized(rows: list[dict], horizon: int, *, field: str = "realized_return_points"
                     ) -> list[float | None]:
    """Pull the per-TRADE realized return at one horizon from replay rows (skips
    NO_TRADE). Returns the ordered sequence for the equity simulation."""
    out: list[float | None] = []
    h = str(horizon)
    for row in rows:
        if row.get("decision") not in ("LONG", "SHORT"):
            continue
        sc = (row.get("score") or {}).get(h) or {}
        out.append(sc.get(field))
    return out
