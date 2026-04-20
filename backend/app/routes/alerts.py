"""
alerts.py — Price alert CRUD endpoints.

Lets users create, list, update, and delete price alerts. Alerts are
evaluated by the alert-worker background service which triggers
notifications when conditions are met.
"""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import PriceAlert
from ..schemas import PriceAlertCreate, PriceAlertOut, PriceAlertUpdate
from .auth_routes import get_current_user

router = APIRouter(prefix="/alerts", tags=["alerts"])

MAX_ALERTS_PER_USER = 50


@router.post("", response_model=PriceAlertOut, status_code=201)
async def create_alert(
    body: PriceAlertCreate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new price alert for the current user.

    Args:
        body: PriceAlertCreate payload with symbol, condition, target_price, note.
        current_user: Authenticated user (injected via Depends).
        db: Async database session (injected via Depends).

    Returns:
        PriceAlertOut: The newly created alert.

    Raises:
        HTTPException 400: If the user already has MAX_ALERTS_PER_USER active alerts.
    """
    # Enforce per-user limit
    count_q = await db.execute(
        select(func.count(PriceAlert.alert_id)).where(
            PriceAlert.user_id == current_user.user_id,
            PriceAlert.is_active == True,  # noqa: E712
        )
    )
    if count_q.scalar() >= MAX_ALERTS_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {MAX_ALERTS_PER_USER} active alerts allowed",
        )

    alert = PriceAlert(
        user_id=current_user.user_id,
        symbol=body.symbol.upper().strip(),
        condition=body.condition,
        target_price=body.target_price,
        note=body.note,
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    return alert


@router.get("", response_model=List[PriceAlertOut])
async def list_alerts(
    active_only: bool = Query(False),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all price alerts for the current user.

    Args:
        active_only: If True, return only active (non-triggered) alerts.
        current_user: Authenticated user (injected via Depends).
        db: Async database session (injected via Depends).

    Returns:
        List[PriceAlertOut]: All matching alerts, newest first.
    """
    filters = [PriceAlert.user_id == current_user.user_id]
    if active_only:
        filters.append(PriceAlert.is_active == True)  # noqa: E712
    result = await db.execute(
        select(PriceAlert).where(*filters).order_by(PriceAlert.created_at.desc())
    )
    return result.scalars().all()


@router.patch("/{alert_id}", response_model=PriceAlertOut)
async def update_alert(
    alert_id: UUID,
    body: PriceAlertUpdate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing price alert.

    Args:
        alert_id: UUID of the alert to update.
        body: PriceAlertUpdate payload with optional fields.
        current_user: Authenticated user (injected via Depends).
        db: Async database session (injected via Depends).

    Returns:
        PriceAlertOut: The updated alert.

    Raises:
        HTTPException 404: If the alert is not found or does not belong to the user.
    """
    result = await db.execute(
        select(PriceAlert).where(
            PriceAlert.alert_id == alert_id,
            PriceAlert.user_id == current_user.user_id,
        )
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    updates = body.dict(exclude_unset=True)
    for key, val in updates.items():
        setattr(alert, key, val)
    await db.commit()
    await db.refresh(alert)
    return alert


@router.delete("/{alert_id}", status_code=204)
async def delete_alert(
    alert_id: UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a price alert.

    Args:
        alert_id: UUID of the alert to delete.
        current_user: Authenticated user (injected via Depends).
        db: Async database session (injected via Depends).

    Raises:
        HTTPException 404: If the alert is not found or does not belong to the user.
    """
    result = await db.execute(
        select(PriceAlert).where(
            PriceAlert.alert_id == alert_id,
            PriceAlert.user_id == current_user.user_id,
        )
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    await db.delete(alert)
    await db.commit()
