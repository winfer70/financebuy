"""
main.py — FastAPI application entry point for TickerTap.

Configures middleware (CORS, rate limiting, security headers, request
logging, body size enforcement, correlation ID), registers all route
modules under the /api/v1 prefix, and validates critical settings on startup.

Security middleware applied (outermost → innermost):
  1. CorrelationIDMiddleware    — UUID per request, binds to structlog context
  2. RequestLoggingMiddleware   — structured access logs (sees correlation ID)
  3. RequestBodySizeMiddleware  — rejects oversized payloads (P6.5)
  4. SecurityHeadersMiddleware  — injects HSTS/CSP/X-Frame etc. (P6.2)
  5. CORSMiddleware             — origin restriction
  6. SlowAPIMiddleware          — rate-limit enforcement (429 on breach)

API versioning:
  All business routes are mounted under /api/v1/ (P7.18).
  The /health and /metrics endpoints remain unversioned for monitoring tools.
"""

import asyncio
import os
import time
import uuid

import structlog
from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from .auth import validate_jwt_config
from .limiter import limiter
from .logging_config import configure_structlog
from .observability import APP_START_TIME, check_db, check_redis, get_worker_metrics
from .routes import (
    accounts,
    admin,
    alerts,
    analysis_routes,
    auth_routes,
    chart_templates,
    degiro_routes,
    feedback,
    guide,
    holdings,
    import_routes,
    internal_portfolio,
    market,
    metrics as metrics_routes,
    news,
    orders,
    portfolio,
    portfolio_manager,
    portfolio_rules,
    reports,
    scanner,
    transactions,
    trading,
    watchlists,
)
from .routes.auth_routes import get_current_admin, register_deletion_purge
from .routes.feedback import register_outcome_checker
from .routes.news import register_retention_task

# ── Logging ──────────────────────────────────────────────────────────────────
configure_structlog()
logger = structlog.get_logger("tickerTap")

# ── Application ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="tickerTap API",
    version="1.0.0",
    # Expose docs only in non-production environments
    docs_url=None if os.getenv("ENVIRONMENT") == "production" else "/docs",
    redoc_url=None if os.getenv("ENVIRONMENT") == "production" else "/redoc",
)

# Attach limiter to app state so SlowAPIMiddleware can find it.
app.state.limiter = limiter

# Return HTTP 429 with a clear JSON body when a rate limit is exceeded.
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ── Startup validation ───────────────────────────────────────────────────────

async def _seed_system_strategies():
    """Insert system strategy templates if the strategies table is empty.

    Reads templates from trading/templates.py and inserts them as
    ``is_system=True`` rows.  Skips if any system strategies already exist
    to avoid duplicates on subsequent restarts.
    """
    import uuid as _uuid
    from sqlalchemy import select

    from .db import AsyncSessionLocal
    from .models import Strategy
    from .trading.templates import TEMPLATES

    async with AsyncSessionLocal() as session:
        # Load existing system strategy slugs
        existing_stmt = select(Strategy).where(
            Strategy.is_system == True  # noqa: E712
        )
        existing = (await session.execute(existing_stmt)).scalars().all()
        existing_slugs = {
            (s.definition_json or {}).get("strategy_slug")
            for s in existing
        }

        # Insert only templates whose slug is not already in the DB
        inserted = 0
        for tmpl in TEMPLATES:
            slug = tmpl["definition_json"].get("strategy_slug")
            if slug in existing_slugs:
                continue
            strategy = Strategy(
                strategy_id=_uuid.uuid4(),
                user_id=None,
                name=tmpl["name"],
                description=tmpl["description"],
                strategy_type=tmpl["strategy_type"],
                category=tmpl.get("category"),
                timeframe=tmpl.get("timeframe"),
                asset_class=tmpl.get("asset_class"),
                definition_json=tmpl["definition_json"],
                is_public=True,
                is_system=True,
            )
            session.add(strategy)
            inserted += 1

        if inserted:
            await session.commit()
            logger.info("system_strategies_seeded", count=inserted)
        else:
            logger.info("system_strategies_already_seeded", count=len(existing))


