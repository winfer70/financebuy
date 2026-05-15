"""
logging_config.py — Centralized structlog configuration for TickerTap.

Used by both the FastAPI app and standalone arq workers. Import and call
configure_structlog() once at process startup. Idempotent — safe to call
multiple times due to the _configured guard.

In production (ENVIRONMENT=production), emits JSON lines. In development,
emits a human-readable console format (colors disabled for Docker logs).

Bridges stdlib logging (uvicorn, sqlalchemy, arq) through structlog
formatters so all log output shares the same structure and destination.
"""

import logging
import os

import structlog

_configured = False


def configure_structlog() -> None:
    """Configure structlog with JSON renderer in production, console in dev.

    Reads ENVIRONMENT and LOG_LEVEL from env vars. Idempotent — safe to
    call multiple times; subsequent calls are no-ops.

    Inputs:  ENVIRONMENT env var ("production" → JSONRenderer, else ConsoleRenderer)
             LOG_LEVEL env var  ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
    Outputs: None — mutates global structlog configuration state.
    """
    global _configured
    if _configured:
        return
    _configured = True

    log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    environment = os.getenv("ENVIRONMENT", "development").lower()

    # Choose renderer based on environment
    if environment == "production":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=False)

    structlog.configure(
        processors=[
            # Merge request-scoped context vars (user_id, worker, job_id, etc.)
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Bridge stdlib logging (uvicorn, sqlalchemy, arq) through structlog format
    logging.basicConfig(
        format="%(message)s",
        level=log_level,
    )
