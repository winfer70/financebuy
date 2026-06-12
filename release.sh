#!/bin/bash
# release.sh - tickerTap production release
# Run from local dev machine. Merges tradingAI0.1 -> main, tags, deploys to REDACTED.
# Usage: ./release.sh
set -e

NODE_IP="REDACTED"
NODE_USER="REDACTED420"
TARGET_DIR="/home/REDACTED420/projects/finance/tickerTap"
INTEGRATION_BRANCH="tradingAI0.1"
DB_CONTAINER="tickertap-db"
DB_NAME="tickertap"
DB_USER="postgres"
KUMA_PUSH_URL=""  # TODO: create Push monitor in REDACTED:3001, paste URL here

# ── 1. Tag and push ──────────────────────────────────────────────────────────
echo "[1/6] Merging $INTEGRATION_BRANCH -> main..."
git checkout main && git pull origin main
git merge "$INTEGRATION_BRANCH" --no-edit
VERSION="v$(date +%Y.%m.%d-%H%M)"
git tag -a "$VERSION" -m "Release $VERSION"
git push origin main --tags
git checkout "$INTEGRATION_BRANCH"
echo "Tagged $VERSION"

# ── 2-6. Remote deploy ───────────────────────────────────────────────────────
echo "[2/6] Connecting to $NODE_USER@$NODE_IP..."
ssh "$NODE_USER@$NODE_IP" bash << ENDSSH
set -e
cd "$TARGET_DIR"

echo "[3/6] Backing up postgres..."
mkdir -p ./backups
if docker ps -q -f name="$DB_CONTAINER" | grep -q .; then
  docker compose --env-file .env.prod exec -T "$DB_CONTAINER" pg_dump -U "$DB_USER" "$DB_NAME" \
    > ./backups/backup_\$(date +%Y%m%d_%H%M%S).sql
  echo "Backup saved."
else
  echo "WARNING: DB container not running, skipping backup."
fi

echo "[4/6] Pulling code..."
git fetch --tags && git checkout main && git pull origin main

echo "[5/6] Rebuilding containers..."
docker compose --env-file .env.prod down && docker compose --env-file .env.prod up -d --build

echo "[6/6] Running Alembic migrations..."
sleep 4
docker compose --env-file .env.prod exec -T app alembic upgrade head
echo "Migrations done."
ENDSSH

# ── Uptime Kuma ping ─────────────────────────────────────────────────────────
if [ -n "$KUMA_PUSH_URL" ]; then
  curl -s "${KUMA_PUSH_URL}?status=up&msg=${VERSION}&ping=" > /dev/null
  echo "Kuma notified."
fi

echo ""
echo "tickerTap $VERSION deployed."
