"""
routes/trading.py — Trading AI API endpoints.

Provides strategy CRUD, backtest queuing/polling, signal retrieval,
notification management, webhook configuration, market regime detection,
and internal endpoints for Server B strategy research/learning scripts.

Public endpoints require authentication.  Internal endpoints use X-Internal-Key.
Backtests are executed asynchronously via the arq task worker and polled by
the frontend.

Route prefix: /api/v1/trading  (registered in main.py)
"""

import asyncio
import csv
import hmac
import io
import json
import logging
import os
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select, update, delete, and_, or_, func, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import (
    Strategy, StrategyVersion, BacktestResult, TradingSignal,
    AuditLog, Notification, UserWebhook, User,
    StrategyRating, StrategyUsage,
    PaperTrade, PaperTradePosition, PaperTradeEquitySnapshot,
)
from ..trading.notifications import check_webhook_host_safe, validate_webhook_url_shape
from ..schemas import (
    StrategyCreate, StrategyOut, StrategyUpdate,
    BacktestRequest, BacktestResultOut,
    TradingSignalOut,
    NotificationOut, NotificationMarkRead, PaginatedNotificationsResponse,
    WebhookCreate, WebhookOut, WebhookUpdate,
    RegimeRequest, RegimeResponse,
    PineScriptValidateRequest, PineScriptValidateResponse,
    PineScriptTranspileRequest, PineScriptTranspileResponse,
    StrategyVersionOut, CompositionRequest,
    RatingCreate, RatingOut, StrategyStatsOut, MarketplaceStrategyOut,
    BatchBacktestRequest,
    PaperTradeCreate, PaperTradeUpdate, PaperTradeOut, PaperTradePositionOut,
    PaperTradeEquitySnapshotOut,
    PortfolioItem, PortfolioScoreRequest, PortfolioScoreResponse, PositionScore,
    ExitAnalysisRequest, ExitAnalysisResponse, ExitLevel,
)
from ..limiter import limiter
from .auth_routes import get_current_user
from ..trading.engine.indicators import sma, ema, rsi, atr, bollinger_bands, highest, lowest

router = APIRouter(prefix="/trading", tags=["trading"])

logger = logging.getLogger(__name__)

# ── Internal API configuration (same env vars as news.py / feedback.py) ──
_INTERNAL_NEWS_KEY = os.getenv("INTERNAL_NEWS_KEY", "")
_ALLOWED_WORKER_IP = os.getenv("WORKER_IP", "")


def _verify_internal_auth(request: Request) -> None:
    """Validate the X-Internal-Key header and optional IP restriction.

    Uses the same shared-secret mechanism as news.py and feedback.py.

    Args:
        request: FastAPI request object.

    Raises:
        HTTPException: 403 if key is wrong or IP is not allowed.
    """
    provided_key = request.headers.get("X-Internal-Key", "")
    if not _INTERNAL_NEWS_KEY or not hmac.compare_digest(provided_key, _INTERNAL_NEWS_KEY):
        logger.warning("Trading internal endpoint: invalid key from %s", request.client.host)
        raise HTTPException(status_code=403, detail="Forbidden")

    if _ALLOWED_WORKER_IP and request.client.host != _ALLOWED_WORKER_IP:
        logger.warning(
            "Trading internal endpoint: rejected IP %s (expected %s)",
            request.client.host, _ALLOWED_WORKER_IP,
        )
        raise HTTPException(status_code=403, detail="Forbidden")


# ── Audit helper ──────────────────────────────────────────────────────────

async def _audit(db: AsyncSession, user_id, action: str, record_id=None, new_values=None):
    """Write an audit log entry for a trading action.

    Args:
        db:         Async database session.
        user_id:    UUID of the acting user.
        action:     Action string (e.g. ``"strategy_created"``).
        record_id:  Optional UUID of the affected record.
        new_values: Optional JSONB payload.
    """
    entry = AuditLog(
        user_id=user_id,
        action=action,
        table_name="strategies",
        record_id=record_id,
        new_values=new_values,
    )
    db.add(entry)


# ── Strategy routes ───────────────────────────────────────────────────────

@router.get("/strategies/registry")
async def get_strategy_registry():
    """Return the built-in strategy engine registry.

    Provides slug, name, description, default_params and param_schema
    for every registered strategy module.  Used by the frontend to
    populate the strategy picker and parameter sliders.

    This endpoint is unauthenticated — it returns only static engine
    metadata, no user data.

    Returns:
        JSON list of strategy metadata dicts.
    """
    from ..trading.engine.strategies import list_strategies as _list_engine
    return _list_engine()


