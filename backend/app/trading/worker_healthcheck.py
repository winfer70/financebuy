"""
worker_healthcheck.py — Docker HEALTHCHECK script for TickerTap arq workers.

Reads the worker's heartbeat key from Redis and exits with code 0 (healthy)
if the key exists and is fresh, or code 1 (unhealthy) if it is missing,
stale, or unreachable.

Usage:
    python -m app.trading.worker_healthcheck <worker_name> <max_age_seconds>

Arguments:
    worker_name       Logical worker name, e.g. "alert-worker".
    max_age_seconds   Maximum acceptable age of the heartbeat in seconds.

Exit codes:
    0 — healthy (heartbeat found and within max_age_seconds)
    1 — unhealthy (key missing, stale, or Redis unreachable)

Example Docker HEALTHCHECK stanza:
    HEALTHCHECK --interval=60s --timeout=5s --start-period=15s --retries=3 \
        CMD python -m app.trading.worker_healthcheck alert-worker 600
"""

import os
import sys
import time


def main() -> None:
    """Entry point: parse args, query Redis, print status, exit with code.

    Reads REDIS_URL from environment (default: redis://redis:6379/0).
    Uses the synchronous redis client to avoid asyncio startup overhead.
    """
    if len(sys.argv) < 3:
        print("Usage: worker_healthcheck.py <worker_name> <max_age_seconds>")
        sys.exit(1)

    worker_name = sys.argv[1]
    try:
        max_age = int(sys.argv[2])
    except ValueError:
        print(f"Invalid max_age_seconds: {sys.argv[2]}")
        sys.exit(1)

    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    key = f"tickertap:worker:heartbeat:{worker_name}"

    try:
        # Use synchronous redis client — avoids asyncio event loop startup cost
        # in a short-lived health check process.
        import redis as sync_redis  # noqa: PLC0415

        client = sync_redis.Redis.from_url(
            redis_url,
            socket_connect_timeout=2,
            socket_timeout=2,
            decode_responses=True,
        )
        val = client.get(key)
        client.close()

        if val is None:
            print(f"UNHEALTHY: No heartbeat key for {worker_name}")
            sys.exit(1)

        age = time.time() - float(val)
        if age > max_age:
            print(f"UNHEALTHY: {worker_name} heartbeat is {age:.0f}s old (max {max_age}s)")
            sys.exit(1)

        print(f"HEALTHY: {worker_name} last seen {age:.0f}s ago")
        sys.exit(0)

    except Exception as e:
        print(f"UNHEALTHY: Health check error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
