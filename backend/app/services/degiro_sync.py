"""degiro_sync.py — arq job: sync DeGiro portfolio positions via direct API calls.

Uses httpx (already in requirements) to call DeGiro's internal HTTPS API.
No third-party DeGiro library — avoids pydantic v2 dep conflict.
Credentials come exclusively from environment variables. Never logged.

Required env vars:
    DEGIRO_USERNAME      DeGiro account email
    DEGIRO_PASSWORD      DeGiro account password
    DEGIRO_TOTP_SECRET   Base32 TOTP secret (from authenticator app setup)
    DEGIRO_INT_ACCOUNT   Integer account ID (fetched automatically if missing)
    DEGIRO_PORTFOLIO_ID  UUID of the portfolio to sync into

Optional env vars:
    DEGIRO_SESSION_ID              Manual browser session cookie (bypasses login)
    DEGIRO_CLEANUP_MANUAL_POSITIONS  Set to "true" to delete non-DEGIRO_SYNC
                                     stock/etf positions from the portfolio on sync

Upserts positions tagged group_tag='DEGIRO_SYNC'. All other positions untouched
unless DEGIRO_CLEANUP_MANUAL_POSITIONS=true.
Removes stale DEGIRO_SYNC positions (fully sold in DeGiro) after each sync.
Updates portfolio.cash_balance from DeGiro cash positions.
Syncs transaction history into degiro_transactions table.
"""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from typing import Any

import httpx
import pyotp
import structlog
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from ..logging_config import configure_structlog
from ..models import DegiroTransaction, Portfolio, PortfolioPosition

configure_structlog()
logger = structlog.get_logger("degiro_sync")

_DATABASE_URL = os.environ["DATABASE_URL"]
_engine = create_async_engine(
    _DATABASE_URL, echo=False, pool_size=3, max_overflow=1, pool_pre_ping=True
)
_SessionLocal = sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

_BASE = "https://trader.degiro.nl"


def _map_product_type(product_type: str | None) -> str:
    if not product_type:
        return "stock"
    return "etf" if str(product_type).upper() == "ETF" else "stock"


async def _login(
    client: httpx.AsyncClient,
    username: str,
    password: str,
    totp_secret: str | None,
) -> str | None:
    """Login to DeGiro and return sessionId, or None on failure.

    Matches degiro-connector behaviour: if TOTP secret is set, send a single
    POST directly to /login/secure/login/totp with all credentials + OTP.
    No two-step challenge flow.
    """
    if totp_secret:
        url = f"{_BASE}/login/secure/login/totp"
        otp_str = pyotp.TOTP(totp_secret).now()  # string, zero-padded
        body: dict[str, Any] = {
            "username": username,
            "password": password,
            "isPassCodeReset": False,
            "isRedirectToMobile": False,
            "queryParams": {},
            "oneTimePassword": otp_str,  # string per degiro-connector
        }
    else:
        url = f"{_BASE}/login/secure/login"
        body = {
            "username": username,
            "password": password,
            "isPassCodeReset": False,
            "isRedirectToMobile": False,
            "queryParams": {},
        }

    resp = await client.post(url, follow_redirects=True, json=body)
    resp_body = resp.json() if resp.text else {}

    logger.info(
        "degiro_login_response",
        status=resp.status_code,
        login_status=resp_body.get("status"),
        login_status_text=resp_body.get("statusText"),
    )

    if not resp.is_success:
        resp.raise_for_status()

    session_id: str | None = (
        resp.cookies.get("JSESSIONID")
        or client.cookies.get("JSESSIONID")
        or (resp_body.get("data") or {}).get("sessionId")
        or resp_body.get("sessionId")
    )
    return session_id


def _flatten_position(raw: dict) -> dict:
    """Convert DeGiro's [{name, value}] position structure to a flat dict."""
    result = {}
    for item in raw.get("value") or []:
        result[item["name"]] = item.get("value")
    return result


async def _get_int_account(client: httpx.AsyncClient, session_id: str) -> int | None:
    resp = await client.get(
        f"{_BASE}/pa/secure/client",
        params={"sessionId": session_id},
    )
    resp.raise_for_status()
    return (resp.json().get("data") or {}).get("intAccount")


