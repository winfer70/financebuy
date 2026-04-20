"""
orders.py — Order placement, cancellation, and execution routes for TickerTap.

Handles market orders (immediate execution) and limit orders (pending until
manually executed via /orders/{id}/execute).

Race-condition protection strategy
───────────────────────────────────
All operations that touch account balances or holdings are wrapped inside a
single ``async with db.begin():`` block and acquire the account row lock via
``SELECT … FOR UPDATE`` *within that same block*.  This ensures:
  - The lock is held from SELECT through COMMIT (no interleaving reads).
  - All mutations (balance, holding, order record) commit atomically.
  - Any exception rolls back the entire operation with no partial state.

Limit orders do NOT touch the balance at placement time; they only insert an
Order record (no locking needed there).  Execution of a limit order follows
the same lock-acquire-mutate-commit pattern as a market order.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import Account, Holding, Order, Security
from ..schemas import OrderCreate, OrderOut
from .auth_routes import get_current_user


router = APIRouter(prefix="/orders", tags=["orders"])


def _normalize_side(side: str) -> str:
    """Validate and normalise order side to lowercase 'buy' or 'sell'.

    Args:
        side: Raw side string from the request payload.

    Returns:
        Lowercase 'buy' or 'sell'.

    Raises:
        HTTP 400 if side is not one of the accepted values.
    """
    s = side.lower()
    if s not in {"buy", "sell"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="side must be 'buy' or 'sell'",
        )
    return s


def _normalize_order_type(order_type: str) -> str:
    """Validate and normalise order type to lowercase 'market' or 'limit'.

    Args:
        order_type: Raw order type string from the request payload.

    Returns:
        Lowercase 'market' or 'limit'.

    Raises:
        HTTP 400 if order_type is not one of the accepted values.
    """
    t = order_type.lower()
    if t not in {"market", "limit"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="order_type must be 'market' or 'limit'",
        )
    return t


@router.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
async def place_order(
    payload: OrderCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Place a new market or limit order.

    Limit orders: insert a pending Order record only — no balance/holding
    changes at placement time.

    Market orders: acquire an exclusive lock on the account row, validate
    funds/position, update balance and holding, then insert the filled order
    — all within a single atomic transaction to prevent race conditions.

    Args:
        payload: OrderCreate — account_id, security_id, side, order_type,
                 quantity, price.
        db: AsyncSession — injected database session.
        current_user: User — the authenticated user (from JWT).

    Returns:
        OrderOut — the newly created Order record.

    Raises:
        HTTP 400 for invalid quantity/price/side/type or insufficient funds.
        HTTP 404 if the account does not belong to current_user.
    """
    if payload.quantity <= Decimal("0"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="quantity must be positive",
        )
    if payload.price <= Decimal("0"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="price must be positive",
        )

    side = _normalize_side(payload.side)
    order_type = _normalize_order_type(payload.order_type)
    effective_price = payload.price
    notional = payload.quantity * effective_price

    # ── Limit orders: no cash/holding mutation at placement time ────────────
    if order_type == "limit":
        # Still verify the account belongs to the user before accepting the order.
        async with db.begin():
            acct_check = await db.execute(
                select(Account).where(
                    and_(
                        Account.account_id == payload.account_id,
                        Account.user_id == current_user.user_id,
                    )
                )
            )
            if acct_check.scalar_one_or_none() is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="account not found",
                )
            order = Order(
                account_id=payload.account_id,
                security_id=payload.security_id,
                order_type=order_type,
                side=side,
                quantity=payload.quantity,
                price=effective_price,
                status="pending",
                filled_quantity=Decimal("0"),
                filled_price=None,
            )
            db.add(order)
        await db.refresh(order)
        return order

    # ── Market orders: acquire lock, validate, mutate, commit atomically ────
    async with db.begin():
        # Lock the account row for the entire market-order execution path.
        account_result = await db.execute(
            select(Account)
            .where(
                and_(
                    Account.account_id == payload.account_id,
                    Account.user_id == current_user.user_id,
                )
            )
            .with_for_update()
        )
        account = account_result.scalar_one_or_none()
        if account is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="account not found",
            )

        # Fetch current holding (no lock needed — account lock is sufficient).
        holding_result = await db.execute(
            select(Holding).where(
                and_(
                    Holding.account_id == payload.account_id,
                    Holding.security_id == payload.security_id,
                )
            )
        )
        holding: Optional[Holding] = holding_result.scalar_one_or_none()

        if side == "buy":
            current_cash = account.balance or Decimal("0")
            if current_cash < notional:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="insufficient funds",
                )
            account.balance = current_cash - notional

            if holding is None:
                holding = Holding(
                    account_id=payload.account_id,
                    security_id=payload.security_id,
                    quantity=payload.quantity,
                    average_cost=effective_price,
                    current_price=effective_price,
                )
                db.add(holding)
            else:
                existing_qty = holding.quantity or Decimal("0")
                existing_cost = holding.average_cost or Decimal("0")
                total_shares = existing_qty + payload.quantity
                total_cost = existing_qty * existing_cost + notional
                holding.quantity = total_shares
                holding.average_cost = total_cost / total_shares
                holding.current_price = effective_price

        else:  # sell
            if holding is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="no position to sell",
                )
            existing_qty = holding.quantity or Decimal("0")
            if existing_qty < payload.quantity:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="insufficient quantity",
                )
            new_qty = existing_qty - payload.quantity
            account.balance = (account.balance or Decimal("0")) + notional

            if new_qty == 0:
                await db.delete(holding)
            else:
                holding.quantity = new_qty
                holding.current_price = effective_price

        order = Order(
            account_id=payload.account_id,
            security_id=payload.security_id,
            order_type=order_type,
            side=side,
            quantity=payload.quantity,
            price=effective_price,
            status="filled",
            filled_quantity=payload.quantity,
            filled_price=effective_price,
        )
        db.add(order)
    # Commit: balance, holding, and order all persisted atomically.

    await db.refresh(order)
    return order