@app.on_event("startup")
async def _startup_checks():
    """Validate critical configuration on startup.

    Performs the following checks and raises RuntimeError on failure:
    - JWT secret is not the default placeholder
    - LOG_LEVEL is not DEBUG when ENVIRONMENT=production (P7.6)
    """
    validate_jwt_config()

    # P7.6 — Block debug logging in production to prevent sensitive data leakage
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    _env = os.getenv("ENVIRONMENT", "development").lower()
    if log_level == "DEBUG" and _env == "production":
        raise RuntimeError(
            "LOG_LEVEL=DEBUG is not allowed in production — "
            "debug logs can expose sensitive data such as query parameters, "
            "account balances, and authentication tokens. "
            "Set LOG_LEVEL=INFO or higher."
        )

    logger.info("startup_checks_passed", log_level=log_level, env=_env)

    # Warn if INTERNAL_NEWS_KEY is weak or using a known default
    _news_key = os.getenv("INTERNAL_NEWS_KEY", "")
    _weak_keys = {"", "please-change-me", "dev_internal_news_key_not_for_production"}
    if _news_key in _weak_keys:
        logger.warning(
            "internal_news_key_weak",
            detail="endpoint is effectively unprotected — generate with: openssl rand -hex 32",
        )

    # Seed system strategies from templates on first run
    await _seed_system_strategies()


# ── Middleware stack (registered last → executes first) ──────────────────────

# 1. Rate limiting — outermost so limits apply before any other processing.
app.add_middleware(SlowAPIMiddleware)

# 2. CORS — restricted to known origins with explicit methods/headers.
_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins.split(",")],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Correlation-ID", "X-Bot-Api-Key"],
)


# 3. Security headers middleware (P6.2) ─────────────────────────────────────
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Injects security headers on every response.

    Provides a defence-in-depth layer for cases where nginx is not in front
    of the backend (e.g. direct development access or container-to-container
    calls).  nginx adds the same headers at the edge for production traffic.

    Headers set:
        Strict-Transport-Security — enforce HTTPS for 1 year, including subdomains
        Content-Security-Policy   — restrictive default; block framing
        X-Content-Type-Options    — prevent MIME-type sniffing
        X-Frame-Options           — prevent clickjacking via iframes
        Referrer-Policy           — limit referrer leakage
        Permissions-Policy        — disable unused browser features
        Cache-Control             — prevent sensitive API responses from caching
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
        response.headers.setdefault(
            "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'"
        )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Referrer-Policy", "strict-origin-when-cross-origin"
        )
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=()",
        )
        # Prevent API responses from being stored in shared caches
        response.headers.setdefault(
            "Cache-Control", "no-store, no-cache, must-revalidate, private"
        )
        return response


app.add_middleware(SecurityHeadersMiddleware)


# 4. Request body size limit (P6.5) ────────────────────────────────────────
_MAX_BODY_BYTES = int(os.getenv("MAX_REQUEST_BODY_BYTES", str(10 * 1024 * 1024)))  # 10 MB


class RequestBodySizeMiddleware(BaseHTTPMiddleware):
    """Reject requests whose Content-Length exceeds MAX_REQUEST_BODY_BYTES.

    Prevents Denial-of-Service attacks where a client sends a huge payload
    to exhaust server memory.  The limit defaults to 10 MB and can be tuned
    via the MAX_REQUEST_BODY_BYTES environment variable.

    Returns HTTP 413 Payload Too Large with a descriptive JSON body.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > _MAX_BODY_BYTES:
            return JSONResponse(
                status_code=413,
                content={
                    "detail": (
                        f"Request payload exceeds the maximum allowed size "
                        f"({_MAX_BODY_BYTES // (1024 * 1024)} MB)."
                    )
                },
            )
        return await call_next(request)


app.add_middleware(RequestBodySizeMiddleware)


# 5. Request logging middleware ──────────────────────────────────────────────
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs every request with method, path, status code, and duration.

    Paths containing 'password' or 'token' are logged with the path
    truncated to prevent accidental credential leakage into log files.
    """

    _SENSITIVE = ("password", "token", "secret")

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        path = request.url.path
        # Redact paths that look like they carry sensitive route segments
        if any(s in path.lower() for s in self._SENSITIVE):
            path = path.split("?")[0]  # strip query string only
        logger.info(
            "http_request",
            method=request.method,
            path=path,
            status=response.status_code,
            duration_ms=round(duration_ms, 1),
        )
        return response


