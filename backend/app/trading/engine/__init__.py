"""
Trading Engine — Core backtest execution and signal generation.

Exports:
  - BacktestEngine    — Runs a strategy against historical OHLCV data
  - Signal            — Dataclass representing an entry/exit/stop-loss signal
  - TradeRecord       — Dataclass representing a completed round-trip trade
  - BacktestOutput    — Dataclass bundling equity curve, trades, and signals

Data flow:
    arq worker  →  BacktestEngine.run(strategy_def, bars, params)
                    → iterate bars chronologically
                    → apply strategy conditions → generate signals
                    → simulate trades (with commission + slippage)
                    → compute equity curve
                    → return BacktestOutput
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from ..providers import OHLCVBar


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Signal:
    """A trading signal produced by a strategy.

    Fields:
        timestamp:   Bar time when the signal fires.
        signal_type: ``"entry"`` | ``"exit"`` | ``"stop_loss"``.
        direction:   ``"long"`` | ``"short"``.
        price:       Price at which the signal suggests action.
        confidence:  Optional 0.0–1.0 confidence score.
        reasoning:   Optional human-readable explanation.
    """
    timestamp: datetime
    signal_type: str   # entry | exit | stop_loss
    direction: str     # long | short
    price: float
    confidence: float = 1.0
    reasoning: str = ""


@dataclass
class TradeRecord:
    """A completed round-trip trade (entry → exit).

    Fields:
        entry_date:  Entry bar timestamp.
        exit_date:   Exit bar timestamp.
        direction:   ``"long"`` | ``"short"``.
        entry_price: Fill price after slippage.
        exit_price:  Fill price after slippage.
        quantity:    Number of units traded.
        commission:  Total commission (entry + exit).
        pnl:         Net profit/loss after commission.
        pnl_pct:     P&L as a percentage of entry value.
        bars_held:   Number of bars the position was open.
    """
    entry_date: datetime
    exit_date: datetime
    direction: str
    entry_price: float
    exit_price: float
    quantity: float
    commission: float
    pnl: float
    pnl_pct: float
    bars_held: int


@dataclass
class BacktestOutput:
    """Complete backtest result bundle.

    Fields:
        trades:       List of completed round-trip trades.
        signals:      All signals generated during the backtest.
        equity_curve: List of (timestamp, equity_value) tuples.
        final_equity: Portfolio value at end of backtest.
    """
    trades: List[TradeRecord] = field(default_factory=list)
    signals: List[Signal] = field(default_factory=list)
    equity_curve: List[Dict[str, Any]] = field(default_factory=list)
    final_equity: float = 0.0


# ---------------------------------------------------------------------------
# Backtest engine
# ---------------------------------------------------------------------------

class BacktestEngine:
    """Simulates strategy execution against historical OHLCV data.

    Iterates through bars chronologically, applies the strategy's signal
    generator, simulates order fills with configurable commission and
    slippage, and tracks the equity curve.

    Usage:
        engine = BacktestEngine()
        output = engine.run(
            signal_fn=strategy.generate_signals,
            bars=ohlcv_bars,
            params={"fast_period": 10, "slow_period": 50},
            initial_capital=10_000,
            commission=1.00,
            slippage_pct=0.0005,
        )
    """

    def run(
        self,
        signal_fn: Callable[[List[OHLCVBar], Dict], List[Signal]],
        bars: List[OHLCVBar],
        params: Optional[Dict] = None,
        initial_capital: float = 10_000.0,
        commission: float = 1.00,
        slippage_pct: float = 0.0005,
    ) -> BacktestOutput:
        """Execute a full backtest.

        Args:
            signal_fn:       Strategy function: ``(bars, params) → List[Signal]``.
            bars:            Chronologically sorted OHLCV data.
            params:          Strategy parameter dict (passed to signal_fn).
            initial_capital: Starting portfolio value.
            commission:      Fixed commission per trade (entry + exit each).
            slippage_pct:    Slippage as a fraction (0.0005 = 0.05%).

        Returns:
            ``BacktestOutput`` with trades, signals, equity curve, final equity.
        """
        if not bars:
            return BacktestOutput(final_equity=initial_capital)

        params = params or {}

        # Generate all signals from the strategy
        all_signals = signal_fn(bars, params)
        all_signals.sort(key=lambda s: s.timestamp)

        # Build a timestamp → bar index map for O(1) lookups
        bar_index = {b.timestamp: i for i, b in enumerate(bars)}

        # Simulation state
        equity = initial_capital
        position: Optional[_OpenPosition] = None
        trades: List[TradeRecord] = []
        equity_curve: List[Dict[str, Any]] = []

        # Index signals by timestamp for efficient per-bar lookup
        signal_map: Dict[datetime, List[Signal]] = {}
        for sig in all_signals:
            signal_map.setdefault(sig.timestamp, []).append(sig)

        for i, bar in enumerate(bars):
            bar_signals = signal_map.get(bar.timestamp, [])

            for sig in bar_signals:
                if sig.signal_type == "entry" and position is None:
                    # Open a new position
                    fill_price = self._apply_slippage(
                        sig.price, slippage_pct, sig.direction, is_entry=True,
                    )
                    # Size: use all available equity (single-position model)
                    qty = (equity - commission) / fill_price if fill_price > 0 else 0
                    if qty <= 0:
                        continue
                    position = _OpenPosition(
                        entry_date=bar.timestamp,
                        entry_bar_idx=i,
                        direction=sig.direction,
                        entry_price=fill_price,
                        quantity=qty,
                    )
                    equity -= commission  # entry commission

                elif sig.signal_type in ("exit", "stop_loss") and position is not None:
                    # Close the position
                    fill_price = self._apply_slippage(
                        sig.price, slippage_pct, position.direction, is_entry=False,
                    )
                    trade = self._close_position(
                        position, fill_price, bar.timestamp, i, commission,
                    )
                    trades.append(trade)
                    equity += trade.pnl + (position.quantity * position.entry_price)
                    equity -= commission  # exit commission
                    position = None

            # If still in a position, mark-to-market
            if position is not None:
                mtm = position.quantity * bar.close
                equity_curve.append({
                    "timestamp": bar.timestamp.isoformat(),
                    "equity": round(mtm + (equity - position.quantity * position.entry_price), 2),
                })
            else:
                equity_curve.append({
                    "timestamp": bar.timestamp.isoformat(),
                    "equity": round(equity, 2),
                })

        # Force-close any open position at the last bar's close
        if position is not None and bars:
            last_bar = bars[-1]
            fill_price = last_bar.close
            trade = self._close_position(
                position, fill_price, last_bar.timestamp, len(bars) - 1, commission,
            )
            trades.append(trade)
            equity += trade.pnl + (position.quantity * position.entry_price)
            equity -= commission

        final_equity = round(equity, 2)

        return BacktestOutput(
            trades=trades,
            signals=all_signals,
            equity_curve=equity_curve,
            final_equity=final_equity,
        )

    # -- Helpers -----------------------------------------------------------

    @staticmethod
    def _apply_slippage(
        price: float,
        slippage_pct: float,
        direction: str,
        is_entry: bool,
    ) -> float:
        """Adjust price for slippage.

        Entries slip against you (buy higher, sell-short lower).
        Exits slip against you (sell lower, cover higher).

        Args:
            price:        Base fill price.
            slippage_pct: Slippage as a fraction.
            direction:    ``"long"`` or ``"short"``.
            is_entry:     True for entry fills, False for exits.

        Returns:
            Adjusted fill price.
        """
        if direction == "long":
            factor = 1 + slippage_pct if is_entry else 1 - slippage_pct
        else:
            factor = 1 - slippage_pct if is_entry else 1 + slippage_pct
        return round(price * factor, 4)

    @staticmethod
    def _close_position(
        position: "_OpenPosition",
        exit_price: float,
        exit_date: datetime,
        exit_bar_idx: int,
        commission: float,
    ) -> TradeRecord:
        """Build a TradeRecord from an open position and its exit.

        Args:
            position:     The open position to close.
            exit_price:   Fill price at exit.
            exit_date:    Exit bar timestamp.
            exit_bar_idx: Index of the exit bar.
            commission:   Per-trade commission (counted once here for exit).

        Returns:
            Completed ``TradeRecord``.
        """
        qty = position.quantity
        if position.direction == "long":
            gross_pnl = (exit_price - position.entry_price) * qty
        else:
            gross_pnl = (position.entry_price - exit_price) * qty

        total_commission = commission * 2  # entry + exit
        net_pnl = round(gross_pnl - total_commission, 4)
        entry_value = position.entry_price * qty
        pnl_pct = round((net_pnl / entry_value) * 100, 4) if entry_value else 0.0
        bars_held = exit_bar_idx - position.entry_bar_idx

        return TradeRecord(
            entry_date=position.entry_date,
            exit_date=exit_date,
            direction=position.direction,
            entry_price=position.entry_price,
            exit_price=exit_price,
            quantity=qty,
            commission=total_commission,
            pnl=net_pnl,
            pnl_pct=pnl_pct,
            bars_held=bars_held,
        )


@dataclass
class _OpenPosition:
    """Internal state for a position that hasn't been closed yet."""
    entry_date: datetime
    entry_bar_idx: int
    direction: str
    entry_price: float
    quantity: float
