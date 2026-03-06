"""
routes/watchlists.py — Watchlist CRUD API endpoints.

Provides full CRUD for user-owned watchlists and their items, plus a
convenience endpoint to buy a watchlist item directly into a portfolio.
All endpoints require authentication.  Ownership is enforced by
verifying watchlist.user_id == current_user.user_id on every operation.

Route prefix: /api/v1/watchlists  (registered in main.py)
"""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func as sa_func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import Portfolio, PortfolioPosition, Watchlist, WatchlistItem
from ..schemas import (
    WatchlistBuyRequest,
    WatchlistCreate,
    WatchlistDetailOut,
    WatchlistItemCreate,
    WatchlistItemOut,
    WatchlistItemUpdate,
    WatchlistOut,
    WatchlistUpdate,
)
from .auth_routes import get_current_user

router = APIRouter(prefix="/watchlists", tags=["watchlists"])


# -- Helpers ------------------------------------------------------------------


async def _get_watchlist_or_404(
    watchlist_id: UUID,
    db: AsyncSession,
    current_user,
) -> Watchlist:
    """Load a watchlist and verify ownership.

    Args:
        watchlist_id: UUID of the watchlist to retrieve.
        db: Active async database session.
        current_user: Authenticated user object (injected via Depends).

    Returns:
        Watchlist: The verified watchlist ORM instance.

    Raises:
        HTTPException 404: If the watchlist does not exist or is not owned
            by the current user.
    """
    result = await db.execute(
        select(Watchlist).where(
            Watchlist.watchlist_id == watchlist_id,
            Watchlist.user_id == current_user.user_id,
        )
    )
    watchlist = result.scalar_one_or_none()
    if watchlist is None:
        raise HTTPException(status_code=404, detail="Watchlist not found.")
    return watchlist