app.add_middleware(RequestLoggingMiddleware)


# 6. Correlation ID middleware ───────────────────────────────────────────────
class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """Generates a UUID correlation ID per request.

    Binds the ID to structlog's contextvars so all log lines within the
    request carry it automatically.  Echoes the ID in the
    ``X-Correlation-ID`` response header for client-side tracing.

    Also clears any stale contextvars left over from previous requests on
    the same worker greenlet.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        structlog.contextvars.clear_contextvars()
        correlation_id = str(uuid.uuid4())
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response


app.add_middleware(CorrelationIDMiddleware)


# ── Routes — all under /api/v1/ prefix (P7.18) ───────────────────────────────
_V1 = "/api/v1"

app.include_router(auth_routes.router, prefix=_V1)
app.include_router(accounts.router, prefix=_V1)
app.include_router(transactions.router, prefix=_V1)
app.include_router(portfolio.router, prefix=_V1)
app.include_router(orders.router, prefix=_V1)
app.include_router(admin.router, prefix=_V1)
app.include_router(market.router, prefix=f"{_V1}/market", tags=["market"])
app.include_router(holdings.router, prefix=f"{_V1}/holdings", tags=["holdings"])
app.include_router(news.router, prefix=_V1)
app.include_router(portfolio_manager.router, prefix=_V1)
app.include_router(portfolio_rules.router, prefix=_V1)
app.include_router(chart_templates.router, prefix=_V1)
app.include_router(feedback.router, prefix=_V1)
app.include_router(guide.router, prefix=_V1)
app.include_router(reports.router, prefix=_V1)
app.include_router(watchlists.router, prefix=_V1)
app.include_router(trading.router, prefix=_V1)
app.include_router(alerts.router, prefix=_V1)
app.include_router(import_routes.router, prefix=_V1)
app.include_router(degiro_routes.router, prefix=_V1)
app.include_router(scanner.router, prefix=_V1)
app.include_router(metrics_routes.router, prefix=_V1)
app.include_router(internal_portfolio.router, prefix=_V1)
app.include_router(analysis_routes.router, prefix=_V1)

# Register the 30-day news retention cleanup background task (Phase 9).
register_retention_task(app)

# Register the outcome checker that validates LLM scoring accuracy.
register_outcome_checker(app)

# Register the daily purge of soft-deleted accounts past their 30-day window.
register_deletion_purge(app)


# ── Health & observability endpoints ─────────────────────────────────────────

@app.get("/health", tags=["health"])
async def health():
    """Deep health check — probes DB and Redis concurrently.

    Returns HTTP 200 if at least one dependency is reachable, 503 only
    when both DB and Redis are unreachable.  Monitoring tools should alert
    on 503 or on individual component failures in the body.

    Returns:
        dict: {status, db, redis, timestamp}
    """
    db_result, redis_result = await asyncio.gather(check_db(), check_redis())
    db_ok = db_result["ok"]
    redis_ok = redis_result["ok"]
    all_down = not db_ok and not redis_ok
    body = {
        "status": "ok" if not all_down else "degraded",
        "db": {
            "status": "ok" if db_ok else "error",
            "latency_ms": db_result["latency_ms"],
            "error": db_result.get("error"),
        },
        "redis": {
            "status": "ok" if redis_ok else "error",
            "latency_ms": redis_result["latency_ms"],
            "error": redis_result.get("error"),
        },
        "timestamp": time.time(),
    }
    return JSONResponse(content=body, status_code=503 if all_down else 200)


@app.get("/metrics", tags=["observability"])
async def metrics(current_user=Depends(get_current_admin)):
    """Worker heartbeat metrics — admin only.

    Returns uptime, per-worker last-seen timestamps, jobs processed,
    and last error strings sourced from Redis heartbeat keys.

    Returns:
        dict: {uptime_seconds, workers: {name: {...}}}
    """
    worker_data = await get_worker_metrics()
    return {
        "uptime_seconds": round(time.monotonic() - APP_START_TIME, 1),
        "workers": worker_data,
    }
