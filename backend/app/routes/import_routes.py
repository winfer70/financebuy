"""
import_routes.py — CSV import routes for broker transaction history.

Currently supports: DeGiro (Dutch online broker).

Provides:
    POST /import/degiro/csv — Parse and optionally persist a DeGiro CSV export.

Dry-run mode (dry_run=true) parses the file and returns a preview without
writing anything to the database.  Submit again with dry_run=false to commit.

Ownership:
    Portfolio ownership is verified against the authenticated user before
    any data is read or written.  Returns HTTP 404 (not 403) to avoid
    leaking portfolio existence to other users.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import Portfolio, PortfolioPosition, PortfolioTrade
from ..services.degiro_csv_parser import DegiroCSVParser, DegiroRow
from .auth_routes import get_current_user

router = APIRouter(prefix="/import", tags=["import"])

# Maximum CSV file size accepted by this endpoint (5 MB).
_MAX_IMPORT_BYTES = 5 * 1024 * 1024


# ---------------------------------------------------------------------------
# Response schemas (Pydantic v1)
# ---------------------------------------------------------------------------

class DegiroPreviewRow(BaseModel):
    """A single trade row returned in dry-run preview mode.

    All numeric fields are serialised as strings to avoid IEEE-754 precision
    loss when the frontend parses the JSON.

    Attributes:
        trade_type:     "BUY" or "SELL".
        product:        Human-readable instrument name.
        isin:           ISIN code.
        quantity:       Number of units traded (string representation).
        price_per_unit: Per-unit execution price (string).
        total_value:    Absolute cash value (|change_amount|) (string).
        trade_date:     ISO-8601 datetime string.
        change_currency: ISO-4217 currency code of the settlement.
        order_id:       DeGiro order ID, or None.
    """
    trade_type: str
    product: str
    isin: str
    quantity: str
    price_per_unit: str
    total_value: str
    trade_date: str
    change_currency: str
    order_id: Optional[str] = None

    class Config:
        orm_mode = True


class DegiroImportResult(BaseModel):
    """Response body for POST /import/degiro/csv.

    Attributes:
        imported_trades:    Number of PortfolioTrade rows inserted (0 on dry run).
        imported_positions: Number of PortfolioPosition rows inserted (0 on dry run).
        skipped_rows:       Non-trade CSV rows skipped (dividends, fees, FX).
        parse_errors:       Human-readable messages for any row parse failures.
        dry_run:            True when the request was a dry run (no DB writes).
        preview:            Parsed trade rows, populated only in dry-run mode.
    """
    imported_trades: int
    imported_positions: int
    skipped_rows: int
    parse_errors: List[str]
    dry_run: bool
    preview: Optional[List[DegiroPreviewRow]] = None

    class Config:
        orm_mode = True


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/degiro/csv", response_model=DegiroImportResult)
async def import_degiro_csv(
    file: UploadFile = File(..., description="DeGiro transaction history CSV export."),
    portfolio_id: str = Form(..., description="UUID of the target portfolio."),
    dry_run: bool = Form(False, description="If true, parse and preview without writing to DB."),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Import a DeGiro transaction history CSV into a portfolio.

    - Verifies portfolio ownership.
    - Parses the CSV using DegiroCSVParser.
    - In dry_run mode, returns a preview without any DB writes.
    - In commit mode, inserts PortfolioTrade rows for every trade and
      upserts net PortfolioPosition rows for all ISINs with quantity > 0.

    Args:
        file:         Uploaded CSV file (max 5 MB).
        portfolio_id: UUID string of the target portfolio.
        dry_run:      When True, parse and return preview; do not write to DB.
        db:           Async SQLAlchemy session (injected).
        current_user: Authenticated user ORM object (injected).

    Returns:
        DegiroImportResult with trade/position counts or preview data.

    Raises:
        HTTP 422: Invalid portfolio_id UUID or CSV parse error.
        HTTP 404: Portfolio not found or not owned by current user.
        HTTP 413: File exceeds 5 MB size limit.
    """
    # Validate and parse portfolio UUID.
    try:
        portfolio_uuid = uuid.UUID(portfolio_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid portfolio_id — must be a UUID")

    # Verify portfolio ownership (returns 404 to avoid ID enumeration).
    portfolio_result = await db.execute(
        select(Portfolio).where(
            Portfolio.portfolio_id == portfolio_uuid,
            Portfolio.user_id == current_user.user_id,
        )
    )
    if portfolio_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    # Read and enforce file size limit.
    content = await file.read()
    if len(content) > _MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 5 MB)")

    # Parse CSV bytes.
    parser = DegiroCSVParser()
    parse_result = parser.parse(content)

    # If there are no rows AND there are header/structural errors, surface them.
    if not parse_result.rows and parse_result.error_count > 0:
        raise HTTPException(
            status_code=422,
            detail="; ".join(parse_result.errors[:5]),
        )

    # --- Dry-run mode: return preview without writing ---
    if dry_run:
        preview = [
            DegiroPreviewRow(
                trade_type=row.trade_type,
                product=row.product,
                isin=row.isin,
                quantity=str(row.quantity),
                price_per_unit=str(row.price_per_unit),
                total_value=str(abs(row.change_amount)),
                trade_date=datetime.combine(row.trade_date, row.trade_time).isoformat(),
                change_currency=row.change_currency,
                order_id=row.order_id,
            )
            for row in parse_result.rows
        ]
        return DegiroImportResult(
            imported_trades=0,
            imported_positions=0,
            skipped_rows=parse_result.skipped_count,
            parse_errors=parse_result.errors,
            dry_run=True,
            preview=preview,
        )

    # --- Commit mode: write trades and net positions ---
    imported_trades = 0

    # net_positions accumulates running quantity and cost per ISIN.
    # Structure: isin → { product, quantity, total_cost, earliest_date }
    net_positions: dict = {}

    for row in parse_result.rows:
        trade = _make_portfolio_trade(portfolio_uuid, row)
        db.add(trade)
        imported_trades += 1

        isin = row.isin
        if isin not in net_positions:
            net_positions[isin] = {
                "product": row.product,
                "quantity": Decimal("0"),
                "total_cost": Decimal("0"),
                "earliest_date": row.trade_date,
            }

        if row.trade_type == "BUY":
            net_positions[isin]["quantity"] += row.quantity
            net_positions[isin]["total_cost"] += row.quantity * row.price_per_unit
        else:  # SELL
            net_positions[isin]["quantity"] -= row.quantity
            # Clamp to zero — we do not model short positions here.
            if net_positions[isin]["quantity"] < 0:
                net_positions[isin]["quantity"] = Decimal("0")

        # Keep the earliest trade date across all trades for this ISIN.
        if row.trade_date < net_positions[isin]["earliest_date"]:
            net_positions[isin]["earliest_date"] = row.trade_date

    # Insert a PortfolioPosition for each ISIN with a positive net quantity.
    imported_positions = 0
    for isin, pos_data in net_positions.items():
        if pos_data["quantity"] <= 0:
            continue

        # Average cost per unit = total buy cost / net quantity held.
        qty = pos_data["quantity"]
        avg_price = pos_data["total_cost"] / qty if qty > 0 else Decimal("0")

        position = _make_portfolio_position(portfolio_uuid, isin, pos_data, avg_price)
        db.add(position)
        imported_positions += 1

    await db.commit()

    return DegiroImportResult(
        imported_trades=imported_trades,
        imported_positions=imported_positions,
        skipped_rows=parse_result.skipped_count,
        parse_errors=parse_result.errors,
        dry_run=False,
        preview=None,
    )