async def _get_item_or_404(
    item_id: UUID,
    watchlist_id: UUID,
    db: AsyncSession,
    current_user,
) -> WatchlistItem:
    """Load a watchlist item and verify ownership via watchlist join.

    Args:
        item_id: UUID of the item to retrieve.
        watchlist_id: UUID of the parent watchlist (for scoping).
        db: Active async database session.
        current_user: Authenticated user object (injected via Depends).

    Returns:
        WatchlistItem: The verified item ORM instance.

    Raises:
        HTTPException 404: If the item does not exist, does not belong to
            the specified watchlist, or the watchlist is not owned by the
            current user.
    """
    result = await db.execute(
        select(WatchlistItem)
        .join(Watchlist, Watchlist.watchlist_id == WatchlistItem.watchlist_id)
        .where(
            WatchlistItem.item_id == item_id,
            WatchlistItem.watchlist_id == watchlist_id,
            Watchlist.user_id == current_user.user_id,
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Watchlist item not found.")
    return item


# -- Watchlist endpoints ------------------------------------------------------


@router.post("", response_model=WatchlistOut, status_code=status.HTTP_201_CREATED)
async def create_watchlist(
    payload: WatchlistCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Create a new watchlist for the authenticated user.

    Args:
        payload: WatchlistCreate schema containing the watchlist name.
        db: Async database session (injected).
        current_user: Authenticated user (injected).

    Returns:
        WatchlistOut: The newly created watchlist with item_count=0.
    """
    watchlist = Watchlist(
        user_id=current_user.user_id,
        name=payload.name,
    )
    db.add(watchlist)
    await db.commit()
    await db.refresh(watchlist)

    # Return with explicit item_count since the ORM model does not carry it
    return WatchlistOut(
        watchlist_id=watchlist.watchlist_id,
        name=watchlist.name,
        item_count=0,
        created_at=watchlist.created_at,
    )


@router.get("", response_model=List[WatchlistOut])
async def list_watchlists(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List all watchlists belonging to the authenticated user.

    Each watchlist includes an ``item_count`` computed via a correlated
    subquery.  Results are ordered by creation date descending (newest first).

    Args:
        db: Async database session (injected).
        current_user: Authenticated user (injected).

    Returns:
        List[WatchlistOut]: User's watchlists with item counts.
    """
    # Correlated subquery: count items per watchlist
    item_count_subq = (
        select(sa_func.count(WatchlistItem.item_id))
        .where(WatchlistItem.watchlist_id == Watchlist.watchlist_id)
        .correlate(Watchlist)
        .scalar_subquery()
        .label("item_count")
    )

    result = await db.execute(
        select(Watchlist, item_count_subq)
        .where(Watchlist.user_id == current_user.user_id)
        .order_by(Watchlist.created_at.desc())
    )

    rows = result.all()
    return [
        WatchlistOut(
            watchlist_id=wl.watchlist_id,
            name=wl.name,
            item_count=count,
            created_at=wl.created_at,
        )
        for wl, count in rows
    ]


@router.get("/{watchlist_id}", response_model=WatchlistDetailOut)
async def get_watchlist(
    watchlist_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get a single watchlist with its items.

    Items are ordered by ``position_order`` ascending so the user's custom
    ordering is preserved.

    Args:
        watchlist_id: UUID of the watchlist to retrieve.
        db: Async database session (injected).
        current_user: Authenticated user (injected).

    Returns:
        WatchlistDetailOut: The watchlist with nested items.

    Raises:
        HTTPException 404: If the watchlist is not found or not owned.
    """
    watchlist = await _get_watchlist_or_404(watchlist_id, db, current_user)

    items_result = await db.execute(
        select(WatchlistItem)
        .where(WatchlistItem.watchlist_id == watchlist_id)
        .order_by(WatchlistItem.position_order.asc())
    )
    items = items_result.scalars().all()

    return WatchlistDetailOut(
        watchlist_id=watchlist.watchlist_id,
        name=watchlist.name,
        items=[
            WatchlistItemOut(
                item_id=item.item_id,
                symbol=item.symbol,
                asset_type=item.asset_type,
                notes=item.notes,
                position_order=item.position_order,
                price_when_added=float(item.price_when_added) if item.price_when_added is not None else None,
                added_at=item.added_at,
            )
            for item in items
        ],
        created_at=watchlist.created_at,
    )


@router.patch("/{watchlist_id}", response_model=WatchlistOut)
async def rename_watchlist(
    watchlist_id: UUID,
    payload: WatchlistUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Rename an existing watchlist.

    Args:
        watchlist_id: UUID of the watchlist to rename.
        payload: WatchlistUpdate schema containing the new name.
        db: Async database session (injected).
        current_user: Authenticated user (injected).

    Returns:
        WatchlistOut: The updated watchlist with current item_count.

    Raises:
        HTTPException 404: If the watchlist is not found or not owned.
    """
    watchlist = await _get_watchlist_or_404(watchlist_id, db, current_user)
    watchlist.name = payload.name
    await db.commit()
    await db.refresh(watchlist)

    # Compute item count for the response
    count_result = await db.execute(
        select(sa_func.count(WatchlistItem.item_id))
        .where(WatchlistItem.watchlist_id == watchlist_id)
    )
    item_count = count_result.scalar() or 0

    return WatchlistOut(
        watchlist_id=watchlist.watchlist_id,
        name=watchlist.name,
        item_count=item_count,
        created_at=watchlist.created_at,
    )


@router.delete("/{watchlist_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_watchlist(
    watchlist_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Delete a watchlist and all its items (CASCADE).

    Args:
        watchlist_id: UUID of the watchlist to delete.
        db: Async database session (injected).
        current_user: Authenticated user (injected).

    Raises:
        HTTPException 404: If the watchlist is not found or not owned.
    """
    watchlist = await _get_watchlist_or_404(watchlist_id, db, current_user)
    await db.delete(watchlist)
    await db.commit()


# -- Watchlist item endpoints -------------------------------------------------


@router.post(
    "/{watchlist_id}/items",
    response_model=WatchlistItemOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_item(
    watchlist_id: UUID,
    payload: WatchlistItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Add an item (symbol) to a watchlist.

    The symbol is uppercased before storage.  A 409 Conflict is returned
    if the symbol already exists in this watchlist (enforced by the DB
    unique constraint as well).

    Args:
        watchlist_id: UUID of the parent watchlist.
        payload: WatchlistItemCreate schema with symbol, asset_type, notes,
            and optional price_when_added.
        db: Async database session (injected).
        current_user: Authenticated user (injected).

    Returns:
        WatchlistItemOut: The newly created watchlist item.

    Raises:
        HTTPException 404: If the watchlist is not found or not owned.
        HTTPException 409: If the symbol is already in this watchlist.
    """
    await _get_watchlist_or_404(watchlist_id, db, current_user)

    # Check for duplicate symbol within this watchlist
    upper_symbol = payload.symbol.upper()
    dup_check = await db.execute(
        select(WatchlistItem).where(
            WatchlistItem.watchlist_id == watchlist_id,
            WatchlistItem.symbol == upper_symbol,
        )
    )
    if dup_check.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Symbol '{upper_symbol}' is already in this watchlist.",
        )

    item = WatchlistItem(
        watchlist_id=watchlist_id,
        symbol=upper_symbol,
        asset_type=payload.asset_type,
        notes=payload.notes,
        price_when_added=payload.price_when_added,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.patch(
    "/{watchlist_id}/items/{item_id}",
    response_model=WatchlistItemOut,
)
async def update_item(
    watchlist_id: UUID,
    item_id: UUID,
    payload: WatchlistItemUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Update notes and/or position_order for a watchlist item.

    Only the fields present in the payload are updated; absent fields
    remain unchanged.

    Args:
        watchlist_id: UUID of the parent watchlist.
        item_id: UUID of the item to update.
        payload: WatchlistItemUpdate schema with optional notes and
            position_order fields.
        db: Async database session (injected).
        current_user: Authenticated user (injected).

    Returns:
        WatchlistItemOut: The updated watchlist item.

    Raises:
        HTTPException 404: If the item or watchlist is not found / not owned.
    """
    item = await _get_item_or_404(item_id, watchlist_id, db, current_user)

    if payload.notes is not None:
        item.notes = payload.notes
    if payload.position_order is not None:
        item.position_order = payload.position_order

    await db.commit()
    await db.refresh(item)
    return item


@router.delete(
    "/{watchlist_id}/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_item(
    watchlist_id: UUID,
    item_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Remove an item from a watchlist.

    Args:
        watchlist_id: UUID of the parent watchlist.
        item_id: UUID of the item to remove.
        db: Async database session (injected).
        current_user: Authenticated user (injected).

    Raises:
        HTTPException 404: If the item or watchlist is not found / not owned.
    """
    item = await _get_item_or_404(item_id, watchlist_id, db, current_user)
    await db.delete(item)
    await db.commit()


# -- Buy from watchlist -------------------------------------------------------


@router.post(
    "/{watchlist_id}/items/{item_id}/buy",
    status_code=status.HTTP_201_CREATED,
)
async def buy_from_watchlist(
    watchlist_id: UUID,
    item_id: UUID,
    payload: WatchlistBuyRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Buy an asset from a watchlist into a portfolio.

    Creates a new PortfolioPosition in the specified portfolio using the
    watchlist item's symbol and asset_type combined with the quantity,
    purchase_price, purchase_date, and name from the request body.

    The target portfolio must belong to the authenticated user.

    Args:
        watchlist_id: UUID of the parent watchlist.
        item_id: UUID of the watchlist item to buy from.
        payload: WatchlistBuyRequest containing portfolio_id, quantity,
            purchase_price, purchase_date, and optional name.
        db: Async database session (injected).
        current_user: Authenticated user (injected).

    Returns:
        dict: A JSON object with "status" and created position details
            (position_id, ticker, quantity, purchase_price).

    Raises:
        HTTPException 404: If the watchlist item is not found / not owned,
            or if the target portfolio is not found / not owned.
    """
    # Verify watchlist item exists and belongs to the user
    item = await _get_item_or_404(item_id, watchlist_id, db, current_user)

    # Verify the target portfolio belongs to the current user
    portfolio_result = await db.execute(
        select(Portfolio).where(
            Portfolio.portfolio_id == payload.portfolio_id,
            Portfolio.user_id == current_user.user_id,
        )
    )
    portfolio = portfolio_result.scalar_one_or_none()
    if portfolio is None:
        raise HTTPException(status_code=404, detail="Portfolio not found.")

    # Create a new position in the target portfolio
    position = PortfolioPosition(
        portfolio_id=payload.portfolio_id,
        ticker=item.symbol,
        name=payload.name,
        quantity=payload.quantity,
        purchase_date=payload.purchase_date,
        purchase_price=payload.purchase_price,
        asset_type=item.asset_type,
    )
    db.add(position)
    await db.commit()
    await db.refresh(position)

    return {
        "status": "success",
        "position_id": str(position.position_id),
        "ticker": position.ticker,
        "quantity": float(position.quantity),
        "purchase_price": float(position.purchase_price),
    }