@router.post("/{order_id}/cancel", response_model=OrderOut)
async def cancel_order(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Cancel a pending limit order.

    Args:
        order_id: UUID of the order to cancel.
        db: AsyncSession — injected database session.
        current_user: User — the authenticated user (from JWT).

    Returns:
        OrderOut — the updated order with status 'cancelled'.

    Raises:
        HTTP 404 if order not found or not owned by current_user.
        HTTP 400 if order is not in 'pending' status.
    """
    async with db.begin():
        result = await db.execute(
            select(Order)
            .join(Account, Order.account_id == Account.account_id)
            .where(
                and_(
                    Order.order_id == order_id,
                    Account.user_id == current_user.user_id,
                )
            )
            .with_for_update()
        )
        order = result.scalar_one_or_none()
        if order is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="order not found",
            )
        if order.status != "pending":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="only pending orders can be cancelled",
            )

        order.status = "cancelled"
        order.cancelled_at = datetime.now(timezone.utc)
        db.add(order)

    await db.refresh(order)
    return order


@router.post("/{order_id}/execute", response_model=OrderOut)
async def execute_order(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Execute a pending limit order.

    Acquires locks on the order and account rows within a single transaction,
    then applies the same buy/sell logic as a market order.

    Args:
        order_id: UUID of the pending order to execute.
        db: AsyncSession — injected database session.
        current_user: User — the authenticated user (from JWT).

    Returns:
        OrderOut — the updated order with status 'filled'.

    Raises:
        HTTP 404 if order not found or not owned by current_user.
        HTTP 400 if order is not in 'pending' status or insufficient funds/qty.
    """
    async with db.begin():
        # Lock both the order and the owning account in one query.
        result = await db.execute(
            select(Order, Account)
            .join(Account, Order.account_id == Account.account_id)
            .where(
                and_(
                    Order.order_id == order_id,
                    Account.user_id == current_user.user_id,
                )
            )
            .with_for_update()
        )
        row = result.first()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="order not found",
            )
        order, account = row

        if order.status != "pending":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="only pending orders can be executed",
            )

        side = _normalize_side(order.side)
        qty = order.quantity
        price = order.price
        notional = qty * price

        holding_result = await db.execute(
            select(Holding).where(
                and_(
                    Holding.account_id == order.account_id,
                    Holding.security_id == order.security_id,
                )
            )
        )
        holding: Optional[Holding] = holding_result.scalar_one_or_none()

        if side == "buy":
            current_cash = account.balance or Decimal("0")
            if current_cash < notional:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="insufficient funds for execution",
                )
            account.balance = current_cash - notional

            if holding is None:
                holding = Holding(
                    account_id=order.account_id,
                    security_id=order.security_id,
                    quantity=qty,
                    average_cost=price,
                    current_price=price,
                )
                db.add(holding)
            else:
                existing_qty = holding.quantity or Decimal("0")
                existing_cost = holding.average_cost or Decimal("0")
                total_shares = existing_qty + qty
                total_cost = existing_qty * existing_cost + notional
                holding.quantity = total_shares
                holding.average_cost = total_cost / total_shares
                holding.current_price = price

        else:  # sell
            if holding is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="no position to sell",
                )
            existing_qty = holding.quantity or Decimal("0")
            if existing_qty < qty:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="insufficient quantity for execution",
                )
            new_qty = existing_qty - qty
            account.balance = (account.balance or Decimal("0")) + notional

            if new_qty == 0:
                await db.delete(holding)
            else:
                holding.quantity = new_qty
                holding.current_price = price

        order.status = "filled"
        order.filled_quantity = qty
        order.filled_price = price
        order.executed_at = datetime.now(timezone.utc)
        db.add(order)
    # Commit: account, holding, and order status all persisted atomically.

    await db.refresh(order)
    return order


@router.get("", response_model=list[OrderOut])
async def list_orders(
    account_id: Optional[str] = Query(
        default=None,
        description="Filter by account_id; must belong to current user if provided.",
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=100,
        description="Maximum number of orders to return (1–100).",
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Number of orders to skip for pagination.",
    ),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List orders belonging to the current user with pagination (P7.2).

    Args:
        account_id: Optional filter — only return orders for this account.
        limit: Maximum results per page (1–100, default 50).
        offset: Number of records to skip (default 0).
        db: AsyncSession — injected database session.
        current_user: User — the authenticated user (from JWT).

    Returns:
        List[OrderOut] — orders ordered newest-first with symbol resolved.
    """
    query = (
        select(Order, Security.symbol)
        .join(Account, Order.account_id == Account.account_id)
        .outerjoin(Security, Order.security_id == Security.security_id)
        .where(Account.user_id == current_user.user_id)
    )

    if account_id is not None:
        query = query.where(Order.account_id == account_id)

    query = query.order_by(Order.placed_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)

    orders = []
    for order, symbol in result.all():
        out = OrderOut.from_orm(order)
        out.symbol = symbol
        out.placed_at = order.placed_at.isoformat() if order.placed_at else None
        orders.append(out)
    return orders
