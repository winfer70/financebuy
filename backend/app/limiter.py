"""
limiter.py — Shared SlowAPI rate-limiter instance for TickerTap.

Centralised here to avoid circular imports: main.py registers the middleware
and exception handler; route modules decorate endpoints with @limiter.limit().

Key-function: client IP address (X-Forwarded-For respected by SlowAPI when
the app sits behind a trusted proxy such as nginx).
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

# Single application-wide limiter instance.
# Storage defaults to in-memory; set RATELIMIT_STORAGE_URL=redis://... in .env
# to use Redis for persistence across worker restarts / multiple processes.
limiter = Limiter(key_func=get_remote_address)
