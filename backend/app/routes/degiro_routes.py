"""degiro_routes.py — Manual trigger, status, and data access for DeGiro sync."""

import os
import uuid

import structlog
from arq.connections import RedisSettings, create_pool
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import DegiroTransaction, User
from .auth_routes import get_current_user

logger = structlog.get_logger("degiro_routes")

_REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

router = APIRouter(prefix="/degiro", tags=["degiro"])


@router.post("/sync")
async def trigger_degiro_sync(current_user: User = Depends(get_current_user)):
    """Enqueue an immediate DeGiro portfolio sync job."""
    pool = await create_pool(RedisSettings.from_dsn(_REDIS_URL))
    job = await pool.enqueue_job("sync_degiro_portfolio", _queue_name="arq:alert")
    await pool.close()
    return {"job_id": job.job_id, "status": "queued"}


@router.get("/sync/status")
async def degiro_sync_status(current_user: User = Depends(get_current_user)):
    """Return whether DeGiro sync env vars are configured."""
    configured = bool(
        os.getenv("DEGIRO_USERNAME")
        and os.getenv("DEGIRO_PASSWORD")
        and os.getenv("DEGIRO_PORTFOLIO_ID")
    )
    has_totp = bool(os.getenv("DEGIRO_TOTP_SECRET"))
    cleanup_enabled = os.getenv("DEGIRO_CLEANUP_MANUAL_POSITIONS", "").lower() == "true"
    return {
        "configured": configured,
        "totp_configured": has_totp,
        "cleanup_manual_positions": cleanup_enabled,
    }


@router.get("/transactions")
async def list_degiro_transactions(
    portfolio_id: uuid.UUID = Query(...),
    limit: int = Query(200, le=1000),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List DeGiro transaction history for a portfolio, newest first."""
    result = await db.execute(
        select(DegiroTransaction)
        .where(DegiroTransaction.portfolio_id == portfolio_id)
        .order_by(DegiroTransaction.date.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = result.scalars().all()
    return [
        {
            "transaction_id": r.transaction_id,
            "date": r.date.isoformat(),
            "product_name": r.product_name,
            "isin": r.isin,
            "ticker": r.ticker,
            "buysell": r.buysell,
            "quantity": str(r.quantity) if r.quantity is not None else None,
            "price": str(r.price) if r.price is not None else None,
            "value": str(r.value) if r.value is not None else None,
            "currency": r.currency,
            "total_in_base": str(r.total_in_base) if r.total_in_base is not None else None,
            "fee_in_base": str(r.fee_in_base) if r.fee_in_base is not None else None,
        }
        for r in rows
    ]
