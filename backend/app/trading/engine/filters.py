"""
engine/filters.py — Signal filters that gate entry/exit signals.

Provides composable filter functions that evaluate a candidate signal
and return it unchanged (pass) or ``None`` (blocked).  The backtest
engine and live signal pipeline apply filters *after* a strategy
produces a raw signal and *before* the signal is acted upon.

Currently implemented:
  - ``sentiment_filter`` — blocks entries when recent news sentiment
    opposes the trade direction (uses NewsArticleTicker scores).

Usage in a strategy pipeline:
    signal = strategy.generate(...)
    signal = sentiment_filter(signal, symbol, db_session) or continue
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger("trading.filters")


async def sentiment_filter(
    signal: object,
    symbol: str,
    session,
    min_sentiment: Optional[int] = None,
) -> Optional[object]:
    """Filter a trading signal based on recent news sentiment scores.

    Looks up the most recent ``NewsArticleTicker`` rows for *symbol*
    and computes an average sentiment score.  If ``min_sentiment`` is
    set, the filter enforces:

      - Long entries only pass when avg sentiment >= min_sentiment.
      - Short entries only pass when avg sentiment <= -min_sentiment.
      - Neutral (no recent news or score is zero) → pass through.
      - Exit / stop-loss signals are never filtered.

    Args:
        signal:        A ``Signal`` dataclass (has signal_type, direction).
        symbol:        Ticker symbol (upper-case).
        session:       Async SQLAlchemy session for DB reads.
        min_sentiment: Minimum absolute sentiment score threshold.
                       ``None`` disables the filter (pass-through).

    Returns:
        The original *signal* if it passes, or ``None`` if blocked.
    """
    # Pass-through when filter is disabled
    if min_sentiment is None:
        return signal

    # Only filter entry signals — exits and stop-losses always pass
    if getattr(signal, "signal_type", "") != "entry":
        return signal

    direction = getattr(signal, "direction", "long")

    try:
        avg_score = await _get_avg_sentiment(symbol, session)
    except Exception as exc:
        # On error, don't block the signal — fail open
        logger.warning("Sentiment lookup failed for %s: %s", symbol, exc)
        return signal

    # No recent news → pass through (neutral)
    if avg_score is None:
        return signal

    # Apply directional gating
    if direction == "long" and avg_score < min_sentiment:
        logger.info(
            "Sentiment filter BLOCKED long entry for %s (avg=%.1f < min=%d)",
            symbol, avg_score, min_sentiment,
        )
        return None

    if direction == "short" and avg_score > -min_sentiment:
        logger.info(
            "Sentiment filter BLOCKED short entry for %s (avg=%.1f > -%d)",
            symbol, avg_score, min_sentiment,
        )
        return None

    return signal


async def _get_avg_sentiment(
    symbol: str,
    session,
    lookback_hours: int = 48,
) -> Optional[float]:
    """Compute average sentiment score for *symbol* over recent articles.

    Queries the ``news_article_tickers`` table for rows matching *symbol*
    with a publication date within the last *lookback_hours* hours.

    Args:
        symbol:         Upper-cased ticker symbol.
        session:        Async SQLAlchemy session.
        lookback_hours: How far back to look for articles (default 48h).

    Returns:
        Average sentiment score as a float, or ``None`` if no articles found.
    """
    from sqlalchemy import text

    cutoff = datetime.utcnow() - timedelta(hours=lookback_hours)

    result = await session.execute(
        text(
            "SELECT AVG(nat.score) "
            "FROM news_article_tickers nat "
            "JOIN news_articles na ON na.article_id = nat.article_id "
            "WHERE nat.symbol = :symbol "
            "  AND na.published_at >= :cutoff"
        ),
        {"symbol": symbol, "cutoff": cutoff},
    )
    row = result.fetchone()
    if row and row[0] is not None:
        return float(row[0])
    return None
