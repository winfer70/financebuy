"""
engine/risk.py — Position sizing and risk management models.

Provides the ``PositionSizer`` class with multiple sizing algorithms
that determine how many shares/units to allocate per trade based on
account equity, risk tolerance, and market volatility.

Models:
    - fixed_percentage — risk a fixed % of account per trade
    - fixed_dollar     — risk a fixed dollar amount per trade
    - kelly            — Kelly criterion (full)
    - fractional_kelly — Fractional Kelly (conservative)
    - atr_based        — ATR-scaled position sizing

The backtest engine uses ``PositionSizer`` when the user configures a
risk model; otherwise it defaults to the existing all-in single-position
model.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class SizeResult:
    """Result of a position-sizing calculation.

    Attributes:
        shares:       Number of shares/units to buy.
        position_value: Dollar value of the position.
        risk_amount:  Dollar amount at risk (position_value × risk %).
        model:        Name of the sizing model used.
    """
    shares: float
    position_value: float
    risk_amount: float
    model: str


class PositionSizer:
    """Calculate position sizes using various risk models.

    All methods are static and stateless — call them directly or
    instantiate for method chaining.  The ``default_risk_pct`` is
    used when no explicit risk parameter is provided.

    Args:
        default_risk_pct: Default risk per trade as a fraction
                          (0.02 = 2%).  Used by ``auto_size``.
    """

    def __init__(self, default_risk_pct: float = 0.02) -> None:
        self.default_risk_pct = default_risk_pct

    @staticmethod
    def fixed_percentage(
        account_size: float,
        risk_pct: float,
        entry_price: float,
        stop_loss: float,
    ) -> SizeResult:
        """Size a position by risking a fixed percentage of the account.

        The number of shares is determined by:
            risk_amount = account_size × risk_pct
            shares = risk_amount / |entry_price - stop_loss|

        Args:
            account_size: Total account equity.
            risk_pct:     Risk per trade as a fraction (e.g. 0.02 = 2%).
            entry_price:  Expected fill price.
            stop_loss:    Stop-loss price level.

        Returns:
            ``SizeResult`` with computed share count and risk details.
        """
        risk_per_share = abs(entry_price - stop_loss)
        if risk_per_share == 0 or entry_price <= 0:
            return SizeResult(0, 0, 0, "fixed_percentage")

        risk_amount = account_size * risk_pct
        shares = math.floor(risk_amount / risk_per_share)
        position_value = shares * entry_price

        # Cap at available equity
        if position_value > account_size:
            shares = math.floor(account_size / entry_price)
            position_value = shares * entry_price

        return SizeResult(
            shares=shares,
            position_value=round(position_value, 2),
            risk_amount=round(shares * risk_per_share, 2),
            model="fixed_percentage",
        )

    @staticmethod
    def fixed_dollar(
        account_size: float,
        risk_amount: float,
        entry_price: float,
        stop_loss: float,
    ) -> SizeResult:
        """Size a position by risking a fixed dollar amount.

        Args:
            account_size: Total account equity.
            risk_amount:  Maximum dollar amount to risk.
            entry_price:  Expected fill price.
            stop_loss:    Stop-loss price level.

        Returns:
            ``SizeResult`` with computed share count.
        """
        risk_per_share = abs(entry_price - stop_loss)
        if risk_per_share == 0 or entry_price <= 0:
            return SizeResult(0, 0, 0, "fixed_dollar")

        shares = math.floor(risk_amount / risk_per_share)
        position_value = shares * entry_price

        if position_value > account_size:
            shares = math.floor(account_size / entry_price)
            position_value = shares * entry_price

        return SizeResult(
            shares=shares,
            position_value=round(position_value, 2),
            risk_amount=round(shares * risk_per_share, 2),
            model="fixed_dollar",
        )

    @staticmethod
    def kelly(
        win_rate: float,
        avg_win: float,
        avg_loss: float,
    ) -> float:
        """Full Kelly criterion — optimal fraction of account to wager.

        Formula: f* = (bp - q) / b
            where b = avg_win / |avg_loss|, p = win_rate, q = 1 - p

        Args:
            win_rate: Fraction of winning trades (0.0 to 1.0).
            avg_win:  Average winning trade return (as fraction).
            avg_loss: Average losing trade return (as positive fraction).

        Returns:
            Optimal account fraction (can be > 1.0 or negative).
        """
        if avg_loss == 0 or win_rate <= 0 or win_rate >= 1:
            return 0.0
        b = avg_win / avg_loss
        q = 1 - win_rate
        return round((b * win_rate - q) / b, 6)

    @staticmethod
    def fractional_kelly(
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        fraction: float = 0.5,
    ) -> float:
        """Fractional Kelly — conservative variant.

        Multiplies the full Kelly fraction by *fraction* (default 0.5)
        to reduce variance at the cost of slightly lower expected growth.

        Args:
            win_rate: Fraction of winning trades.
            avg_win:  Average winning return.
            avg_loss: Average losing return (positive).
            fraction: Kelly scaling factor (default 0.5 = half-Kelly).

        Returns:
            Scaled account fraction.
        """
        full = PositionSizer.kelly(win_rate, avg_win, avg_loss)
        return round(max(0, full * fraction), 6)

    @staticmethod
    def atr_based(
        account_size: float,
        risk_pct: float,
        atr: float,
        entry_price: float,
        multiplier: float = 2.0,
    ) -> SizeResult:
        """ATR-based position sizing.

        Uses Average True Range to set a volatility-adjusted stop
        distance, then sizes the position to risk *risk_pct* of account.

            stop_distance = atr × multiplier
            shares = (account_size × risk_pct) / stop_distance

        Args:
            account_size: Total account equity.
            risk_pct:     Risk per trade as a fraction.
            atr:          Current ATR value for the instrument.
            entry_price:  Expected fill price.
            multiplier:   ATR multiplier for stop distance (default 2.0).

        Returns:
            ``SizeResult`` with ATR-scaled share count.
        """
        stop_distance = atr * multiplier
        if stop_distance <= 0 or entry_price <= 0:
            return SizeResult(0, 0, 0, "atr_based")

        risk_amount = account_size * risk_pct
        shares = math.floor(risk_amount / stop_distance)
        position_value = shares * entry_price

        if position_value > account_size:
            shares = math.floor(account_size / entry_price)
            position_value = shares * entry_price

        return SizeResult(
            shares=shares,
            position_value=round(position_value, 2),
            risk_amount=round(shares * stop_distance, 2),
            model="atr_based",
        )

    def auto_size(
        self,
        account_size: float,
        entry_price: float,
        stop_loss: Optional[float] = None,
        atr: Optional[float] = None,
    ) -> SizeResult:
        """Automatically choose and apply the best sizing model.

        Prefers ATR-based sizing when *atr* is provided, otherwise
        falls back to fixed-percentage using the stop-loss distance.
        If neither stop nor ATR is given, allocates the full account.

        Args:
            account_size: Total account equity.
            entry_price:  Expected fill price.
            stop_loss:    Optional stop-loss price level.
            atr:          Optional ATR value.

        Returns:
            ``SizeResult`` from the selected model.
        """
        if atr and atr > 0:
            return self.atr_based(
                account_size, self.default_risk_pct, atr, entry_price,
            )

        if stop_loss is not None and stop_loss > 0:
            return self.fixed_percentage(
                account_size, self.default_risk_pct, entry_price, stop_loss,
            )

        # Fallback: all-in (legacy behaviour)
        shares = math.floor(account_size / entry_price) if entry_price > 0 else 0
        return SizeResult(
            shares=shares,
            position_value=round(shares * entry_price, 2),
            risk_amount=round(shares * entry_price, 2),
            model="all_in",
        )
