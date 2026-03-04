"""
routes/news.py — News aggregation API endpoints for TickerTap.

Provides two endpoints:
  GET /api/v1/news/feed     — aggregated news for the user's top portfolio tickers
  GET /api/v1/news/tickers/{ticker} — on-demand deep fetch for a single ticker

Articles are fetched from multiple RSS/HTML sources (Yahoo Finance, Google News,
Finviz, MarketWatch), classified by FinBERT sentiment, and annotated with
portfolio association flags.  Results are cached in memory with a 5-minute TTL
to avoid excessive outbound traffic.

Route prefix: /api/v1/news  (registered in main.py)
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Set, Tuple

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import Portfolio, PortfolioPosition
from ..news_sources import fetch_all_news, fetch_ticker_news
from ..schemas import NewsArticleOut
from ..sentiment import classify_headlines
from .auth_routes import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/news", tags=["news"])


# ── In-memory cache (mirrors the pattern in routes/market.py) ────────────────
_cache: Dict[str, Tuple[float, object]] = {}
_NEWS_FEED_TTL = 300    # 5 minutes — aggregated feed
_TICKER_NEWS_TTL = 300  # 5 minutes — single-ticker deep fetch


def _get_cached(key: str, ttl: float) -> Optional[object]:
    """Return cached value if it exists and has not expired.

    Args:
        key: Cache key string.
        ttl: Time-to-live in seconds.

    Returns:
        Cached object, or None if expired / missing.
    """
    entry = _cache.get(key)
    if entry and (time.time() - entry[0]) < ttl:
        return entry[1]
    return None


def _set_cached(key: str, value: object) -> None:
    """Store a value in the in-memory cache with the current timestamp.

    Args:
        key:   Cache key string.
        value: Object to cache.
    """
    _cache[key] = (time.time(), value)


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _get_user_portfolio_tickers(
    db: AsyncSession,
    user_id,
) -> List[str]:
    """Collect all unique, non-excluded ticker symbols across the user's portfolios.

    Args:
        db:      Async database session.
        user_id: UUID of the authenticated user.

    Returns:
        Ordered list of unique ticker symbols (uppercase).
    """
    result = await db.execute(
        select(PortfolioPosition.ticker)
        .join(Portfolio, Portfolio.portfolio_id == PortfolioPosition.portfolio_id)
        .where(
            Portfolio.user_id == user_id,
            PortfolioPosition.is_excluded.is_(False),
        )
        .distinct()
    )
    return [row[0].upper() for row in result.all()]


def _enrich_articles(
    articles: List[Dict],
    portfolio_tickers: Set[str],
) -> List[Dict]:
    """Apply sentiment classification and portfolio flags to raw article dicts.

    Runs FinBERT over all headlines in a single batch for efficiency, then
    marks each article's ``in_portfolio`` flag based on ticker overlap.

    Args:
        articles:          List of raw article dicts from news_sources.
        portfolio_tickers: Set of user's portfolio ticker symbols (uppercase).

    Returns:
        The same article dicts, mutated in-place with sentiment and portfolio data.
    """
    if not articles:
        return articles

    # Batch-classify all headlines at once.
    headlines = [a["title"] for a in articles]
    sentiments = classify_headlines(headlines)

    for article, sent in zip(articles, sentiments):
        article["sentiment"] = sent["label"]
        article["sentiment_score"] = sent["score"]
        # Mark articles that mention at least one portfolio ticker.
        article_tickers = {t.upper() for t in article.get("tickers", [])}
        article["in_portfolio"] = bool(article_tickers & portfolio_tickers)

    return articles


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/feed", response_model=List[NewsArticleOut])
async def get_news_feed(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Aggregated news feed for the authenticated user's portfolio tickers.

    Fetches articles from Yahoo Finance RSS, Google News RSS, Finviz HTML
    scrape, and MarketWatch top-stories RSS.  Results are limited to the
    top 10 portfolio tickers per source to respect rate limits.

    Articles are deduplicated by URL, classified by FinBERT sentiment,
    sorted by publication date (newest first), and annotated with an
    ``in_portfolio`` flag.

    Returns:
        List of NewsArticleOut dicts sorted by published_at descending.
    """
    # Collect the user's portfolio tickers for source targeting and flagging.
    tickers = await _get_user_portfolio_tickers(db, current_user.user_id)
    portfolio_set: Set[str] = set(tickers)

    # Build a cache key scoped to the user's ticker set (order-independent).
    cache_key = f"news_feed:{current_user.user_id}"
    cached = _get_cached(cache_key, _NEWS_FEED_TTL)
    if cached:
        return cached

    # Fetch from all sources concurrently (I/O-bound, runs in async context).
    raw_articles = await fetch_all_news(tickers, portfolio_set)

    # Enrich with sentiment and portfolio flags (CPU-bound FinBERT inference).
    enriched = await asyncio.to_thread(_enrich_articles, raw_articles, portfolio_set)

    # Convert to response schema.
    response = [NewsArticleOut(**a) for a in enriched]

    _set_cached(cache_key, response)
    return response


@router.get("/tickers/{ticker}", response_model=List[NewsArticleOut])
async def get_ticker_news(
    ticker: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """On-demand deep fetch of news for a single ticker symbol.

    Bypasses the top-10 ticker limit used in the aggregated feed and
    fetches from every source for the specified ticker.  Use this
    endpoint when the user clicks "load more" on a specific stock.

    Args:
        ticker: Stock ticker symbol (e.g. "AAPL").

    Returns:
        List of NewsArticleOut dicts sorted by published_at descending.
    """
    sym = ticker.strip().upper()
    if not sym:
        raise HTTPException(status_code=400, detail="Ticker symbol is required.")

    cache_key = f"ticker_news:{sym}"
    cached = _get_cached(cache_key, _TICKER_NEWS_TTL)
    if cached:
        return cached

    # Collect portfolio tickers for the in_portfolio flag.
    user_tickers = await _get_user_portfolio_tickers(db, current_user.user_id)
    portfolio_set: Set[str] = set(user_tickers)

    # Deep fetch for this single ticker (no top-10 limit).
    raw_articles = await fetch_ticker_news(sym)

    # Enrich with sentiment and portfolio flags.
    enriched = await asyncio.to_thread(_enrich_articles, raw_articles, portfolio_set)

    response = [NewsArticleOut(**a) for a in enriched]

    _set_cached(cache_key, response)
    return response
