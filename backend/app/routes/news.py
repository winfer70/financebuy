"""
routes/news.py — News API endpoints for TickerTap.

Provides three endpoints:
  GET  /api/v1/news/feed              — Paginated, DB-backed news feed with portfolio-aware scoring
  GET  /api/v1/news/tickers/{ticker}  — Paginated articles filtered by a single ticker
  POST /api/v1/internal/news          — Internal ingestion API for the LLM worker (Server B)

Both read endpoints support server-side pagination via ``limit`` and ``offset``
query parameters. The default page size is 25 articles; the maximum is 100.
Responses use the PaginatedNewsResponse schema which includes a ``total`` field
so the frontend can render page navigation controls.

Articles are pre-scored by a background LLM worker on Server B and pushed into
PostgreSQL via the internal endpoint.  Read endpoints serve directly from the
database with no external HTTP calls or LLM inference at request time.

A daily retention task (30-day TTL) is registered on application startup.

Route prefix: /api/v1/news  (registered in main.py)
"""

import asyncio
import hmac
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Set

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import NewsArticle, NewsArticleTicker, Portfolio, PortfolioPosition
from ..schemas import NewsArticleIngest, NewsArticleOut, PaginatedNewsResponse, TickerScoreOut
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

@router.get("/feed", response_model=PaginatedNewsResponse)
async def get_news_feed(
    limit: int = Query(25, ge=25, le=100, description="Articles per page (25, 50, 75, or 100)."),
    offset: int = Query(0, ge=0, description="Number of articles to skip."),
    portfolio_tickers: Optional[str] = Query(None, description="Comma-separated portfolio ticker symbols for filtering."),
    portfolio_only: bool = Query(False, description="If true, filter to articles matching the user's portfolio tickers."),
    sentiment: Optional[str] = Query(None, description="Filter by sentiment: bullish or bearish."),
    ticker_search: Optional[str] = Query(None, description="Search articles by ticker symbol or title text."),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Paginated, DB-backed news feed with portfolio-aware scoring and
    server-side filtering.

    Queries articles from ``news_articles``, joins with
    ``news_article_tickers`` for per-ticker scores, and selects the most
    relevant score based on the user's portfolio holdings.

    Pagination is controlled via ``limit`` (page size, default 25, max 100)
    and ``offset`` (number of articles to skip, default 0).  The response
    includes a ``total`` field with the overall article count so the frontend
    can calculate page numbers.

    Server-side filters are applied BEFORE pagination so that total counts
    and page offsets stay consistent:

      - ``portfolio_tickers``: Comma-separated ticker symbols.  Only articles
        mentioning at least one of these tickers are returned.
      - ``portfolio_only``: When true, automatically filters to articles
        mentioning the authenticated user's portfolio tickers (derived from
        the database).  Takes effect only when ``portfolio_tickers`` is not
        explicitly provided.
      - ``sentiment``: ``"bullish"`` (general_score > 0) or ``"bearish"``
        (general_score < 0).
      - ``ticker_search``: Free-text search against ticker symbols and
        article titles (case-insensitive partial match).

    Args:
        limit:              Page size — articles per page (25-100, default 25).
        offset:             Number of articles to skip (default 0).
        portfolio_tickers:  Comma-separated ticker symbols for filtering (optional).
        portfolio_only:     Use the user's portfolio tickers for filtering (optional).
        sentiment:          Filter by sentiment: "bullish" or "bearish" (optional).
        ticker_search:      Search articles by ticker or title (optional).
        db:                 Async database session.
        current_user:       Authenticated user (injected via dependency).

    Returns:
        PaginatedNewsResponse with articles, total, limit, and offset.
    """
    # 1. Get user's portfolio tickers for scoring context.
    tickers = await _get_user_portfolio_tickers(db, current_user.user_id)
    portfolio_set: Set[str] = {t.upper() for t in tickers}

    # 2. Build the base query and count query, applying server-side filters.
    base_query = select(NewsArticle)
    count_query = select(func.count(NewsArticle.article_id))

    # ── Filter: portfolio_tickers OR portfolio_only ──────────────────────
    # If explicit portfolio_tickers are provided, use those; otherwise, if
    # portfolio_only is true, use the user's own portfolio tickers.
    filter_tickers: Optional[List[str]] = None
    if portfolio_tickers:
        filter_tickers = [t.strip().upper() for t in portfolio_tickers.split(",") if t.strip()]
    elif portfolio_only:
        filter_tickers = list(portfolio_set)

    if filter_tickers:
        # Use an EXISTS subquery to avoid duplicates from the join.
        # Returns articles where at least one associated ticker matches.
        ticker_exists = (
            select(NewsArticleTicker.article_id)
            .where(
                NewsArticleTicker.article_id == NewsArticle.article_id,
                NewsArticleTicker.ticker.in_(filter_tickers),
            )
            .exists()
        )
        base_query = base_query.where(ticker_exists)
        count_query = count_query.where(ticker_exists)

    # ── Filter: sentiment (bullish / bearish) ────────────────────────────
    if sentiment == "bullish":
        base_query = base_query.where(NewsArticle.general_score > 0)
        count_query = count_query.where(NewsArticle.general_score > 0)
    elif sentiment == "bearish":
        base_query = base_query.where(NewsArticle.general_score < 0)
        count_query = count_query.where(NewsArticle.general_score < 0)

    # ── Filter: ticker_search (ticker symbol OR title, case-insensitive) ─
    if ticker_search:
        search_pattern = f"%{ticker_search.strip()}%"
        # Use an EXISTS subquery for ticker match to avoid duplicates.
        ticker_search_exists = (
            select(NewsArticleTicker.article_id)
            .where(
                NewsArticleTicker.article_id == NewsArticle.article_id,
                NewsArticleTicker.ticker.ilike(search_pattern),
            )
            .exists()
        )
        base_query = base_query.where(
            ticker_search_exists | NewsArticle.title.ilike(search_pattern)
        )
        count_query = count_query.where(
            ticker_search_exists | NewsArticle.title.ilike(search_pattern)
        )

    # 3. Execute the filtered count query for pagination metadata.
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # 4. Fetch the requested page of articles ordered by published_at DESC.
    articles_result = await db.execute(
        base_query
        .order_by(NewsArticle.published_at.desc().nullslast())
        .offset(offset)
        .limit(limit)
    )
    articles = articles_result.scalars().all()

    if not articles:
        return PaginatedNewsResponse(articles=[], total=total, limit=limit, offset=offset)

    # 5. Batch-fetch all ticker rows for these articles in one query.
    article_ids = [a.article_id for a in articles]
    tickers_result = await db.execute(
        select(NewsArticleTicker)
        .where(NewsArticleTicker.article_id.in_(article_ids))
    )
    all_ticker_rows = tickers_result.scalars().all()

    # 6. Group ticker rows by article_id for efficient lookup.
    ticker_map: dict = {}
    for tr in all_ticker_rows:
        ticker_map.setdefault(tr.article_id, []).append(tr)

    # 7. Build response objects.
    response_articles = [
        _build_article_response(
            article,
            ticker_map.get(article.article_id, []),
            portfolio_set,
        )
        for article in articles
    ]

    return PaginatedNewsResponse(
        articles=response_articles,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/tickers/{ticker}", response_model=PaginatedNewsResponse)
async def get_ticker_news(
    ticker: str,
    limit: int = Query(25, ge=25, le=100, description="Articles per page (25, 50, 75, or 100)."),
    offset: int = Query(0, ge=0, description="Number of articles to skip."),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Paginated articles filtered by a single ticker symbol, scored from the DB.

    Returns articles that mention the specified ticker, ordered by
    published_at descending.  Pagination via ``limit`` and ``offset``.

    Args:
        ticker: Stock ticker symbol (e.g. "AAPL").
        limit:  Page size — articles per page (25-100, default 25).
        offset: Number of articles to skip (default 0).
        db:     Async database session.
        current_user: Authenticated user (injected via dependency).

    Returns:
        PaginatedNewsResponse with articles, total, limit, and offset.
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
        return PaginatedNewsResponse(articles=[], total=0, limit=limit, offset=offset)

    # 3. Total count of articles referencing this ticker.
    total = len(article_ids)

    # 4. Fetch the requested page of articles ordered by published_at DESC.
    articles_result = await db.execute(
        select(NewsArticle)
        .where(NewsArticle.article_id.in_(article_ids))
        .order_by(NewsArticle.published_at.desc().nullslast())
        .offset(offset)
        .limit(limit)
    )
    articles = articles_result.scalars().all()

    # 5. Batch-fetch all ticker rows for these articles.
    final_article_ids = [a.article_id for a in articles]
    tickers_result = await db.execute(
        select(NewsArticleTicker)
        .where(NewsArticleTicker.article_id.in_(final_article_ids))
    )
    all_ticker_rows = tickers_result.scalars().all()

    ticker_map: dict = {}
    for tr in all_ticker_rows:
        ticker_map.setdefault(tr.article_id, []).append(tr)

    # 6. Build response objects.
    response_articles = [
        _build_article_response(
            article,
            ticker_map.get(article.article_id, []),
            portfolio_set,
        )
        for article in articles
    ]

    return PaginatedNewsResponse(
        articles=response_articles,
        total=total,
        limit=limit,
        offset=offset,
    )


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
    if not _INTERNAL_NEWS_KEY or not hmac.compare_digest(provided_key, _INTERNAL_NEWS_KEY):
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