# ---------------------------------------------------------------------------
# ORM factory helpers
# ---------------------------------------------------------------------------

def _make_portfolio_trade(portfolio_id: uuid.UUID, row: DegiroRow) -> PortfolioTrade:
    """Construct a PortfolioTrade ORM instance from a parsed DeGiro row.

    Uses exact field names from the PortfolioTrade model:
        trade_type  — String(10): "BUY" or "SELL" (uppercase)
        ticker      — String(20): product name truncated to 20 chars
        quantity    — Numeric(18, 6)
        price       — Numeric(18, 4): per-unit execution price
        total_value — Numeric(18, 4): absolute cash value of the trade
        notes       — Text: ISIN, order ID, and source tag
        created_at  — DateTime: trade date + time combined

    Args:
        portfolio_id: UUID of the parent portfolio.
        row:          Parsed DegiroRow.

    Returns:
        Unsaved PortfolioTrade ORM instance.
    """
    return PortfolioTrade(
        portfolio_id=portfolio_id,
        trade_type=row.trade_type,                       # "BUY" or "SELL" — uppercase as stored in DB
        ticker=row.product[:20],                         # String(20) column limit
        quantity=row.quantity,
        price=row.price_per_unit,
        cost_basis=None,                                 # Only captured for SELL with known avg cost
        total_value=abs(row.change_amount),
        notes=(
            f"DEGIRO | ISIN: {row.isin} | "
            f"Order: {row.order_id or 'N/A'} | "
            f"CCY: {row.change_currency}"
        ),
        created_at=datetime.combine(row.trade_date, row.trade_time),
    )


def _make_portfolio_position(
    portfolio_id: uuid.UUID,
    isin: str,
    pos_data: dict,
    avg_price: Decimal,
) -> PortfolioPosition:
    """Construct a PortfolioPosition ORM instance from net ISIN data.

    Uses exact field names from the PortfolioPosition model:
        ticker        — String(20): product name truncated to 20 chars
        name          — String(256): full product name
        quantity      — Numeric(18, 6): net quantity after all BUY/SELL
        purchase_date — DateTime: earliest trade date for this ISIN
        purchase_price — Numeric(18, 2): average cost per unit
        group_tag     — String(64): "DEGIRO" to mark import source
        is_excluded   — Boolean: False (visible in portfolio)
        asset_type    — String(20): "stock" (DeGiro default)

    Args:
        portfolio_id: UUID of the parent portfolio.
        isin:         ISIN code for the position.
        pos_data:     Accumulated net data dict (product, quantity, etc.).
        avg_price:    Computed average cost per unit.

    Returns:
        Unsaved PortfolioPosition ORM instance.
    """
    return PortfolioPosition(
        portfolio_id=portfolio_id,
        ticker=pos_data["product"][:20],                 # String(20) column limit
        name=pos_data["product"][:256],                  # String(256) column limit
        quantity=pos_data["quantity"],
        purchase_date=datetime.combine(
            pos_data["earliest_date"], datetime.min.time()
        ),
        purchase_price=avg_price,
        group_tag="DEGIRO",                              # Source tag for filtering
        is_excluded=False,
        asset_type="stock",                              # Default; DeGiro is primarily equities
    )