@router.get("/strategies", response_model=List[StrategyOut])
async def list_strategies(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all strategies visible to the current user (own + system).

    Returns user-owned strategies plus all public system strategies.
    """
    stmt = select(Strategy).where(
        or_(
            Strategy.user_id == current_user.user_id,
            Strategy.is_system == True,  # noqa: E712
        )
    ).order_by(Strategy.is_system.desc(), Strategy.created_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/strategies", response_model=StrategyOut, status_code=201)
@limiter.limit("10/minute")
async def create_strategy(
    body: StrategyCreate,
    request: Request,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new user-owned strategy.

    Args:
        body: Strategy creation payload.

    Returns:
        The newly created strategy.
    """
    strategy = Strategy(
        strategy_id=uuid.uuid4(),
        user_id=current_user.user_id,
        name=body.name,
        description=body.description,
        strategy_type=body.strategy_type,
        category=body.category,
        timeframe=body.timeframe,
        asset_class=body.asset_class,
        definition_json=body.definition_json,
        is_public=body.is_public,
    )
    db.add(strategy)
    await _audit(
        db, current_user.user_id, "strategy_created",
        record_id=strategy.strategy_id,
        new_values={"name": body.name, "type": body.strategy_type},
    )
    await db.commit()
    await db.refresh(strategy)
    return strategy


@router.get("/strategies/{strategy_id}", response_model=StrategyOut)
async def get_strategy(
    strategy_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a strategy by ID (must be owned by user or be a system strategy).

    Args:
        strategy_id: UUID of the strategy.

    Returns:
        Strategy details.

    Raises:
        404: Strategy not found or not accessible.
    """
    stmt = select(Strategy).where(
        Strategy.strategy_id == strategy_id,
        or_(
            Strategy.user_id == current_user.user_id,
            Strategy.is_system == True,  # noqa: E712
        ),
    )
    result = await db.execute(stmt)
    strategy = result.scalar_one_or_none()
    if not strategy:
        raise HTTPException(404, "Strategy not found.")
    return strategy


@router.patch("/strategies/{strategy_id}", response_model=StrategyOut)
@limiter.limit("10/minute")
async def update_strategy(
    strategy_id: uuid.UUID,
    body: StrategyUpdate,
    request: Request,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a user-owned strategy.  Creates a version snapshot before updating.

    Args:
        strategy_id: UUID of the strategy to update.
        body:        Partial update payload.

    Returns:
        Updated strategy.

    Raises:
        404: Strategy not found.
        403: Cannot modify system strategies.
    """
    stmt = select(Strategy).where(
        Strategy.strategy_id == strategy_id,
        Strategy.user_id == current_user.user_id,
    )
    result = await db.execute(stmt)
    strategy = result.scalar_one_or_none()
    if not strategy:
        raise HTTPException(404, "Strategy not found or not owned by you.")
    if strategy.is_system:
        raise HTTPException(403, "Cannot modify system strategies. Clone it first.")

    # Snapshot current version before updating
    snapshot = StrategyVersion(
        version_id=uuid.uuid4(),
        strategy_id=strategy.strategy_id,
        version_number=strategy.version,
        definition_json=strategy.definition_json,
    )
    db.add(snapshot)

    # Apply updates
    updates = body.dict(exclude_unset=True)
    for key, value in updates.items():
        setattr(strategy, key, value)
    strategy.version += 1
    strategy.updated_at = datetime.utcnow()

    await _audit(
        db, current_user.user_id, "strategy_updated",
        record_id=strategy.strategy_id,
        new_values=updates,
    )
    await db.commit()
    await db.refresh(strategy)
    return strategy


@router.delete("/strategies/{strategy_id}", status_code=204)
@limiter.limit("10/minute")
async def delete_strategy(
    strategy_id: uuid.UUID,
    request: Request,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a user-owned strategy.

    Args:
        strategy_id: UUID of the strategy to delete.

    Raises:
        404: Strategy not found.
        403: Cannot delete system strategies.
    """
    stmt = select(Strategy).where(
        Strategy.strategy_id == strategy_id,
        Strategy.user_id == current_user.user_id,
    )
    result = await db.execute(stmt)
    strategy = result.scalar_one_or_none()
    if not strategy:
        raise HTTPException(404, "Strategy not found or not owned by you.")
    if strategy.is_system:
        raise HTTPException(403, "Cannot delete system strategies.")

    await _audit(
        db, current_user.user_id, "strategy_deleted",
        record_id=strategy.strategy_id,
        new_values={"name": strategy.name},
    )
    await db.delete(strategy)
    await db.commit()


@router.post("/strategies/{strategy_id}/clone", response_model=StrategyOut, status_code=201)
@limiter.limit("10/minute")
async def clone_strategy(
    strategy_id: uuid.UUID,
    request: Request,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Clone a system or public strategy into the user's own collection.

    Args:
        strategy_id: UUID of the strategy to clone.

    Returns:
        The newly cloned strategy, owned by the current user.

    Raises:
        404: Source strategy not found.
    """
    stmt = select(Strategy).where(
        Strategy.strategy_id == strategy_id,
        or_(
            Strategy.is_system == True,   # noqa: E712
            Strategy.is_public == True,    # noqa: E712
            Strategy.user_id == current_user.user_id,
        ),
    )
    result = await db.execute(stmt)
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(404, "Strategy not found or not clonable.")

    clone = Strategy(
        strategy_id=uuid.uuid4(),
        user_id=current_user.user_id,
        name=f"{source.name} (Copy)",
        description=source.description,
        strategy_type=source.strategy_type,
        category=source.category,
        timeframe=source.timeframe,
        asset_class=source.asset_class,
        definition_json=source.definition_json,
        is_public=False,
        is_system=False,
        version=1,
    )
    db.add(clone)
    # Track marketplace usage (clone event)
    db.add(StrategyUsage(
        usage_id=uuid.uuid4(),
        strategy_id=strategy_id,
        user_id=current_user.user_id,
    ))
    await db.commit()
    await db.refresh(clone)
    return clone


# ── PineScript routes ────────────────────────────────────────────────


@router.post("/pinescript/validate", response_model=PineScriptValidateResponse)
@limiter.limit("5/minute")
async def validate_pinescript(
    body: PineScriptValidateRequest,
    request: Request,
    current_user=Depends(get_current_user),
):
    """Validate PineScript source code syntax.

    Parses the code with the lark grammar and returns any syntax errors.
    Does not create a strategy — use /pinescript/transpile for that.

    Args:
        body: Source code to validate.

    Returns:
        Validation result with boolean and error list.
    """
    from ..trading.pinescript import validate as ps_validate
    result = ps_validate(body.source_code)
    return PineScriptValidateResponse(
        valid=result.valid,
        errors=result.errors,
    )


@router.post("/pinescript/transpile", response_model=PineScriptTranspileResponse)
@limiter.limit("5/minute")
async def transpile_pinescript(
    body: PineScriptTranspileRequest,
    request: Request,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Transpile PineScript source and create a strategy.

    Attempts deterministic lark transpilation first. If that fails and
    ``use_llm_fallback`` is True, falls back to Ollama LLM translation.

    Args:
        body: PineScript source, name, description, and LLM fallback flag.

    Returns:
        Transpilation result with strategy ID and compiled definition.
    """
    from ..trading.pinescript import transpile as ps_transpile
    from ..trading.pinescript import PineScriptError

    definition = None
    warnings = []

    # Try deterministic transpilation first
    try:
        definition = ps_transpile(body.source_code)
    except PineScriptError as exc:
        if not body.use_llm_fallback:
            return PineScriptTranspileResponse(
                success=False,
                errors=[str(exc)],
            )
        # Fall through to LLM fallback
        warnings.append(f"Lark parse failed: {exc}. Attempting LLM fallback.")

    # LLM fallback
    if definition is None and body.use_llm_fallback:
        try:
            from ..trading.pinescript.llm_fallback import llm_transpile, LLMTranspileError
            definition = await llm_transpile(body.source_code)
        except LLMTranspileError as exc:
            return PineScriptTranspileResponse(
                success=False,
                errors=[f"LLM fallback failed: {exc}"],
                warnings=warnings,
            )

    if definition is None:
        return PineScriptTranspileResponse(
            success=False,
            errors=["Transpilation failed."],
            warnings=warnings,
        )

    # Create a Strategy row
    strategy = Strategy(
        strategy_id=uuid.uuid4(),
        user_id=current_user.user_id,
        name=body.name,
        description=body.description,
        strategy_type="pinescript",
        definition_json=definition,
    )
    db.add(strategy)
    await _audit(
        db, current_user.user_id, "strategy_created",
        record_id=strategy.strategy_id,
        new_values={"name": body.name, "type": "pinescript",
                    "transpile_method": definition.get("transpile_method")},
    )
    await db.commit()

    return PineScriptTranspileResponse(
        success=True,
        strategy_id=strategy.strategy_id,
        transpile_method=definition.get("transpile_method"),
        definition_json=definition,
        warnings=warnings,
    )


# ── Strategy Version History routes ──────────────────────────────────


@router.get("/strategies/{strategy_id}/versions", response_model=list)
async def list_strategy_versions(
    strategy_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List version history for a strategy.

    Args:
        strategy_id: UUID of the strategy.

    Returns:
        List of version snapshots (newest first).
    """
    # Verify access
    strat_stmt = select(Strategy).where(
        Strategy.strategy_id == strategy_id,
        or_(
            Strategy.user_id == current_user.user_id,
            Strategy.is_system == True,  # noqa: E712
        ),
    )
    strat_result = await db.execute(strat_stmt)
    if not strat_result.scalar_one_or_none():
        raise HTTPException(404, "Strategy not found.")

    stmt = (
        select(StrategyVersion)
        .where(StrategyVersion.strategy_id == strategy_id)
        .order_by(StrategyVersion.version_number.desc())
    )
    result = await db.execute(stmt)
    versions = result.scalars().all()
    return [
        {
            "version_id": str(v.version_id),
            "strategy_id": str(v.strategy_id),
            "version_number": v.version_number,
            "definition_json": v.definition_json,
            "created_at": v.created_at.isoformat() if v.created_at else None,
        }
        for v in versions
    ]


@router.get("/strategies/{strategy_id}/versions/{version_number}")
async def get_strategy_version(
    strategy_id: uuid.UUID,
    version_number: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific version of a strategy.

    Args:
        strategy_id:    UUID of the strategy.
        version_number: Numeric version to retrieve.

    Returns:
        Version snapshot dict.
    """
    stmt = select(StrategyVersion).where(
        StrategyVersion.strategy_id == strategy_id,
        StrategyVersion.version_number == version_number,
    )
    result = await db.execute(stmt)
    version = result.scalar_one_or_none()
    if not version:
        raise HTTPException(404, "Version not found.")
    return {
        "version_id": str(version.version_id),
        "strategy_id": str(version.strategy_id),
        "version_number": version.version_number,
        "definition_json": version.definition_json,
        "created_at": version.created_at.isoformat() if version.created_at else None,
    }


@router.post("/strategies/{strategy_id}/revert/{version_number}", response_model=StrategyOut)
@limiter.limit("10/minute")
async def revert_strategy_version(
    strategy_id: uuid.UUID,
    version_number: int,
    request: Request,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revert a strategy to a previous version.

    Creates a new version snapshot of the current state, then replaces
    the definition with the specified historical version.

    Args:
        strategy_id:    UUID of the strategy.
        version_number: Version to revert to.

    Returns:
        Updated strategy.
    """
    # Load the strategy
    strat_stmt = select(Strategy).where(
        Strategy.strategy_id == strategy_id,
        Strategy.user_id == current_user.user_id,
    )
    strat_result = await db.execute(strat_stmt)
    strategy = strat_result.scalar_one_or_none()
    if not strategy:
        raise HTTPException(404, "Strategy not found or not owned by you.")
    if strategy.is_system:
        raise HTTPException(403, "Cannot modify system strategies.")

    # Load the target version
    ver_stmt = select(StrategyVersion).where(
        StrategyVersion.strategy_id == strategy_id,
        StrategyVersion.version_number == version_number,
    )
    ver_result = await db.execute(ver_stmt)
    target_version = ver_result.scalar_one_or_none()
    if not target_version:
        raise HTTPException(404, f"Version {version_number} not found.")

    # Snapshot current state before reverting
    snapshot = StrategyVersion(
        version_id=uuid.uuid4(),
        strategy_id=strategy.strategy_id,
        version_number=strategy.version,
        definition_json=strategy.definition_json,
    )
    db.add(snapshot)

    # Revert
    strategy.definition_json = target_version.definition_json
    strategy.version += 1
    strategy.updated_at = datetime.utcnow()

    await _audit(
        db, current_user.user_id, "strategy_reverted",
        record_id=strategy.strategy_id,
        new_values={"reverted_to_version": version_number},
    )
    await db.commit()
    await db.refresh(strategy)
    return strategy


# ── Composition route ────────────────────────────────────────────────


@router.post("/compose", response_model=StrategyOut, status_code=201)
@limiter.limit("5/minute")
async def create_composed_strategy(
    body: CompositionRequest,
    request: Request,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a composed strategy from indicator nodes and logic expressions.

    The composition_json should contain:
      - indicators: list of indicator node definitions
      - entry_expr: boolean expression for entry (e.g. "fast_sma > slow_sma")
      - exit_expr: boolean expression for exit
      - stop_loss: optional stop loss config
      - params: default parameter values
      - param_schema: parameter definitions for the UI

    Args:
        body: Composition creation payload.

    Returns:
        The newly created strategy.
    """
    # Validate expressions are safe
    from ..trading.engine.composition import _validate_expression
    comp = body.composition_json

    entry_expr = comp.get("entry_expr", "")
    exit_expr = comp.get("exit_expr", "")

    if entry_expr:
        try:
            _validate_expression(entry_expr)
        except ValueError as exc:
            raise HTTPException(400, f"Invalid entry expression: {exc}")
    if exit_expr:
        try:
            _validate_expression(exit_expr)
        except ValueError as exc:
            raise HTTPException(400, f"Invalid exit expression: {exc}")

    # Build definition_json — normalize node format to fn/args
    raw_nodes = comp.get("nodes", comp.get("indicators", []))
    indicators = []
    for node in raw_nodes:
        indicators.append({
            "fn": node.get("fn", node.get("indicator", "")),
            "args": node.get("args", node.get("params", {})),
            "output_var": node.get("output_var", ""),
        })

    definition = {
        "strategy_slug": f"composed_{uuid.uuid4().hex[:8]}",
        "source_type": "composed",
        "compiled": {
            "indicators": indicators,
            "entry_expr": entry_expr,
            "exit_expr": exit_expr,
            "stop_loss": comp.get("stop_loss"),
            "stop_loss_pct": comp.get("stop_loss_pct"),
        },
        "params": comp.get("params", {}),
        "param_schema": comp.get("param_schema", []),
    }

    strategy = Strategy(
        strategy_id=uuid.uuid4(),
        user_id=current_user.user_id,
        name=body.name,
        description=body.description,
        strategy_type="composed",
        definition_json=definition,
    )
    db.add(strategy)
    await _audit(
        db, current_user.user_id, "strategy_created",
        record_id=strategy.strategy_id,
        new_values={"name": body.name, "type": "composed"},
    )
    await db.commit()
    await db.refresh(strategy)
    return strategy


# ── Backtest routes ───────────────────────────────────────────────────────

@router.post("/backtest", response_model=BacktestResultOut, status_code=201)
@limiter.limit("5/minute")
async def queue_backtest(
    body: BacktestRequest,
    request: Request,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Queue a backtest job for async execution by the arq worker.

    Creates a BacktestResult row with status='pending' and enqueues
    the job.  The frontend polls GET /backtest/{id} for results.

    Accepts either ``strategy_id`` (UUID) or ``strategy_slug`` (string).
    When a slug is provided, the route looks up the matching system
    strategy by its ``definition_json`` content.

    Args:
        body: Backtest request payload.

    Returns:
        The pending backtest result (poll for status updates).

    Raises:
        429: Too many concurrent backtests.
        404: Strategy slug not found.
    """
    # Enforce a per-user concurrent backtest limit to prevent queue flooding.
    stmt = select(BacktestResult).where(
        BacktestResult.user_id == current_user.user_id,
        BacktestResult.status.in_(["pending", "running"]),
    )
    result = await db.execute(stmt)
    active = result.scalars().all()
    if len(active) >= 3:
        raise HTTPException(429, "Maximum 3 concurrent backtests. Wait for one to finish.")

    # Resolve strategy_id from slug if not provided directly
    strategy_id = body.strategy_id
    if not strategy_id and body.strategy_slug:
        slug_stmt = select(
            Strategy.strategy_id, Strategy.definition_json,
        ).where(Strategy.is_system == True)  # noqa: E712
        slug_result = await db.execute(slug_stmt)
        for row in slug_result.all():
            defn = row.definition_json or {}
            if defn.get("strategy_slug") == body.strategy_slug:
                strategy_id = row.strategy_id
                break
        if not strategy_id:
            raise HTTPException(404, f"No system strategy found for slug '{body.strategy_slug}'.")

    # Merge params alias into parameters_json
    parameters_json = body.parameters_json or body.params

    # Parse date strings into datetime objects
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=365)
    if body.end_date:
        try:
            end_date = datetime.fromisoformat(body.end_date)
        except ValueError:
            raise HTTPException(400, f"Invalid end_date format: {body.end_date}")
    if body.start_date:
        try:
            start_date = datetime.fromisoformat(body.start_date)
        except ValueError:
            raise HTTPException(400, f"Invalid start_date format: {body.start_date}")

    bt = BacktestResult(
        result_id=uuid.uuid4(),
        user_id=current_user.user_id,
        strategy_id=strategy_id,
        symbol=body.symbol.upper(),
        interval=body.interval,
        start_date=start_date,
        end_date=end_date,
        parameters_json=parameters_json,
        commission_per_trade=body.commission_per_trade or 1.00,
        slippage_pct=body.slippage_pct or 0.0005,
        status="pending",
    )
    db.add(bt)

    await _audit(
        db, current_user.user_id, "backtest_queued",
        record_id=bt.result_id,
        new_values={
            "strategy_id": str(strategy_id),
            "symbol": body.symbol.upper(),
            "interval": body.interval,
        },
    )
    await db.commit()

    # Eagerly load all attributes to prevent MissingGreenlet during
    # Pydantic serialization (JSONB columns trigger lazy loading).
    await db.refresh(bt)

    # Enqueue arq job (imported lazily to avoid circular imports)
    try:
        from ..trading.worker import enqueue_backtest
        await enqueue_backtest(str(bt.result_id))
    except Exception:
        # If enqueue fails, the worker will pick it up via polling
        pass

    return bt


@router.get("/backtest/{result_id}", response_model=BacktestResultOut)
async def get_backtest(
    result_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a backtest result by ID (poll for completion).

    Args:
        result_id: UUID of the backtest result.

    Returns:
        Backtest result with current status and data (if completed).

    Raises:
        404: Backtest not found.
    """
    stmt = select(BacktestResult).where(
        BacktestResult.result_id == result_id,
        BacktestResult.user_id == current_user.user_id,
    )
    result = await db.execute(stmt)
    bt = result.scalar_one_or_none()
    if not bt:
        raise HTTPException(404, "Backtest result not found.")
    # Eagerly load all attributes to prevent MissingGreenlet during
    # Pydantic serialization (JSONB columns trigger lazy loading).
    await db.refresh(bt)
    return bt


@router.get("/backtest/history", response_model=List[BacktestResultOut])
async def list_backtests(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List the current user's backtest history (newest first).

    Args:
        limit:  Max results per page.
        offset: Pagination offset.

    Returns:
        Paginated list of backtest results.
    """
    stmt = (
        select(BacktestResult)
        .where(BacktestResult.user_id == current_user.user_id)
        .order_by(BacktestResult.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    # Eagerly load all attributes to prevent MissingGreenlet during
    # Pydantic serialization (JSONB columns trigger lazy loading).
    for row in rows:
        await db.refresh(row)
    return rows


# ── Signal routes ─────────────────────────────────────────────────────────

@router.get("/signals/{strategy_id}", response_model=List[TradingSignalOut])
async def get_strategy_signals(
    strategy_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get active signals for a specific strategy.

    Args:
        strategy_id: UUID of the strategy.

    Returns:
        List of active trading signals.
    """
    stmt = (
        select(TradingSignal)
        .where(
            TradingSignal.strategy_id == strategy_id,
            TradingSignal.user_id == current_user.user_id,
            TradingSignal.is_active == True,  # noqa: E712
        )
        .order_by(TradingSignal.created_at.desc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/signals/symbol/{symbol}", response_model=List[TradingSignalOut])
async def get_symbol_signals(
    symbol: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all active signals for a specific symbol.

    Args:
        symbol: Ticker symbol.

    Returns:
        List of active trading signals across all strategies.
    """
    stmt = (
        select(TradingSignal)
        .where(
            TradingSignal.symbol == symbol.upper(),
            TradingSignal.user_id == current_user.user_id,
            TradingSignal.is_active == True,  # noqa: E712
        )
        .order_by(TradingSignal.created_at.desc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()


# ── Notification routes ──────────────────────────────────────────────────

@router.get("/notifications", response_model=PaginatedNotificationsResponse)
async def list_notifications(
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    unread_only: bool = Query(False),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List the current user's notifications (newest first).

    Args:
        limit:       Max results per page.
        offset:      Pagination offset.
        unread_only: If True, only return unread notifications.

    Returns:
        Paginated list with total count and unread count.
    """
    base_filter = [Notification.user_id == current_user.user_id]
    if unread_only:
        base_filter.append(Notification.is_read == False)  # noqa: E712

    # Total matching count
    count_stmt = select(func.count(Notification.notification_id)).where(*base_filter)
    total = (await db.execute(count_stmt)).scalar() or 0

    # Unread count (always, regardless of filter)
    unread_stmt = select(func.count(Notification.notification_id)).where(
        Notification.user_id == current_user.user_id,
        Notification.is_read == False,  # noqa: E712
    )
    unread_count = (await db.execute(unread_stmt)).scalar() or 0

    # Fetch page
    stmt = (
        select(Notification)
        .where(*base_filter)
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    notifications = result.scalars().all()

    return PaginatedNotificationsResponse(
        notifications=notifications,
        total=total,
        unread_count=unread_count,
        limit=limit,
        offset=offset,
    )


@router.post("/notifications/read", status_code=204)
async def mark_notifications_read(
    body: NotificationMarkRead,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark one or more notifications as read.

    Args:
        body: List of notification UUIDs to mark as read.
    """
    stmt = (
        update(Notification)
        .where(
            Notification.user_id == current_user.user_id,
            Notification.notification_id.in_(body.notification_ids),
        )
        .values(is_read=True)
    )
    await db.execute(stmt)
    await db.commit()


@router.post("/notifications/read-all", status_code=204)
async def mark_all_notifications_read(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark all of the current user's notifications as read."""
    stmt = (
        update(Notification)
        .where(
            Notification.user_id == current_user.user_id,
            Notification.is_read == False,  # noqa: E712
        )
        .values(is_read=True)
    )
    await db.execute(stmt)
    await db.commit()


# ── Webhook routes ───────────────────────────────────────────────────────

async def _require_safe_webhook_url(url: str) -> None:
    """Reject webhook URLs that could be used for SSRF (see
    trading/notifications.py for the shape + DNS checks). Registration-time
    rejection catches obvious cases early; _fire_webhooks re-checks the host
    immediately before every send since DNS can change afterward."""
    try:
        host = validate_webhook_url_shape(url)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not await check_webhook_host_safe(host):
        raise HTTPException(400, "Webhook host does not resolve to a permitted public address.")


@router.get("/webhooks", response_model=List[WebhookOut])
async def list_webhooks(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all webhooks configured by the current user.

    Returns:
        List of webhook objects ordered by creation date.
    """
    stmt = (
        select(UserWebhook)
        .where(UserWebhook.user_id == current_user.user_id)
        .order_by(UserWebhook.created_at.desc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/webhooks", response_model=WebhookOut, status_code=201)
@limiter.limit("10/minute")
async def create_webhook(
    body: WebhookCreate,
    request: Request,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register a new webhook endpoint.

    Args:
        body: Webhook creation payload (url + event types).

    Returns:
        The newly created webhook.

    Raises:
        400: Invalid URL scheme (must be https).
        429: Max 5 webhooks per user.
    """
    await _require_safe_webhook_url(body.url)

    count_stmt = select(func.count(UserWebhook.webhook_id)).where(
        UserWebhook.user_id == current_user.user_id,
    )
    count = (await db.execute(count_stmt)).scalar() or 0
    if count >= 5:
        raise HTTPException(429, "Maximum 5 webhooks allowed. Delete one first.")

    wh = UserWebhook(
        webhook_id=uuid.uuid4(),
        user_id=current_user.user_id,
        url=body.url,
        events=body.events,
    )
    db.add(wh)
    await db.commit()
    return wh


@router.patch("/webhooks/{webhook_id}", response_model=WebhookOut)
async def update_webhook(
    webhook_id: uuid.UUID,
    body: WebhookUpdate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a webhook's URL, events, or active status.

    Args:
        webhook_id: UUID of the webhook to update.
        body:       Partial update payload.

    Returns:
        Updated webhook.

    Raises:
        404: Webhook not found or not owned by user.
        400: Invalid URL scheme.
    """
    stmt = select(UserWebhook).where(
        UserWebhook.webhook_id == webhook_id,
        UserWebhook.user_id == current_user.user_id,
    )
    result = await db.execute(stmt)
    wh = result.scalar_one_or_none()
    if not wh:
        raise HTTPException(404, "Webhook not found.")

    updates = body.dict(exclude_unset=True)
    if "url" in updates:
        await _require_safe_webhook_url(updates["url"])

    for key, value in updates.items():
        setattr(wh, key, value)
    await db.commit()
    return wh


@router.delete("/webhooks/{webhook_id}", status_code=204)
async def delete_webhook(
    webhook_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a webhook.

    Args:
        webhook_id: UUID of the webhook to delete.

    Raises:
        404: Webhook not found or not owned by user.
    """
    stmt = select(UserWebhook).where(
        UserWebhook.webhook_id == webhook_id,
        UserWebhook.user_id == current_user.user_id,
    )
    result = await db.execute(stmt)
    wh = result.scalar_one_or_none()
    if not wh:
        raise HTTPException(404, "Webhook not found.")

    await db.delete(wh)
    await db.commit()


# ── Market Regime routes ─────────────────────────────────────────────────

# URL of the trading-ml container (internal Docker network)
_TRADING_ML_URL = os.getenv("TRADING_ML_URL", "http://trading-ml:8001")


@router.post("/regime", response_model=RegimeResponse)
@limiter.limit("10/minute")
async def detect_regime(
    body: RegimeRequest,
    request: Request,
    current_user=Depends(get_current_user),
):
    """Detect the current market regime for a symbol.

    Fetches OHLCV data via yfinance and sends it to the trading-ml
    container's regime detector.  Falls back to a simple rule-based
    classifier if the ML service is unavailable.

    Args:
        body: Symbol, interval, and lookback period.

    Returns:
        RegimeResponse with regime type, confidence, and metrics.
    """
    import httpx
    import yfinance as yf

    symbol = body.symbol.upper()

    # Fetch OHLCV data from yfinance
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=f"{body.period_days}d", interval=body.interval)
        if hist.empty:
            raise HTTPException(400, f"No price data found for {symbol}.")
    except Exception as exc:
        raise HTTPException(502, f"Failed to fetch market data: {exc}")

    # Convert to bar dicts for the ML service
    bars = []
    for idx, row in hist.iterrows():
        bars.append({
            "timestamp": idx.isoformat(),
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "volume": float(row["Volume"]),
        })

    if len(bars) < 60:
        raise HTTPException(400, "Insufficient data for regime detection (need 60+ bars).")

    # Call trading-ml regime endpoint
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{_TRADING_ML_URL}/predict/regime",
                json={"symbol": symbol, "bars": bars},
            )
            if resp.status_code == 200:
                data = resp.json()
                return RegimeResponse(
                    symbol=symbol,
                    regime=data["regime"],
                    confidence=data["confidence"],
                    volatility_percentile=data.get("volatility_percentile", 0),
                    trend_strength=data.get("trend_strength", 0),
                )
    except Exception:
        pass  # Fall through to rule-based fallback

    # Fallback: rule-based regime detection (no ML container needed)
    import numpy as np

    closes = np.array([b["close"] for b in bars], dtype=np.float64)
    highs = np.array([b["high"] for b in bars], dtype=np.float64)
    lows = np.array([b["low"] for b in bars], dtype=np.float64)

    log_ret = np.diff(np.log(np.maximum(closes, 1e-8)))
    recent_vol = np.std(log_ret[-20:]) if len(log_ret) >= 20 else 0
    hist_vol = np.std(log_ret) if len(log_ret) > 0 else 0.001
    vol_pctl = min(100.0, (recent_vol / hist_vol) * 50) if hist_vol > 0 else 50.0

    sma20 = np.convolve(closes, np.ones(20) / 20, mode="valid")
    sma_slope = (sma20[-1] - sma20[-5]) / sma20[-5] if len(sma20) >= 5 and sma20[-5] > 0 else 0

    if vol_pctl > 80:
        regime, conf = "high_volatility", min(0.90, 0.5 + (vol_pctl - 80) / 40)
    elif sma_slope > 0.005:
        regime, conf = "trending_up", 0.70
    elif sma_slope < -0.005:
        regime, conf = "trending_down", 0.70
    else:
        regime, conf = "mean_reverting", 0.60

    return RegimeResponse(
        symbol=symbol,
        regime=regime,
        confidence=round(conf, 4),
        volatility_percentile=round(vol_pctl, 2),
        trend_strength=round(abs(sma_slope) * 1000, 2),
    )


# ── Internal endpoints (Server B strategy scripts) ──────────────────────


@router.get("/internal/recent-backtests")
async def internal_recent_backtests(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Return recent completed backtests for strategy research.

    Called by Server B's strategy_researcher.py to analyse recent
    backtest performance and suggest improvements.

    Args:
        request: FastAPI request (for internal auth).
        limit:   Max results to return.
        db:      Async database session.

    Returns:
        JSON list of backtest summary dicts.
    """
    _verify_internal_auth(request)

    # Join BacktestResult with Strategy to get strategy_name
    stmt = (
        select(BacktestResult, Strategy.name.label("strategy_name"))
        .outerjoin(Strategy, BacktestResult.strategy_id == Strategy.strategy_id)
        .where(BacktestResult.status == "completed")
        .order_by(BacktestResult.completed_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.all()

    backtests = []
    for bt, strategy_name in rows:
        metrics = bt.metrics_json or {}
        backtests.append({
            "result_id": str(bt.result_id),
            "strategy_name": strategy_name or "Unknown",
            "symbol": bt.symbol,
            "interval": bt.interval,
            "sharpe_ratio": metrics.get("sharpe_ratio", 0),
            "total_return_pct": metrics.get("total_return_pct", 0),
            "win_rate": metrics.get("win_rate", 0),
            "total_trades": metrics.get("total_trades", 0),
            "max_drawdown_pct": metrics.get("max_drawdown_pct", 0),
            "completed_at": bt.completed_at.isoformat() if bt.completed_at else None,
        })

    return backtests


@router.get("/internal/regime-summary")
async def internal_regime_summary(request: Request):
    """Return a quick regime summary for the overall market (SPY).

    Called by Server B's strategy_researcher.py to add market context
    to the research prompt. Uses the same rule-based fallback as the
    public /regime endpoint.

    Args:
        request: FastAPI request (for internal auth).

    Returns:
        JSON dict with regime, confidence, volatility_percentile, trend_strength.
    """
    _verify_internal_auth(request)

    import numpy as np
    import yfinance as yf

    try:
        ticker = yf.Ticker("SPY")
        hist = ticker.history(period="180d", interval="1d")
        if hist.empty:
            return {"regime": "unknown", "confidence": 0, "volatility_percentile": 0, "trend_strength": 0}
    except Exception:
        return {"regime": "unknown", "confidence": 0, "volatility_percentile": 0, "trend_strength": 0}

    closes = np.array(hist["Close"].values, dtype=np.float64)
    log_ret = np.diff(np.log(np.maximum(closes, 1e-8)))
    recent_vol = np.std(log_ret[-20:]) if len(log_ret) >= 20 else 0
    hist_vol = np.std(log_ret) if len(log_ret) > 0 else 0.001
    vol_pctl = min(100.0, (recent_vol / hist_vol) * 50) if hist_vol > 0 else 50.0

    sma20 = np.convolve(closes, np.ones(20) / 20, mode="valid")
    sma_slope = (sma20[-1] - sma20[-5]) / sma20[-5] if len(sma20) >= 5 and sma20[-5] > 0 else 0

    if vol_pctl > 80:
        regime, conf = "high_volatility", min(0.90, 0.5 + (vol_pctl - 80) / 40)
    elif sma_slope > 0.005:
        regime, conf = "trending_up", 0.70
    elif sma_slope < -0.005:
        regime, conf = "trending_down", 0.70
    else:
        regime, conf = "mean_reverting", 0.60

    return {
        "regime": regime,
        "confidence": round(conf, 4),
        "volatility_percentile": round(vol_pctl, 2),
        "trend_strength": round(abs(sma_slope) * 1000, 2),
    }


@router.post("/internal/recommendations", status_code=201)
async def internal_post_recommendations(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Receive strategy recommendations from Server B's researcher.

    Stores recommendations as user notifications for review.  Each
    recommendation is saved as a separate notification so the user
    can act on them individually.

    Args:
        request: FastAPI request (for internal auth + JSON body).
        db:      Async database session.

    Returns:
        Dict with count of stored recommendations.
    """
    _verify_internal_auth(request)

    body = await request.json()
    recommendations = body.get("recommendations", [])
    overall = body.get("overall_assessment", "")
    regime_analysis = body.get("regime_analysis", "")

    # Fetch all active user IDs for broadcast
    uid_stmt = select(User.user_id).where(User.is_active == True)  # noqa: E712
    uid_result = await db.execute(uid_stmt)
    user_ids = [row[0] for row in uid_result.all()]

    if not user_ids:
        return {"stored": 0}

    stored = 0
    for uid in user_ids:
        # Summary notification
        if overall or regime_analysis:
            summary_detail = {}
            if regime_analysis:
                summary_detail["regime_analysis"] = regime_analysis
            if overall:
                summary_detail["overall_assessment"] = overall
            summary_detail["type"] = "strategy_research_summary"

            db.add(Notification(
                notification_id=uuid.uuid4(),
                user_id=uid,
                event_type="strategy_research",
                title="AI Strategy Research Summary",
                body=overall[:500] if overall else regime_analysis[:500],
                metadata_json=summary_detail,
            ))

        # Individual recommendation notifications
        for rec in recommendations[:8]:
            db.add(Notification(
                notification_id=uuid.uuid4(),
                user_id=uid,
                event_type="strategy_recommendation",
                title=f"Strategy Rec: {rec.get('strategy', 'Unknown')} — {rec.get('type', 'adjust')}",
                body=rec.get("reason", "")[:500],
                metadata_json=rec,
            ))
            stored += 1

    await db.commit()
    return {"stored": stored}


@router.get("/internal/backtest-history")
async def internal_backtest_history(
    request: Request,
    limit: int = Query(500, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """Return extended backtest history for strategy-regime learning.

    Called by Server B's strategy_learner.py to build strategy
    performance profiles per regime.  Similar to recent-backtests
    but with a higher limit and regime field.

    Args:
        request: FastAPI request (for internal auth).
        limit:   Max results to return.
        db:      Async database session.

    Returns:
        JSON list of backtest dicts with regime info.
    """
    _verify_internal_auth(request)

    stmt = (
        select(BacktestResult, Strategy.name.label("strategy_name"))
        .outerjoin(Strategy, BacktestResult.strategy_id == Strategy.strategy_id)
        .where(BacktestResult.status == "completed")
        .order_by(BacktestResult.completed_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.all()

    backtests = []
    for bt, strategy_name in rows:
        metrics = bt.metrics_json or {}
        params = bt.parameters_json or {}
        backtests.append({
            "result_id": str(bt.result_id),
            "strategy_name": strategy_name or "Unknown",
            "symbol": bt.symbol,
            "interval": bt.interval,
            "regime": params.get("regime", "unknown"),
            "total_return_pct": metrics.get("total_return_pct", 0),
            "sharpe_ratio": metrics.get("sharpe_ratio", 0),
            "win_rate": metrics.get("win_rate", 0),
            "total_trades": metrics.get("total_trades", 0),
            "max_drawdown_pct": metrics.get("max_drawdown_pct", 0),
            "completed_at": bt.completed_at.isoformat() if bt.completed_at else None,
        })

    return backtests


@router.post("/internal/strategy-rules", status_code=201)
async def internal_post_strategy_rules(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Receive learned strategy-regime fitness rules from Server B.

    Stores the rules as system notifications and optionally updates
    strategy metadata with regime fitness info.

    Args:
        request: FastAPI request (for internal auth + JSON body).
        db:      Async database session.

    Returns:
        Dict with count of stored rules.
    """
    _verify_internal_auth(request)

    body = await request.json()
    strategy_rules = body.get("strategy_rules", [])
    regime_recs = body.get("regime_recommendations", {})
    insights = body.get("insights", "")
    sample_size = body.get("sample_size", 0)

    # Fetch all active user IDs for broadcast
    uid_stmt = select(User.user_id).where(User.is_active == True)  # noqa: E712
    uid_result = await db.execute(uid_stmt)
    user_ids = [row[0] for row in uid_result.all()]

    if not user_ids:
        return {"stored": 0}

    stored = 0
    for uid in user_ids:
        # Summary notification
        if insights:
            db.add(Notification(
                notification_id=uuid.uuid4(),
                user_id=uid,
                event_type="strategy_learning",
                title="AI Strategy-Regime Learning Update",
                body=insights[:500],
                metadata_json={
                    "type": "strategy_learning_summary",
                    "regime_recommendations": regime_recs,
                    "sample_size": sample_size,
                },
            ))

        # Individual strategy rule notifications
        for rule in strategy_rules:
            best = ", ".join(rule.get("best_regimes", []))
            avoid = ", ".join(rule.get("avoid_regimes", []))
            db.add(Notification(
                notification_id=uuid.uuid4(),
                user_id=uid,
                event_type="strategy_rule",
                title=f"Strategy Rule: {rule.get('strategy', 'Unknown')}",
                body=f"Best in: {best}. Avoid: {avoid}. {rule.get('notes', '')}"[:500],
                metadata_json=rule,
            ))
            stored += 1

    await db.commit()
    return {"stored": stored}


# ─── MARKETPLACE ─────────────────────────────────────────────────────────────


@router.get("/marketplace", response_model=List[MarketplaceStrategyOut])
@limiter.limit("30/minute")
async def browse_marketplace(
    request: Request,
    category: Optional[str] = None,
    timeframe: Optional[str] = None,
    asset_class: Optional[str] = None,
    sort_by: Optional[str] = "newest",
    search: Optional[str] = None,
    limit: int = 25,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Browse the public strategy marketplace.

    Returns paginated list of public strategies with author name,
    average rating, rating count, and clone count. Supports filtering
    by category, timeframe, asset class, and search term.
    """
    # Base query: public strategies with author info + aggregated stats
    stmt = (
        select(
            Strategy,
            User.first_name.label("author_name"),
            func.coalesce(func.avg(StrategyRating.stars), None).label("avg_rating"),
            func.count(distinct(StrategyRating.rating_id)).label("rating_count"),
            func.count(distinct(StrategyUsage.usage_id)).label("clone_count"),
        )
        .join(User, Strategy.user_id == User.user_id)
        .outerjoin(StrategyRating, Strategy.strategy_id == StrategyRating.strategy_id)
        .outerjoin(StrategyUsage, Strategy.strategy_id == StrategyUsage.strategy_id)
        .where(Strategy.is_public == True)
        .group_by(Strategy.strategy_id, User.first_name)
    )

    # -- Filters --
    if category:
        stmt = stmt.where(Strategy.category == category)
    if timeframe:
        stmt = stmt.where(Strategy.timeframe == timeframe)
    if asset_class:
        stmt = stmt.where(Strategy.asset_class == asset_class)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            or_(
                Strategy.name.ilike(pattern),
                Strategy.description.ilike(pattern),
            )
        )

    # -- Sorting --
    sort_map = {
        "newest": Strategy.created_at.desc(),
        "oldest": Strategy.created_at.asc(),
        "most_cloned": func.count(distinct(StrategyUsage.usage_id)).desc(),
        "top_rated": func.coalesce(func.avg(StrategyRating.stars), 0).desc(),
        "name_asc": Strategy.name.asc(),
    }
    stmt = stmt.order_by(sort_map.get(sort_by, Strategy.created_at.desc()))

    # -- Pagination --
    stmt = stmt.limit(min(limit, 100)).offset(offset)

    rows = (await db.execute(stmt)).all()

    results = []
    for row in rows:
        strat = row[0]
        results.append(MarketplaceStrategyOut(
            strategy_id=str(strat.strategy_id),
            user_id=str(strat.user_id),
            name=strat.name,
            slug=strat.slug,
            description=strat.description or "",
            category=strat.category or "",
            timeframe=strat.timeframe or "",
            asset_class=strat.asset_class or "",
            is_public=strat.is_public,
            created_at=strat.created_at,
            author_name=row.author_name or "Anonymous",
            avg_rating=round(float(row.avg_rating), 2) if row.avg_rating else None,
            rating_count=row.rating_count,
            clone_count=row.clone_count,
        ))

    return results


@router.get("/marketplace/featured", response_model=List[MarketplaceStrategyOut])
@limiter.limit("30/minute")
async def featured_strategies(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Return top 10 featured public strategies.

    Featured = highest average rating (>= 3.0) with at least 1 rating,
    ordered by average rating descending, then by clone count.
    """
    stmt = (
        select(
            Strategy,
            User.first_name.label("author_name"),
            func.coalesce(func.avg(StrategyRating.stars), None).label("avg_rating"),
            func.count(distinct(StrategyRating.rating_id)).label("rating_count"),
            func.count(distinct(StrategyUsage.usage_id)).label("clone_count"),
        )
        .join(User, Strategy.user_id == User.user_id)
        .outerjoin(StrategyRating, Strategy.strategy_id == StrategyRating.strategy_id)
        .outerjoin(StrategyUsage, Strategy.strategy_id == StrategyUsage.strategy_id)
        .where(Strategy.is_public == True)
        .group_by(Strategy.strategy_id, User.first_name)
        .having(func.avg(StrategyRating.stars) >= 3.0)
        .order_by(
            func.avg(StrategyRating.stars).desc(),
            func.count(distinct(StrategyUsage.usage_id)).desc(),
        )
        .limit(10)
    )

    rows = (await db.execute(stmt)).all()

    results = []
    for row in rows:
        strat = row[0]
        results.append(MarketplaceStrategyOut(
            strategy_id=str(strat.strategy_id),
            user_id=str(strat.user_id),
            name=strat.name,
            slug=strat.slug,
            description=strat.description or "",
            category=strat.category or "",
            timeframe=strat.timeframe or "",
            asset_class=strat.asset_class or "",
            is_public=strat.is_public,
            created_at=strat.created_at,
            author_name=row.author_name or "Anonymous",
            avg_rating=round(float(row.avg_rating), 2) if row.avg_rating else None,
            rating_count=row.rating_count,
            clone_count=row.clone_count,
        ))

    return results


@router.post("/strategies/{strategy_id}/rate", response_model=RatingOut)
@limiter.limit("10/minute")
async def rate_strategy(
    strategy_id: str,
    body: RatingCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Rate a public strategy (upsert — one rating per user per strategy).

    Users cannot rate their own strategies. Stars must be 1–5.
    If the user has already rated this strategy, their rating is updated.
    """
    uid = current_user.user_id
    sid = uuid.UUID(strategy_id)

    # Verify strategy exists and is public
    strat = (await db.execute(
        select(Strategy).where(Strategy.strategy_id == sid)
    )).scalar_one_or_none()
    if not strat:
        raise HTTPException(404, "Strategy not found")
    if not strat.is_public:
        raise HTTPException(403, "Cannot rate a private strategy")
    if strat.user_id == uid:
        raise HTTPException(403, "Cannot rate your own strategy")

    # Check for existing rating (upsert)
    existing = (await db.execute(
        select(StrategyRating).where(
            StrategyRating.strategy_id == sid,
            StrategyRating.user_id == uid,
        )
    )).scalar_one_or_none()

    if existing:
        existing.stars = body.stars
        existing.review = body.review
        await db.commit()
        await db.refresh(existing)
        rating = existing
    else:
        rating = StrategyRating(
            rating_id=uuid.uuid4(),
            strategy_id=sid,
            user_id=uid,
            stars=body.stars,
            review=body.review,
        )
        db.add(rating)
        await db.commit()
        await db.refresh(rating)

    # Fetch author name for response
    author_name = await _get_user_name(db, uid)

    return RatingOut(
        rating_id=str(rating.rating_id),
        strategy_id=str(rating.strategy_id),
        user_id=str(rating.user_id),
        author_name=author_name,
        stars=rating.stars,
        review=rating.review,
        created_at=rating.created_at,
    )


async def _get_user_name(db: AsyncSession, user_id: uuid.UUID) -> str:
    """Helper: fetch a user's display name (first_name or 'Anonymous')."""
    user = (await db.execute(
        select(User.first_name).where(User.user_id == user_id)
    )).scalar_one_or_none()
    return user or "Anonymous"


@router.get("/strategies/{strategy_id}/ratings", response_model=List[RatingOut])
@limiter.limit("30/minute")
async def list_ratings(
    strategy_id: str,
    request: Request,
    limit: int = 25,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    List all ratings for a strategy, paginated.

    Returns each rating with the reviewer's display name.
    """
    sid = uuid.UUID(strategy_id)

    stmt = (
        select(StrategyRating, User.first_name.label("author_name"))
        .join(User, StrategyRating.user_id == User.user_id)
        .where(StrategyRating.strategy_id == sid)
        .order_by(StrategyRating.created_at.desc())
        .limit(min(limit, 100))
        .offset(offset)
    )

    rows = (await db.execute(stmt)).all()

    return [
        RatingOut(
            rating_id=str(r.rating_id),
            strategy_id=str(r.strategy_id),
            user_id=str(r.user_id),
            author_name=author_name or "Anonymous",
            stars=r.stars,
            review=r.review,
            created_at=r.created_at,
        )
        for r, author_name in rows
    ]


@router.get("/strategies/{strategy_id}/stats", response_model=StrategyStatsOut)
@limiter.limit("30/minute")
async def get_strategy_stats(
    strategy_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Aggregate statistics for a strategy.

    Returns clone count, average rating, rating count, and backtest count.
    """
    sid = uuid.UUID(strategy_id)

    # Clone count
    clone_count = (await db.execute(
        select(func.count(StrategyUsage.usage_id)).where(
            StrategyUsage.strategy_id == sid
        )
    )).scalar() or 0

    # Rating stats
    rating_row = (await db.execute(
        select(
            func.avg(StrategyRating.stars),
            func.count(StrategyRating.rating_id),
        ).where(StrategyRating.strategy_id == sid)
    )).one()
    avg_rating = round(float(rating_row[0]), 2) if rating_row[0] else None
    rating_count = rating_row[1]

    # Backtest count
    backtest_count = (await db.execute(
        select(func.count(BacktestResult.result_id)).where(
            BacktestResult.strategy_id == sid
        )
    )).scalar() or 0

    return StrategyStatsOut(
        clone_count=clone_count,
        avg_rating=avg_rating,
        rating_count=rating_count,
        backtest_count=backtest_count,
    )


@router.post("/strategies/{strategy_id}/publish")
@limiter.limit("10/minute")
async def toggle_publish(
    strategy_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Toggle a strategy's public/private visibility.

    Only the strategy owner can publish or unpublish. Returns the new
    is_public state.
    """
    uid = current_user.user_id
    sid = uuid.UUID(strategy_id)

    strat = (await db.execute(
        select(Strategy).where(Strategy.strategy_id == sid)
    )).scalar_one_or_none()
    if not strat:
        raise HTTPException(404, "Strategy not found")
    if strat.user_id != uid:
        raise HTTPException(403, "Only the owner can publish/unpublish")

    strat.is_public = not strat.is_public
    await db.commit()
    await db.refresh(strat)

    return {"strategy_id": str(sid), "is_public": strat.is_public}


# ─── BACKTEST EXPORT ─────────────────────────────────────────────────────────


@router.get("/backtest/{result_id}/export")
@limiter.limit("10/minute")
async def export_backtest(
    result_id: str,
    request: Request,
    format: str = "csv",
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Export backtest results as a downloadable CSV file.

    Includes a summary section (metrics) followed by a trades table.
    The file is streamed as an attachment.
    """
    uid = current_user.user_id
    rid = uuid.UUID(result_id)

    result = (await db.execute(
        select(BacktestResult).where(BacktestResult.result_id == rid)
    )).scalar_one_or_none()
    if not result:
        raise HTTPException(404, "Backtest result not found")

    # Verify ownership via the backtest result itself
    if result.user_id != uid:
        raise HTTPException(403, "Not authorized to export this result")

    strat = (await db.execute(
        select(Strategy).where(Strategy.strategy_id == result.strategy_id)
    )).scalar_one_or_none()

    if format != "csv":
        raise HTTPException(400, "Only CSV export is currently supported")

    # Build CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # -- Metrics summary section --
    metrics = result.metrics_json or {}
    writer.writerow(["=== BACKTEST SUMMARY ==="])
    writer.writerow(["Strategy", strat.name])
    writer.writerow(["Symbol", result.symbol])
    writer.writerow(["Interval", result.interval])
    writer.writerow(["Period", f"{result.start_date} to {result.end_date}"])
    writer.writerow([])
    for key, val in metrics.items():
        writer.writerow([key, val])
    writer.writerow([])

    # -- Trades table --
    trades = (result.results_json or {}).get("trades", [])
    if trades:
        writer.writerow(["=== TRADES ==="])
        headers = list(trades[0].keys()) if trades else []
        writer.writerow(headers)
        for trade in trades:
            writer.writerow([trade.get(h, "") for h in headers])

    output.seek(0)
    filename = f"backtest_{result_id[:8]}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ─── BATCH BACKTEST ──────────────────────────────────────────────────────────


@router.post("/backtest/batch")
@limiter.limit("3/minute")
async def queue_batch_backtest(
    body: BatchBacktestRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Queue backtests for a strategy across multiple symbols.

    Accepts up to 20 symbols and enqueues individual backtest tasks
    for each. Returns a batch_id and list of backtest result IDs for
    polling.
    """
    uid = current_user.user_id

    if len(body.symbols) > 20:
        raise HTTPException(400, "Maximum 20 symbols per batch")
    if not body.symbols:
        raise HTTPException(400, "At least one symbol is required")

    # Resolve strategy
    strat = None
    strategy_id = None
    if body.strategy_id:
        strat = (await db.execute(
            select(Strategy).where(
                Strategy.strategy_id == uuid.UUID(body.strategy_id),
                Strategy.user_id == uid,
            )
        )).scalar_one_or_none()
        if strat:
            strategy_id = strat.strategy_id
    elif body.strategy_slug:
        # Check user strategies first (slug stored in definition_json)
        user_strats = (await db.execute(
            select(Strategy).where(Strategy.user_id == uid)
        )).scalars().all()
        for s in user_strats:
            defn = s.definition_json or {}
            if defn.get("strategy_slug") == body.strategy_slug:
                strat = s
                strategy_id = s.strategy_id
                break
        # Fall back to system strategies
        if not strat:
            sys_strats = (await db.execute(
                select(Strategy).where(Strategy.is_system == True)
            )).scalars().all()
            for s in sys_strats:
                defn = s.definition_json or {}
                if defn.get("strategy_slug") == body.strategy_slug:
                    strat = s
                    strategy_id = s.strategy_id
                    break

    if not strat:
        raise HTTPException(404, "Strategy not found")

    batch_id = str(uuid.uuid4())
    backtest_ids = []

    # Parse date strings
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=365)
    if body.end_date:
        try:
            end_date = datetime.fromisoformat(body.end_date)
        except ValueError:
            raise HTTPException(400, f"Invalid end_date: {body.end_date}")
    if body.start_date:
        try:
            start_date = datetime.fromisoformat(body.start_date)
        except ValueError:
            raise HTTPException(400, f"Invalid start_date: {body.start_date}")

    for symbol in body.symbols:
        result_id = uuid.uuid4()
        bt = BacktestResult(
            result_id=result_id,
            user_id=uid,
            strategy_id=strat.strategy_id,
            symbol=symbol.upper(),
            interval=body.interval or "1d",
            start_date=start_date,
            end_date=end_date,
            parameters_json=body.parameters or {},
            commission_per_trade=body.commission or 1.00,
            slippage_pct=body.slippage or 0.0005,
            status="pending",
        )
        db.add(bt)
        backtest_ids.append(str(result_id))

    await db.commit()

    # Enqueue arq tasks for each symbol (same pattern as queue_backtest)
    try:
        from ..trading.worker import enqueue_backtest
        for bid in backtest_ids:
            await enqueue_backtest(bid)
    except Exception:
        # If enqueue fails, the worker will pick them up via polling
        pass

    return {
        "batch_id": batch_id,
        "backtest_ids": backtest_ids,
        "symbol_count": len(body.symbols),
    }


# ─── PORTFOLIO SCORING ──────────────────────────────────────────────────────


# Strategy slugs evaluated by the portfolio scorer (best-of-3 selection).
_PORTFOLIO_SCORE_STRATEGIES = ["sma_crossover", "rsi_mean_reversion", "macd_crossover"]


async def _fetch_bars_for_symbol(symbol: str):
    """Fetch last ~200 daily bars for *symbol* via yfinance.

    Uses ``NormalizedDataService`` wrapping ``YFinanceProvider`` so the
    data is cache-friendly and normalised.

    Args:
        symbol: Ticker symbol (upper-cased by caller).

    Returns:
        List of ``OHLCVBar`` sorted chronologically.
    """
    from ..trading.providers.normalizer import NormalizedDataService
    from ..trading.providers.yfinance_provider import YFinanceProvider

    svc = NormalizedDataService(YFinanceProvider())
    end = datetime.utcnow()
    start = end - timedelta(days=300)  # request extra to guarantee ~200 bars
    return await svc.get_bars(symbol, "1d", start, end)


def _compute_trend(closes, sma_50, sma_200, idx):
    """Classify the trend at bar *idx* based on SMA positions.

    Rules:
        - "bullish"  — price above both 50-SMA and 200-SMA.
        - "bearish"  — price below both 50-SMA and 200-SMA.
        - "neutral"  — otherwise (price between the two averages).

    Args:
        closes:  List of close prices.
        sma_50:  50-period SMA series from ``indicators.sma``.
        sma_200: 200-period SMA series from ``indicators.sma``.
        idx:     Bar index to evaluate.

    Returns:
        Trend string: ``"bullish"``, ``"bearish"``, or ``"neutral"``.
    """
    price = closes[idx]
    s50 = sma_50[idx]
    s200 = sma_200[idx]
    if s50 == 0 or s200 == 0:
        return "neutral"
    if price > s50 and price > s200:
        return "bullish"
    if price < s50 and price < s200:
        return "bearish"
    return "neutral"


def _pick_best_signal(bars):
    """Run three core strategies on *bars* and return the most recent signal.

    Strategies evaluated: SMA crossover, RSI mean reversion, MACD crossover.
    For each, signals are generated with default parameters.  The strategy
    whose last signal is most recent wins.

    Args:
        bars: Chronologically sorted ``OHLCVBar`` list (>= 200 bars).

    Returns:
        Tuple of (signal_label, strategy_slug) where signal_label is one of
        ``"BUY"``, ``"SELL"``, or ``"HOLD"``, and strategy_slug identifies
        the winning strategy.
    """
    from ..trading.engine.strategies import get_strategy

    best_ts = None
    best_label = "HOLD"
    best_slug = _PORTFOLIO_SCORE_STRATEGIES[0]

    for slug in _PORTFOLIO_SCORE_STRATEGIES:
        try:
            strat = get_strategy(slug)
            signals = strat["generate_signals"](bars, strat["default_params"])
            if not signals:
                continue
            # Most recent signal from this strategy
            latest = max(signals, key=lambda s: s.timestamp)
            if best_ts is None or latest.timestamp > best_ts:
                best_ts = latest.timestamp
                best_slug = slug
                # Map signal_type + direction to a user-facing label
                if latest.signal_type == "entry" and latest.direction == "long":
                    best_label = "BUY"
                elif latest.signal_type in ("exit", "stop_loss"):
                    best_label = "SELL"
                else:
                    best_label = "HOLD"
        except Exception:
            continue

    return best_label, best_slug


def _compute_score(rsi_val, trend, volatility_pct, signal_label):
    """Compute a composite 1-100 position score.

    Scoring components (summed then clamped):
        - Base score 50.
        - RSI: +15 if in healthy 30-70, -10 if oversold (<30) or overbought (>70).
        - Trend alignment: +20 for bullish, -15 for bearish, 0 for neutral.
        - Volatility: +10 if < 3%, 0 if 3-6%, -10 if > 6%.
        - Signal boost: +15 for BUY, -15 for SELL, 0 for HOLD.

    Args:
        rsi_val:        Latest RSI value (0-100).
        trend:          ``"bullish"`` / ``"bearish"`` / ``"neutral"``.
        volatility_pct: ATR as a percentage of price.
        signal_label:   ``"BUY"`` / ``"SELL"`` / ``"HOLD"``.

    Returns:
        Integer score clamped to [1, 100].
    """
    score = 50

    # RSI component
    if 30 <= rsi_val <= 70:
        score += 15
    else:
        score -= 10

    # Trend component
    if trend == "bullish":
        score += 20
    elif trend == "bearish":
        score -= 15

    # Volatility component
    if volatility_pct < 3.0:
        score += 10
    elif volatility_pct > 6.0:
        score -= 10

    # Signal component
    if signal_label == "BUY":
        score += 15
    elif signal_label == "SELL":
        score -= 15

    return max(1, min(100, score))


def _generate_suggestion(trend, rsi_val, signal_label, volatility_pct):
    """Build a human-readable suggestion from indicator readings.

    Prioritises the most actionable observation: overbought/oversold RSI,
    strong trend alignment, or high volatility caution.

    Args:
        trend:          ``"bullish"`` / ``"bearish"`` / ``"neutral"``.
        rsi_val:        Latest RSI value (0-100).
        signal_label:   ``"BUY"`` / ``"SELL"`` / ``"HOLD"``.
        volatility_pct: ATR as a percentage of price.

    Returns:
        Suggestion string.
    """
    rsi_rounded = round(rsi_val, 1)

    # RSI extremes take priority
    if rsi_val >= 70:
        return f"RSI overbought ({rsi_rounded}). Consider taking profits."
    if rsi_val <= 30:
        return (
            f"RSI oversold ({rsi_rounded}). "
            "May present a buying opportunity if trend supports."
        )

    # Trend-based suggestions
    if trend == "bullish" and signal_label == "BUY":
        return (
            f"Strong uptrend with moderate RSI ({rsi_rounded}). "
            "Consider holding or adding to position."
        )
    if trend == "bullish":
        return (
            f"Uptrend intact with RSI at {rsi_rounded}. "
            "Consider holding."
        )
    if trend == "bearish" and signal_label == "SELL":
        return (
            f"Downtrend with RSI at {rsi_rounded}. "
            "Consider reducing exposure."
        )
    if trend == "bearish":
        return (
            f"Downtrend detected with RSI at {rsi_rounded}. "
            "Monitor for reversal signals."
        )

    # Neutral / high volatility
    if volatility_pct > 6.0:
        return (
            f"High volatility ({round(volatility_pct, 1)}% ATR). "
            "Consider tightening stop-losses."
        )

    return (
        f"Sideways movement with RSI at {rsi_rounded}. "
        "Wait for a clearer trend before acting."
    )


async def _analyze_single_symbol(
    symbol: str,
    position: Optional[PortfolioItem] = None,
) -> PositionScore:
    """Run full technical analysis on a single symbol.

    Fetches daily bars, computes trend / RSI / ATR / best strategy signal,
    and returns a ``PositionScore`` ready for serialisation.  When ``position``
    is provided, extended P&L and stop-loss status fields are also populated.

    Args:
        symbol:   Upper-cased ticker symbol.
        position: Optional ``PortfolioItem`` with cost-basis and stop-loss data.

    Returns:
        ``PositionScore`` with all fields populated.

    Raises:
        Exception: Propagated so the caller can catch and return a
        zero-score fallback for this symbol.
    """
    from ..trading.engine.indicators import sma as ind_sma, rsi as ind_rsi, atr as ind_atr

    bars = await _fetch_bars_for_symbol(symbol)
    if not bars or len(bars) < 200:
        raise ValueError(f"Insufficient data for {symbol}: got {len(bars) if bars else 0} bars")

    # Extract price series
    closes = [b.close for b in bars]
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]

    current_price = closes[-1]
    last_idx = len(closes) - 1

    # Trend: 50-SMA vs 200-SMA relative to price
    sma_50 = ind_sma(closes, 50)
    sma_200 = ind_sma(closes, 200)
    trend = _compute_trend(closes, sma_50, sma_200, last_idx)

    # RSI (14-period)
    rsi_series = ind_rsi(closes, 14)
    rsi_val = rsi_series[last_idx] if rsi_series[last_idx] != 0 else 50.0

    # ATR (14-period) as % of current price
    atr_series = ind_atr(highs, lows, closes, 14)
    atr_val = atr_series[last_idx]
    volatility_pct = (atr_val / current_price * 100) if current_price > 0 else 0.0

    # Best signal from top 3 strategies
    signal_label, signal_strategy = _pick_best_signal(bars)

    # Composite score
    score = _compute_score(rsi_val, trend, volatility_pct, signal_label)

    # Human-readable suggestion
    suggestion = _generate_suggestion(trend, rsi_val, signal_label, volatility_pct)

    # --- Extended P&L fields (populated when position detail is supplied) ---
    cost_basis = unrealized_pnl = unrealized_pnl_pct = stop_loss_recommendation = None
    if position is not None:
        # Fetch a live price so unrealized P&L is accurate during market hours.
        # Daily bars return yesterday's close until the market day ends, which
        # makes intraday P&L stale.  Technical indicators above still use
        # closes[-1] from the OHLCV history — only P&L pricing is overridden.
        # Falls back to closes[-1] if the live fetch fails for any reason.
        import yfinance as yf  # noqa: PLC0415 — local import matches existing pattern
        pnl_price = current_price  # fallback: yesterday's close
        try:
            live = yf.Ticker(symbol).fast_info.last_price
            if live and live > 0:
                pnl_price = live
        except Exception:
            pass

        cost_basis = float(position.purchase_price * position.quantity)
        current_value = float(pnl_price * position.quantity)
        unrealized_pnl = current_value - cost_basis
        unrealized_pnl_pct = (unrealized_pnl / cost_basis * 100) if cost_basis else None
        if position.hard_stop_loss:
            if pnl_price < position.hard_stop_loss:
                stop_loss_recommendation = "TRIGGERED: Price below stop loss"
            elif pnl_price < position.hard_stop_loss * 1.05:
                stop_loss_recommendation = "WARNING: Within 5% of stop loss"
            else:
                stop_loss_recommendation = "OK"
        else:
            stop_loss_recommendation = "No stop loss set"

    return PositionScore(
        symbol=symbol,
        current_price=round(current_price, 4),
        trend=trend,
        rsi=round(rsi_val, 2),
        volatility=round(volatility_pct, 2),
        signal=signal_label,
        signal_strategy=signal_strategy,
        suggestion=suggestion,
        score=score,
        cost_basis=round(cost_basis, 2) if cost_basis is not None else None,
        unrealized_pnl=round(unrealized_pnl, 2) if unrealized_pnl is not None else None,
        unrealized_pnl_pct=round(unrealized_pnl_pct, 2) if unrealized_pnl_pct is not None else None,
        stop_loss_recommendation=stop_loss_recommendation,
    )


@router.post("/portfolio-score", response_model=PortfolioScoreResponse)
@limiter.limit("5/minute")
async def score_portfolio(
    body: PortfolioScoreRequest,
    request: Request,
    current_user=Depends(get_current_user),
):
    """Score a portfolio of up to 30 symbols with technical analysis.

    For each ticker, fetches daily OHLCV data and computes trend (50/200 SMA),
    RSI(14), ATR-based volatility, and the best signal from three core
    strategies (SMA crossover, RSI mean reversion, MACD crossover).  Returns
    a per-position score (1-100) with a human-readable suggestion, plus an
    aggregate portfolio score.

    Args:
        body: ``PortfolioScoreRequest`` containing the list of symbols.

    Returns:
        ``PortfolioScoreResponse`` with per-position analysis and overall score.

    Raises:
        HTTPException 400: If more than 30 symbols are provided.
    """
    if len(body.symbols) > 30:
        raise HTTPException(400, "Maximum 30 symbols per request.")
    if not body.symbols:
        raise HTTPException(400, "At least one symbol is required.")

    # Deduplicate and upper-case symbols
    seen = set()
    unique_symbols = []
    for s in body.symbols:
        upper = s.strip().upper()
        if upper and upper not in seen:
            seen.add(upper)
            unique_symbols.append(upper)

    # Build a ticker -> PortfolioItem map from the optional positions list
    positions_map: dict = {}
    if body.positions:
        for pos in body.positions:
            positions_map[pos.ticker.strip().upper()] = pos

    # Analyze all symbols in parallel
    async def _safe_analyze(sym: str) -> PositionScore:
        """Wrapper that returns a zero-score fallback on any failure.

        Args:
            sym: Upper-cased ticker symbol.

        Returns:
            ``PositionScore`` — real analysis on success, or a stub with
            score=0 and an error suggestion on failure.
        """
        try:
            return await _analyze_single_symbol(sym, position=positions_map.get(sym))
        except Exception as exc:
            logger.warning("Portfolio score: failed to analyze %s: %s", sym, exc)
            return PositionScore(
                symbol=sym,
                current_price=0.0,
                trend="neutral",
                rsi=0.0,
                volatility=0.0,
                signal="HOLD",
                signal_strategy="",
                suggestion="Unable to fetch data.",
                score=0,
            )

    positions = await asyncio.gather(*[_safe_analyze(sym) for sym in unique_symbols])
    positions = list(positions)

    # Overall score: average of all position scores (including zero-score failures)
    scored = [p.score for p in positions if p.score > 0]
    overall_score = round(sum(scored) / len(scored)) if scored else 0

    # Top suggestion: from the lowest-scored position (most urgent action)
    if positions:
        worst = min(positions, key=lambda p: p.score)
        top_suggestion = f"{worst.symbol}: {worst.suggestion}"
    else:
        top_suggestion = "No positions to analyze."

    return PortfolioScoreResponse(
        positions=positions,
        overall_score=max(0, min(100, overall_score)),
        top_suggestion=top_suggestion,
    )


# ─── PAPER TRADING ──────────────────────────────────────────────────────────


async def _enrich_paper_trade(pt, db: AsyncSession) -> dict:
    """Convert PaperTrade ORM to dict enriched with strategy_name/strategy_slug.

    Args:
        pt:  PaperTrade ORM object.
        db:  Active DB session.

    Returns:
        Dict suitable for PaperTradeOut serialisation.
    """
    data = {
        "paper_trade_id": pt.paper_trade_id,
        "user_id": pt.user_id,
        "strategy_id": pt.strategy_id,
        "strategy_name": None,
        "strategy_slug": None,
        "symbol": pt.symbol,
        "initial_capital": pt.initial_capital,
        "current_equity": pt.current_equity,
        "status": pt.status,
        "parameters_json": pt.parameters_json,
        "created_at": pt.created_at,
        "stopped_at": pt.stopped_at,
    }
    if pt.strategy_id:
        strat = (await db.execute(
            select(Strategy).where(Strategy.strategy_id == pt.strategy_id)
        )).scalar_one_or_none()
        if strat:
            defn = strat.definition_json or {}
            data["strategy_name"] = strat.name
            data["strategy_slug"] = defn.get("strategy_slug", "")
    return data


@router.post("/paper", response_model=PaperTradeOut, status_code=201)
async def start_paper_trade(
    body: PaperTradeCreate,
    request: Request,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start a new paper trading session.

    Creates a virtual portfolio that tracks a strategy's signals in
    real-time against live market data.

    Args:
        body: Paper trade configuration (strategy, symbol, capital).

    Returns:
        The newly created paper trade.
    """
    uid = current_user.user_id

    # Resolve strategy (same logic as queue_backtest)
    strategy_id = None
    if body.strategy_id:
        strategy_id = body.strategy_id
    elif body.strategy_slug:
        sys_strats = (await db.execute(
            select(Strategy).where(Strategy.is_system == True)
        )).scalars().all()
        for s in sys_strats:
            defn = s.definition_json or {}
            if defn.get("strategy_slug") == body.strategy_slug:
                strategy_id = s.strategy_id
                break
        if not strategy_id:
            # Check user strategies
            user_strats = (await db.execute(
                select(Strategy).where(Strategy.user_id == uid)
            )).scalars().all()
            for s in user_strats:
                defn = s.definition_json or {}
                if defn.get("strategy_slug") == body.strategy_slug:
                    strategy_id = s.strategy_id
                    break
    if not strategy_id:
        raise HTTPException(404, "Strategy not found")

    # Check active paper trade limit (max 5 per user)
    active_count = (await db.execute(
        select(func.count(PaperTrade.paper_trade_id)).where(
            PaperTrade.user_id == uid,
            PaperTrade.status == "active",
        )
    )).scalar() or 0
    if active_count >= 5:
        raise HTTPException(429, "Maximum 5 active paper trades. Stop one before starting another.")

    pt = PaperTrade(
        paper_trade_id=uuid.uuid4(),
        user_id=uid,
        strategy_id=strategy_id,
        symbol=body.symbol.upper(),
        initial_capital=body.initial_capital,
        current_equity=body.initial_capital,
        status="active",
        parameters_json=body.parameters,
    )
    db.add(pt)

    # Add initial equity snapshot
    db.add(PaperTradeEquitySnapshot(
        snapshot_id=uuid.uuid4(),
        paper_trade_id=pt.paper_trade_id,
        equity=body.initial_capital,
    ))

    await db.commit()
    await db.refresh(pt)

    # Kick-start the paper worker evaluation loop so it picks up this trade.
    try:
        from arq.connections import create_pool, RedisSettings
        _redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        pool = await create_pool(RedisSettings.from_dsn(_redis_url))
        await pool.enqueue_job("evaluate_paper_trades", _defer_by=5, _queue_name="arq:paper")
        await pool.close()
    except Exception:
        pass  # Worker startup hook will eventually pick it up

    return await _enrich_paper_trade(pt, db)


@router.get("/paper", response_model=List[PaperTradeOut])
async def list_paper_trades(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all paper trades for the current user."""
    result = await db.execute(
        select(PaperTrade)
        .where(PaperTrade.user_id == current_user.user_id)
        .order_by(PaperTrade.created_at.desc())
    )
    trades = result.scalars().all()
    return [await _enrich_paper_trade(t, db) for t in trades]


@router.get("/paper/{paper_trade_id}", response_model=PaperTradeOut)
async def get_paper_trade(
    paper_trade_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific paper trade by ID."""
    pt = (await db.execute(
        select(PaperTrade).where(
            PaperTrade.paper_trade_id == paper_trade_id,
            PaperTrade.user_id == current_user.user_id,
        )
    )).scalar_one_or_none()
    if not pt:
        raise HTTPException(404, "Paper trade not found")
    return await _enrich_paper_trade(pt, db)


@router.post("/paper/{paper_trade_id}/pause", response_model=PaperTradeOut)
async def pause_paper_trade(
    paper_trade_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Pause an active paper trade (stops signal evaluation)."""
    pt = (await db.execute(
        select(PaperTrade).where(
            PaperTrade.paper_trade_id == paper_trade_id,
            PaperTrade.user_id == current_user.user_id,
        )
    )).scalar_one_or_none()
    if not pt:
        raise HTTPException(404, "Paper trade not found")
    if pt.status != "active":
        raise HTTPException(400, f"Cannot pause paper trade with status '{pt.status}'")
    pt.status = "paused"
    await db.commit()
    await db.refresh(pt)
    return await _enrich_paper_trade(pt, db)


@router.post("/paper/{paper_trade_id}/resume", response_model=PaperTradeOut)
async def resume_paper_trade(
    paper_trade_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Resume a paused paper trade."""
    pt = (await db.execute(
        select(PaperTrade).where(
            PaperTrade.paper_trade_id == paper_trade_id,
            PaperTrade.user_id == current_user.user_id,
        )
    )).scalar_one_or_none()
    if not pt:
        raise HTTPException(404, "Paper trade not found")
    if pt.status != "paused":
        raise HTTPException(400, f"Cannot resume paper trade with status '{pt.status}'")
    pt.status = "active"
    await db.commit()
    await db.refresh(pt)
    return await _enrich_paper_trade(pt, db)


@router.post("/paper/{paper_trade_id}/stop", response_model=PaperTradeOut)
async def stop_paper_trade(
    paper_trade_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stop a paper trade permanently and close all open positions."""
    pt = (await db.execute(
        select(PaperTrade).where(
            PaperTrade.paper_trade_id == paper_trade_id,
            PaperTrade.user_id == current_user.user_id,
        )
    )).scalar_one_or_none()
    if not pt:
        raise HTTPException(404, "Paper trade not found")
    if pt.status == "stopped":
        raise HTTPException(400, "Paper trade already stopped")

    # Close all open positions at current equity (no price fetch needed for stopping)
    open_positions = (await db.execute(
        select(PaperTradePosition).where(
            PaperTradePosition.paper_trade_id == paper_trade_id,
            PaperTradePosition.status == "open",
        )
    )).scalars().all()
    for pos in open_positions:
        pos.status = "closed"
        pos.exit_date = datetime.utcnow()
        # P&L will be approximate — positions were being tracked by the worker

    pt.status = "stopped"
    pt.stopped_at = datetime.utcnow()
    await db.commit()
    await db.refresh(pt)
    return await _enrich_paper_trade(pt, db)


@router.delete("/paper/{paper_trade_id}", status_code=204)
async def delete_paper_trade(
    paper_trade_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a stopped paper trade and its cascade-linked data.

    Only trades with status "stopped" may be deleted.  FK ondelete=CASCADE
    on paper_trade_positions and paper_trade_equity_snapshots handles
    child-row cleanup automatically.

    Args:
        paper_trade_id: UUID of the paper trade to delete.

    Returns:
        204 No Content on success.
    """
    pt = (await db.execute(
        select(PaperTrade).where(
            PaperTrade.paper_trade_id == paper_trade_id,
            PaperTrade.user_id == current_user.user_id,
        )
    )).scalar_one_or_none()
    if not pt:
        raise HTTPException(404, "Paper trade not found")
    if pt.status != "stopped":
        raise HTTPException(400, "Only stopped paper trades can be deleted")

    await db.delete(pt)
    await db.commit()
    return Response(status_code=204)


@router.patch("/paper/{paper_trade_id}", response_model=PaperTradeOut)
async def update_paper_trade(
    paper_trade_id: uuid.UUID,
    body: PaperTradeUpdate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Edit an active or paused paper trade's capital and parameters.

    When initial_capital is changed, current_equity is reset to the new
    value so the P&L calculation starts fresh from the updated baseline.

    Args:
        paper_trade_id: UUID of the paper trade to update.
        body: PaperTradeUpdate with optional initial_capital and parameters.

    Returns:
        The updated paper trade enriched with strategy metadata.
    """
    pt = (await db.execute(
        select(PaperTrade).where(
            PaperTrade.paper_trade_id == paper_trade_id,
            PaperTrade.user_id == current_user.user_id,
        )
    )).scalar_one_or_none()
    if not pt:
        raise HTTPException(404, "Paper trade not found")
    if pt.status not in ("active", "paused"):
        raise HTTPException(400, f"Cannot edit paper trade with status '{pt.status}'")

    # Apply initial_capital change — also reset current_equity to match
    if body.initial_capital is not None:
        pt.initial_capital = body.initial_capital
        pt.current_equity = body.initial_capital

    # Apply parameters change
    if body.parameters is not None:
        pt.parameters_json = body.parameters

    await db.commit()
    await db.refresh(pt)
    return await _enrich_paper_trade(pt, db)


@router.get("/paper/{paper_trade_id}/equity", response_model=List[PaperTradeEquitySnapshotOut])
async def get_paper_equity(
    paper_trade_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get equity time series for a paper trade (for charting)."""
    # Verify ownership
    pt = (await db.execute(
        select(PaperTrade).where(
            PaperTrade.paper_trade_id == paper_trade_id,
            PaperTrade.user_id == current_user.user_id,
        )
    )).scalar_one_or_none()
    if not pt:
        raise HTTPException(404, "Paper trade not found")

    result = await db.execute(
        select(PaperTradeEquitySnapshot)
        .where(PaperTradeEquitySnapshot.paper_trade_id == paper_trade_id)
        .order_by(PaperTradeEquitySnapshot.timestamp)
    )
    return result.scalars().all()


@router.get("/paper/{paper_trade_id}/positions", response_model=List[PaperTradePositionOut])
async def get_paper_positions(
    paper_trade_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get position history for a paper trade."""
    # Verify ownership
    pt = (await db.execute(
        select(PaperTrade).where(
            PaperTrade.paper_trade_id == paper_trade_id,
            PaperTrade.user_id == current_user.user_id,
        )
    )).scalar_one_or_none()
    if not pt:
        raise HTTPException(404, "Paper trade not found")

    result = await db.execute(
        select(PaperTradePosition)
        .where(PaperTradePosition.paper_trade_id == paper_trade_id)
        .order_by(PaperTradePosition.entry_date.desc())
    )
    return result.scalars().all()


# ---------------------------------------------------------------------------
# Paper trade SSE stream — real-time updates via Server-Sent Events
# ---------------------------------------------------------------------------


@router.get("/paper/{paper_trade_id}/stream")
async def stream_paper_trade(
    paper_trade_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stream real-time paper trade updates via Server-Sent Events.

    Polls the database every 5 seconds and emits the trade's current status,
    equity, and latest positions as SSE ``data:`` frames.  The stream
    terminates automatically when the trade reaches ``stopped`` or ``error``
    status.

    Args:
        paper_trade_id: UUID of the paper trade to stream.
        current_user:   Authenticated user (injected via Depends).
        db:             Async DB session (injected via Depends).

    Returns:
        StreamingResponse with ``media_type="text/event-stream"``.

    Raises:
        HTTPException 404: Paper trade not found or not owned by the user.
    """
    # Verify ownership before opening the stream
    pt = (await db.execute(
        select(PaperTrade).where(
            PaperTrade.paper_trade_id == paper_trade_id,
            PaperTrade.user_id == current_user.user_id,
        )
    )).scalar_one_or_none()
    if not pt:
        raise HTTPException(404, "Paper trade not found")

    async def _event_generator():
        """Yield SSE events with trade state until the trade terminates.

        Each event is a JSON payload containing:
            - paper_trade_id (str)
            - status (str): "active", "stopped", or "error"
            - current_equity (float)
            - positions (list[dict]): latest open/closed positions
            - timestamp (str): ISO-8601 UTC timestamp of this snapshot

        Yields:
            str: SSE-formatted ``data: {json}\n\n`` frames.
        """
        while True:
            # Refresh the trade object to get the latest DB state
            trade_result = await db.execute(
                select(PaperTrade).where(
                    PaperTrade.paper_trade_id == paper_trade_id,
                    PaperTrade.user_id == current_user.user_id,
                )
            )
            trade = trade_result.scalar_one_or_none()
            if not trade:
                # Trade deleted while streaming — send final event and stop
                payload = json.dumps({
                    "paper_trade_id": str(paper_trade_id),
                    "status": "error",
                    "message": "Paper trade no longer exists",
                })
                yield f"data: {payload}\n\n"
                return

            # Fetch latest positions for this trade
            pos_result = await db.execute(
                select(PaperTradePosition)
                .where(PaperTradePosition.paper_trade_id == paper_trade_id)
                .order_by(PaperTradePosition.entry_date.desc())
            )
            positions = pos_result.scalars().all()

            # Serialise positions into plain dicts
            positions_data = [
                {
                    "position_id": str(p.position_id),
                    "side": p.side,
                    "entry_price": float(p.entry_price),
                    "entry_date": p.entry_date.isoformat() if p.entry_date else None,
                    "exit_price": float(p.exit_price) if p.exit_price else None,
                    "exit_date": p.exit_date.isoformat() if p.exit_date else None,
                    "quantity": float(p.quantity),
                    "pnl": float(p.pnl) if p.pnl else None,
                    "status": p.status,
                }
                for p in positions
            ]

            # Build and emit the SSE event
            payload = json.dumps({
                "paper_trade_id": str(trade.paper_trade_id),
                "status": trade.status,
                "current_equity": float(trade.current_equity),
                "symbol": trade.symbol,
                "initial_capital": float(trade.initial_capital),
                "positions": positions_data,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            })
            yield f"data: {payload}\n\n"

            # Stop streaming when the trade has reached a terminal state
            if trade.status in ("stopped", "error"):
                return

            # Poll interval — wait 5 seconds before the next DB check
            await asyncio.sleep(5)

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering for SSE
        },
    )


# ── Exit Analysis ────────────────────────────────────────────────────────────

# In-memory cache for exit analysis results (10-minute TTL).
_exit_analysis_cache: Dict[str, Tuple[float, dict]] = {}
_EXIT_ANALYSIS_TTL = 600  # seconds (10 minutes)


def _get_exit_cached(key: str) -> Optional[dict]:
    """Return cached exit analysis result if still valid, else None.

    Args:
        key: Cache key string (symbol + period).

    Returns:
        Cached response dict, or None if expired / absent.
    """
    entry = _exit_analysis_cache.get(key)
    if entry and (time.time() - entry[0]) < _EXIT_ANALYSIS_TTL:
        return entry[1]
    return None


def _set_exit_cached(key: str, value: dict) -> None:
    """Store an exit analysis result in the in-memory cache.

    Args:
        key:   Cache key string.
        value: Serialisable response dict to cache.
    """
    _exit_analysis_cache[key] = (time.time(), value)


def _compute_exit_analysis(symbol: str, period_days: int) -> dict:
    """Run the full exit-point analysis for *symbol* (blocking / CPU-bound).

    Fetches OHLCV data via yfinance and computes ATR stops, Bollinger
    levels, moving-average support/resistance, 52-week extremes, and
    Fibonacci retracements.  This is a synchronous function intended to
    be called via ``asyncio.to_thread``.

    Args:
        symbol:      Upper-cased ticker symbol (e.g. "AAPL").
        period_days: Historical lookback window in calendar days.

    Returns:
        Dict matching the ExitAnalysisResponse schema.

    Raises:
        ValueError:  If yfinance returns no data or insufficient bars.
    """
    import yfinance as yf

    # ── 1. Fetch OHLCV data ────────────────────────────────────────────
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period=f"{period_days}d")
    if hist.empty or len(hist) < 60:
        raise ValueError(
            f"Insufficient price data for {symbol} "
            f"({len(hist) if not hist.empty else 0} bars, need 60+)."
        )

    # Extract plain lists for the indicator functions
    closes: List[float] = hist["Close"].tolist()
    highs_list: List[float] = hist["High"].tolist()
    lows_list: List[float] = hist["Low"].tolist()

    current_price = closes[-1]

    # ── 2. Calculate indicators ────────────────────────────────────────
    atr_series = atr(highs_list, lows_list, closes, 14)
    rsi_series = rsi(closes, 14)
    sma50_series = sma(closes, 50)
    sma200_series = sma(closes, 200)
    bb_mid, bb_upper, bb_lower, _bw = bollinger_bands(closes, 20, 2.0)
    ema21_series = ema(closes, 21)
    high52_series = highest(highs_list, 52)
    low52_series = lowest(lows_list, 52)

    # Current (last valid) values
    atr_val = atr_series[-1] if atr_series[-1] > 0 else atr_series[-2]
    rsi_val = rsi_series[-1] if rsi_series[-1] > 0 else rsi_series[-2]
    sma50_val = sma50_series[-1]
    sma200_val = sma200_series[-1]
    bb_upper_val = bb_upper[-1]
    bb_lower_val = bb_lower[-1]
    ema21_val = ema21_series[-1]
    high52_val = high52_series[-1]
    low52_val = low52_series[-1]

    atr_pct = (atr_val / current_price * 100) if current_price > 0 else 0.0

    # ── 3. Determine trend ─────────────────────────────────────────────
    if sma50_val > sma200_val and current_price > sma50_val:
        trend = "bullish"
    elif sma50_val < sma200_val and current_price < sma50_val:
        trend = "bearish"
    else:
        trend = "neutral"

    # ── 4. Build exit levels ───────────────────────────────────────────
    levels: List[dict] = []

    # ATR-based stop losses
    levels.append({
        "level_type": "stop_loss",
        "price": round(current_price - 1.5 * atr_val, 2),
        "label": "ATR Stop (1.5x)",
        "rationale": "Tight stop — 1.5x ATR below current price, suitable for low-volatility entries.",
    })
    levels.append({
        "level_type": "stop_loss",
        "price": round(current_price - 2.0 * atr_val, 2),
        "label": "ATR Stop (2x)",
        "rationale": "Standard stop — 2x ATR below current price, balances protection and noise tolerance.",
    })
    levels.append({
        "level_type": "stop_loss",
        "price": round(current_price - 3.0 * atr_val, 2),
        "label": "ATR Stop (3x)",
        "rationale": "Wide stop — 3x ATR below current price, allows for larger swings.",
    })

    # ATR-based take profit targets (risk = 2x ATR as standard risk unit)
    risk_unit = 2.0 * atr_val
    levels.append({
        "level_type": "take_profit",
        "price": round(current_price + risk_unit * 2, 2),
        "label": "Take Profit (1:2 R)",
        "rationale": "2x reward-to-risk target using 2-ATR risk unit.",
    })
    levels.append({
        "level_type": "take_profit",
        "price": round(current_price + risk_unit * 3, 2),
        "label": "Take Profit (1:3 R)",
        "rationale": "3x reward-to-risk target using 2-ATR risk unit.",
    })

    # Bollinger Bands
    levels.append({
        "level_type": "support",
        "price": round(bb_lower_val, 2),
        "label": "Bollinger Lower",
        "rationale": "Lower Bollinger Band (20, 2) — statistical support zone.",
    })
    levels.append({
        "level_type": "resistance",
        "price": round(bb_upper_val, 2),
        "label": "Bollinger Upper",
        "rationale": "Upper Bollinger Band (20, 2) — statistical resistance zone.",
    })

    # SMA 50 — support or resistance depending on price position
    if current_price > sma50_val:
        levels.append({
            "level_type": "support",
            "price": round(sma50_val, 2),
            "label": "SMA 50",
            "rationale": "50-day SMA acting as dynamic support (price is above).",
        })
    else:
        levels.append({
            "level_type": "resistance",
            "price": round(sma50_val, 2),
            "label": "SMA 50",
            "rationale": "50-day SMA acting as dynamic resistance (price is below).",
        })

    # SMA 200 — major support/resistance
    if current_price > sma200_val:
        levels.append({
            "level_type": "support",
            "price": round(sma200_val, 2),
            "label": "SMA 200",
            "rationale": "200-day SMA — major long-term support level.",
        })
    else:
        levels.append({
            "level_type": "resistance",
            "price": round(sma200_val, 2),
            "label": "SMA 200",
            "rationale": "200-day SMA — major long-term resistance level.",
        })

    # EMA 21 — short-term trailing stop reference
    if current_price > ema21_val:
        levels.append({
            "level_type": "support",
            "price": round(ema21_val, 2),
            "label": "EMA 21",
            "rationale": "21-day EMA — short-term trailing stop reference (price above).",
        })
    else:
        levels.append({
            "level_type": "resistance",
            "price": round(ema21_val, 2),
            "label": "EMA 21",
            "rationale": "21-day EMA — short-term resistance (price below).",
        })

    # 52-week high / low
    levels.append({
        "level_type": "resistance",
        "price": round(high52_val, 2),
        "label": "52w High",
        "rationale": "52-week rolling high — major psychological resistance.",
    })
    levels.append({
        "level_type": "support",
        "price": round(low52_val, 2),
        "label": "52w Low",
        "rationale": "52-week rolling low — major psychological support.",
    })

    # Fibonacci retracements from 52-week range
    fib_range = high52_val - low52_val
    if fib_range > 0:
        for pct, label in [
            (0.236, "23.6%"), (0.382, "38.2%"), (0.500, "50.0%"),
            (0.618, "61.8%"), (0.786, "78.6%"),
        ]:
            fib_price = round(high52_val - fib_range * pct, 2)
            levels.append({
                "level_type": "fibonacci",
                "price": fib_price,
                "label": f"Fib {label}",
                "rationale": f"Fibonacci {label} retracement of the 52-week range ({round(low52_val, 2)} – {round(high52_val, 2)}).",
            })

    # ── 5. Derive support / resistance zones ───────────────────────────
    # Support zone: highest support-type level that is still below price
    support_levels = [
        l["price"] for l in levels
        if l["level_type"] in ("support", "stop_loss", "fibonacci")
        and l["price"] < current_price
    ]
    support_zone = max(support_levels) if support_levels else None

    # Resistance zone: lowest resistance-type level that is above price
    resistance_levels = [
        l["price"] for l in levels
        if l["level_type"] in ("resistance", "take_profit", "fibonacci")
        and l["price"] > current_price
    ]
    resistance_zone = min(resistance_levels) if resistance_levels else None

    return {
        "symbol": symbol,
        "current_price": round(current_price, 2),
        "levels": levels,
        "atr_value": round(atr_val, 4),
        "atr_pct": round(atr_pct, 2),
        "trend": trend,
        "rsi": round(rsi_val, 2),
        "support_zone": round(support_zone, 2) if support_zone is not None else None,
        "resistance_zone": round(resistance_zone, 2) if resistance_zone is not None else None,
    }


@router.post("/exit-analysis", response_model=ExitAnalysisResponse)
async def exit_analysis(
    body: ExitAnalysisRequest,
    request: Request,
    current_user=Depends(get_current_user),
):
    """Compute comprehensive exit-point analysis for a symbol.

    Calculates ATR-based stops, Bollinger levels, moving-average
    support/resistance, 52-week extremes, and Fibonacci retracements.
    Results are cached for 10 minutes per symbol + period combination.

    Args:
        body:         Symbol and lookback period.
        request:      FastAPI request (for rate-limiter context).
        current_user: Authenticated user (injected via Depends).

    Returns:
        ExitAnalysisResponse with all computed levels, trend, and zones.
    """
    symbol = body.symbol.upper().strip()
    period_days = body.period_days

    # Check cache first
    cache_key = f"exit_analysis:{symbol}:{period_days}"
    cached = _get_exit_cached(cache_key)
    if cached:
        return cached

    # Run the blocking computation in a thread to avoid starving the event loop
    try:
        result = await asyncio.to_thread(_compute_exit_analysis, symbol, period_days)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Exit analysis failed for %s: %s", symbol, exc)
        raise HTTPException(status_code=502, detail=f"Failed to fetch market data for {symbol}.")

    _set_exit_cached(cache_key, result)
    return result
