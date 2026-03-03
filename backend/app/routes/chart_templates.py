"""
routes/chart_templates.py — Chart Template CRUD API endpoints.

Provides CRUD for user-owned chart templates (saved drawings + overlay
configuration).  All endpoints require authentication.  Ownership is
enforced by verifying template.user_id == current_user.user_id on every
operation.

Route prefix: /api/v1/chart-templates  (registered in main.py)
"""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import ChartTemplate
from ..schemas import (
    ChartTemplateCreate,
    ChartTemplateOut,
    ChartTemplateUpdate,
)
from .auth_routes import get_current_user

router = APIRouter(prefix="/chart-templates", tags=["chart-templates"])


# ── Helper ───────────────────────────────────────────────────────────────────

async def _get_template_or_404(
    template_id: UUID,
    db: AsyncSession,
    current_user,
) -> ChartTemplate:
    """Load a chart template and verify ownership; raise 404 if not found or not owned."""
    result = await db.execute(
        select(ChartTemplate).where(
            ChartTemplate.template_id == template_id,
            ChartTemplate.user_id == current_user.user_id,
        )
    )
    template = result.scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=404, detail="Chart template not found.")
    return template


# ── List all templates ────────────────────────────────────────────────────────

@router.get("/", response_model=List[ChartTemplateOut])
async def list_templates(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return all chart templates owned by the authenticated user."""
    result = await db.execute(
        select(ChartTemplate)
        .where(ChartTemplate.user_id == current_user.user_id)
        .order_by(ChartTemplate.updated_at.desc())
    )
    return result.scalars().all()


# ── Create template ──────────────────────────────────────────────────────────

@router.post("/", response_model=ChartTemplateOut, status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: ChartTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Create a new chart template for the authenticated user."""
    template = ChartTemplate(
        user_id=current_user.user_id,
        name=payload.name,
        symbol=payload.symbol,
        interval=payload.interval,
        drawings_json=payload.drawings_json,
        overlays_json=payload.overlays_json,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


# ── Get single template ──────────────────────────────────────────────────────

@router.get("/{template_id}", response_model=ChartTemplateOut)
async def get_template(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return a single chart template by ID (ownership enforced)."""
    return await _get_template_or_404(template_id, db, current_user)


# ── Update template ─────────────────────────────────────────────────────────

@router.patch("/{template_id}", response_model=ChartTemplateOut)
async def update_template(
    template_id: UUID,
    payload: ChartTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Partially update a chart template (ownership enforced)."""
    template = await _get_template_or_404(template_id, db, current_user)

    if payload.name is not None:
        template.name = payload.name
    if payload.symbol is not None:
        template.symbol = payload.symbol
    if payload.interval is not None:
        template.interval = payload.interval
    if payload.drawings_json is not None:
        template.drawings_json = payload.drawings_json
    if payload.overlays_json is not None:
        template.overlays_json = payload.overlays_json

    await db.commit()
    await db.refresh(template)
    return template


# ── Delete template ──────────────────────────────────────────────────────────

@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Delete a chart template (ownership enforced)."""
    template = await _get_template_or_404(template_id, db, current_user)
    await db.delete(template)
    await db.commit()
