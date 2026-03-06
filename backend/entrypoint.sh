#!/bin/bash
# entrypoint.sh — TickerTap backend container entrypoint.
#
# Waits for PostgreSQL to be ready, runs Alembic migrations,
# then starts the Uvicorn application server.

set -e

# ── Wait for PostgreSQL to accept connections ────────────────────────────────
# The Docker healthcheck on the db service isn't always sufficient; this
# retry loop guarantees the app container won't crash if the database is
# still initialising.
MAX_RETRIES=30
RETRY_INTERVAL=2

echo "Waiting for database to be ready..."
for i in $(seq 1 $MAX_RETRIES); do
  if python3 -c "
import socket, os, sys
host = os.getenv('DB_HOST', 'db')
port = int(os.getenv('DB_PORT', '5432'))
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    s.settimeout(2)
    s.connect((host, port))
    s.close()
    sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null; then
    echo "Database is ready (attempt $i/$MAX_RETRIES)."
    break
  fi

  if [ "$i" -eq "$MAX_RETRIES" ]; then
    echo "ERROR: Database not ready after $MAX_RETRIES attempts. Exiting."
    exit 1
  fi

  echo "Database not ready yet (attempt $i/$MAX_RETRIES). Retrying in ${RETRY_INTERVAL}s..."
  sleep $RETRY_INTERVAL
done

# ── Run Alembic migrations ───────────────────────────────────────────────────
echo "Running database migrations..."
alembic -c /app/alembic.ini upgrade head

# ── Start the application ────────────────────────────────────────────────────
echo "Starting application..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