async def _get_portfolio(
    client: httpx.AsyncClient, session_id: str, int_account: int
) -> list[dict[str, Any]]:
    resp = await client.get(
        f"{_BASE}/trading/secure/v5/update/{int_account};jsessionid={session_id}",
        params={"portfolio": 0, "totalPortfolio": 0},
    )
    resp.raise_for_status()
    return (resp.json().get("portfolio") or {}).get("value") or []


async def _get_account_overview(
    client: httpx.AsyncClient, session_id: str, int_account: int
) -> dict[str, Any]:
    resp = await client.get(
        f"{_BASE}/trading/secure/v5/update/{int_account};jsessionid={session_id}",
        params={"totalPortfolio": 0},
    )
    resp.raise_for_status()
    raw = (resp.json().get("totalPortfolio") or {}).get("value") or []
    return {item["name"]: item.get("value") for item in raw}


async def _get_products_info(
    client: httpx.AsyncClient,
    session_id: str,
    int_account: int,
    product_ids: list[int],
) -> dict[str, Any]:
    resp = await client.post(
        f"{_BASE}/product_search/secure/v5/products/info",
        params={"intAccount": int_account, "sessionId": session_id},
        json=product_ids,
    )
    resp.raise_for_status()
    return resp.json().get("data") or {}


async def _get_transactions(
    client: httpx.AsyncClient,
    session_id: str,
    int_account: int,
    from_date: date,
    to_date: date,
) -> list[dict[str, Any]]:
    # Use a separate client with follow_redirects=True — the account endpoint
    # returns 302 when sessionId is passed as a query param; jsessionid in path
    # also redirects in some deployments. Follow through to the final destination.
    async with httpx.AsyncClient(
        timeout=30.0,
        follow_redirects=True,
        headers=client.headers,
        cookies=client.cookies,
    ) as tx_client:
        resp = await tx_client.get(
            f"{_BASE}/account/secure/v5/transactions",
            params={
                "fromDate": from_date.strftime("%d/%m/%Y"),
                "toDate": to_date.strftime("%d/%m/%Y"),
                "intAccount": int_account,
                "sessionId": session_id,
            },
        )
    logger.info("degiro_transactions_response", status=resp.status_code, url=str(resp.url))
    if not resp.is_success:
        resp.raise_for_status()
    return resp.json().get("data") or []


def _extract_cash_balance(positions_raw: list[dict]) -> Decimal:
    """Sum all CASH-type positions (base-currency value) from portfolio response."""
    total = Decimal(0)
    for raw in positions_raw:
        flat = _flatten_position(raw)
        if flat.get("positionType") == "CASH":
            size = flat.get("size") or 0
            total += Decimal(str(size))
    return total


