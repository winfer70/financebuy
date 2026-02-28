"""
main.py — FastAPI application entry point for TickerTap.

Configures middleware (CORS, request logging), registers all route modules,
and performs startup validation of critical settings.
"""

import logging
import os
import time

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from .auth import validate_jwt_config
from .routes import accounts, admin, auth_routes, holdings, market, orders, portfolio, transactions

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("tickerTap")

# ── Application ──────────────────────────────────────────────────────────────
app = FastAPI(title="tickerTap API", version="0.2.0")


# ── Startup validation ───────────────────────────────────────────────────────
@app.on_event("startup")
async def _startup_checks():
    """Validate critical configuration on startup."""
    validate_jwt_config()
    logger.info("Startup checks passed — JWT secret validated.")


# ── CORS — restricted to known origins with explicit methods/headers ─────────
_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins.split(",")],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)


# ── Request logging middleware ───────────────────────────────────────────────
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs every request with method, path, status code, and duration."""

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "%s %s → %d (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response


app.add_middleware(RequestLoggingMiddleware)


# ── Routes ───────────────────────────────────────────────────────────────────
app.include_router(auth_routes.router)
app.include_router(accounts.router)
app.include_router(transactions.router)
app.include_router(portfolio.router)
app.include_router(orders.router)
app.include_router(admin.router)
app.include_router(market.router, prefix="/market", tags=["market"])
app.include_router(holdings.router, prefix="/holdings", tags=["holdings"])


@app.get("/health")
async def health():
    """Lightweight health check for load balancers and monitoring."""
    return {"status": "ok"}


@app.get("/docker-compose")
async def docker_compose():
    """Endpoint used by integration tests to validate docker-compose setup."""
    return {"status": "ok"}
