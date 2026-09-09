"""
limiter.py — Shared SlowAPI rate-limiter instance for TickerTap.

Centralised here to avoid circular imports: main.py registers the middleware
and exception handler; route modules decorate endpoints with @limiter.limit().

Key-function: client IP address (X-Forwarded-For respected by SlowAPI when
the app sits behind a trusted proxy such as nginx).

Storage backend: Redis (via REDIS_URL env var) for persistence across worker
restarts and correct counting in multi-process deployments.
"""

import os

from slowapi import Limiter
from slowapi.util import get_remote_address

_storage_uri = os.getenv("RATE_LIMIT_STORAGE") or os.getenv("REDIS_URL", "redis://localhost:6379/0")

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=_storage_uri,
)
