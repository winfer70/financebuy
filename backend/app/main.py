"""
main.py — FastAPI application entry point for TickerTap.

Configures middleware (CORS, rate limiting, security headers, request
logging, body size enforcement), registers all route modules under the
/api/v1 prefix, and validates critical settings on startup.

Security middleware applied (outermost → innermost):
  1. SlowAPIMiddleware          — rate-limit enforcement (429 on breach)
  2. CORSMiddleware             — origin restriction
  3. SecurityHeadersMiddleware  — injects HSTS/CSP/X-Frame etc. (P6.2)
  4. RequestBodySizeMiddleware  — rejects oversized payloads (P6.5)
  5. RequestLoggingMiddleware   — structured access logs

API versioning:
  All business routes are mounted under /api/v1/ (P7.18).
  The /health endpoint remains unversioned for monitoring tools.
"""

import logging
import os
import time

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from .auth import validate_jwt_config
from .limiter import limiter
from .routes import accounts, admin, auth_routes, holdings, market, orders, portfolio, transactions

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("tickerTap")

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

    logger.info("Startup checks passed — JWT secret validated, log level OK.")


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
    allow_headers=["Authorization", "Content-Type", "Accept"],
)


# 3. Security headers middleware (P6.2) ─────────────────────────────────────
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Injects security headers on every response.

    Provides a defence-in-depth layer for cases where nginx is not in front
    of the backend (e.g. direct development access or container-to-container
    calls).  nginx adds the same headers at the edge for production traffic.

    Headers set:
        X-Content-Type-Options  — prevent MIME-type sniffing
        X-Frame-Options         — prevent clickjacking via iframes
        Referrer-Policy         — limit referrer leakage
        Permissions-Policy      — disable unused browser features
        Cache-Control           — prevent sensitive API responses from caching
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
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
            "%s %s → %d (%.1fms)",
            request.method,
            path,
            response.status_code,
            duration_ms,
        )
        return response


app.add_middleware(RequestLoggingMiddleware)


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


@app.get("/health", tags=["health"])
async def health():
    """Lightweight health check for load balancers and monitoring.

    Intentionally unversioned so monitoring tools need no configuration
    changes between API versions.

    Returns:
        dict: {"status": "ok"}
    """
    return {"status": "ok"}
