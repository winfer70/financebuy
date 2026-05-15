"""
routes/scanner.py — Volume Flow Scanner endpoints.

Exposes three routes under /api/v1/scanner/:
  POST /run            — Queue a new scan job (arq background task).
  GET  /latest         — Fetch the most recent scan for the current user.
  GET  /{result_id}    — Fetch a specific scan result.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import ScanResult
from app.routes.auth_routes import get_current_user
from app.schemas import ScanResultOut, ScanRunRequest

router = APIRouter(prefix="/scanner", tags=["scanner"])


@router.post("/run", response_model=ScanResultOut, status_code=201)
async def run_scanner_endpoint(
    body: ScanRunRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Start a Volume Flow Scan in the background.

    Creates a pending ScanResult row, enqueues the arq job, and returns
    immediately so the client can poll for completion.

    Args:
        body:         ScanRunRequest with portfolio_value_usd.
        db:           Async DB session.
        current_user: Authenticated user from JWT.

    Returns:
        ScanResultOut with status=pending and a result_id for polling.
    """
    scan = ScanResult(
        user_id=current_user.user_id,
        status="pending",
        parameters_json={
            "portfolio_value_usd": float(body.portfolio_value_usd),
            "mode": body.mode,
        },
        created_at=datetime.utcnow(),
    )
    async with db.begin():
        db.add(scan)

    # Enqueue the background job — if Redis is unavailable, scan stays pending
    try:
        from app.trading.scanner_worker import enqueue_scanner
        await enqueue_scanner(str(scan.result_id))
    except Exception:
        pass  # Job will remain pending; worker retry will pick it up

    return scan


@router.get("/latest", response_model=ScanResultOut)
async def get_latest_scan(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return the most recent scan result for the current user.

    Args:
        db:           Async DB session.
        current_user: Authenticated user from JWT.

    Returns:
        Most recent ScanResultOut, or 404 if no scans exist.
    """
    result = await db.execute(
        select(ScanResult)
        .where(ScanResult.user_id == current_user.user_id)
        .order_by(ScanResult.created_at.desc())
        .limit(1)
    )
    scan = result.scalar_one_or_none()
    if not scan:
        raise HTTPException(status_code=404, detail="No scan results found.")
    return scan


@router.get("/{result_id}", response_model=ScanResultOut)
async def get_scan_result(
    result_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return a specific scan result by ID.

    Args:
        result_id:    UUID string of the scan result.
        db:           Async DB session.
        current_user: Authenticated user from JWT.

    Returns:
        ScanResultOut if found and owned by current user, else 404.
    """
    try:
        rid = uuid.UUID(result_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid result_id format.")

    result = await db.execute(
        select(ScanResult).where(
            ScanResult.result_id == rid,
            ScanResult.user_id == current_user.user_id,
        )
    )
    scan = result.scalar_one_or_none()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan result not found.")
    return scan