async def sync_degiro_portfolio(ctx: dict) -> dict:
    """arq job: pull DeGiro positions, cash, and transactions; upsert into DB."""
    log = logger.bind(job="sync_degiro_portfolio")

    username = os.getenv("DEGIRO_USERNAME")
    password = os.getenv("DEGIRO_PASSWORD")
    totp_secret = os.getenv("DEGIRO_TOTP_SECRET")
    int_account_env = os.getenv("DEGIRO_INT_ACCOUNT")
    portfolio_id_str = os.getenv("DEGIRO_PORTFOLIO_ID")
    session_id_env = os.getenv("DEGIRO_SESSION_ID")
    cleanup_manual = os.getenv("DEGIRO_CLEANUP_MANUAL_POSITIONS", "").lower() == "true"

    if not portfolio_id_str:
        log.warning("degiro_sync_skipped", reason="DEGIRO_PORTFOLIO_ID not set")
        return {"status": "skipped", "reason": "DEGIRO_PORTFOLIO_ID not set"}

    if not session_id_env and not (username and password):
        log.warning("degiro_sync_skipped", reason="credentials not configured")
        return {"status": "skipped", "reason": "credentials not set"}

    try:
        portfolio_id = uuid.UUID(portfolio_id_str)
    except ValueError:
        log.error("degiro_sync_error", reason="invalid DEGIRO_PORTFOLIO_ID")
        return {"status": "error", "reason": "DEGIRO_PORTFOLIO_ID is not a valid UUID"}

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Origin": "https://trader.degiro.nl",
            "Referer": "https://trader.degiro.nl/trader/",
        }
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=False, headers=headers) as client:
            log.info("degiro_connecting")
            if session_id_env:
                session_id = session_id_env
                log.info("degiro_using_env_session")
            else:
                session_id = await _login(client, username, password, totp_secret)
            if not session_id:
                log.error("degiro_login_failed")
                return {"status": "error", "reason": "login failed — check credentials"}

            int_account = (
                int(int_account_env)
                if int_account_env
                else await _get_int_account(client, session_id)
            )
            if not int_account:
                log.error("degiro_sync_error", reason="could not resolve int_account")
                return {"status": "error", "reason": "could not resolve int_account"}

            log.info("degiro_fetching_portfolio")
            positions_raw = await _get_portfolio(client, session_id, int_account)
            all_flat = [_flatten_position(p) for p in positions_raw]

            cash_balance = _extract_cash_balance(positions_raw)

            product_positions = [
                p for p in all_flat
                if p.get("positionType") == "PRODUCT" and (p.get("size") or 0) > 0
            ]

            if not product_positions:
                log.info("degiro_sync_empty")
                async with _SessionLocal() as db:
                    if cleanup_manual:
                        await _delete_manual_positions(portfolio_id, db)
                    await _update_cash(portfolio_id, cash_balance, db)
                    await db.commit()
                return {"status": "ok", "synced": 0, "deleted": 0, "cash": str(cash_balance)}

            product_ids = [p["id"] for p in product_positions]
            products_map = await _get_products_info(
                client, session_id, int_account, product_ids
            )

            # Fetch account overview (best-effort)
            try:
                overview = await _get_account_overview(client, session_id, int_account)
            except Exception:
                overview = {}

            # Fetch transactions (last 2 years, best-effort)
            try:
                today = date.today()
                tx_raw = await _get_transactions(
                    client, session_id, int_account,
                    from_date=today - timedelta(days=730),
                    to_date=today,
                )
            except Exception:
                tx_raw = []

    except httpx.HTTPStatusError as exc:
        log.error("degiro_http_error", status=exc.response.status_code)
        return {"status": "error", "reason": f"HTTP {exc.response.status_code}"}
    except httpx.RequestError as exc:
        log.error("degiro_request_error", error=type(exc).__name__)
        return {"status": "error", "reason": f"request error: {type(exc).__name__}"}

    synced = 0
    skipped = 0
    current_isins: set[str] = set()

    async with _SessionLocal() as db:
        # ── cleanup manual positions (optional) ──────────────────────────────
        cleaned = 0
        if cleanup_manual:
            cleaned = await _delete_manual_positions(portfolio_id, db)

        # ── upsert DEGIRO_SYNC positions ─────────────────────────────────────
        for raw_pos in product_positions:
            product = products_map.get(str(raw_pos["id"]))
            if not product or not product.get("isin"):
                skipped += 1
                continue

            isin: str = product["isin"]
            current_isins.add(isin)

            quantity = Decimal(str(raw_pos.get("size") or 0))
            if quantity <= 0:
                skipped += 1
                continue

            avg_price = Decimal(
                str(raw_pos.get("breakEvenPrice") or raw_pos.get("price") or 0)
            )
            symbol: str = product.get("symbol") or ""
            ticker = symbol[:20] if symbol else isin[:20]
            name = (product.get("name") or isin)[:256]
            asset_type = _map_product_type(product.get("productType"))

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
                        degiro_product_id=int(raw_pos["id"]),
                        quantity=quantity,
                        purchase_price=avg_price,
                        purchase_date=datetime.now(timezone.utc),
                        group_tag="DEGIRO_SYNC",
                        asset_type=asset_type,
                        is_excluded=False,
                    )
                )
            synced += 1

        # ── soft-close stale DEGIRO_SYNC positions ───────────────────────────
        stale_result = await db.execute(
            select(PortfolioPosition).where(
                PortfolioPosition.portfolio_id == portfolio_id,
                PortfolioPosition.group_tag == "DEGIRO_SYNC",
                PortfolioPosition.isin.notin_(current_isins),
                PortfolioPosition.closed_at.is_(None),
            )
        )
        stale = stale_result.scalars().all()
        now = datetime.now(timezone.utc)
        for pos in stale:
            pos.closed_at = now
            pos.sold_reason = f"DEGIRO_SYNC: not in holdings as of {now.date().isoformat()}"
        deleted = len(stale)

        # ── update cash balance ───────────────────────────────────────────────
        await _update_cash(portfolio_id, cash_balance, db)

        # ── upsert transactions ───────────────────────────────────────────────
        tx_count = await _upsert_transactions(portfolio_id, tx_raw, db)

        await db.commit()

    log.info(
        "degiro_sync_complete",
        synced=synced,
        skipped=skipped,
        deleted=deleted,
        cleaned=cleaned,
        cash=str(cash_balance),
        transactions=tx_count,
        portfolio_value=overview.get("reportNetliq"),
    )
    return {
        "status": "ok",
        "synced": synced,
        "skipped": skipped,
        "deleted": deleted,
        "cleaned": cleaned,
        "cash": str(cash_balance),
        "transactions_synced": tx_count,
        "portfolio_value": overview.get("reportNetliq"),
        "total_cash": overview.get("totalCash"),
    }


