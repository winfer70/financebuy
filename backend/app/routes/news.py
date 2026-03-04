"""
routes/news.py — News API endpoints for TickerTap.

Provides three endpoints:
  GET  /api/v1/news/feed              — DB-backed news feed with portfolio-aware scoring
  GET  /api/v1/news/tickers/{ticker}  — articles filtered by a single ticker
  POST /api/v1/internal/news          — internal ingestion API for the LLM worker (Server B)

Articles are pre-scored by a background LLM worker on Server B and pushed into
PostgreSQL via the internal endpoint.  Read endpoints serve directly from the
database with no external HTTP calls or LLM inference at request time.

A daily retention task (30-day TTL) is registered on application startup.

Route prefix: /api/v1/news  (registered in main.py)
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Set

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import NewsArticle, NewsArticleTicker, Portfolio, PortfolioPosition
from ..schemas import NewsArticleIngest, NewsArticleOut, TickerScoreOut
from .auth_routes import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/news", tags=["news"])

# ── Internal API configuration ───────────────────────────────────────────────
_INTERNAL_NEWS_KEY = os.getenv("INTERNAL_NEWS_KEY", "")
_ALLOWED_WORKER_IP = os.getenv("WORKER_IP", "")  # Optional IP restriction


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


def _build_article_response(
    article: NewsArticle,
    ticker_rows: List[NewsArticleTicker],
    portfolio_tickers: Set[str],
) -> NewsArticleOut:
    """Convert an ORM NewsArticle + its ticker rows into a response schema.

    Selects the most relevant score for display: if any ticker in the article
    matches the user's portfolio, the highest-absolute-value portfolio ticker
    score is used; otherwise the general market score is returned.

    Args:
        article:           The NewsArticle ORM instance.
        ticker_rows:       All NewsArticleTicker rows for this article.
        portfolio_tickers: Set of user's portfolio ticker symbols (uppercase).

    Returns:
        A NewsArticleOut instance ready for JSON serialisation.
    """
    # Build per-ticker score list for the response.
    ticker_scores = [
        TickerScoreOut(
            ticker=tr.ticker,
            score=tr.score,
            reasoning=tr.reasoning,
        )
        for tr in ticker_rows
    ]

    # Determine portfolio overlap.
    article_tickers = {tr.ticker.upper() for tr in ticker_rows}
    in_portfolio = bool(article_tickers & portfolio_tickers)

    # Select the most relevant score for the top-level ``score`` field.
    if in_portfolio:
        # Pick the portfolio-matching ticker with the strongest impact.
        portfolio_matches = [
            tr for tr in ticker_rows if tr.ticker.upper() in portfolio_tickers
        ]
        best = max(portfolio_matches, key=lambda tr: abs(tr.score))
        score = best.score
        reasoning = best.reasoning
    else:
        score = article.general_score
        reasoning = article.general_reasoning

    return NewsArticleOut(
        title=article.title,
        url=article.url,
        source=article.source,
        published_at=article.published_at,
        score=score,
        reasoning=reasoning,
        ticker_scores=ticker_scores,
        in_portfolio=in_portfolio,
        summary=article.summary,
    )


# ── Read Endpoints ───────────────────────────────────────────────────────────

@router.get("/feed", response_model=List[NewsArticleOut])
async def get_news_feed(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """DB-backed news feed with portfolio-aware scoring.

    Queries the 100 most recent articles from ``news_articles``, joins with
    ``news_article_tickers`` for per-ticker scores, and selects the most
    relevant score based on the user's portfolio holdings.

    Returns:
        List of NewsArticleOut sorted by published_at descending.
    """
    # 1. Get user's portfolio tickers for scoring context.
    tickers = await _get_user_portfolio_tickers(db, current_user.user_id)
    portfolio_set: Set[str] = {t.upper() for t in tickers}

    # 2. Fetch recent articles ordered by published_at DESC.
    articles_result = await db.execute(
        select(NewsArticle)
        .order_by(NewsArticle.published_at.desc().nullslast())
        .limit(100)
    )
    articles = articles_result.scalars().all()

    if not articles:
        return []

    # 3. Batch-fetch all ticker rows for these articles in one query.
    article_ids = [a.article_id for a in articles]
    tickers_result = await db.execute(
        select(NewsArticleTicker)
        .where(NewsArticleTicker.article_id.in_(article_ids))
    )
    all_ticker_rows = tickers_result.scalars().all()

    # 4. Group ticker rows by article_id for efficient lookup.
    ticker_map: dict = {}
    for tr in all_ticker_rows:
        ticker_map.setdefault(tr.article_id, []).append(tr)

    # 5. Build response objects.
    return [
        _build_article_response(
            article,
            ticker_map.get(article.article_id, []),
            portfolio_set,
        )
        for article in articles
    ]


@router.get("/tickers/{ticker}", response_model=List[NewsArticleOut])
async def get_ticker_news(
    ticker: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Articles filtered by a single ticker symbol, scored from the DB.

    Returns up to 50 articles that mention the specified ticker, ordered by
    published_at descending.

    Args:
        ticker: Stock ticker symbol (e.g. "AAPL").

    Returns:
        List of NewsArticleOut sorted by published_at descending.
    """
    sym = ticker.strip().upper()
    if not sym:
        raise HTTPException(status_code=400, detail="Ticker symbol is required.")

    # 1. Get user's portfolio tickers for scoring context.
    user_tickers = await _get_user_portfolio_tickers(db, current_user.user_id)
    portfolio_set: Set[str] = {t.upper() for t in user_tickers}

    # 2. Find article IDs that reference this ticker.
    ticker_article_ids_result = await db.execute(
        select(NewsArticleTicker.article_id)
        .where(NewsArticleTicker.ticker == sym)
    )
    article_ids = [row[0] for row in ticker_article_ids_result.all()]

    if not article_ids:
        return []

    # 3. Fetch the articles ordered by published_at DESC.
    articles_result = await db.execute(
        select(NewsArticle)
        .where(NewsArticle.article_id.in_(article_ids))
        .order_by(NewsArticle.published_at.desc().nullslast())
        .limit(50)
    )
    articles = articles_result.scalars().all()

    # 4. Batch-fetch all ticker rows for these articles.
    final_article_ids = [a.article_id for a in articles]
    tickers_result = await db.execute(
        select(NewsArticleTicker)
        .where(NewsArticleTicker.article_id.in_(final_article_ids))
    )
    all_ticker_rows = tickers_result.scalars().all()

    ticker_map: dict = {}
    for tr in all_ticker_rows:
        ticker_map.setdefault(tr.article_id, []).append(tr)

    # 5. Build response objects.
    return [
        _build_article_response(
            article,
            ticker_map.get(article.article_id, []),
            portfolio_set,
        )
        for article in articles
    ]


