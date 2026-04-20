"""
dependencies.py — Shared FastAPI dependencies for TickerTap.

Re-exports the canonical get_current_user dependency from auth_routes so that
all route modules can import from a single location.  This resolves the
previous inconsistency where dependencies.py returned a string user_id while
auth_routes.py returned a full User object.

Usage in route modules:
    from ..dependencies import get_current_user
"""

from .routes.auth_routes import get_current_user, get_current_admin  # noqa: F401