async def _delete_manual_positions(portfolio_id: uuid.UUID, db: AsyncSession) -> int:
    """Hard-delete non-DEGIRO_SYNC stock/etf positions from the portfolio."""
    result = await db.execute(
        delete(PortfolioPosition)
        .where(
            PortfolioPosition.portfolio_id == portfolio_id,
            or_(
                PortfolioPosition.group_tag.is_(None),
                PortfolioPosition.group_tag != "DEGIRO_SYNC",
            ),
            PortfolioPosition.asset_type.in_(["stock", "etf"]),
            PortfolioPosition.closed_at.is_(None),
        )
        .returning(PortfolioPosition.position_id)
    )
    return len(result.fetchall())


async def _update_cash(
    portfolio_id: uuid.UUID, cash_balance: Decimal, db: AsyncSession
) -> None:
    result = await db.execute(
        select(Portfolio).where(Portfolio.portfolio_id == portfolio_id)
    )
    portfolio = result.scalar_one_or_none()
    if portfolio:
        portfolio.cash_balance = cash_balance


async def _upsert_transactions(
    portfolio_id: uuid.UUID,
    tx_raw: list[dict],
    db: AsyncSession,
) -> int:
    if not tx_raw:
        return 0

    upserted = 0
    for tx in tx_raw:
        tx_id = tx.get("id")
        if not tx_id:
            continue

        existing = await db.get(DegiroTransaction, tx_id)
        if existing:
            continue  # already stored, skip (transactions are immutable)

        raw_date = tx.get("date") or tx.get("transactionDate") or ""
        try:
            tx_date = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            tx_date = datetime.now(timezone.utc)

        fees = tx.get("totalFeesInBaseCurrency") or 0
        db.add(
            DegiroTransaction(
                transaction_id=int(tx_id),
                portfolio_id=portfolio_id,
                date=tx_date,
                product_name=(tx.get("product") or "")[:256],
                isin=(tx.get("isin") or "")[:12] or None,
                ticker=(tx.get("symbol") or "")[:20] or None,
                buysell=tx.get("buysell") or None,
                quantity=Decimal(str(tx.get("quantity") or 0)),
                price=Decimal(str(tx.get("price") or 0)),
                value=Decimal(str(tx.get("value") or 0)),
                currency=tx.get("currency") or None,
                total_in_base=Decimal(str(tx.get("totalInBaseCurrency") or 0)),
                fee_in_base=Decimal(str(fees)),
            )
        )
        upserted += 1

    return upserted