# ── Internal Ingestion Endpoint ──────────────────────────────────────────────

@router.post("/internal/news")
async def ingest_news(
    articles: List[NewsArticleIngest],
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Receive pre-scored articles from the LLM worker on Server B.

    Authentication is two-factor:
      1. ``X-Internal-Key`` header must match the ``INTERNAL_NEWS_KEY`` env var.
      2. (Optional) ``request.client.host`` must match ``WORKER_IP`` if set.

    Articles are upserted by URL — duplicates are silently skipped.

    Args:
        articles: List of NewsArticleIngest payloads from the worker.
        request:  FastAPI request object (for IP validation).
        db:       Async database session.

    Returns:
        dict with ``inserted`` and ``skipped`` counts.
    """
    # ── Auth: shared secret ──────────────────────────────────────────────────
    provided_key = request.headers.get("X-Internal-Key", "")
    if not _INTERNAL_NEWS_KEY or provided_key != _INTERNAL_NEWS_KEY:
        logger.warning(
            "Internal news endpoint: invalid key from %s", request.client.host
        )
        raise HTTPException(status_code=403, detail="Forbidden")

    # ── Auth: optional IP restriction ────────────────────────────────────────
    if _ALLOWED_WORKER_IP and request.client.host != _ALLOWED_WORKER_IP:
        logger.warning(
            "Internal news endpoint: rejected IP %s (expected %s)",
            request.client.host,
            _ALLOWED_WORKER_IP,
        )
        raise HTTPException(status_code=403, detail="Forbidden")

    # ── Upsert articles ─────────────────────────────────────────────────────
    inserted = 0
    skipped = 0

    for payload in articles:
        # Check for duplicate URLs.
        existing = await db.execute(
            select(NewsArticle.article_id)
            .where(NewsArticle.url == payload.url)
        )
        if existing.scalar_one_or_none() is not None:
            skipped += 1
            continue

        # Insert the article.
        article = NewsArticle(
            url=payload.url,
            title=payload.title,
            summary=payload.summary,
            source=payload.source,
            published_at=payload.published_at,
            general_score=payload.general_score,
            general_reasoning=payload.general_reasoning,
        )
        db.add(article)
        # Flush to get the article_id for ticker rows.
        await db.flush()

        # Insert per-ticker scores.
        for ts in payload.tickers:
            ticker_row = NewsArticleTicker(
                article_id=article.article_id,
                ticker=ts.ticker.upper(),
                score=ts.score,
                reasoning=ts.reasoning,
            )
            db.add(ticker_row)

        inserted += 1

    await db.commit()

    logger.info(
        "Internal news ingestion: inserted=%d, skipped=%d, from=%s",
        inserted,
        skipped,
        request.client.host,
    )
    return {"inserted": inserted, "skipped": skipped}


# ── Retention Cleanup ────────────────────────────────────────────────────────

_RETENTION_DAYS = 30
_RETENTION_CHECK_INTERVAL = 86400  # 24 hours in seconds


async def _retention_cleanup_loop():
    """Background task that removes articles older than 30 days once daily.

    Runs indefinitely in the background.  CASCADE deletes on the foreign key
    automatically remove associated news_article_tickers rows.
    """
    while True:
        try:
            # Import here to avoid circular import; engine is fully initialised by now.
            from ..db import AsyncSessionLocal

            cutoff = datetime.now(timezone.utc) - timedelta(days=_RETENTION_DAYS)
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    delete(NewsArticle).where(NewsArticle.created_at < cutoff)
                )
                await session.commit()
                deleted = result.rowcount
                if deleted > 0:
                    logger.info(
                        "Retention cleanup: deleted %d articles older than %d days.",
                        deleted,
                        _RETENTION_DAYS,
                    )
        except Exception:
            logger.exception("Retention cleanup task failed.")

        await asyncio.sleep(_RETENTION_CHECK_INTERVAL)


def register_retention_task(app):
    """Register the retention cleanup loop on FastAPI startup.

    Call this from main.py during application initialisation:
        from .routes.news import register_retention_task
        register_retention_task(app)

    Args:
        app: The FastAPI application instance.
    """

    @app.on_event("startup")
    async def _start_retention():
        asyncio.create_task(_retention_cleanup_loop())
        logger.info("Retention cleanup task registered (30-day TTL, daily check).")
