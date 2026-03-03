#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Wait for Docker daemon to be ready (up to 60 seconds)
echo "[tickertap] Waiting for Docker daemon..."
for i in $(seq 1 30); do
    if /usr/bin/docker info > /dev/null 2>&1; then
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "[tickertap] ERROR: Docker daemon did not become ready in time." >&2
        exit 1
    fi
    sleep 2
done

echo "[tickertap] Starting development containers..."
/usr/bin/docker compose -f "$PROJECT_DIR/docker-compose.yml" up -d --remove-orphans

echo "[tickertap] Containers started."
/usr/bin/docker compose -f "$PROJECT_DIR/docker-compose.yml" ps
