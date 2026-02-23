from collections import defaultdict
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import Account, Holding, Security
from ..schemas import (
    AccountPortfolioSummary,
    HoldingPositionOut,
    PortfolioSummary,
)
from .auth_routes import get_current_user


router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("/positions", response_model=list[HoldingPositionOut])
async def get_positions(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    accounts_result = await db.execute(
        select(Account).where(Account.user_id == current_user.user_id)
    )
    accounts = accounts_result.scalars().all()
    account_ids = [a.account_id for a in accounts]

    if not account_ids:
        return []

    result = await db.execute(
        select(Holding, Security)
        .join(Security, Holding.security_id == Security.security_id)
        .where(Holding.account_id.in_(account_ids))
    )

    positions: list[HoldingPositionOut] = []
    for holding, security in result.all():
        quantity = holding.quantity or Decimal("0")
        current_price = holding.current_price or Decimal("0")
        market_value = quantity * current_price

        positions.append(
            HoldingPositionOut(
                account_id=holding.account_id,
                security_id=holding.security_id,
                symbol=security.symbol,
                name=security.name,
                quantity=quantity,
                average_cost=holding.average_cost,
                current_price=holding.current_price,
                market_value=market_value,
                currency=security.currency,
            )
        )

    return positions


@router.get("/summary", response_model=PortfolioSummary)
async def get_portfolio_summary(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    accounts_result = await db.execute(
        select(Account).where(Account.user_id == current_user.user_id)
    )
    accounts = accounts_result.scalars().all()
    account_ids = [a.account_id for a in accounts]

    # No accounts yet -> empty portfolio
    if not account_ids:
        return PortfolioSummary(accounts=[], total_portfolio_value=Decimal("0.00"))

    holdings_result = await db.execute(
        select(Holding, Security)
        .join(Security, Holding.security_id == Security.security_id)
        .where(Holding.account_id.in_(account_ids))
    )

    positions_value_by_account: dict = defaultdict(lambda: Decimal("0"))

    for holding, security in holdings_result.all():
        quantity = holding.quantity or Decimal("0")
        current_price = holding.current_price or Decimal("0")
        market_value = quantity * current_price
        positions_value_by_account[holding.account_id] += market_value

    account_summaries: list[AccountPortfolioSummary] = []
    total_portfolio_value = Decimal("0")

    for account in accounts:
        cash_balance = account.balance or Decimal("0")
        positions_value = positions_value_by_account[account.account_id]
        total_value = cash_balance + positions_value

        account_summaries.append(
            AccountPortfolioSummary(
                account_id=account.account_id,
                account_type=account.account_type,
                currency=account.currency,
                cash_balance=cash_balance,
                positions_value=positions_value,
                total_value=total_value,
            )
        )
        total_portfolio_value += total_value

    # We keep a single top-level currency field for now; in mixed-currency
    # setups, consumers should look at per-account currencies.
    return PortfolioSummary(
        accounts=account_summaries,
        total_portfolio_value=total_portfolio_value,
        currency="USD",
    )

