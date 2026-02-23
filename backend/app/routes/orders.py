from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import Account, Holding, Order
from ..schemas import OrderCreate, OrderOut
from .auth_routes import get_current_user


router = APIRouter(prefix="/orders", tags=["orders"])


def _normalize_side(side: str) -> str:
    s = side.lower()
    if s not in {"buy", "sell"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="side must be 'buy' or 'sell'",
        )
    return s


def _normalize_order_type(order_type: str) -> str:
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

    # Load and lock the account row
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

    # Limit orders: create a pending order in the book without
    # touching cash or holdings. Execution happens via /orders/{id}/execute.
    if order_type == "limit":
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
        async with db.begin():
            db.add(order)
        await db.refresh(order)
        return order

    # Market orders: immediate execution model
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
        new_cash = current_cash - notional

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
            new_avg = total_cost / total_shares

            holding.quantity = total_shares
            holding.average_cost = new_avg
            holding.current_price = effective_price

        account.balance = new_cash

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

    async with db.begin():
        db.add(order)

    await db.refresh(order)
    return order


@router.post("/{order_id}/cancel", response_model=OrderOut)
async def cancel_order(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
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
    order.cancelled_at = datetime.utcnow()

    async with db.begin():
        db.add(order)

    await db.refresh(order)
    return order


@router.post("/{order_id}/execute", response_model=OrderOut)
async def execute_order(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # Load order and owning account with a lock
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
        new_cash = current_cash - notional

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
            new_avg = total_cost / total_shares

            holding.quantity = total_shares
            holding.average_cost = new_avg
            holding.current_price = price

        account.balance = new_cash

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
    order.executed_at = datetime.utcnow()

    async with db.begin():
        db.add(order)

    await db.refresh(order)
    return order


@router.get("", response_model=list[OrderOut])
async def list_orders(
    account_id: Optional[str] = Query(
        default=None,
        description="Filter by account_id; must belong to current user if provided.",
    ),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    query = select(Order).join(Account, Order.account_id == Account.account_id).where(
        Account.user_id == current_user.user_id
    )

    if account_id is not None:
        query = query.where(Order.account_id == account_id)

    result = await db.execute(query)
    return result.scalars().all()
