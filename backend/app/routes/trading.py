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
import uuid
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
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
    PaperTradeCreate, PaperTradeOut, PaperTradePositionOut,
    PaperTradeEquitySnapshotOut,
)
from ..limiter import limiter
from .auth_routes import get_current_user

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
# TEMP: rate limits disabled for testing
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
# TEMP: rate limits disabled for testing
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
# TEMP: rate limits disabled for testing
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
# TEMP: rate limits disabled for testing
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
# TEMP: rate limits disabled for testing
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
# TEMP: rate limits disabled for testing
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
# TEMP: rate limits disabled for testing
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
# TEMP: rate limits disabled for testing
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
# TEMP: rate limits disabled for testing
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
    # TEMP: concurrent limit disabled for testing (was 3 per user)
    # stmt = select(BacktestResult).where(
    #     BacktestResult.user_id == current_user.user_id,
    #     BacktestResult.status.in_(["pending", "running"]),
    # )
    # result = await db.execute(stmt)
    # active = result.scalars().all()
    # if len(active) >= 3:
    #     raise HTTPException(429, "Maximum 3 concurrent backtests. Wait for one to finish.")

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
# TEMP: rate limits disabled for testing
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
    if not body.url.startswith("https://"):
        raise HTTPException(400, "Webhook URL must use HTTPS.")

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
    if "url" in updates and not updates["url"].startswith("https://"):
        raise HTTPException(400, "Webhook URL must use HTTPS.")

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
# TEMP: rate limits disabled for testing
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
# TEMP: rate limits disabled for testing
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
# TEMP: rate limits disabled for testing
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
# TEMP: rate limits disabled for testing
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
# TEMP: rate limits disabled for testing
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
# TEMP: rate limits disabled for testing
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
# TEMP: rate limits disabled for testing
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
# TEMP: rate limits disabled for testing
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
# TEMP: rate limits disabled for testing
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
        await pool.enqueue_job("evaluate_paper_trades", _defer_by=5)
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
