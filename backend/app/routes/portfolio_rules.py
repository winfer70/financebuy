"""
portfolio_rules.py — Portfolio rules engine API routes.

Endpoints for triggering the rules engine, viewing alerts, and managing config.
All endpoints require authentication. Portfolio ownership is verified before
any operation that touches portfolio-specific data.

Route prefix: /api/v1/portfolio-manager  (mounted in main.py)

Endpoints:
    POST /portfolios/{portfolio_id}/run-rules   — enqueue rules engine job
    GET  /portfolios/{portfolio_id}/rule-alerts  — list alerts for a portfolio
    PATCH /rule-alerts/{alert_id}               — snooze / action an alert
    GET  /rule-config                           — read user rule thresholds
    PATCH /rule-config                          — update user rule thresholds
"""

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from ..db import get_db
from ..models import Portfolio, RuleAlert, User
from ..schemas import (
    PortfolioRulesConfig,
    PortfolioRulesRunRequest,
    PortfolioRulesRunResponse,
    RuleAlertPatch,
    RuleAlertResponse,
)
from ..trading.worker import enqueue_portfolio_rules
from .auth_routes import get_current_user

router = APIRouter(prefix="/portfolio-manager", tags=["portfolio-rules"])


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _verify_portfolio_ownership(
    portfolio_id: UUID,
    db: AsyncSession,
    current_user,
) -> Portfolio:
    """Load portfolio and verify it belongs to the authenticated user.

    Args:
        portfolio_id:  UUID of the portfolio to check.
        db:            Async DB session.
        current_user:  Authenticated User ORM object.

    Returns:
        Portfolio ORM object.

    Raises:
        HTTPException 404 if not found or not owned by the user.
    """
    result = await db.execute(
        select(Portfolio).where(
            Portfolio.portfolio_id == portfolio_id,
            Portfolio.user_id == current_user.user_id,
        )
    )
    portfolio = result.scalar_one_or_none()
    if portfolio is None:
        raise HTTPException(status_code=404, detail="Portfolio not found.")
    return portfolio


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post(
    "/portfolios/{portfolio_id}/run-rules",
    response_model=PortfolioRulesRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_portfolio_rules(
    portfolio_id: UUID,
    payload: PortfolioRulesRunRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Enqueue a portfolio rules engine run for the specified portfolio.

    Verifies ownership, then dispatches the arq job to the trading worker.
    Returns 202 Accepted immediately; the caller should poll rule-alerts to
    see results once the job completes.

    Args:
        portfolio_id:  UUID of the portfolio to evaluate.
        payload:       PortfolioRulesRunRequest with optional schedule hint.
        db:            Async DB session (injected).
        current_user:  Authenticated user (injected).

    Returns:
        PortfolioRulesRunResponse with arq job_id and status.

    Raises:
        HTTPException 404: Portfolio not found or not owned by user.
    """
    await _verify_portfolio_ownership(portfolio_id, db, current_user)

    schedule = payload.schedule or "on_demand"
    job_id = await enqueue_portfolio_rules(
        str(portfolio_id),
        str(current_user.user_id),
        schedule,
    )

    return PortfolioRulesRunResponse(
        job_id=job_id if job_id else "enqueue_failed",
        status="queued" if job_id else "already_running",
    )


@router.get(
    "/portfolios/{portfolio_id}/rule-alerts",
    response_model=List[RuleAlertResponse],
)
async def list_rule_alerts(
    portfolio_id: UUID,
    severity: Optional[str] = Query(None, description="Filter by severity: info | warning | critical"),
    state: Optional[str] = Query("active", description="Filter by state: active | snoozed | actioned | expired"),
    rule_type: Optional[str] = Query(None, description="Filter by rule type slug (e.g. house_money)"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return rule alerts for the authenticated user filtered by optional criteria.

    Always scopes results to the current user. The portfolio_id parameter is
    used to verify ownership; alerts are stored at the user level.

    Args:
        portfolio_id:  UUID of the portfolio (ownership check only).
        severity:      Optional filter — info | warning | critical.
        state:         Optional filter — defaults to 'active'.
        rule_type:     Optional filter by rule slug.
        db:            Async DB session (injected).
        current_user:  Authenticated user (injected).

    Returns:
        List of RuleAlertResponse objects sorted by created_at descending.

    Raises:
        HTTPException 404: Portfolio not found or not owned by user.
    """
    await _verify_portfolio_ownership(portfolio_id, db, current_user)

    stmt = select(RuleAlert).where(RuleAlert.user_id == current_user.user_id)

    if state:
        stmt = stmt.where(RuleAlert.state == state)
    if severity:
        stmt = stmt.where(RuleAlert.severity == severity)
    if rule_type:
        stmt = stmt.where(RuleAlert.rule_type == rule_type)

    stmt = stmt.order_by(RuleAlert.created_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()


@router.patch(
    "/rule-alerts/{alert_id}",
    response_model=RuleAlertResponse,
)
async def patch_rule_alert(
    alert_id: int,
    payload: RuleAlertPatch,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Snooze or action a rule alert.

    Ownership is enforced by filtering on user_id.

    Args:
        alert_id:     Integer PK of the RuleAlert row.
        payload:      RuleAlertPatch with new state and optional snoozed_until.
        db:           Async DB session (injected).
        current_user: Authenticated user (injected).

    Returns:
        Updated RuleAlertResponse.

    Raises:
        HTTPException 404: Alert not found or not owned by user.
    """
    result = await db.execute(
        select(RuleAlert).where(
            RuleAlert.id == alert_id,
            RuleAlert.user_id == current_user.user_id,
        )
    )
    alert = result.scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found.")

    if payload.state is not None:
        alert.state = payload.state
    if payload.snoozed_until is not None:
        alert.snoozed_until = payload.snoozed_until

    await db.commit()
    await db.refresh(alert)
    return alert


@router.get(
    "/rule-config",
    response_model=PortfolioRulesConfig,
)
async def get_rule_config(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return the authenticated user's portfolio rules configuration.

    Reads from users.preferences["portfolio_rules"]. Returns default values
    if no custom config has been saved.

    Args:
        db:           Async DB session (injected).
        current_user: Authenticated user (injected).

    Returns:
        PortfolioRulesConfig with current or default thresholds.
    """
    result = await db.execute(
        select(User).where(User.user_id == current_user.user_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        return PortfolioRulesConfig()

    prefs = user.preferences or {}
    rules_raw = prefs.get("portfolio_rules", {})
    try:
        return PortfolioRulesConfig(**rules_raw)
    except Exception:
        return PortfolioRulesConfig()


@router.patch(
    "/rule-config",
    response_model=PortfolioRulesConfig,
)
async def update_rule_config(
    payload: Dict[str, Any] = Body(..., description="Partial rule config overrides. Keys must match PortfolioRulesConfig fields."),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Partially update the authenticated user's portfolio rules configuration.

    Only keys present in PortfolioRulesConfig are applied; unknown keys are
    silently ignored.  Values are merged into the existing config rather than
    replacing it wholesale.

    Args:
        payload:      Dict of field overrides (e.g. {"stop_proximity_pct": 0.05}).
        db:           Async DB session (injected).
        current_user: Authenticated user (injected).

    Returns:
        Full updated PortfolioRulesConfig after applying the patch.

    Raises:
        HTTPException 404: User record not found.
    """
    result = await db.execute(
        select(User).where(User.user_id == current_user.user_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    # Clone prefs dict so SQLAlchemy detects the mutation via reassignment
    prefs: dict = dict(user.preferences or {})
    current_rules: dict = dict(prefs.get("portfolio_rules", {}))

    # Apply only valid PortfolioRulesConfig field keys
    valid_fields = set(PortfolioRulesConfig.__fields__.keys())
    for key, value in payload.items():
        if key in valid_fields:
            current_rules[key] = value

    prefs["portfolio_rules"] = current_rules

    # Reassign to trigger SQLAlchemy change detection on the JSONB column
    user.preferences = prefs
    flag_modified(user, "preferences")

    await db.commit()

    try:
        return PortfolioRulesConfig(**current_rules)
    except Exception:
        return PortfolioRulesConfig()
