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

Upserts positions tagged group_tag='DEGIRO_SYNC'. All other positions untouched.
Removes stale DEGIRO_SYNC positions (fully sold in DeGiro) after each sync.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import httpx
import pyotp
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from ..logging_config import configure_structlog
from ..models import PortfolioPosition

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
    """Login to DeGiro and return sessionId, or None on failure."""
    resp = await client.post(
        f"{_BASE}/login/secure/login",
        json={
            "username": username,
            "password": password,
            "isPassCodeReset": False,
            "isRedirectToMobile": False,
        },
    )
    resp.raise_for_status()
    body = resp.json()

    logger.info(
        "degiro_login_response",
        status=resp.status_code,
        body_keys=list(body.keys()),
        data_keys=list((body.get("data") or {}).keys()),
        cookie_keys=list(resp.cookies.keys()),
        captcha_required=body.get("captchaRequired"),
        login_status=body.get("status"),
        login_status_text=body.get("statusText"),
    )

    session_id: str | None = resp.cookies.get("JSESSIONID") or (
        body.get("data") or {}
    ).get("sessionId")

    if not session_id:
        return None

    # Send TOTP if configured — completes 2FA regardless of status code
    if totp_secret:
        otp_code = int(pyotp.TOTP(totp_secret).now())
        totp_resp = await client.post(
            f"{_BASE}/login/secure/login/totp",
            json={"oneTimePassword": otp_code},
            cookies={"JSESSIONID": session_id},
        )
        totp_resp.raise_for_status()
        totp_body = totp_resp.json()
        session_id = (
            totp_resp.cookies.get("JSESSIONID")
            or (totp_body.get("data") or {}).get("sessionId")
            or session_id
        )

    return session_id


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
        params={"portfolio": 0},
    )
    resp.raise_for_status()
    return (resp.json().get("portfolio") or {}).get("value") or []


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


async def sync_degiro_portfolio(ctx: dict) -> dict:
    """arq job: pull DeGiro positions and upsert into portfolio_positions."""
    log = logger.bind(job="sync_degiro_portfolio")

    username = os.getenv("DEGIRO_USERNAME")
    password = os.getenv("DEGIRO_PASSWORD")
    totp_secret = os.getenv("DEGIRO_TOTP_SECRET")
    int_account_env = os.getenv("DEGIRO_INT_ACCOUNT")
    portfolio_id_str = os.getenv("DEGIRO_PORTFOLIO_ID")
    session_id_env = os.getenv("DEGIRO_SESSION_ID")

    if not (portfolio_id_str):
        log.warning("degiro_sync_skipped", reason="env vars not configured")
        return {
            "status": "skipped",
            "reason": "DEGIRO_PORTFOLIO_ID not set",
        }

    session_id_env = os.getenv("DEGIRO_SESSION_ID")
    if not session_id_env and not (username and password):
        log.warning("degiro_sync_skipped", reason="env vars not configured")
        return {
            "status": "skipped",
            "reason": "DEGIRO_USERNAME / DEGIRO_PASSWORD / DEGIRO_PORTFOLIO_ID not set",
        }

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
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers=headers) as client:
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
            product_positions = [
                p for p in positions_raw
                if p.get("positionType") == "PRODUCT" and (p.get("size") or 0) > 0
            ]

            if not product_positions:
                log.info("degiro_sync_empty")
                return {"status": "ok", "synced": 0, "deleted": 0}

            product_ids = [p["id"] for p in product_positions]
            products_map = await _get_products_info(
                client, session_id, int_account, product_ids
            )

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

        # Soft-close stale DEGIRO_SYNC positions no longer held in DeGiro
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
        await db.commit()

    log.info("degiro_sync_complete", synced=synced, skipped=skipped, deleted=deleted)
    return {"status": "ok", "synced": synced, "skipped": skipped, "deleted": deleted}
