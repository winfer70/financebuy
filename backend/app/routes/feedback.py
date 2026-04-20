"""
routes/feedback.py — Scoring feedback loop endpoints and background tasks.

Provides internal endpoints for the self-improving scoring system:
  GET  /api/v1/feedback/internal/outcome-data      — learner fetches accuracy data
  GET  /api/v1/feedback/internal/rules/active       — worker fetches current rules
  POST /api/v1/feedback/internal/rules              — learner posts new rules
  GET  /api/v1/feedback/internal/training-export    — future fine-tuning data export

Background task:
  _outcome_checker_loop() — runs every 6 hours, checks actual stock price
  movements via yfinance against LLM predictions, grades accuracy.

All internal endpoints use the same X-Internal-Key + optional IP restriction
as the news ingestion endpoint in routes/news.py.

Route prefix: /api/v1/feedback  (registered in main.py)
"""

import asyncio
import hmac
import logging
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Optional

import yfinance as yf
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import (
    NewsArticle,
    NewsArticleTicker,
    ScoreOutcome,
    ScoringRule,
)
from ..schemas import (
    ScoreOutcomeOut,
    ScoringRuleCreate,
    ScoringRuleOut,
    TrainingPairOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feedback", tags=["feedback"])

# ── Internal API configuration (same env vars as news.py) ────────────────────
_INTERNAL_NEWS_KEY = os.getenv("INTERNAL_NEWS_KEY", "")
_ALLOWED_WORKER_IP = os.getenv("WORKER_IP", "")


# ── Auth helper ──────────────────────────────────────────────────────────────

def _verify_internal_auth(request: Request) -> None:
    """Validate the X-Internal-Key header and optional IP restriction.

    Raises HTTPException 403 if authentication fails.  Uses the same
    shared-secret mechanism as the news ingestion endpoint.

    Args:
        request: FastAPI request object.

    Raises:
        HTTPException: 403 if the key is missing/wrong or IP is not allowed.
    """
    # Guard: reject immediately if no key is configured to avoid comparing
    # an empty string, which would allow any request through.
    if not _INTERNAL_NEWS_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")
    provided_key = request.headers.get("X-Internal-Key", "")
    # Use constant-time comparison to prevent timing-based key enumeration.
    if not hmac.compare_digest(provided_key, _INTERNAL_NEWS_KEY):
        logger.warning(
            "Feedback endpoint: invalid key from %s", request.client.host
        )
        raise HTTPException(status_code=403, detail="Forbidden")

    if _ALLOWED_WORKER_IP and request.client.host != _ALLOWED_WORKER_IP:
        logger.warning(
            "Feedback endpoint: rejected IP %s (expected %s)",
            request.client.host,
            _ALLOWED_WORKER_IP,
        )
        raise HTTPException(status_code=403, detail="Forbidden")


# ── Accuracy grading ─────────────────────────────────────────────────────────

def _grade_accuracy(predicted_score: int, actual_change_pct: float) -> str:
    """Grade the accuracy of a predicted score against actual price movement.

    Compares the LLM's directional prediction and magnitude estimate against
    the real percentage change in the stock price.

    Args:
        predicted_score:  The LLM's score (-5 to +5).
        actual_change_pct: Actual % change (e.g. -2.5 means -2.5%).

    Returns:
        One of: 'correct', 'close', 'wrong', 'opposite'.
    """
    # Determine predicted direction.
    if predicted_score > 0:
        pred_dir = "bullish"
    elif predicted_score < 0:
        pred_dir = "bearish"
    else:
        pred_dir = "neutral"

    # Determine actual direction (0.25% deadzone for "neutral").
    if actual_change_pct > 0.25:
        actual_dir = "bullish"
    elif actual_change_pct < -0.25:
        actual_dir = "bearish"
    else:
        actual_dir = "neutral"

    # Both neutral → correct.
    if pred_dir == "neutral" and actual_dir == "neutral":
        return "correct"

    # Opposite directions.
    if (pred_dir == "bullish" and actual_dir == "bearish") or \
       (pred_dir == "bearish" and actual_dir == "bullish"):
        return "opposite"

    # Same direction — check magnitude alignment.
    if pred_dir == actual_dir:
        abs_score = abs(predicted_score)
        abs_change = abs(actual_change_pct)
        # Strong prediction (4-5) needs >1.5% move to be "correct".
        if abs_score >= 4:
            return "correct" if abs_change >= 1.5 else "close"
        # Moderate prediction (2-3) needs >0.5% move.
        elif abs_score >= 2:
            return "correct" if abs_change >= 0.5 else "close"
        # Mild prediction (1) just needs right direction.
        else:
            return "correct"

    # Predicted movement but was neutral, or vice versa.
    return "wrong"


# ── yfinance price lookup ────────────────────────────────────────────────────

def _fetch_outcome_prices(
    ticker: str, scored_at: datetime
) -> tuple:
    """Fetch close prices on the scoring day and the next trading day.

    Uses yfinance daily data.  Handles weekends and holidays by finding
    the nearest available trading days in a 10-day window.

    This is a synchronous function — call via asyncio.to_thread() from
    async context.

    Args:
        ticker:    Stock ticker symbol (e.g. 'AAPL' or 'SPY').
        scored_at: Timestamp when the article was scored.

    Returns:
        Tuple of (price_at_score, price_after, actual_change_pct) where
        each value is a float, or (None, None, None) if data is unavailable.
    """
    start = (scored_at - timedelta(days=3)).strftime("%Y-%m-%d")
    end = (scored_at + timedelta(days=5)).strftime("%Y-%m-%d")

    try:
        hist = yf.Ticker(ticker).history(start=start, end=end, auto_adjust=True)
    except Exception as exc:
        logger.debug("yfinance fetch failed for %s: %s", ticker, exc)
        return (None, None, None)

    if hist is None or len(hist) < 2:
        return (None, None, None)

    score_date = scored_at.date()

    # Find the trading day at or before scored_at.
    before_dates = [d.date() for d in hist.index if d.date() <= score_date]
    if not before_dates:
        before_dates = [hist.index[0].date()]
    score_trading_day = max(before_dates)

    # Find the next trading day after score_trading_day.
    after_dates = [d.date() for d in hist.index if d.date() > score_trading_day]
    if not after_dates:
        return (None, None, None)
    next_trading_day = min(after_dates)

    try:
        price_at = float(
            hist.loc[hist.index.date == score_trading_day, "Close"].iloc[0]
        )
        price_after = float(
            hist.loc[hist.index.date == next_trading_day, "Close"].iloc[0]
        )
    except (IndexError, ValueError):
        return (None, None, None)

    if price_at == 0:
        return (price_at, price_after, None)

    change_pct = round(((price_after - price_at) / price_at) * 100, 4)
    return (price_at, price_after, change_pct)


def _change_pct_to_score(change_pct: float) -> int:
    """Map an actual percentage change back to the -5/+5 score scale.

    Used for generating training pairs for future fine-tuning export.

    Args:
        change_pct: Actual % change in stock price.

    Returns:
        Integer score from -5 to +5.
    """
    abs_change = abs(change_pct)
    if abs_change < 0.25:
        return 0
    elif abs_change < 0.5:
        magnitude = 1
    elif abs_change < 1.0:
        magnitude = 2
    elif abs_change < 1.5:
        magnitude = 3
    elif abs_change < 3.0:
        magnitude = 4
    else:
        magnitude = 5

    return magnitude if change_pct > 0 else -magnitude


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/internal/outcome-data", response_model=List[ScoreOutcomeOut])
async def get_outcome_data(
    request: Request,
    limit: int = Query(500, ge=1, le=2000, description="Max records to return."),
    offset: int = Query(0, ge=0, description="Number of records to skip."),
    min_date: Optional[str] = Query(
        None, description="ISO-8601 datetime filter on checked_at (inclusive)."
    ),
    db: AsyncSession = Depends(get_db),
):
    """Provide outcome data for the learner to analyse scoring accuracy.

    Returns score outcomes joined with article metadata for context.
    Ordered by checked_at descending (most recent first).

    Args:
        request:  FastAPI request (for auth).
        limit:    Max records to return (1-2000).
        offset:   Number of records to skip.
        min_date: Optional ISO datetime filter on checked_at.
        db:       Async database session.

    Returns:
        List of ScoreOutcomeOut with denormalised article fields.
    """
    _verify_internal_auth(request)

    # Build the query: outcomes joined with articles for context.
    query = (
        select(
            ScoreOutcome,
            NewsArticle.title.label("article_title"),
            NewsArticle.summary.label("article_summary"),
            NewsArticle.source.label("article_source"),
        )
        .join(NewsArticle, NewsArticle.article_id == ScoreOutcome.article_id)
        .order_by(ScoreOutcome.checked_at.desc())
    )

    if min_date:
        try:
            min_dt = datetime.fromisoformat(min_date)
            query = query.where(ScoreOutcome.checked_at >= min_dt)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid min_date format. Use ISO-8601.",
            )

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    rows = result.all()

    # Build response objects with denormalised article fields.
    outcomes = []
    for row in rows:
        outcome = row[0]  # ScoreOutcome ORM instance
        outcomes.append(
            ScoreOutcomeOut(
                outcome_id=outcome.outcome_id,
                article_id=outcome.article_id,
                ticker=outcome.ticker,
                score_type=outcome.score_type,
                predicted_score=outcome.predicted_score,
                predicted_reasoning=outcome.predicted_reasoning,
                price_at_score=outcome.price_at_score,
                price_after=outcome.price_after,
                actual_change_pct=outcome.actual_change_pct,
                accuracy_grade=outcome.accuracy_grade,
                scored_at=outcome.scored_at,
                checked_at=outcome.checked_at,
                article_title=row.article_title,
                article_summary=row.article_summary,
                article_source=row.article_source,
            )
        )

    return outcomes


