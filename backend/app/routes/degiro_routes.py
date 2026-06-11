"""degiro_routes.py — Manual trigger and status for DeGiro portfolio sync."""

import os

import structlog
from arq.connections import RedisSettings, create_pool
from fastapi import APIRouter, Depends

from ..models import User
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
    return {"configured": configured, "totp_configured": has_totp}
