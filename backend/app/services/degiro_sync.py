"""degiro_sync.py — arq job: sync DeGiro portfolio positions.

Reads credentials from environment variables only. Never logs credential values.
Upserts positions tagged group_tag='DEGIRO_SYNC' — other positions untouched.
Removes stale DEGIRO_SYNC positions (fully sold in DeGiro) after each sync.

Run manually via POST /api/v1/degiro/sync or automatically via daily cron at 02:00.

Required env vars:
    DEGIRO_USERNAME      DeGiro account email
    DEGIRO_PASSWORD      DeGiro account password
    DEGIRO_TOTP_SECRET   Base32 TOTP secret (from authenticator app setup)
    DEGIRO_INT_ACCOUNT   Integer account ID (fetched automatically if missing)
    DEGIRO_PORTFOLIO_ID  UUID of portfolio to sync into
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from ..logging_config import configure_structlog
from ..models import PortfolioPosition

configure_structlog()
logger = structlog.get_logger("degiro_sync")

_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@db:5432/tickerTap",
)
_engine = create_async_engine(
    _DATABASE_URL, echo=False, pool_size=3, max_overflow=1, pool_pre_ping=True
)
_SessionLocal = sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


def _map_product_type(product_type: str | None) -> str:
    if not product_type:
        return "stock"
    pt = product_type.upper()
    if pt == "ETF":
        return "etf"
    return "stock"


async def _run_sync(api: Any, fn, *args, **kwargs):
    """Run a synchronous degiro-connector call in a thread executor."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))


async def sync_degiro_portfolio(ctx: dict) -> dict:
    """arq job: pull DeGiro positions and upsert into portfolio_positions."""
    log = logger.bind(job="sync_degiro_portfolio")

    username = os.getenv("DEGIRO_USERNAME")
    password = os.getenv("DEGIRO_PASSWORD")
    totp_secret = os.getenv("DEGIRO_TOTP_SECRET")
    int_account_env = os.getenv("DEGIRO_INT_ACCOUNT")
    portfolio_id_str = os.getenv("DEGIRO_PORTFOLIO_ID")

    if not (username and password and portfolio_id_str):
        log.warning("degiro_sync_skipped", reason="env vars not configured")
        return {"status": "skipped", "reason": "DEGIRO_USERNAME/DEGIRO_PASSWORD/DEGIRO_PORTFOLIO_ID not set"}

    try:
        portfolio_id = uuid.UUID(portfolio_id_str)
    except ValueError:
        log.error("degiro_sync_error", reason="invalid DEGIRO_PORTFOLIO_ID uuid")
        return {"status": "error", "reason": "invalid DEGIRO_PORTFOLIO_ID"}

    # Import here to avoid hard dep when env not configured
    from degiro_connector.trading.api import API as TradingAPI
    from degiro_connector.trading.models.credentials import Credentials
    from degiro_connector.trading.models.account import UpdateOption, UpdateRequest

    cred_kwargs: dict[str, Any] = {"username": username, "password": password}
    if totp_secret:
        cred_kwargs["totp_secret_key"] = totp_secret
    if int_account_env:
        cred_kwargs["int_account"] = int(int_account_env)

    credentials = Credentials(**cred_kwargs)
    api = TradingAPI(credentials=credentials)

    log.info("degiro_connecting")
    connect_result = await _run_sync(api, api.connect)
    if connect_result is None and not getattr(api, "session_id", None):
        log.error("degiro_connect_failed")
        return {"status": "error", "reason": "DeGiro connect failed — check credentials"}

    # Resolve int_account if not provided
    if not int_account_env:
        details = await _run_sync(api, api.get_client_details)
        if not details:
            log.error("degiro_sync_error", reason="get_client_details returned None")
            return {"status": "error", "reason": "could not fetch int_account"}
        api.credentials.int_account = details["data"]["intAccount"]
        log.info("degiro_int_account_resolved")

    # Fetch portfolio
    account_update = await _run_sync(
        api,
        api.get_update,
        request_list=[UpdateRequest(option=UpdateOption.PORTFOLIO, last_updated=0)],
        raw=True,
    )
    if account_update is None:
        log.error("degiro_sync_error", reason="get_update returned None")
        return {"status": "error", "reason": "get_update returned None"}

    portfolio_data = account_update.get("portfolio") or {}
    positions_raw = [
        p for p in (portfolio_data.get("value") or [])
        if p.get("positionType") == "PRODUCT" and p.get("size", 0) > 0
    ]

    if not positions_raw:
        log.info("degiro_sync_empty")
        return {"status": "ok", "synced": 0, "deleted": 0}

    # Resolve product IDs → metadata
    product_ids = [p["id"] for p in positions_raw]
    products_resp = await _run_sync(api, api.get_products_info, product_list=product_ids, raw=False)
    if products_resp is None:
        log.error("degiro_sync_error", reason="get_products_info returned None")
        return {"status": "error", "reason": "get_products_info returned None"}

    products_map: dict[int, Any] = products_resp.data or {}

    synced = 0
    skipped = 0
    current_isins: set[str] = set()

    async with _SessionLocal() as db:
        for raw_pos in positions_raw:
            product = products_map.get(raw_pos["id"])
            if not product or not getattr(product, "isin", None):
                skipped += 1
                log.debug("degiro_position_skipped", product_id=raw_pos["id"])
                continue

            isin: str = product.isin
            current_isins.add(isin)

            quantity = Decimal(str(raw_pos.get("size", 0)))
            if quantity <= 0:
                skipped += 1
                continue

            break_even = raw_pos.get("breakEvenPrice") or raw_pos.get("price") or 0
            avg_price = Decimal(str(break_even))

            symbol = getattr(product, "symbol", None) or ""
            ticker = (symbol[:20] if symbol else isin[:20])
            name = (getattr(product, "name", None) or isin)[:256]
            asset_type = _map_product_type(getattr(product, "product_type", None))

            result = await db.execute(
                select(PortfolioPosition).where(
                    PortfolioPosition.portfolio_id == portfolio_id,
                    PortfolioPosition.isin == isin,
                    PortfolioPosition.group_tag == "DEGIRO_SYNC",
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.quantity = quantity
                existing.purchase_price = avg_price
                existing.name = name
                existing.ticker = ticker
            else:
                db.add(
                    PortfolioPosition(
                        portfolio_id=portfolio_id,
                        ticker=ticker,
                        name=name,
                        isin=isin,
                        degiro_product_id=raw_pos["id"],
                        quantity=quantity,
                        purchase_price=avg_price,
                        purchase_date=datetime.now(timezone.utc),
                        group_tag="DEGIRO_SYNC",
                        asset_type=asset_type,
                        is_excluded=False,
                    )
                )
            synced += 1

        # Remove stale DEGIRO_SYNC positions no longer in DeGiro
        delete_result = await db.execute(
            delete(PortfolioPosition)
            .where(
                PortfolioPosition.portfolio_id == portfolio_id,
                PortfolioPosition.group_tag == "DEGIRO_SYNC",
                PortfolioPosition.isin.notin_(current_isins),
            )
            .returning(PortfolioPosition.position_id)
        )
        deleted = len(delete_result.fetchall())

        await db.commit()

    log.info("degiro_sync_complete", synced=synced, skipped=skipped, deleted=deleted)
    return {"status": "ok", "synced": synced, "skipped": skipped, "deleted": deleted}