@router.get("/internal/rules/active", response_model=ScoringRuleOut)
async def get_active_rules(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Return the currently active scoring rules for the worker.

    The worker calls this endpoint periodically to fetch calibration rules
    that are injected into the LLM scoring prompt.

    Args:
        request: FastAPI request (for auth).
        db:      Async database session.

    Returns:
        ScoringRuleOut for the active rule set, or 404 if none exist.
    """
    _verify_internal_auth(request)

    result = await db.execute(
        select(ScoringRule).where(ScoringRule.is_active.is_(True)).limit(1)
    )
    rule = result.scalar_one_or_none()

    if rule is None:
        raise HTTPException(status_code=404, detail="No active scoring rules.")

    return ScoringRuleOut.from_orm(rule)


@router.post("/internal/rules", response_model=ScoringRuleOut)
async def create_scoring_rules(
    payload: ScoringRuleCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Accept new calibration rules from the learner.

    Deactivates all previous rule sets and activates the new one.
    Rule versions auto-increment.

    Args:
        payload: ScoringRuleCreate with rules_text and analysis metadata.
        request: FastAPI request (for auth).
        db:      Async database session.

    Returns:
        ScoringRuleOut for the newly created rule set.
    """
    _verify_internal_auth(request)

    # Determine the next version number.
    max_version_result = await db.execute(
        select(func.max(ScoringRule.rule_version))
    )
    max_version = max_version_result.scalar() or 0
    next_version = max_version + 1

    # Deactivate all existing rules.
    await db.execute(
        update(ScoringRule).where(ScoringRule.is_active.is_(True)).values(
            is_active=False
        )
    )

    # Insert the new active rule.
    new_rule = ScoringRule(
        rule_version=next_version,
        rules_text=payload.rules_text,
        analysis_summary=payload.analysis_summary,
        sample_size=payload.sample_size,
        accuracy_before=payload.accuracy_before,
        is_active=True,
        generated_at=datetime.now(timezone.utc),
    )
    db.add(new_rule)
    await db.commit()
    await db.refresh(new_rule)

    logger.info(
        "New scoring rules v%d activated (sample_size=%s, accuracy_before=%s).",
        next_version,
        payload.sample_size,
        payload.accuracy_before,
    )
    return ScoringRuleOut.from_orm(new_rule)


@router.get("/internal/training-export", response_model=List[TrainingPairOut])
async def export_training_data(
    request: Request,
    limit: int = Query(1000, ge=1, le=5000, description="Max records."),
    offset: int = Query(0, ge=0, description="Records to skip."),
    db: AsyncSession = Depends(get_db),
):
    """Export score outcomes as training pairs for future LoRA fine-tuning.

    Each record combines the article input with the original LLM prediction
    and a corrected output derived from actual price movements.

    Args:
        request: FastAPI request (for auth).
        limit:   Max records to return.
        offset:  Records to skip.
        db:      Async database session.

    Returns:
        List of TrainingPairOut ready for JSONL export.
    """
    _verify_internal_auth(request)

    instruction = (
        "You are a financial news analyst. Analyze this news article and "
        "return ONLY valid JSON with general_score, general_reasoning, and "
        "tickers array."
    )

    # Fetch outcomes with article context.
    result = await db.execute(
        select(
            ScoreOutcome,
            NewsArticle.title,
            NewsArticle.summary,
            NewsArticle.general_score,
            NewsArticle.general_reasoning,
        )
        .join(NewsArticle, NewsArticle.article_id == ScoreOutcome.article_id)
        .where(ScoreOutcome.actual_change_pct.isnot(None))
        .order_by(ScoreOutcome.checked_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = result.all()

    pairs = []
    for row in rows:
        outcome = row[0]
        title = row[1]
        summary = row[2] or ""
        general_score = row[3]
        general_reasoning = row[4] or ""

        # Use actual change to compute what the "correct" score should be.
        actual_pct = float(outcome.actual_change_pct) if outcome.actual_change_pct else 0.0
        corrected_score = _change_pct_to_score(actual_pct)

        pairs.append(
            TrainingPairOut(
                instruction=instruction,
                input_text=f"Article headline: {title}\nArticle summary: {summary}",
                original_output={
                    "general_score": general_score,
                    "general_reasoning": general_reasoning,
                    "ticker": outcome.ticker,
                    "ticker_score": outcome.predicted_score,
                    "ticker_reasoning": outcome.predicted_reasoning or "",
                },
                corrected_output={
                    "score": corrected_score,
                    "reasoning": (
                        f"Actual price change was {actual_pct:+.2f}%. "
                        f"Grade: {outcome.accuracy_grade}."
                    ),
                },
                actual_change_pct=outcome.actual_change_pct,
                accuracy_grade=outcome.accuracy_grade,
            )
        )

    return pairs


# ── Background Task: Outcome Checker ────────────────────────────────────────

_OUTCOME_CHECK_INTERVAL = 21600  # 6 hours in seconds
_OUTCOME_MIN_AGE_HOURS = 24     # Check articles scored at least 24h ago
_OUTCOME_MAX_AGE_HOURS = 72     # Don't check articles older than 72h
_OUTCOME_BATCH_SIZE = 50        # Max articles to check per cycle
_RETENTION_DAYS = 30            # Match article retention


async def _check_article_outcomes(session: AsyncSession) -> int:
    """Check actual price movements for recently scored articles.

    Finds articles scored between 24h and 72h ago that don't have outcomes
    yet, fetches prices via yfinance, grades accuracy, and inserts results.

    Args:
        session: Async database session.

    Returns:
        Number of outcome records created.
    """
    now = datetime.now(timezone.utc)
    min_scored = now - timedelta(hours=_OUTCOME_MAX_AGE_HOURS)
    max_scored = now - timedelta(hours=_OUTCOME_MIN_AGE_HOURS)

    # Find articles in the scoring window that don't have outcomes yet.
    # Use a subquery to exclude articles already checked.
    checked_article_ids = (
        select(ScoreOutcome.article_id)
        .where(ScoreOutcome.score_type == "general")
        .correlate(None)
    )

    articles_result = await session.execute(
        select(NewsArticle)
        .where(
            NewsArticle.scored_at >= min_scored,
            NewsArticle.scored_at <= max_scored,
            NewsArticle.article_id.notin_(checked_article_ids),
        )
        .order_by(NewsArticle.scored_at.asc())
        .limit(_OUTCOME_BATCH_SIZE)
    )
    articles = articles_result.scalars().all()

    if not articles:
        return 0

    logger.info(
        "Outcome checker: found %d articles to check (scored %dh-%dh ago).",
        len(articles),
        _OUTCOME_MIN_AGE_HOURS,
        _OUTCOME_MAX_AGE_HOURS,
    )

    created = 0

    for article in articles:
        # 1. Check general score against SPY.
        price_at, price_after, change_pct = await asyncio.to_thread(
            _fetch_outcome_prices, "SPY", article.scored_at
        )

        if change_pct is not None:
            grade = _grade_accuracy(article.general_score, change_pct)
            outcome = ScoreOutcome(
                article_id=article.article_id,
                ticker="SPY",
                score_type="general",
                predicted_score=article.general_score,
                predicted_reasoning=article.general_reasoning,
                price_at_score=Decimal(str(price_at)) if price_at else None,
                price_after=Decimal(str(price_after)) if price_after else None,
                actual_change_pct=Decimal(str(change_pct)),
                accuracy_grade=grade,
                scored_at=article.scored_at,
                checked_at=now,
            )
            session.add(outcome)
            created += 1

        # 2. Check each ticker-specific score.
        ticker_rows_result = await session.execute(
            select(NewsArticleTicker)
            .where(NewsArticleTicker.article_id == article.article_id)
        )
        ticker_rows = ticker_rows_result.scalars().all()

        for tr in ticker_rows:
            price_at, price_after, change_pct = await asyncio.to_thread(
                _fetch_outcome_prices, tr.ticker, article.scored_at
            )

            if change_pct is not None:
                grade = _grade_accuracy(tr.score, change_pct)
                outcome = ScoreOutcome(
                    article_id=article.article_id,
                    ticker=tr.ticker,
                    score_type="ticker",
                    predicted_score=tr.score,
                    predicted_reasoning=tr.reasoning,
                    price_at_score=Decimal(str(price_at)) if price_at else None,
                    price_after=Decimal(str(price_after)) if price_after else None,
                    actual_change_pct=Decimal(str(change_pct)),
                    accuracy_grade=grade,
                    scored_at=article.scored_at,
                    checked_at=now,
                )
                session.add(outcome)
                created += 1

    await session.commit()
    return created


async def _outcome_checker_loop():
    """Background task that checks article scoring accuracy every 6 hours.

    Runs indefinitely.  On each cycle:
    1. Checks actual price movements for recently scored articles.
    2. Cleans up outcome records older than the retention period.
    """
    while True:
        try:
            from ..db import AsyncSessionLocal

            async with AsyncSessionLocal() as session:
                # 1. Check outcomes for recent articles.
                created = await _check_article_outcomes(session)
                if created > 0:
                    logger.info(
                        "Outcome checker: created %d outcome records.", created
                    )

                # 2. Clean up old outcome records (match 30-day article retention).
                cutoff = datetime.now(timezone.utc) - timedelta(days=_RETENTION_DAYS)
                result = await session.execute(
                    delete(ScoreOutcome).where(ScoreOutcome.created_at < cutoff)
                )
                await session.commit()
                deleted = result.rowcount
                if deleted > 0:
                    logger.info(
                        "Outcome checker: cleaned up %d outcome records older than %d days.",
                        deleted,
                        _RETENTION_DAYS,
                    )

        except Exception:
            logger.exception("Outcome checker task failed.")

        await asyncio.sleep(_OUTCOME_CHECK_INTERVAL)


def register_outcome_checker(app):
    """Register the outcome checker loop on FastAPI startup.

    Call this from main.py during application initialisation:
        from .routes.feedback import register_outcome_checker
        register_outcome_checker(app)

    Args:
        app: The FastAPI application instance.
    """

    @app.on_event("startup")
    async def _start_outcome_checker():
        asyncio.create_task(_outcome_checker_loop())
        logger.info(
            "Outcome checker task registered (every %dh).",
            _OUTCOME_CHECK_INTERVAL // 3600,
        )
