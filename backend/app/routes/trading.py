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

import hmac
import logging
import os
import uuid
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, update, delete, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import Strategy, StrategyVersion, BacktestResult, TradingSignal, AuditLog, Notification, UserWebhook, User
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
@limiter.limit("30/minute")
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
@limiter.limit("30/minute")
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
@limiter.limit("30/minute")
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
@limiter.limit("30/minute")
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
    await db.commit()
    await db.refresh(clone)
    return clone


# ── PineScript routes ────────────────────────────────────────────────


@router.post("/pinescript/validate", response_model=PineScriptValidateResponse)
@limiter.limit("60/minute")
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
@limiter.limit("20/minute")
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
@limiter.limit("20/minute")
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
@limiter.limit("10/hour")
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
    # Check concurrent limit (3 per user)
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
@limiter.limit("30/minute")
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
